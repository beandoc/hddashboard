from fastapi import APIRouter, Depends, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
from typing import Optional
import logging

from datetime import date, datetime, timedelta
from database import get_db, Patient, ClinicalEvent, SessionRecord, MonthlyRecord
from config import templates
from dependencies import get_user, _require_analytics_access
from dashboard_logic import compute_dashboard, get_current_month_str
from ml_analytics import (
    run_patient_analytics, analyze_bfr_trend, run_cohort_analytics,
    get_at_risk_trends, analyze_pds, analyze_mia_cascade,
    analyze_cardiorenal_cascade, analyze_avf_maturation, detect_occult_overload,
    train_deterioration_model, get_deterioration_model_status,
    predict_mortality_risk, get_all_patients_mortality_risk,
)
from constants import EVENT_TYPES, EVENT_TYPE_GROUPS
from krcrw_model import estimate_krcrw
from phosphate_model import estimate_phosphate_kinetics, calculate_pbe

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["analytics"])
root_router = APIRouter(tags=["clinical-review"])

@router.get("/census", response_class=HTMLResponse)
async def census_report(request: Request, month: Optional[str] = None, db: Session = Depends(get_db)):
    _require_analytics_access(request)
    month_str = month or get_current_month_str()
    
    # 1. Monthly Totals
    patients = db.query(Patient).all()
    active_patients = [p for p in patients if p.is_active]
    
    # 2. New Registrations this month
    new_regs = [p for p in patients if p.created_at and p.created_at.strftime("%Y-%m") == month_str]
    
    # 3. Deaths this month
    deaths = [p for p in patients if p.current_survival_status == "Deceased" and p.date_of_death and p.date_of_death.strftime("%Y-%m") == month_str]
    
    # 4. Transfers this month
    transfers = [p for p in patients if p.current_survival_status == "Transferred" and p.date_facility_transfer and p.date_facility_transfer.strftime("%Y-%m") == month_str]
    
    # 5. Hospitalizations this month
    monthly_recs = db.query(MonthlyRecord).filter(MonthlyRecord.record_month == month_str).all()
    hosp_count = sum(1 for r in monthly_recs if r.hospitalization_diagnosis or r.hospitalization_icd_diagnosis)
    
    # 6. Admission Rate (Hosp per 100 patient months)
    hosp_rate = (hosp_count / len(active_patients) * 100) if active_patients else 0

    return templates.TemplateResponse("census_report.html", {
        "request": request,
        "month_str": month_str,
        "metrics": {
            "total_active": len(active_patients),
            "new_registrations": len(new_regs),
            "deaths": len(deaths),
            "transfers": len(transfers),
            "hospitalizations": hosp_count,
            "hosp_rate": round(hosp_rate, 1)
        },
        "new_patients": new_regs,
        "deceased_patients": deaths,
        "transferred_patients": transfers,
        "user": get_user(request)
    })

