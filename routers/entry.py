from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date, datetime
import json
import logging

from database import get_db, Patient, MonthlyRecord, ResearchRecord
from config import templates, _csrf_signer
from itsdangerous import BadData
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
    
    # Calculate stats
    total_count = len(patients)
    completed_count = len(existing_records)
    
    # Calculate days remaining in the month
    try:
        from calendar import monthrange
        year, mon = map(int, month_str.split("-"))
        _, last_day = monthrange(year, mon)
        target_date = date(year, mon, last_day)
        today = date.today()
        if today.year == year and today.month == mon:
            days_remaining = (target_date - today).days
        elif today > target_date:
            days_remaining = 0
        else:
            days_remaining = last_day
    except:
        days_remaining = 0

    from urllib.parse import quote
    return templates.TemplateResponse("entry_list.html", {
        "request": request,
        "patients": patients,
        "patient_slot_info": patient_slot_info,
        "month_str": month_str,
        "month_label": get_month_label(month_str),
        "existing_records": existing_records,
        "total_count": total_count,
        "completed_count": completed_count,
        "days_remaining": days_remaining,
        "return_to_entry": quote(f"/entry?month={month_str}", safe=""),
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

    hosp_details = []
    if rec and rec.hospitalization_details:
        try: hosp_details = json.loads(rec.hospitalization_details)
        except: pass

    # Research Mapped Flag
    is_research_mapped = db.query(ResearchRecord).filter(ResearchRecord.patient_id == patient_id).first() is not None

    # Residual Urine Output Carry-Forward
    carried_ruo = None
    prior_ruo_rec = db.query(MonthlyRecord).filter(
        MonthlyRecord.patient_id == patient_id,
        MonthlyRecord.record_month < month_str,
        MonthlyRecord.residual_urine_output.isnot(None)
    ).order_by(MonthlyRecord.record_month.desc()).first()
    if prior_ruo_rec:
        carried_ruo = prior_ruo_rec.residual_urine_output

    csrf_token = _csrf_signer.sign(f"entry-{patient_id}").decode()
    return templates.TemplateResponse("entry_form.html", {
        "request": request, "patient": p, "record": rec,
        "anti_meds": anti_meds,
        "hosp_details": hosp_details,
        "prior_record": prior_rec,
        "prior_anti_meds": prior_anti_meds,
        "month_str": month_str, "month_label": get_month_label(month_str),
        "prev_month_str": prev_month_str, "prev_month_label": get_month_label(prev_month_str),
        "next_month_str": next_month_str, "next_month_label": get_month_label(next_month_str),
        "user": get_user(request),
        "csrf_token": csrf_token,
        "is_research_mapped": is_research_mapped,
        "carried_ruo": carried_ruo,
    })

from services import entry_service

@router.post("/{patient_id}")
async def save_entry(
    patient_id: int, request: Request, db: Session = Depends(get_db),
    csrf_token: str = Form(...),
    month_str: str = Form(...),
    entered_by: str = Form(""),
    access_type: str = Form(""),
    target_dry_weight: Optional[float] = Form(None),
    idwg: Optional[float] = Form(None),
    last_prehd_weight: Optional[float] = Form(None),
    hb: Optional[float] = Form(None),
    bp_sys: Optional[float] = Form(None),
    bp_dia: Optional[float] = Form(None),
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
    prealbumin: Optional[float] = Form(None),
    npcr: Optional[float] = Form(None),
    sga_score: str = Form(""),
    mis_score: Optional[int] = Form(None),
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
    neutrophil_count: Optional[float] = Form(None),
    platelet_count: Optional[float] = Form(None),
    hba1c: Optional[float] = Form(None),
    vitamin_d_analog_dose: str = Form(""),
    phosphate_binder_type: str = Form(""),
    pb_strength: Optional[float] = Form(None),
    phosphate_binder_dose_mg: Optional[float] = Form(None),
    phosphate_binder_freq: str = Form(""),
    antihypertensive_count: Optional[int] = Form(None),
    antihypertensive_name: list[str] = Form([]),
    antihypertensive_dose: list[str] = Form([]),
    antihypertensive_freq: list[str] = Form([]),
    hrqol_score: Optional[float] = Form(None),
    hospitalization_this_month: bool = Form(False),
    hospitalization_date: list[str] = Form([]),
    hospitalization_diagnosis: list[str] = Form([]),
    hospitalization_icd_code: list[str] = Form([]),
    hospitalization_icd_diagnosis: list[str] = Form([]),
    blood_transfusion_units: Optional[int] = Form(None),
    transfusion_date: Optional[str] = Form(None),
    nt_probnp: Optional[float] = Form(None),
    ejection_fraction: Optional[float] = Form(None),
    diastolic_dysfunction: str = Form(""),
    echo_date: Optional[str] = Form(None),
    clinical_background: str = Form(""),
    issues: str = Form(""),
    action: str = Form("save_back"),
):
    try:
        _csrf_signer.unsign(csrf_token, max_age=3600)
    except BadData:
        raise HTTPException(status_code=403, detail="Invalid or expired form token. Please refresh and try again.")

    session_user = get_user(request)
    if session_user:
        actor = session_user.get("username") if isinstance(session_user, dict) else getattr(session_user, "username", "unknown")
        role = getattr(session_user, "role", None) if not isinstance(session_user, dict) else session_user.get("role", "")
    else:
        actor = "unknown"
        role = ""

    try:
        entry_service.save_monthly_record(db, patient_id, locals(), actor=actor)
    except (ValueError, Exception) as exc:
        db.rollback()
        is_validation = isinstance(exc, ValueError)
        if is_validation:
            logger.warning("VALIDATION ERROR — patient_id=%s: %s", patient_id, exc)
        else:
            logger.error("SAVE FAILED — patient_id=%s month=%s error=%s",
                         patient_id, month_str, exc, exc_info=True)

        # Re-render the form with the error message instead of a blank error page.
        p = db.query(Patient).filter(Patient.id == patient_id).first()
        if not p:
            raise HTTPException(status_code=404)

        year, mon = map(int, month_str.split("-"))
        prev_y, prev_m = (year, mon - 1) if mon > 1 else (year - 1, 12)
        next_y, next_m = (year, mon + 1) if mon < 12 else (year + 1, 1)
        prev_ms = f"{prev_y}-{prev_m:02d}"
        next_ms = f"{next_y}-{next_m:02d}"

        existing_rec = db.query(MonthlyRecord).filter(
            MonthlyRecord.patient_id == patient_id,
            MonthlyRecord.record_month == month_str
        ).first()

        prior_rec = db.query(MonthlyRecord).filter(
            MonthlyRecord.patient_id == patient_id,
            MonthlyRecord.record_month == prev_ms
        ).first()

        _anti_meds, _prior_anti, _hosp = [], [], []
        if existing_rec and existing_rec.antihypertensive_details:
            try: _anti_meds = json.loads(existing_rec.antihypertensive_details)
            except: pass
        if prior_rec and prior_rec.antihypertensive_details:
            try: _prior_anti = json.loads(prior_rec.antihypertensive_details)
            except: pass
        if existing_rec and existing_rec.hospitalization_details:
            try: _hosp = json.loads(existing_rec.hospitalization_details)
            except: pass

        _ruo = None
        _ruo_rec = db.query(MonthlyRecord).filter(
            MonthlyRecord.patient_id == patient_id,
            MonthlyRecord.record_month < month_str,
            MonthlyRecord.residual_urine_output.isnot(None)
        ).order_by(MonthlyRecord.record_month.desc()).first()
        if _ruo_rec:
            _ruo = _ruo_rec.residual_urine_output

        _is_research = db.query(ResearchRecord).filter(
            ResearchRecord.patient_id == patient_id
        ).first() is not None

        _csrf = _csrf_signer.sign(f"entry-{patient_id}").decode()
        return templates.TemplateResponse("entry_form.html", {
            "request": request,
            "patient": p,
            "record": existing_rec,
            "anti_meds": _anti_meds,
            "hosp_details": _hosp,
            "prior_record": prior_rec,
            "prior_anti_meds": _prior_anti,
            "month_str": month_str,
            "month_label": get_month_label(month_str),
            "prev_month_str": prev_ms,
            "prev_month_label": get_month_label(prev_ms),
            "next_month_str": next_ms,
            "next_month_label": get_month_label(next_ms),
            "user": session_user,
            "csrf_token": _csrf,
            "is_research_mapped": _is_research,
            "carried_ruo": _ruo,
            "form_error": str(exc),
        }, status_code=400 if is_validation else 500)

    if action == "save_next":
        # Find next pending patient
        all_active = db.query(Patient).filter(Patient.is_active == True).order_by(Patient.name).all()
        existing = db.query(MonthlyRecord.patient_id).filter(MonthlyRecord.record_month == month_str).all()
        existing_ids = {r[0] for r in existing}

        for p in all_active:
            if p.id not in existing_ids:
                return RedirectResponse(url=f"/entry/{p.id}?month={month_str}&saved=1", status_code=303)

    return RedirectResponse(url=f"/entry?month={month_str}&saved=1", status_code=303)
