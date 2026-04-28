from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from datetime import date, datetime, timedelta
import logging

from database import get_db, Patient, MonthlyRecord, SessionRecord, PatientMealRecord, PatientSymptomReport
from config import templates
from dependencies import get_user
from dashboard_logic import get_month_label

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/patient", tags=["patient_portal"])

@router.get("/dashboard", response_class=HTMLResponse)
async def patient_dashboard(request: Request, db: Session = Depends(get_db)):
    u = get_user(request)
    if not u or not isinstance(u, dict) or u.get("role") != "patient":
        return RedirectResponse(url="/login")
    
    p = db.query(Patient).filter(Patient.id == u["id"]).first()
    if not p: return RedirectResponse(url="/login")

    latest_monthly = db.query(MonthlyRecord).filter(MonthlyRecord.patient_id == p.id).order_by(MonthlyRecord.record_month.desc()).first()
    
    # Simple trends for patient
    trends = []
    if latest_monthly:
        monthly_records = db.query(MonthlyRecord).filter(MonthlyRecord.patient_id == p.id).order_by(MonthlyRecord.record_month.desc()).limit(6).all()
        for r in reversed(monthly_records):
            trends.append({"month": get_month_label(r.record_month), "hb": r.hb, "albumin": r.albumin})

    # Vaccination status
    vax_reminders = []
    today = date.today()
    if p.hep_b_status != "Completed": vax_reminders.append("Hepatitis B Vaccination")
    if not p.pcv13_date or (today - p.pcv13_date).days > 365: vax_reminders.append("Pneumococcal (PCV13) Booster")

    # Nutrition Tracker
    seven_days_ago = today - timedelta(days=7)
    meal_records = db.query(PatientMealRecord).filter(PatientMealRecord.patient_id == p.id, PatientMealRecord.date >= seven_days_ago).order_by(PatientMealRecord.date.desc()).all()
    
    meals_by_day = {}
    for m in meal_records:
        d_str = m.date.strftime("%Y-%m-%d")
        if d_str not in meals_by_day:
            meals_by_day[d_str] = {"date": m.date, "total_cal": 0, "total_prot": 0, "entries": []}
        meals_by_day[d_str]["total_cal"] += (m.calories or 0)
        meals_by_day[d_str]["total_prot"] += (m.protein or 0)
        meals_by_day[d_str]["entries"].append(m)

    nutrition_targets = {
        "calories": round((p.dry_weight or 60) * 30),
        "protein": round((p.dry_weight or 60) * 1.2, 1)
    }

    today_str = today.strftime("%Y-%m-%d")
    today_stats = meals_by_day.get(today_str, {"total_cal": 0, "total_prot": 0})

    import json
    anti_meds = []
    if latest_monthly and latest_monthly.antihypertensive_details:
        try: anti_meds = json.loads(latest_monthly.antihypertensive_details)
        except: pass

    last_session = db.query(SessionRecord).filter(SessionRecord.patient_id == p.id).order_by(SessionRecord.session_date.desc()).first()
    idwg = None
    if last_session and last_session.weight_pre is not None and p.dry_weight is not None:
        idwg = round(last_session.weight_pre - p.dry_weight, 2)

    ruo = latest_monthly.residual_urine_output if (latest_monthly and latest_monthly.residual_urine_output) else 0
    fluid_allowance_ml = 500 + int(ruo)

    recent_symptoms = db.query(PatientSymptomReport).filter(PatientSymptomReport.patient_id == p.id).order_by(PatientSymptomReport.reported_at.desc()).limit(5).all()

    return templates.TemplateResponse("patient_view.html", {
        "request": request, "patient": p, "latest_monthly": latest_monthly, "anti_meds": anti_meds,
        "meals_by_day": meals_by_day, "today_stats": today_stats, "nutrition_targets": nutrition_targets,
        "trends": trends, "vax_reminders": vax_reminders, "last_session": last_session, "idwg": idwg,
        "fluid_allowance_ml": fluid_allowance_ml, "recent_symptoms": recent_symptoms, "user": u
    })

@router.post("/meals")
async def log_meal(request: Request, calories: float = Form(...), protein: float = Form(...), meal_type: str = Form("Breakfast"), notes: str = Form(""), db: Session = Depends(get_db)):
    u = get_user(request)
    if not u or not isinstance(u, dict) or u.get("role") != "patient": raise HTTPException(status_code=403)
    meal = PatientMealRecord(patient_id=u["id"], date=datetime.utcnow().date(), calories=calories, protein=protein, meal_type=meal_type, notes=notes)
    db.add(meal)
    db.commit()
    return RedirectResponse(url="/patient/dashboard", status_code=303)

@router.post("/symptoms")
async def log_symptoms(
    request: Request,
    db: Session = Depends(get_db),
    # Legacy fields
    symptoms: str = Form(""),
    severity: int = Form(3),
    notes: str = Form(""),
    # PDS Specific fields
    dialysis_recovery_time_mins: int = Form(None),
    tiredness_score: int = Form(None),
    energy_level_score: int = Form(None),
    daily_activity_impact: int = Form(None),
    cognitive_alertness: str = Form(None),
    post_hd_mood: str = Form(None),
    sleepiness_severity: int = Form(None),
    missed_social_or_work_event: bool = Form(False)
):
    u = get_user(request)
    if not u or not isinstance(u, dict) or u.get("role") != "patient":
        raise HTTPException(status_code=403)
        
    report = PatientSymptomReport(
        patient_id=u["id"],
        symptoms=symptoms,
        severity=severity,
        notes=notes,
        dialysis_recovery_time_mins=dialysis_recovery_time_mins,
        tiredness_score=tiredness_score,
        energy_level_score=energy_level_score,
        daily_activity_impact=daily_activity_impact,
        cognitive_alertness=cognitive_alertness,
        post_hd_mood=post_hd_mood,
        sleepiness_severity=sleepiness_severity,
        missed_social_or_work_event=missed_social_or_work_event
    )
    db.add(report)
    db.commit()
    return RedirectResponse(url="/patient/dashboard", status_code=303)
