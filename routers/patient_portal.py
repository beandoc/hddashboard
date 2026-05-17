from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import date, datetime, timedelta
from typing import List
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
    
    # Trends for chart (template expects dict with separate label/value arrays)
    trends = {"labels": [], "hb": [], "alb": [], "phos": []}
    if latest_monthly:
        monthly_records = db.query(MonthlyRecord).filter(MonthlyRecord.patient_id == p.id).order_by(MonthlyRecord.record_month.desc()).limit(6).all()
        for r in reversed(monthly_records):
            trends["labels"].append(get_month_label(r.record_month))
            trends["hb"].append(r.hb)
            trends["alb"].append(r.albumin)
            trends["phos"].append(r.phosphorus)

    # Vaccination status
    vax_reminders = []
    today = date.today()
    if p.hep_b_status not in ("Completed", "Immune"):
        vax_reminders.append("Hepatitis B Vaccination incomplete — please check with your nurse")
    if not p.pcv13_date:
        vax_reminders.append("Primary Pneumococcal (PCV13) Vaccine due")
    elif not p.ppsv23_date and (today - p.pcv13_date).days > 60:
        vax_reminders.append("Pneumococcal (PPSV23) Vaccine due")

    # Next session day
    day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    session_days = [(getattr(p, f"hd_day_{i}"), getattr(p, f"hd_slot_{i}")) for i in (1, 2, 3) if getattr(p, f"hd_day_{i}")]
    next_session = None
    if session_days:
        today_dow = today.weekday()  # 0=Monday
        best = None
        for day_name, slot in session_days:
            try:
                target_dow = day_order.index(day_name)
                delta = (target_dow - today_dow) % 7 or 7
                if best is None or delta < best[0]:
                    best = (delta, day_name, slot)
            except ValueError:
                pass
        if best:
            next_date = today + timedelta(days=best[0])
            next_session = {"date": next_date, "day": best[1], "slot": best[2]}

    # Nutrition Tracker — fetch 14 days so rolling averages have enough history
    fourteen_days_ago = today - timedelta(days=13)
    meal_records = (
        db.query(PatientMealRecord)
        .filter(PatientMealRecord.patient_id == p.id, PatientMealRecord.date >= fourteen_days_ago)
        .order_by(PatientMealRecord.date.desc())
        .all()
    )

    meals_by_day = {}
    for m in meal_records:
        d_str = m.date.strftime("%Y-%m-%d")
        if d_str not in meals_by_day:
            meals_by_day[d_str] = {
                "date": m.date,
                "total_cal": 0, "total_prot": 0, "total_phos": 0,
                "total_pot": 0, "total_calc": 0,
                "entries": [],
            }
        meals_by_day[d_str]["total_cal"]  += (m.calories   or 0)
        meals_by_day[d_str]["total_prot"] += (m.protein    or 0)
        meals_by_day[d_str]["total_phos"] += (m.phosphorus or 0)
        meals_by_day[d_str]["total_pot"]  += (m.potassium  or 0)
        meals_by_day[d_str]["total_calc"] += (m.calcium    or 0)
        meals_by_day[d_str]["entries"].append(m)

    weight_kg = p.dry_weight or 60
    nutrition_targets = {
        "calories":   round(weight_kg * 30),
        "protein":    round(weight_kg * 1.2, 1),
        "phosphorus": 900,
        "potassium":  2000,
        "calcium":    1000,
    }

    today_str = today.strftime("%Y-%m-%d")
    today_stats = meals_by_day.get(today_str, {
        "total_cal": 0, "total_prot": 0, "total_phos": 0, "total_pot": 0, "total_calc": 0
    })

    def _rolling_avg(days: int):
        """Average per-day nutrient totals across the last `days` calendar days that have logged data."""
        data_days = []
        for i in range(days):
            d_str = (today - timedelta(days=i)).strftime("%Y-%m-%d")
            if d_str in meals_by_day:
                data_days.append(meals_by_day[d_str])
        n = len(data_days)
        if n == 0:
            return None
        return {
            "n": n, "of": days,
            "cal":  round(sum(d["total_cal"]  for d in data_days) / n),
            "prot": round(sum(d["total_prot"] for d in data_days) / n, 1),
            "phos": round(sum(d["total_phos"] for d in data_days) / n),
            "pot":  round(sum(d["total_pot"]  for d in data_days) / n),
            "calc": round(sum(d["total_calc"] for d in data_days) / n),
        }

    nutrition_avg = {
        "d1": _rolling_avg(1),
        "d3": _rolling_avg(3),
        "d7": _rolling_avg(7),
    }

    import json
    anti_meds = []
    if latest_monthly and latest_monthly.antihypertensive_details:
        try: anti_meds = json.loads(latest_monthly.antihypertensive_details)
        except: pass

    last_session = db.query(SessionRecord).filter(SessionRecord.patient_id == p.id).order_by(SessionRecord.session_date.desc()).first()

    # Calculate IDWG: prefer live session data (pre-HD weight − dry weight);
    # fall back to the monthly record IDWG field when no sessions have been logged yet.
    idwg = None
    if last_session and last_session.weight_pre is not None and p.dry_weight is not None:
        idwg = round(last_session.weight_pre - p.dry_weight, 2)
    elif latest_monthly and latest_monthly.idwg is not None:
        idwg = latest_monthly.idwg  # monthly aggregate / last-known value

    # Effective dry weight: prefer monthly target, fall back to patient baseline
    effective_dry_weight = (
        (latest_monthly.target_dry_weight if latest_monthly and latest_monthly.target_dry_weight else None)
        or p.dry_weight
        or 60
    )

    # Fluid allowance = 500 mL base + residual urine output (mL/day)
    ruo = latest_monthly.residual_urine_output if (latest_monthly and latest_monthly.residual_urine_output) else 0
    fluid_allowance_ml = 500 + int(ruo)

    # Resolve ESA label for medication display — handles both structured esa_type
    # and legacy free-text epo_mircera_dose strings (e.g. "MIRCERA 75")
    epo_label = None
    if latest_monthly:
        if latest_monthly.esa_type:
            epo_label = latest_monthly.esa_type
        elif latest_monthly.epo_mircera_dose:
            # Normalise common variants → human-readable name
            raw = (latest_monthly.epo_mircera_dose or "").upper()
            if "MIRCERA" in raw:
                epo_label = "Mircera (CERA)"
            elif "DESIDUSTAT" in raw or "OXEMIA" in raw:
                epo_label = "Desidustat (Oxemia)"
            elif "DARBEPOETIN" in raw or "ARANESP" in raw:
                epo_label = "Darbepoetin Alfa"
            elif "EPO" in raw or "ERYTHROPOETIN" in raw or "ERYPEG" in raw:
                epo_label = "Epoetin Alfa"
            else:
                epo_label = latest_monthly.epo_mircera_dose

    recent_symptoms = db.query(PatientSymptomReport).filter(PatientSymptomReport.patient_id == p.id).order_by(PatientSymptomReport.reported_at.desc()).limit(5).all()

    return templates.TemplateResponse("patient_view.html", {
        "request": request,
        "patient": p,
        "latest_monthly": latest_monthly,
        "anti_meds": anti_meds,
        "meals_by_day": meals_by_day,
        "today_stats": today_stats,
        "nutrition_targets": nutrition_targets,
        "nutrition_avg": nutrition_avg,
        "trends": trends,
        "vax_reminders": vax_reminders,
        "last_session": last_session,
        "idwg": idwg,
        "fluid_allowance_ml": fluid_allowance_ml,
        "effective_dry_weight": effective_dry_weight,
        "epo_label": epo_label,
        "recent_symptoms": recent_symptoms,
        "user": u,
        "next_session": next_session,
        "today": today,
        "today_iso": today.isoformat(),
        "min_log_date": (today - timedelta(days=13)).isoformat(),
    })

