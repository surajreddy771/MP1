import argparse
import base64
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
 
import cv2
import face_recognition
import numpy as np
 
# ── Config ────────────────────────────────────────────────────────────────────
 
ENCODINGS_FILE = Path(__file__).parent / "known_faces.json"
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")
 
# How close a face match needs to be (lower = stricter). 0.6 is a good default.
MATCH_TOLERANCE = 0.55
 
# Min seconds between logging the same person again in one session
COOLDOWN_SECONDS = 30
 
 
# ── Encoding Store ────────────────────────────────────────────────────────────
 
def load_encodings() -> dict:
    """Load stored face encodings from disk."""
    if not ENCODINGS_FILE.exists():
        return {}
    with open(ENCODINGS_FILE, "r") as f:
        raw = json.load(f)
    # Convert lists back to numpy arrays
    return {name: np.array(enc) for name, enc in raw.items()}
 
 
def save_encodings(encodings: dict) -> None:
    """Persist face encodings to disk."""
    serializable = {name: enc.tolist() for name, enc in encodings.items()}
    with open(ENCODINGS_FILE, "w") as f:
        json.dump(serializable, f, indent=2)
    print(f"  Saved {len(encodings)} encoding(s) → {ENCODINGS_FILE}")
 
 
# ── Enrollment ────────────────────────────────────────────────────────────────
 
def enroll_from_image(name: str, image_path: str) -> bool:
    """
    Enroll a person from a single image file.
    Returns True if successful, False otherwise.
    """
    path = Path(image_path)
    if not path.exists():
        print(f"  ERROR: Image not found: {image_path}")
        return False
 
    print(f"  Loading image: {path.name}")
    image = face_recognition.load_image_file(str(path))
    encodings = face_recognition.face_encodings(image)
 
    if not encodings:
        print("  ERROR: No face detected in the image. Try a clearer, front-facing photo.")
        return False
 
    if len(encodings) > 1:
        print(f"  WARNING: {len(encodings)} faces detected. Using the first (largest) one.")
 
    encoding = encodings[0]
    known = load_encodings()
 
    if name in known:
        print(f"  Updating existing enrollment for '{name}'")
    else:
        print(f"  Enrolling new person: '{name}'")
 
    known[name] = encoding
    save_encodings(known)
    print(f"  ✓ '{name}' enrolled successfully.")
    return True
 
 
def enroll_from_camera(name: str, camera_index: int = 0, num_samples: int = 5) -> bool:
    """
    Enroll a person by capturing multiple frames from the webcam
    and averaging the encodings for better accuracy.
    """
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        print(f"  ERROR: Cannot open camera {camera_index}")
        return False
 
    print(f"\n  Enrolling '{name}' from camera.")
    print(f"  Will capture {num_samples} samples. Look directly at the camera.")
    print("  Press SPACE to capture a sample, Q to quit.\n")
 
    samples = []
    window = f"Enrolling: {name}"
 
    while len(samples) < num_samples:
        ret, frame = cap.read()
        if not ret:
            break
 
        display = frame.copy()
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        locations = face_recognition.face_locations(rgb)
 
        for (top, right, bottom, left) in locations:
            cv2.rectangle(display, (left, top), (right, bottom), (0, 220, 100), 2)
 
        status = f"Samples: {len(samples)}/{num_samples}  |  SPACE = capture   Q = quit"
        cv2.putText(display, status, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)
        cv2.imshow(window, display)
 
        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        if key == ord(" ") and locations:
            encodings = face_recognition.face_encodings(rgb, locations)
            if encodings:
                samples.append(encodings[0])
                print(f"  Sample {len(samples)}/{num_samples} captured.")
 
    cap.release()
    cv2.destroyAllWindows()
 
    if not samples:
        print("  ERROR: No samples captured.")
        return False
 
    # Average all samples for a robust encoding
    avg_encoding = np.mean(samples, axis=0)
    known = load_encodings()
    known[name] = avg_encoding
    save_encodings(known)
    print(f"\n  ✓ '{name}' enrolled from {len(samples)} samples.")
    return True
 
 
# ── Recognition ───────────────────────────────────────────────────────────────
 
