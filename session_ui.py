"""Session state, camera dashboard, and dependency-free PDF receipts."""
from datetime import datetime
from pathlib import Path
import cv2
import numpy as np


def duration(seconds):
    minutes, seconds = divmod(int(seconds), 60)
    return f"{minutes:02d}:{seconds:02d}"


class Session:
    def __init__(self, target=10):
        self.target = target
        self.reset()

    def reset(self):
        self.count = 0
        self.elapsed = 0.0
        self.running_since = None
        self.completed_at = None

    def seconds(self, now):
        return self.elapsed + (now - self.running_since if self.running_since is not None else 0)

    def pause(self, now):
        self.elapsed = self.seconds(now)
        self.running_since = None

    def start(self, now):
        if self.completed_at is None and self.running_since is None:
            self.running_since = now

    def add(self, count, now):
        if self.running_since is None or self.completed_at is not None:
            return
        # Model predictions may be NumPy scalars; keep transport/report values native.
        self.count = min(self.target, self.count + int(count))
        if self.count == self.target:
            self.pause(now)
            self.completed_at = datetime.now().astimezone()

    def export(self, path, exercise):
        if self.completed_at is None:
            raise ValueError("Finish the session before exporting.")
        exercise_name = {"Dumbbell curl": "Dumbbell curls",
                         "Floor push-up": "Floor push-ups",
                         "Shoulder press": "Shoulder presses",
                         "Bent-over row": "Bent-over rows"}.get(exercise, exercise)
        lines = [f"{exercise_name} completed: {self.count}",
                 f"Time taken: {duration(self.elapsed)}",
                 self.completed_at.strftime('%B %d, %Y')]
        stream = b"0.08 0.13 0.20 rg\n"
        for i, line in enumerate(lines):
            escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            stream += f"BT /F1 14 Tf 56 {760 - i * 28} Td ({escaped}) Tj ET\n".encode("cp1252", "replace")
        objects = [b"<< /Type /Catalog /Pages 2 0 R >>",
                   b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
                   b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
                   b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
                   b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"endstream"]
        data = bytearray(b"%PDF-1.4\n")
        offsets = [0]
        for i, obj in enumerate(objects, 1):
            offsets.append(len(data))
            data.extend(f"{i} 0 obj\n".encode() + obj + b"\nendobj\n")
        start = len(data)
        data.extend(b"xref\n0 6\n0000000000 65535 f \n")
        for offset in offsets[1:]:
            data.extend(f"{offset:010d} 00000 n \n".encode())
        data.extend(f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n".encode())
        Path(path).write_bytes(data)


def dashboard(frame, exercises, selected, session, active, now, status, movement, color, notice):
    canvas = np.full((820, 1160, 3), (24, 20, 17), dtype=np.uint8)
    buttons = []
    white, muted, accent = (243, 240, 231), (162, 151, 139), (180, 231, 106)

    def text(value, x, y, size=.55, ink=white):
        cv2.putText(canvas, value, (x, y), cv2.FONT_HERSHEY_SIMPLEX, size, ink, 1, cv2.LINE_AA)

    def card(x, y, w, h, fill=(39, 33, 28)):
        cv2.rectangle(canvas, (x, y), (x+w, y+h), fill, -1)

    def button(title, x, y, w, key, chosen=False):
        card(x, y, w, 42, (77, 82, 48) if chosen else (55, 46, 38))
        text(title, x+12, y+27, .49, accent if chosen else white)
        buttons.append((x, y, x+w, y+42, key))

    text("FORM", 28, 43, 1, accent)
    text("MOVE WITH INTENTION", 160, 41, .43, muted)
    text("YOUR PERSONAL MOVEMENT STUDIO", 28, 85, .45, muted)
    text("A little progress. Every session.", 28, 122, .85)
    card(28, 150, 790, 540)
    h, w = frame.shape[:2]
    scale = min(790/w, 492/h)
    pw, ph = round(w*scale), round(h*scale)
    x, y = 28+(790-pw)//2, 174+(492-ph)//2
    canvas[y:y+ph, x:x+pw] = cv2.resize(frame, (pw, ph))
    text("LIVE CAMERA", 44, 175, .42, accent)
    card(840, 150, 292, 540)
    text("YOUR SESSION", 860, 183, .45, muted)
    text("Choose your movement", 860, 218, .57)
    for i, (_, name) in enumerate(exercises):
        button(f"{i+1}  {name}", 860, 238+i*50, 252, ord("1")+i, i == selected)
    text("REPETITION GOAL", 860, 465, .42, muted)
    button("-", 860, 481, 46, ord("-"))
    text(str(session.target), 938, 510, .85, accent)
    button("+", 1066, 481, 46, ord("+"))
    text("Set goal before starting", 860, 548, .40, muted)
    button("Pause" if active else "Start session", 860, 567, 252, ord(" "), True)
    button("New session", 860, 622, 252, ord("r"))
    card(28, 707, 1104, 86)
    text(f"{session.count} / {session.target}", 48, 746, .85, accent)
    text("REPS COMPLETED", 48, 775, .37, muted)
    text(duration(session.seconds(now)), 270, 746, .85)
    text("ACTIVE TIME", 270, 775, .37, muted)
    text(status[:64], 440, 737, .48, color)
    text((notice or movement)[:80], 440, 764, .40, muted)
    cv2.rectangle(canvas, (28, 697), (1132, 700), (55, 46, 38), -1)
    progress = round(1104 * session.count/session.target)
    if progress:
        cv2.rectangle(canvas, (28, 697), (28+progress, 700), accent, -1)
    if session.completed_at:
        card(140, 260, 650, 330, (50, 43, 34))
        text("SESSION COMPLETE", 180, 310, .48, accent)
        text("You showed up. Nice work.", 180, 358, .85)
        text(f"{session.count} reps completed   /   {duration(session.elapsed)} active time", 180, 404, .58)
        text(session.completed_at.strftime("%B %d, %Y  /  %H:%M %Z"), 180, 439, .49, muted)
        button("Export PDF (E)", 180, 470, 250, ord("e"), True)
        button("New session (R)", 450, 470, 250, ord("r"))
        text(notice[:76] if notice else "Save a record of today's progress.", 180, 553, .41, muted)
        buttons = buttons[-2:]
    elif exercises[selected][0] != "bicep_curl":
        button("Log completed rep (C)", 530, 632, 268, ord("c"))
    return canvas, buttons
