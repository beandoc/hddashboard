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
from database import get_db, create_tables, Patient, MonthlyRecord, User, ClinicalEvent, engine, SessionLocal
from passlib.context import CryptContext
from itsdangerous import URLSafeSerializer

# Auth Configuration
SECRET_KEY = "HD_DASHBOARD_SECRET_SECURE_2026"
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
serializer = URLSafeSerializer(SECRET_KEY)

from dashboard_logic import compute_dashboard, get_current_month_str, get_month_label, get_patients_needing_alerts
from alerts import (send_bulk_whatsapp_alerts, send_ward_email, send_entry_alert_email,
                    build_schedule_message, build_individual_whatsapp_link, send_whatsapp)
from ml_analytics import run_patient_analytics, run_cohort_analytics
from dynamic_vars import (get_all_variables, seed_preset_variables,
                          VariableDefinition, VariableValue, upsert_variable_value,
                          get_patient_variable_history)

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
    
    # 🚨 Self-Healing Migration — auto-syncs ALL ORM model columns to the live DB.
    # Compares SQLAlchemy metadata against actual table columns; adds any missing
    # ones. No manual column lists needed — works for any future additions too.
    from database import Base
    from sqlalchemy import String, Integer, Float, Boolean, Date, DateTime, Text

    def _pg_type(col):
        """Map SQLAlchemy column type to a safe PostgreSQL DDL string."""
        t = col.type
        if isinstance(t, Boolean):   return "BOOLEAN"
        if isinstance(t, Integer):   return "INTEGER"
        if isinstance(t, Float):     return "FLOAT"
        if isinstance(t, Date):      return "DATE"
        if isinstance(t, DateTime):  return "TIMESTAMP"
        if isinstance(t, Text):      return "TEXT"
        return "VARCHAR"  # String and anything else

    inspector = inspect(engine)
    with engine.connect() as conn:
        for table_name, orm_table in Base.metadata.tables.items():
            try:
                existing_cols = {c['name'] for c in inspector.get_columns(table_name)}
            except Exception:
                continue  # table doesn't exist yet — create_all() will handle it
            for col in orm_table.columns:
                if col.name not in existing_cols:
                    ddl_type = _pg_type(col)
                    try:
                        conn.execute(text(
                            f'ALTER TABLE "{table_name}" ADD COLUMN "{col.name}" {ddl_type}'
                        ))
                        conn.commit()
                        print(f"✅ Migration: added {table_name}.{col.name} ({ddl_type})")
                    except Exception as e:
                        print(f"⚠️  Migration skip {table_name}.{col.name}: {e}")

        # Keep the users-specific defaults that need DEFAULT values
        try:
            u_existing = {c['name'] for c in inspector.get_columns('users')}
            u_missing = [
                ("last_login", "TIMESTAMP"),
                ("created_at", "TIMESTAMP DEFAULT NOW()"),
                ("full_name", "VARCHAR"),
                ("role", "VARCHAR DEFAULT 'staff'"),
                ("is_active", "BOOLEAN DEFAULT TRUE"),
            ]
            for col, dtype in u_missing:
                if col not in u_existing:
                    try:
                        conn.execute(text(f"ALTER TABLE users ADD COLUMN {col} {dtype}"))
                        conn.commit()
                    except Exception: pass
        except Exception:
            pass  # users table doesn't exist yet — create_all() will handle it


    # Create dynamic variable tables and seed presets
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_preset_variables(db)
        # Ensure default admin user exists
        admin = db.query(User).filter(User.username == "admin").first()
        if not admin:
            hashed = pwd_context.hash("admin123")
            db.add(User(username="admin", full_name="System Admin", hashed_password=hashed, role="admin"))
            db.commit()
            print("✅ Default admin user created (admin / admin123)")
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

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Simple session-based cookie middleware."""
    session_cookie = request.cookies.get("hd_session")
    request.state.user = None
    
    if session_cookie:
        try:
            username = serializer.loads(session_cookie)
            db = SessionLocal()
            user = db.query(User).filter(User.username == username, User.is_active == True).first()
            if user:
                request.state.user = user
            db.close()
        except Exception:
            pass # Invalid cookie

    # Protect all routes excpet public ones
    public_paths = ["/login", "/static", "/health"]
    if not request.state.user and request.url.path not in public_paths:
        if not any(request.url.path.startswith(p) for p in public_paths):
            return RedirectResponse(url="/login")

    response = await call_next(request)
    return response



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
                "trend_hb": [],
                "trend_albumin": [],
                "trend_phosphorus": [],
            },
            "patient_rows": [], "month_label": get_month_label(month_str),
            "prev_month_label": "N/A", "total_active": 0
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
    height: Optional[float] = Form(None),
    education_level: str = Form(""),
    healthcare_facility: str = Form(""),
    primary_renal_disease: str = Form(""),
    date_esrd_diagnosis: Optional[str] = Form(None),
    native_kidney_biopsy: str = Form(""),
    dm_status: str = Form(""),
    htn_status: bool = Form(False),
    cad_status: bool = Form(False),
    chf_status: bool = Form(False),
    history_of_stroke: bool = Form(False),
    smoking_status: str = Form(""),
    alcohol_consumption: str = Form(""),
    charlson_comorbidity_index: Optional[int] = Form(None),
    comorbidities: str = Form(""),
    drug_allergies: str = Form(""),
    dialysis_modality: str = Form(""),
    previous_krt_modality: str = Form(""),
    history_of_renal_transplant: bool = Form(False),
    transplant_prospect: str = Form(""),
    viral_markers: str = Form(""),
    viral_hbsag: str = Form(""),
    viral_anti_hcv: str = Form(""),
    viral_hiv: str = Form(""),
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
    date_first_cannulation: Optional[str] = Form(None),
    history_of_access_thrombosis: bool = Form(False),
    access_intervention_history: str = Form(""),
    catheter_type: str = Form(""),
    catheter_insertion_site: str = Form(""),
    age: Optional[int] = Form(None),
    ejection_fraction: Optional[float] = Form(None),
    dry_weight: Optional[float] = Form(None),
    hd_frequency: int = Form(2),
    hd_day_1: str = Form(""),
    hd_day_2: str = Form(""),
    hd_day_3: str = Form(""),
    hd_slot_1: str = Form(""),
    hd_slot_2: str = Form(""),
    hd_slot_3: str = Form(""),
    blood_group: str = Form(""),
    current_survival_status: str = Form(""),
    date_of_death: Optional[str] = Form(None),
    primary_cause_of_death: str = Form(""),
    withdrawal_from_dialysis: bool = Form(False),
    date_facility_transfer: Optional[str] = Form(None),
    whatsapp_notify: bool = Form(False),
    mail_trigger: bool = Form(False),
):
    existing = db.query(Patient).filter(Patient.hid_no == hid_no).first()
    if existing:
        return templates.TemplateResponse("patient_form.html", {
            "request": request, "patient": None, "mode": "new",
            "error": f"HID {hid_no} already exists.", "user": get_user(request),
        })

    def _d(s): return datetime.strptime(s, "%Y-%m-%d").date() if s else None
    _cn = re.sub(r"\D", "", contact_no.strip()) if contact_no else ""
    whatsapp_link = f"https://wa.me/91{_cn}" if len(_cn) == 10 else ""

    p = Patient(
        hid_no=hid_no, name=name, relation=relation, relation_type=relation_type,
        sex=sex, contact_no=contact_no, email=email, diagnosis=diagnosis,
        hd_wef_date=_d(hd_wef_date), height=height, education_level=education_level,
        healthcare_facility=healthcare_facility, primary_renal_disease=primary_renal_disease,
        date_esrd_diagnosis=_d(date_esrd_diagnosis), native_kidney_biopsy=native_kidney_biopsy,
        dm_status=dm_status, htn_status=htn_status, cad_status=cad_status,
        chf_status=chf_status, history_of_stroke=history_of_stroke,
        smoking_status=smoking_status, alcohol_consumption=alcohol_consumption,
        charlson_comorbidity_index=charlson_comorbidity_index,
        comorbidities=comorbidities, drug_allergies=drug_allergies,
        dialysis_modality=dialysis_modality, previous_krt_modality=previous_krt_modality,
        history_of_renal_transplant=history_of_renal_transplant,
        transplant_prospect=transplant_prospect,
        viral_markers=viral_markers, viral_hbsag=viral_hbsag,
        viral_anti_hcv=viral_anti_hcv, viral_hiv=viral_hiv,
        hep_b_status=hep_b_status,
        hep_b_dose1_date=_d(hep_b_dose1_date), hep_b_dose2_date=_d(hep_b_dose2_date),
        hep_b_dose3_date=_d(hep_b_dose3_date), hep_b_dose4_date=_d(hep_b_dose4_date),
        hep_b_titer_date=_d(hep_b_titer_date),
        pcv13_date=_d(pcv13_date), ppsv23_date=_d(ppsv23_date),
        hz_dose1_date=_d(hz_dose1_date), hz_dose2_date=_d(hz_dose2_date),
        influenza_date=_d(influenza_date),
        access_type=access_type, access_date=_d(access_date),
        date_first_cannulation=_d(date_first_cannulation),
        history_of_access_thrombosis=history_of_access_thrombosis,
        access_intervention_history=access_intervention_history,
        catheter_type=catheter_type, catheter_insertion_site=catheter_insertion_site,
        age=age, ejection_fraction=ejection_fraction if ejection_fraction is not None else 60.0,
        dry_weight=dry_weight, hd_frequency=hd_frequency,
        hd_day_1=hd_day_1, hd_day_2=hd_day_2, hd_day_3=hd_day_3,
        hd_slot_1=hd_slot_1, hd_slot_2=hd_slot_2, hd_slot_3=hd_slot_3,
        blood_group=blood_group,
        current_survival_status=current_survival_status, date_of_death=_d(date_of_death),
        primary_cause_of_death=primary_cause_of_death,
        withdrawal_from_dialysis=withdrawal_from_dialysis,
        date_facility_transfer=_d(date_facility_transfer),
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
    height: Optional[float] = Form(None),
    education_level: str = Form(""),
    healthcare_facility: str = Form(""),
    primary_renal_disease: str = Form(""),
    date_esrd_diagnosis: Optional[str] = Form(None),
    native_kidney_biopsy: str = Form(""),
    dm_status: str = Form(""),
    htn_status: bool = Form(False),
    cad_status: bool = Form(False),
    chf_status: bool = Form(False),
    history_of_stroke: bool = Form(False),
    smoking_status: str = Form(""),
    alcohol_consumption: str = Form(""),
    charlson_comorbidity_index: Optional[int] = Form(None),
    comorbidities: str = Form(""),
    drug_allergies: str = Form(""),
    dialysis_modality: str = Form(""),
    previous_krt_modality: str = Form(""),
    history_of_renal_transplant: bool = Form(False),
    transplant_prospect: str = Form(""),
    viral_markers: str = Form(""),
    viral_hbsag: str = Form(""),
    viral_anti_hcv: str = Form(""),
    viral_hiv: str = Form(""),
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
    date_first_cannulation: Optional[str] = Form(None),
    history_of_access_thrombosis: bool = Form(False),
    access_intervention_history: str = Form(""),
    catheter_type: str = Form(""),
    catheter_insertion_site: str = Form(""),
    age: Optional[int] = Form(None),
    ejection_fraction: Optional[float] = Form(None),
    dry_weight: Optional[float] = Form(None),
    hd_frequency: int = Form(2),
    hd_day_1: str = Form(""),
    hd_day_2: str = Form(""),
    hd_day_3: str = Form(""),
    hd_slot_1: str = Form(""),
    hd_slot_2: str = Form(""),
    hd_slot_3: str = Form(""),
    blood_group: str = Form(""),
    current_survival_status: str = Form(""),
    date_of_death: Optional[str] = Form(None),
    primary_cause_of_death: str = Form(""),
    withdrawal_from_dialysis: bool = Form(False),
    date_facility_transfer: Optional[str] = Form(None),
    whatsapp_notify: bool = Form(False),
    mail_trigger: bool = Form(False),
):
    p = db.query(Patient).filter(Patient.id == patient_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")

    def _d(s): return datetime.strptime(s, "%Y-%m-%d").date() if s else None

    p.hid_no = hid_no; p.name = name; p.relation = relation; p.relation_type = relation_type
    p.sex = sex; p.contact_no = contact_no; p.email = email; p.diagnosis = diagnosis
    p.hd_wef_date = _d(hd_wef_date); p.height = height; p.education_level = education_level
    p.healthcare_facility = healthcare_facility; p.primary_renal_disease = primary_renal_disease
    p.date_esrd_diagnosis = _d(date_esrd_diagnosis); p.native_kidney_biopsy = native_kidney_biopsy
    p.dm_status = dm_status; p.htn_status = htn_status; p.cad_status = cad_status
    p.chf_status = chf_status; p.history_of_stroke = history_of_stroke
    p.smoking_status = smoking_status; p.alcohol_consumption = alcohol_consumption
    p.charlson_comorbidity_index = charlson_comorbidity_index
    p.comorbidities = comorbidities; p.drug_allergies = drug_allergies
    p.dialysis_modality = dialysis_modality; p.previous_krt_modality = previous_krt_modality
    p.history_of_renal_transplant = history_of_renal_transplant
    p.transplant_prospect = transplant_prospect
    p.viral_markers = viral_markers; p.viral_hbsag = viral_hbsag
    p.viral_anti_hcv = viral_anti_hcv; p.viral_hiv = viral_hiv
    p.hep_b_status = hep_b_status
    p.hep_b_dose1_date = _d(hep_b_dose1_date); p.hep_b_dose2_date = _d(hep_b_dose2_date)
    p.hep_b_dose3_date = _d(hep_b_dose3_date); p.hep_b_dose4_date = _d(hep_b_dose4_date)
    p.hep_b_titer_date = _d(hep_b_titer_date)
    p.pcv13_date = _d(pcv13_date); p.ppsv23_date = _d(ppsv23_date)
    p.hz_dose1_date = _d(hz_dose1_date); p.hz_dose2_date = _d(hz_dose2_date)
    p.influenza_date = _d(influenza_date)
    p.access_type = access_type; p.access_date = _d(access_date)
    p.date_first_cannulation = _d(date_first_cannulation)
    p.history_of_access_thrombosis = history_of_access_thrombosis
    p.access_intervention_history = access_intervention_history
    p.catheter_type = catheter_type; p.catheter_insertion_site = catheter_insertion_site
    p.age = age; p.ejection_fraction = ejection_fraction if ejection_fraction is not None else (p.ejection_fraction or 60.0)
    p.dry_weight = dry_weight; p.hd_frequency = hd_frequency
    p.hd_day_1 = hd_day_1; p.hd_day_2 = hd_day_2; p.hd_day_3 = hd_day_3
    p.hd_slot_1 = hd_slot_1; p.hd_slot_2 = hd_slot_2; p.hd_slot_3 = hd_slot_3
    p.blood_group = blood_group
    p.current_survival_status = current_survival_status; p.date_of_death = _d(date_of_death)
    p.primary_cause_of_death = primary_cause_of_death
    p.withdrawal_from_dialysis = withdrawal_from_dialysis
    p.date_facility_transfer = _d(date_facility_transfer)
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
    """Return display_slots, this_week_dates, and effective hd_frequency."""
    from datetime import timedelta
    cutoff = date.today() - timedelta(days=7)
    shift_names = {"morning", "afternoon"}
    day_to_weekday = {
        "Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3,
        "Friday": 4, "Saturday": 5, "Sunday": 6,
    }

    # Compute Monday of the current ISO week
    today = date.today()
    week_monday = today - timedelta(days=today.weekday())

    def _week_date_for_day(day_name: str) -> str:
        wd = day_to_weekday.get(day_name)
        if wd is None:
            return ""
        d = week_monday + timedelta(days=wd)
        return d.strftime("%-d %b")  # e.g. "21 Apr"

    slots = []
    for day_raw, shift_raw in (
        (p.hd_day_1, p.hd_slot_1),
        (p.hd_day_2, p.hd_slot_2),
        (p.hd_day_3, p.hd_slot_3),
    ):
        day = (day_raw or "").strip()
        shift_raw = (shift_raw or "").strip()
        shift = shift_raw if shift_raw.lower() in shift_names else ""

        if day:
            slots.append({"day": day, "shift": shift, "date": _week_date_for_day(day)})
        elif shift:
            # Legacy: shift only, no day configured
            slots.append({"day": "", "shift": shift, "date": ""})
        else:
            # Legacy hd_slot_* with date strings
            if shift_raw:
                try:
                    slot_date = datetime.strptime(shift_raw, "%d/%m/%Y").date()
                    if slot_date >= cutoff:
                        slots.append({"day": "", "shift": "", "date": slot_date.strftime("%-d %b")})
                except ValueError:
                    slots.append({"day": "", "shift": shift_raw, "date": ""})

    freq = p.hd_frequency or len([s for s in (p.hd_slot_1, p.hd_slot_2, p.hd_slot_3) if s]) or 2
    return {"display_slots": slots, "hd_frequency": freq}


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
    idwg: Optional[float] = Form(None),
    last_prehd_weight: Optional[float] = Form(None),
    hb: Optional[float] = Form(None),
    bp_sys: Optional[float] = Form(None),
    serum_ferritin: Optional[float] = Form(None),
    tsat: Optional[float] = Form(None),
    serum_iron: Optional[float] = Form(None),
    epo_mircera_dose: str = Form(""),
    desidustat_dose: str = Form(""),
    epo_weekly_units: Optional[float] = Form(None),
    esa_type: str = Form(""),
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
    urr: Optional[float] = Form(None),
    crp: Optional[float] = Form(None),
    single_pool_ktv: Optional[float] = Form(None),
    equilibrated_ktv: Optional[float] = Form(None),
    pre_dialysis_urea: Optional[float] = Form(None),
    post_dialysis_urea: Optional[float] = Form(None),
    serum_creatinine: Optional[float] = Form(None),
    residual_urine_output: Optional[float] = Form(None),
    tibc: Optional[float] = Form(None),
    iv_iron_product: str = Form(""),
    iv_iron_dose: Optional[float] = Form(None),
    iv_iron_date: Optional[str] = Form(None),
    serum_sodium: Optional[float] = Form(None),
    serum_potassium: Optional[float] = Form(None),
    serum_bicarbonate: Optional[float] = Form(None),
    serum_uric_acid: Optional[float] = Form(None),
    total_cholesterol: Optional[float] = Form(None),
    ldl_cholesterol: Optional[float] = Form(None),
    wbc_count: Optional[float] = Form(None),
    platelet_count: Optional[float] = Form(None),
    hba1c: Optional[float] = Form(None),
    vitamin_d_analog_dose: str = Form(""),
    phosphate_binder_type: str = Form(""),
    antihypertensive_count: Optional[int] = Form(None),
    hrqol_score: Optional[float] = Form(None),
    hospitalization_this_month: bool = Form(False),
    hospitalization_date: Optional[str] = Form(None),
    hospitalization_icd_code: str = Form(""),
    issues: str = Form(""),
):
    from datetime import date as _date
    def _d(s): return datetime.strptime(s, "%Y-%m-%d").date() if s else None

    if idwg is not None and idwg > 15:
        idwg = None

    rec = db.query(MonthlyRecord).filter(
        MonthlyRecord.patient_id == patient_id,
        MonthlyRecord.record_month == month_str
    ).first()

    fields = dict(
        access_type=access_type, target_dry_weight=target_dry_weight,
        idwg=idwg, last_prehd_weight=last_prehd_weight, hb=hb, bp_sys=bp_sys,
        serum_ferritin=serum_ferritin, tsat=tsat, serum_iron=serum_iron,
        epo_mircera_dose=epo_mircera_dose, desidustat_dose=desidustat_dose,
        epo_weekly_units=epo_weekly_units, esa_type=esa_type,
        calcium=calcium, alkaline_phosphate=alkaline_phosphate, phosphorus=phosphorus,
        albumin=albumin, ast=ast, alt=alt, vit_d=vit_d, ipth=ipth,
        av_daily_calories=av_daily_calories, av_daily_protein=av_daily_protein,
        urr=urr, crp=crp, issues=issues, entered_by=entered_by,
        single_pool_ktv=single_pool_ktv, equilibrated_ktv=equilibrated_ktv,
        pre_dialysis_urea=pre_dialysis_urea, post_dialysis_urea=post_dialysis_urea,
        serum_creatinine=serum_creatinine, residual_urine_output=residual_urine_output,
        tibc=tibc, iv_iron_product=iv_iron_product, iv_iron_dose=iv_iron_dose, iv_iron_date=_d(iv_iron_date),
        serum_sodium=serum_sodium, serum_potassium=serum_potassium,
        serum_bicarbonate=serum_bicarbonate, serum_uric_acid=serum_uric_acid,
        total_cholesterol=total_cholesterol, ldl_cholesterol=ldl_cholesterol,
        wbc_count=wbc_count, platelet_count=platelet_count, hba1c=hba1c,
        vitamin_d_analog_dose=vitamin_d_analog_dose,
        phosphate_binder_type=phosphate_binder_type,
        antihypertensive_count=antihypertensive_count, hrqol_score=hrqol_score,
        hospitalization_this_month=hospitalization_this_month,
        hospitalization_date=_d(hospitalization_date),
        hospitalization_icd_code=hospitalization_icd_code,
    )

    if rec:
        for k, v in fields.items():
            setattr(rec, k, v)
        rec.timestamp = datetime.utcnow()
    else:
        rec = MonthlyRecord(patient_id=patient_id, record_month=month_str, **fields)
        db.add(rec)

    p = db.query(Patient).filter(Patient.id == patient_id).first()
    if p and access_type:
        p.access_type = access_type

    db.commit()

    # Auto-email alert if any critical flags are present (background thread)
    if p:
        from dashboard_logic import get_month_label
        _alerts_for_patient = []
        # Inline flag checks matching dashboard_logic thresholds
        _raw = (access_type or p.access_type or "").upper()
        if _raw and "AVF" not in _raw:
            _alerts_for_patient.append("Non-AVF Access")
        if idwg and idwg > 2.5:
            _alerts_for_patient.append("High IDWG")
        if albumin and albumin < 2.5:
            _alerts_for_patient.append("Low Albumin")
        _corr_ca = (calcium + 0.8 * (4.0 - albumin)) if (calcium and albumin) else calcium
        if _corr_ca and _corr_ca < 8.0:
            _alerts_for_patient.append("Low Calcium")
        if phosphorus and phosphorus > 5.5:
            _alerts_for_patient.append("High Phosphorus")
        if hb and hb < 9:
            _alerts_for_patient.append("Low Hb (<9)")
        if _alerts_for_patient:
            send_entry_alert_email(
                patient_name=p.name, hid=p.hid_no,
                month_label=get_month_label(month_str),
                alerts=_alerts_for_patient,
                labs={"hb": hb, "albumin": albumin, "phosphorus": phosphorus,
                      "corrected_ca": _corr_ca, "idwg": idwg, "ipth": ipth},
                entered_by=entered_by,
            )

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
    pt_events = (
        db.query(ClinicalEvent)
        .filter(ClinicalEvent.patient_id == patient_id)
        .order_by(ClinicalEvent.event_date.desc())
        .all()
    )
    return templates.TemplateResponse("patient_timeline.html", {
        "request": request, "patient": patient, "analytics": analytics,
        "pt_events": pt_events, "event_types": EVENT_TYPES, "event_type_groups": EVENT_TYPE_GROUPS,
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
# VARIABLE MANAGER API
# ─────────────────────────────────────────────────────────────────────────────

# Maps variable.name → MonthlyRecord column so data entered via the main form
# is visible in the Variable Manager without manual re-entry.
_VAR_TO_MONTHLY: dict[str, str] = {
    "uric_acid":               "serum_uric_acid",
    "crp":                     "crp",
    "kt_v":                    "single_pool_ktv",
    "bicarbonate":             "serum_bicarbonate",
    "systolic_bp_pre":         "bp_sys",
    "blood_transfusion_units": None,
    "intradialytic_hypotension": None,
}

def _monthly_field_values(db, field: str, patient_ids: list[int],
                           from_m: str, to_m: str) -> dict:
    """Pull {patient_id: {month: value}} from MonthlyRecord for a given column."""
    rows = db.query(MonthlyRecord).filter(
        MonthlyRecord.patient_id.in_(patient_ids),
        MonthlyRecord.record_month >= from_m,
        MonthlyRecord.record_month <= to_m,
    ).all()
    out: dict = {}
    for r in rows:
        v = getattr(r, field, None)
        if v is not None:
            out.setdefault(r.patient_id, {})[r.record_month] = v
    return out


@app.post("/api/variables")
def api_create_variable(payload: dict, db: Session = Depends(get_db)):
    existing = db.query(VariableDefinition).filter(
        VariableDefinition.name == payload.get("name")
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Variable name already exists")
    vdef = VariableDefinition(**{k: v for k, v in payload.items()
                                  if hasattr(VariableDefinition, k)})
    db.add(vdef)
    db.commit()
    db.refresh(vdef)
    return {"id": vdef.id, "name": vdef.name}


@app.put("/api/variables/{var_id}")
def api_update_variable(var_id: int, payload: dict, db: Session = Depends(get_db)):
    vdef = db.query(VariableDefinition).filter(VariableDefinition.id == var_id).first()
    if not vdef:
        raise HTTPException(status_code=404, detail="Variable not found")
    for k, v in payload.items():
        if hasattr(vdef, k) and k not in ("id", "created_at"):
            setattr(vdef, k, v)
    db.commit()
    return {"ok": True}


@app.post("/api/variables/{var_id}/toggle")
def api_toggle_variable(var_id: int, db: Session = Depends(get_db)):
    vdef = db.query(VariableDefinition).filter(VariableDefinition.id == var_id).first()
    if not vdef:
        raise HTTPException(status_code=404, detail="Variable not found")
    vdef.is_active = not vdef.is_active
    db.commit()
    return {"is_active": vdef.is_active}


@app.get("/api/variables/{var_id}/values")
def api_get_variable_values(var_id: int, request: Request,
                             db: Session = Depends(get_db)):
    # JS sends ?from=YYYY-MM&to=YYYY-MM; "from" is a Python keyword so we read
    # directly from query_params instead of declaring it as a parameter.
    from_m = request.query_params.get("from", "2023-01")
    to_m   = request.query_params.get("to", get_current_month_str())

    vdef = db.query(VariableDefinition).filter(VariableDefinition.id == var_id).first()
    if not vdef:
        raise HTTPException(status_code=404, detail="Variable not found")

    patients = db.query(Patient).filter(Patient.is_active == True).all()
    pid_list = [p.id for p in patients]

    rows = db.query(VariableValue).filter(
        VariableValue.variable_id == var_id,
        VariableValue.patient_id.in_(pid_list),
        VariableValue.record_month >= from_m,
        VariableValue.record_month <= to_m,
    ).all()
    result: dict = {}
    for r in rows:
        result.setdefault(r.patient_id, {})[r.record_month] = r.value_num

    monthly_field = _VAR_TO_MONTHLY.get(vdef.name)
    if monthly_field:
        bridged = _monthly_field_values(db, monthly_field, pid_list, from_m, to_m)
        for pid, months in bridged.items():
            for month, val in months.items():
                result.setdefault(pid, {}).setdefault(month, val)

    return result


@app.post("/api/variables/value")
def api_upsert_value(payload: dict, db: Session = Depends(get_db)):
    upsert_variable_value(
        db,
        patient_id=int(payload["patient_id"]),
        month_str=payload["record_month"],
        variable_id=int(payload["variable_id"]),
        value_num=payload.get("value_num"),
        value_text=payload.get("value_text"),
        entered_by=payload.get("entered_by", ""),
    )
    return {"ok": True}


@app.get("/api/variables/{var_id}/summary")
def api_variable_summary(var_id: int, db: Session = Depends(get_db)):
    vdef = db.query(VariableDefinition).filter(VariableDefinition.id == var_id).first()
    if not vdef:
        raise HTTPException(status_code=404, detail="Variable not found")

    patients = db.query(Patient).filter(Patient.is_active == True).order_by(Patient.name).all()
    pid_list = [p.id for p in patients]

    # Collect all values: EAV first, bridge MonthlyRecord
    all_data: dict = {}  # {patient_id: {month: value}}
    rows = db.query(VariableValue).filter(
        VariableValue.variable_id == var_id,
        VariableValue.patient_id.in_(pid_list),
    ).all()
    for r in rows:
        all_data.setdefault(r.patient_id, {})[r.record_month] = r.value_num

    monthly_field = _VAR_TO_MONTHLY.get(vdef.name)
    if monthly_field:
        bridged = _monthly_field_values(db, monthly_field, pid_list, "2020-01",
                                        get_current_month_str())
        for pid, months in bridged.items():
            for month, val in months.items():
                all_data.setdefault(pid, {}).setdefault(month, val)

    # Per-patient latest value
    patient_rows = []
    for p in patients:
        months = all_data.get(p.id, {})
        latest = months[max(months)] if months else None
        patient_rows.append({
            "id": p.id, "name": p.name, "hid": p.hid_no, "latest_value": latest
        })

    # Cohort trend: per month median/p25/p75
    month_buckets: dict = {}
    for pid, months in all_data.items():
        for m, v in months.items():
            if v is not None:
                month_buckets.setdefault(m, []).append(v)

    def _pct(sorted_vals, p):
        n = len(sorted_vals)
        if n == 0:
            return None
        idx = (p / 100) * (n - 1)
        lo, hi = int(idx), min(int(idx) + 1, n - 1)
        return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (idx - lo)

    trend = []
    for m in sorted(month_buckets):
        vals = sorted(month_buckets[m])
        trend.append({
            "month": m,
            "median": round(_pct(vals, 50), 2),
            "p25":    round(_pct(vals, 25), 2),
            "p75":    round(_pct(vals, 75), 2),
        })

    return {"patients": patient_rows, "trend": trend}


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


# ─────────────────────────────────────────────────────────────────────────────
# CLINICAL EVENTS TIMELINE
# ─────────────────────────────────────────────────────────────────────────────

EVENT_TYPE_GROUPS = [
    ("Intradialytic Complications", [
        "Intradialytic Hypotension",
        "Fever / Rigors",
        "Cramps",
        "Nausea / Vomiting",
        "Chest Pain",
        "Headache / Dizziness",
        "Needle Dislodgement",
        "Circuit Clot / Clotted Lines",
        "Air Embolism",
        "Cardiac Arrest",
        "Seizure",
        "Anaphylaxis / Allergic Reaction",
    ]),
    ("Vascular Access", [
        "Access Thrombosis",
        "AV Fistula Revision",
        "AV Fistula Failure",
        "Catheter Change",
        "Catheter / Exit-Site Infection",
    ]),
    ("Systemic / Hospitalizations", [
        "Hospitalization",
        "Fluid Overload",
        "Blood Transfusion",
        "Sepsis / Bacteremia",
        "Cardiac Event",
        "EPO Hyporesponse",
    ]),
    ("Administrative", [
        "Missed Sessions",
        "Transfer",
        "Transplant",
        "Fall / Injury",
        "Death",
        "Other",
    ]),
]
EVENT_TYPES = [et for _, ets in EVENT_TYPE_GROUPS for et in ets]

@app.get("/events", response_class=HTMLResponse)
def events_timeline(
    request: Request,
    date_from: Optional[str] = None,
    date_to:   Optional[str] = None,
    event_type: Optional[str] = None,
    severity:   Optional[str] = None,
    patient_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    from datetime import timedelta
    today = date.today()

    # Default: last 90 days
    d_from = date.fromisoformat(date_from) if date_from else today - timedelta(days=90)
    d_to   = date.fromisoformat(date_to)   if date_to   else today

    q = db.query(ClinicalEvent).filter(
        ClinicalEvent.event_date >= d_from,
        ClinicalEvent.event_date <= d_to,
    )
    if event_type:
        q = q.filter(ClinicalEvent.event_type == event_type)
    if severity:
        q = q.filter(ClinicalEvent.severity == severity)
    if patient_id:
        q = q.filter(ClinicalEvent.patient_id == patient_id)

    events = q.order_by(ClinicalEvent.event_date.desc()).all()

    # Summary counts
    sev_counts = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0}
    type_counts: dict = {}
    for ev in events:
        sev_counts[ev.severity] = sev_counts.get(ev.severity, 0) + 1
        type_counts[ev.event_type] = type_counts.get(ev.event_type, 0) + 1

    patients = db.query(Patient).filter(Patient.is_active == True).order_by(Patient.name).all()

    return templates.TemplateResponse("events.html", {
        "request":     request,
        "events":      events,
        "patients":    patients,
        "event_types":       EVENT_TYPES,
        "event_type_groups": EVENT_TYPE_GROUPS,
        "sev_counts":  sev_counts,
        "type_counts": type_counts,
        "date_from":   d_from.isoformat(),
        "date_to":     d_to.isoformat(),
        "filter_type": event_type or "",
        "filter_sev":  severity or "",
        "filter_pid":  patient_id or "",
        "total":       len(events),
        "today":       today.isoformat(),
        "user":        get_user(request),
    })


@app.post("/events/new")
def create_event(
    request:    Request,
    patient_id: int          = Form(...),
    event_date: str          = Form(...),
    event_type: str          = Form(...),
    severity:   str          = Form("Medium"),
    notes:      str          = Form(""),
    db:         Session      = Depends(get_db),
):
    ev = ClinicalEvent(
        patient_id = patient_id,
        event_date = date.fromisoformat(event_date),
        event_type = event_type,
        severity   = severity,
        notes      = notes.strip(),
        created_by = (get_user(request).username if get_user(request) else ""),
    )
    db.add(ev)
    db.commit()
    # Return to referring page (events list or patient timeline)
    ref = request.headers.get("referer", "/events")
    return RedirectResponse(url=ref, status_code=303)


@app.post("/events/{event_id}/delete")
def delete_event(event_id: int, request: Request, db: Session = Depends(get_db)):
    ev = db.query(ClinicalEvent).filter(ClinicalEvent.id == event_id).first()
    if ev:
        db.delete(ev)
        db.commit()
    ref = request.headers.get("referer", "/events")
    return RedirectResponse(url=ref, status_code=303)


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
        def _slot_label(day, shift):
            parts = [p for p in [day or "", shift or ""] if p]
            return " – ".join(parts) if parts else ""
        slots = [
            _slot_label(p.hd_day_1, p.hd_slot_1),
            _slot_label(p.hd_day_2, p.hd_slot_2),
            _slot_label(p.hd_day_3, p.hd_slot_3),
        ]
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
# ─────────────────────────────────────────────────────────────────────────────
# ADMIN — USER MANAGEMENT
# ─────────────────────────────────────────────────────────────────────────────

def _require_admin(request: Request):
    user = get_user(request)
    if not user or user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required.")
    return user

@app.get("/admin/users", response_class=HTMLResponse)
def admin_users(request: Request, db: Session = Depends(get_db)):
    _require_admin(request)
    users = db.query(User).order_by(User.created_at).all()
    return templates.TemplateResponse("admin_users.html", {
        "request": request,
        "users": users,
        "user": get_user(request),
    })

@app.post("/admin/users/create")
def admin_create_user(
    request: Request, db: Session = Depends(get_db),
    username: str = Form(...),
    full_name: str = Form(""),
    password: str = Form(...),
    role: str = Form("staff"),
):
    _require_admin(request)
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=400, detail=f"Username '{username}' already exists.")
    db.add(User(
        username=username, full_name=full_name,
        hashed_password=pwd_context.hash(password), role=role,
    ))
    db.commit()
    return RedirectResponse(url="/admin/users", status_code=303)

@app.post("/admin/users/{user_id}/reset-password")
def admin_reset_password(
    user_id: int, request: Request, db: Session = Depends(get_db),
    new_password: str = Form(...),
):
    _require_admin(request)
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404)
    u.hashed_password = pwd_context.hash(new_password)
    db.commit()
    return RedirectResponse(url="/admin/users", status_code=303)

@app.post("/admin/users/{user_id}/toggle")
def admin_toggle_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    admin = _require_admin(request)
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404)
    if u.id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot deactivate your own account.")
    u.is_active = not u.is_active
    db.commit()
    return RedirectResponse(url="/admin/users", status_code=303)


@app.get("/admin/test-email")
def admin_test_email(request: Request):
    """Send a test alert email to DOCTOR_EMAIL to verify SMTP config."""
    _require_admin(request)
    from alerts import send_entry_alert_email, SMTP_USER, SMTP_PASSWORD, DOCTOR_EMAIL
    if not SMTP_PASSWORD:
        return JSONResponse({"status": "error",
                             "message": "SMTP_PASSWORD not set in Render environment variables."})
    send_entry_alert_email(
        patient_name="Test Patient (John Doe)",
        hid="TEST-001",
        month_label="April 2026",
        alerts=["Low Hb (<9)", "High Phosphorus", "Low Albumin"],
        labs={"hb": 7.8, "albumin": 2.1, "phosphorus": 6.2,
              "corrected_ca": 7.9, "idwg": 2.8, "ipth": 420},
        entered_by="admin-test",
    )
    return JSONResponse({"status": "ok",
                         "message": f"Test email fired from {SMTP_USER} → {DOCTOR_EMAIL}. Check inbox (may take ~30 sec)."})


# ─────────────────────────────────────────────────────────────────────────────
# AUTHENTICATION
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, error: str = None):
    return templates.TemplateResponse("login.html", {"request": request, "error": error})

@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username, User.is_active == True).first()
    if not user or not pwd_context.verify(password, user.hashed_password):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid username or password"})
    
    user.last_login = datetime.utcnow()
    db.commit()
    
    response = RedirectResponse(url="/", status_code=303)
    # Sign the session cookie
    token = serializer.dumps(user.username)
    response.set_cookie(key="hd_session", value=token, httponly=True)
    return response

@app.get("/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("hd_session")
    return response

@app.get("/api/me")
def get_current_user_api(request: Request):
    user = get_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"username": user.username, "full_name": user.full_name, "role": user.role}
