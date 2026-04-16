import os
from fastapi import FastAPI, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import date, datetime, timedelta
from typing import Optional
import json
import re
import statistics

from database import get_db, create_tables, Patient, MonthlyRecord, AlertLog, User
from dashboard_logic import compute_dashboard, get_current_month_str, get_month_label, get_patients_needing_alerts
from alerts import send_bulk_whatsapp_alerts, send_ward_email
from tasks import task_send_bulk_whatsapp, task_send_ward_email, task_send_schedule_reminder

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from passlib.context import CryptContext
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="HD Dashboard")

# Enable CORS for the React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all for internal clinical deployment
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Use a strong SECRET_KEY from environment in production
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "clinical-dashboard-secret-2026"))
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ─────────────────────────────────────────────────────────────────────────────
# AUTHENTICATION & PERMISSIONS
# ─────────────────────────────────────────────────────────────────────────────

def get_current_user(request: Request, db: Session = Depends(get_db)):
    """Dependency to retrieve the logged-in user or return None."""
    username = request.session.get("user")
    if not username:
        return None
    user = db.query(User).filter(User.username == username, User.is_active == True).first()
    return user

def login_required(user=Depends(get_current_user)):
    """Ensure a user is logged in, or raise 401."""
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user

def require_role(roles: list):
    """Factory for role-based access checks."""
    def role_checker(user: User = Depends(login_required)):
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient clinical permissions")
        return user
    return role_checker

# Predefined role dependencies
admin_only = require_role(["admin"])
doctor_or_admin = require_role(["doctor", "admin"])
nurse_or_admin = require_role(["nurse", "admin"])
any_staff = require_role(["admin", "doctor", "nurse"])

# ─────────────────────────────────────────────────────────────────────────────
# ROUTES: AUTH
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if request.session.get("user"):
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
def login(request: Request, db: Session = Depends(get_db), username: str = Form(...), password: str = Form(...)):
    user = db.query(User).filter(User.username == username).first()
    
    # Force JSON if it's a cross-origin request (standard for Vercel -> Render)
    origin = request.headers.get("origin", "")
    is_api_call = origin and "localhost" not in origin
    is_ajax = "application/json" in request.headers.get("accept", "")

    if not user or not pwd_context.verify(password, user.hashed_password):
        msg = "Invalid clinical credentials. Please check your username/password."
        if is_api_call or is_ajax: return JSONResponse({"success": False, "detail": msg}, status_code=401)
        return templates.TemplateResponse("login.html", {"request": request, "error": msg})
    
    if not user.is_active:
        msg = "Your clinical account has been deactivated."
        if is_api_call or is_ajax: return JSONResponse({"success": False, "detail": msg}, status_code=403)
        return templates.TemplateResponse("login.html", {"request": request, "error": msg})

    # Set session
    request.session["user"] = user.username
    request.session["role"] = user.role
    
    if is_api_call or is_ajax:
        return JSONResponse({
            "success": True, 
            "user": {"username": user.username, "role": user.role}
        })
    
    return RedirectResponse(url="/", status_code=303)

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login")

# ─────────────────────────────────────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, month: Optional[str] = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not user: return RedirectResponse(url="/login", status_code=303)
    if user.role == "nurse": return RedirectResponse(url="/entry", status_code=303)
    
    month_str = month or get_current_month_str()
    data = compute_dashboard(db, month_str)
    return templates.TemplateResponse("dashboard.html", {
        "request": request, "data": data, "month_str": month_str,
        "current_month": get_current_month_str(), "user": user
    })

@app.get("/api/dashboard")
def api_dashboard(month: Optional[str] = None, db: Session = Depends(get_db), user: User = Depends(doctor_or_admin)):
    month_str = month or get_current_month_str()
    data = compute_dashboard(db, month_str)
    return JSONResponse(content=data)

# ─────────────────────────────────────────────────────────────────────────────
# PATIENTS
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/patients", response_class=HTMLResponse)
def patient_list(request: Request, db: Session = Depends(get_db), user: User = Depends(doctor_or_admin)):
    patients = db.query(Patient).filter(Patient.is_active == True).order_by(Patient.name).all()
    return templates.TemplateResponse("patients.html", {"request": request, "patients": patients, "user": user})

