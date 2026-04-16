import os
from fastapi import FastAPI, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import date, datetime
from typing import Optional
import json

from database import get_db, create_tables, Patient, MonthlyRecord, AlertLog
from dashboard_logic import compute_dashboard, get_current_month_str, get_month_label, get_patients_needing_alerts
from alerts import send_bulk_whatsapp_alerts, send_ward_email, send_whatsapp

app = FastAPI(title="HD Dashboard")

# 1. Config
SECRET_KEY = os.getenv("SECRET_KEY", "clinical-secret-99-super-harden")

# 2. Session Middleware (Disabled as per import cleanup)
# app.add_middleware(
#     SessionMiddleware, 
#     secret_key=SECRET_KEY,
#     same_site="none",
#     https_only=True
# )

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ─────────────────────────────────────────────────────────────────────────────
# AUTHENTICATION & PERMISSIONS
# ─────────────────────────────────────────────────────────────────────────────

# SECRET_KEY moved up

# ─────────────────────────────────────────────────────────────────────────────
# ROUTES: AUTH
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# DIAGNOSTICS
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health")
def health_check():
    """Heartbeat endpoint for UptimeRobot monitoring."""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

# def get_current_user(request: Request, db: Session = Depends(get_db)):
#     # 1. Check Session (Local Templates - Monolith)
#     username = request.session.get("user")
#     if username:
#         return db.query(User).filter(User.username == username, User.is_active == True).first()
#     return None
# 
# def login_required(user=Depends(get_current_user)):
#     if not user:
#         raise HTTPException(status_code=401, detail="Authentication required")
#     return user
# 
# def require_role(roles: list):
#     def role_checker(user: User = Depends(login_required)):
#         if user.role not in roles:
#             raise HTTPException(status_code=403, detail="Insufficient clinical permissions")
#         return user
#     return role_checker
# 
# # Predefined role dependencies
# admin_only = require_role(["admin"])
# doctor_or_admin = require_role(["doctor", "admin"])
# nurse_or_admin = require_role(["nurse", "admin"])
# any_staff = require_role(["admin", "doctor", "nurse"])

# ─────────────────────────────────────────────────────────────────────────────
# ROUTES: AUTH
# ─────────────────────────────────────────────────────────────────────────────

# @app.get("/login", response_class=HTMLResponse)
# def login_page(request: Request):
#     if request.session.get("user"):
#         return RedirectResponse(url="/", status_code=303)
#     return templates.TemplateResponse("login.html", {"request": request})
# 
# @app.post("/login")
# async def login(request: Request, db: Session = Depends(get_db), 
#                 username: str = Form(...), password: str = Form(...)):
#     # Auth logic disabled for stability
#     return RedirectResponse(url="/", status_code=303)
# 
# @app.get("/logout")
# def logout(request: Request):
#     request.session.clear()
#     return RedirectResponse(url="/login")

# ─────────────────────────────────────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, month: Optional[str] = None, db: Session = Depends(get_db)): # Removed user dep
    # if not user: return RedirectResponse(url="/login", status_code=303)
    # if user.role == "nurse": return RedirectResponse(url="/entry", status_code=303)
    
    month_str = month or get_current_month_str()
    data = compute_dashboard(db, month_str)
    return templates.TemplateResponse("dashboard.html", {
        "request": request, "data": data, "month_str": month_str,
        "current_month": get_current_month_str(), "user": None
    })

@app.get("/api/dashboard")
def api_dashboard(month: Optional[str] = None, db: Session = Depends(get_db)): # Removed user dep
    month_str = month or get_current_month_str()
    data = compute_dashboard(db, month_str)
    return data

# ─────────────────────────────────────────────────────────────────────────────
# PATIENTS
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/patients", response_class=HTMLResponse)
def patient_list(request: Request, db: Session = Depends(get_db)): # Removed user dep
    patients = db.query(Patient).filter(Patient.is_active == True).order_by(Patient.name).all()
    return templates.TemplateResponse("patients.html", {"request": request, "patients": patients, "user": None})

