"""
Attendance System — FastAPI Backend
=====================================
Install deps:
    pip install fastapi uvicorn[standard] sqlalchemy pydantic python-multipart

Run:
    uvicorn main:app --reload --port 8000

API docs auto-generated at:
    http://localhost:8000/docs
"""

import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import (
    Boolean, Column, DateTime, Integer, String,
    create_engine, func, desc
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
import csv
import io

# ── Database setup ─────────────────────────────────────────────────────────────

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./attendance.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


class UserModel(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    email = Column(String, nullable=True)
    role = Column(String, default="student")          # student | staff | admin
    enrolled_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)


class AttendanceModel(Base):
    __tablename__ = "attendance"

    id = Column(Integer, primary_key=True, index=True)
    user_name = Column(String, nullable=False, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    session_date = Column(String, index=True)         # YYYY-MM-DD
    confidence = Column(Integer, nullable=True)        # 0-100
    camera_id = Column(String, nullable=True)
    is_late = Column(Boolean, default=False)
    note = Column(String, nullable=True)


Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    name: str
    email: Optional[str] = None
    role: str = "student"


class UserOut(BaseModel):
    id: int
    name: str
    email: Optional[str]
    role: str
    enrolled_at: datetime
    is_active: bool

    class Config:
        from_attributes = True


class AttendanceMark(BaseModel):
    name: str
    timestamp: Optional[datetime] = None
    confidence: Optional[int] = None
    camera_id: Optional[str] = None
    session_date: Optional[str] = None    # defaults to today
    late_after: Optional[str] = None      # "HH:MM" — if present, marks late


class AttendanceOut(BaseModel):
    id: int
    user_name: str
    timestamp: datetime
    session_date: str
    confidence: Optional[int]
    camera_id: Optional[str]
    is_late: bool
    note: Optional[str]

    class Config:
        from_attributes = True


class DailySummary(BaseModel):
    date: str
    total_present: int
    total_enrolled: int
    late_count: int
    absent_names: list[str]


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Attendance System API",
    description="Facial recognition attendance tracker",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}


# ── Users ─────────────────────────────────────────────────────────────────────

@app.post("/users", response_model=UserOut, tags=["users"])
def create_user(payload: UserCreate, db: Session = Depends(get_db)):
    """Enroll a new user in the system."""
    existing = db.query(UserModel).filter(UserModel.name == payload.name).first()
    if existing:
        raise HTTPException(400, f"User '{payload.name}' already exists.")
    user = UserModel(**payload.model_dump())
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@app.get("/users", response_model=list[UserOut], tags=["users"])
def list_users(
    active_only: bool = True,
    db: Session = Depends(get_db)
):
    """List all enrolled users."""
    q = db.query(UserModel)
    if active_only:
        q = q.filter(UserModel.is_active == True)
    return q.order_by(UserModel.name).all()


@app.delete("/users/{name}", tags=["users"])
def delete_user(name: str, db: Session = Depends(get_db)):
    """Deactivate a user (soft delete)."""
    user = db.query(UserModel).filter(UserModel.name == name).first()
    if not user:
        raise HTTPException(404, f"User '{name}' not found.")
    user.is_active = False
    db.commit()
    return {"message": f"'{name}' deactivated."}


# ── Attendance ────────────────────────────────────────────────────────────────

@app.post("/attendance/mark", response_model=AttendanceOut, tags=["attendance"])
def mark_attendance(payload: AttendanceMark, db: Session = Depends(get_db)):
    """
    Called by the face_engine.py recognition loop when a known face is detected.
    Handles deduplication: a user can only be marked once per session date.
    """
    session_date = payload.session_date or date.today().isoformat()
    timestamp = payload.timestamp or datetime.utcnow()

    # Dedup: already marked today?
    existing = db.query(AttendanceModel).filter(
        AttendanceModel.user_name == payload.name,
        AttendanceModel.session_date == session_date,
    ).first()
    if existing:
        return existing   # idempotent — return existing record

    # Late check
    is_late = False
    if payload.late_after:
        cutoff_h, cutoff_m = map(int, payload.late_after.split(":"))
        cutoff = timestamp.replace(hour=cutoff_h, minute=cutoff_m, second=0, microsecond=0)
        is_late = timestamp > cutoff

    record = AttendanceModel(
        user_name=payload.name,
        timestamp=timestamp,
        session_date=session_date,
        confidence=payload.confidence,
        camera_id=payload.camera_id,
        is_late=is_late,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@app.get("/attendance", response_model=list[AttendanceOut], tags=["attendance"])
def get_attendance(
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD"),
    user_name: Optional[str] = None,
    limit: int = Query(100, le=1000),
    db: Session = Depends(get_db),
):
    """Query attendance records with optional filters."""
    q = db.query(AttendanceModel)
    if date_from:
        q = q.filter(AttendanceModel.session_date >= date_from)
    if date_to:
        q = q.filter(AttendanceModel.session_date <= date_to)
    if user_name:
        q = q.filter(AttendanceModel.user_name == user_name)
    return q.order_by(desc(AttendanceModel.timestamp)).limit(limit).all()


@app.get("/attendance/today", response_model=list[AttendanceOut], tags=["attendance"])
def get_today(db: Session = Depends(get_db)):
    """Shortcut: all attendance records for today."""
    today = date.today().isoformat()
    return (
        db.query(AttendanceModel)
        .filter(AttendanceModel.session_date == today)
        .order_by(desc(AttendanceModel.timestamp))
        .all()
    )


@app.get("/attendance/summary/{session_date}", response_model=DailySummary, tags=["attendance"])
def daily_summary(session_date: str, db: Session = Depends(get_db)):
    """Return a summary for a given date: present, absent, late counts."""
    present = (
        db.query(AttendanceModel)
        .filter(AttendanceModel.session_date == session_date)
        .all()
    )
    present_names = {r.user_name for r in present}
    late_count = sum(1 for r in present if r.is_late)

    all_users = db.query(UserModel).filter(UserModel.is_active == True).all()
    all_names = {u.name for u in all_users}
    absent_names = sorted(all_names - present_names)

    return DailySummary(
        date=session_date,
        total_present=len(present_names),
        total_enrolled=len(all_users),
        late_count=late_count,
        absent_names=absent_names,
    )


@app.get("/attendance/export", tags=["attendance"])
def export_csv(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Download attendance records as CSV."""
    q = db.query(AttendanceModel)
    if date_from:
        q = q.filter(AttendanceModel.session_date >= date_from)
    if date_to:
        q = q.filter(AttendanceModel.session_date <= date_to)
    records = q.order_by(AttendanceModel.session_date, AttendanceModel.timestamp).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Name", "Date", "Timestamp", "Late", "Confidence", "Camera"])
    for r in records:
        writer.writerow([
            r.id, r.user_name, r.session_date,
            r.timestamp.isoformat(), r.is_late,
            r.confidence or "", r.camera_id or "",
        ])

    output.seek(0)
    filename = f"attendance_{date_from or 'all'}_{date_to or 'now'}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ── Stats ─────────────────────────────────────────────────────────────────────

@app.get("/stats/overview", tags=["stats"])
def overview_stats(db: Session = Depends(get_db)):
    """Dashboard overview numbers."""
    today = date.today().isoformat()
    week_ago = (date.today() - timedelta(days=7)).isoformat()

    today_present = db.query(func.count(AttendanceModel.id)).filter(
        AttendanceModel.session_date == today
    ).scalar()

    week_records = db.query(AttendanceModel).filter(
        AttendanceModel.session_date >= week_ago
    ).all()

    total_enrolled = db.query(func.count(UserModel.id)).filter(
        UserModel.is_active == True
    ).scalar()

    # Avg attendance rate over last 7 days
    if total_enrolled and week_records:
        days_with_data = len({r.session_date for r in week_records})
        avg_rate = round(
            (len(week_records) / (days_with_data * total_enrolled)) * 100, 1
        ) if days_with_data else 0
    else:
        avg_rate = 0

    # Attendance by day (last 7 days)
    daily = {}
    for r in week_records:
        daily[r.session_date] = daily.get(r.session_date, 0) + 1

    return {
        "today_present": today_present,
        "total_enrolled": total_enrolled,
        "avg_weekly_rate": avg_rate,
        "daily_counts": [
            {"date": d, "count": c}
            for d, c in sorted(daily.items())
        ],
    }