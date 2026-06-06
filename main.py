from __future__ import annotations

from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from sqlalchemy.orm import Session
from typing import Optional
import logging
import os
import subprocess
import threading
import time

from database import get_db, Patient, SessionLocal, User, create_tables
from config import templates, serializer, pwd_context, limiter, COOKIE_SECURE, SESSION_MAX_AGE, SESSION_IDLE_TTL
from dependencies import get_user
from dashboard_logic import compute_dashboard, get_current_month_str, get_month_label, get_effective_month
from routers import auth, patients, entry, sessions, analytics, events, variables, admin, patient_portal, schedule, alerts, sustainability, fluid_status, admin_analytics, research, api_v1, ocr, api_next, acm, twin, protocols

# ─────────────────────────────────────────────────────────────────────────────
# REQUIRED DB SCHEMA VERSION
# Bump this whenever a new Alembic migration must be applied before boot.
# ─────────────────────────────────────────────────────────────────────────────
REQUIRED_DB_VERSION = "8b92695a7472"


def _check_schema_version() -> None:
    """Log the current DB schema version. Migrations run via scripts/pre_deploy.py at deploy time."""
    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT version_num FROM alembic_version ORDER BY version_num DESC LIMIT 1")
        ).fetchone()
        current = row[0] if row else None
    except Exception as exc:
        logging.warning("Schema version check skipped: %s", exc)
        return
    finally:
        db.close()

    if current == REQUIRED_DB_VERSION:
        logging.info("Schema version OK: %s", current)
    else:
        logging.warning(
            "DB schema is at version '%s', app expects '%s'. "
            "Run scripts/pre_deploy.py to apply migrations — NOT done at runtime.",
            current, REQUIRED_DB_VERSION,
        )


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


# Set when the dashboard warm-up thread finishes (or fails).  The dashboard
# route waits on this before running compute_dashboard so the first cold
# request finds a warm cache instead of paying the full DB cost itself.
_DASHBOARD_WARM_EVENT = threading.Event()

# Set when the background database startup thread completes (migrations, seeding, models restore).
# The cache warm-up threads wait on this before performing queries so they don't hit old schemas.
_STARTUP_COMPLETE_EVENT = threading.Event()


def _warm_caches() -> None:
    """Pre-populate dashboard and ML caches at startup.

    Two daemon threads run in parallel so dashboard data and ML scores are
    both ready before the first real user request lands.  Each thread gets its
    own SessionLocal so they don't share a connection or fight over pool slots.
    """
    def _warm_dashboard():
        _STARTUP_COMPLETE_EVENT.wait()
        db = SessionLocal()
        try:
            from dashboard_logic import compute_dashboard
            compute_dashboard(db)
            logging.info("Dashboard cache warm-up complete.")
        except Exception as exc:
            logging.warning("Dashboard cache warm-up failed (non-fatal): %s", exc)
        finally:
            db.close()
            _DASHBOARD_WARM_EVENT.set()

    def _warm_ml():
        _STARTUP_COMPLETE_EVENT.wait()
        db = SessionLocal()
        try:
            from ml_analytics import get_all_patients_mortality_risk, run_cohort_analytics
            result = get_all_patients_mortality_risk(db)
            cohort = run_cohort_analytics(db)
            hr_count = sum(1 for p in result if p.get("risk_level") == "high")
            expiry = time.time() + _ML_ANALYTICS_TTL
            with _ML_ANALYTICS_LOCK:
                _ML_ANALYTICS_CACHE["high_risk_count"]  = (hr_count, expiry)
                _ML_ANALYTICS_CACHE["cohort_analytics"] = (cohort,    expiry)
            logging.info("ML analytics cache warm-up complete.")
        except Exception as exc:
            logging.warning("ML cache warm-up failed (non-fatal): %s", exc)
        finally:
            db.close()

    threading.Thread(target=_warm_dashboard, daemon=True, name="cache-warmup-dashboard").start()
    threading.Thread(target=_warm_ml,        daemon=True, name="cache-warmup-ml").start()