@router.get("/vascular-access", response_class=HTMLResponse)
async def vascular_access_quality(request: Request, month: Optional[str] = None, db: Session = Depends(get_db)):
    _require_analytics_access(request)
    from datetime import datetime
    from ml_analytics import analyze_avf_maturation
    month_str = month or get_current_month_str()
    
    patients = db.query(Patient).filter(Patient.is_active == True).all()
    total_prevalent = len(patients)
    
    # 1. Prevalent AVF Rate (All active patients)
    prevalent_avf = [p for p in patients if p.access_type and "AVF" in p.access_type.upper()]
    prevalent_rate = (len(prevalent_avf) / total_prevalent * 100) if total_prevalent else 0
    
    # 2. Incident AVF Rate (Started this month)
    incident_patients = [p for p in patients if p.hd_wef_date and p.hd_wef_date.strftime("%Y-%m") == month_str]
    incident_avf = [p for p in incident_patients if p.access_type and "AVF" in p.access_type.upper()]
    incident_rate = (len(incident_avf) / len(incident_patients) * 100) if incident_patients else 0
    
    # 3. Watchlists & Intelligence
    maturation_watchlist = []
    functional_watchlist = []
    conversion_watchlist = []
    
    today = datetime.now().date()
    
    for p in patients:
        # a) Late Conversion Watchlist (>90 days on HD with non-AVF access)
        if p.access_type and "AVF" not in p.access_type.upper():
            if p.hd_wef_date:
                days_on_hd = (today - p.hd_wef_date).days
                if days_on_hd > 90:
                    conversion_watchlist.append({
                        "patient": p,
                        "days": days_on_hd,
                        "vintage": p.hd_wef_date.strftime("%b %Y")
                    })
        
        # b) Intelligence Engine (Maturation & Functional)
        status = analyze_avf_maturation(db, p.id)
        if status.get("available"):
            if status.get("maturation_failure"):
                maturation_watchlist.append({
                    "patient": p,
                    "status": status
                })
            if status.get("suboptimal_flow") or status.get("high_recirculation"):
                functional_watchlist.append({
                    "patient": p,
                    "status": status
                })

    return templates.TemplateResponse("access_quality.html", {
        "request": request,
        "month_str": month_str,
        "metrics": {
            "prevalent_rate": round(prevalent_rate, 1),
            "incident_rate": round(incident_rate, 1),
            "watchlist_count": len(conversion_watchlist),
            "maturation_failure_count": len(maturation_watchlist),
            "functional_alert_count": len(functional_watchlist),
            "target_prevalent": 90.0,
            "target_incident": 65.0
        },
        "watchlist": conversion_watchlist,
        "maturation_watchlist": maturation_watchlist,
        "functional_watchlist": functional_watchlist,
        "user": get_user(request)
    })

@router.get("/mortality-risk", response_class=HTMLResponse)
async def mortality_risk_list(request: Request, db: Session = Depends(get_db)):
    _require_analytics_access(request)
    from ml_analytics import get_all_patients_mortality_risk
    rows = get_all_patients_mortality_risk(db)

    # Sort: no-data patients last, then descending by 1-yr probability
    rows.sort(key=lambda r: (r["prob_1yr"] is None, -(r["prob_1yr"] or 0)))

    high_risk   = [r for r in rows if r["risk_level"] in ("High", "Very High")]
    moderate    = [r for r in rows if r["risk_level"] == "Moderate"]
    low_risk    = [r for r in rows if r["risk_level"] == "Low"]
    no_data     = [r for r in rows if not r["mort"].get("available")]

    return templates.TemplateResponse("mortality_risk.html", {
        "request":   request,
        "rows":      rows,
        "high_risk": high_risk,
        "moderate":  moderate,
        "low_risk":  low_risk,
        "no_data":   no_data,
        "user":      get_user(request),
    })


@router.get("", response_class=HTMLResponse)
async def analytics_hub(request: Request, db: Session = Depends(get_db)):
    _require_analytics_access(request)
    from dashboard_logic import get_current_month_str
    from ml_analytics import run_cohort_analytics
    
    # We can reuse the dashboard data logic or fetch patients with alerts
    patients = db.query(Patient).filter(Patient.is_active == True).all()
    # Simple logic to find patients with alerts for the watchlist
    data = compute_dashboard(db, get_current_month_str())
    patient_rows = data.get("patient_rows", [])
    
    return templates.TemplateResponse("analytics_hub.html", {
        "request": request,
        "patients": patient_rows,
        "user": get_user(request)
    })