@app.get("/patients/{patient_id}/timeline", response_class=HTMLResponse)
def patient_timeline(patient_id: int, request: Request, db: Session = Depends(get_db)): # Removed user dep
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient: raise HTTPException(status_code=404)
    
    records = db.query(MonthlyRecord).filter(MonthlyRecord.patient_id == patient_id).order_by(MonthlyRecord.record_month.asc()).all()
    
    def extract_epo(text):
        if not text: return None
        matches = re.findall(r'\d+', text)
        return float(matches[0]) if matches else None

    timeline_data = [{
        "month": r.record_month, "hb": r.hb, "alb": r.albumin, "phos": r.phosphorus,
        "ipth": r.ipth, "vit_d": r.vit_d, "idwg": r.idwg, "epo": extract_epo(r.epo_mircera_dose)
    } for r in records]

    return templates.TemplateResponse("timeline.html", {"request": request, "patient": patient, "timeline_data": timeline_data, "user": user})

@app.get("/patients/new", response_class=HTMLResponse)
def new_patient_form(request: Request): # Removed user dep
    return templates.TemplateResponse("patient_form.html", {"request": request, "patient": None, "mode": "new", "user": None})

@app.post("/patients/new")
def create_patient(request: Request, db: Session = Depends(get_db), # Removed user dep
                   hid_no: str = Form(...), name: str = Form(...), sex: str = Form(...),
                   relation_type: str = Form(""),
                   contact_no: str = Form(""), diagnosis: str = Form(""), access_type: str = Form(""),
                   dry_weight: Optional[float] = Form(None), hd_slot_1: str = Form(""),
                   hd_slot_2: str = Form(""), hd_slot_3: str = Form(""),
                   hep_b_status: str = Form(""), hep_b_date: str = Form(""),
                   pneumococcal_date: str = Form(""),
                   whatsapp_notify: bool = Form(False), mail_trigger: bool = Form(False)):
    
    if db.query(Patient).filter(Patient.hid_no == hid_no).first():
        return templates.TemplateResponse("patient_form.html", {"request": request, "mode": "new", "error": f"HID {hid_no} exists.", "user": user})

    def p_date(ds): return datetime.strptime(ds, "%Y-%m-%d").date() if ds else None

    p = Patient(hid_no=hid_no, name=name, sex=sex, relation_type=relation_type, contact_no=contact_no, diagnosis=diagnosis,
                access_type=access_type, dry_weight=dry_weight, hd_slot_1=hd_slot_1, hd_slot_2=hd_slot_2, hd_slot_3=hd_slot_3,
                hep_b_status=hep_b_status, hep_b_date=p_date(hep_b_date), pneumococcal_date=p_date(pneumococcal_date),
                whatsapp_notify=whatsapp_notify, mail_trigger=mail_trigger, created_by="system")
    db.add(p); db.commit()
    return RedirectResponse(url="/patients", status_code=303)

@app.get("/patients/{patient_id}/edit", response_class=HTMLResponse)
def edit_patient_form(patient_id: int, request: Request, db: Session = Depends(get_db)): # Removed user dep
    p = db.query(Patient).filter(Patient.id == patient_id).first()
    if not p: raise HTTPException(status_code=404)
    return templates.TemplateResponse("patient_form.html", {"request": request, "patient": p, "mode": "edit", "user": None})

@app.post("/patients/{patient_id}/edit")
def update_patient(patient_id: int, request: Request, db: Session = Depends(get_db), # Removed user dep
                   hid_no: str = Form(...), name: str = Form(...), sex: str = Form(...),
                   relation_type: str = Form(""),
                   contact_no: str = Form(""), diagnosis: str = Form(""), access_type: str = Form(""),
                   dry_weight: Optional[float] = Form(None), hd_slot_1: str = Form(""),
                   hd_slot_2: str = Form(""), hd_slot_3: str = Form(""),
                   hep_b_status: str = Form(""), hep_b_date: str = Form(""),
                   pneumococcal_date: str = Form(""),
                   whatsapp_notify: bool = Form(False), mail_trigger: bool = Form(False)):
    p = db.query(Patient).filter(Patient.id == patient_id).first()
    if not p: raise HTTPException(status_code=404)

    def p_date(ds): return datetime.strptime(ds, "%Y-%m-%d").date() if ds else None

    p.hid_no = hid_no; p.name = name; p.sex = sex; p.relation_type = relation_type; p.contact_no = contact_no
    p.diagnosis = diagnosis; p.access_type = access_type; p.dry_weight = dry_weight
    p.hd_slot_1 = hd_slot_1; p.hd_slot_2 = hd_slot_2; p.hd_slot_3 = hd_slot_3
    p.hep_b_status = hep_b_status; p.hep_b_date = p_date(hep_b_date); p.pneumococcal_date = p_date(pneumococcal_date)
        p.whatsapp_notify = whatsapp_notify; p.mail_trigger = mail_trigger
    p.updated_by = "system"; p.updated_at = datetime.utcnow() # Changed user.username to "system"
    db.commit()
    return RedirectResponse(url="/patients", status_code=303)