# Readiness flag: False until the background startup thread finishes its DB
# work.  The /health endpoint returns 503 while this is False so load-balancers
# and Render's health-check don't route traffic to an unready instance.
_APP_READY = False


def _restore_all_ml_models() -> None:
    """Restore all trained ML model .pkl files from the DB model_binary column.

    Render's ephemeral filesystem loses every .pkl on container restart.
    Each module already has its own _restore_model_from_db() — this function
    calls them all so startup logging shows a single "restored N models" line.
    """
    restored = []
    try:
        from ml_idh import _restore_model_from_db as _restore_idh
        if _restore_idh():
            restored.append("idh_v1")
    except Exception as exc:
        logging.warning("IDH model restore failed: %s", exc)

    try:
        from ml_acm import _restore_model_from_db as _restore_acm
        if _restore_acm():
            restored.append("acm_v1")
    except Exception as exc:
        logging.warning("ACM model restore failed: %s", exc)

    try:
        from ml_risk import _restore_model_from_db as _restore_det
        if _restore_det():
            restored.append("deterioration_v1")
    except Exception as exc:
        logging.warning("Deterioration model restore failed: %s", exc)

    if restored:
        logging.info("ML models restored from DB: %s", ", ".join(restored))
    else:
        logging.info("No ML models needed restore (files present or no binary in DB).")


def _background_startup() -> None:
    """Run all blocking startup work off the event loop.

    Runs in a daemon thread so uvicorn starts accepting connections (and can
    respond to the Render/UptimeRobot health probe) immediately, instead of
    waiting for DB round-trips before the first `yield` in lifespan.
    """
    global _APP_READY
    try:
        # Run alembic migrations automatically on startup
        logging.info("Applying database migrations (alembic upgrade head)...")
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            logging.warning(f"Alembic auto-upgrade did not run or failed: {result.stderr or result.returncode}")
        else:
            logging.info("Alembic migrations applied successfully.")

        create_tables()
        _check_schema_version()
        _seed_default_users()
        _restore_all_ml_models()
        logging.info("Background startup complete.")
    except Exception as exc:
        logging.error("Background startup error: %s", exc)
    finally:
        _APP_READY = True   # flip even on error so health check reports degraded
        _STARTUP_COMPLETE_EVENT.set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fire all blocking work in the background and yield immediately so the
    # ASGI server is ready to accept connections within milliseconds.
    startup_thread = threading.Thread(
        target=_background_startup, daemon=True, name="startup"
    )
    startup_thread.start()
    _warm_caches()          # also non-blocking (spawns its own threads)
    logging.info("Startup complete — background initialisation in progress.")
    yield


app = FastAPI(title="Hemodialysis Dashboard", version="2.0.0", lifespan=lifespan)

from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        # Local development
        "http://localhost:3000", "http://localhost:3001",
        "http://127.0.0.1:3000", "http://127.0.0.1:3001",
        "http://localhost:8080", "http://127.0.0.1:8080",
        # Production
        "https://hddashboard.onrender.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from starlette.types import ASGIApp, Scope, Receive, Send

class RewriteLoginMiddleware:
    """Proper ASGI middleware to rewrite /login to /api/login for JSON requests BEFORE routing."""
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] == "http":
            if scope.get("path") == "/login" and scope.get("method") == "POST":
                headers = {k.lower(): v for k, v in scope.get("headers", [])}
                content_type = headers.get(b"content-type", b"").decode("utf-8")
                if "application/json" in content_type:
                    scope["path"] = "/api/login"
                    if "raw_path" in scope:
                        scope["raw_path"] = b"/api/login"
        await self.app(scope, receive, send)

app.add_middleware(RewriteLoginMiddleware)