@root_router.get("/review", response_class=HTMLResponse)
@root_router.get("/review/", response_class=HTMLResponse)
async def clinical_review_queue(request: Request, db: Session = Depends(get_db)):
    _require_analytics_access(request)
    user = get_user(request)

    # 1. Fetch data from dashboard compute (handles Hb drop, Albumin < 2.5, Phos, IDWG)
    dash_data = compute_dashboard(db)
    # 2. Fetch mortality risks + Bayesian profiles (both computed in get_all_patients_mortality_risk)
    mort_data = get_all_patients_mortality_risk(db)
    mort_map = {r['patient'].id: r for r in mort_data}

    active_patients = db.query(Patient).filter(Patient.is_active == True).all()

    flagged = {}  # patient_id -> {patient, flags, priority}
    
    # Pre-fetch monthly records for weight trend analysis
    current_month = get_current_month_str()
    y, m = int(current_month[:4]), int(current_month[5:7])
    prev_month = f"{y-1}-12" if m == 1 else f"{y}-{m-1:02d}"
    
    curr_recs = {r.patient_id: r for r in db.query(MonthlyRecord).filter(MonthlyRecord.record_month == current_month).all()}
    prev_recs = {r.patient_id: r for r in db.query(MonthlyRecord).filter(MonthlyRecord.record_month == prev_month).all()}

    for p in active_patients:
        p_flags = []
        priority = 0
        m = mort_map.get(p.id)
        bay = (m or {}).get("bay_profile", {})
        bay_summary = bay.get("summary", {}) if bay.get("available") else {}

        # A. High Mortality Risk (P >= 0.40)
        if m and m.get('prob_1yr') and m['prob_1yr'] >= 0.40:
            p_flags.append("High Mortality Risk")
            priority += 3

        # B. Hb Drop (Current < 9 and dropped from previous)
        hb_trend = next((item for item in dash_data['metrics']['trend_hb'] if item['id'] == p.id), None)
        if hb_trend:
            p_flags.append("Hb Drop (<9)")
            priority += 2

        # C. Low Albumin
        alb_trend = next((item for item in dash_data['metrics']['trend_albumin'] if item['id'] == p.id), None)
        if alb_trend:
            p_flags.append("Low Albumin")
            priority += 2

        # D. High IDWG
        if p.name in dash_data['metrics']['idwg_high']['names']:
            p_flags.append("High IDWG (>2.5kg)")
            priority += 1

        # D2. Significant Dry Weight Change (±2.0 kg)
        curr_r = curr_recs.get(p.id)
        prev_r = prev_recs.get(p.id)
        if curr_r and prev_r and curr_r.target_dry_weight and prev_r.target_dry_weight:
            weight_diff = curr_r.target_dry_weight - prev_r.target_dry_weight
            if abs(weight_diff) >= 2.0:
                dir_str = "Reduction" if weight_diff < 0 else "Increase"
                p_flags.append(f"Dry Weight {dir_str} ({abs(weight_diff):.1f}kg)")
                priority += 3 if weight_diff < 0 else 2 # Drops are higher priority for malnutrition

        # E. Occult Overload
        occult = detect_occult_overload(db, p.id)
        if occult:
            p_flags.append("Occult Fluid Overload")
            priority += 4

        # F. Fluid Status Pending (No assessment in last 90 days)
        last_fs = db.query(ClinicalEvent).filter(
            ClinicalEvent.patient_id == p.id,
            ClinicalEvent.event_type == "Fluid Status Assessment"
        ).order_by(ClinicalEvent.event_date.desc()).first()
        if not last_fs or (datetime.now().date() - last_fs.event_date).days > 90:
            p_flags.append("Fluid Assessment Pending")
            priority += 1

        # G. Bayesian persistence flags — only added when Bayesian data is available
        #    and the flag is not already captured by the point-in-time checks above.
        if bay.get("available"):
            hb_bay  = bay.get("hb", {})
            alb_bay = bay.get("albumin", {})
            phos_bay = bay.get("phosphorus", {})

            # High Hb persistence: prob of being low for 3+ months >= 40%
            # Only add if Hb Drop flag not already present (avoid double-flag)
            if hb_bay.get("prob_persistent_3", 0) >= 0.40 and "Hb Drop (<9)" not in p_flags:
                pct = round(hb_bay["prob_persistent_3"] * 100)
                p_flags.append(f"P(Hb Low×3) {pct}%")
                priority += 2

            # High Albumin persistence: prob >= 35%
            if alb_bay.get("prob_persistent_3", 0) >= 0.35 and "Low Albumin" not in p_flags:
                pct = round(alb_bay["prob_persistent_3"] * 100)
                p_flags.append(f"P(Alb Low×3) {pct}%")
                priority += 2

            # High Phosphorus persistence: prob >= 45%
            if phos_bay.get("prob_persistent_3", 0) >= 0.45:
                pct = round(phos_bay["prob_persistent_3"] * 100)
                p_flags.append(f"P(Phos High×3) {pct}%")
                priority += 1

            # Elevated composite alert score — catch multi-parameter borderline patients
            # who pass each individual threshold but are flagged together
            if bay_summary.get("composite_alert_score", 0) >= 0.55 and not p_flags:
                p_flags.append("Composite Risk Elevated")
                priority += 2

        if p_flags:
            # Get last reviewed date (from ClinicalEvent "Clinical Review")
            last_review = db.query(ClinicalEvent).filter(
                ClinicalEvent.patient_id == p.id,
                ClinicalEvent.event_type == "Clinical Review"
            ).order_by(ClinicalEvent.event_date.desc()).first()

            flagged[p.id] = {
                "patient": p,
                "flags": p_flags,
                "priority": priority,
                "mort_prob": m['prob_1yr'] if m else 0,
                "last_review": last_review.event_date if last_review else None,
                "bay_profile": bay,
                "bay_signal": (m.get("mort", {}) or {}).get("bay_signal") if m else None,
            }

    # Sort by priority desc, then Bayesian composite desc, then mortality risk desc
    review_list = sorted(
        flagged.values(),
        key=lambda x: (
            -x['priority'],
            -(x.get('bay_profile', {}).get('summary', {}).get('composite_alert_score') or 0),
            -(x['mort_prob'] or 0),
            x['patient'].name,
        )
    )

    return templates.TemplateResponse("review_queue.html", {
        "request": request,
        "user": user,
        "review_list": review_list,
        "generated_at": datetime.now()
    })

