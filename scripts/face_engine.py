"""
Face Enrollment & Recognition Engine (DeepFace backend)
========================================================
No dlib/CMake required. Installs cleanly on Windows.

Install deps:
    pip install deepface tf-keras opencv-python numpy requests

Usage:
    python face_engine.py enroll --name "Alice" --image path/to/alice.jpg
    python face_engine.py enroll --name "Alice"          # webcam capture
    python face_engine.py recognize --camera 0
    python face_engine.py list
    python face_engine.py delete --name "Alice"
"""

import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

ENCODINGS_FILE   = Path(__file__).parent / "known_faces.json"
BACKEND_URL      = os.environ.get("BACKEND_URL", "http://localhost:8000")
MODEL_NAME       = "Facenet"
MATCH_THRESHOLD  = 0.40
COOLDOWN_SECONDS = 30


def get_embedding(img_rgb: np.ndarray):
    from deepface import DeepFace
    try:
        result = DeepFace.represent(
            img_path=img_rgb,
            model_name=MODEL_NAME,
            enforce_detection=True,
            detector_backend="opencv",
        )
        return np.array(result[0]["embedding"])
    except Exception:
        return None


def cosine_distance(a, b):
    a = a / (np.linalg.norm(a) + 1e-9)
    b = b / (np.linalg.norm(b) + 1e-9)
    return float(1 - np.dot(a, b))


def load_encodings():
    if not ENCODINGS_FILE.exists():
        return {}
    with open(ENCODINGS_FILE) as f:
        raw = json.load(f)
    return {name: np.array(enc) for name, enc in raw.items()}


def save_encodings(encodings):
    with open(ENCODINGS_FILE, "w") as f:
        json.dump({n: e.tolist() for n, e in encodings.items()}, f, indent=2)
    print(f"  Saved {len(encodings)} encoding(s) -> {ENCODINGS_FILE}")


def enroll_from_image(name, image_path):
    path = Path(image_path)
    if not path.exists():
        print(f"  ERROR: File not found: {image_path}")
        return False
    img = cv2.imread(str(path))
    if img is None:
        print("  ERROR: Could not read image.")
        return False
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    print("  Computing embedding (may download model ~90MB on first run) ...")
    enc = get_embedding(rgb)
    if enc is None:
        print("  ERROR: No face detected. Use a clear front-facing photo.")
        return False
    known = load_encodings()
    known[name] = enc
    save_encodings(known)
    print(f"  '{name}' enrolled from image.")
    return True


