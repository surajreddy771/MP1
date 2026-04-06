"""
Attendance System — FastAPI Backend
=====================================
Install deps:
    pip install fastapi uvicorn[standard] sqlalchemy pydantic python-multipart twilio

Run:
    python -m uvicorn main:app --reload --port 8000
"""

import os
import csv
import io
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import Boolean, Column, DateTime, Integer, String, create_engine, func, desc
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# ── Database ──────────────────────────────────────────────────────────────────

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./attendance.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


class UserModel(Base):
    __tablename__ = "users"
    id          = Column(Integer, primary_key=True, index=True)
    name        = Column(String, unique=True, nullable=False)
    email       = Column(String, nullable=True)
    phone       = Column(String, nullable=True)   # e.g. +919876543210
    role        = Column(String, default="student")
    enrolled_at = Column(DateTime, default=datetime.utcnow)
    is_active   = Column(Boolean, default=True)


class AttendanceModel(Base):
    __tablename__ = "attendance"
    id           = Column(Integer, primary_key=True, index=True)
    user_name    = Column(String, nullable=False, index=True)
    timestamp    = Column(DateTime, default=datetime.utcnow, index=True)
    session_date = Column(String, index=True)
    confidence   = Column(Integer, nullable=True)
    camera_id    = Column(String, nullable=True)
    is_late      = Column(Boolean, default=False)
    note         = Column(String, nullable=True)


Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Schemas ───────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    name:  str
    email: Optional[str] = None
    phone: Optional[str] = None
    role:  str = "student"


class UserOut(BaseModel):
    id:          int
    name:        str
    email:       Optional[str]
    phone:       Optional[str]
    role:        str
    enrolled_at: datetime
    is_active:   bool
    class Config:
        from_attributes = True


class AttendanceMark(BaseModel):
    name:         str
    timestamp:    Optional[datetime] = None
    confidence:   Optional[int]      = None
    camera_id:    Optional[str]      = None
    session_date: Optional[str]      = None
    late_after:   Optional[str]      = None


class AttendanceOut(BaseModel):
    id:           int
    user_name:    str
    timestamp:    datetime
    session_date: str
    confidence:   Optional[int]
    camera_id:    Optional[str]
    is_late:      bool
    note:         Optional[str]
    class Config:
        from_attributes = True


class DailySummary(BaseModel):
    date:          str
    total_present: int
    total_enrolled: int
    late_count:    int
    absent_names:  list[str]


class FaceCommand(BaseModel):
    command:    str              # "enroll" | "recognize" | "list" | "delete"
    name:       Optional[str] = None
    image_path: Optional[str] = None
    camera:     int = 0
    headless:   bool = True


class SMSRequest(BaseModel):
    threshold:  float = 75.0    # send SMS to anyone below this %
    date_from:  Optional[str] = None
    date_to:    Optional[str] = None
    dry_run:    bool = False    # if True, return who would be messaged without sending


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="FaceTrack API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Path to face_engine.py — adjust if your layout differs
FACE_ENGINE = Path(__file__).parent.parent / "scripts" / "face_engine.py"


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}


# ── Users ─────────────────────────────────────────────────────────────────────

@app.post("/users", response_model=UserOut, tags=["users"])
def create_user(payload: UserCreate, db: Session = Depends(get_db)):
    if db.query(UserModel).filter(UserModel.name == payload.name).first():
        raise HTTPException(400, f"'{payload.name}' already exists.")
    user = UserModel(**payload.model_dump())
    db.add(user); db.commit(); db.refresh(user)
    return user


@app.get("/users", response_model=list[UserOut], tags=["users"])
def list_users(active_only: bool = True, db: Session = Depends(get_db)):
    q = db.query(UserModel)
    if active_only:
        q = q.filter(UserModel.is_active == True)
    return q.order_by(UserModel.name).all()


@app.patch("/users/{name}", response_model=UserOut, tags=["users"])
def update_user(name: str, payload: UserCreate, db: Session = Depends(get_db)):
    user = db.query(UserModel).filter(UserModel.name == name).first()
    if not user:
        raise HTTPException(404, f"'{name}' not found.")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(user, k, v)
    db.commit(); db.refresh(user)
    return user


@app.delete("/users/{name}", tags=["users"])
def delete_user(name: str, db: Session = Depends(get_db)):
    user = db.query(UserModel).filter(UserModel.name == name).first()
    if not user:
        raise HTTPException(404, f"'{name}' not found.")
    user.is_active = False
    db.commit()
    return {"message": f"'{name}' deactivated."}


# ── Attendance ────────────────────────────────────────────────────────────────