@router.get("/patients", response_class=HTMLResponse)
async def analytics_patient_list(request: Request, db: Session = Depends(get_db), filter: str = None):
    _require_analytics_access(request)
    user = get_user(request)
    
    # Fetch active patients
    patients = db.query(Patient).filter(Patient.is_active == True).order_by(Patient.name).all()
    
    # Get latest labs and risk for each
    mort_data = get_all_patients_mortality_risk(db)
    mort_map = {r['patient'].id: r for r in mort_data}
    
    # Fetch latest monthly record for each patient to get current labs
    enriched_patients = []
    for p in patients:
        latest_rec = db.query(MonthlyRecord).filter(MonthlyRecord.patient_id == p.id).order_by(MonthlyRecord.record_month.desc()).first()
        m = mort_map.get(p.id)
        
        # Check if patient matches requested filter
        matches_filter = True
        if filter:
            matches_filter = False
            if filter == "epo_resistant":
                # Check for any HypoR level
                if latest_rec and (latest_rec.esa_hyporesponse_level or 0) > 0: matches_filter = True
            elif filter == "iv_iron":
                if m and any("Iron" in f for f in m.get('flags', [])): matches_filter = True
            elif filter == "idwg_high":
                if latest_rec and (latest_rec.idwg or 0) > 2.5: matches_filter = True
            elif filter == "albumin_low":
                if latest_rec and (latest_rec.albumin or 4) < 2.5: matches_filter = True
            elif filter == "calcium_low":
                if latest_rec and (latest_rec.calcium_corrected or 9) < 8.0: matches_filter = True
            elif filter == "phos_high":
                if latest_rec and (latest_rec.phosphorus or 0) > 5.5: matches_filter = True
        
        if matches_filter:
            enriched_patients.append({
                "id": p.id,
                "name": p.name,
                "hid_no": p.hid_no,
                "latest_hb": latest_rec.hb if latest_rec else None,
                "latest_alb": latest_rec.albumin if latest_rec else None,
                "latest_phos": latest_rec.phosphorus if latest_rec else None,
                "mortality_risk": m if m else None
            })
        
    return templates.TemplateResponse("analytics_patients.html", {
        "request": request,
        "user": user,
        "patients": enriched_patients,
        "active_filter": filter
    })

