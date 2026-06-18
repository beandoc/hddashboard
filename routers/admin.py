from fastapi import APIRouter, Depends, Request, Form, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import text, func, cast, Date as SADate
from sqlalchemy.exc import IntegrityError
from typing import Optional
import json
import logging
import re
import secrets

from datetime import date, datetime, timedelta
from database import (
    get_db, User, Patient, MonthlyRecord, SessionRecord, InterimLabRecord,
    ClinicalEvent, HospitalisationEvent, engine,
)
from config import templates, pwd_context
from dependencies import get_user, _require_admin

logger = logging.getLogger(__name__)

_ALLOWED_MIGRATION_TABLES = frozenset({
    "session_records", "patient_symptom_reports", "patients", "monthly_records",
})
_ALLOWED_SQL_TYPES = frozenset({
    "INTEGER", "FLOAT", "TEXT", "VARCHAR", "DATE",
    "BOOLEAN", "BOOLEAN DEFAULT FALSE", "BOOLEAN DEFAULT TRUE",
})
_SAFE_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")

def _safe_alter_table(conn, table: str, col: str, col_type: str) -> None:
    if table not in _ALLOWED_MIGRATION_TABLES:
        raise ValueError(f"table '{table}' not in migration allowlist")
    if not _SAFE_IDENTIFIER.match(col):
        raise ValueError(f"column name '{col}' contains unsafe characters")
    if col_type.upper() not in _ALLOWED_SQL_TYPES:
        raise ValueError(f"SQL type '{col_type}' not in allowlist")
    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"))

router = APIRouter(prefix="/admin", tags=["admin"])

@router.get("/system", response_class=HTMLResponse)
async def admin_system(request: Request):
    """Consolidated system admin page: ML model management + schema migration."""
    _require_admin(request)
    return templates.TemplateResponse("admin_system.html", {
        "request": request,
        "user": get_user(request),
        "migration_results": None,
    })

@router.get("/run-migration", response_class=HTMLResponse)
async def run_pds_migration(request: Request, db: Session = Depends(get_db)):
    """Triggers the PDS schema migration. Useful for Render free tier."""
    _require_admin(request)
    
    from database import Base, PatientReminder
    results = []
    try:
        Base.metadata.create_all(bind=engine)
        results.append("✅ Ensured all tables exist (PatientReminder, etc.)")
    except Exception as e:
        results.append(f"⚠️ Table creation: {str(e)}")
    
    # Columns to add to session_records
    session_cols = [
        ("intradialytic_exercise_mins", "INTEGER"),
        ("intradialytic_meals_eaten", "BOOLEAN DEFAULT FALSE")
    ]
    
    # Columns to add to patient_symptom_reports
    symptom_cols = [
        ("session_id", "INTEGER"),
        ("dialysis_recovery_time_mins", "INTEGER"),
        ("tiredness_score", "INTEGER"),
        ("energy_level_score", "INTEGER"),
        ("daily_activity_impact", "INTEGER"),
        ("cognitive_alertness", "VARCHAR"),
        ("post_hd_mood", "VARCHAR"),
        ("sleepiness_severity", "INTEGER"),
        ("missed_social_or_work_event", "BOOLEAN DEFAULT FALSE")
    ]

    with engine.connect() as conn:
        # 1. Update session_records
        for col, col_type in session_cols:
            try:
                _safe_alter_table(conn, "session_records", col, col_type)
                conn.commit()
                results.append(f"✅ Added {col} to session_records")
            except Exception as e:
                results.append(f"⚠️ {col} (session): {str(e)[:50]}...")

        # 2. Update patient_symptom_reports
        for col, col_type in symptom_cols:
            try:
                _safe_alter_table(conn, "patient_symptom_reports", col, col_type)
                conn.commit()
                results.append(f"✅ Added {col} to patient_symptom_reports")
            except Exception as e:
                results.append(f"⚠️ {col} (symptom): {str(e)[:50]}...")

        # 3. Update patients
        patient_cols = [
            ("diastolic_dysfunction", "VARCHAR"),
            ("handgrip_strength", "FLOAT"),
            ("native_kidney_biopsy_date", "DATE"),
            ("native_kidney_biopsy_report", "TEXT"),
            ("echo_date", "DATE"),
            ("echo_report", "TEXT"),
        ]
        for col, col_type in patient_cols:
            try:
                _safe_alter_table(conn, "patients", col, col_type)
                conn.commit()
                results.append(f"✅ Added {col} to patients")
            except Exception as e:
                results.append(f"⚠️ {col} (patient): {str(e)[:50]}...")

        # 4. Update monthly_records
        monthly_cols = [
            ("npcr", "FLOAT"),
            ("ufr", "FLOAT"),
            ("prealbumin", "FLOAT"),
            ("sga_score", "VARCHAR"),
            ("mis_score", "INTEGER"),
            ("neutrophil_count", "FLOAT"),
            ("lymphocyte_count", "FLOAT"),
            ("il6", "FLOAT"),
            ("tnf_alpha", "FLOAT"),
            ("bp_dia", "FLOAT"),
            ("troponin_i", "FLOAT"),
            ("nt_probnp", "FLOAT"),
            ("hospitalization_diagnosis", "TEXT"),
            ("hospitalization_icd_diagnosis", "TEXT")
        ]
        for col, col_type in monthly_cols:
            try:
                _safe_alter_table(conn, "monthly_records", col, col_type)
                conn.commit()
                results.append(f"✅ Added {col} to monthly_records")
            except Exception as e:
                results.append(f"⚠️ {col} (monthly): {str(e)[:50]}...")

    res_html = "<h2>Migration Results</h2><ul>" + "".join([f"<li>{r}</li>" for r in results]) + "</ul><a href='/admin/users'>Back to Admin</a>"
    return HTMLResponse(content=res_html)

