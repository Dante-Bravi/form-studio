import argparse
from concurrent.futures import ProcessPoolExecutor
import json
import re
import shutil
from pathlib import Path
from zipfile import ZipFile

import cv2
import joblib
import mediapipe as mp
import numpy as np
from sklearn.ensemble import ExtraTreesClassifier
from sklearn.metrics import balanced_accuracy_score, classification_report
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GridSearchCV, StratifiedGroupKFold, cross_val_predict
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

ROOT = Path(__file__).resolve().parent
FOOTAGE = ROOT / "footage"
EXERCISES = {"bicep_curl", "push_up", "shoulder", "back"}
NAME = re.compile(r"subject_(\d+)_(.+)_(good|bad)_(front|side|diagonal)\.mp4", re.I)
JOINTS = [(11,13,15), (12,14,16), (13,11,23), (14,12,24),
          (11,23,25), (12,24,26), (23,25,27), (24,26,28)]


def make_detector():
    options = mp.tasks.vision.PoseLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=str(ROOT / "pose_landmarker_lite.task")),
        running_mode=mp.tasks.vision.RunningMode.VIDEO,
    )
    return mp.tasks.vision.PoseLandmarker.create_from_options(options)


def features(path):
    video = cv2.VideoCapture(str(path), cv2.CAP_FFMPEG, [cv2.CAP_PROP_N_THREADS, 1])
    fps = video.get(cv2.CAP_PROP_FPS) or 30
    stride = max(1, round(fps / 8))
    rows = []
    sampled = 0
    try:
        with make_detector() as detector:
            index = 0
            while video.grab():
                index += 1
                if (index - 1) % stride:
                    continue
                ok, frame = video.retrieve()
                if not ok:
                    continue
                sampled += 1
                height, width = frame.shape[:2]
                scale = min(1, 640 / max(height, width))
                if scale < 1:
                    frame = cv2.resize(frame, (round(width * scale), round(height * scale)))
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                result = detector.detect_for_video(
                    mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), round(index * 1000 / fps)
                )
                if not result.pose_landmarks:
                    continue
                rows.append(pose_row(result.pose_landmarks[0], width / height))
    finally:
        video.release()
    if len(rows) < max(8, sampled * 0.6):
        return None
    return summarize(rows)


def pose_row(pose, aspect):
    xy = np.array([[p.x * aspect, p.y] for p in pose])
    a, b, c = np.array(JOINTS).T
    u, v = xy[a] - xy[b], xy[c] - xy[b]
    angles = np.sum(u * v, axis=1) / np.maximum(
        np.linalg.norm(u, axis=1) * np.linalg.norm(v, axis=1), 1e-6
    )
    torso = (xy[11] + xy[12] - xy[23] - xy[24]) / 2
    return np.r_[angles, torso / max(np.linalg.norm(torso), 1e-6)]


def summarize(rows):
    sequence = np.asarray(rows)
    return np.r_[np.percentile(sequence, [5, 25, 50, 75, 95], axis=0).ravel(),
                 np.mean(np.abs(np.diff(sequence, axis=0)), axis=0)]


def prepare(archive):
    with ZipFile(archive) as source:
        for entry in source.infolist():
            filename = Path(entry.filename).name
            match = NAME.fullmatch(filename)
            if not match or match[2] not in EXERCISES:
                continue
            output = FOOTAGE / match[2] / filename
            output.parent.mkdir(exist_ok=True)
            if not output.exists() or output.stat().st_size != entry.file_size:
                with source.open(entry) as origin, output.open("wb") as target:
                    shutil.copyfileobj(origin, target)


def cache_features(video):
    saved = ROOT / "pose_features" / (video.stem + ".npy")
    if saved.exists():
        try:
            np.load(saved, allow_pickle=False)
            return
        except (ValueError, EOFError):
            pass
    row = features(video)
    temporary = saved.with_suffix(".part")
    with temporary.open("wb") as output:
        np.save(output, np.array([]) if row is None else row)
    temporary.replace(saved)


