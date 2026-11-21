"""Run the trained clip classifier against a rolling webcam window."""
import argparse
from session_ui import Session, dashboard
from model_assets import movement_model as load_movement_model
from contextlib import ExitStack
import sys
import time
from collections import deque

import cv2
import joblib
import mediapipe as mp
import numpy as np

from train_form import ROOT, make_detector, pose_row, summarize

EXERCISES = [
    ("push_up", "Floor push-up"),
    ("bicep_curl", "Dumbbell curl"),
    ("shoulder", "Shoulder press"),
    ("back", "Bent-over row"),
]
WINDOW = "Exercise Form | Live Camera"
SECONDS = 4
MOVEMENT_WINDOW = 28
MIN_MOVEMENT_SAMPLES = 12
MOTION_SECONDS = 1.5


def label(image, content, position, color=(240, 240, 240), size=0.56):
    cv2.putText(image, content, position, cv2.FONT_HERSHEY_SIMPLEX,
                size, color, 1, cv2.LINE_AA)


def landmark_box(pose, width, height):
    points = [(p.x, p.y) for p in pose
              if p.visibility >= 0.5 and p.presence >= 0.5 and 0 <= p.x <= 1 and 0 <= p.y <= 1]
    if len(points) < 3:
        return None
    xs, ys = zip(*points)
    return (
        (max(0, round((min(xs) - 0.035) * width)),
         max(0, round((min(ys) - 0.035) * height))),
        (min(width - 1, round((max(xs) + 0.035) * width)),
         min(height - 1, round((max(ys) + 0.035) * height))),
    )


def exercise_signals(pose, aspect, exercise, row):
    """Measure elbow motion only where the arm and supporting body are visible."""
    signals = np.full(2, np.nan)
    for side in range(2):
        arm = [11 + side, 13 + side, 15 + side]
        hip = 23 + side
        joints = (*arm, hip, 27 + side) if exercise == "push_up" else (*arm, hip)
        points = [pose[index] for index in joints]
        if any(p.visibility < 0.55 or p.presence < 0.55
               or not (0 <= p.x <= 1 and 0 <= p.y <= 1) for p in points):
            continue
        shoulder, _, wrist, pelvis = points[:4]
        horizontal = abs(shoulder.x - pelvis.x) * aspect
        vertical = abs(shoulder.y - pelvis.y)
        if exercise == "push_up" and horizontal < vertical:
            continue
        if exercise == "back" and horizontal < 0.40 * vertical:
            continue
        if exercise == "bicep_curl" and horizontal > 0.8 * vertical:
            continue
        if exercise == "shoulder" and wrist.y > shoulder.y + 0.15 * vertical:
            continue
        if exercise == "back":
            # A diagonal view can flatten the apparent elbow bend.
            torso_length = np.hypot(horizontal, vertical)
            if torso_length > 0.04:
                signals[side] = (wrist.y - pelvis.y) / torso_length
        else:
            signals[side] = np.degrees(np.arccos(np.clip(row[side], -1, 1)))
    return signals


def moving_arms(samples, now, exercise):
    recent = np.array([signals for timestamp, _, signals in samples
                       if timestamp >= now - MOTION_SECONDS])
    if len(recent) < 5:
        return []
    moving = []
    minimum_excursion = 0.18 if exercise == "back" else 18
    for side, arm in enumerate(recent.T):
        visible = arm[np.isfinite(arm)]
        if np.isfinite(arm[-1]) and len(visible) >= max(5, 0.7 * len(arm)):
            low, high = np.percentile(visible, [10, 90])
            if high - low >= minimum_excursion:
                moving.append(side)
    return moving