@router.get("/users", response_class=HTMLResponse)
async def user_manager(request: Request, reset_ok: Optional[str] = None, temp_pw: Optional[str] = None, db: Session = Depends(get_db)):
    _require_admin(request)
    users = db.query(User).all()
    reset_msg = f"Password for {reset_ok} has been reset." if reset_ok else None
    return templates.TemplateResponse("admin_users.html", {
        "request": request,
        "users": users,
        "user": get_user(request),
        "reset_msg": reset_msg,
        "temp_pw": temp_pw,
    })

@router.post("/users/create")
async def create_user(request: Request, username: str = Form(...), full_name: str = Form(""), password: str = Form(...), role: str = Form("viewer"), db: Session = Depends(get_db)):
    _require_admin(request)
    hashed = pwd_context.hash(password)
    new_user = User(username=username, full_name=full_name, hashed_password=hashed, role=role)
    db.add(new_user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        users = db.query(User).all()
        return templates.TemplateResponse("admin_users.html", {
            "request": request,
            "users": users,
            "user": get_user(request),
            "error": "Username already exists.",
            "reset_msg": None,
            "temp_pw": None,
        })
    return RedirectResponse(url="/admin/users", status_code=303)

@router.post("/patients/{patient_id}/reactivate")
async def reactivate_patient(patient_id: int, request: Request, db: Session = Depends(get_db)):
    _require_admin(request)
    p = db.query(Patient).filter(Patient.id == patient_id).first()
    if p:
        p.is_active = True
        db.commit()
    return RedirectResponse(url="/admin/backup", status_code=303)

@router.post("/users/{user_id}/toggle")
async def toggle_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    _require_admin(request)
    u = db.query(User).filter(User.id == user_id).first()
    if u:
        u.is_active = not u.is_active
        db.commit()
    return RedirectResponse(url="/admin/users", status_code=303)

@router.post("/users/{user_id}/reset-password")
async def reset_password(user_id: int, request: Request, db: Session = Depends(get_db)):
    _require_admin(request)
    u = db.query(User).filter(User.id == user_id).first()
    if u:
        temp_pw = secrets.token_urlsafe(8)
        u.hashed_password = pwd_context.hash(temp_pw)
        db.commit()
        return RedirectResponse(
            url=f"/admin/users?reset_ok={u.username}&temp_pw={temp_pw}",
            status_code=303,
        )
    return RedirectResponse(url="/admin/users", status_code=303)

@router.get("/backup", response_class=HTMLResponse)
async def backup_page(
    request: Request,
    success: Optional[str] = None,
    error: Optional[str] = None,
    db: Session = Depends(get_db)
):
    _require_admin(request)
    inactive_patients = (
        db.query(Patient)
        .filter(Patient.is_active == False)
        .order_by(Patient.name)
        .all()
    )
    from database import FoodDatabaseItem
    food_items = db.query(FoodDatabaseItem).order_by(FoodDatabaseItem.name).all()
    return templates.TemplateResponse("admin_db.html", {
        "request": request,
        "user": get_user(request),
        "inactive_patients": inactive_patients,
        "food_items": food_items,
        "success": success,
        "error": error,
    })

@router.post("/food-items/create")
async def create_food_item(
    request: Request,
    food_id: Optional[int] = Form(None),
    name: str = Form(...),
    synonyms: str = Form(...),
    calories: float = Form(...),
    protein: float = Form(...),
    phosphorus: float = Form(...),
    potassium: Optional[float] = Form(None),
    calcium: Optional[float] = Form(None),
    db: Session = Depends(get_db)
):
    _require_admin(request)
    from database import FoodDatabaseItem
    
    item = None
    if food_id:
        item = db.query(FoodDatabaseItem).filter(FoodDatabaseItem.id == food_id).first()
        
    if item:
        # Check duplicate name on another food item
        duplicate = db.query(FoodDatabaseItem).filter(
            FoodDatabaseItem.name.ilike(name),
            FoodDatabaseItem.id != food_id
        ).first()
        if duplicate:
            return RedirectResponse(
                url="/admin/backup?error=A+food+item+with+that+name+already+exists.",
                status_code=303
            )
        item.name = name
        item.synonyms = synonyms.lower()
        item.calories = calories
        item.protein = protein
        item.phosphorus = phosphorus
        item.potassium = potassium
        item.calcium = calcium
    else:
        existing = db.query(FoodDatabaseItem).filter(FoodDatabaseItem.name.ilike(name)).first()
        if existing:
            existing.synonyms = synonyms.lower()
            existing.calories = calories
            existing.protein = protein
            existing.phosphorus = phosphorus
            existing.potassium = potassium
            existing.calcium = calcium
        else:
            item = FoodDatabaseItem(
                name=name,
                synonyms=synonyms.lower(),
                calories=calories,
                protein=protein,
                phosphorus=phosphorus,
                potassium=potassium,
                calcium=calcium
            )
            db.add(item)
            
    db.commit()
    return RedirectResponse(url="/admin/backup?success=Food+item+saved+successfully.", status_code=303)

@router.post("/food-items/{item_id}/delete")
async def delete_food_item(item_id: int, request: Request, db: Session = Depends(get_db)):
    _require_admin(request)
    from database import FoodDatabaseItem
    item = db.query(FoodDatabaseItem).filter(FoodDatabaseItem.id == item_id).first()
    if item:
        db.delete(item)
        db.commit()
    return RedirectResponse(url="/admin/backup?success=Food+item+deleted+successfully.", status_code=303)

@router.post("/db/strip-western")
async def strip_western_foods(request: Request, db: Session = Depends(get_db)):
    _require_admin(request)
    from database import FoodDatabaseItem
    from sqlalchemy import or_
    
    brand_keywords = [
        'kraft', 'campbell', 'mcdonald', 'taco bell', 'pizza hut', 'burger king', 
        'wendy', 'kfc', 'subway', 'heinz', 'kellogg', 'nestle', 'hershey', 'nabisco', 
        'pepsico', 'coca-cola', 'cocacola', 'pepsi', 'cadbury', 'quaker', 'general mills', 
        'pillsbury', 'betty crocker', 'oscar mayer', 'tyson', 'swanson', 'stouffer', 
        'del monte', 'lean cuisine', 'digiorno', 'uncle ben', 'conagra', 'hunt', 
        'chef boyardee', 'banquet', 'jimmy dean', 'eggo', 'pampers', 'gerber', 
        'keebler', 'frito-lay', 'fritolay', 'post ', 'post consumer', 'mccormick'
    ]
    
    processed_keywords = [
        'hamburger', 'cheeseburger', 'hot dog', 'hotdog', 'lasagna', 'spaghetti', 
        'macaroni', 'waffle', 'pancake', 'bagel', 'croissant', 'muffin', 'salami', 
        'bologna', 'pepperoni', 'marshmallow', 'poptart', 'pop-tart', 'pretzel', 
        'caesar dressing', 'ranch dressing', 'thousand island', 'maple syrup', 
        'cornflakes', 'doughnut', 'donut', 'taco shell', 'nacho', 'quesadilla', 
        'burrito', 'fettuccine', 'gravy', 'clam chowder', 'chicken nuggets', 
        'fish sticks', 'pork loin', 'pork chop', 'beef sirloin', 'ribeye', 't-bone', 
        'chuck roast', 'bacon', 'prosciutto'
    ]
    
    all_keywords = brand_keywords + processed_keywords
    conditions = []
    for kw in all_keywords:
        conditions.append(FoodDatabaseItem.name.ilike(f"%{kw}%"))
        conditions.append(FoodDatabaseItem.synonyms.ilike(f"%{kw}%"))
        
    matching_items = db.query(FoodDatabaseItem).filter(or_(*conditions)).all()
    deleted_count = len(matching_items)
    
    if deleted_count > 0:
        for item in matching_items:
            db.delete(item)
        db.commit()
        
    return RedirectResponse(
        url=f"/admin/backup?success=Successfully+stripped+{deleted_count}+pure+western+food+items+from+the+master+database!",
        status_code=303
    )

_EXPORT_CHUNK_SIZE = 200  # rows per yield — keeps peak memory bounded


def _row_to_dict(obj) -> dict:
    """Serialise a SQLAlchemy ORM row to a JSON-safe dict."""
    d = {k: v for k, v in obj.__dict__.items() if k != "_sa_instance_state"}
    for k, v in d.items():
        if isinstance(v, (date, datetime)):
            d[k] = v.isoformat()
        elif isinstance(v, bytes):
            d[k] = None  # skip binary blobs (e.g. model_binary) in exports
    return d


def _stream_table(db: Session, model, order_col, label: str):
    """Yield JSON fragments for one table, chunked to avoid OOM on large tables."""
    yield f'  "{label}": [\n'
    first = True
    offset = 0
    while True:
        chunk = (
            db.query(model)
            .order_by(order_col)
            .limit(_EXPORT_CHUNK_SIZE)
            .offset(offset)
            .all()
        )
        if not chunk:
            break
        for row in chunk:
            prefix = "" if first else ",\n"
            yield f"{prefix}    {json.dumps(_row_to_dict(row))}"
            first = False
        offset += _EXPORT_CHUNK_SIZE
        db.expunge_all()  # free ORM identity-map memory between chunks
    yield "\n  ]"


@router.get("/db/export")
async def download_backup(request: Request, db: Session = Depends(get_db)):
    _require_admin(request)
    import asyncio
    from database import FoodDatabaseItem
    from dynamic_vars import VariableDefinition

    # Stream the JSON so Supabase's 30-second statement_timeout is never
    # hit in one query, and peak container memory stays bounded regardless
    # of how many session/monthly records exist.
    def _generate():
        yield '{\n'
        tables = [
            (Patient,            Patient.id,              "patients"),
            (VariableDefinition, VariableDefinition.id,   "variable_definitions"),
            (MonthlyRecord,      MonthlyRecord.id,        "monthly_records"),
            (SessionRecord,      SessionRecord.id,        "session_records"),
            (InterimLabRecord,   InterimLabRecord.id,     "interim_labs"),
            (ClinicalEvent,      ClinicalEvent.id,        "clinical_events"),
            (User,               User.id,                 "users"),
            (FoodDatabaseItem,   FoodDatabaseItem.id,     "food_items"),
        ]
        for i, (model, order_col, label) in enumerate(tables):
            yield from _stream_table(db, model, order_col, label)
            if i < len(tables) - 1:
                yield ",\n"
            else:
                yield "\n"
        yield '}\n'

    return StreamingResponse(
        _generate(),
        media_type="application/json",
        headers={
            "Content-Disposition": (
                f"attachment; filename=hd_dashboard_backup_{date.today().isoformat()}.json"
            )
        },
    )

@router.post("/db/import")
async def restore_backup(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
    _require_admin(request)
    from database import FoodDatabaseItem
    content = await file.read()
    data = json.loads(content)

    # Simple restore logic (clear and insert) - CAUTION: High Risk
    # In a real app, you'd want to merge or handle conflicts
    # For now, let's just log and provide a placeholder
    logger.warning("Restore initiated by %s", get_user(request).get("username"))

    inactive_patients = (
        db.query(Patient)
        .filter(Patient.is_active == False)
        .order_by(Patient.name)
        .all()
    )
    food_items = db.query(FoodDatabaseItem).order_by(FoodDatabaseItem.name).all()
    return templates.TemplateResponse("admin_db.html", {
        "request": request,
        "user": get_user(request),
        "inactive_patients": inactive_patients,
        "food_items": food_items,
        "error": "Restore feature is under development. Please contact support.",
        "success": None,
    })

@router.get("/missing-data", response_class=HTMLResponse)
async def admin_missing_data(
    request: Request,
    patient_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    _require_admin(request)
    
    # Get all active patients sorted by name
    patients = db.query(Patient).filter(Patient.is_active == True).order_by(Patient.name).all()
    
    selected_patient = None
    report = None
    
    if patient_id:
        selected_patient = db.query(Patient).filter(Patient.id == patient_id).first()
        if selected_patient:
            # 1. Profile fields check
            profile_missing = []
            if not selected_patient.age: profile_missing.append("Age")
            if not selected_patient.height: profile_missing.append("Height")
            if not selected_patient.dry_weight: profile_missing.append("Dry Weight")
            if not selected_patient.hd_wef_date: profile_missing.append("HD Start Date (WEF)")
            
            acc = selected_patient.vascular_access
            if not acc:
                profile_missing.extend(["Access Type", "Access Date (Surgery)", "First Cannulation Date"])
            else:
                if not acc.access_type: profile_missing.append("Access Type")
                if not acc.access_date: profile_missing.append("Access Date (Surgery)")
                if not acc.date_first_cannulation: profile_missing.append("First Cannulation Date")
                
            # 2. Dialysis Session fields check up to May 2026
            sessions = (
                db.query(SessionRecord)
                .filter(
                    SessionRecord.patient_id == patient_id,
                    SessionRecord.session_date <= date(2026, 5, 31)
                )
                .order_by(SessionRecord.session_date.desc())
                .all()
            )
            
            session_issues = []
            for s in sessions:
                missing_fields = []
                if not s.blood_flow_rate: missing_fields.append("Prescribed BFR")
                if not s.actual_blood_flow_rate: missing_fields.append("Actual BFR")
                if not s.duration_hours: missing_fields.append("Duration (Hours)")
                if s.weight_pre is None: missing_fields.append("Weight Pre-HD")
                if s.weight_post is None: missing_fields.append("Weight Post-HD")
                if s.bp_pre_sys is None: missing_fields.append("BP Pre-HD Systolic")
                if s.bp_pre_dia is None: missing_fields.append("BP Pre-HD Diastolic")
                if s.bp_post_sys is None: missing_fields.append("BP Post-HD Systolic")
                if s.bp_post_dia is None: missing_fields.append("BP Post-HD Diastolic")
                if s.bp_nadir_sys is None: missing_fields.append("BP Nadir Systolic")
                
                if missing_fields:
                    session_issues.append({
                        "id": s.id,
                        "date": s.session_date.strftime('%Y-%m-%d'),
                        "missing": missing_fields
                    })
                    
            # 3. Monthly Labs check up to May 2026
            monthly_records = (
                db.query(MonthlyRecord)
                .filter(
                    MonthlyRecord.patient_id == patient_id,
                    MonthlyRecord.record_month <= "2026-05"
                )
                .order_by(MonthlyRecord.record_month.desc())
                .all()
            )
            
            monthly_issues = []
            for m in monthly_records:
                missing_labs = []
                if not m.hb: missing_labs.append("Hemoglobin (Hb)")
                if not m.albumin: missing_labs.append("Albumin")
                if not m.phosphorus: missing_labs.append("Phosphorus")
                if not m.crp: missing_labs.append("CRP")
                if not m.single_pool_ktv: missing_labs.append("Kt/V")
                
                if missing_labs:
                    monthly_issues.append({
                        "month": m.record_month,
                        "missing": missing_labs
                    })
                    
            report = {
                "profile_missing": profile_missing,
                "session_issues": session_issues,
                "monthly_issues": monthly_issues,
                "total_sessions_checked": len(sessions),
                "total_months_checked": len(monthly_records)
            }
            
    return templates.TemplateResponse("admin_missing_data.html", {
        "request": request,
        "user": get_user(request),
        "patients": patients,
        "selected_patient": selected_patient,
        "report": report
    })


# ── Data Entry Activity Monitor ───────────────────────────────────────────────

@router.get("/activity", response_class=HTMLResponse)
async def admin_activity(
    request: Request,
    days: int = 7,
    filter_user: str = "",
    db: Session = Depends(get_db),
):
    """Staff data-entry activity monitor — daily / weekly breakdown by user."""
    _require_admin(request)

    if days not in (1, 7, 14, 30):
        days = 7

    today = date.today()
    since = today - timedelta(days=days - 1)

    # ── helpers ───────────────────────────────────────────────────────────────
    def _rows(model, ts_col, actor_col):
        """Return list of (actor, date, count) within the window."""
        rows = (
            db.query(
                actor_col.label("actor"),
                cast(ts_col, SADate).label("day"),
                func.count().label("cnt"),
            )
            .filter(cast(ts_col, SADate) >= since)
            .group_by(actor_col, cast(ts_col, SADate))
            .all()
        )
        return rows

    sr  = _rows(SessionRecord,       SessionRecord.timestamp,        SessionRecord.entered_by)
    mr  = _rows(MonthlyRecord,       MonthlyRecord.timestamp,        MonthlyRecord.entered_by)
    il  = _rows(InterimLabRecord,    InterimLabRecord.created_at,    InterimLabRecord.entered_by)
    ce  = _rows(ClinicalEvent,       ClinicalEvent.created_at,       ClinicalEvent.created_by)
    he  = _rows(HospitalisationEvent, HospitalisationEvent.created_at, HospitalisationEvent.entered_by)

    ENTRY_TYPES = [
        ("Session Record",      sr,  "#6366f1"),
        ("Monthly Lab Record",  mr,  "#0ea5e9"),
        ("Interim Labs",        il,  "#10b981"),
        ("Clinical Event",      ce,  "#f59e0b"),
        ("Hospitalisation",     he,  "#ef4444"),
    ]

    # ── collect all active actors ─────────────────────────────────────────────
    all_actors: set[str] = set()
    for _, rows, _ in ENTRY_TYPES:
        for r in rows:
            if r.actor:
                all_actors.add(r.actor)

    # ── date range list ───────────────────────────────────────────────────────
    date_range = [since + timedelta(days=i) for i in range(days)]

    # ── per-user, per-day grid  {actor: {date: {type: count}}} ───────────────
    grid: dict = {}
    for label, rows, color in ENTRY_TYPES:
        for r in rows:
            actor = r.actor or "unknown"
            if filter_user and actor != filter_user:
                continue
            grid.setdefault(actor, {}).setdefault(str(r.day), {})
            grid[actor][str(r.day)][label] = grid[actor][str(r.day)].get(label, 0) + r.cnt

    # ── user summary: total this period & today ───────────────────────────────
    user_summary: list[dict] = []
    today_str = str(today)
    for actor in sorted(all_actors):
        if filter_user and actor != filter_user:
            continue
        days_data = grid.get(actor, {})
        total_period = sum(
            sum(types.values()) for types in days_data.values()
        )
        total_today = sum(days_data.get(today_str, {}).values())
        breakdown_period: dict[str, int] = {}
        for day_types in days_data.values():
            for t, c in day_types.items():
                breakdown_period[t] = breakdown_period.get(t, 0) + c
        last_active = max(days_data.keys()) if days_data else None
        user_summary.append({
            "actor": actor,
            "total_today": total_today,
            "total_period": total_period,
            "breakdown": breakdown_period,
            "last_active": last_active,
        })
    user_summary.sort(key=lambda x: x["total_period"], reverse=True)

    # ── heatmap data: {actor: [count per day in date_range]} ─────────────────
    heatmap: dict[str, list[int]] = {}
    for actor in all_actors:
        if filter_user and actor != filter_user:
            continue
        heatmap[actor] = [
            sum(grid.get(actor, {}).get(str(d), {}).values())
            for d in date_range
        ]

    # ── KPI totals ────────────────────────────────────────────────────────────
    kpi_today   = sum(s["total_today"]  for s in user_summary)
    kpi_period  = sum(s["total_period"] for s in user_summary)
    kpi_users   = len([s for s in user_summary if s["total_period"] > 0])
    type_totals = {}
    for label, rows, color in ENTRY_TYPES:
        cnt = sum(
            r.cnt for r in rows
            if (not filter_user or r.actor == filter_user)
        )
        type_totals[label] = {"count": cnt, "color": color}

    # ── recent detailed log (last 200 rows across all sources) ────────────────
    def _recent(ts_col, actor_col, label: str):
        q = (
            db.query(actor_col.label("actor"), ts_col.label("ts"))
            .filter(cast(ts_col, SADate) >= since)
        )
        if filter_user:
            q = q.filter(actor_col == filter_user)
        return [(r.actor or "—", r.ts, label) for r in q.order_by(ts_col.desc()).limit(60)]

    recent_log = (
        _recent(SessionRecord.timestamp,           SessionRecord.entered_by,           "Session Record")
        + _recent(MonthlyRecord.timestamp,         MonthlyRecord.entered_by,           "Monthly Lab Record")
        + _recent(InterimLabRecord.created_at,     InterimLabRecord.entered_by,        "Interim Labs")
        + _recent(ClinicalEvent.created_at,        ClinicalEvent.created_by,           "Clinical Event")
        + _recent(HospitalisationEvent.created_at, HospitalisationEvent.entered_by,    "Hospitalisation")
    )
    recent_log.sort(key=lambda x: x[1] or datetime.min, reverse=True)
    recent_log = recent_log[:200]

    all_users_list = sorted(all_actors)

    return templates.TemplateResponse("admin_activity.html", {
        "request": request,
        "user": get_user(request),
        "days": days,
        "filter_user": filter_user,
        "since": since,
        "today": today,
        "date_range": [str(d) for d in date_range],
        "date_labels": [d.strftime("%d %b") for d in date_range],
        "kpi_today": kpi_today,
        "kpi_period": kpi_period,
        "kpi_users": kpi_users,
        "kpi_days": days,
        "user_summary": user_summary,
        "heatmap": heatmap,
        "type_totals": type_totals,
        "recent_log": recent_log,
        "all_users_list": all_users_list,
        "entry_types": [(label, color) for label, _, color in ENTRY_TYPES],
    })


@router.get("/activity/export-csv")
async def admin_activity_export_csv(
    request: Request,
    days: int = 7,
    filter_user: str = "",
    db: Session = Depends(get_db),
):
    """Download the activity log as a CSV file."""
    _require_admin(request)

    if days not in (1, 7, 14, 30):
        days = 7

    today = date.today()
    since = today - timedelta(days=days - 1)

    def _recent_csv(ts_col, actor_col, label: str):
        q = (
            db.query(actor_col.label("actor"), ts_col.label("ts"))
            .filter(cast(ts_col, SADate) >= since)
        )
        if filter_user:
            q = q.filter(actor_col == filter_user)
        return [(r.actor or "—", r.ts, label) for r in q.order_by(ts_col.desc()).limit(500)]

    rows = (
        _recent_csv(SessionRecord.timestamp,           SessionRecord.entered_by,           "Session Record")
        + _recent_csv(MonthlyRecord.timestamp,         MonthlyRecord.entered_by,           "Monthly Lab Record")
        + _recent_csv(InterimLabRecord.created_at,     InterimLabRecord.entered_by,        "Interim Labs")
        + _recent_csv(ClinicalEvent.created_at,        ClinicalEvent.created_by,           "Clinical Event")
        + _recent_csv(HospitalisationEvent.created_at, HospitalisationEvent.entered_by,    "Hospitalisation")
    )
    rows.sort(key=lambda x: x[1] or datetime.min, reverse=True)

    import io, csv
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Staff Username", "Entry Type", "Timestamp"])
    for actor, ts, label in rows:
        w.writerow([actor, label, ts.strftime("%Y-%m-%d %H:%M:%S") if ts else ""])

    filename = f"activity_{since}_{today}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )

