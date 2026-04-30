from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date, datetime
import logging

from database import get_db, Patient, DryWeightAssessment, MonthlyRecord, SessionRecord
from config import templates
from dependencies import get_user

router = APIRouter(prefix="/patients/{patient_id}/fluid-status", tags=["fluid-status"])

@router.get("", response_class=HTMLResponse)
async def fluid_status_dashboard(patient_id: int, request: Request, db: Session = Depends(get_db)):
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient: raise HTTPException(status_code=404)
    
    assessments = db.query(DryWeightAssessment).filter(DryWeightAssessment.patient_id == patient_id).order_by(DryWeightAssessment.assessment_date.desc()).all()
    
    # Calculate Fluid Overload Risk Score (Concept)
    latest_record = db.query(MonthlyRecord).filter(MonthlyRecord.patient_id == patient_id).order_by(MonthlyRecord.record_month.desc()).first()
    latest_sessions = db.query(SessionRecord).filter(SessionRecord.patient_id == patient_id).order_by(SessionRecord.session_date.desc()).limit(10).all()
    
    risk_score = 0
    risk_factors = []
    
    if latest_record and latest_record.nt_probnp and latest_record.nt_probnp > 1000:
        risk_score += 2
        risk_factors.append("High NT-proBNP (>1000 pg/mL)")
        
    avg_idwg = sum([s.weight_pre - s.weight_post for s in latest_sessions if s.weight_pre and s.weight_post]) / len(latest_sessions) if latest_sessions else 0
    if avg_idwg > 2.5:
        risk_score += 2
        risk_factors.append(f"High IDWG (Avg {round(avg_idwg,1)} kg)")
        
    idh_episodes = [s for s in latest_sessions if s.idh_episode]
    if len(idh_episodes) > 2:
        risk_score += 2
        risk_factors.append(f"Frequent IDH ({len(idh_episodes)} episodes in last 10 sessions)")

    if patient.ejection_fraction and patient.ejection_fraction < 40:
        risk_score += 1
        risk_factors.append(f"Low EF ({patient.ejection_fraction}%)")

    # Latest Assessment Data
    latest_assess = assessments[0] if assessments else None
    if latest_assess:
        if latest_assess.ivc_diameter_max and latest_assess.ivc_diameter_max > 21:
            risk_score += 2
            risk_factors.append(f"High IVC Diameter ({latest_assess.ivc_diameter_max} mm)")

    return templates.TemplateResponse("fluid_status.html", {
        "request": request,
        "patient": patient,
        "assessments": assessments,
        "risk_score": risk_score,
        "risk_factors": risk_factors,
        "user": get_user(request),
        "today": date.today().isoformat(),
    })

@router.post("/save")
async def save_assessment(
    patient_id: int,
    request: Request,
    assess_date: date = Form(...),
    ivc_max: Optional[float] = Form(None),
    ivc_ci: Optional[float] = Form(None),
    bia_fo: Optional[float] = Form(None),
    bia_oh: Optional[float] = Form(None),
    bia_tbw: Optional[float] = Form(None),
    bia_pa: Optional[float] = Form(None),
    nt_probnp: Optional[float] = Form(None),
    edema: str = Form("None"),
    lability: str = Form("Stable"),
    rec_dw: Optional[float] = Form(None),
    notes: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    user = get_user(request)
    assess = DryWeightAssessment(
        patient_id=patient_id,
        assessment_date=assess_date,
        ivc_diameter_max=ivc_max,
        ivc_collapsibility_index=ivc_ci,
        bia_fluid_overload_litres=bia_fo,
        bia_overhydration_percent=bia_oh,
        bia_total_body_water=bia_tbw,
        bia_phase_angle=bia_pa,
        nt_probnp=nt_probnp,
        edema_status=edema,
        bp_lability=lability,
        recommended_dry_weight=rec_dw,
        assessment_notes=notes,
        performed_by=user.username if user else "System"
    )
    db.add(assess)
    
    # If a recommended dry weight is provided, update the patient's baseline
    if rec_dw:
        patient = db.query(Patient).filter(Patient.id == patient_id).first()
        if patient:
            patient.dry_weight = rec_dw
            
    db.commit()
    return RedirectResponse(url=f"/patients/{patient_id}/fluid-status", status_code=303)
