"""
HD Dashboard — FastAPI Application
Multi-user hemodialysis patient data entry + clinical dashboard
"""
import os
import re
from fastapi import FastAPI, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import date, datetime
from typing import Optional
import json

from database import get_db, create_tables, Patient, MonthlyRecord, AlertLog, SessionLocal
from dashboard_logic import compute_dashboard, get_current_month_str, get_month_label, get_patients_needing_alerts
from alerts import send_bulk_whatsapp_alerts, send_ward_email, generate_all_whatsapp_links
from ml_analytics import run_patient_analytics, run_cohort_analytics
import dynamic_vars

app = FastAPI(title="HD Dashboard")
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/health")
def health_check():
    """Render health check endpoint — also used by UptimeRobot to prevent sleep."""
    from datetime import datetime
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}

def run_migrations():
    """Auto-add new clinical columns if they don't exist (Fixes 500 errors)."""
    from sqlalchemy import text
    db = SessionLocal()
    migrations = [
        "ALTER TABLE patients ADD COLUMN IF NOT EXISTS dialysis_vintage_months INTEGER DEFAULT 0",
        "ALTER TABLE patients ADD COLUMN IF NOT EXISTS primary_diagnosis VARCHAR",
        "ALTER TABLE patients ADD COLUMN IF NOT EXISTS comorbidity_cvd BOOLEAN DEFAULT FALSE",
        "ALTER TABLE patients ADD COLUMN IF NOT EXISTS comorbidity_cvsd BOOLEAN DEFAULT FALSE",
        "ALTER TABLE patients ADD COLUMN IF NOT EXISTS hyperparathyroidism BOOLEAN DEFAULT FALSE",
        "ALTER TABLE monthly_records ADD COLUMN IF NOT EXISTS bp_sys INTEGER",
        "ALTER TABLE monthly_records ADD COLUMN IF NOT EXISTS bp_dia INTEGER",
        "ALTER TABLE monthly_records ADD COLUMN IF NOT EXISTS crp FLOAT",
        "ALTER TABLE monthly_records ADD COLUMN IF NOT EXISTS urr FLOAT",
        "ALTER TABLE monthly_records ADD COLUMN IF NOT EXISTS mcv FLOAT",
        "ALTER TABLE monthly_records ADD COLUMN IF NOT EXISTS hb_hematocrit FLOAT",
        "ALTER TABLE monthly_records ADD COLUMN IF NOT EXISTS iron_iv_supplement BOOLEAN DEFAULT FALSE"
    ]
    for m in migrations:
        try:
            db.execute(text(m))
            db.commit()
        except Exception:
            db.rollback()
    
    # Also seed default dynamic variables
    try:
        dynamic_vars.seed_default_variables(db)
    except Exception as e:
        print(f"Seeding error: {e}")
        
    db.close()

# Create tables and run migrations on startup
@app.on_event("startup")
def startup():
    create_tables()
    run_migrations()


# ─────────────────────────────────────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────

@app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
def dashboard(request: Request, month: Optional[str] = None, db: Session = Depends(get_db)):
    if request.method == "HEAD":
        return HTMLResponse(content="", status_code=200)
    month_str = month or get_current_month_str()
    data = compute_dashboard(db, month_str)
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "data": data,
        "month_str": month_str,
        "current_month": get_current_month_str(),
        "user": {"role": "admin", "full_name": "Doctor"} # Safety dummy for templates
    })


@app.get("/api/dashboard")
def api_dashboard(month: Optional[str] = None, db: Session = Depends(get_db)):
    """JSON endpoint for dashboard data (used by Plotly.js on client)."""
    month_str = month or get_current_month_str()
    data = compute_dashboard(db, month_str)
    return JSONResponse(content=data)


# ─────────────────────────────────────────────────────────────────────────────
# PATIENT LIST
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/patients", response_class=HTMLResponse)
def patient_list(request: Request, db: Session = Depends(get_db)):
    patients = db.query(Patient).filter(Patient.is_active == True).order_by(Patient.name).all()
    return templates.TemplateResponse("patients.html", {
        "request": request,
        "patients": patients,
    })


