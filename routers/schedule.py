from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date, datetime
import logging

from database import get_db, Patient
from config import templates
from dependencies import get_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/schedule", tags=["schedule"])

@router.get("", response_class=HTMLResponse)
async def schedule_index(request: Request, date: Optional[str] = None, db: Session = Depends(get_db)):
    if not date:
        target_date = datetime.now().date()
    else:
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            target_date = datetime.now().date()
            
    day_name = target_date.strftime("%A")
    display_date = target_date.strftime("%d %b %Y")
    
    patients = db.query(Patient).filter(Patient.is_active == True).order_by(Patient.name).all()
    
    shift_data = {"Morning": [], "Afternoon": []}
    
    for p in patients:
        matched_shift = None
        if p.hd_day_1 == day_name:
            matched_shift = p.hd_slot_1
        elif p.hd_day_2 == day_name:
            matched_shift = p.hd_slot_2
        elif p.hd_day_3 == day_name:
            matched_shift = p.hd_slot_3
            
        if matched_shift in shift_data:
            shift_data[matched_shift].append(p)
            
    return templates.TemplateResponse("schedule.html", {
        "request": request,
        "selected_date": target_date.strftime("%Y-%m-%d"),
        "display_date": display_date,
        "day_of_week": day_name,
        "shift_data": shift_data,
        "all_patients": patients,
        "user": get_user(request),
    })

@router.post("/assign")
async def assign_schedule(
    request: Request,
    patient_id: int = Form(...),
    hd_frequency: int = Form(2),
    hd_day_1: str = Form(""),
    hd_slot_1: str = Form(""),
    hd_day_2: str = Form(""),
    hd_slot_2: str = Form(""),
    hd_day_3: str = Form(""),
    hd_slot_3: str = Form(""),
    db: Session = Depends(get_db)
):
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if patient:
        patient.hd_frequency = hd_frequency
        patient.hd_day_1 = hd_day_1 or None
        patient.hd_slot_1 = hd_slot_1 or None
        patient.hd_day_2 = hd_day_2 or None
        patient.hd_slot_2 = hd_slot_2 or None
        patient.hd_day_3 = hd_day_3 or None
        patient.hd_slot_3 = hd_slot_3 or None
        db.commit()
    ref = request.headers.get("referer", "/schedule")
    return RedirectResponse(url=ref, status_code=303)