class CurlTracker:
    """Detect the top of a lift; require extension only to rearm the next rep."""

    def __init__(self):
        self.readings = deque(maxlen=3)
        self.reset()

    def reset(self):
        self.readings.clear()
        self.baseline = None
        self.started = None
        self.phase = None
        self.verified = False
        self.counted = False
        self.extreme = 0
        self.last_progress = None
        self.last_visible = None

    def update(self, pose, side, aspect, now, image_moving):
        joints = [pose[index + side] for index in (11, 13, 15)] if pose else []
        if not joints or any(
            p.visibility < 0.55 or p.presence < 0.55 or not (0 <= p.x <= 1 and 0 <= p.y <= 1)
            for p in joints
        ):
            if self.last_visible is not None and now - self.last_visible > 0.4:
                self.reset()
            return False
        self.last_visible = now
        shoulder, elbow, wrist = np.array([(p.x * aspect, p.y) for p in joints])
        upper, lower = shoulder - elbow, wrist - elbow
        upper_length, lower_length = np.linalg.norm(upper), np.linalg.norm(lower)
        if min(upper_length, lower_length) < 0.025:
            return False
        cosine = np.dot(upper, lower) / (upper_length * lower_length)
        angle = np.degrees(np.arccos(np.clip(cosine, -1, 1)))
        reach = np.linalg.norm(wrist - shoulder) / (upper_length + lower_length)
        wrist_height = (shoulder[1] - wrist[1]) / (upper_length + lower_length)
        upper_x, upper_y = upper / upper_length
        self.readings.append((angle, reach, wrist_height, upper_x, upper_y))
        if len(self.readings) < 3:
            return False
        angle, reach, wrist_height, upper_x, upper_y = np.median(self.readings, axis=0)

        if self.phase == "lifting" and (now - self.last_progress > 0.85 or now - self.started > 9):
            self.reset()
        if self.baseline is None:
            if angle >= 120:
                self.baseline = (angle, reach, wrist_height, upper_x, upper_y)
            return False

        start_angle, start_reach, start_height, start_x, start_y = self.baseline
        bend = start_angle - angle
        steady_upper_arm = upper_x * start_x + upper_y * start_y >= 0.78
        if self.phase is None:
            if angle >= start_angle:
                self.baseline = (angle, reach, wrist_height, upper_x, upper_y)
            elif (bend >= 36 and start_reach - reach >= 0.10 and wrist_height - start_height >= 0.20
                  and steady_upper_arm and upper_y <= -0.35 and image_moving):
                self.phase = "lifting"
                self.started = self.last_progress = now
                self.extreme = bend
            return False

        if not steady_upper_arm or upper_y > -0.35:
            self.reset()
            return False
        # The top is a latched state: holding or jittering cannot add reps.
        # Lowering only rearms a new lift; it never awards a repetition.
        if self.phase == "top":
            if bend <= 20:
                self.reset()
            return False
        if not image_moving:
            return False

        # A clearly bent arm or a short hold at its highest point is the top.
        # Preserve the previous minimum excursion for shorter-range curls.
        at_top = angle <= 90 or (bend >= self.extreme - 4 and now - self.last_progress >= 0.25)
        if at_top and bend >= 40 and now - self.started >= 0.25:
            self.phase = "top"
            self.last_progress = now
            return True
        if bend >= self.extreme + 3:
            self.extreme, self.last_progress = bend, now
        elif bend <= self.extreme - 9:
            self.reset()
        return False



def detect_movement(model, samples, now, minimum_confidence=0):
    if len(samples) < MIN_MOVEMENT_SAMPLES:
        return None
    rows = [row for _, row, _ in samples]
    probabilities = model.predict_proba([summarize(rows[-MOVEMENT_WINDOW:])])[0]
    best = np.argmax(probabilities)
    if probabilities[best] < minimum_confidence:
        return None
    detected = model.classes_[best]
    if detected == "no_attempt":
        return None
    index = next(index for index, (exercise, _) in enumerate(EXERCISES) if exercise == detected)
    signals = [(timestamp, row, motion[index]) for timestamp, row, motion in samples]
    return detected if moving_arms(signals, now, detected) else None


def model_confirms_curl(model, samples, started):
    rows = [row for timestamp, row, _ in samples if timestamp >= started - 0.85]
    if len(rows) < 8:
        return False
    probabilities = model.predict_proba([summarize(rows[-MOVEMENT_WINDOW:])])[0]
    ranked = np.argsort(probabilities)
    best, runner_up = ranked[-1], ranked[-2]
    return (model.classes_[best] == "bicep_curl" and probabilities[best] >= 0.45
            and probabilities[best] - probabilities[runner_up] >= 0.10)