@router.get("/patients/{patient_id}", response_class=HTMLResponse)
async def patient_analytics_page(patient_id: int, request: Request, db: Session = Depends(get_db)):
    _require_analytics_access(request)
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient: raise HTTPException(status_code=404)
    try:
        analytics = run_patient_analytics(db, patient_id)
        occult_overload = detect_occult_overload(db, patient_id)
        if occult_overload:
            analytics["occult_alert"] = occult_overload
        pt_events = db.query(ClinicalEvent).filter(ClinicalEvent.patient_id == patient_id).order_by(ClinicalEvent.event_date.desc()).all()
        recent_sessions = db.query(SessionRecord).filter(SessionRecord.patient_id == patient_id).order_by(SessionRecord.session_date.desc()).limit(20).all()

        session_dicts = [
            {
                "session_date": str(s.session_date),
                "blood_flow_rate": s.blood_flow_rate,
                "actual_blood_flow_rate": s.actual_blood_flow_rate,
                "access_condition": s.access_condition,
                "arterial_line_pressure": s.arterial_line_pressure,
                "venous_line_pressure": s.venous_line_pressure,
            }
            for s in recent_sessions
        ]
        bfr_analytics = analyze_bfr_trend(session_dicts)
        pds_analytics = analyze_pds(db, patient_id)
        mia_cascade = analyze_mia_cascade(db, patient_id)
        cardiorenal_cascade = analyze_cardiorenal_cascade(db, patient_id)
        avf_cascade = analyze_avf_maturation(db, patient_id)
    except Exception as exc:
        logging.exception("patient_analytics_page error for patient_id=%s", patient_id)
        raise HTTPException(status_code=500, detail=str(exc))

    return templates.TemplateResponse("patient_analytics.html", {
        "request": request, "patient": patient, "analytics": analytics,
        "pt_events": pt_events, "event_types": EVENT_TYPES, "event_type_groups": EVENT_TYPE_GROUPS,
        "bfr_analytics": bfr_analytics, "recent_sessions": recent_sessions,
        "pds_analytics": pds_analytics,
        "mia_cascade": mia_cascade,
        "cardiorenal_cascade": cardiorenal_cascade,
        "avf_cascade": avf_cascade,
        "user": get_user(request),
        "doctor_note": db.query(MonthlyRecord).filter(
            MonthlyRecord.patient_id == patient_id,
            MonthlyRecord.record_month == get_current_month_str()
        ).first(),
        "current_month": get_current_month_str()
    })

@router.post("/patients/{patient_id}/note")
async def save_doctor_note(
    patient_id: int,
    note: str = Form(...),
    record_month: str = Form(...),
    db: Session = Depends(get_db),
    request: Request = None
):
    _require_analytics_access(request)
    user = get_user(request)
    
    record = db.query(MonthlyRecord).filter(
        MonthlyRecord.patient_id == patient_id,
        MonthlyRecord.record_month == record_month
    ).first()
    
    if not record:
        record = MonthlyRecord(
            patient_id=patient_id,
            record_month=record_month,
            entered_by=getattr(user, "username", "doctor")
        )
        db.add(record)
    
    record.doctor_notes = note
    record.reviewed_by = getattr(user, "full_name", getattr(user, "username", "Doctor"))
    record.reviewed_at = datetime.now()
    
    db.commit()
    return RedirectResponse(url=f"/analytics/patients/{patient_id}?success=note_saved", status_code=303)

@router.get("/api/dashboard")
async def api_dashboard(month: Optional[str] = None, db: Session = Depends(get_db)):
    from dashboard_logic import get_current_month_str
    from fastapi.encoders import jsonable_encoder
    month_str = month or get_current_month_str()
    try:
        data = compute_dashboard(db, month_str)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return JSONResponse(content=jsonable_encoder(data))

