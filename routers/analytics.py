from fastapi import APIRouter, Depends, Request, HTTPException
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
    predict_mortality_risk,
)
from constants import EVENT_TYPES, EVENT_TYPE_GROUPS

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analytics"])

@router.get("/analytics/census", response_class=HTMLResponse)
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

@router.get("/analytics/vascular-access", response_class=HTMLResponse)
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

@router.get("/analytics/mortality-risk", response_class=HTMLResponse)
async def mortality_risk_list(request: Request, db: Session = Depends(get_db)):
    _require_analytics_access(request)
    patients = db.query(Patient).filter(Patient.is_active == True).order_by(Patient.name).all()

    rows = []
    for p in patients:
        records = (
            db.query(MonthlyRecord)
            .filter(MonthlyRecord.patient_id == p.id)
            .order_by(MonthlyRecord.record_month.desc())
            .limit(6)
            .all()
        )
        df = [
            {
                "month": r.record_month,
                "hb": r.hb, "albumin": r.albumin,
                "phosphorus": r.phosphorus, "idwg": r.idwg,
                "urr": r.urr, "serum_ferritin": r.serum_ferritin,
                "tsat": r.tsat, "ipth": r.ipth, "bp_sys": r.bp_sys,
                "epo_weekly_units": r.epo_weekly_units,
                "epo_mircera_dose": r.epo_mircera_dose,
                "wbc_count": r.wbc_count, "crp": r.crp,
                "hospitalization_this_month": r.hospitalization_this_month,
                "weight": r.target_dry_weight or p.dry_weight,
            }
            for r in records
        ]
        patient_info = {
            "age":        p.age,
            "cad_status": p.cad_status,
            "chf_status": p.chf_status,
            "dm_status":  p.dm_status,
            "ef":         p.ejection_fraction if p.ejection_fraction is not None else 60.0,
        }
        mort = predict_mortality_risk(df, patient_info) if df else {"available": False}
        rows.append({
            "patient":    p,
            "mort":       mort,
            "prob_1yr":   mort.get("prob_1yr", 0) if mort.get("available") else None,
            "risk_level": mort.get("risk_level", "Unknown"),
            "css_class":  mort.get("class", "secondary"),
            "confidence": mort.get("confidence", "—"),
            "latest_hb":  df[0].get("hb") if df else None,
            "latest_alb": df[0].get("albumin") if df else None,
            "n_months":   len(df),
        })

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


@router.get("/analytics", response_class=HTMLResponse)
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

@router.get("/analytics/patients", tags=["api"])
async def api_patients(q: str = "", db: Session = Depends(get_db)):
    patients = db.query(Patient).filter(Patient.is_active == True, Patient.name.ilike(f"%{q}%")).limit(20).all()
    return [{"id": p.id, "name": p.name, "hid": p.hid_no} for p in patients]

@router.get("/analytics/patients/{patient_id}", response_class=HTMLResponse)
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
    })

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