def run(camera_index, leds=(), bridge=None):
    leds = list(leds)
    models = joblib.load(ROOT / "form_models.joblib")
    movement_model = load_movement_model()
    movement_model.n_jobs = 1
    for model in models.values():
        model.n_jobs = 1
    camera = cv2.VideoCapture(camera_index)
    if not camera.isOpened():
        camera.release()
        raise RuntimeError(f"Could not open camera {camera_index}. Try another camera index.")
    session = Session()
    buttons = []
    notice = ""
    selected = 1
    active = False
    samples = deque()
    next_sample = next_prediction = last_image_motion = 0
    previous_gray = None
    box = None
    overlay = None
    curl_trackers = [CurlTracker(), CurlTracker()]
    curl_count = 0
    curl_feedback_until = 0
    movement = "Movement: paused"
    started = time.monotonic()
    status = "Select an exercise and press Space to start"
    color = (240, 240, 240)

    try:
        def on_click(event, x, y, flags, data):
            if event == cv2.EVENT_LBUTTONUP:
                for x0, y0, x1, y1, key in reversed(buttons):
                    if x0 <= x <= x1 and y0 <= y <= y1:
                        clicks.append(key)
                        break

        clicks = deque()
        if bridge is None:
            cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
            cv2.setMouseCallback(WINDOW, on_click)
            cv2.resizeWindow(WINDOW, 1160, 820)
        with make_detector() as detector:
            while True:
                ok, frame = camera.read()
                if not ok:
                    raise RuntimeError("The camera stopped returning frames.")
                now = time.monotonic() - started
                height, width = frame.shape[:2]
                if now >= next_sample:
                    next_sample = now + 0.125
                    scale = min(1, 640 / max(height, width))
                    sample = cv2.resize(frame, (round(width * scale), round(height * scale)))
                    rgb = cv2.cvtColor(sample, cv2.COLOR_BGR2RGB)
                    result = detector.detect_for_video(
                        mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), int(now * 1000)
                    )
                    pose = result.pose_landmarks[0] if result.pose_landmarks else None
                    box = landmark_box(pose, width, height) if pose is not None else None
                    gray = cv2.resize(cv2.cvtColor(sample, cv2.COLOR_BGR2GRAY),
                                      (96, 72), interpolation=cv2.INTER_AREA)
                    if previous_gray is not None and box is not None:
                        (x0, y0), (x1, y1) = box
                        crop = np.s_[y0 * 72 // height : (y1 * 72 // height) + 1,
                                     x0 * 96 // width : (x1 * 96 // width) + 1]
                        if cv2.absdiff(gray, previous_gray)[crop].mean() >= 0.8:
                            last_image_motion = now
                    previous_gray = gray
                    if active:
                        if pose is None or now - last_image_motion > 0.75:
                            overlay = None
                        selected_exercise = EXERCISES[selected][0]
                        if pose is None:
                            samples.clear()
                        else:
                            aspect = width / height
                            row = pose_row(pose, aspect)
                            signals = np.array([exercise_signals(pose, aspect, exercise, row)
                                                for exercise, _ in EXERCISES])
                            if np.isfinite(signals).any():
                                samples.append((now, row, signals))
                                while samples[0][0] < now - SECONDS:
                                    samples.popleft()
                            else:
                                samples.clear()
                        if selected_exercise == "bicep_curl":
                            recent_motion = now - last_image_motion <= 0.75
                            completed = 0
                            for side, tracker in enumerate(curl_trackers):
                                tracker.update(pose, side, width / height, now, recent_motion)
                                if tracker.phase == "top" and not tracker.counted:
                                    accepted = tracker.verified or model_confirms_curl(
                                        movement_model, samples, tracker.started
                                    )
                                    if accepted:
                                        tracker.counted = True
                                        tracker.verified = True
                                        completed += 1
                                elif tracker.phase is not None and not tracker.verified:
                                    tracker.verified = model_confirms_curl(
                                        movement_model, samples, tracker.started
                                    )
                            session.add(completed, now)
                            curl_count = session.count
                            if session.completed_at or session.awaiting_next_set:
                                active = False
                            if completed:
                                curl_feedback_until = now + 0.5
                                for led in leds[:]:
                                    try:
                                        led.write(b"B")
                                    except OSError as error:
                                        print(f"ESP32 LED disconnected: {error}", file=sys.stderr)
                                        leds.remove(led)
                            confirmed = recent_motion and now < curl_feedback_until
                            progressing = recent_motion and any(
                                tracker.verified and tracker.last_visible == now
                                for tracker in curl_trackers
                            )
                            overlay = "bicep_curl" if confirmed or progressing else None
                            movement = f"Completed curls (each arm): {curl_count}"
                            status = ("Curl rep detected" if confirmed else
                                      "Curl in progress" if progressing else "No attempt")
                            color = (130, 235, 155) if confirmed or progressing else (240, 240, 240)
                        elif pose is None:
                            samples.clear()
                            movement = "Movement: no attempt"
                            status = "No attempt | Step back so the camera can see your body"
                            color = (240, 240, 240)
                        else:
                            if now >= next_prediction:
                                next_prediction = now + 0.25
                                detected = None
                                if now - last_image_motion <= 0.75:
                                    detected = detect_movement(movement_model, samples, now)
                                overlay = detected
                                movement = "Movement: no attempt"
                                status = "No attempt | Waiting for recognizable exercise movement"
                                color = (240, 240, 240)
                                if detected is not None:
                                    movement = "Movement: " + dict(EXERCISES)[detected]
                                    if detected == selected_exercise:
                                        rows = [item for _, item, _ in samples]
                                        good = models[detected].predict([summarize(rows)])[0] == "good"
                                        status = "Good form detected" if good else "Possible form issue"
                                        color = (130, 235, 155) if good else (100, 210, 255)
                                    else:
                                        status = "Detected movement differs from the selected exercise"

                # Mirror camera pixels before drawing labels, so text stays readable.
                display_box = box
                if bridge is not None:
                    frame = cv2.flip(frame, 1)
                    if box is not None:
                        (x0, y0), (x1, y1) = box
                        display_box = ((width - 1 - x1, y0), (width - 1 - x0, y1))
                if display_box is not None:
                    title = "Person" if overlay is None else dict(EXERCISES)[overlay]
                    cv2.rectangle(frame, *display_box, (130, 235, 155), 2)
                    label(frame, title, (display_box[0][0] + 4, max(20, display_box[0][1] - 6)), (130, 235, 155))
                if bridge is not None:
                    bridge.publish(frame, session, selected, active, now, status, movement)
                    key = bridge.poll(session)
                else:
                    preview, buttons = dashboard(frame, EXERCISES, selected, session,
                        active, now, status, movement, color, notice)
                    cv2.imshow(WINDOW, preview)
                    key = cv2.waitKey(1) & 255
                    if key in (27, ord("q")) or cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                        break
                if clicks:
                    key = clicks.popleft()
                if key == ord("e") and session.completed_at:
                    from tkinter import Tk, filedialog
                    root = None
                    try:
                        root = Tk()
                        root.withdraw()
                        root.attributes("-topmost", True)
                        path = filedialog.asksaveasfilename(title="Save session report",
                            defaultextension=".pdf",
                            initialfile=session.completed_at.strftime("session-%Y-%m-%d-%H%M%S.pdf"),
                            filetypes=[("PDF document", "*.pdf")])
                        if path:
                            session.export(path, EXERCISES[selected][1])
                            notice = "PDF saved successfully."
                    except Exception as error:
                        notice = "Could not save PDF. Press E to try again."
                        print(f"PDF export failed: {error}", file=sys.stderr)
                    finally:
                        if root is not None:
                            root.destroy()
                elif key == ord("r"):
                    session.reset()
                    active = False
                    curl_count = 0
                    notice = ""
                    samples.clear()
                    overlay = None
                    for tracker in curl_trackers:
                        tracker.reset()
                    status = "Ready for a new session"
                    movement = "Movement: paused"
                elif key in (ord("-"), ord("+"), ord("=")):
                    if session.running_since is None and session.count == 0 and session.elapsed == 0:
                        session.target = max(1, min(999, session.target + (-1 if key == ord("-") else 1)))
                elif key == ord("c") and EXERCISES[selected][0] != "bicep_curl":
                    session.add(1, now)
                    if session.completed_at or session.awaiting_next_set:
                        active = False
                elif ord("1") <= key <= ord("4") and session.count == 0 and session.elapsed == 0 and not active:
                    for tracker in curl_trackers:
                        tracker.reset()
                    curl_count = 0
                    curl_feedback_until = 0
                    overlay = None
                    selected = key - ord("1")
                    movement = "Movement: no attempt" if active else "Movement: paused"
                    status = "Collecting movement..." if active else "Click Start to begin"
                    color = (240, 240, 240)
                    samples.clear()
                elif key == ord(" ") and session.completed_at is None:
                    overlay = None
                    for tracker in curl_trackers:
                        tracker.reset()
                    curl_feedback_until = 0
                    active = not active
                    if active:
                        session.start(now)
                    else:
                        session.pause(now)
                    movement = "Movement: no attempt" if active else "Movement: paused"
                    samples.clear()
                    status = "Starting..." if active else "Paused. Press Space to start"
                    color = (240, 240, 240)
    finally:
        camera.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument('--esp32-port', action='append', default=[], help='USB serial port; repeat for multiple boards')
    args = parser.parse_args()
    try:
        with ExitStack() as connections:
            leds = []
            if args.esp32_port:
                try:
                    import serial
                except ImportError:
                    parser.exit(1, "ESP32 support requires pyserial. See README.md.\n")
                for port in dict.fromkeys(port.upper() for port in args.esp32_port):
                    try:
                        leds.append(connections.enter_context(
                            serial.Serial(port, 115200, write_timeout=0.1)
                        ))
                    except OSError as error:
                        raise RuntimeError(f"Could not open ESP32 on {port}: {error}") from error
            run(args.camera, leds)
    except (OSError, RuntimeError) as error:
        parser.exit(1, f"{error}\n")