# ─────────────────────────────────────────────────────────────────────────────
# ADD / EDIT PATIENT (Demographics)
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/patients/new", response_class=HTMLResponse)
def new_patient_form(request: Request):
    return templates.TemplateResponse("patient_form.html", {
        "request": request,
        "patient": None,
        "mode": "new",
    })


@app.post("/patients/new")
def create_patient(
    request: Request,
    db: Session = Depends(get_db),
    hid_no: str = Form(...),
    name: str = Form(...),
    relation: str = Form(""),
    sex: str = Form(...),
    contact_no: str = Form(""),
    email: str = Form(""),
    diagnosis: str = Form(""),
    hd_wef_date: Optional[str] = Form(None),
    viral_markers: str = Form(""),
    access_type: str = Form(""),
    access_date: Optional[str] = Form(None),
    dry_weight: Optional[float] = Form(None),
    hd_slot_1: str = Form(""),
    hd_slot_2: str = Form(""),
    hd_slot_3: str = Form(""),
    whatsapp_notify: bool = Form(False),
    mail_trigger: bool = Form(False),
):
    # Check HID uniqueness
    existing = db.query(Patient).filter(Patient.hid_no == hid_no).first()
    if existing:
        return templates.TemplateResponse("patient_form.html", {
            "request": request,
            "patient": None,
            "mode": "new",
            "error": f"HID {hid_no} already exists.",
        })

    # Build WhatsApp link from contact number
    whatsapp_link = f"https://wa.me/91{contact_no.strip()}" if contact_no else ""

    p = Patient(
        hid_no=hid_no,
        name=name,
        relation=relation,
        sex=sex,
        contact_no=contact_no,
        email=email,
        diagnosis=diagnosis,
        hd_wef_date=datetime.strptime(hd_wef_date, "%Y-%m-%d").date() if hd_wef_date else None,
        viral_markers=viral_markers,
        access_type=access_type,
        access_date=datetime.strptime(access_date, "%Y-%m-%d").date() if access_date else None,
        dry_weight=dry_weight,
        hd_slot_1=hd_slot_1,
        hd_slot_2=hd_slot_2,
        hd_slot_3=hd_slot_3,
        whatsapp_link=whatsapp_link,
        whatsapp_notify=whatsapp_notify,
        mail_trigger=mail_trigger,
    )
    db.add(p)
    db.commit()
    return RedirectResponse(url="/patients", status_code=303)


