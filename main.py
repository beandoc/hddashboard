"""
HD Dashboard — FastAPI Application
Multi-user hemodialysis patient data entry + clinical dashboard
"""
import os
from fastapi import FastAPI, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import text, inspect
from datetime import date, datetime
from typing import Optional
import json

# Database engine and session for startup logic
from database import get_db, create_tables, Patient, MonthlyRecord, AlertLog, engine, SessionLocal
from dashboard_logic import compute_dashboard, get_current_month_str, get_month_label, get_patients_needing_alerts
from alerts import send_bulk_whatsapp_alerts, send_ward_email, generate_all_whatsapp_links
from ml_analytics import run_patient_analytics, run_cohort_analytics
from dynamic_vars import (VariableDefinition, VariableValue, get_all_variables,
    get_patient_variable_history, upsert_variable_value, seed_preset_variables)

app = FastAPI(title="HD Dashboard")
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/health")
def health_check():
    """Render health check endpoint — also used by UptimeRobot to prevent sleep."""
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}

# Create tables on startup
@app.on_event("startup")
def startup():
    create_tables()
    
    # 🚨 Self-Healing Migration (Handles Render Free Column Sync)
    inspector = inspect(engine)
    with engine.connect() as conn:
        # 1. Check variable_definitions columns
        v_existing = [c['name'] for c in inspector.get_columns('variable_definitions')]
        v_missing = [
            ("alert_direction", "VARCHAR DEFAULT 'both'"),
            ("decimal_places", "INTEGER DEFAULT 1"),
            ("created_at", "TIMESTAMP DEFAULT NOW()"),
            ("created_by", "VARCHAR DEFAULT 'system'"),
        ]
        for col, dtype in v_missing:
            if col not in v_existing:
                try:
                    conn.execute(text(f"ALTER TABLE variable_definitions ADD COLUMN {col} {dtype}"))
                    conn.commit()
                except Exception: pass

        # 2. Check monthly_records columns (New Clinical Sensors)
        r_existing = [c['name'] for c in inspector.get_columns('monthly_records')]
        r_missing = [
            ("urr", "FLOAT"),
            ("epo_weekly_units", "FLOAT"),
            ("bp_sys", "FLOAT"),
            ("crp", "FLOAT"),
            ("target_dry_weight", "FLOAT"),
            ("access_type", "VARCHAR"),
        ]
        for col, dtype in r_missing:
            if col not in r_existing:
                try:
                    conn.execute(text(f"ALTER TABLE monthly_records ADD COLUMN {col} {dtype}"))
                    conn.commit()
                except Exception: pass

        # 3. Check patients columns (Vaccination & Demographics)
        p_existing = [c['name'] for c in inspector.get_columns('patients')]
        p_missing = [
            ("relation_type", "VARCHAR"),
            ("hep_b_status", "VARCHAR"),
            ("hep_b_date", "DATE"),
            ("pneumococcal_date", "DATE"),
            ("influenza_date", "DATE"),
        ]
        for col, dtype in p_missing:
            if col not in p_existing:
                try:
                    conn.execute(text(f"ALTER TABLE patients ADD COLUMN {col} {dtype}"))
                    conn.commit()
                except Exception: pass

    # Create dynamic variable tables and seed presets
    from database import Base
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_preset_variables(db)
    finally:
        db.close()

# Helper to inject user into every template
def get_user(request: Request):
    return getattr(request.state, "user", None)


