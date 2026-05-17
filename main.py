from __future__ import annotations

from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from sqlalchemy.orm import Session
from typing import Optional
import logging
import time

from database import get_db, Patient, SessionLocal, User
from config import templates, serializer, pwd_context, limiter, COOKIE_SECURE, SESSION_MAX_AGE, SESSION_IDLE_TTL
from dependencies import get_user
from dashboard_logic import compute_dashboard, get_current_month_str, get_month_label, get_effective_month
from routers import auth, patients, entry, sessions, analytics, events, variables, admin, patient_portal, schedule, alerts, sustainability, fluid_status, admin_analytics, research, api_v1

# ─────────────────────────────────────────────────────────────────────────────
# REQUIRED DB SCHEMA VERSION
# Bump this whenever a new Alembic migration must be applied before boot.
# ─────────────────────────────────────────────────────────────────────────────
REQUIRED_DB_VERSION = "0007"


def _check_schema_version() -> None:
    """Warn (never crash) if the DB schema version is unexpected."""
    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT version_num FROM alembic_version ORDER BY version_num DESC LIMIT 1")
        ).fetchone()
        current = row[0] if row else None
        if current != REQUIRED_DB_VERSION:
            logging.warning(
                "DB schema is at version '%s', app expects '%s'. "
                "Run 'alembic upgrade head' to apply pending migrations.",
                current, REQUIRED_DB_VERSION,
            )
        else:
            logging.info("Schema version OK: %s", current)
    except Exception as exc:
        # alembic_version table may not exist yet on first deploy —
        # log the real error and continue; the app will work if the
        # underlying tables are present.
        logging.warning("Schema version check skipped: %s", exc)
    finally:
        db.close()


def _seed_default_users() -> None:
    db = SessionLocal()
    try:
        defaults = [
            {"username": "admin",  "full_name": "Administrator", "role": "admin"},
            {"username": "staff",  "full_name": "Staff User",    "role": "staff"},
            {"username": "doctor", "full_name": "Doctor User",   "role": "doctor"},
        ]
        for d in defaults:
            if not db.query(User).filter(User.username == d["username"]).first():
                db.add(User(
                    username=d["username"],
                    full_name=d["full_name"],
                    hashed_password=pwd_context.hash("chsc"),
                    role=d["role"],
                    is_active=True,
                ))
        db.commit()
    except Exception as exc:
        logging.error(f"Startup seed failed: {exc}")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _check_schema_version()
    _seed_default_users()
    logging.info("Startup complete.")
    yield


app = FastAPI(title="Hemodialysis Dashboard", version="2.0.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Paths where the route handler manages its own session cookie — middleware
# must not overwrite those Set-Cookie headers.
_AUTH_PATHS = {"/login", "/logout", "/change-password"}


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Decode session cookie, enforce idle + absolute TTL, refresh sliding window."""
    from itsdangerous import SignatureExpired, BadData

    token = request.cookies.get("hd_session")
    request.state.user = None
    new_token: str | None = None

    if token:
        try:
            # max_age enforces 8 h absolute TTL server-side (URLSafeTimedSerializer
            # embeds creation timestamp in the signature).
            data = serializer.loads(token, max_age=SESSION_MAX_AGE)
            parts = data.split(":", 2)
            if len(parts) == 3:
                user_type, username, lat_str = parts
                lat = int(lat_str)
            else:
                user_type, username = parts[0], parts[1]
                lat = 0  # legacy token — treat as idle immediately

            if time.time() - lat <= SESSION_IDLE_TTL:
                db = SessionLocal()
                try:
                    if user_type == "staff":
                        user = db.query(User).filter(
                            User.username == username, User.is_active == True
                        ).first()
                        if user:
                            request.state.user = user
                    elif user_type == "patient":
                        p = db.query(Patient).filter(
                            Patient.login_username == username, Patient.is_active == True
                        ).first()
                        if p:
                            request.state.user = {
                                "username": p.login_username,
                                "full_name": p.name,
                                "role": "patient",
                                "id": p.id,
                            }
                except Exception as db_err:
                    logging.error(f"Auth middleware DB error: {db_err}")
                finally:
                    db.close()

                if request.state.user and request.url.path not in _AUTH_PATHS:
                    new_token = serializer.dumps(
                        f"{user_type}:{username}:{int(time.time())}"
                    )
        except (SignatureExpired, BadData):
            pass

    response = await call_next(request)

    if new_token and request.url.path not in _AUTH_PATHS:
        response.set_cookie(
            key="hd_session", value=new_token,
            httponly=True, secure=COOKIE_SECURE,
            samesite="strict", max_age=SESSION_MAX_AGE,
        )
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
app.include_router(analytics.root_router)
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
app.include_router(api_v1.router)

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
                "hb_high": {"count": 0, "names": []},
                "hb_variability_high": {"count": 0, "names": []},
                "adherence_risk": {"count": 0, "names": []},
                "epo_hypo":    {"count": 0, "names": []},
                "epo_hypo_r2": {"count": 0, "names": []},
                "epo_hypo_r3": {"count": 0, "names": [], "cutoff": None},
                "iv_iron_rec": {"count": 0, "names": []},
                "missing_records": {"count": 0, "names": []},
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
    
    # Contextual banner logic for staff
    greeting = "morning"
    from datetime import datetime, date
    hour = datetime.now().hour
    if hour < 12: greeting = "morning"
    elif hour < 17: greeting = "afternoon"
    else: greeting = "evening"

    pending_entry_count = 0

    # Authentication check
    user = get_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    
    # Patient role check - redirect to portal
    if getattr(user, "role", None) == "patient" or (isinstance(user, dict) and user.get("role") == "patient"):
        return RedirectResponse(url="/patient/dashboard", status_code=302)

    high_risk_count = 0
    if getattr(user, "role", None) == "doctor" or (isinstance(user, dict) and user.get("role") == "doctor"):
        from ml_analytics import get_high_risk_mortality_count
        high_risk_count = get_high_risk_mortality_count(db)

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "data": data,
        "month_str": month_str,
        "current_month": _current_month,
        "current_month_label": get_month_label(_current_month),
        "user": user,
        "greeting": greeting,
        "pending_entry_count": pending_entry_count,
        "high_risk_count": high_risk_count,
    })

# Root health check
@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "2.0.0"}

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