@router.post("/meals")
async def log_meal(
    request: Request,
    log_date: str = Form(None),
    calories: float = Form(None),
    protein: float = Form(None),
    phosphorus: float = Form(None),
    potassium: float = Form(None),
    calcium: float = Form(None),
    meal_type: str = Form("Breakfast"),
    notes: str = Form(""),
    db: Session = Depends(get_db)
):
    u = get_user(request)
    if not u or not isinstance(u, dict) or u.get("role") != "patient":
        raise HTTPException(status_code=403)

    try:
        record_date = date.fromisoformat(log_date) if log_date else datetime.utcnow().date()
        # Clamp to last 13 days — no future dates, no very stale history
        today = date.today()
        record_date = max(today - timedelta(days=13), min(record_date, today))
    except ValueError:
        record_date = datetime.utcnow().date()

    from services.nutrition_service import estimate_meal_nutrients
    est_cal, est_prot, est_phos, est_pot, est_calc = estimate_meal_nutrients(notes, meal_type, db)

    final_cal  = calories   if (calories   is not None and calories   > 0) else est_cal
    final_prot = protein    if (protein    is not None and protein    > 0) else est_prot
    final_phos = phosphorus if (phosphorus is not None and phosphorus > 0) else est_phos
    final_pot  = potassium  if (potassium  is not None and potassium  > 0) else est_pot
    final_calc = calcium    if (calcium    is not None and calcium    > 0) else est_calc

    meal = PatientMealRecord(
        patient_id=u["id"],
        date=record_date,
        calories=final_cal,
        protein=final_prot,
        phosphorus=final_phos,
        potassium=final_pot,
        calcium=final_calc,
        meal_type=meal_type,
        notes=notes,
    )
    db.add(meal)
    db.commit()
    return RedirectResponse(url="/patient/dashboard", status_code=303)