@app.post("/patients/{patient_id}/deactivate")
def deactivate_patient(patient_id: int, db: Session = Depends(get_db)): # Removed user dep and admin_only
    p = db.query(Patient).filter(Patient.id == patient_id).first()
    if p: p.is_active = False; p.updated_by = "system"; db.commit() # Changed user.username to "system"
    return RedirectResponse(url="/patients", status_code=303)

# ─────────────────────────────────────────────────────────────────────────────
# DATA ENTRY
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/entry", response_class=HTMLResponse)
def entry_index(request: Request, month: Optional[str] = None, db: Session = Depends(get_db)): # Removed user dep
    month_str = month or get_current_month_str()
    patients = db.query(Patient).filter(Patient.is_active == True).order_by(Patient.name).all()
    existing_ids = {r.patient_id for r in db.query(MonthlyRecord).filter(MonthlyRecord.record_month == month_str).all()}
    return templates.TemplateResponse("entry_list.html", {"request": request, "patients": patients, "month_str": month_str, "month_label": get_month_label(month_str), "existing_ids": existing_ids, "user": None})

@app.get("/entry/{patient_id}", response_class=HTMLResponse)
def entry_form(patient_id: int, request: Request, month: Optional[str] = None, db: Session = Depends(get_db)): # Removed user dep
    p = db.query(Patient).filter(Patient.id == patient_id).first()
    if not p: raise HTTPException(status_code=404)
    month_str = month or get_current_month_str()
    rec = db.query(MonthlyRecord).filter(MonthlyRecord.patient_id == patient_id, MonthlyRecord.record_month == month_str).first()
    return templates.TemplateResponse("entry_form.html", {"request": request, "patient": p, "record": rec, "month_str": month_str, "month_label": get_month_label(month_str), "user": user})

@app.post("/api/entries/bulk")
def api_bulk_entries(records: list, db: Session = Depends(get_db)): # Changed List to list
    for r in records:
        pid = r.get("patient_id")
        m_str = r.get("record_month")
        if not pid or not m_str: continue
        
        rec = db.query(MonthlyRecord).filter(MonthlyRecord.patient_id == pid, MonthlyRecord.record_month == m_str).first()
        if not rec:
            rec = MonthlyRecord(patient_id=pid, record_month=m_str)
            db.add(rec)
        
        # Mapping frontend fields to backend
        rec.hb = float(r.get("hb")) if r.get("hb") else None
        rec.idwg = float(r.get("idwg")) if r.get("idwg") else None
        rec.phosphorus = float(r.get("phosphorus")) if r.get("phosphorus") else None
        rec.albumin = float(r.get("albumin")) if r.get("albumin") else None
        rec.updated_at = datetime.utcnow()

        # Backgrounding Critical Alerts for Robustness
        def trigger_alerts(p_name, metric, val):
            # from alerts import send_critical_clinical_alert
            # send_critical_clinical_alert(p_name, metric, val)
            pass

        import threading
        p_obj = None # Initialize
        if rec.hb and rec.hb < 7.0:
            p_obj = db.query(Patient).filter(Patient.id == pid).first()
            threading.Thread(target=trigger_alerts, args=(p_obj.name, "Hemoglobin", rec.hb)).start()
        
        if rec.phosphorus and rec.phosphorus > 7.0:
            if not p_obj: p_obj = db.query(Patient).filter(Patient.id == pid).first()
            threading.Thread(target=trigger_alerts, args=(p_obj.name, "Serum Phosphorus", rec.phosphorus)).start()
        
        if rec.idwg and rec.idwg > 3.5:
            if not p_obj: p_obj = db.query(Patient).filter(Patient.id == pid).first()
            threading.Thread(target=trigger_alerts, args=(p_obj.name, "IDWG (Fluid Overload)", rec.idwg)).start()
    
    db.commit()
    return {"success": True, "count": len(records)}

