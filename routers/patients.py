from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from typing import Optional
import logging
import re

from database import get_db, Patient, MonthlyRecord, ClinicalEvent, SessionRecord, InterimLabRecord, PatientMealRecord
from config import templates, _csrf_signer
from dependencies import get_user
from dashboard_logic import compute_dashboard, get_current_month_str, get_month_label
from services import patient_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/patients", tags=["patients"])

@router.get("", response_class=HTMLResponse)
async def patient_list(request: Request, month: Optional[str] = None, db: Session = Depends(get_db)):
    month_str = month or get_current_month_str()
    try:
        data = compute_dashboard(db, month_str)
    except Exception as e:
        logger.error(f"Dashboard computation failed for {month_str}: {e}", exc_info=True)
        data = {"patient_rows": [], "metrics": {}}
        
    patients = db.query(Patient).filter(Patient.is_active == True).order_by(Patient.name).all()
    patients_by_id = {p.id: p for p in patients}
    
    return templates.TemplateResponse("patients.html", {
        "request": request,
        "patients": patients,
        "patients_by_id": patients_by_id,
        "data": data,
        "month_str": month_str,
        "current_month": get_current_month_str(),
        "user": get_user(request),
    })

@router.get("/new", response_class=HTMLResponse)
async def new_patient_form(request: Request):
    return templates.TemplateResponse("patient_form.html", {
        "request": request,
        "patient": None,
        "mode": "new",
        "error": None,
        "user": get_user(request),
    })

@router.post("/new")
async def create_patient(
    request: Request,
    db: Session = Depends(get_db),
    hid_no: str = Form(...),
    name: str = Form(...),
    relation: str = Form(""),
    sex: str = Form(...),
    age: int = Form(...),
    contact_no: str = Form(...),
    guardian_name: str = Form(""),
    guardian_contact: str = Form(""),
    address: str = Form(""),
    diagnosis: str = Form(""),
    access_type: str = Form(""),
    dry_weight: float = Form(0.0),
    blood_group: str = Form(""),
    viral_marker_hcv: bool = Form(False),
    viral_marker_hbsag: bool = Form(False),
    viral_marker_hiv: bool = Form(False),
    # CCI Fields
    cad_status: bool = Form(False),
    chf_status: bool = Form(False),
    history_of_pvd: bool = Form(False),
    history_of_stroke: bool = Form(False),
    history_of_dementia: bool = Form(False),
    history_of_cpd: bool = Form(False),
    history_of_ctd: bool = Form(False),
    history_of_pud: bool = Form(False),
    liver_disease: str = Form("None"),
    dm_status: str = Form("None"),
    dm_end_organ_damage: bool = Form(False),
    hemiplegia: bool = Form(False),
    solid_tumor: str = Form("None"),
    leukemia: bool = Form(False),
    lymphoma: bool = Form(False),
    viral_hiv: str = Form("Negative"),
    clinical_background: str = Form(""),
    native_kidney_biopsy_date: Optional[str] = Form(None),
    native_kidney_biopsy_report: str = Form(""),
    echo_date: Optional[str] = Form(None),
    echo_report: str = Form("")
):
    try:
        patient_service.create_patient_record(db, locals())
    except ValueError as e:
        return templates.TemplateResponse("patient_form.html", {
            "request": request, "patient": None, "mode": "new",
            "error": str(e), "user": get_user(request),
        })
    return RedirectResponse(url="/patients", status_code=303)

