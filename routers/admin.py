from fastapi import APIRouter, Depends, Request, Form, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional
import json
import io
import logging

from datetime import date, datetime
from database import get_db, User, Patient, MonthlyRecord, SessionRecord, InterimLabRecord, ClinicalEvent, engine
from config import templates, pwd_context
from dependencies import get_user, _require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

@router.get("/run-migration", response_class=HTMLResponse)
async def run_pds_migration(request: Request, db: Session = Depends(get_db)):
    """Triggers the PDS schema migration. Useful for Render free tier."""
    _require_admin(request)
    
    results = []
    # Columns to add to session_records
    session_cols = [
        ("intradialytic_exercise_mins", "INTEGER"),
        ("intradialytic_meals_eaten", "BOOLEAN DEFAULT FALSE")
    ]
    
    # Columns to add to patient_symptom_reports
    symptom_cols = [
        ("session_id", "INTEGER"),
        ("dialysis_recovery_time_mins", "INTEGER"),
        ("tiredness_score", "INTEGER"),
        ("energy_level_score", "INTEGER"),
        ("daily_activity_impact", "INTEGER"),
        ("cognitive_alertness", "VARCHAR"),
        ("post_hd_mood", "VARCHAR"),
        ("sleepiness_severity", "INTEGER"),
        ("missed_social_or_work_event", "BOOLEAN DEFAULT FALSE")
    ]

    with engine.connect() as conn:
        # 1. Update session_records
        for col, col_type in session_cols:
            try:
                conn.execute(text(f"ALTER TABLE session_records ADD COLUMN {col} {col_type}"))
                conn.commit()
                results.append(f"✅ Added {col} to session_records")
            except Exception as e:
                results.append(f"⚠️ {col} (session): {str(e)[:50]}...")

        # 2. Update patient_symptom_reports
        for col, col_type in symptom_cols:
            try:
                conn.execute(text(f"ALTER TABLE patient_symptom_reports ADD COLUMN {col} {col_type}"))
                conn.commit()
                results.append(f"✅ Added {col} to patient_symptom_reports")
            except Exception as e:
                results.append(f"⚠️ {col} (symptom): {str(e)[:50]}...")

        # 3. Update patients
        patient_cols = [
            ("diastolic_dysfunction", "VARCHAR"),
            ("handgrip_strength", "FLOAT")
        ]
        for col, col_type in patient_cols:
            try:
                conn.execute(text(f"ALTER TABLE patients ADD COLUMN {col} {col_type}"))
                conn.commit()
                results.append(f"✅ Added {col} to patients")
            except Exception as e:
                results.append(f"⚠️ {col} (patient): {str(e)[:50]}...")

        # 4. Update monthly_records
        monthly_cols = [
            ("npcr", "FLOAT"),
            ("ufr", "FLOAT"),
            ("prealbumin", "FLOAT"),
            ("sga_score", "VARCHAR"),
            ("mis_score", "INTEGER"),
            ("neutrophil_count", "FLOAT"),
            ("lymphocyte_count", "FLOAT"),
            ("il6", "FLOAT"),
            ("tnf_alpha", "FLOAT"),
            ("bp_dia", "FLOAT"),
            ("troponin_i", "FLOAT"),
            ("nt_probnp", "FLOAT")
        ]
        for col, col_type in monthly_cols:
            try:
                conn.execute(text(f"ALTER TABLE monthly_records ADD COLUMN {col} {col_type}"))
                conn.commit()
                results.append(f"✅ Added {col} to monthly_records")
            except Exception as e:
                results.append(f"⚠️ {col} (monthly): {str(e)[:50]}...")

    res_html = "<h2>Migration Results</h2><ul>" + "".join([f"<li>{r}</li>" for r in results]) + "</ul><a href='/admin/users'>Back to Admin</a>"
    return HTMLResponse(content=res_html)

@router.get("/users", response_class=HTMLResponse)
async def user_manager(request: Request, db: Session = Depends(get_db)):
    _require_admin(request)
    users = db.query(User).all()
    return templates.TemplateResponse("admin_users.html", {"request": request, "users": users, "user": get_user(request)})

@router.post("/users/create")
async def create_user(request: Request, username: str = Form(...), full_name: str = Form(""), password: str = Form(...), role: str = Form("viewer"), db: Session = Depends(get_db)):
    _require_admin(request)
    hashed = pwd_context.hash(password)
    new_user = User(username=username, full_name=full_name, hashed_password=hashed, role=role)
    db.add(new_user)
    db.commit()
    return RedirectResponse(url="/admin/users", status_code=303)

@router.post("/users/{user_id}/toggle")
async def toggle_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    _require_admin(request)
    u = db.query(User).filter(User.id == user_id).first()
    if u:
        u.is_active = not u.is_active
        db.commit()
    return RedirectResponse(url="/admin/users", status_code=303)

@router.post("/users/{user_id}/reset-password")
async def reset_password(user_id: int, request: Request, new_password: str = Form(...), db: Session = Depends(get_db)):
    _require_admin(request)
    u = db.query(User).filter(User.id == user_id).first()
    if u:
        u.hashed_password = pwd_context.hash(new_password)
        db.commit()
    return RedirectResponse(url="/admin/users", status_code=303)

@router.get("/backup", response_class=HTMLResponse)
async def backup_page(request: Request):
    _require_admin(request)
    return templates.TemplateResponse("admin_db.html", {"request": request, "user": get_user(request)})

@router.get("/db/export")
async def download_backup(request: Request, db: Session = Depends(get_db)):
    _require_admin(request)
    data = {
        "patients": [p.__dict__ for p in db.query(Patient).all()],
        "monthly_records": [r.__dict__ for r in db.query(MonthlyRecord).all()],
        "session_records": [s.__dict__ for s in db.query(SessionRecord).all()],
        "interim_labs": [l.__dict__ for l in db.query(InterimLabRecord).all()],
        "clinical_events": [e.__dict__ for e in db.query(ClinicalEvent).all()],
        "users": [u.__dict__ for u in db.query(User).all()]
    }
    # Remove SQLAlchemy internal state
    for key in data:
        for item in data[key]:
            item.pop("_sa_instance_state", None)
            # Convert dates/datetimes to strings
            for k, v in item.items():
                if isinstance(v, (date, datetime)):
                    item[k] = v.isoformat()
    
    json_data = json.dumps(data, indent=2)
    return StreamingResponse(
        io.BytesIO(json_data.encode()),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=hd_dashboard_backup_{date.today().isoformat()}.json"}
    )

@router.post("/db/import")
async def restore_backup(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
    _require_admin(request)
    content = await file.read()
    data = json.loads(content)
    
    # Simple restore logic (clear and insert) - CAUTION: High Risk
    # In a real app, you'd want to merge or handle conflicts
    # For now, let's just log and provide a placeholder
    logger.warning("Restore initiated by %s", get_user(request).get("username"))
    return templates.TemplateResponse("admin_db.html", {"request": request, "error": "Restore feature is under development. Please contact support.", "user": get_user(request)})
