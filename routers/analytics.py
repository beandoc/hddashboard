from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
from typing import Optional
import logging

from database import get_db, Patient, ClinicalEvent, SessionRecord
from config import templates
from dependencies import get_user
from dashboard_logic import compute_dashboard
from ml_analytics import run_patient_analytics, analyze_bfr_trend, run_cohort_analytics, get_at_risk_trends, analyze_pds
from constants import EVENT_TYPES, EVENT_TYPE_GROUPS

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analytics"])

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
    
    return templates.TemplateResponse("patient_analytics.html", {
        "request": request, "patient": patient, "analytics": analytics,
        "pt_events": pt_events, "event_types": EVENT_TYPES, "event_type_groups": EVENT_TYPE_GROUPS,
        "bfr_analytics": bfr_analytics, "recent_sessions": recent_sessions,
        "pds_analytics": pds_analytics,
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
