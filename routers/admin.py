from fastapi import APIRouter, Depends, Request, Form, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional
import json
import io
import logging
import re

from datetime import date, datetime
from database import get_db, User, Patient, MonthlyRecord, SessionRecord, InterimLabRecord, ClinicalEvent, engine
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
async def user_manager(request: Request, db: Session = Depends(get_db)):
    _require_admin(request)
    users = db.query(User).all()
    return templates.TemplateResponse("admin_users.html", {"request": request, "users": users, "user": get_user(request)})

@router.post("/users/create")
async def create_user(request: Request, username: str = Form(...), full_name: str = Form(""), password: str = Form(...), role: str = Form("viewer"), db: Session = Depends(get_db)):
    _require_admin(request)
    hashed = pwd_context.hash(password)
    new_user = User(username=username, full_name=full_name, hashed_password=hashed, role=role)
    db.add(new_user)
    db.commit()
    return RedirectResponse(url="/admin/users", status_code=303)

@router.post("/users/{user_id}/toggle")
async def toggle_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    _require_admin(request)
    u = db.query(User).filter(User.id == user_id).first()
    if u:
        u.is_active = not u.is_active
        db.commit()
    return RedirectResponse(url="/admin/users", status_code=303)

@router.post("/users/{user_id}/reset-password")
async def reset_password(user_id: int, request: Request, new_password: str = Form(...), db: Session = Depends(get_db)):
    _require_admin(request)
    u = db.query(User).filter(User.id == user_id).first()
    if u:
        u.hashed_password = pwd_context.hash(new_password)
        db.commit()
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

@router.get("/db/export")
async def download_backup(request: Request, db: Session = Depends(get_db)):
    _require_admin(request)
    data = {
        "patients": [p.__dict__ for p in db.query(Patient).all()],
        "monthly_records": [r.__dict__ for r in db.query(MonthlyRecord).all()],
        "session_records": [s.__dict__ for s in db.query(SessionRecord).all()],
        "interim_labs": [l.__dict__ for l in db.query(InterimLabRecord).all()],
        "clinical_events": [e.__dict__ for e in db.query(ClinicalEvent).all()],
        "users": [u.__dict__ for u in db.query(User).all()]
    }
    # Remove SQLAlchemy internal state
    for key in data:
        for item in data[key]:
            item.pop("_sa_instance_state", None)
            # Convert dates/datetimes to strings
            for k, v in item.items():
                if isinstance(v, (date, datetime)):
                    item[k] = v.isoformat()
    
    json_data = json.dumps(data, indent=2)
    return StreamingResponse(
        io.BytesIO(json_data.encode()),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=hd_dashboard_backup_{date.today().isoformat()}.json"}
    )

@router.post("/db/import")
async def restore_backup(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
    _require_admin(request)
    content = await file.read()
    data = json.loads(content)
    
    # Simple restore logic (clear and insert) - CAUTION: High Risk
    # In a real app, you'd want to merge or handle conflicts
    # For now, let's just log and provide a placeholder
    logger.warning("Restore initiated by %s", get_user(request).get("username"))
    return templates.TemplateResponse("admin_db.html", {"request": request, "error": "Restore feature is under development. Please contact support.", "user": get_user(request)})