# ─────────────────────────────────────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, month: Optional[str] = None, db: Session = Depends(get_db)):
    month_str = month or get_current_month_str()
    try:
        data = compute_dashboard(db, month_str)
    except Exception as e:
        import logging
        logging.error(f"Dashboard logic failure: {e}")
        data = {
            "metrics": {
                "total": 0, "male": 0, "female": 0, "unknown_sex": 0,
                "high_idwg": {"count": 0, "names": []}, 
                "low_albumin": {"count": 0, "names": []}, "high_phosphorus": {"count": 0, "names": []},
                "iv_iron": {"count": 0, "names": []}, "hb_drop_alert": {"count": 0, "names": []},
                "low_calcium": {"count": 0, "names": []}, "high_ipth": {"count": 0, "names": []},
                "low_vit_d": {"count": 0, "names": []}, "low_protein": {"count": 0, "names": []},
                "elevated_liver": {"count": 0, "names": []}, "dialysis_intensification": {"count": 0, "names": []},
                "todays_hd": {"count": 0, "names": []}, "non_avf": {"count": 0, "names": [], "types": {}},
                "trend_hb": [], "trend_albumin": [], "trend_phosphorus": []
            },
            "patient_rows": [], "month_label": get_month_label(month_str), "prev_month_label": "N/A"
        }
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "data": data,
        "month_str": month_str,
        "current_month": get_current_month_str(),
        "user": get_user(request),
    })


# ─────────────────────────────────────────────────────────────────────────────
# PATIENT LIST
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/patients", response_class=HTMLResponse)
def patient_list(request: Request, db: Session = Depends(get_db)):
    patients = db.query(Patient).filter(Patient.is_active == True).order_by(Patient.name).all()
    return templates.TemplateResponse("patients.html", {
        "request": request,
        "patients": patients,
        "user": get_user(request),
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
        "error": None,
        "user": get_user(request),
    })


@app.post("/patients/new")
def create_patient(
    request: Request,
    db: Session = Depends(get_db),
    hid_no: str = Form(...),
    name: str = Form(...),
    relation: str = Form(""),
    relation_type: str = Form(""),
    sex: str = Form(...),
    contact_no: str = Form(""),
    email: str = Form(""),
    diagnosis: str = Form(""),
    hd_wef_date: Optional[str] = Form(None),
    viral_markers: str = Form(""),
    hep_b_status: str = Form(""),
    hep_b_date: Optional[str] = Form(None),
    pneumococcal_date: Optional[str] = Form(None),
    influenza_date: Optional[str] = Form(None),
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
            "user": get_user(request),
        })

    whatsapp_link = f"https://wa.me/91{contact_no.strip()}" if contact_no else ""

    p = Patient(
        hid_no=hid_no, name=name, relation=relation, relation_type=relation_type,
        sex=sex, contact_no=contact_no, email=email, diagnosis=diagnosis,
        hd_wef_date=datetime.strptime(hd_wef_date, "%Y-%m-%d").date() if hd_wef_date else None,
        viral_markers=viral_markers, hep_b_status=hep_b_status,
        hep_b_date=datetime.strptime(hep_b_date, "%Y-%m-%d").date() if hep_b_date else None,
        pneumococcal_date=datetime.strptime(pneumococcal_date, "%Y-%m-%d").date() if pneumococcal_date else None,
        influenza_date=datetime.strptime(influenza_date, "%Y-%m-%d").date() if influenza_date else None,
        access_type=access_type,
        access_date=datetime.strptime(access_date, "%Y-%m-%d").date() if access_date else None,
        dry_weight=dry_weight, hd_slot_1=hd_slot_1, hd_slot_2=hd_slot_2, hd_slot_3=hd_slot_3,
        whatsapp_link=whatsapp_link, whatsapp_notify=whatsapp_notify, mail_trigger=mail_trigger,
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
        "error": None,
        "user": get_user(request),
    })


