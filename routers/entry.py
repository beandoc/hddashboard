from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date, datetime
import json
import logging

from database import get_db, Patient, MonthlyRecord
from config import templates
from dependencies import get_user
from dashboard_logic import get_current_month_str, get_month_label
from alerts import send_entry_alert_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/entry", tags=["entry"])

def _build_patient_slot_info(p) -> dict:
    """Return display_slots, this_week_dates, and effective hd_frequency."""
    from datetime import timedelta
    cutoff = date.today() - timedelta(days=7)
    shift_names = {"morning", "afternoon"}
    day_to_weekday = {
        "Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3,
        "Friday": 4, "Saturday": 5, "Sunday": 6,
    }

    today = date.today()
    week_monday = today - timedelta(days=today.weekday())

    def _week_date_for_day(day_name: str) -> str:
        wd = day_to_weekday.get(day_name)
        if wd is None:
            return ""
        d = week_monday + timedelta(days=wd)
        return d.strftime("%-d %b")

    slots = []
    for day_raw, shift_raw in (
        (p.hd_day_1, p.hd_slot_1),
        (p.hd_day_2, p.hd_slot_2),
        (p.hd_day_3, p.hd_slot_3),
    ):
        day = (day_raw or "").strip()
        shift_raw = (shift_raw or "").strip()
        shift = shift_raw if shift_raw.lower() in shift_names else ""

        if day:
            slots.append({"day": day, "shift": shift, "date": _week_date_for_day(day)})
        elif shift:
            slots.append({"day": "", "shift": shift, "date": ""})
        else:
            if shift_raw:
                try:
                    slot_date = datetime.strptime(shift_raw, "%d/%m/%Y").date()
                    if slot_date >= cutoff:
                        slots.append({"day": "", "shift": "", "date": slot_date.strftime("%-d %b")})
                except ValueError:
                    slots.append({"day": "", "shift": shift_raw, "date": ""})

    freq = p.hd_frequency or len([s for s in (p.hd_slot_1, p.hd_slot_2, p.hd_slot_3) if s]) or 2
    return {"display_slots": slots, "hd_frequency": freq}

@router.get("", response_class=HTMLResponse)
async def entry_index(request: Request, month: Optional[str] = None, db: Session = Depends(get_db)):
    month_str = month or get_current_month_str()
    patients = db.query(Patient).filter(Patient.is_active == True).order_by(Patient.name).all()
    records = db.query(MonthlyRecord).filter(MonthlyRecord.record_month == month_str).all()
    existing_records = {r.patient_id: r for r in records}
    patient_slot_info = {p.id: _build_patient_slot_info(p) for p in patients}
    return templates.TemplateResponse("entry_list.html", {
        "request": request,
        "patients": patients,
        "patient_slot_info": patient_slot_info,
        "month_str": month_str,
        "month_label": get_month_label(month_str),
        "existing_records": existing_records,
        "user": get_user(request),
    })

@router.get("/{patient_id}", response_class=HTMLResponse)
async def entry_form(patient_id: int, request: Request, month: Optional[str] = None, db: Session = Depends(get_db)):
    p = db.query(Patient).filter(Patient.id == patient_id).first()
    if not p: raise HTTPException(status_code=404)
    month_str = month or get_current_month_str()
    rec = db.query(MonthlyRecord).filter(MonthlyRecord.patient_id == patient_id, MonthlyRecord.record_month == month_str).first()

    year, mon = map(int, month_str.split("-"))
    prev_y, prev_m = (year, mon - 1) if mon > 1 else (year - 1, 12)
    next_y, next_m = (year, mon + 1) if mon < 12 else (year + 1, 1)
    prev_month_str = f"{prev_y}-{prev_m:02d}"
    next_month_str = f"{next_y}-{next_m:02d}"

    prior_rec = db.query(MonthlyRecord).filter(
        MonthlyRecord.patient_id == patient_id,
        MonthlyRecord.record_month == prev_month_str
    ).first()
    prior_anti_meds = []
    if prior_rec and prior_rec.antihypertensive_details:
        try: prior_anti_meds = json.loads(prior_rec.antihypertensive_details)
        except: pass

    anti_meds = []
    if rec and rec.antihypertensive_details:
        try: anti_meds = json.loads(rec.antihypertensive_details)
        except: pass

    return templates.TemplateResponse("entry_form.html", {
        "request": request, "patient": p, "record": rec,
        "anti_meds": anti_meds,
        "prior_record": prior_rec,
        "prior_anti_meds": prior_anti_meds,
        "month_str": month_str, "month_label": get_month_label(month_str),
        "prev_month_str": prev_month_str, "prev_month_label": get_month_label(prev_month_str),
        "next_month_str": next_month_str, "next_month_label": get_month_label(next_month_str),
        "user": get_user(request),
    })