@router.get("/{patient_id}/profile", response_class=HTMLResponse)
async def patient_profile(patient_id: int, request: Request, db: Session = Depends(get_db), msg: Optional[str] = None):
    import json
    p = db.query(Patient).filter(Patient.id == patient_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")

    monthly_records = db.query(MonthlyRecord).filter(MonthlyRecord.patient_id == patient_id).order_by(MonthlyRecord.record_month.desc()).limit(6).all()
    latest_monthly = monthly_records[0] if len(monthly_records) > 0 else None
    prior_monthly = monthly_records[1] if len(monthly_records) > 1 else None

    # Real trend data (chronological) for chart
    trend_records = list(reversed(monthly_records))
    hb_trend_labels = [r.record_month for r in trend_records]
    
    hb_trend_data = []
    esa_trend_data = []
    for r in trend_records:
        try: hb_trend_data.append(float(r.hb) if r.hb else None)
        except: hb_trend_data.append(None)
        
        try: esa_trend_data.append(round(float(r.epo_weekly_units) / 100, 1) if r.epo_weekly_units else None)
        except: esa_trend_data.append(None)

    csrf_token = _csrf_signer.sign(f"interim-{patient_id}").decode()

    anti_meds = []
    if latest_monthly and latest_monthly.antihypertensive_details:
        try: anti_meds = json.loads(latest_monthly.antihypertensive_details)
        except: pass

    sessions = db.query(SessionRecord).filter(SessionRecord.patient_id == patient_id).order_by(SessionRecord.session_date.desc()).limit(5).all()
    interims = db.query(InterimLabRecord).filter(InterimLabRecord.patient_id == patient_id).order_by(InterimLabRecord.lab_date.desc()).limit(5).all()
    events = db.query(ClinicalEvent).filter(ClinicalEvent.patient_id == patient_id).order_by(ClinicalEvent.event_date.desc()).limit(8).all()

    # 12-month data coverage heatmap
    from datetime import date as _date
    _today = _date.today()
    _y, _m = _today.year, _today.month
    _months_12 = []
    for _ in range(12):
        _months_12.append(f"{_y}-{_m:02d}")
        _m -= 1
        if _m == 0: _m = 12; _y -= 1
    _months_12.reverse()
    _existing_months = {
        r.record_month
        for r in db.query(MonthlyRecord.record_month)
              .filter(MonthlyRecord.patient_id == patient_id,
                      MonthlyRecord.record_month.in_(_months_12))
              .all()
    }
    month_coverage = [
        {
            "month_str": ms,
            "label": get_month_label(ms),
            "abbr": get_month_label(ms)[:3],
            "year": ms[:4],
            "has_data": ms in _existing_months,
        }
        for ms in _months_12
    ]

    eri = None
    if latest_monthly and p.dry_weight and latest_monthly.hb and latest_monthly.epo_weekly_units:
        try: eri = round(float(latest_monthly.epo_weekly_units) / float(p.dry_weight) / float(latest_monthly.hb), 2)
        except: pass

    # Nutrition Logic
    from datetime import date, timedelta
    seven_days_ago = date.today() - timedelta(days=7)
    meal_records = db.query(PatientMealRecord).filter(PatientMealRecord.patient_id == patient_id, PatientMealRecord.date >= seven_days_ago).order_by(PatientMealRecord.date.desc()).all()
    
    meals_by_day = {}
    for m in meal_records:
        d_str = m.date.strftime("%Y-%m-%d")
        if d_str not in meals_by_day:
            meals_by_day[d_str] = {"date": m.date, "total_cal": 0, "total_prot": 0, "entries": []}
        try: meals_by_day[d_str]["total_cal"] += float(m.calories or 0)
        except: pass
        try: meals_by_day[d_str]["total_prot"] += float(m.protein or 0)
        except: pass
        meals_by_day[d_str]["entries"].append(m)

    try:
        w = float(p.dry_weight) if p.dry_weight else 60.0
    except:
        w = 60.0
        
    nutrition_targets = {
        "calories": round(w * 30),
        "protein": round(w * 1.2, 1)
    }

    return templates.TemplateResponse("patient_profile.html", {
        "request": request,
        "patient": p,
        "latest_monthly": latest_monthly,
        "prior_monthly": prior_monthly,
        "anti_meds": anti_meds,
        "sessions": sessions,
        "interims": interims,
        "events": events,
        "eri": eri,
        "meals_by_day": meals_by_day,
        "nutrition_targets": nutrition_targets,
        "month_coverage": month_coverage,
        "hb_trend_labels": hb_trend_labels,
        "hb_trend_data": hb_trend_data,
        "esa_trend_data": esa_trend_data,
        "csrf_token": csrf_token,
        "success_msg": msg,
        "user": get_user(request),
    })

@router.get("/{patient_id}/edit", response_class=HTMLResponse)
async def edit_patient_form(patient_id: int, request: Request, db: Session = Depends(get_db)):
    p = db.query(Patient).filter(Patient.id == patient_id).first()
    if not p: raise HTTPException(status_code=404)
    return templates.TemplateResponse("patient_form.html", {
        "request": request, "patient": p, "mode": "edit", "error": None,
        "user": get_user(request),
    })

@router.post("/{patient_id}/edit")
async def update_patient(
    patient_id: int, db: Session = Depends(get_db),
    hid_no: str = Form(...),
    name: str = Form(...),
    relation: str = Form(""),
    sex: str = Form(...),
    age: int = Form(...),
    contact_no: str = Form(...),
    guardian_name: str = Form(""),
    guardian_contact: str = Form(""),
    address: str = Form(""),
    diagnosis: str = Form(""),
    access_type: str = Form(""),
    dry_weight: float = Form(0.0),
    blood_group: str = Form(""),
    viral_marker_hcv: bool = Form(False),
    viral_marker_hbsag: bool = Form(False),
    viral_marker_hiv: bool = Form(False),
    # CCI Fields
    cad_status: bool = Form(False),
    chf_status: bool = Form(False),
    history_of_pvd: bool = Form(False),
    history_of_stroke: bool = Form(False),
    history_of_dementia: bool = Form(False),
    history_of_cpd: bool = Form(False),
    history_of_ctd: bool = Form(False),
    history_of_pud: bool = Form(False),
    liver_disease: str = Form("None"),
    dm_status: str = Form("None"),
    dm_end_organ_damage: bool = Form(False),
    hemiplegia: bool = Form(False),
    solid_tumor: str = Form("None"),
    leukemia: bool = Form(False),
    lymphoma: bool = Form(False),
    viral_hiv: str = Form("Negative"),
    clinical_background: str = Form(""),
    native_kidney_biopsy_date: Optional[str] = Form(None),
    native_kidney_biopsy_report: str = Form(""),
    echo_date: Optional[str] = Form(None),
    echo_report: str = Form("")
):
    try:
        patient_service.update_patient_record(db, patient_id, locals())
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return RedirectResponse(url="/patients", status_code=303)
