from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime
from itsdangerous import BadData

from database import get_db, SustainabilityRecord, MonthlyRecord, Patient
from config import templates, _csrf_signer
from dependencies import get_user
from dashboard_logic import get_current_month_str, get_month_label

router = APIRouter(prefix="/analytics/sustainability", tags=["sustainability"])

# ── Centre location — drives supply-chain logistics EF ───────────────────────
CENTRE_LOCATION = "Pune"   # update when centre moves
# Nashik → Pune one-way road distance (km).  Nashik is the primary HD consumable
# distribution hub serving Western/National region (Baxter, Fresenius regional warehouse).
CONS_SUPPLY_KM = 180
# Tonne-km formula: 998 kg/patient/yr × distance_km × 0.08 kg CO₂e/tonne-km
# = 0.998 tonne × 0.08 EF × 180 km = 14.37 kg/patient/yr for Pune.
# Cite: Barraclough KA et al. AJKD 2025 Table 1 (material inventory, India-adapted);
#       MoRTH road freight EF = 0.08 kg CO₂e/tonne-km.
CO2E_CONS_SUPPLY_TONNE_KM = 0.08         # kg CO₂e/tonne-km — MoRTH road freight
CONS_ANNUAL_WEIGHT_KG = 998              # kg consumables/patient/yr — Barraclough AJKD 2025, India-adapted
CO2E_CONS_SUPPLY_PER_PATIENT_YR = (CONS_ANNUAL_WEIGHT_KG / 1000) * CONS_SUPPLY_KM * CO2E_CONS_SUPPLY_TONNE_KM
# = 14.37 kg/patient/yr for Pune

# ── ICHD India Factors (LCI-validated, Barraclough AJKD 2025 + CEA v19) ──────
CO2E_ELECTRICITY = 0.71    # kg/kWh — CEA CO2 Baseline Database v19 (Dec 2023)
CO2E_WATER = 0.30          # kg/m3 — CPHEEO norms for Indian municipal WTPs
CO2E_BIO_WASTE = 1.85      # kg/kg — yellow-bag incineration (IPCC clinical waste LCA)
CO2E_GEN_WASTE = 0.24      # kg/kg — red-bag autoclave (BMWM Rules 2016); matches frontend
CO2E_CONS_PER_SESSION = 13.5  # kg/session — Barraclough Table 3 ÷ 156 sessions = 14.2 AU; 13.5 India
# Patient transport: NOT calculated here — use km-by-mode entry in the frontend
# calculator (frontend JS already captures bus/car/auto/bike × mode EF).  A flat
# per-session factor cannot represent the 3–5× range across urban/rural centres.

@router.get("", response_class=HTMLResponse)
async def sustainability_dashboard(request: Request, month: Optional[str] = None, db: Session = Depends(get_db)):
    month_str = month or get_current_month_str()
    record = db.query(SustainabilityRecord).filter(SustainabilityRecord.record_month == month_str).first()
    
    # Get total sessions for the month from MonthlyRecords
    # Note: In a production app, we'd count actual SessionRecords, but we'll approximate 
    # based on patients * frequency or just total active count * 12.
    patient_count = db.query(MonthlyRecord).filter(MonthlyRecord.record_month == month_str).count()
    # Prefer the frontend's frequency-weighted override; fall back to flat estimate when absent or <= 0.
    _override = record.total_sessions_override if record else None
    session_count = (_override if _override is not None and _override > 0 else (patient_count * 13)) or 1
    
    analysis = None
    if record:
        e = record.electricity_kwh * CO2E_ELECTRICITY
        w = record.water_m3 * CO2E_WATER
        wt = (record.biomedical_waste_kg * CO2E_BIO_WASTE) + (record.general_waste_kg * CO2E_GEN_WASTE)
        c = session_count * CO2E_CONS_PER_SESSION
        # Supply-chain logistics: annual per-patient cost, prorated to month
        s = patient_count * CO2E_CONS_SUPPLY_PER_PATIENT_YR / 12
        # Patient transport excluded — mode-split varies 3–5× across centres;
        # use the km-by-mode frontend calculator for accurate transport figures.
        total = e + w + wt + c + s

        analysis = {
            "total": round(total, 1),
            "per_session": round(total / session_count, 1),
            "centre_location": CENTRE_LOCATION,
            "cons_supply_km": CONS_SUPPLY_KM,
            "breakdown": [
                {"label": "Energy (Electricity)",              "val": round(e,  1), "color": "#10b981"},
                {"label": "Water (Purification)",              "val": round(w,  1), "color": "#3b82f6"},
                {"label": "Waste Management",                  "val": round(wt, 1), "color": "#ef4444"},
                {"label": "Medical Consumables",               "val": round(c,  1), "color": "#8b5cf6"},
                {"label": f"Supply Chain ({CENTRE_LOCATION})", "val": round(s,  1), "color": "#06b6d4"},
            ]
        }

    active_count = db.query(Patient).filter(Patient.is_active == True).count()

    csrf_token = _csrf_signer.sign("sustainability").decode()

    return templates.TemplateResponse("sustainability.html", {
        "request": request,
        "month_str": month_str,
        "month_label": get_month_label(month_str),
        "record": record,
        "session_count": session_count,
        "analysis": analysis,
        "active_count": active_count,
        "user": get_user(request),
        "csrf_token": csrf_token,
    })

