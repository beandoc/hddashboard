"""
HD Dashboard — FastAPI Application
Multi-user hemodialysis patient data entry + clinical dashboard
"""
import re
from fastapi import FastAPI, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import text, inspect
from datetime import date, datetime
from typing import Optional

# Database engine and session for startup logic
from database import get_db, create_tables, Patient, MonthlyRecord, engine, SessionLocal
from dashboard_logic import compute_dashboard, get_current_month_str, get_month_label, get_patients_needing_alerts
from alerts import (send_bulk_whatsapp_alerts, send_ward_email,
                    build_schedule_message, build_individual_whatsapp_link, send_whatsapp)
from ml_analytics import run_patient_analytics, run_cohort_analytics
from dynamic_vars import (get_all_variables, seed_preset_variables)

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
            ("hep_b_dose1_date", "DATE"),
            ("hep_b_dose2_date", "DATE"),
            ("hep_b_dose3_date", "DATE"),
            ("hep_b_dose4_date", "DATE"),
            ("hep_b_titer_date", "DATE"),
            ("pcv13_date", "DATE"),
            ("ppsv23_date", "DATE"),
            ("hz_dose1_date", "DATE"),
            ("hz_dose2_date", "DATE"),
            ("influenza_date", "DATE"),
            ("hd_frequency", "INTEGER"),
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

    # ── Retrospective Data Sync ───────────────────────────────────────────────
    # Runs on every boot — safely skips records that already exist.
    # Populates production PostgreSQL with all historical monthly records.
    try:
        import push_historic_data
        push_historic_data.run()
        print("✅ Retrospective data sync complete.")
    except Exception as e:
        print(f"⚠️  Retrospective sync skipped: {e}")

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
                "total_patients": {"count": 0, "names": []},
                "male_patients": {"count": 0, "names": []},
                "female_patients": {"count": 0, "names": []},
                "non_avf": {"count": 0, "names": []},
                "idwg_high": {"count": 0, "names": []},
                "albumin_low": {"count": 0, "names": []},
                "calcium_low": {"count": 0, "names": []},
                "phos_high": {"count": 0, "names": []},
                "epo_hypo": {"count": 0, "names": []},
                "iv_iron_rec": {"count": 0, "names": []},
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
    hep_b_dose1_date: Optional[str] = Form(None),
    hep_b_dose2_date: Optional[str] = Form(None),
    hep_b_dose3_date: Optional[str] = Form(None),
    hep_b_dose4_date: Optional[str] = Form(None),
    hep_b_titer_date: Optional[str] = Form(None),
    pcv13_date: Optional[str] = Form(None),
    ppsv23_date: Optional[str] = Form(None),
    hz_dose1_date: Optional[str] = Form(None),
    hz_dose2_date: Optional[str] = Form(None),
    influenza_date: Optional[str] = Form(None),
    access_type: str = Form(""),
    access_date: Optional[str] = Form(None),
    dry_weight: Optional[float] = Form(None),
    hd_frequency: int = Form(2),
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

    def _d(s): return datetime.strptime(s, "%Y-%m-%d").date() if s else None
    _cn = re.sub(r"\D", "", contact_no.strip()) if contact_no else ""
    whatsapp_link = f"https://wa.me/91{_cn}" if len(_cn) == 10 else ""

    p = Patient(
        hid_no=hid_no, name=name, relation=relation, relation_type=relation_type,
        sex=sex, contact_no=contact_no, email=email, diagnosis=diagnosis,
        hd_wef_date=_d(hd_wef_date), viral_markers=viral_markers, hep_b_status=hep_b_status,
        hep_b_dose1_date=_d(hep_b_dose1_date), hep_b_dose2_date=_d(hep_b_dose2_date),
        hep_b_dose3_date=_d(hep_b_dose3_date), hep_b_dose4_date=_d(hep_b_dose4_date),
        hep_b_titer_date=_d(hep_b_titer_date),
        pcv13_date=_d(pcv13_date), ppsv23_date=_d(ppsv23_date),
        hz_dose1_date=_d(hz_dose1_date), hz_dose2_date=_d(hz_dose2_date),
        influenza_date=_d(influenza_date),
        access_type=access_type, access_date=_d(access_date),
        dry_weight=dry_weight, hd_frequency=hd_frequency,
        hd_slot_1=hd_slot_1, hd_slot_2=hd_slot_2, hd_slot_3=hd_slot_3,
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
    hep_b_dose1_date: Optional[str] = Form(None),
    hep_b_dose2_date: Optional[str] = Form(None),
    hep_b_dose3_date: Optional[str] = Form(None),
    hep_b_dose4_date: Optional[str] = Form(None),
    hep_b_titer_date: Optional[str] = Form(None),
    pcv13_date: Optional[str] = Form(None),
    ppsv23_date: Optional[str] = Form(None),
    hz_dose1_date: Optional[str] = Form(None),
    hz_dose2_date: Optional[str] = Form(None),
    influenza_date: Optional[str] = Form(None),
    access_type: str = Form(""),
    access_date: Optional[str] = Form(None),
    dry_weight: Optional[float] = Form(None),
    hd_frequency: int = Form(2),
    hd_slot_1: str = Form(""),
    hd_slot_2: str = Form(""),
    hd_slot_3: str = Form(""),
    whatsapp_notify: bool = Form(False),
    mail_trigger: bool = Form(False),
):
    p = db.query(Patient).filter(Patient.id == patient_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")

    def _d(s): return datetime.strptime(s, "%Y-%m-%d").date() if s else None

    p.hid_no = hid_no; p.name = name; p.relation = relation; p.relation_type = relation_type
    p.sex = sex; p.contact_no = contact_no; p.email = email; p.diagnosis = diagnosis
    p.hd_wef_date = _d(hd_wef_date)
    p.viral_markers = viral_markers; p.hep_b_status = hep_b_status
    p.hep_b_dose1_date = _d(hep_b_dose1_date); p.hep_b_dose2_date = _d(hep_b_dose2_date)
    p.hep_b_dose3_date = _d(hep_b_dose3_date); p.hep_b_dose4_date = _d(hep_b_dose4_date)
    p.hep_b_titer_date = _d(hep_b_titer_date)
    p.pcv13_date = _d(pcv13_date); p.ppsv23_date = _d(ppsv23_date)
    p.hz_dose1_date = _d(hz_dose1_date); p.hz_dose2_date = _d(hz_dose2_date)
    p.influenza_date = _d(influenza_date)
    p.access_type = access_type; p.access_date = _d(access_date)
    p.dry_weight = dry_weight; p.hd_frequency = hd_frequency
    p.hd_slot_1 = hd_slot_1; p.hd_slot_2 = hd_slot_2; p.hd_slot_3 = hd_slot_3
    _cn = re.sub(r"\D", "", contact_no.strip()) if contact_no else ""
    p.whatsapp_link = f"https://wa.me/91{_cn}" if len(_cn) == 10 else ""
    p.whatsapp_notify = whatsapp_notify; p.mail_trigger = mail_trigger
    p.updated_at = datetime.utcnow()

    db.commit()
    return RedirectResponse(url="/patients", status_code=303)


# ─────────────────────────────────────────────────────────────────────────────
# MONTHLY DATA ENTRY
# ─────────────────────────────────────────────────────────────────────────────

def _build_patient_slot_info(p) -> dict:
    """Return display_slots (shift names only, no stale dates) and effective hd_frequency."""
    from datetime import timedelta
    cutoff = date.today() - timedelta(days=7)
    shift_names = {"morning", "afternoon"}
    clean_slots = []
    for raw in (p.hd_slot_1, p.hd_slot_2, p.hd_slot_3):
        if not raw:
            continue
        val = raw.strip()
        if val.lower() in shift_names:
            clean_slots.append(val)
        else:
            # Try parsing as DD/MM/YYYY legacy date — only keep if within last week
            try:
                slot_date = datetime.strptime(val, "%d/%m/%Y").date()
                if slot_date >= cutoff:
                    clean_slots.append(val)
            except ValueError:
                clean_slots.append(val)  # unknown format — show as-is
    freq = p.hd_frequency or len([s for s in (p.hd_slot_1, p.hd_slot_2, p.hd_slot_3) if s]) or 2
    return {"display_slots": clean_slots, "hd_frequency": freq}


@app.get("/entry", response_class=HTMLResponse)
def entry_index(request: Request, month: Optional[str] = None, db: Session = Depends(get_db)):
    month_str = month or get_current_month_str()
    patients = db.query(Patient).filter(Patient.is_active == True).order_by(Patient.name).all()
    existing_ids = {r.patient_id for r in db.query(MonthlyRecord).filter(MonthlyRecord.record_month == month_str).all()}
    patient_slot_info = {p.id: _build_patient_slot_info(p) for p in patients}
    return templates.TemplateResponse("entry_list.html", {
        "request": request,
        "patients": patients,
        "patient_slot_info": patient_slot_info,
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
    patient_id: int, db: Session = Depends(get_db),
    month_str: str = Form(...),
    entered_by: str = Form(""),
    access_type: str = Form(""),
    target_dry_weight: Optional[float] = Form(None),
    idwg: Optional[float] = Form(None), hb: Optional[float] = Form(None),
    bp_sys: Optional[float] = Form(None),
    serum_ferritin: Optional[float] = Form(None), tsat: Optional[float] = Form(None),
    serum_iron: Optional[float] = Form(None), epo_mircera_dose: str = Form(""),
    epo_weekly_units: Optional[float] = Form(None), calcium: Optional[float] = Form(None),
    alkaline_phosphate: Optional[float] = Form(None), phosphorus: Optional[float] = Form(None),
    albumin: Optional[float] = Form(None), ast: Optional[float] = Form(None),
    alt: Optional[float] = Form(None), vit_d: Optional[float] = Form(None),
    ipth: Optional[float] = Form(None), av_daily_calories: Optional[float] = Form(None),
    av_daily_protein: Optional[float] = Form(None), urr: Optional[float] = Form(None),
    crp: Optional[float] = Form(None),
    issues: str = Form(""),
):
    if idwg is not None and idwg > 15:
        idwg = None
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
        rec.av_daily_protein = av_daily_protein; rec.urr = urr; rec.issues = issues; rec.entered_by = entered_by
        rec.bp_sys = bp_sys; rec.crp = crp
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
            av_daily_calories=av_daily_calories, av_daily_protein=av_daily_protein, urr=urr, issues=issues,
            bp_sys=bp_sys, crp=crp,
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


# ─────────────────────────────────────────────────────────────────────────────
# API ENDPOINTS (for JS polling)
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/dashboard")
def api_dashboard(month: Optional[str] = None, db: Session = Depends(get_db)):
    month_str = month or get_current_month_str()
    try:
        data = compute_dashboard(db, month_str)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return JSONResponse(content=data)


@app.get("/api/cohort-trends")
def api_cohort_trends(db: Session = Depends(get_db)):
    try:
        data = run_cohort_analytics(db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return JSONResponse(content=data)


@app.get("/whatsapp-links", response_class=HTMLResponse)
def whatsapp_links_page(month: Optional[str] = None, request: Request = None,
                         db: Session = Depends(get_db)):
    month_str = month or get_current_month_str()
    month_label = get_month_label(month_str)
    alert_patients = get_patients_needing_alerts(db, month_str)

    # Alert links — one per patient, includes labs + schedule + remarks
    alert_links = []
    for ap in alert_patients:
        p = ap["patient"]
        rec_obj = db.query(MonthlyRecord).filter(
            MonthlyRecord.patient_id == p.id,
            MonthlyRecord.record_month == month_str
        ).first()
        link = build_individual_whatsapp_link(p, rec_obj, month_label)
        alert_links.append({
            "name": p.name, "hid": p.hid_no, "contact": p.contact_no,
            "alerts": ap["alerts"], "link": link,
        })

    # Schedule links — all active patients with contact number
    active = db.query(Patient).filter(Patient.is_active == True).order_by(Patient.name).all()
    schedule_links = []
    for p in active:
        if not p.contact_no:
            continue
        rec_obj = db.query(MonthlyRecord).filter(
            MonthlyRecord.patient_id == p.id,
            MonthlyRecord.record_month == month_str
        ).first()
        slots = [p.hd_slot_1, p.hd_slot_2, p.hd_slot_3]
        remarks = (rec_obj.issues or "") if rec_obj else ""
        msg = build_schedule_message(p.name, slots, remarks)
        _, link = send_whatsapp(p.contact_no, msg)
        schedule_links.append({
            "name": p.name, "hid": p.hid_no, "contact": p.contact_no,
            "slots": [s for s in slots if s],
            "remarks": remarks, "link": link,
        })

    return templates.TemplateResponse("whatsapp_links.html", {
        "request": request, "alert_links": alert_links,
        "schedule_links": schedule_links, "month_str": month_str,
        "month_label": month_label, "user": get_user(request),
    })


@app.get("/api/wa-link/{patient_id}")
def api_wa_link(patient_id: int, month: Optional[str] = None,
                db: Session = Depends(get_db)):
    """Return a one-to-one wa.me link for a single patient (dashboard row button)."""
    p = db.query(Patient).filter(Patient.id == patient_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")
    if not p.contact_no:
        raise HTTPException(status_code=400, detail="No contact number on file")
    month_str = month or get_current_month_str()
    month_label = get_month_label(month_str)
    rec_obj = db.query(MonthlyRecord).filter(
        MonthlyRecord.patient_id == patient_id,
        MonthlyRecord.record_month == month_str
    ).first()
    link = build_individual_whatsapp_link(p, rec_obj, month_label)
    return JSONResponse(content={"url": link})


@app.post("/api/send-whatsapp")
def api_send_whatsapp(month: Optional[str] = None, db: Session = Depends(get_db)):
    month_str = month or get_current_month_str()
    try:
        patients = get_patients_needing_alerts(db, month_str)
        result = send_bulk_whatsapp_alerts(patients, get_month_label(month_str))
        return JSONResponse(content={"message": result.get("message", "✅ Done.")})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/send-email")
def api_send_email(month: Optional[str] = None, db: Session = Depends(get_db)):
    month_str = month or get_current_month_str()
    try:
        patients = get_patients_needing_alerts(db, month_str)
        success, detail = send_ward_email(patients, get_month_label(month_str), month_str[:4])
        if not success:
            raise HTTPException(status_code=500, detail=detail)
        return JSONResponse(content={"message": f"✅ {detail}"})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