class StaticCacheMiddleware:
    """Add long-lived Cache-Control headers to versioned static assets.

    Versioned assets (URLs containing ?v= or /vendor/) are immutable and safe
    to cache for 1 year.  Font files (.woff2) and JS bundles get the same
    treatment.  All other /static/ responses get a short revalidation window
    so changes propagate within a minute.
    """
    _IMMUTABLE_EXTS = frozenset([".woff2", ".woff", ".ttf", ".otf", ".eot"])
    _LONG_CACHE = b"public, max-age=31536000, immutable"   # 1 year
    _SHORT_CACHE = b"public, max-age=60, must-revalidate"  # 1 minute

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http" or not scope.get("path", "").startswith("/static/"):
            await self.app(scope, receive, send)
            return

        path: str = scope["path"]
        qs: str = scope.get("query_string", b"").decode()
        ext = path.rsplit(".", 1)[-1] if "." in path else ""
        is_immutable = (
            f".{ext}" in self._IMMUTABLE_EXTS
            or "v=" in qs
            or "/vendor/" in path
        )
        cache_value = self._LONG_CACHE if is_immutable else self._SHORT_CACHE

        async def send_with_cache(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers = [(k, v) for k, v in headers if k.lower() != b"cache-control"]
                headers.append((b"cache-control", cache_value))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_cache)

app.add_middleware(StaticCacheMiddleware)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_request: Request, exc: RequestValidationError):
    # Surface form parsing errors (e.g. comma-decimal like "1,20") as a readable JSON response
    # instead of a raw 422 page that gives no hint about which field failed.
    errors = [
        {"field": " → ".join(str(l) for l in e["loc"]), "msg": e["msg"]}
        for e in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": "Form validation failed", "errors": errors})

# Paths where the route handler manages its own session cookie — middleware
# must not overwrite those Set-Cookie headers.
_AUTH_PATHS = {"/login", "/logout", "/change-password", "/api/login"}

# Process-level user identity cache: username -> (user_obj_or_dict, expiry_ts)
# Avoids a DB round-trip on every request for already-authenticated users.
# TTL is kept short (120s) so role/active-status changes propagate quickly.
_USER_IDENTITY_CACHE: dict = {}
_USER_IDENTITY_CACHE_TTL = 120  # seconds

# Process-level ML analytics cache — heavyweight computations scored over all
# patients.  TTL = 5 minutes.  Lock prevents the check-then-set race where two
# concurrent threads both see a stale entry, both recompute, and both write.
_ML_ANALYTICS_CACHE: dict = {}
_ML_ANALYTICS_LOCK  = threading.Lock()
_ML_ANALYTICS_TTL   = 300  # seconds


def _invalidate_user_cache(username: str) -> None:
    """Call on logout or role change to force a fresh DB lookup."""
    _USER_IDENTITY_CACHE.pop(username, None)


def _resolve_user_identity(user_type: str, username: str) -> object | dict | None:
    """Return cached user identity, or fetch from DB and cache it."""
    now = time.time()
    cached = _USER_IDENTITY_CACHE.get(username)
    if cached and now < cached[1]:
        return cached[0]

    db = SessionLocal()
    try:
        if user_type == "staff":
            user = db.query(User).filter(
                User.username == username, User.is_active == True
            ).first()
            if user:
                # Detach from session so the object is safe to use after db.close()
                db.expunge(user)
                _USER_IDENTITY_CACHE[username] = (user, now + _USER_IDENTITY_CACHE_TTL)
                return user
        elif user_type == "patient":
            from sqlalchemy import or_, func
            p = db.query(Patient).filter(
                or_(
                    Patient.login_username == username,
                    func.lower(Patient.hid_no) == username.lower()
                ),
                Patient.is_active == True
            ).first()
            if p:
                identity = {
                    "username": p.login_username,
                    "full_name": p.name,
                    "role": "patient",
                    "id": p.id,
                }
                _USER_IDENTITY_CACHE[username] = (identity, now + _USER_IDENTITY_CACHE_TTL)
                return identity
    except Exception as db_err:
        logging.error(f"Auth middleware DB error: {db_err}")
    finally:
        db.close()
    return None


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
                user = _resolve_user_identity(user_type, username)
                if user:
                    request.state.user = user
                    if request.url.path not in _AUTH_PATHS:
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
app.include_router(ocr.router)
app.include_router(api_next.router)
app.include_router(acm.router)
app.include_router(twin.router)
app.include_router(protocols.router)

# ─────────────────────────────────────────────────────────────────────────────
# ICD-10 LOOKUP
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/icd", response_class=HTMLResponse)
async def icd_lookup(request: Request):
    return templates.TemplateResponse("icd_lookup.html", {
        "request": request,
        "user": get_user(request),
    })


# ─────────────────────────────────────────────────────────────────────────────
# HOSPITALISATIONS — unit-wide view (all patients)
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/hospitalisations", response_class=HTMLResponse)
async def hospitalisations_index(
    request: Request,
    db: Session = Depends(get_db),
    patient_id: Optional[int] = None,
):
    from database import HospitalisationEvent, Patient as Pt
    user = get_user(request)
    # Build query — optionally filtered to one patient
    q = (
        db.query(HospitalisationEvent)
        .join(Pt, Pt.id == HospitalisationEvent.patient_id)
        .filter(Pt.is_active == True)
        .order_by(HospitalisationEvent.admission_date.desc())
    )
    if patient_id:
        q = q.filter(HospitalisationEvent.patient_id == patient_id)
    events_all = q.limit(200).all()
    patients_all = db.query(Pt).filter(Pt.is_active == True).order_by(Pt.name).all()
    return templates.TemplateResponse("hospitalisations_index.html", {
        "request": request,
        "user": user,
        "events": events_all,
        "patients": patients_all,
        "filter_patient_id": patient_id,
    })


# ─────────────────────────────────────────────────────────────────────────────
# CORE ROUTES (Dashboard)
# ─────────────────────────────────────────────────────────────────────────────

@app.head("/", include_in_schema=False)
async def dashboard_head():
    return HTMLResponse(content="")


@app.get("/run-migrations", include_in_schema=False)
async def run_migrations(secret: str = ""):
    """One-shot migration trigger. Protected by MIGRATE_SECRET env var."""
    expected = os.environ.get("MIGRATE_SECRET", "")
    if not expected or secret != expected:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Forbidden")
    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        capture_output=True, text=True
    )
    return {
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }

_DASHBOARD_EMPTY: dict = {
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
        "ipth_very_high": {"count": 0, "names": []},
        "infectious_hd": {"count": 0, "names": []},
        "avf_low_flow": {"count": 0, "names": []},
        "transplant_prospects": {"count": 0, "names": []},
        "cadaveric_listed": {"count": 0, "names": []},
        "avf_count": 0,
        "avg_count": 0,
        "epo_hypo":    {"count": 0, "names": []},
        "epo_hypo_r2": {"count": 0, "names": []},
        "epo_hypo_r3": {"count": 0, "names": [], "cutoff": None},
        "iv_iron_rec": {"count": 0, "names": []},
        "missing_records": {"count": 0, "names": []},
        "trend_hb": [],
        "trend_albumin": [],
        "trend_phosphorus": [],
        "avg_hb": None,
    },
    "patient_rows": [],
    "prev_month_label": "N/A",
    "total_active": 0,
}


@app.get("/", response_class=HTMLResponse)
async def dashboard_index(request: Request, month: Optional[str] = None, db: Session = Depends(get_db)):
    import asyncio
    from datetime import datetime as _dt

    # Auth check first — unauthenticated requests pay zero DB cost.
    user = get_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if getattr(user, "role", None) == "patient" or (isinstance(user, dict) and user.get("role") == "patient"):
        return RedirectResponse(url="/patient/dashboard", status_code=302)

    loop = asyncio.get_running_loop()

    # Wait for the startup warm-up to finish (max 8 s) so the first request
    # finds a warm cache instead of paying the full cold-compute cost itself.
    # After warm-up, the event stays set so subsequent requests skip this wait.
    if not _DASHBOARD_WARM_EVENT.is_set():
        await loop.run_in_executor(None, lambda: _DASHBOARD_WARM_EVENT.wait(timeout=8))

    # compute_dashboard uses synchronous SQLAlchemy.  Running it directly in an
    # async handler blocks the uvicorn event loop for the full query duration —
    # with a pool of 3 connections, two simultaneous requests would deadlock.
    # run_in_executor hands the work to the default ThreadPoolExecutor so the
    # event loop stays free to handle other requests while queries execute.
    def _sync_dashboard():
        m_str, d_note = get_effective_month(db, month)
        try:
            d = compute_dashboard(db, m_str)
            d["data_note"] = d_note
        except Exception as exc:
            logging.error("Dashboard error: %s", exc)
            d = dict(_DASHBOARD_EMPTY)
            d["month_label"] = get_month_label(m_str)
            d["data_note"] = d_note
        return m_str, d

    month_str, data = await loop.run_in_executor(None, _sync_dashboard)

    _current_month = get_current_month_str()
    hour = _dt.now().hour
    if hour < 12:
        greeting = "morning"
    elif hour < 17:
        greeting = "afternoon"
    else:
        greeting = "evening"

    pending_entry_count = data.get("metrics", {}).get("missing_records", {}).get("count", 0)

    high_risk_count = 0
    if getattr(user, "role", None) == "doctor" or (isinstance(user, dict) and user.get("role") == "doctor"):
        with _ML_ANALYTICS_LOCK:
            _cached_hr = _ML_ANALYTICS_CACHE.get("high_risk_count")
            _hr_stale  = not (_cached_hr and time.time() < _cached_hr[1])
        if _hr_stale:
            def _sync_hr():
                from ml_analytics import get_high_risk_mortality_count
                return get_high_risk_mortality_count(db)
            high_risk_count = await loop.run_in_executor(None, _sync_hr)
            with _ML_ANALYTICS_LOCK:
                _ML_ANALYTICS_CACHE["high_risk_count"] = (high_risk_count, time.time() + _ML_ANALYTICS_TTL)
        else:
            high_risk_count = _cached_hr[0]

    try:
        with _ML_ANALYTICS_LOCK:
            _cached_cohort = _ML_ANALYTICS_CACHE.get("cohort_analytics")
            _cohort_stale  = not (_cached_cohort and time.time() < _cached_cohort[1])
        if _cohort_stale:
            def _sync_cohort():
                from ml_analytics import run_cohort_analytics
                return run_cohort_analytics(db)
            cohort_data = await loop.run_in_executor(None, _sync_cohort)
            with _ML_ANALYTICS_LOCK:
                _ML_ANALYTICS_CACHE["cohort_analytics"] = (cohort_data, time.time() + _ML_ANALYTICS_TTL)
        else:
            cohort_data = _cached_cohort[0]
    except Exception as _ce:
        logging.warning("Cohort analytics failed: %s", _ce)
        cohort_data = {"available": False}

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
        "cohort_data": cohort_data,
    })