@router.post("/save")
async def save_sustainability(
    request: Request,
    month_str: str = Form(...),
    csrf_token: Optional[str] = Form(None),
    # The frontend always posts monthly-normalised floats (timeframe conversion
    # is applied in saveRecord() before submission).
    electricity: float = Form(0),
    water: float = Form(0),
    bio_waste: float = Form(0),
    gen_waste: float = Form(0),
    sessions: Optional[int] = Form(None),
    db: Session = Depends(get_db)
):
    # ── CSRF verification (1 h window, same scheme as entry.py) ──────────────
    try:
        if not csrf_token:
            raise BadData("Missing CSRF token")
        val = _csrf_signer.unsign(csrf_token, max_age=3600)
        val_str = val.decode() if isinstance(val, bytes) else val
        if val_str != "sustainability":
            raise BadData("Scope mismatch")
    except BadData:
        raise HTTPException(status_code=403, detail="Invalid or expired form token. Please refresh and try again.")

    user = get_user(request)
    role = getattr(user, "role", None) if not isinstance(user, dict) else user.get("role", "")
    if role == "ecogreen":
        raise HTTPException(status_code=403, detail="Save disabled for EcoGreen user.")

    actor = (user.get("username") if isinstance(user, dict) else getattr(user, "username", "unknown")) or "unknown"

    # ── Input bounds validation (reject with 400 on failure) ──────────────────
    if electricity < 0 or electricity > 500000:
        raise HTTPException(status_code=400, detail="Electricity quantity out of bounds.")
    if water < 0 or water > 50000:
        raise HTTPException(status_code=400, detail="Water quantity out of bounds.")
    if bio_waste < 0 or bio_waste > 100000:
        raise HTTPException(status_code=400, detail="Biomedical waste quantity out of bounds.")
    if gen_waste < 0 or gen_waste > 100000:
        raise HTTPException(status_code=400, detail="General waste quantity out of bounds.")
    if sessions is not None and not (0 < sessions <= 20000):
        raise HTTPException(status_code=400, detail="Sessions quantity out of bounds.")

    record = db.query(SustainabilityRecord).filter(SustainabilityRecord.record_month == month_str).first()
    if not record:
        record = SustainabilityRecord(record_month=month_str)
        db.add(record)

    record.electricity_kwh          = electricity
    record.water_m3                 = water
    record.biomedical_waste_kg      = bio_waste
    record.general_waste_kg         = gen_waste
    record.total_sessions_override  = sessions
    record.timestamp                = datetime.utcnow()
    record.updated_by               = actor

    db.commit()
    return RedirectResponse(url=f"/analytics/sustainability?month={month_str}", status_code=303)