@router.post("/symptoms")
async def log_symptoms(
    request: Request,
    db: Session = Depends(get_db),
    # Legacy fields
    symptoms: str = Form(""),
    severity: str = Form("3"),
    notes: str = Form(""),
    # PDS Specific fields
    dialysis_recovery_time_mins: str = Form(None),
    tiredness_score: str = Form(None),
    energy_level_score: str = Form(None),
    daily_activity_impact: str = Form(None),
    cognitive_alertness: str = Form(None),
    post_hd_mood: str = Form(None),
    sleepiness_severity: str = Form(None),
    missed_social_or_work_event: str = Form(None)
):
    u = get_user(request)
    if not u or not isinstance(u, dict) or u.get("role") != "patient":
        raise HTTPException(status_code=403)

    # Safe type-conversion helper utilities
    def parse_int(val, default=None):
        if val is None:
            return default
        val_str = str(val).strip()
        if not val_str or val_str.lower() in ("none", "null", ""):
            return default
        try:
            return int(val_str)
        except ValueError:
            return default

    def parse_str(val):
        if val is None:
            return None
        val_str = str(val).strip()
        if not val_str or val_str.lower() in ("none", "null", ""):
            return None
        return val_str

    def parse_bool(val):
        if val is None:
            return False
        val_str = str(val).strip().lower()
        return val_str in ("true", "1", "yes", "on", "checked")

    # Apply safe conversions
    conv_severity = parse_int(severity, 3)
    conv_recovery = parse_int(dialysis_recovery_time_mins)
    conv_tiredness = parse_int(tiredness_score)
    conv_energy = parse_int(energy_level_score)
    conv_activity = parse_int(daily_activity_impact)
    conv_sleepiness = parse_int(sleepiness_severity)
    
    conv_alertness = parse_str(cognitive_alertness)
    conv_mood = parse_str(post_hd_mood)
    conv_notes = parse_str(notes)
    
    conv_missed = parse_bool(missed_social_or_work_event)
        
    report = PatientSymptomReport(
        patient_id=u["id"],
        symptoms=symptoms,
        severity=conv_severity,
        notes=conv_notes,
        dialysis_recovery_time_mins=conv_recovery,
        tiredness_score=conv_tiredness,
        energy_level_score=conv_energy,
        daily_activity_impact=conv_activity,
        cognitive_alertness=conv_alertness,
        post_hd_mood=conv_mood,
        sleepiness_severity=conv_sleepiness,
        missed_social_or_work_event=conv_missed
    )
    db.add(report)
    db.commit()
    return RedirectResponse(url="/patient/dashboard", status_code=303)