# Root health check — GET for humans, HEAD for UptimeRobot/monitoring probes
@app.api_route("/health", methods=["GET", "HEAD"])
async def health_check():
    from fastapi.responses import JSONResponse
    db_host = os.environ.get("DATABASE_URL", "").split("@")[-1].split("/")[0] if "@" in os.environ.get("DATABASE_URL", "") else "unknown"
    region = "Mumbai (ap-south-1)" if "ap-south-1" in db_host else ("Tokyo (ap-northeast-1)" if "ap-northeast-1" in db_host else db_host)
    try:
        _db = SessionLocal()
        t0 = time.time()
        _db.execute(text("SELECT 1"))
        db_latency_ms = round((time.time() - t0) * 1000, 1)
        _db.close()
        db_status = "ok"
    except Exception as e:
        db_latency_ms = None
        db_status = str(e)

    payload = {
        "status": "ok" if _APP_READY else "starting",
        "ready": _APP_READY,
        "version": "2.0.0",
        "db_region": region,
        "db_host": db_host,
        "db_latency_ms": db_latency_ms,
        "db_status": db_status,
    }
    # Return 503 while startup is still running so Render doesn't route live
    # traffic to an instance that hasn't finished table creation / seeding.
    status_code = 200 if _APP_READY else 503
    return JSONResponse(content=payload, status_code=status_code)

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