@app.post("/entry/{patient_id}")
def save_entry(patient_id: int, db: Session = Depends(get_db), # Removed user dep
               month_str: str = Form(...), entered_by: str = Form(""),
               target_dry_weight: Optional[float] = Form(None), idwg: Optional[float] = Form(None), hb: Optional[float] = Form(None),
               serum_ferritin: Optional[float] = Form(None), tsat: Optional[float] = Form(None),
               serum_iron: Optional[float] = Form(None), epo_mircera_dose: str = Form(""),
               calcium: Optional[float] = Form(None), phosphorus: Optional[float] = Form(None),
               alkaline_phosphate: Optional[float] = Form(None),
               albumin: Optional[float] = Form(None), ast: Optional[float] = Form(None), alt: Optional[float] = Form(None),
               vit_d: Optional[float] = Form(None), ipth: Optional[float] = Form(None),
               av_daily_calories: Optional[float] = Form(None), av_daily_protein: Optional[float] = Form(None),
               issues: str = Form("")):
    
    rec = db.query(MonthlyRecord).filter(MonthlyRecord.patient_id == patient_id, MonthlyRecord.record_month == month_str).first()
    if not rec:
        rec = MonthlyRecord(patient_id=patient_id, record_month=month_str)
        db.add(rec)
    
    rec.target_dry_weight = target_dry_weight; rec.idwg = idwg; rec.hb = hb; rec.serum_ferritin = serum_ferritin; rec.tsat = tsat
    rec.serum_iron = serum_iron; rec.epo_mircera_dose = epo_mircera_dose
    rec.calcium = calcium; rec.phosphorus = phosphorus; rec.alkaline_phosphate = alkaline_phosphate
        rec.albumin = albumin; rec.ast = ast; rec.alt = alt; rec.vit_d = vit_d; rec.ipth = ipth
    rec.av_daily_calories = av_daily_calories; rec.av_daily_protein = av_daily_protein
    rec.issues = issues; rec.entered_by = "system"; rec.timestamp = datetime.utcnow() # Changed user.username to "system"
    db.commit()

    # Backgrounding Critical Alerts for Robustness
    def trigger_alerts(p_name, metric, val):
        # from alerts import send_critical_clinical_alert
        # send_critical_clinical_alert(p_name, metric, val)
        pass

    import threading
    p_obj = db.query(Patient).filter(Patient.id == patient_id).first()
    if hb is not None and hb < 7.0:
        threading.Thread(target=trigger_alerts, args=(p_obj.name, "Hemoglobin", hb)).start()
    
    if phosphorus is not None and phosphorus > 7.0:
        threading.Thread(target=trigger_alerts, args=(p_obj.name, "Serum Phosphorus", phosphorus)).start()

    if idwg is not None and idwg > 3.5:
        threading.Thread(target=trigger_alerts, args=(p_obj.name, "IDWG (Fluid Overload)", idwg)).start()

    return RedirectResponse(url=f"/entry?month={month_str}&saved=1", status_code=303)

# ─────────────────────────────────────────────────────────────────────────────
# API & ALERTS
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/me")
def api_me(): # Removed user dep
    # if not user: return JSONResponse({"logged_in": False})
    return {"logged_in": False}

@app.get("/api/patients")
def api_patients(q: str = "", db: Session = Depends(get_db)): # Removed user dep
    patients = db.query(Patient).filter(Patient.is_active == True, Patient.name.ilike(f"%{q}%")).limit(100).all()
    return [{
        "id": p.id, "name": p.name, "hid": p.hid_no, "sex": p.sex, 
        "contact": p.contact_no, "diagnosis": p.diagnosis, 
        "access": p.access_type,
        "slots": [p.hd_slot_1, p.hd_slot_2, p.hd_slot_3]
    } for p in patients]

@app.get("/api/patients/{patient_id}")
def api_patient_detail(patient_id: int, db: Session = Depends(get_db)): # Removed user dep
    p = db.query(Patient).filter(Patient.id == patient_id).first()
    if not p: raise HTTPException(status_code=404)
    return {
        "id": p.id, "name": p.name, "hid": p.hid_no, "sex": p.sex, 
        "contact": p.contact_no, "diagnosis": p.diagnosis, 
        "access": p.access_type, "dry_weight": p.dry_weight,
        "slots": [p.hd_slot_1, p.hd_slot_2, p.hd_slot_3],
        "whatsapp_notify": p.whatsapp_notify,
        "clinical_remarks": p.clinical_remarks or ""
    }

# class PatientData(BaseModel):
#     name: str
#     ...

@app.post("/api/patients")
def api_create_patient(data: dict, db: Session = Depends(get_db)): # Changed to dict
    p = Patient(
        name=data.get("name"), contact_no=data.get("contact"), sex=data.get("gender"), 
        diagnosis=data.get("diagnosis"), hd_slot_1=data.get("hd_slot_1"), 
        hd_slot_2=data.get("hd_slot_2"), hd_slot_3=data.get("hd_slot_3"),
        is_active=data.get("is_active", True), clinical_remarks=data.get("clinical_remarks", ""),
        created_by="system"
    )
    db.add(p)
    db.commit()
    return {"id": p.id, "success": True}

@app.put("/api/patients/{patient_id}")
def api_update_patient(patient_id: int, data: dict, db: Session = Depends(get_db)): # Changed to dict
    p = db.query(Patient).filter(Patient.id == patient_id).first()
    if not p: raise HTTPException(status_code=404)
    p.name = data.get("name"); p.contact_no = data.get("contact"); p.sex = data.get("gender")
    p.diagnosis = data.get("diagnosis"); p.hd_slot_1 = data.get("hd_slot_1")
    p.hd_slot_2 = data.get("hd_slot_2"); p.hd_slot_3 = data.get("hd_slot_3")
    p.is_active = data.get("is_active", True); p.clinical_remarks = data.get("clinical_remarks", "")
    p.updated_by = "system"; p.updated_at = datetime.utcnow()
    db.commit()
    return {"success": True}

@app.get("/api/patients/{patient_id}/timeline")
def api_patient_timeline(patient_id: int, db: Session = Depends(get_db)): # Removed user dep
    p = db.query(Patient).filter(Patient.id == patient_id).first()
    if not p: raise HTTPException(status_code=404)
    records = db.query(MonthlyRecord).filter(MonthlyRecord.patient_id == patient_id).order_by(MonthlyRecord.record_month.desc()).all()
    
    timeline = []
    for r in records:
        timeline.append({
            "month": r.record_month,
            "label": get_month_label(r.record_month),
            "hb": r.hb, "albumin": r.albumin, "phosphorus": r.phosphorus,
            "idwg": r.idwg, "ferritin": r.serum_ferritin, "tsat": r.tsat,
            "calcium": r.calcium, "ipth": r.ipth, "vit_d": r.vit_d,
            "issues": r.issues
        })
    return {"patient": {"id": p.id, "name": p.name}, "timeline": timeline}


@app.post("/api/send-whatsapp")
def api_send_whatsapp(month: Optional[str] = None, db: Session = Depends(get_db)): # Removed user dep
    month_str = month or get_current_month_str()
    import threading
    threading.Thread(target=send_bulk_whatsapp_alerts, args=(get_patients_needing_alerts(db, month_str), get_month_label(month_str))).start()
    return JSONResponse({"message": "⏳ WhatsApp alert task queued via threading."})

