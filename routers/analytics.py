from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
from typing import Optional
import logging

from datetime import date, datetime, timedelta
from database import get_db, Patient, ClinicalEvent, SessionRecord, MonthlyRecord
from config import templates
from dependencies import get_user
from dashboard_logic import compute_dashboard, get_current_month_str
from ml_analytics import run_patient_analytics, analyze_bfr_trend, run_cohort_analytics, get_at_risk_trends, analyze_pds, analyze_mia_cascade, analyze_cardiorenal_cascade, analyze_avf_maturation
from constants import EVENT_TYPES, EVENT_TYPE_GROUPS

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analytics"])

@router.get("/analytics/census", response_class=HTMLResponse)
async def census_report(request: Request, month: Optional[str] = None, db: Session = Depends(get_db)):
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

@router.get("/analytics", response_class=HTMLResponse)
async def analytics_hub(request: Request, db: Session = Depends(get_db)):
    # Fetch some "at risk" patients for the summary table
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
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient: raise HTTPException(status_code=404)
    analytics = run_patient_analytics(db, patient_id)
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
    month_str = month or get_current_month_str()
    try:
        data = compute_dashboard(db, month_str)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return JSONResponse(content=data)

@router.get("/api/cohort-trends")
async def api_cohort_trends(db: Session = Depends(get_db)):
    try:
        data = run_cohort_analytics(db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return JSONResponse(content=data)

@router.get("/api/at-risk-trends")
async def api_at_risk_trends(parameter: str, month: Optional[str] = None, db: Session = Depends(get_db)):
    try:
        data = get_at_risk_trends(db, parameter, month)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return JSONResponse(content=data)