@app.get("/patients/{patient_id}/timeline", response_class=HTMLResponse)
def patient_timeline(patient_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(doctor_or_admin)):
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
def new_patient_form(request: Request, user: User = Depends(admin_only)):
    return templates.TemplateResponse("patient_form.html", {"request": request, "patient": None, "mode": "new", "user": user})

@app.post("/patients/new")
def create_patient(request: Request, db: Session = Depends(get_db), user: User = Depends(admin_only),
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
                whatsapp_notify=whatsapp_notify, mail_trigger=mail_trigger, created_by=user.username)
    db.add(p); db.commit()
    return RedirectResponse(url="/patients", status_code=303)

@app.get("/patients/{patient_id}/edit", response_class=HTMLResponse)
def edit_patient_form(patient_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    p = db.query(Patient).filter(Patient.id == patient_id).first()
    if not p: raise HTTPException(status_code=404)
    return templates.TemplateResponse("patient_form.html", {"request": request, "patient": p, "mode": "edit", "user": user})

@app.post("/patients/{patient_id}/edit")
def update_patient(patient_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(admin_only),
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
    p.updated_by = user.username; p.updated_at = datetime.utcnow()
    db.commit()
    return RedirectResponse(url="/patients", status_code=303)

@app.post("/patients/{patient_id}/deactivate")
def deactivate_patient(patient_id: int, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    p = db.query(Patient).filter(Patient.id == patient_id).first()
    if p: p.is_active = False; p.updated_by = user.username; db.commit()
    return RedirectResponse(url="/patients", status_code=303)

# ─────────────────────────────────────────────────────────────────────────────
# DATA ENTRY
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/entry", response_class=HTMLResponse)
def entry_index(request: Request, month: Optional[str] = None, db: Session = Depends(get_db), user: User = Depends(nurse_or_admin)):
    month_str = month or get_current_month_str()
    patients = db.query(Patient).filter(Patient.is_active == True).order_by(Patient.name).all()
    existing_ids = {r.patient_id for r in db.query(MonthlyRecord).filter(MonthlyRecord.record_month == month_str).all()}
    return templates.TemplateResponse("entry_list.html", {"request": request, "patients": patients, "month_str": month_str, "month_label": get_month_label(month_str), "existing_ids": existing_ids, "user": user})

@app.get("/entry/{patient_id}", response_class=HTMLResponse)
def entry_form(patient_id: int, request: Request, month: Optional[str] = None, db: Session = Depends(get_db), user: User = Depends(nurse_or_admin)):
    p = db.query(Patient).filter(Patient.id == patient_id).first()
    if not p: raise HTTPException(status_code=404)
    month_str = month or get_current_month_str()
    rec = db.query(MonthlyRecord).filter(MonthlyRecord.patient_id == patient_id, MonthlyRecord.record_month == month_str).first()
    return templates.TemplateResponse("entry_form.html", {"request": request, "patient": p, "record": rec, "month_str": month_str, "month_label": get_month_label(month_str), "user": user})

@app.post("/api/entries/bulk")
def api_bulk_entries(records: List[dict], db: Session = Depends(get_db), user: User = Depends(nurse_or_admin)):
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
    
    db.commit()
    return {"success": True, "count": len(records)}

@app.post("/entry/{patient_id}")
def save_entry(patient_id: int, db: Session = Depends(get_db), user: User = Depends(nurse_or_admin),
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
    rec.issues = issues; rec.entered_by = user.username; rec.timestamp = datetime.utcnow()
    db.commit()
    return RedirectResponse(url=f"/entry?month={month_str}&saved=1", status_code=303)

# ─────────────────────────────────────────────────────────────────────────────
# API & ALERTS
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/me")
def api_me(user: User = Depends(get_current_user)):
    if not user: return JSONResponse({"logged_in": False})
    return {"logged_in": True, "username": user.username, "full_name": user.full_name, "role": user.role}

@app.get("/api/patients")
def api_patients(q: str = "", db: Session = Depends(get_db), user: User = Depends(any_staff)):
    patients = db.query(Patient).filter(Patient.is_active == True, Patient.name.ilike(f"%{q}%")).limit(20).all()
    return [{"id": p.id, "name": p.name, "hid": p.hid_no, "sex": p.sex, "contact": p.contact_no, "diagnosis": p.diagnosis, "access": p.access_type} for p in patients]

@app.get("/api/patients/{patient_id}")
def api_patient_detail(patient_id: int, db: Session = Depends(get_db), user: User = Depends(any_staff)):
    p = db.query(Patient).filter(Patient.id == patient_id).first()
    if not p: raise HTTPException(status_code=404)
    return {
        "id": p.id, "name": p.name, "hid": p.hid_no, "sex": p.sex, 
        "contact": p.contact_no, "diagnosis": p.diagnosis, 
        "access": p.access_type, "dry_weight": p.dry_weight,
        "slots": [p.hd_slot_1, p.hd_slot_2, p.hd_slot_3],
        "whatsapp_notify": p.whatsapp_notify
    }

@app.get("/api/patients/{patient_id}/timeline")
def api_patient_timeline(patient_id: int, db: Session = Depends(get_db), user: User = Depends(any_staff)):
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
def api_send_whatsapp(month: Optional[str] = None, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    month_str = month or get_current_month_str()
    task_send_bulk_whatsapp.delay(month_str)
    return JSONResponse({"message": "⏳ WhatsApp alert task queued."})



@app.post("/api/send-schedule/{patient_id}")
def api_send_schedule_reminder(patient_id: int, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    """Send a specific patient their weekly HD schedule via WhatsApp."""
    p = db.query(Patient).filter(Patient.id == patient_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    if not p.contact_no:
        return JSONResponse({"message": "❌ No contact number recorded."}, status_code=400)
    
    task_send_schedule_reminder.delay(patient_id)
    return JSONResponse({"message": f"⏳ Schedule reminder queued for {p.name}."})


@app.post("/api/send-email")
def api_send_email(month: Optional[str] = None, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    month_str = month or get_current_month_str()
    task_send_ward_email.delay(month_str)
    return JSONResponse({"message": "⏳ Ward report email task queued."})


@app.get("/api/cohort-trends")
def api_cohort_trends(db: Session = Depends(get_db), user: User = Depends(doctor_or_admin)):
    months = []; current = datetime.now()
    for i in range(11, -1, -1): months.append((current - timedelta(days=i*30)).strftime("%Y-%m"))
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

@app.get("/admin/users", response_class=HTMLResponse)
def user_management(request: Request, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    users = db.query(User).all()
    return templates.TemplateResponse("admin_users.html", {"request": request, "users": users, "user": user})

@app.post("/admin/users/new")
def create_user(request: Request, db: Session = Depends(get_db), user: User = Depends(admin_only),
                username: str = Form(...), full_name: str = Form(...), password: str = Form(...), role: str = Form(...)):
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=400, detail="Username exists")
    new_user = User(username=username, full_name=full_name, hashed_password=pwd_context.hash(password), role=role)
    db.add(new_user); db.commit()
    return RedirectResponse(url="/admin/users", status_code=303)

@app.post("/admin/users/{user_id}/deactivate")
def deactivate_user(user_id: int, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    target = db.query(User).filter(User.id == user_id).first()
    if target and target.username != user.username:
        target.is_active = False; db.commit()
    return RedirectResponse(url="/admin/users", status_code=303)

@app.get("/account/password", response_class=HTMLResponse)
def change_password_page(request: Request, user: User = Depends(login_required)):
    return templates.TemplateResponse("change_password.html", {"request": request, "user": user})

@app.post("/account/password")
def change_password(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required),
                    current_pw: str = Form(...), new_pw: str = Form(...), confirm_pw: str = Form(...)):
    if not pwd_context.verify(current_pw, user.hashed_password):
        return templates.TemplateResponse("change_password.html", {"request": request, "user": user, "error": "Incorrect current password"})
    if new_pw != confirm_pw:
        return templates.TemplateResponse("change_password.html", {"request": request, "user": user, "error": "Passwords do not match"})
    user.hashed_password = pwd_context.hash(new_pw); db.commit()
    return RedirectResponse(url="/", status_code=303)

# ── SCHEDULER ──
@app.on_event("startup")
def startup():
    create_tables()
    db = SessionLocal()
    # Ensure admin exists
    admin_user = db.query(User).filter(User.username == "admin").first()
    if not admin_user:
        admin = User(
            username="admin", 
            full_name="System Admin", 
            hashed_password=pwd_context.hash("admin123"), 
            role="admin",
            is_active=True
        )
        db.add(admin)
        db.commit()
    db.close()

    scheduler = BackgroundScheduler()
    def auto_report():
        m = get_current_month_str()
        task_send_ward_email.delay(m)
    scheduler.add_job(auto_report, CronTrigger(hour=8, minute=0))
    scheduler.start()

