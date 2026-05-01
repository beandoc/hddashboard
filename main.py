from fastapi import FastAPI, Depends, Request, Form, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional
import logging
import time

from database import engine, Base, get_db, Patient, SessionLocal, User
from config import templates, serializer, pwd_context
from dependencies import get_user
from dashboard_logic import compute_dashboard, get_current_month_str, get_month_label, get_effective_month
from routers import auth, patients, entry, sessions, analytics, events, variables, admin, patient_portal, schedule, alerts, sustainability, fluid_status, admin_analytics, research

# ─────────────────────────────────────────────────────────────────────────────
# APP INITIALIZATION
# ─────────────────────────────────────────────────────────────────────────────

def _init_db_with_retry(max_attempts: int = 5, delay: int = 5):
    for attempt in range(1, max_attempts + 1):
        try:
            Base.metadata.create_all(bind=engine)
            return
        except Exception as exc:
            logging.warning("DB init attempt %d/%d failed: %s", attempt, max_attempts, exc)
            if attempt == max_attempts:
                raise
            time.sleep(delay)

_init_db_with_retry()

# Auto-migrate: sync DB schema with SQLAlchemy models on every startup
def _run_startup_migrations():
    # Map SQLAlchemy column types to SQL DDL strings
    from sqlalchemy import inspect as sa_inspect
    from sqlalchemy import Integer, String, Float, Boolean, Date, DateTime, Text

    type_map = {
        Integer: "INTEGER",
        String: "VARCHAR",
        Float: "FLOAT",
        Boolean: "BOOLEAN",
        Date: "DATE",
        DateTime: "DATETIME",
        Text: "TEXT",
    }

    inspector = sa_inspect(engine)
    with engine.connect() as conn:
        for mapper in Base.registry.mappers:
            table_name = mapper.persist_selectable.name
            if not inspector.has_table(table_name):
                continue
            existing = {col["name"] for col in inspector.get_columns(table_name)}
            for col in mapper.persist_selectable.columns:
                if col.name in existing or col.primary_key:
                    continue
                sql_type = type_map.get(type(col.type), "VARCHAR")
                default_clause = ""
                if col.default is not None and hasattr(col.default, "arg") and not callable(col.default.arg):
                    default_clause = f" DEFAULT {col.default.arg}"
                try:
                    conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {col.name} {sql_type}{default_clause}"))
                    conn.commit()
                    logging.info(f"Migration: added {col.name} to {table_name}")
                except Exception:
                    pass  # column already exists or unsupported

_run_startup_migrations()


def _seed_default_users():
    db = SessionLocal()
    try:
        defaults = [
            {"username": "admin",  "full_name": "Administrator", "role": "admin"},
            {"username": "staff",  "full_name": "Staff User",    "role": "staff"},
            {"username": "doctor", "full_name": "Doctor User",   "role": "doctor"},
        ]
        for d in defaults:
            exists = db.query(User).filter(User.username == d["username"]).first()
            if not exists:
                db.add(User(
                    username=d["username"],
                    full_name=d["full_name"],
                    hashed_password=pwd_context.hash("chsc"),
                    role=d["role"],
                    is_active=True,
                ))
        db.commit()
    finally:
        db.close()

_seed_default_users()

app = FastAPI(title="Hemodialysis Dashboard", version="2.0.0")

# Authentication Middleware
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Processes session cookie and populates request.state.user."""
    token = request.cookies.get("hd_session")
    request.state.user = None
    
    if token:
        try:
            data = serializer.loads(token)
            user_type, username = data.split(":", 1)
            
            try:
                db = SessionLocal()
                try:
                    if user_type == "staff":
                        user = db.query(User).filter(User.username == username, User.is_active == True).first()
                        if user:
                            request.state.user = user
                    elif user_type == "patient":
                        p = db.query(Patient).filter(Patient.login_username == username, Patient.is_active == True).first()
                        if p:
                            request.state.user = {
                                "username": p.login_username,
                                "full_name": p.name,
                                "role": "patient",
                                "id": p.id
                            }
                finally:
                    db.close()
            except Exception as db_err:
                logging.error(f"Auth middleware DB error: {db_err}")
                pass
        except Exception:
            pass
            
    response = await call_next(request)
    return response

# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Routers
app.include_router(auth.router)
app.include_router(patients.router)
app.include_router(entry.router)
app.include_router(sessions.router)
app.include_router(sessions.session_router)
app.include_router(analytics.router)
app.include_router(events.router)
app.include_router(variables.router)
app.include_router(admin.router)
app.include_router(patient_portal.router)
app.include_router(schedule.router)
app.include_router(alerts.router)
app.include_router(sustainability.router)
app.include_router(fluid_status.router)
app.include_router(admin_analytics.router)
app.include_router(research.router)

# ─────────────────────────────────────────────────────────────────────────────
# CORE ROUTES (Dashboard)
# ─────────────────────────────────────────────────────────────────────────────

@app.head("/", include_in_schema=False)
async def dashboard_head():
    return HTMLResponse(content="")

@app.get("/", response_class=HTMLResponse)
async def dashboard_index(request: Request, month: Optional[str] = None, db: Session = Depends(get_db)):
    month_str, data_note = get_effective_month(db, month)
    try:
        data = compute_dashboard(db, month_str)
        data["data_note"] = data_note
    except Exception as e:
        logging.error(f"Dashboard error: {e}")
        data = {
            "alerts": {
                "hb_low": {"count": 0, "names": []},
                "albumin_low": {"count": 0, "names": []},
                "phos_high": {"count": 0, "names": []},
                "ca_low": {"count": 0, "names": []},
                "idwg_high": {"count": 0, "names": []},
                "non_avf": {"count": 0, "names": []},
                "epo_hypo": {"count": 0, "names": []},
                "iv_iron_rec": {"count": 0, "names": []},
                "trend_hb": [],
            },
            "metrics": {
                "total_patients": {"count": 0, "names": []},
                "male_patients": {"count": 0, "names": []},
                "female_patients": {"count": 0, "names": []},
                "non_avf": {"count": 0, "names": [], "types": {}},
                "idwg_high": {"count": 0, "names": []},
                "albumin_low": {"count": 0, "names": []},
                "calcium_low": {"count": 0, "names": []},
                "phos_high": {"count": 0, "names": []},
                "epo_hypo":    {"count": 0, "names": []},
                "epo_hypo_r2": {"count": 0, "names": []},
                "epo_hypo_r3": {"count": 0, "names": [], "cutoff": None},
                "iv_iron_rec": {"count": 0, "names": []},
                "trend_hb": [],
                "trend_albumin": [],
                "trend_phosphorus": []
            },
            "patient_rows": [],
            "month_label": get_month_label(month_str),
            "prev_month_label": "N/A",
            "total_active": 0,
            "data_note": data_note,
        }

    _current_month = get_current_month_str()
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "data": data,
        "month_str": month_str,
        "current_month": _current_month,
        "current_month_label": get_month_label(_current_month),
        "user": get_user(request),
    })

# Root health check
@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "2.0.0"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