def log_attendance(name: str) -> None:
    """
    Send an attendance event to the FastAPI backend.
    Falls back to a local print if the backend is unreachable.
    """
    try:
        import requests
        payload = {"name": name, "timestamp": datetime.utcnow().isoformat()}
        resp = requests.post(f"{BACKEND_URL}/attendance/mark", json=payload, timeout=2)
        if resp.status_code == 200:
            print(f"  → Logged to backend: {name}")
        else:
            print(f"  → Backend error {resp.status_code}: {resp.text}")
    except Exception:
        # Backend unavailable — log locally
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"  [LOCAL LOG] {ts} — {name} marked present")
 
 
def run_recognition(camera_index: int = 0, show_window: bool = True) -> None:
    """
    Main recognition loop. Reads frames from the webcam, detects faces,
    matches against enrolled users, and logs attendance.
    """
    known = load_encodings()
    if not known:
        print("  ERROR: No enrolled faces. Run 'enroll' first.")
        return
 
    names = list(known.keys())
    encodings = list(known.values())
    print(f"  Loaded {len(names)} enrolled face(s): {', '.join(names)}")
 
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        print(f"  ERROR: Cannot open camera {camera_index}")
        return
 
    # Reduce resolution for speed; recognition still works well at 640×480
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
 
    print("\n  Recognition running. Press Q to quit.\n")
 
    last_logged: dict[str, float] = {}   # name → epoch time of last log
    frame_count = 0
 
    while True:
        ret, frame = cap.read()
        if not ret:
            break
 
        frame_count += 1
        # Only process every 2nd frame for performance
        if frame_count % 2 != 0:
            if show_window:
                cv2.imshow("Attendance — Press Q to quit", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
            continue
 
        # Downsample for faster face_recognition
        small = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
        rgb_small = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
 
        locations = face_recognition.face_locations(rgb_small, model="hog")
        found_encodings = face_recognition.face_encodings(rgb_small, locations)
 
        for (top, right, bottom, left), face_enc in zip(locations, found_encodings):
            # Scale back to original frame size
            top, right, bottom, left = top * 2, right * 2, bottom * 2, left * 2
 
            distances = face_recognition.face_distance(encodings, face_enc)
            best_idx = int(np.argmin(distances))
            best_dist = distances[best_idx]
            matched = best_dist <= MATCH_TOLERANCE
 
            if matched:
                label = names[best_idx]
                confidence = round((1 - best_dist) * 100, 1)
                color = (0, 220, 100)
 
                # Cooldown check before logging
                now = time.time()
                last = last_logged.get(label, 0)
                if now - last >= COOLDOWN_SECONDS:
                    last_logged[label] = now
                    log_attendance(label)
            else:
                label = "Unknown"
                confidence = 0
                color = (0, 60, 220)
 
            if show_window:
                cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
                display_text = f"{label} ({confidence}%)" if matched else label
                cv2.rectangle(frame, (left, bottom - 28), (right, bottom), color, cv2.FILLED)
                cv2.putText(frame, display_text, (left + 6, bottom - 8),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
 
        if show_window:
            cv2.imshow("Attendance — Press Q to quit", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
 
    cap.release()
    cv2.destroyAllWindows()
    print("  Recognition stopped.")
 
 
# ── CLI ───────────────────────────────────────────────────────────────────────
 
def cmd_enroll(args):
    if args.image:
        enroll_from_image(args.name, args.image)
    else:
        enroll_from_camera(args.name, args.camera)
 
 
def cmd_recognize(args):
    run_recognition(camera_index=args.camera, show_window=not args.headless)
 
 
def cmd_list(args):
    known = load_encodings()
    if not known:
        print("  No enrolled faces.")
    else:
        print(f"  {len(known)} enrolled face(s):")
        for name in sorted(known.keys()):
            print(f"    • {name}")
 
 
def cmd_delete(args):
    known = load_encodings()
    if args.name not in known:
        print(f"  '{args.name}' not found.")
        return
    del known[args.name]
    save_encodings(known)
    print(f"  ✓ '{args.name}' removed.")
 
 
def main():
    parser = argparse.ArgumentParser(description="Face Attendance Engine")
    sub = parser.add_subparsers(dest="command", required=True)
 
    # enroll
    p_enroll = sub.add_parser("enroll", help="Enroll a new person")
    p_enroll.add_argument("--name", required=True, help="Person's display name")
    p_enroll.add_argument("--image", help="Path to image file (skip for webcam capture)")
    p_enroll.add_argument("--camera", type=int, default=0, help="Camera index (default 0)")
    p_enroll.set_defaults(func=cmd_enroll)
 
    # recognize
    p_rec = sub.add_parser("recognize", help="Run live recognition")
    p_rec.add_argument("--camera", type=int, default=0, help="Camera index (default 0)")
    p_rec.add_argument("--headless", action="store_true", help="No display window (server mode)")
    p_rec.set_defaults(func=cmd_recognize)
 
    # list
    p_list = sub.add_parser("list", help="List enrolled people")
    p_list.set_defaults(func=cmd_list)
 
    # delete
    p_del = sub.add_parser("delete", help="Remove an enrolled person")
    p_del.add_argument("--name", required=True, help="Name to remove")
    p_del.set_defaults(func=cmd_delete)
 
    args = parser.parse_args()
    args.func(args)
 
 
if __name__ == "__main__":
    main()