@router.get("/api/foods/search")
async def search_foods(q: str = "", diet: str = "all", db: Session = Depends(get_db)):
    if not q or len(q.strip()) < 2:
        return []
        
    from database import FoodDatabaseItem
    query_str = q.strip().lower()
    
    # Fast case-insensitive keyword and synonym query (pull a larger batch to filter in Python)
    results = (
        db.query(FoodDatabaseItem)
        .filter(
            (FoodDatabaseItem.name.ilike(f"%{query_str}%")) |
            (FoodDatabaseItem.synonyms.ilike(f"%{query_str}%"))
        )
        .order_by(FoodDatabaseItem.name)
        .limit(120)
        .all()
    )
    
    # Dynamic clinical diet classification lists
    non_veg_keywords = [
        'chicken', 'fish', 'mutton', 'pork', 'turkey', 'shrimp', 'crab', 'lobster', 
        'salmon', 'tuna', 'sardine', 'cod', 'mackerel', 'oyster', 'prawn', 'lamb', 
        'ham', 'bacon', 'pepperoni', 'sausage', 'seafood', 'clam', 'anchov', 
        'herring', 'tilapia', 'halibut', 'squid', 'octopus', 'gelatin', 'duck', 'venison'
    ]
    egg_keywords = ['egg', 'eggs', 'omelet', 'omelette', 'meringue', 'eggnog']

    def get_diet_classification(name):
        name_lower = name.lower()
        
        # 1. Check Non-Veg
        if any(kw in name_lower for kw in non_veg_keywords):
            return "nonveg"
            
        # 2. Check Egg (with smart eggplant/eggfruit bypass)
        has_egg = False
        for kw in egg_keywords:
            if kw in name_lower:
                if "eggplant" in name_lower or "egg-plant" in name_lower or "egg fruit" in name_lower:
                    continue
                has_egg = True
                break
                
        if has_egg:
            return "egg"
            
        return "veg"

    # Filter suggestions based on patient selection
    filtered = []
    for item in results:
        classification = get_diet_classification(item.name)
        if diet == "veg":
            if classification != "veg":
                continue
        elif diet == "egg":
            if classification not in ("veg", "egg"):
                continue
        # For diet == "all" / "nonveg", include all
        filtered.append(item)
        if len(filtered) >= 12:
            break
            
    return [
        {
            "id": item.id,
            "name": item.name,
            "serving_size": item.serving_size or "",
            "serving_sizes": item.serving_sizes or "",
            "calories": round(item.calories, 1),
            "protein": round(item.protein, 1),
            "phosphorus": round(item.phosphorus, 1),
            "potassium": round(item.potassium or 0, 1),
            "calcium": round(item.calcium or 0, 1),
        }
        for item in filtered
    ]


class BulkMealItem(BaseModel):
    meal_type: str
    notes: str
    calories: float
    protein: float
    phosphorus: float
    potassium: float = 0.0
    calcium: float = 0.0
    log_date: str = ""  # ISO "YYYY-MM-DD"; empty string → today

@router.post("/meals/{record_id}/delete")
async def delete_meal(
    request: Request,
    record_id: int,
    db: Session = Depends(get_db)
):
    u = get_user(request)
    if not u or not isinstance(u, dict) or u.get("role") != "patient":
        raise HTTPException(status_code=403)
        
    meal = db.query(PatientMealRecord).filter(
        PatientMealRecord.id == record_id,
        PatientMealRecord.patient_id == u["id"]
    ).first()
    
    if not meal:
        raise HTTPException(status_code=404, detail="Meal record not found")
        
    db.delete(meal)
    db.commit()
    return RedirectResponse(url="/patient/dashboard", status_code=303)


@router.post("/meals/bulk")
async def log_meals_bulk(
    request: Request,
    meals: List[BulkMealItem],
    db: Session = Depends(get_db)
):
    u = get_user(request)
    if not u or not isinstance(u, dict) or u.get("role") != "patient":
        raise HTTPException(status_code=403)
        
    today = date.today()
    for m in meals:
        try:
            record_date = date.fromisoformat(m.log_date) if m.log_date else today
            record_date = max(today - timedelta(days=13), min(record_date, today))
        except ValueError:
            record_date = today

        record = PatientMealRecord(
            patient_id=u["id"],
            date=record_date,
            calories=m.calories,
            protein=m.protein,
            phosphorus=m.phosphorus,
            potassium=m.potassium,
            calcium=m.calcium,
            meal_type=m.meal_type,
            notes=m.notes,
        )
        db.add(record)
    db.commit()
    return {"status": "success", "count": len(meals)}

