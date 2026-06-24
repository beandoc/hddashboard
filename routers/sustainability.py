from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime

from database import get_db, SustainabilityRecord, MonthlyRecord, Patient
from config import templates
from dependencies import get_user
from dashboard_logic import get_current_month_str, get_month_label

router = APIRouter(prefix="/analytics/sustainability", tags=["sustainability"])

# ICHD India Factors — aligned with frontend (LCI-validated, Barraclough 2025 + CEA v19)
CO2E_ELECTRICITY = 0.71   # kg/kWh — CEA CO2 Baseline Database v19 (Dec 2023), national average
CO2E_WATER = 0.30         # kg/m3 — CPHEEO norms for Indian municipal WTPs
CO2E_BIO_WASTE = 1.85     # kg/kg — IPCC clinical waste lifecycle (aligned with frontend)
CO2E_GEN_WASTE = 0.44     # kg/kg
CO2E_CONS_PER_SESSION = 7.5  # kg/session — LCI-validated (Tables S5-S6, Barraclough AJKD 2025)
CO2E_TRANS_PER_SESSION = 5.0 # kg/session (Avg patient commute in India)

@router.get("", response_class=HTMLResponse)
async def sustainability_dashboard(request: Request, month: Optional[str] = None, db: Session = Depends(get_db)):
    month_str = month or get_current_month_str()
    record = db.query(SustainabilityRecord).filter(SustainabilityRecord.record_month == month_str).first()
    
    # Get total sessions for the month from MonthlyRecords
    # Note: In a production app, we'd count actual SessionRecords, but we'll approximate 
    # based on patients * frequency or just total active count * 12.
    patient_count = db.query(MonthlyRecord).filter(MonthlyRecord.record_month == month_str).count()
    session_count = (record.total_sessions_override if record and record.total_sessions_override else (patient_count * 12)) or 1
    
    analysis = None
    if record:
        e = record.electricity_kwh * CO2E_ELECTRICITY
        w = record.water_m3 * CO2E_WATER
        wt = (record.biomedical_waste_kg * CO2E_BIO_WASTE) + (record.general_waste_kg * CO2E_GEN_WASTE)
        c = session_count * CO2E_CONS_PER_SESSION
        t = session_count * CO2E_TRANS_PER_SESSION
        total = e + w + wt + c + t
        
        analysis = {
            "total": round(total, 1),
            "per_session": round(total / session_count, 1),
            "breakdown": [
                {"label": "Energy (Electricity)", "val": round(e, 1), "color": "#f59e0b"},
                {"label": "Water (Purification)", "val": round(w, 1), "color": "#0ea5e9"},
                {"label": "Waste Management", "val": round(wt, 1), "color": "#ef4444"},
                {"label": "Medical Consumables", "val": round(c, 1), "color": "#8b5cf6"},
                {"label": "Patient Transport", "val": round(t, 1), "color": "#10b981"}
            ]
        }

    active_count = db.query(Patient).filter(Patient.is_active == True).count()

    return templates.TemplateResponse("sustainability.html", {
        "request": request,
        "month_str": month_str,
        "month_label": get_month_label(month_str),
        "record": record,
        "session_count": session_count,
        "analysis": analysis,
        "active_count": active_count,
        "user": get_user(request)
    })

@router.post("/save")
async def save_sustainability(
    request: Request,
    month_str: str = Form(...),
    electricity: float = Form(0),
    water: float = Form(0),
    bio_waste: float = Form(0),
    gen_waste: float = Form(0),
    sessions: Optional[int] = Form(None),
    db: Session = Depends(get_db)
):
    user = get_user(request)
    role = getattr(user, "role", None) if not isinstance(user, dict) else user.get("role", "")
    if role == "ecogreen":
        raise HTTPException(status_code=403, detail="Save operation disabled for EcoGreen user")

    record = db.query(SustainabilityRecord).filter(SustainabilityRecord.record_month == month_str).first()
    if not record:
        record = SustainabilityRecord(record_month=month_str)
        db.add(record)
    
    record.electricity_kwh = electricity
    record.water_m3 = water
    record.biomedical_waste_kg = bio_waste
    record.general_waste_kg = gen_waste
    record.total_sessions_override = sessions
    record.timestamp = datetime.utcnow()
    
    db.commit()
    return RedirectResponse(url=f"/analytics/sustainability?month={month_str}", status_code=303)