@router.get("/api/cohort-trends")
async def api_cohort_trends(db: Session = Depends(get_db)):
    from fastapi.encoders import jsonable_encoder
    try:
        data = run_cohort_analytics(db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return JSONResponse(content=jsonable_encoder(data))

@router.get("/api/at-risk-trends")
async def api_at_risk_trends(parameter: str, month: Optional[str] = None, db: Session = Depends(get_db)):
    from fastapi.encoders import jsonable_encoder
    try:
        data = get_at_risk_trends(db, parameter, month)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return JSONResponse(content=jsonable_encoder(data))


@router.post("/admin/train-deterioration-model")
async def admin_train_deterioration_model(db: Session = Depends(get_db)):
    """
    Train (or retrain) the logistic regression deterioration risk model against
    all current MonthlyRecord data.

    Requires scikit-learn.  Returns training metadata including cross-validated
    AUC, sample count, and event rate.  The model is persisted to
    deterioration_model.pkl and loaded automatically on the next patient page load.

    Typical runtime: < 2 seconds for cohorts up to 500 patients.
    """
    try:
        result = train_deterioration_model(db)
    except Exception as e:
        logger.exception("Deterioration model training failed")
        raise HTTPException(status_code=500, detail=str(e))
    if not result.get("success"):
        raise HTTPException(status_code=422, detail=result.get("error", "Training failed"))
    return JSONResponse(content=result)


@router.get("/admin/deterioration-model-status")
async def admin_deterioration_model_status():
    """
    Return metadata about the currently deployed deterioration model:
    training date, sample count, cross-validated AUC, feature list.
    Returns a 'not trained' sentinel if no model has been trained yet.
    """
    try:
        status = get_deterioration_model_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return JSONResponse(content=status)

@router.get("/krcrw", response_class=HTMLResponse)
async def krcrw_calculator(request: Request, db: Session = Depends(get_db)):
    _require_analytics_access(request)
    from database import Patient
    patients = db.query(Patient).filter(Patient.is_active == True).order_by(Patient.name).all()
    return templates.TemplateResponse("krcrw_calculator.html", {
        "request": request,
        "patients": patients,
        "user": get_user(request)
    })

@router.post("/api/krcrw")
async def api_krcrw(payload: dict):
    try:
        from krcrw_model import estimate_krcrw
        res = estimate_krcrw(
            sex=payload["sex"],
            age=payload["age"],
            weight=payload["weight"],
            g_creat_input=payload["g_creat"],
            lab_day=payload["lab_day"],
            schedule=payload["schedule"],
            pre_creat_measured=payload["pre_creat"],
            ivp2=payload["ivp2"],
            qb=payload["qb"],
            qd=payload["qd"],
            td=payload["td"],
            weekly_fluid_l=payload["weekly_fluid"],
            k_code=payload["k_code"],
            koa=payload["koa"],
            is_black=payload.get("is_black", False)
        )
        return res
    except Exception as e:
        logger.exception("KRCRw calculation failed")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/krcrw/set-baseline")
async def api_krcrw_set_baseline(request: Request, payload: dict, db: Session = Depends(get_db)):
    _require_analytics_access(request)
    patient_id = payload["patient_id"]
    from database import Patient
    p = db.query(Patient).filter(Patient.id == patient_id).first()
    if not p: raise HTTPException(status_code=404)
    
    p.baseline_gcr = payload["g_creat"]
    p.baseline_vdcr = payload["vdcr"] # This is the IVP2 value used
    db.commit()
    return {"ok": True}

@router.get("/phosphate-modeling", response_class=HTMLResponse)
async def phosphate_calculator(request: Request, db: Session = Depends(get_db)):
    _require_analytics_access(request)
    from database import Patient
    patients = db.query(Patient).filter(Patient.is_active == True).order_by(Patient.name).all()
    return templates.TemplateResponse("phosphate_calculator.html", {
        "request": request,
        "patients": patients,
        "user": get_user(request)
    })

@router.post("/api/phosphate/calculate")
async def api_phosphate_calculate(payload: dict):
    try:
        res = estimate_phosphate_kinetics(
            sex=payload["sex"],
            weight=payload["weight"],
            v_urea=payload["v_urea"],
            koa_urea=payload["koa_urea"],
            qb=payload["qb"],
            qd=payload["qd"],
            td=payload["td"],
            schedule=payload["schedule"],
            p_pre_measured=payload["p_pre"],
            p_intake_mg_day=payload["p_intake"],
            p_binder_pbe=payload["p_binder"],
            krp_ml_min=payload["krp"],
            solve_for=payload.get("solve_for", "p_pre"),
            koa_p_ratio=payload.get("koa_ratio", 0.5),
            hdf_pre=payload.get("hdf_pre", 0.0),
            hdf_post=payload.get("hdf_post", 0.0)
        )
        return res
    except Exception as e:
        logger.exception("Phosphate calculation failed")
        raise HTTPException(status_code=500, detail=str(e))