@app.post("/patients/{patient_id}/edit")
def update_patient(
    patient_id: int,
    request: Request,
    db: Session = Depends(get_db),
    hid_no: str = Form(...),
    name: str = Form(...),
    relation: str = Form(""),
    relation_type: str = Form(""),
    sex: str = Form(...),
    contact_no: str = Form(""),
    email: str = Form(""),
    diagnosis: str = Form(""),
    hd_wef_date: Optional[str] = Form(None),
    viral_markers: str = Form(""),
    hep_b_status: str = Form(""),
    hep_b_date: Optional[str] = Form(None),
    pneumococcal_date: Optional[str] = Form(None),
    influenza_date: Optional[str] = Form(None),
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

    p.hid_no = hid_no; p.name = name; p.relation = relation; p.relation_type = relation_type
    p.sex = sex; p.contact_no = contact_no; p.email = email; p.diagnosis = diagnosis
    p.hd_wef_date = datetime.strptime(hd_wef_date, "%Y-%m-%d").date() if hd_wef_date else None
    p.viral_markers = viral_markers; p.hep_b_status = hep_b_status
    p.hep_b_date = datetime.strptime(hep_b_date, "%Y-%m-%d").date() if hep_b_date else None
    p.pneumococcal_date = datetime.strptime(pneumococcal_date, "%Y-%m-%d").date() if pneumococcal_date else None
    p.influenza_date = datetime.strptime(influenza_date, "%Y-%m-%d").date() if influenza_date else None
    p.access_type = access_type
    p.access_date = datetime.strptime(access_date, "%Y-%m-%d").date() if access_date else None
    p.dry_weight = dry_weight; p.hd_slot_1 = hd_slot_1; p.hd_slot_2 = hd_slot_2; p.hd_slot_3 = hd_slot_3
    p.whatsapp_link = f"https://wa.me/91{contact_no.strip()}" if contact_no else ""
    p.whatsapp_notify = whatsapp_notify; p.mail_trigger = mail_trigger
    p.updated_at = datetime.utcnow()

    db.commit()
    return RedirectResponse(url="/patients", status_code=303)


# ─────────────────────────────────────────────────────────────────────────────
# MONTHLY DATA ENTRY
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/entry", response_class=HTMLResponse)
def entry_index(request: Request, month: Optional[str] = None, db: Session = Depends(get_db)):
    month_str = month or get_current_month_str()
    patients = db.query(Patient).filter(Patient.is_active == True).order_by(Patient.name).all()
    existing_ids = {r.patient_id for r in db.query(MonthlyRecord).filter(MonthlyRecord.record_month == month_str).all()}
    return templates.TemplateResponse("entry_list.html", {
        "request": request,
        "patients": patients,
        "month_str": month_str,
        "month_label": get_month_label(month_str),
        "existing_ids": existing_ids,
        "user": get_user(request),
    })


@app.get("/entry/{patient_id}", response_class=HTMLResponse)
def entry_form(patient_id: int, request: Request, month: Optional[str] = None, db: Session = Depends(get_db)):
    p = db.query(Patient).filter(Patient.id == patient_id).first()
    if not p: raise HTTPException(status_code=404)
    month_str = month or get_current_month_str()
    rec = db.query(MonthlyRecord).filter(MonthlyRecord.patient_id == patient_id, MonthlyRecord.record_month == month_str).first()
    return templates.TemplateResponse("entry_form.html", {
        "request": request, "patient": p, "record": rec,
        "month_str": month_str, "month_label": get_month_label(month_str),
        "user": get_user(request),
    })


@app.post("/entry/{patient_id}")
def save_entry(
    patient_id: int, request: Request, db: Session = Depends(get_db),
    month_str: str = Form(...),
    entered_by: str = Form(""),
    access_type: str = Form(""),
    target_dry_weight: Optional[float] = Form(None),
    idwg: Optional[float] = Form(None), hb: Optional[float] = Form(None),
    serum_ferritin: Optional[float] = Form(None), tsat: Optional[float] = Form(None),
    serum_iron: Optional[float] = Form(None), epo_mircera_dose: str = Form(""),
    epo_weekly_units: Optional[float] = Form(None), calcium: Optional[float] = Form(None),
    alkaline_phosphate: Optional[float] = Form(None), phosphorus: Optional[float] = Form(None),
    albumin: Optional[float] = Form(None), ast: Optional[float] = Form(None),
    alt: Optional[float] = Form(None), vit_d: Optional[float] = Form(None),
    ipth: Optional[float] = Form(None), av_daily_calories: Optional[float] = Form(None),
    av_daily_protein: Optional[float] = Form(None), issues: str = Form(""),
):
    rec = db.query(MonthlyRecord).filter(MonthlyRecord.patient_id == patient_id, MonthlyRecord.record_month == month_str).first()
    if rec:
        # Update existing
        rec.access_type = access_type
        rec.target_dry_weight = target_dry_weight
        rec.idwg = idwg; rec.hb = hb
        rec.serum_ferritin = serum_ferritin; rec.tsat = tsat; rec.serum_iron = serum_iron
        rec.epo_mircera_dose = epo_mircera_dose; rec.epo_weekly_units = epo_weekly_units
        rec.calcium = calcium; rec.alkaline_phosphate = alkaline_phosphate
        rec.phosphorus = phosphorus; rec.albumin = albumin; rec.ast = ast; rec.alt = alt
        rec.vit_d = vit_d; rec.ipth = ipth; rec.av_daily_calories = av_daily_calories
        rec.av_daily_protein = av_daily_protein; rec.issues = issues; rec.entered_by = entered_by
        rec.timestamp = datetime.utcnow()
    else:
        rec = MonthlyRecord(
            patient_id=patient_id, record_month=month_str, entered_by=entered_by,
            access_type=access_type,
            target_dry_weight=target_dry_weight,
            idwg=idwg, hb=hb, serum_ferritin=serum_ferritin,
            tsat=tsat, serum_iron=serum_iron, epo_mircera_dose=epo_mircera_dose,
            epo_weekly_units=epo_weekly_units, calcium=calcium, alkaline_phosphate=alkaline_phosphate,
            phosphorus=phosphorus, albumin=albumin, ast=ast, alt=alt, vit_d=vit_d, ipth=ipth,
            av_daily_calories=av_daily_calories, av_daily_protein=av_daily_protein, issues=issues,
        )
        db.add(rec)
    
    # Also update master patient profile for real-time dashboard accuracy
    p = db.query(Patient).filter(Patient.id == patient_id).first()
    if p and access_type:
        p.access_type = access_type

    db.commit()
    return RedirectResponse(url=f"/entry?month={month_str}", status_code=303)


# ─────────────────────────────────────────────────────────────────────────────
# OTHERS
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/patients")
def api_patients(q: str = "", db: Session = Depends(get_db)):
    patients = db.query(Patient).filter(Patient.is_active == True, Patient.name.ilike(f"%{q}%")).limit(20).all()
    return [{"id": p.id, "name": p.name, "hid": p.hid_no} for p in patients]

@app.get("/patients/{patient_id}/timeline", response_class=HTMLResponse)
def patient_timeline(patient_id: int, request: Request, db: Session = Depends(get_db)):
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient: raise HTTPException(status_code=404)
    analytics = run_patient_analytics(db, patient_id)
    return templates.TemplateResponse("patient_timeline.html", {
        "request": request, "patient": patient, "analytics": analytics,
        "user": get_user(request),
    })

@app.get("/variables", response_class=HTMLResponse)
def variable_manager(request: Request, db: Session = Depends(get_db)):
    variables = get_all_variables(db, active_only=False)
    patients = db.query(Patient).filter(Patient.is_active == True).order_by(Patient.name).all()
    vars_json = [{"id": v.id, "name": v.name, "display_name": v.display_name, "unit": v.unit} for v in variables]
    return templates.TemplateResponse("variable_manager.html", {
        "request": request, "variables": variables, "variables_json": vars_json,
        "patients": [{"id": p.id, "name": p.name} for p in patients],
        "default_from": "2023-01", "default_to": get_current_month_str(),
        "user": get_user(request),
    })
