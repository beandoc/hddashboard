from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional
import logging
import re
from datetime import datetime

from database import get_db, Patient, MonthlyRecord, ClinicalEvent, SessionRecord, InterimLabRecord, PatientMealRecord, HospitalisationEvent
from config import templates, _csrf_signer
from itsdangerous import BadData
from dependencies import get_user, _require_admin_role
from dashboard_logic import compute_dashboard, get_current_month_str, get_month_label, get_effective_month, _resolve_epo_dose
from services import patient_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/patients", tags=["patients"])

@router.get("", response_class=HTMLResponse)
async def patient_list(
    request: Request,
    month: Optional[str] = None,
    filter: Optional[str] = None,
    sort: Optional[str] = None,
    dir: Optional[str] = None,
    chip: Optional[str] = None,
    db: Session = Depends(get_db),
):
    month_str, data_note = get_effective_month(db, month)
    try:
        data = compute_dashboard(db, month_str)
        data["data_note"] = data_note
    except Exception as e:
        logger.error(f"Dashboard computation failed for {month_str}: {e}", exc_info=True)
        data = {"patient_rows": [], "metrics": {}, "data_note": data_note}

    _current_month = get_current_month_str()
    csrf_token = _csrf_signer.sign("events-new").decode()
    return templates.TemplateResponse("patients.html", {
        "request": request,
        "data": data,
        "month_str": month_str,
        "current_month": _current_month,
        "current_month_label": get_month_label(_current_month),
        "user": get_user(request),
        "active_filter": filter,
        "active_sort": sort or "name",
        "active_dir": dir or "asc",
        "active_chip": chip or "",
        "csrf_token": csrf_token,
    })

@router.get("/new", response_class=HTMLResponse)
async def new_patient_form(request: Request):
    _require_admin_role(request)
    csrf_token = _csrf_signer.sign("patient-new").decode()
    return templates.TemplateResponse("patient_form.html", {
        "request": request,
        "patient": None,
        "mode": "new",
        "error": None,
        "user": get_user(request),
        "csrf_token": csrf_token,
    })

@router.post("/new")
async def create_patient(
    request: Request,
    db: Session = Depends(get_db),
    csrf_token: str = Form(...),
    # ── Identity ──────────────────────────────────────────────────────────────
    hid_no: str = Form(...),
    name: str = Form(...),
    sex: str = Form(...),
    age: Optional[int] = Form(None),
    relation: str = Form(""),
    relation_type: str = Form(""),
    contact_no: str = Form(""),
    email: str = Form(""),
    address: str = Form(""),
    height: Optional[float] = Form(None),
    handgrip_strength: Optional[float] = Form(None),
    blood_group: str = Form(""),
    education_level: str = Form(""),
    healthcare_facility: str = Form(""),
    # ── Renal / HD history ────────────────────────────────────────────────────
    diagnosis: str = Form(""),
    primary_renal_disease: str = Form(""),
    date_esrd_diagnosis: Optional[str] = Form(None),
    hd_wef_date: Optional[str] = Form(None),
    dialysis_modality: str = Form(""),
    previous_krt_modality: str = Form(""),
    history_of_renal_transplant: bool = Form(False),
    transplant_prospect: str = Form(""),
    # ── Comorbidities (CCI) ───────────────────────────────────────────────────
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
    htn_status: bool = Form(False),
    smoking_status: str = Form(""),
    alcohol_consumption: str = Form(""),
    comorbidities: str = Form(""),
    drug_allergies: str = Form(""),
    clinical_background: str = Form(""),
    # ── Cardiac ───────────────────────────────────────────────────────────────
    ejection_fraction: Optional[float] = Form(None),
    diastolic_dysfunction: str = Form(""),
    echo_date: Optional[str] = Form(None),
    echo_report: str = Form(""),
    lvot_diameter: Optional[float] = Form(None),
    lvot_vti: Optional[float] = Form(None),
    heart_rate: Optional[int] = Form(None),
    stroke_volume: Optional[float] = Form(None),
    cardiac_output: Optional[float] = Form(None),
    # ── Vascular access ───────────────────────────────────────────────────────
    access_type: str = Form(""),
    access_date: Optional[str] = Form(None),
    date_first_cannulation: Optional[str] = Form(None),
    history_of_access_thrombosis: bool = Form(False),
    access_intervention_history: str = Form(""),
    catheter_type: str = Form(""),
    catheter_insertion_site: str = Form(""),
    # ── Dry weight ────────────────────────────────────────────────────────────
    dry_weight: Optional[float] = Form(None),
    # ── Viral markers ─────────────────────────────────────────────────────────
    viral_hiv: str = Form("Negative"),
    viral_hbsag: str = Form(""),
    viral_anti_hcv: str = Form(""),
    # ── Vaccination ───────────────────────────────────────────────────────────
    hep_b_status: str = Form(""),
    hep_b_dose1_date: Optional[str] = Form(None),
    hep_b_dose2_date: Optional[str] = Form(None),
    hep_b_dose3_date: Optional[str] = Form(None),
    hep_b_dose4_date: Optional[str] = Form(None),
    hep_b_titer_date: Optional[str] = Form(None),
    pcv13_date: Optional[str] = Form(None),
    ppsv23_date: Optional[str] = Form(None),
    hz_dose1_date: Optional[str] = Form(None),
    hz_dose2_date: Optional[str] = Form(None),
    influenza_date: Optional[str] = Form(None),
    # ── Biopsy ────────────────────────────────────────────────────────────────
    native_kidney_biopsy: str = Form(""),
    native_kidney_biopsy_date: Optional[str] = Form(None),
    native_kidney_biopsy_report: str = Form(""),
    # ── Outcome / status ──────────────────────────────────────────────────────
    current_survival_status: str = Form(""),
    date_of_death: Optional[str] = Form(None),
    primary_cause_of_death: str = Form(""),
    date_of_transplant: Optional[str] = Form(None),
    withdrawal_date: Optional[str] = Form(None),
    withdrawal_reason: str = Form(""),
    withdrawal_clinician: str = Form(""),
    date_facility_transfer: Optional[str] = Form(None),
    # ── Notifications ─────────────────────────────────────────────────────────
    whatsapp_notify: bool = Form(False),
    mail_trigger: bool = Form(False),
):
    _require_admin_role(request)
    try:
        _csrf_signer.unsign(csrf_token, max_age=3600)
    except BadData:
        raise HTTPException(status_code=403, detail="Invalid or expired form token. Please refresh and try again.")
    try:
        new_patient = patient_service.create_patient_record(db, locals())
    except ValueError as e:
        fresh_csrf = _csrf_signer.sign("patient-new").decode()
        return templates.TemplateResponse("patient_form.html", {
            "request": request, "patient": None, "mode": "new",
            "error": str(e), "user": get_user(request),
            "csrf_token": fresh_csrf,
        })
    return RedirectResponse(url=f"/patients/{new_patient.id}/profile", status_code=303)

