from fastapi import APIRouter, Depends, Request, Form, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional
import json
import io
import logging

from database import get_db, User, Patient, MonthlyRecord, SessionRecord, InterimLabRecord, ClinicalEvent
from config import templates, pwd_context
from dependencies import get_user, _require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

@router.get("/users", response_class=HTMLResponse)
async def user_manager(request: Request, db: Session = Depends(get_db)):
    _require_admin(request)
    users = db.query(User).all()
    return templates.TemplateResponse("user_manager.html", {"request": request, "users": users, "user": get_user(request)})

@router.post("/users/new")
async def create_user(request: Request, username: str = Form(...), password: str = Form(...), role: str = Form("viewer"), db: Session = Depends(get_db)):
    _require_admin(request)
    hashed = pwd_context.hash(password)
    new_user = User(username=username, hashed_password=hashed, role=role)
    db.add(new_user)
    db.commit()
    return RedirectResponse(url="/admin/users", status_code=303)

@router.post("/users/{user_id}/delete")
async def delete_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    _require_admin(request)
    u = db.query(User).filter(User.id == user_id).first()
    if u:
        db.delete(u)
        db.commit()
    return RedirectResponse(url="/admin/users", status_code=303)

@router.get("/backup", response_class=HTMLResponse)
async def backup_page(request: Request):
    _require_admin(request)
    return templates.TemplateResponse("backup.html", {"request": request, "user": get_user(request)})

@router.get("/backup/download")
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

@router.post("/backup/restore")
async def restore_backup(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
    _require_admin(request)
    content = await file.read()
    data = json.loads(content)
    
    # Simple restore logic (clear and insert) - CAUTION: High Risk
    # In a real app, you'd want to merge or handle conflicts
    # For now, let's just log and provide a placeholder
    logger.warning("Restore initiated by %s", get_user(request).get("username"))
    return {"message": "Restore feature is under development. Please contact support."}
