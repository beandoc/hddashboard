from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date, datetime, timedelta
import logging

from database import get_db, Patient
from config import templates
from dependencies import get_user, _require_researcher_role

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/schedule", tags=["schedule"])

@router.get("", response_class=HTMLResponse)
async def schedule_index(
    request: Request,
    date: Optional[str] = None,
    saved: Optional[str] = None,
    db: Session = Depends(get_db),
    _auth=Depends(_require_researcher_role),
):
    if not date:
        target_date = datetime.now().date()
    else:
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            try:
                target_date = datetime.strptime(date, "%d/%m/%Y").date()
            except ValueError:
                target_date = datetime.now().date()

    week_start = target_date - timedelta(days=target_date.weekday())
    week_end = week_start + timedelta(days=6)
    week_days = [week_start + timedelta(days=i) for i in range(7)]

    patients = db.query(Patient).filter(Patient.is_active == True).order_by(Patient.name).all()

    schedule_grid = {}
    for wd in week_days:
        dn = wd.strftime("%A")
        schedule_grid[dn] = {"Morning": [], "Afternoon": []}
        for p in patients:
            matched_shift = None
            if p.hd_day_1 and p.hd_day_1.strip().lower() == dn.lower():
                matched_shift = p.hd_slot_1
            elif p.hd_day_2 and p.hd_day_2.strip().lower() == dn.lower():
                matched_shift = p.hd_slot_2
            elif p.hd_day_3 and p.hd_day_3.strip().lower() == dn.lower():
                matched_shift = p.hd_slot_3
            if matched_shift:
                normalized_shift = matched_shift.strip().capitalize()
                if normalized_shift in schedule_grid[dn]:
                    schedule_grid[dn][normalized_shift].append(p)

    day_name = target_date.strftime("%A")
    shift_data = schedule_grid.get(day_name, {"Morning": [], "Afternoon": []})
    display_date = target_date.strftime("%d %b %Y")

    prev_week = (week_start - timedelta(days=7)).strftime("%Y-%m-%d")
    next_week = (week_start + timedelta(days=7)).strftime("%Y-%m-%d")

    return templates.TemplateResponse("schedule.html", {
        "request": request,
        "selected_date": target_date.strftime("%Y-%m-%d"),
        "display_date": display_date,
        "day_of_week": day_name,
        "shift_data": shift_data,
        "all_patients": patients,
        "user": get_user(request),
        "week_start": week_start,
        "week_end": week_end,
        "week_days": week_days,
        "schedule_grid": schedule_grid,
        "prev_week": prev_week,
        "next_week": next_week,
        "saved": saved,
    })

@router.post("/assign")
async def assign_schedule(
    patient_id: int = Form(...),
    hd_frequency: int = Form(2),
    hd_day_1: str = Form(""),
    hd_slot_1: str = Form(""),
    hd_day_2: str = Form(""),
    hd_slot_2: str = Form(""),
    hd_day_3: str = Form(""),
    hd_slot_3: str = Form(""),
    date: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    _auth=Depends(_require_researcher_role),
):
    patient = db.query(Patient).filter(Patient.id == patient_id, Patient.is_active == True).first()
    if patient:
        patient.hd_frequency = hd_frequency
        patient.hd_day_1 = hd_day_1 or None
        patient.hd_slot_1 = hd_slot_1 or None
        patient.hd_day_2 = hd_day_2 or None
        patient.hd_slot_2 = hd_slot_2 or None
        patient.hd_day_3 = hd_day_3 or None
        patient.hd_slot_3 = hd_slot_3 or None
        db.commit()
        date_str = date or datetime.now().date().strftime("%Y-%m-%d")
        return RedirectResponse(url=f"/schedule?date={date_str}&saved=1", status_code=303)
    else:
        raise HTTPException(status_code=404, detail="Patient not found")