@router.get("/{patient_id}/profile", response_class=HTMLResponse)
async def patient_profile(patient_id: int, request: Request, db: Session = Depends(get_db), msg: Optional[str] = None):
    import json
    p = db.query(Patient).filter(Patient.id == patient_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")

    monthly_records = db.query(MonthlyRecord).filter(MonthlyRecord.patient_id == patient_id).order_by(MonthlyRecord.record_month.desc()).limit(6).all()
    latest_monthly = monthly_records[0] if len(monthly_records) > 0 else None
    prior_monthly = monthly_records[1] if len(monthly_records) > 1 else None

    # ── Look-back for quarterly/infrequent labs ───────────────────────────────
    # iPTH, Ferritin, TSAT, CRP, Calcium are NOT measured monthly.
    # We search up to 6 months back to find the last recorded value.
    # This is used in the template to show a "last known" badge instead of "—".
    # Quarterly / intermittent labs — NOT measured every month by default.
    # Calcium and Phosphorus ARE monthly — excluded here.
    QUARTERLY_FIELDS = {
        "ipth":           {"label": "Parathyroid hormone(iPTH)",      "unit": "pg/mL"},
        "serum_ferritin": {"label": "Ferritin",  "unit": "ng/mL"},
        "tsat":           {"label": "TSAT",       "unit": "%"},
        "serum_iron":     {"label": "Serum Iron", "unit": "µg/dL"},
        "vit_d":          {"label": "Vit D",      "unit": "ng/mL"},
    }

    # Load up to 6 months of records for look-back (already fetched above)
    lookback_records = monthly_records  # already desc order, last 6 months

    # Interim lab parameter names for each quarterly field (lowercase, as stored in InterimLabRecord)
    QUARTERLY_INTERIM_PARAM = {
        "ipth":           "ipth",
        "serum_ferritin": "ferritin",
        "tsat":           "tsat",
        "serum_iron":     "serum_iron",
        "vit_d":          "vit_d",
    }

    quarterly_labs = {}
    latest_month_str = latest_monthly.record_month if latest_monthly else None

    for field, meta in QUARTERLY_FIELDS.items():
        found_val = None
        found_month = None
        months_ago = None
        source = "monthly"

        for r in lookback_records:
            val = getattr(r, field, None)
            if val is not None:
                found_val = val
                found_month = r.record_month
                if latest_month_str and found_month:
                    try:
                        ly, lm = int(latest_month_str[:4]), int(latest_month_str[5:7])
                        fy, fm = int(found_month[:4]),      int(found_month[5:7])
                        months_ago = (ly * 12 + lm) - (fy * 12 + fm)
                    except Exception:
                        months_ago = None
                break  # stop at first found (most recent)

        # Fallback: search InterimLabRecord if monthly records have no value
        if found_val is None:
            interim_param = QUARTERLY_INTERIM_PARAM.get(field)
            if interim_param:
                interim_hit = (
                    db.query(InterimLabRecord)
                    .filter(
                        InterimLabRecord.patient_id == patient_id,
                        InterimLabRecord.parameter == interim_param,
                    )
                    .order_by(InterimLabRecord.lab_date.desc())
                    .first()
                )
                if interim_hit:
                    found_val = interim_hit.value
                    found_month = str(interim_hit.lab_date)[:7] if interim_hit.lab_date else None
                    source = "interim"
                    if latest_month_str and found_month:
                        try:
                            ly, lm = int(latest_month_str[:4]), int(latest_month_str[5:7])
                            fy, fm = int(found_month[:4]),      int(found_month[5:7])
                            months_ago = (ly * 12 + lm) - (fy * 12 + fm)
                        except Exception:
                            months_ago = None

        quarterly_labs[field] = {
            "label":      meta["label"],
            "unit":       meta["unit"],
            "value":      found_val,
            "month":      found_month,
            "months_ago": months_ago,
            "source":     source,
            # current = value is in the latest monthly record itself
            "is_current": (found_month == latest_month_str) if (found_month and source == "monthly") else False,
        }

    # Real trend data (chronological) for chart
    trend_records = list(reversed(monthly_records))
    hb_trend_labels = [r.record_month for r in trend_records]
    
    hb_trend_data = []
    esa_trend_data = []
    weight_trend_data = []
    albumin_trend_data = []
    idwg_trend_data = []

    for r in trend_records:
        try: hb_trend_data.append(float(r.hb) if r.hb else None)
        except: hb_trend_data.append(None)

        try:
            _dose = _resolve_epo_dose(r)
            esa_trend_data.append(float(_dose) if _dose is not None else None)
        except: esa_trend_data.append(None)

        try: weight_trend_data.append(float(r.target_dry_weight) if r.target_dry_weight else None)
        except: weight_trend_data.append(None)

        try: albumin_trend_data.append(float(r.albumin) if r.albumin else None)
        except: albumin_trend_data.append(None)

        try: idwg_trend_data.append(float(r.idwg) if r.idwg else None)
        except: idwg_trend_data.append(None)

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
    if latest_monthly and latest_monthly.hb:
        try:
            _dose = _resolve_epo_dose(latest_monthly)
            _weight = latest_monthly.target_dry_weight or p.dry_weight
            if _dose and _weight and float(latest_monthly.hb) > 0:
                # ERI = (Weekly ESA Dose / Weight) / Hemoglobin (g/dL)
                eri = round((float(_dose) / float(_weight)) / float(latest_monthly.hb), 2)
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

    # KRCRw Trend Logic
    krcr_trend_labels = []
    krcr_trend_data = []
    if p.baseline_gcr and p.baseline_vdcr:
        from krcrw_model import track_patient_krcrw_over_time
        krcr_history = track_patient_krcrw_over_time(
            sex=p.sex or "m",
            age=p.age or 50,
            weight=p.dry_weight or 60.0,
            baseline_gcr=p.baseline_gcr,
            baseline_vdcr=p.baseline_vdcr,
            hd_frequency=p.hd_frequency or 2,
            records=p.records
        )
        for h in sorted(krcr_history, key=lambda x: x["month"]):
            krcr_trend_labels.append(get_month_label(h["month"]))
            krcr_trend_data.append(h["krcr"])

    try:
        w = float(p.dry_weight) if p.dry_weight else 60.0
    except:
        w = 60.0
        
    nutrition_targets = {
        "calories": round(w * 30),
        "protein": round(w * 1.2, 1)
    }

    from alerts import build_individual_whatsapp_link
    wa_link = build_individual_whatsapp_link(p, latest_monthly, get_month_label(latest_monthly.record_month) if latest_monthly else "")

    hospitalisations = (
        db.query(HospitalisationEvent)
        .filter(HospitalisationEvent.patient_id == patient_id)
        .order_by(HospitalisationEvent.admission_date.desc())
        .all()
    )

    return templates.TemplateResponse("patient_profile.html", {
        "request": request,
        "patient": p,
        "latest_monthly": latest_monthly,
        "prior_monthly": prior_monthly,
        "quarterly_labs": quarterly_labs,
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
        "weight_trend_data": weight_trend_data,
        "albumin_trend_data": albumin_trend_data,
        "idwg_trend_data": idwg_trend_data,
        "krcr_trend_labels": krcr_trend_labels,
        "krcr_trend_data": krcr_trend_data,
        "csrf_token": csrf_token,
        "success_msg": msg,
        "user": get_user(request),
        "whatsapp_link": wa_link,
        "hospitalisations": hospitalisations,
    })

@router.get("/{patient_id}/summary", response_class=HTMLResponse)
async def patient_clinical_summary(patient_id: int, request: Request, db: Session = Depends(get_db)):
    import json
    from datetime import datetime
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient: raise HTTPException(status_code=404)
    
    record = db.query(MonthlyRecord).filter(MonthlyRecord.patient_id == patient_id).order_by(MonthlyRecord.record_month.desc()).first()
    
    meds = []
    if record and record.antihypertensive_details:
        try: meds = json.loads(record.antihypertensive_details)
        except: meds = []
    
    # Simple alert logic for the summary card
    alerts = []
    if record:
        if record.hb and record.hb < 10: alerts.append(f"Low Hb: {record.hb} g/dL")
        if record.phosphorus and record.phosphorus > 5.5: alerts.append(f"High Phos: {record.phosphorus} mg/dL")
        if record.albumin and record.albumin < 3.5: alerts.append(f"Low Albumin: {record.albumin} g/dL")
        if record.single_pool_ktv and record.single_pool_ktv < 1.2: alerts.append(f"Inadequate Kt/V: {record.single_pool_ktv}")
        if record.idwg and record.idwg > 2.5: alerts.append(f"High IDWG: {record.idwg} kg")

        # Persistent IDH Alarm
        sessions = db.query(SessionRecord).filter(SessionRecord.patient_id == patient_id).order_by(SessionRecord.session_date.desc()).limit(5).all()
        recent_idh = [s.idh_episode for s in sessions if s.idh_episode]
        if len(recent_idh) >= 2:
            alerts.append("Persistent Intradialytic Hypotension: Risk of myocardial stunning & access clotting.")

    return templates.TemplateResponse("patient_summary_card.html", {
        "request": request, "patient": patient, "record": record, "meds": meds,
        "alerts": alerts, "now": datetime.now(), "user": get_user(request)
    })

@router.get("/{patient_id}/meds", response_class=HTMLResponse)
async def patient_med_recon(patient_id: int, request: Request, db: Session = Depends(get_db)):
    import json
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient: raise HTTPException(status_code=404)

    record = db.query(MonthlyRecord).filter(MonthlyRecord.patient_id == patient_id).order_by(MonthlyRecord.record_month.desc()).first()

    meds = []
    if record and record.antihypertensive_details:
        try:
            meds = json.loads(record.antihypertensive_details)
        except Exception:
            meds = []

    pb_list_parsed = []
    if record and record.phosphate_binder_details:
        try:
            pb_list_parsed = json.loads(record.phosphate_binder_details)
        except Exception:
            pb_list_parsed = []

    return templates.TemplateResponse("med_recon.html", {
        "request": request,
        "patient": patient,
        "record": record,
        "meds": meds,
        "pb_list_parsed": pb_list_parsed,
        "user": get_user(request)
    })

@router.get("/{patient_id}/edit", response_class=HTMLResponse)
async def edit_patient_form(patient_id: int, request: Request, db: Session = Depends(get_db), return_to: Optional[str] = None):
    p = db.query(Patient).filter(Patient.id == patient_id).first()
    if not p: raise HTTPException(status_code=404)
    csrf_token = _csrf_signer.sign(f"patient-edit-{patient_id}").decode()
    return templates.TemplateResponse("patient_form.html", {
        "request": request, "patient": p, "mode": "edit", "error": None,
        "user": get_user(request),
        "return_to": return_to,
        "csrf_token": csrf_token,
    })

@router.post("/{patient_id}/edit")
async def update_patient(
    request: Request,
    patient_id: int, db: Session = Depends(get_db),
    csrf_token: str = Form(...),
    # ── Identity ──────────────────────────────────────────────────────────────
    hid_no: str = Form(...),
    name: str = Form(...),
    sex: str = Form(...),
    age: Optional[int] = Form(None),
    relation: str = Form(""),
    relation_type: str = Form(""),
    contact_no: str = Form(""),
    email: str = Form(""),
    guardian_name: str = Form(""),
    guardian_contact: str = Form(""),
    address: str = Form(""),
    height: Optional[float] = Form(None),
    handgrip_strength: Optional[float] = Form(None),
    blood_group: str = Form(""),
    education_level: str = Form(""),
    healthcare_facility: str = Form(""),
    # ── Renal / HD history ────────────────────────────────────────────────────
    diagnosis: str = Form(""),
    primary_renal_disease: str = Form(""),
    date_esrd_diagnosis: Optional[str] = Form(None),
    hd_wef_date: Optional[str] = Form(None),
    dialysis_modality: str = Form(""),
    previous_krt_modality: str = Form(""),
    history_of_renal_transplant: bool = Form(False),
    transplant_prospect: str = Form(""),
    # ── Comorbidities (CCI) ───────────────────────────────────────────────────
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
    htn_status: bool = Form(False),
    smoking_status: str = Form(""),
    alcohol_consumption: str = Form(""),
    comorbidities: str = Form(""),
    drug_allergies: str = Form(""),
    clinical_background: str = Form(""),
    # ── Cardiac ───────────────────────────────────────────────────────────────
    ejection_fraction: Optional[float] = Form(None),
    diastolic_dysfunction: str = Form(""),
    echo_date: Optional[str] = Form(None),
    echo_report: str = Form(""),
    lvot_diameter: Optional[float] = Form(None),
    lvot_vti: Optional[float] = Form(None),
    heart_rate: Optional[int] = Form(None),
    stroke_volume: Optional[float] = Form(None),
    cardiac_output: Optional[float] = Form(None),
    # ── Vascular access ───────────────────────────────────────────────────────
    access_type: str = Form(""),
    access_date: Optional[str] = Form(None),
    date_first_cannulation: Optional[str] = Form(None),
    history_of_access_thrombosis: bool = Form(False),
    access_intervention_history: str = Form(""),
    catheter_type: str = Form(""),
    catheter_insertion_site: str = Form(""),
    # ── Dry weight ────────────────────────────────────────────────────────────
    dry_weight: Optional[float] = Form(None),
    # ── Viral markers ─────────────────────────────────────────────────────────
    viral_hiv: str = Form("Negative"),
    viral_hbsag: str = Form(""),
    viral_anti_hcv: str = Form(""),
    # ── Vaccination ───────────────────────────────────────────────────────────
    hep_b_status: str = Form(""),
    hep_b_dose1_date: Optional[str] = Form(None),
    hep_b_dose2_date: Optional[str] = Form(None),
    hep_b_dose3_date: Optional[str] = Form(None),
    hep_b_dose4_date: Optional[str] = Form(None),
    hep_b_titer_date: Optional[str] = Form(None),
    pcv13_date: Optional[str] = Form(None),
    ppsv23_date: Optional[str] = Form(None),
    hz_dose1_date: Optional[str] = Form(None),
    hz_dose2_date: Optional[str] = Form(None),
    influenza_date: Optional[str] = Form(None),
    # ── Biopsy ────────────────────────────────────────────────────────────────
    native_kidney_biopsy: str = Form(""),
    native_kidney_biopsy_date: Optional[str] = Form(None),
    native_kidney_biopsy_report: str = Form(""),
    # ── Outcome / status ──────────────────────────────────────────────────────
    current_survival_status: str = Form(""),
    date_of_death: Optional[str] = Form(None),
    primary_cause_of_death: str = Form(""),
    date_of_transplant: Optional[str] = Form(None),
    withdrawal_date: Optional[str] = Form(None),
    withdrawal_reason: str = Form(""),
    withdrawal_clinician: str = Form(""),
    date_facility_transfer: Optional[str] = Form(None),
    # ── Notifications ─────────────────────────────────────────────────────────
    whatsapp_notify: bool = Form(False),
    mail_trigger: bool = Form(False),
):
    try:
        _csrf_signer.unsign(csrf_token, max_age=3600)
    except BadData:
        raise HTTPException(status_code=403, detail="Invalid or expired form token. Please refresh and try again.")

    return_to = request.query_params.get("return_to")

    try:
        patient_service.update_patient_record(db, patient_id, locals())
    except ValueError as e:
        p = db.query(Patient).filter(Patient.id == patient_id).first()
        if not p:
            raise HTTPException(status_code=404)
        fresh_csrf = _csrf_signer.sign(f"patient-edit-{patient_id}").decode()
        return templates.TemplateResponse("patient_form.html", {
            "request": request, "patient": p, "mode": "edit",
            "error": str(e), "user": get_user(request),
            "csrf_token": fresh_csrf,
            "return_to": return_to,
        })

    if return_to:
        return RedirectResponse(url=return_to, status_code=303)
    return RedirectResponse(url=f"/patients/{patient_id}/profile", status_code=303)

@router.post("/{patient_id}/deactivate")
async def deactivate_patient(
    patient_id: int,
    request: Request,
    db: Session = Depends(get_db),
    is_death: str = Form("0"),
    date_of_death: str = Form(""),
    cause_of_death: str = Form(""),
):
    """Deactivates a patient record. Restricted to admin/doctor roles."""
    user = get_user(request)

    if isinstance(user, dict):
        role = user.get("role")
        username = user.get("username", "unknown")
    else:
        role = getattr(user, "role", None)
        username = getattr(user, "username", "unknown")

    if not user or role not in ["admin", "doctor"]:
        logger.warning(f"Unauthorized deactivation attempt for patient {patient_id} by '{username}' (role={role})")
        raise HTTPException(status_code=403, detail="Only doctors or admins can deactivate patients.")

    p = db.query(Patient).filter(Patient.id == patient_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")

    if not p.is_active:
        logger.info(f"Patient {patient_id} ({p.name}) was already inactive. No-op by '{username}'")
        return RedirectResponse(url="/patients", status_code=303)

    try:
        params: dict = {"now": datetime.utcnow(), "pid": patient_id}
        if is_death == "1" and date_of_death:
            try:
                dod = datetime.strptime(date_of_death, "%Y-%m-%d").date()
            except ValueError:
                dod = None
            params["dod"] = dod
            params["cause"] = cause_of_death or None
            db.execute(
                text("UPDATE patients SET is_active = false, updated_at = :now WHERE id = :pid"),
                params,
            )
            # date_of_death / primary_cause_of_death live in patient_outcomes
            db.execute(
                text(
                    "INSERT INTO patient_outcomes "
                    "(patient_id, date_of_death, primary_cause_of_death, current_survival_status) "
                    "VALUES (:pid, :dod, :cause, 'Deceased') "
                    "ON CONFLICT (patient_id) DO UPDATE SET "
                    "date_of_death = EXCLUDED.date_of_death, "
                    "primary_cause_of_death = EXCLUDED.primary_cause_of_death, "
                    "current_survival_status = 'Deceased'"
                ),
                params,
            )
            logger.info(f"Patient {patient_id} ({p.name}) deactivated (deceased) by '{username}'")
        else:
            db.execute(
                text("UPDATE patients SET is_active = false, updated_at = :now WHERE id = :pid"),
                params,
            )
            logger.info(f"Patient {patient_id} ({p.name}) deactivated by '{username}'")
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"CRITICAL: Failed to deactivate patient {patient_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error during deactivation. Error: {str(e)}")

    return RedirectResponse(url="/patients", status_code=303)


# ── Hospitalisation Event Log ─────────────────────────────────────────────────

@router.get("/{patient_id}/clinical-events-json")
async def patient_clinical_events_json(
    patient_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Return ClinicalEvents for a patient as JSON for the hospitalisation link picker.
    Only includes event types that are plausibly associated with an admission."""
    from fastapi.responses import JSONResponse
    user = get_user(request)
    if not user:
        raise HTTPException(status_code=401)
    p = db.query(Patient).filter(Patient.id == patient_id).first()
    if not p:
        raise HTTPException(status_code=404)

    events = (
        db.query(ClinicalEvent)
        .filter(ClinicalEvent.patient_id == patient_id)
        .order_by(ClinicalEvent.event_date.desc())
        .limit(120)
        .all()
    )

    result = []
    for ev in events:
        result.append({
            "id": ev.id,
            "event_date": ev.event_date.strftime("%Y-%m-%d"),
            "event_date_display": ev.event_date.strftime("%d %b %Y"),
            "event_type": ev.event_type,
            "severity": ev.severity or "",
            "notes": (ev.notes or "")[:120],
        })

    return JSONResponse(content=result)


@router.get("/{patient_id}/hospitalisations", response_class=HTMLResponse)
async def patient_hospitalisations_page(
    patient_id: int, request: Request, db: Session = Depends(get_db),
    open: Optional[str] = None,
):
    p = db.query(Patient).filter(Patient.id == patient_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")
    hospitalisations = (
        db.query(HospitalisationEvent)
        .filter(HospitalisationEvent.patient_id == patient_id)
        .order_by(HospitalisationEvent.admission_date.desc())
        .all()
    )
    clinical_events = (
        db.query(ClinicalEvent)
        .filter(ClinicalEvent.patient_id == patient_id)
        .order_by(ClinicalEvent.event_date.desc())
        .limit(120)
        .all()
    )
    return templates.TemplateResponse("patient_hospitalisations.html", {
        "request": request,
        "patient": p,
        "hospitalisations": hospitalisations,
        "clinical_events": clinical_events,
        "user": get_user(request),
        "open": open,
    })


@router.post("/{patient_id}/hospitalisations")
async def add_hospitalisation(
    patient_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admission_date: str = Form(...),
    discharge_date: Optional[str] = Form(None),
    los_days: Optional[int] = Form(None),
    diagnosis: list[str] = Form([], alias="diagnosis[]"),
    icd_code: list[str] = Form([], alias="icd_code[]"),
    icd_name: list[str] = Form([], alias="icd_name[]"),
    notes: str = Form(""),
    clinical_event_id: Optional[str] = Form(None),
    new_event_type: Optional[str] = Form(None),
    new_event_date: Optional[str] = Form(None),
    new_event_severity: Optional[str] = Form(None),
    new_event_notes: Optional[str] = Form(None),
    severity: Optional[str] = Form(None),
    icu_admission: Optional[str] = Form(None),
    pct: Optional[float] = Form(None),
    shock_on_admission: Optional[int] = Form(None),
    inotrope_days: Optional[float] = Form(None),
    ventilation_days: Optional[float] = Form(None),
    transfusion_units: Optional[float] = Form(None),
):
    import json as _json
    user = get_user(request)
    p = db.query(Patient).filter(Patient.id == patient_id).first()
    if not p:
        raise HTTPException(status_code=404)

    try:
        adm = datetime.strptime(admission_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid admission_date")

    dis = None
    los = los_days
    if discharge_date:
        try:
            dis = datetime.strptime(discharge_date, "%Y-%m-%d").date()
            if los is None:
                los = max((dis - adm).days, 0)
        except ValueError:
            pass

    # Build structured diagnosis list — filter out blank rows
    def _pad(lst, n): return lst + [''] * (n - len(lst))
    n = max(len(diagnosis), len(icd_code), len(icd_name))
    diag_list = []
    for d, c, nm in zip(_pad(diagnosis, n), _pad(icd_code, n), _pad(icd_name, n)):
        d = d.strip(); c = c.strip(); nm = nm.strip()
        if d:
            diag_list.append({"diagnosis": d, "icd_code": c, "icd_name": nm})

    # primary fields from first entry for ML training path
    primary_diag = diag_list[0]["diagnosis"] if diag_list else None
    primary_icd  = diag_list[0]["icd_code"]  if diag_list else None

    # Store all diagnoses as JSON in notes; append free-text notes after
    notes_clean = notes.strip() if notes else ""
    if diag_list:
        notes_stored = _json.dumps(diag_list, ensure_ascii=False)
        if notes_clean:
            notes_stored = notes_stored + "\n" + notes_clean
    else:
        notes_stored = notes_clean or None

    from datetime import timedelta
    prior = (
        db.query(HospitalisationEvent)
        .filter(
            HospitalisationEvent.patient_id == patient_id,
            HospitalisationEvent.discharge_date != None,
            HospitalisationEvent.discharge_date >= adm - timedelta(days=30),
            HospitalisationEvent.discharge_date < adm,
        )
        .first()
    )

    username = (user.get("username") if isinstance(user, dict) else getattr(user, "username", "")) if user else ""

    # Resolve linked clinical event — either an existing one or create inline
    linked_event_id = None
    if clinical_event_id == "__new__" and new_event_type and new_event_type.strip():
        try:
            ev_date = datetime.strptime(new_event_date, "%Y-%m-%d").date() if new_event_date else adm
        except ValueError:
            ev_date = adm
        new_ce = ClinicalEvent(
            patient_id=patient_id,
            event_date=ev_date,
            event_type=new_event_type.strip(),
            severity=new_event_severity or "Medium",
            notes=new_event_notes.strip() if new_event_notes else None,
            created_by=username,
        )
        db.add(new_ce)
        db.flush()  # get new_ce.id without committing
        linked_event_id = new_ce.id
    elif clinical_event_id and clinical_event_id != "__new__":
        try:
            ce_id = int(clinical_event_id)
            ce = db.query(ClinicalEvent).filter(
                ClinicalEvent.id == ce_id,
                ClinicalEvent.patient_id == patient_id,
            ).first()
            if ce:
                linked_event_id = ce.id
        except (ValueError, TypeError):
            pass
    icu_checked = bool(icu_admission == "1" or icu_admission == "on" or icu_admission is True)
    ev = HospitalisationEvent(
        patient_id=patient_id,
        admission_date=adm,
        discharge_date=dis,
        los_days=los,
        primary_icd=primary_icd or None,
        primary_diagnosis=primary_diag or None,
        cause_category=None,
        readmission_within_30d=bool(prior),
        notes=notes_stored or None,
        entered_by=username,
        clinical_event_id=linked_event_id,
        severity=severity or None,
        icu_admission=icu_checked,
        pct=pct,
        shock_on_admission=shock_on_admission or 0,
        inotrope_days=inotrope_days,
        ventilation_days=ventilation_days,
        transfusion_units=transfusion_units,
    )
    db.add(ev)

    from services.patient_service import sync_hospitalization_to_monthly_record
    sync_hospitalization_to_monthly_record(
        db=db,
        patient_id=patient_id,
        event_date=adm,
        diagnosis=primary_diag or "",
        icd_code=primary_icd or "",
        icd_diagnosis="",
        discharge_date=dis,
        los_days=los,
        severity=severity or None,
        icu_admission=icu_checked,
        pct=pct,
        shock_on_admission=shock_on_admission,
        inotrope_days=inotrope_days,
        ventilation_days=ventilation_days,
        transfusion_units=transfusion_units,
    )

    db.commit()
    return RedirectResponse(url=f"/patients/{patient_id}/hospitalisations", status_code=303)


@router.post("/{patient_id}/hospitalisations/{event_id}/edit")
async def edit_hospitalisation(
    patient_id: int,
    event_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admission_date: str = Form(...),
    discharge_date: Optional[str] = Form(None),
    los_days: Optional[int] = Form(None),
    diagnosis: list[str] = Form([], alias="diagnosis[]"),
    icd_code: list[str] = Form([], alias="icd_code[]"),
    icd_name: list[str] = Form([], alias="icd_name[]"),
    notes: str = Form(""),
    clinical_event_id: Optional[int] = Form(None),
    severity: Optional[str] = Form(None),
    icu_admission: Optional[str] = Form(None),
    pct: Optional[float] = Form(None),
    shock_on_admission: Optional[int] = Form(None),
    inotrope_days: Optional[float] = Form(None),
    ventilation_days: Optional[float] = Form(None),
    transfusion_units: Optional[float] = Form(None),
):
    import json as _json
    user = get_user(request)
    role = (user.get("role") if isinstance(user, dict) else getattr(user, "role", "")) if user else ""
    if role not in ("admin", "doctor"):
        raise HTTPException(status_code=403)

    ev = db.query(HospitalisationEvent).filter(
        HospitalisationEvent.id == event_id,
        HospitalisationEvent.patient_id == patient_id,
    ).first()
    if not ev:
        raise HTTPException(status_code=404)

    try:
        adm = datetime.strptime(admission_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid admission_date")

    dis = None
    los = los_days
    if discharge_date:
        try:
            dis = datetime.strptime(discharge_date, "%Y-%m-%d").date()
            if los is None:
                los = max((dis - adm).days, 0)
        except ValueError:
            pass

    # Rebuild diagnosis list
    def _pad(lst, n): return lst + [''] * (n - len(lst))
    n = max(len(diagnosis), len(icd_code), len(icd_name), 1)
    diag_list = []
    for d, c, nm in zip(_pad(diagnosis, n), _pad(icd_code, n), _pad(icd_name, n)):
        d = d.strip(); c = c.strip(); nm = nm.strip()
        if d:
            diag_list.append({"diagnosis": d, "icd_code": c, "icd_name": nm})

    primary_diag = diag_list[0]["diagnosis"] if diag_list else None
    primary_icd  = diag_list[0]["icd_code"]  if diag_list else None

    notes_clean = notes.strip() if notes else ""
    if diag_list:
        notes_stored = _json.dumps(diag_list, ensure_ascii=False)
        if notes_clean:
            notes_stored = notes_stored + "\n" + notes_clean
    else:
        notes_stored = notes_clean or None

    # Validate the linked clinical event belongs to this patient
    if clinical_event_id:
        ce = db.query(ClinicalEvent).filter(
            ClinicalEvent.id == clinical_event_id,
            ClinicalEvent.patient_id == patient_id,
        ).first()
        ev.clinical_event_id = ce.id if ce else None
    else:
        ev.clinical_event_id = None

    icu_checked = bool(icu_admission == "1" or icu_admission == "on" or icu_admission is True)
    ev.admission_date     = adm
    ev.discharge_date     = dis
    ev.los_days           = los
    ev.primary_diagnosis  = primary_diag or None
    ev.primary_icd        = primary_icd or None
    ev.notes              = notes_stored or None
    ev.severity           = severity or None
    ev.icu_admission      = icu_checked
    ev.pct                = pct
    ev.shock_on_admission = shock_on_admission or 0
    ev.inotrope_days      = inotrope_days
    ev.ventilation_days   = ventilation_days
    ev.transfusion_units  = transfusion_units

    from services.patient_service import sync_hospitalization_to_monthly_record
    sync_hospitalization_to_monthly_record(
        db=db, patient_id=patient_id, event_date=adm,
        diagnosis=primary_diag or "", icd_code=primary_icd or "", icd_diagnosis="",
        discharge_date=dis, los_days=los,
        severity=severity or None, icu_admission=icu_checked,
        pct=pct, shock_on_admission=shock_on_admission,
        inotrope_days=inotrope_days, ventilation_days=ventilation_days,
        transfusion_units=transfusion_units,
    )

    db.commit()
    return RedirectResponse(url=f"/patients/{patient_id}/hospitalisations", status_code=303)


@router.post("/{patient_id}/hospitalisations/{event_id}/delete")
async def delete_hospitalisation(
    patient_id: int,
    event_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user = get_user(request)
    role = (user.get("role") if isinstance(user, dict) else getattr(user, "role", "")) if user else ""
    if role not in ("admin", "doctor"):
        raise HTTPException(status_code=403)
    ev = db.query(HospitalisationEvent).filter(
        HospitalisationEvent.id == event_id,
        HospitalisationEvent.patient_id == patient_id,
    ).first()
    if not ev:
        raise HTTPException(status_code=404)
    db.delete(ev)
    db.commit()
    return RedirectResponse(url=f"/patients/{patient_id}/hospitalisations", status_code=303)


@router.post("/{patient_id}/clinical_background")
async def update_clinical_background(
    patient_id: int,
    request: Request,
    clinical_background: str = Form(""),
    db: Session = Depends(get_db),
):
    p = db.query(Patient).filter(Patient.id == patient_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    user = get_user(request)
    role = (user.get("role") if isinstance(user, dict) else getattr(user, "role", "")) if user else ""
    if role not in ("admin", "doctor"):
        raise HTTPException(status_code=403, detail="Permission denied")
        
    p.clinical_background = clinical_background
    db.commit()
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=f"/patients/{patient_id}/profile", status_code=303)