def enroll_from_camera(name, camera_index=0, num_samples=5):
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        print(f"  ERROR: Cannot open camera {camera_index}")
        return False

    print(f"\n  Enrolling '{name}' from camera.")
    print(f"  Will capture {num_samples} samples. Look directly at the camera.")
    print("  Press SPACE to capture, Q to quit.\n")

    samples = []

    while len(samples) < num_samples:
        ret, frame = cap.read()
        if not ret:
            break

        display = frame.copy()
        h, w = frame.shape[:2]
        cx, cy = w // 2, h // 2
        bw, bh = int(w * 0.35), int(h * 0.55)
        cv2.rectangle(display, (cx-bw, cy-bh), (cx+bw, cy+bh), (0, 200, 255), 1)
        cv2.putText(display, f"Samples: {len(samples)}/{num_samples}  SPACE=capture  Q=quit",
                    (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.imshow(f"Enrolling: {name}", display)

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        if key == ord(" "):
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            print(f"  Computing sample {len(samples)+1} ...")
            enc = get_embedding(rgb)
            if enc is not None:
                samples.append(enc)
                print(f"  Sample {len(samples)}/{num_samples} done.")
            else:
                print("  No face detected — try again.")

    cap.release()
    cv2.destroyAllWindows()

    if not samples:
        print("  ERROR: No samples captured.")
        return False

    known = load_encodings()
    known[name] = np.mean(samples, axis=0)
    save_encodings(known)
    print(f"\n  '{name}' enrolled from {len(samples)} sample(s).")
    return True


def log_attendance(name):
    try:
        import requests
        resp = requests.post(
            f"{BACKEND_URL}/attendance/mark",
            json={"name": name, "timestamp": datetime.utcnow().isoformat()},
            timeout=2,
        )
        print(f"  -> Logged: {name}" if resp.status_code == 200 else f"  -> Backend error {resp.status_code}")
    except Exception:
        print(f"  [LOCAL] {datetime.now().strftime('%H:%M:%S')} -- {name} present")


def detect_faces_opencv(frame_bgr):
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    detector = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    faces = detector.detectMultiScale(gray, 1.1, 5, minSize=(60, 60))
    return faces if len(faces) > 0 else []


def run_recognition(camera_index=0, show_window=True):
    known = load_encodings()
    if not known:
        print("  ERROR: No enrolled faces. Run 'enroll' first.")
        return

    names     = list(known.keys())
    encodings = list(known.values())
    print(f"  Loaded {len(names)} face(s): {', '.join(names)}")
    print("  Running. Press Q to quit. First frame may be slow.\n")

    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        print(f"  ERROR: Cannot open camera {camera_index}")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    last_logged = {}
    frame_count = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frame_count += 1

        if frame_count % 5 == 0:
            for (x, y, w, h) in detect_faces_opencv(frame):
                m = 20
                crop = frame[max(0,y-m):y+h+m, max(0,x-m):x+w+m]
                enc  = get_embedding(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))

                if enc is not None:
                    dists   = [cosine_distance(enc, e) for e in encodings]
                    best_i  = int(np.argmin(dists))
                    matched = dists[best_i] <= MATCH_THRESHOLD
                    label   = names[best_i] if matched else "Unknown"
                    conf    = round((1 - dists[best_i]) * 100, 1) if matched else 0
                    color   = (0, 220, 100) if matched else (0, 60, 220)

                    if matched:
                        now = time.time()
                        if now - last_logged.get(label, 0) >= COOLDOWN_SECONDS:
                            last_logged[label] = now
                            log_attendance(label)
                else:
                    label, conf, color = "?", 0, (100, 100, 100)

                if show_window:
                    cv2.rectangle(frame, (x, y), (x+w, y+h), color, 2)
                    cv2.rectangle(frame, (x, y+h-26), (x+w, y+h), color, cv2.FILLED)
                    cv2.putText(frame, f"{label} ({conf}%)" if conf else label,
                                (x+5, y+h-8), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (255,255,255), 1)

        if show_window:
            cv2.imshow("Attendance -- Q to quit", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    cap.release()
    cv2.destroyAllWindows()
    print("  Stopped.")


def main():
    parser = argparse.ArgumentParser(description="Face Attendance Engine")
    sub    = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("enroll")
    p.add_argument("--name",   required=True)
    p.add_argument("--image",  default=None)
    p.add_argument("--camera", type=int, default=0)
    p.set_defaults(func=lambda a: enroll_from_image(a.name, a.image) if a.image else enroll_from_camera(a.name, a.camera))

    p = sub.add_parser("recognize")
    p.add_argument("--camera",   type=int, default=0)
    p.add_argument("--headless", action="store_true")
    p.set_defaults(func=lambda a: run_recognition(a.camera, not a.headless))

    p = sub.add_parser("list")
    p.set_defaults(func=lambda a: [print(f"  * {n}") for n in sorted(load_encodings())] or print("  No faces enrolled.") if not load_encodings() else None)

    p = sub.add_parser("delete")
    p.add_argument("--name", required=True)
    def do_delete(a):
        k = load_encodings()
        if a.name not in k:
            print(f"  '{a.name}' not found.")
            return
        del k[a.name]
        save_encodings(k)
        print(f"  '{a.name}' removed.")
    p.set_defaults(func=do_delete)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()