@app.post("/attendance/mark", response_model=AttendanceOut, tags=["attendance"])
def mark_attendance(payload: AttendanceMark, db: Session = Depends(get_db)):
    session_date = payload.session_date or date.today().isoformat()
    timestamp    = payload.timestamp    or datetime.utcnow()

    existing = db.query(AttendanceModel).filter(
        AttendanceModel.user_name    == payload.name,
        AttendanceModel.session_date == session_date,
    ).first()
    if existing:
        return existing

    is_late = False
    if payload.late_after:
        h, m   = map(int, payload.late_after.split(":"))
        cutoff = timestamp.replace(hour=h, minute=m, second=0, microsecond=0)
        is_late = timestamp > cutoff

    record = AttendanceModel(
        user_name=payload.name, timestamp=timestamp,
        session_date=session_date, confidence=payload.confidence,
        camera_id=payload.camera_id, is_late=is_late,
    )
    db.add(record); db.commit(); db.refresh(record)
    return record


@app.get("/attendance", response_model=list[AttendanceOut], tags=["attendance"])
def get_attendance(
    date_from:  Optional[str] = None,
    date_to:    Optional[str] = None,
    user_name:  Optional[str] = None,
    limit:      int = Query(200, le=1000),
    db: Session = Depends(get_db),
):
    q = db.query(AttendanceModel)
    if date_from: q = q.filter(AttendanceModel.session_date >= date_from)
    if date_to:   q = q.filter(AttendanceModel.session_date <= date_to)
    if user_name: q = q.filter(AttendanceModel.user_name == user_name)
    return q.order_by(desc(AttendanceModel.timestamp)).limit(limit).all()


@app.get("/attendance/today", response_model=list[AttendanceOut], tags=["attendance"])
def get_today(db: Session = Depends(get_db)):
    today = date.today().isoformat()
    return db.query(AttendanceModel).filter(
        AttendanceModel.session_date == today
    ).order_by(desc(AttendanceModel.timestamp)).all()


@app.get("/attendance/summary/{session_date}", response_model=DailySummary, tags=["attendance"])
def daily_summary(session_date: str, db: Session = Depends(get_db)):
    present       = db.query(AttendanceModel).filter(AttendanceModel.session_date == session_date).all()
    present_names = {r.user_name for r in present}
    all_users     = db.query(UserModel).filter(UserModel.is_active == True).all()
    return DailySummary(
        date=session_date,
        total_present=len(present_names),
        total_enrolled=len(all_users),
        late_count=sum(1 for r in present if r.is_late),
        absent_names=sorted({u.name for u in all_users} - present_names),
    )


@app.get("/attendance/export", tags=["attendance"])
def export_csv(
    date_from: Optional[str] = None,
    date_to:   Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = db.query(AttendanceModel)
    if date_from: q = q.filter(AttendanceModel.session_date >= date_from)
    if date_to:   q = q.filter(AttendanceModel.session_date <= date_to)
    records = q.order_by(AttendanceModel.session_date, AttendanceModel.timestamp).all()

    out = io.StringIO()
    w   = csv.writer(out)
    w.writerow(["ID", "Name", "Date", "Timestamp", "Late", "Confidence", "Camera"])
    for r in records:
        w.writerow([r.id, r.user_name, r.session_date, r.timestamp.isoformat(),
                    r.is_late, r.confidence or "", r.camera_id or ""])
    out.seek(0)
    return StreamingResponse(iter([out.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=attendance.csv"})


# ── Attendance rate per student ───────────────────────────────────────────────

@app.get("/stats/rates", tags=["stats"])
def attendance_rates(
    date_from: Optional[str] = None,
    date_to:   Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Return attendance % for every active student."""
    q = db.query(AttendanceModel)
    if date_from: q = q.filter(AttendanceModel.session_date >= date_from)
    if date_to:   q = q.filter(AttendanceModel.session_date <= date_to)
    records   = q.all()

    all_dates = sorted({r.session_date for r in records})
    total_days = len(all_dates) or 1

    counts: dict[str, int] = {}
    for r in records:
        counts[r.user_name] = counts.get(r.user_name, 0) + 1

    users = db.query(UserModel).filter(UserModel.is_active == True).all()
    result = []
    for u in users:
        present = counts.get(u.name, 0)
        rate    = round((present / total_days) * 100, 1)
        result.append({
            "name":       u.name,
            "phone":      u.phone,
            "email":      u.email,
            "present":    present,
            "total_days": total_days,
            "rate":       rate,
            "below_75":   rate < 75.0,
        })
    return sorted(result, key=lambda x: x["rate"])


@app.get("/stats/overview", tags=["stats"])
def overview_stats(db: Session = Depends(get_db)):
    today    = date.today().isoformat()
    week_ago = (date.today() - timedelta(days=7)).isoformat()

    today_present = db.query(func.count(AttendanceModel.id)).filter(
        AttendanceModel.session_date == today).scalar()
    week_records  = db.query(AttendanceModel).filter(
        AttendanceModel.session_date >= week_ago).all()
    total_enrolled = db.query(func.count(UserModel.id)).filter(
        UserModel.is_active == True).scalar()

    days_with_data = len({r.session_date for r in week_records})
    avg_rate = round((len(week_records) / (days_with_data * total_enrolled)) * 100, 1) \
        if total_enrolled and days_with_data else 0

    daily: dict[str, int] = {}
    for r in week_records:
        daily[r.session_date] = daily.get(r.session_date, 0) + 1

    return {
        "today_present":    today_present,
        "total_enrolled":   total_enrolled,
        "avg_weekly_rate":  avg_rate,
        "daily_counts":     [{"date": d, "count": c} for d, c in sorted(daily.items())],
    }


# ── Face engine control ───────────────────────────────────────────────────────

recognition_process = None   # global handle for the recognition subprocess

@app.post("/face/run", tags=["face"])
def run_face_command(payload: FaceCommand):
    """
    Trigger face_engine.py commands from the frontend.
    enroll/list/delete run synchronously and return output.
    recognize starts a background process.
    """
    global recognition_process

    if not FACE_ENGINE.exists():
        raise HTTPException(500, f"face_engine.py not found at {FACE_ENGINE}")

    if payload.command == "recognize":
        if recognition_process and recognition_process.poll() is None:
            return {"status": "already_running", "pid": recognition_process.pid}
        args = [sys.executable, str(FACE_ENGINE), "recognize",
                "--camera", str(payload.camera)]
        if payload.headless:
            args.append("--headless")
        recognition_process = subprocess.Popen(args,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        return {"status": "started", "pid": recognition_process.pid}

    if payload.command == "stop":
        if recognition_process and recognition_process.poll() is None:
            recognition_process.terminate()
            return {"status": "stopped"}
        return {"status": "not_running"}

    # Synchronous commands: enroll, list, delete
    args = [sys.executable, str(FACE_ENGINE), payload.command]
    if payload.command == "enroll":
        if not payload.name:
            raise HTTPException(400, "name required for enroll")
        args += ["--name", payload.name]
        if payload.image_path:
            args += ["--image", payload.image_path]
        else:
            return {"status": "error",
                    "output": "Webcam enroll must be run from terminal. Use image upload instead."}
    elif payload.command == "delete":
        if not payload.name:
            raise HTTPException(400, "name required for delete")
        args += ["--name", payload.name]

    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=60)
        output = result.stdout + result.stderr
        return {"status": "ok" if result.returncode == 0 else "error", "output": output.strip()}
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "Command timed out")


@app.get("/face/status", tags=["face"])
def recognition_status():
    global recognition_process
    if recognition_process is None:
        return {"running": False}
    running = recognition_process.poll() is None
    return {"running": running, "pid": recognition_process.pid if running else None}


# ── SMS alerts ────────────────────────────────────────────────────────────────

@app.post("/sms/send", tags=["sms"])
def send_sms_alerts(payload: SMSRequest, db: Session = Depends(get_db)):
    """
    Send SMS to students below the attendance threshold.
    Requires env vars: TWILIO_SID, TWILIO_TOKEN, TWILIO_FROM
    Set them before running the backend, or use dry_run=true to preview.
    """
    # Get rates
    q = db.query(AttendanceModel)
    if payload.date_from: q = q.filter(AttendanceModel.session_date >= payload.date_from)
    if payload.date_to:   q = q.filter(AttendanceModel.session_date <= payload.date_to)
    records    = q.all()
    all_dates  = sorted({r.session_date for r in records})
    total_days = len(all_dates) or 1
    counts: dict[str, int] = {}
    for r in records:
        counts[r.user_name] = counts.get(r.user_name, 0) + 1

    users = db.query(UserModel).filter(
        UserModel.is_active == True, UserModel.role == "student"
    ).all()

    targets = []
    for u in users:
        rate = round((counts.get(u.name, 0) / total_days) * 100, 1)
        if rate < payload.threshold:
            targets.append({"name": u.name, "phone": u.phone, "rate": rate})

    if payload.dry_run:
        return {"dry_run": True, "would_message": targets, "total": len(targets)}

    # Send via Twilio
    sid   = os.environ.get("TWILIO_SID")
    token = os.environ.get("TWILIO_TOKEN")
    frm   = os.environ.get("TWILIO_FROM")

    if not all([sid, token, frm]):
        raise HTTPException(500,
            "Twilio not configured. Set TWILIO_SID, TWILIO_TOKEN, TWILIO_FROM env vars.")

    try:
        from twilio.rest import Client
        client = Client(sid, token)
    except ImportError:
        raise HTTPException(500, "Twilio not installed. Run: pip install twilio")

    sent, failed, skipped = [], [], []
    for t in targets:
        if not t["phone"]:
            skipped.append({"name": t["name"], "reason": "no phone number"})
            continue
        msg = (f"Dear {t['name']}, your attendance is {t['rate']}% which is below "
               f"the required {payload.threshold}%. Please contact your department.")
        try:
            client.messages.create(body=msg, from_=frm, to=t["phone"])
            sent.append({"name": t["name"], "phone": t["phone"], "rate": t["rate"]})
        except Exception as e:
            failed.append({"name": t["name"], "error": str(e)})

    return {"sent": sent, "failed": failed, "skipped": skipped,
            "total_sent": len(sent)}