@app.get("/patients/{patient_id}/edit", response_class=HTMLResponse)
def edit_patient_form(patient_id: int, request: Request, db: Session = Depends(get_db)):
    p = db.query(Patient).filter(Patient.id == patient_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")
    return templates.TemplateResponse("patient_form.html", {
        "request": request,
        "patient": p,
        "mode": "edit",
    })


@app.post("/patients/{patient_id}/edit")
def update_patient(
    patient_id: int,
    request: Request,
    db: Session = Depends(get_db),
    hid_no: str = Form(...),
    name: str = Form(...),
    relation: str = Form(""),
    sex: str = Form(...),
    contact_no: str = Form(""),
    email: str = Form(""),
    diagnosis: str = Form(""),
    hd_wef_date: Optional[str] = Form(None),
    viral_markers: str = Form(""),
    access_type: str = Form(""),
    access_date: Optional[str] = Form(None),
    dry_weight: Optional[float] = Form(None),
    hd_slot_1: str = Form(""),
    hd_slot_2: str = Form(""),
    hd_slot_3: str = Form(""),
    whatsapp_notify: bool = Form(False),
    mail_trigger: bool = Form(False),
):
    p = db.query(Patient).filter(Patient.id == patient_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")

    p.hid_no = hid_no
    p.name = name
    p.relation = relation
    p.sex = sex
    p.contact_no = contact_no
    p.email = email
    p.diagnosis = diagnosis
    p.hd_wef_date = datetime.strptime(hd_wef_date, "%Y-%m-%d").date() if hd_wef_date else None
    p.viral_markers = viral_markers
    p.access_type = access_type
    p.access_date = datetime.strptime(access_date, "%Y-%m-%d").date() if access_date else None
    p.dry_weight = dry_weight
    p.hd_slot_1 = hd_slot_1
    p.hd_slot_2 = hd_slot_2
    p.hd_slot_3 = hd_slot_3
    p.whatsapp_link = f"https://wa.me/91{contact_no.strip()}" if contact_no else ""
    p.whatsapp_notify = whatsapp_notify
    p.mail_trigger = mail_trigger
    p.updated_at = datetime.utcnow()

    db.commit()
    return RedirectResponse(url="/patients", status_code=303)


@app.post("/patients/{patient_id}/deactivate")
def deactivate_patient(patient_id: int, db: Session = Depends(get_db)):
    p = db.query(Patient).filter(Patient.id == patient_id).first()
    if p:
        p.is_active = False
        db.commit()
    return RedirectResponse(url="/patients", status_code=303)


# ─────────────────────────────────────────────────────────────────────────────
# MONTHLY DATA ENTRY
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/entry", response_class=HTMLResponse)
def entry_index(request: Request, month: Optional[str] = None, db: Session = Depends(get_db)):
    month_str = month or get_current_month_str()
    patients = db.query(Patient).filter(Patient.is_active == True).order_by(Patient.name).all()
    # Tag which patients already have a record for this month
    existing_ids = {
        r.patient_id
        for r in db.query(MonthlyRecord).filter(MonthlyRecord.record_month == month_str).all()
    }
    return templates.TemplateResponse("entry_list.html", {
        "request": request,
        "patients": patients,
        "month_str": month_str,
        "month_label": get_month_label(month_str),
        "existing_ids": existing_ids,
    })


@app.get("/entry/{patient_id}", response_class=HTMLResponse)
def entry_form(patient_id: int, request: Request, month: Optional[str] = None, db: Session = Depends(get_db)):
    p = db.query(Patient).filter(Patient.id == patient_id).first()
    if not p:
        raise HTTPException(status_code=404)
    month_str = month or get_current_month_str()
    # Load existing record if present (for editing)
    rec = db.query(MonthlyRecord).filter(
        MonthlyRecord.patient_id == patient_id,
        MonthlyRecord.record_month == month_str
    ).first()
    return templates.TemplateResponse("entry_form.html", {
        "request": request,
        "patient": p,
        "record": rec,
        "month_str": month_str,
        "month_label": get_month_label(month_str),
    })


@app.post("/entry/{patient_id}")
def save_entry(
    patient_id: int,
    request: Request,
    db: Session = Depends(get_db),
    month_str: str = Form(...),
    entered_by: str = Form(""),
    idwg: Optional[float] = Form(None),
    hb: Optional[float] = Form(None),
    serum_ferritin: Optional[float] = Form(None),
    tsat: Optional[float] = Form(None),
    serum_iron: Optional[float] = Form(None),
    epo_mircera_dose: str = Form(""),
    calcium: Optional[float] = Form(None),
    alkaline_phosphate: Optional[float] = Form(None),
    phosphorus: Optional[float] = Form(None),
    albumin: Optional[float] = Form(None),
    ast: Optional[float] = Form(None),
    alt: Optional[float] = Form(None),
    vit_d: Optional[float] = Form(None),
    ipth: Optional[float] = Form(None),
    av_daily_calories: Optional[float] = Form(None),
    av_daily_protein: Optional[float] = Form(None),
    issues: str = Form(""),
):
    # Clinical Validation
    if idwg and idwg > 15.0:
        raise HTTPException(status_code=400, detail=f"IDWG error: {idwg} is clinically invalid. Max allowed is 15kg.")
    if hb and hb > 25.0:
        raise HTTPException(status_code=400, detail=f"Hemoglobin error: {hb} is clinically invalid. Max allowed is 25g/dL.")

    # Upsert: update if exists, else create
    rec = db.query(MonthlyRecord).filter(
        MonthlyRecord.patient_id == patient_id,
        MonthlyRecord.record_month == month_str
    ).first()
    
    # Auto-calculate epo_weekly_units for ERI
    def parse_epo(text):
        if not text: return 0.0
        matches = re.findall(r"\d+", str(text))
        return float(matches[0]) if matches else 0.0
    epo_units = parse_epo(epo_mircera_dose)

    if rec:
        # Update existing
        rec.idwg = idwg; rec.hb = hb; rec.serum_ferritin = serum_ferritin
        rec.tsat = tsat; rec.serum_iron = serum_iron; rec.epo_mircera_dose = epo_mircera_dose
        rec.calcium = calcium; rec.alkaline_phosphate = alkaline_phosphate
        rec.phosphorus = phosphorus; rec.albumin = albumin
        rec.ast = ast; rec.alt = alt; rec.vit_d = vit_d; rec.ipth = ipth
        rec.av_daily_calories = av_daily_calories; rec.av_daily_protein = av_daily_protein
        rec.issues = issues; rec.entered_by = entered_by
        rec.timestamp = datetime.utcnow()
        rec.epo_weekly_units = epo_units
    else:
        rec = MonthlyRecord(
            patient_id=patient_id, record_month=month_str, entered_by=entered_by,
            idwg=idwg, hb=hb, serum_ferritin=serum_ferritin, tsat=tsat,
            serum_iron=serum_iron, epo_mircera_dose=epo_mircera_dose,
            calcium=calcium, alkaline_phosphate=alkaline_phosphate,
            phosphorus=phosphorus, albumin=albumin, ast=ast, alt=alt,
            vit_d=vit_d, ipth=ipth, av_daily_calories=av_daily_calories,
            av_daily_protein=av_daily_protein, issues=issues,
            epo_weekly_units=epo_units
        )
        db.add(rec)
    db.commit()
    return RedirectResponse(url=f"/entry?month={month_str}", status_code=303)


# ─────────────────────────────────────────────────────────────────────────────
# API — patient search (for autocomplete)
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/patients")
def api_patients(q: str = "", db: Session = Depends(get_db)):
    patients = db.query(Patient).filter(
        Patient.is_active == True,
        Patient.name.ilike(f"%{q}%")
    ).limit(20).all()
    return [{"id": p.id, "name": p.name, "hid": p.hid_no} for p in patients]


# ─────────────────────────────────────────────────────────────────────────────
# ALERT API ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/api/send-whatsapp")
def api_send_whatsapp(month: Optional[str] = None, db: Session = Depends(get_db)):
    """WhatsApp: auto via Twilio if configured, else returns wa.me links."""
    month_str = month or get_current_month_str()
    month_label = get_month_label(month_str)
    alert_patients = get_patients_needing_alerts(db, month_str)
    if not alert_patients:
        return JSONResponse({"message": "No alert patients this month."})
    results = send_bulk_whatsapp_alerts(alert_patients, month_label)
    if results.get("mode") == "twilio":
        for r in results.get("results", []):
            p = db.query(Patient).filter(Patient.name == r["name"]).first()
            if p:
                db.add(AlertLog(
                    patient_id=p.id, alert_type="whatsapp",
                    alert_reason=r.get("status"),
                    status="sent" if r.get("status") == "sent" else "failed",
                    message_preview=r.get("sid") or r.get("error") or "",
                ))
        db.commit()
    return JSONResponse(results)


@app.get("/api/whatsapp-links")
def api_whatsapp_links(month: Optional[str] = None, db: Session = Depends(get_db)):
    """Return pre-filled wa.me links for all alert patients — no Twilio needed."""
    month_str = month or get_current_month_str()
    month_label = get_month_label(month_str)
    alert_patients = get_patients_needing_alerts(db, month_str)
    if not alert_patients:
        return JSONResponse({"links": [], "message": "No alert patients."})
    links = generate_all_whatsapp_links(alert_patients, month_label)
    return JSONResponse({"links": links, "count": len(links)})


@app.post("/api/send-email")
def api_send_email(month: Optional[str] = None, db: Session = Depends(get_db)):
    """Send ward report email to the configured doctor/admin address."""
    month_str = month or get_current_month_str()
    month_label = get_month_label(month_str)
    year = month_str[:4]
    alert_patients = get_patients_needing_alerts(db, month_str)

    if not alert_patients:
        return JSONResponse({"message": "✅ No alert patients — nothing to report."})

    success, detail = send_ward_email(alert_patients, month_label, year)

    # Log
    log = AlertLog(
        patient_id=None,
        alert_type="email",
        alert_reason=f"Ward report {month_label} {year}",
        status="sent" if success else "failed",
        message_preview=detail,
    )
    db.add(log)
    db.commit()

    if success:
        return JSONResponse({"message": f"✅ {detail}"})
    return JSONResponse({"message": f"❌ {detail}"}, status_code=500)

# ─────────────────────────────────────────────────────────────────────────────
# ML ANALYTICS ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/analytics/patient/{patient_id}")
def api_patient_analytics(
    patient_id: int,
    month: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Run all ML analytics for a single patient."""
    result = run_patient_analytics(db, patient_id)
    return JSONResponse(content=result)


@app.get("/api/analytics/cohort")
def api_cohort_analytics(db: Session = Depends(get_db)):
    """Run cohort-wide analytics for unit-wide trend panel."""
    result = run_cohort_analytics(db)
    return JSONResponse(content=result)


@app.get("/patients/{patient_id}/timeline", response_class=HTMLResponse)
def patient_timeline(
    patient_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Individual patient timeline page with all charts and ML insights."""
    from database import Patient as PatientModel
    patient = db.query(PatientModel).filter(
        PatientModel.id == patient_id
    ).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    analytics = run_patient_analytics(db, patient_id)
    return templates.TemplateResponse("patient_timeline.html", {
        "request": request,
        "patient": patient,
        "analytics": analytics,
    })


# ─────────────────────────────────────────────────────────────────────────────
# DYNAMIC VARIABLES (EAV SYSTEM)
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/variables", response_class=HTMLResponse)
def variable_manager(request: Request, db: Session = Depends(get_db)):
    """UI for defining vars and bulk entering data."""
    from database import DynamicVariableDefinition
    vars = db.query(DynamicVariableDefinition).filter(DynamicVariableDefinition.is_active == True).all()
    return templates.TemplateResponse("variable_manager.html", {
        "request": request,
        "variables": vars,
        "user": {"role": "admin", "full_name": "Doctor"}
    })

@app.get("/api/variables")
def get_variables(db: Session = Depends(get_db)):
    from database import DynamicVariableDefinition
    vars = db.query(DynamicVariableDefinition).all()
    return vars

@app.get("/api/variable-data-grid/{variable_id}")
def get_variable_grid(variable_id: int, start: str, end: str, db: Session = Depends(get_db)):
    # Helper to generate month list
    try:
        s_yr, s_mo = map(int, start.split('-'))
        e_yr, e_mo = map(int, end.split('-'))
        months = []
        curr_yr, curr_mo = s_yr, s_mo
        while (curr_yr < e_yr) or (curr_yr == e_yr and curr_mo <= e_mo):
            months.append(f"{curr_yr}-{curr_mo:02d}")
            curr_mo += 1
            if curr_mo > 12: curr_mo = 1; curr_yr += 1
        
        grid = dynamic_vars.get_variable_data_grid(db, variable_id, months)
        return {"months": months, "grid": grid}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/variable-values/{variable_id}")
async def save_variable_grid(variable_id: int, request: Request, db: Session = Depends(get_db)):
    data = await request.json() # list of {patient_id, month, value}
    dynamic_vars.save_variable_values(db, variable_id, data)
    return {"status": "ok"}

@app.get("/api/analytics/dynamic/{variable_id}")
def get_dynamic_analytics(variable_id: int, db: Session = Depends(get_db)):
    data = dynamic_vars.get_dynamic_variable_analytics(db, variable_id)
    return data