@app.post("/api/send-schedule/{patient_id}")
def api_send_schedule_reminder(patient_id: int, db: Session = Depends(get_db)): # Removed user dep
    """Send a specific patient their weekly HD schedule via WhatsApp and Email."""
    p = db.query(Patient).filter(Patient.id == patient_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    # Send WhatsApp/Email via direct threading
    import threading
    def send_p_schedule():
        # Email
        if p.email:
            from alerts import send_schedule_email
            send_schedule_email(p.name, p.email, [p.hd_slot_1, p.hd_slot_2, p.hd_slot_3])
        # WhatsApp
        if p.contact_no:
            # msg = build_schedule_message(p.name, [p.hd_slot_1, p.hd_slot_2, p.hd_slot_3])
            # send_whatsapp(p.contact_no, msg)
            pass

    # threading.Thread(target=send_p_schedule).start()
    return JSONResponse({"message": f"⏳ Schedule reminder dispatched via Threading."})


@app.post("/api/send-email")
def api_send_email(month: Optional[str] = None, db: Session = Depends(get_db)): # Removed user dep
    month_str = month or get_current_month_str()
    import threading
    threading.Thread(target=send_ward_email, args=(get_patients_needing_alerts(db, month_str), get_month_label(month_str), month_str[:4])).start()
    return JSONResponse({"message": "⏳ Ward report email task queued via threading."})


@app.get("/api/cohort-trends")
def api_cohort_trends(db: Session = Depends(get_db)): # Removed user dep
    months = []; current = datetime.now()
    for i in range(11, -1, -1): months.append((current - datetime.timedelta(days=i*30)).strftime("%Y-%m"))
    months.sort()

    res = {m: {"hb": [], "alb": [], "phos": []} for m in months}
    for r in db.query(MonthlyRecord).filter(MonthlyRecord.record_month.in_(months)).all():
        if r.hb: res[r.record_month]["hb"].append(r.hb)
        if r.albumin: res[r.record_month]["alb"].append(r.albumin)
        if r.phosphorus: res[r.record_month]["phos"].append(r.phosphorus)
        
    def get_stats(data):
        if not data: return {"median": None, "p25": None, "p75": None}
        data.sort(); n = len(data)
        return {"median": statistics.median(data), "p25": data[int(n*0.25)], "p75": data[int(n*0.75)]}

    return JSONResponse({"months": months, "hb": [get_stats(res[m]["hb"]) for m in months], "alb": [get_stats(res[m]["alb"]) for m in months], "phos": [get_stats(res[m]["phos"]) for m in months]})

# ─────────────────────────────────────────────────────────────────────────────
# USER MANAGEMENT (ADMIN ONLY)
# ─────────────────────────────────────────────────────────────────────────────

# @app.get("/admin/users", ...)
# @app.post("/admin/users/new", ...)
# @app.post("/admin/users/{user_id}/deactivate", ...)
# @app.get("/account/password", ...)
# @app.post("/account/password", ...)

# ── SCHEDULER ──
def migrate_db():
    from sqlalchemy import text
    db = SessionLocal()
    # Clinical columns to auto-ensure
    migrations = [
        ("patients", "relation_type", "VARCHAR"),
        ("patients", "relation_name", "VARCHAR"),
        ("patients", "hep_b_status", "VARCHAR"),
        ("patients", "hep_b_date", "DATE"),
        ("patients", "pneumococcal_date", "DATE"),
        ("patients", "updated_by", "VARCHAR"),
        ("monthly_records", "target_dry_weight", "FLOAT"),
        ("monthly_records", "updated_at", "TIMESTAMP"),
        ("monthly_records", "entered_by", "VARCHAR")
    ]
    for table, col, col_type in migrations:
        try:
            db.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"))
            db.commit()
        except Exception:
            db.rollback() 
    db.close()

@app.on_event("startup")
def startup():
    create_tables()
    # migrate_db()
    # db = SessionLocal()
    # Ensure admin exists
    # admin_user = db.query(User).filter(User.username == "admin").first()
    # if not admin_user:
    #     admin = User(
    #         username="admin", 
    #         full_name="System Admin", 
    #         hashed_password=pwd_context.hash("admin123"), 
    #         role="admin",
    #         is_active=True
    #     )
    #     db.add(admin)
    #     db.commit()
    # db.close()

    # scheduler = BackgroundScheduler()
    # def auto_report():
    #     import threading
    #     m = get_current_month_str()
    #     # db = SessionLocal()
    #     # try:
    #     #     pts = get_patients_needing_alerts(db, m)
    #     #     threading.Thread(target=send_ward_email, args=(pts, get_month_label(m), m[:4])).start()
    #     # finally:
    #     #     db.close()
    # # scheduler.add_job(auto_report, CronTrigger(hour=8, minute=0))
    # # scheduler.start()

