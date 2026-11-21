"""Loopback-only desktop transport. Model and session state stay in Python."""
import json
import secrets
import threading
import tempfile
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class DesktopBridge:
    def __init__(self):
        self.lock = threading.Lock()
        self.commands = deque()
        self.frame = b''
        self.state = {'status': 'Loading movement models…', 'ready': False}
        self.report = None
        self.token = secrets.token_hex(24)
        self.last_seen = time.monotonic()
        self.connected = False

    def publish(self, frame, session, selected, active, now, status, movement):
        import cv2
        from live_camera import EXERCISES
        ok, encoded = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 82])
        with self.lock:
            if ok:
                self.frame = encoded.tobytes()
            self.state = dict(ready=True, count=session.count, target=session.target,
                elapsed=session.seconds(now), selected=selected, active=active,
                completed=session.completed_at.isoformat() if session.completed_at else None,
                status=status, movement=movement)
            if session.completed_at and self.report is None:
                with tempfile.TemporaryDirectory() as folder:
                    path = Path(folder) / 'session.pdf'
                    session.export(path, EXERCISES[selected][1])
                    self.report = path.read_bytes()
            elif not session.completed_at:
                self.report = None

    def poll(self, session):
        with self.lock:
            if not self.commands:
                return 255
            command = self.commands.popleft()
        if 'target' in command:
            if session.running_since is None and session.count == 0 and session.elapsed == 0:
                session.target = command['target']
            return 255
        return command['key']


def serve(bridge):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            route = self.path.split('?')[0]
            if route == '/state':
                bridge.last_seen = time.monotonic()
                bridge.connected = True
                with bridge.lock:
                    content = json.dumps({**bridge.state, 'token': bridge.token}).encode()
                mime = 'application/json'
            elif route == '/frame':
                with bridge.lock:
                    content = bridge.frame
                mime = 'image/jpeg'
            elif route == '/report':
                with bridge.lock:
                    content = bridge.report
                if content is None:
                    self.send_error(409)
                    return
                mime = 'application/pdf'
            elif route in ('/', '/app.js', '/style.css'):
                name = {'/':'index.html', '/app.js':'app.js', '/style.css':'style.css'}[route]
                content = (ROOT / 'desktop' / name).read_bytes()
                mime = {'/':'text/html', '/app.js':'text/javascript', '/style.css':'text/css'}[route]
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(content)))
            if route == '/report':
                self.send_header('Content-Disposition', 'attachment; filename="FORM-session.pdf"')
            self.end_headers()
            try:
                self.wfile.write(content)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_POST(self):
            if self.path != '/command' or self.headers.get('X-Form-Token') != bridge.token:
                self.send_error(403)
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 256:
                    raise ValueError()
                command = json.loads(self.rfile.read(length))
                if set(command) == {'target'}:
                    if type(command['target']) is not int or not 1 <= command['target'] <= 999:
                        raise ValueError()
                elif set(command) == {'key'}:
                    if command['key'] not in [32, 49, 50, 51, 52, 99, 114]:
                        raise ValueError()
                else:
                    raise ValueError()
                with bridge.lock:
                    if len(bridge.commands) < 20:
                        bridge.commands.append(command)
                self.send_response(204)
                self.end_headers()
            except (ValueError, TypeError):
                self.send_error(400)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f'FORM_URL=http://127.0.0.1:{server.server_port}', flush=True)
    return server


if __name__ == '__main__':
    bridge = DesktopBridge()
    server = serve(bridge)
    import sys
    if '--check' in sys.argv:
        from train_form import make_detector
        import joblib
        with make_detector():
            pass
        from model_assets import movement_model
        model = movement_model()
        joblib.load(ROOT / 'form_models.joblib')
        assert model.n_features_in_ == 60
        print('FORM runtime and model checks passed', flush=True)
        server.shutdown()
        sys.exit(0)
    if '--browser' in sys.argv:
        import subprocess
        import os
        edge = Path(os.environ.get('PROGRAMFILES(X86)', r'C:\Program Files (x86)')) / 'Microsoft/Edge/Application/msedge.exe'
        if not edge.exists():
            edge = Path(os.environ.get('PROGRAMFILES', r'C:\Program Files')) / 'Microsoft/Edge/Application/msedge.exe'
        if not edge.exists():
            raise RuntimeError('Microsoft Edge is required. Install Edge or run the Electron frontend.')
        subprocess.Popen([str(edge), f'--app=http://127.0.0.1:{server.server_port}',
                          '--window-size=1440,960', '--no-first-run'])
    def watch_window():
        import os
        while True:
            time.sleep(2)
            if time.monotonic() - bridge.last_seen > (25 if bridge.connected else 120):
                os._exit(0)
    threading.Thread(target=watch_window, daemon=True).start()
    try:
        from live_camera import run
        run(0, bridge=bridge)
    except Exception as error:
        import traceback
        traceback.print_exc()
        with bridge.lock:
            bridge.state = {'ready':False, 'error':True, 'status':str(error)}
        while True:
            time.sleep(1)