def model_search():
    trees = ExtraTreesClassifier(n_estimators=300, class_weight="balanced",
                                 random_state=23, n_jobs=1)
    return GridSearchCV(
        Pipeline([("classifier", trees)]),
        [
            {"classifier": [trees], "classifier__min_samples_leaf": [1, 3, 6]},
            {"classifier": [make_pipeline(StandardScaler(), SVC(class_weight="balanced"))],
             "classifier__svc__C": [0.5, 2, 8]},
            {"classifier": [make_pipeline(StandardScaler(),
                                            LogisticRegression(class_weight="balanced", max_iter=2000))],
             "classifier__logisticregression__C": [0.1, 1, 10]},
        ],
        scoring="balanced_accuracy",
        cv=StratifiedGroupKFold(n_splits=3, shuffle=True, random_state=41),
        n_jobs=4,
        error_score="raise",
    )


def train(tune=False):
    cache = ROOT / "pose_features"
    cache.mkdir(exist_ok=True)
    videos = sorted(
        video for exercise in EXERCISES for video in (FOOTAGE / exercise).glob("*.mp4")
        if NAME.fullmatch(video.name)
    )
    cv2.setNumThreads(1)
    with ProcessPoolExecutor(max_workers=8, initializer=cv2.setNumThreads, initargs=(1,)) as pool:
        for count, _ in enumerate(pool.map(cache_features, videos), 1):
            if count % 50 == 0 or count == len(videos):
                print(f"Extracted pose features for {count}/{len(videos)} videos", flush=True)
    reports = {}
    models = {}
    for exercise in sorted(EXERCISES):
        x, y, groups = [], [], []
        for video in sorted((FOOTAGE / exercise).glob("*.mp4")):
            match = NAME.fullmatch(video.name)
            if not match:
                continue
            saved = cache / (video.stem + ".npy")
            if saved.exists():
                row = np.load(saved, allow_pickle=False)
            else:
                row = features(video)
                row = np.array([]) if row is None else row
                np.save(saved, row)
            if row.size:
                x.append(row)
                y.append(match[3])
                groups.append(match[1])
        print(exercise, len(x), "usable videos", flush=True)
        if len(set(groups)) < 5 or len(set(y)) < 2:
            continue
        model = ExtraTreesClassifier(n_estimators=400, min_samples_leaf=3,
                                     class_weight="balanced", random_state=23, n_jobs=-1)
        cv = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=23)
        if tune:
            search = model_search()
            # Route participant IDs to each inner search as well as to the outer split.
            predicted = cross_val_predict(search, x, y, groups=groups, cv=cv,
                                          params={"groups": groups})
            search.fit(x, y, groups=groups)
            model = search.best_estimator_
        else:
            predicted = cross_val_predict(model, x, y, groups=groups, cv=cv)
        reports[exercise] = {
            "clips": len(x), "people": len(set(groups)),
            "balanced_accuracy": balanced_accuracy_score(y, predicted),
            "classification": classification_report(y, predicted, output_dict=True, zero_division=0),
        }
        models[exercise] = model.fit(x, y)
        if tune:
            reports[exercise]["selected_model"] = str(model.named_steps["classifier"])
        suffix = "_tuned" if tune else ""
        joblib.dump(models, ROOT / f"form_models{suffix}.joblib")
        (ROOT / f"training_metrics{suffix}.json").write_text(json.dumps(reports, indent=2))
        print(exercise, reports[exercise]["balanced_accuracy"], flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--predict", type=Path)
    parser.add_argument("--exercise", choices=sorted(EXERCISES))
    parser.add_argument("--tune", action="store_true")
    args = parser.parse_args()
    if args.predict:
        if not args.exercise:
            parser.error("--predict requires --exercise")
        row = features(args.predict)
        if row is None:
            parser.error("Insufficient visible pose to score this clip")
        model = joblib.load(ROOT / ("form_models_tuned.joblib" if args.tune else "form_models.joblib"))[args.exercise]
        print(model.predict([row])[0])
    else:
        if args.archive:
            prepare(args.archive)
        train(tune=args.tune)