from services import entry_service

@router.post("/{patient_id}")
async def save_entry(
    patient_id: int, db: Session = Depends(get_db),
    month_str: str = Form(...),
    entered_by: str = Form(""),
    access_type: str = Form(""),
    target_dry_weight: Optional[float] = Form(None),
    idwg: Optional[float] = Form(None),
    last_prehd_weight: Optional[float] = Form(None),
    hb: Optional[float] = Form(None),
    bp_sys: Optional[float] = Form(None),
    serum_ferritin: Optional[float] = Form(None),
    tsat: Optional[float] = Form(None),
    serum_iron: Optional[float] = Form(None),
    epo_mircera_dose: str = Form(""),
    desidustat_dose: str = Form(""),
    epo_weekly_units: Optional[float] = Form(None),
    esa_type: str = Form(""),
    calcium: Optional[float] = Form(None),
    alkaline_phosphate: Optional[float] = Form(None),
    phosphorus: Optional[float] = Form(None),
    albumin: Optional[float] = Form(None),
    ast: Optional[float] = Form(None),
    alt: Optional[float] = Form(None),
    vit_d: Optional[float] = Form(None),
    ipth: Optional[float] = Form(None),
    av_daily_calories: Optional[float] = Form(None),
    av_daily_protein: Optional[float] = Form(None),
    urr: Optional[float] = Form(None),
    crp: Optional[float] = Form(None),
    single_pool_ktv: Optional[float] = Form(None),
    equilibrated_ktv: Optional[float] = Form(None),
    pre_dialysis_urea: Optional[float] = Form(None),
    post_dialysis_urea: Optional[float] = Form(None),
    serum_creatinine: Optional[float] = Form(None),
    residual_urine_output: Optional[float] = Form(None),
    tibc: Optional[float] = Form(None),
    iv_iron_product: str = Form(""),
    iv_iron_dose: Optional[float] = Form(None),
    iv_iron_date: Optional[str] = Form(None),
    serum_sodium: Optional[float] = Form(None),
    serum_potassium: Optional[float] = Form(None),
    serum_bicarbonate: Optional[float] = Form(None),
    serum_uric_acid: Optional[float] = Form(None),
    total_cholesterol: Optional[float] = Form(None),
    ldl_cholesterol: Optional[float] = Form(None),
    wbc_count: Optional[float] = Form(None),
    platelet_count: Optional[float] = Form(None),
    hba1c: Optional[float] = Form(None),
    vitamin_d_analog_dose: str = Form(""),
    phosphate_binder_type: str = Form(""),
    antihypertensive_count: Optional[int] = Form(None),
    antihypertensive_name: list[str] = Form([]),
    antihypertensive_dose: list[str] = Form([]),
    antihypertensive_freq: list[str] = Form([]),
    hrqol_score: Optional[float] = Form(None),
    hospitalization_this_month: bool = Form(False),
    hospitalization_date: Optional[str] = Form(None),
    hospitalization_diagnosis: str = Form(""),
    hospitalization_icd_code: str = Form(""),
    hospitalization_icd_diagnosis: str = Form(""),
    clinical_background: str = Form(""),
    issues: str = Form(""),
):
    entry_service.save_monthly_record(db, patient_id, locals())
    return RedirectResponse(url=f"/entry?month={month_str}", status_code=303)
