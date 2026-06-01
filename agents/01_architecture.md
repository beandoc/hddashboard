# 01 — Full-Stack Architecture

> Agent memory file · HD Dashboard · Last updated 2026-06-01

---

## Technology Stack

| Layer | Technology | Details |
|-------|------------|---------|
| Backend framework | FastAPI 2.0 | `main.py` — uvicorn ASGI |
| Templating | Jinja2 | Data-entry forms only — see §Frontend Split |
| Frontend | Next.js (TypeScript) | `/frontend/` — read dashboards only |
| Database | PostgreSQL (Supabase) | SQLAlchemy ORM + Alembic migrations |
| Background tasks | Celery + Redis | `celery_app.py` + `tasks.py` |
| Auth | itsdangerous cookies | Session-based, 8 h absolute + 2 h idle TTL |
| Static assets | `/static/` | Mounted via StaticFiles |
| Deployment | Render | Web Service + Celery worker |

---

## Application Boot Sequence (`main.py`)

```
lifespan()  →  threading.Thread(_background_startup)
                   create_tables()
                   _check_schema_version()   # must match REQUIRED_DB_VERSION
                   _seed_default_users()
             →  _warm_caches()  (two parallel daemon threads)
                   _warm_dashboard()         → compute_dashboard(db)
                   _warm_ml()               → get_all_patients_mortality_risk(db)
                                            → run_cohort_analytics(db)
```

**Health probe**: `GET /health` returns `{"status": "ok"}` (200) or `{"status": "starting"}` (503) while `_APP_READY = False`.

---

## Middleware Stack (order matters)

1. **CORSMiddleware** — allows `localhost:3000/3001/8080` + `hddashboard.onrender.com`
2. **RewriteLoginMiddleware** — rewrites `POST /login` → `POST /api/login` for JSON content-type (Next.js auth)
3. **StaticCacheMiddleware** — adds `Cache-Control` headers to `/static/` assets
4. **slowapi RateLimitExceeded** handler
5. **auth_middleware** (HTTP middleware) — validates `hd_session` cookie, enforces idle TTL, refreshes sliding window

---

## Session Auth Design

- Cookie name: `hd_session`
- Payload format: `"{user_type}:{username}:{last_active_ts}"` signed with URLSafeTimedSerializer
- Two user types: `"staff"` (User ORM row) and `"patient"` (Patient ORM row)
- **Identity cache**: `_USER_IDENTITY_CACHE` — 120 s TTL, avoids DB round-trip per request
- **Invalidation**: `_invalidate_user_cache(username)` on logout or role change
- Absolute TTL: `SESSION_MAX_AGE` (default 8 h, set in `config.py`)
- Idle TTL: `SESSION_IDLE_TTL` (default 2 h)

---

## Router Registry (`main.py`)

```python
app.include_router(auth.router)           # /login, /logout, /change-password
app.include_router(patients.router)       # /patients/*, CRUD
app.include_router(entry.router)          # /entry/{patient_id}  (monthly data entry)
app.include_router(sessions.router)       # /sessions/* (dialysis session records)
app.include_router(sessions.session_router)
app.include_router(analytics.router)      # /analytics/*
app.include_router(analytics.root_router)
app.include_router(events.router)         # /events/*
app.include_router(variables.router)      # /variables/*
app.include_router(admin.router)          # /admin/*
app.include_router(patient_portal.router) # /patient/*
app.include_router(schedule.router)       # /schedule/*
app.include_router(alerts.router)         # /alerts/*
app.include_router(sustainability.router) # /sustainability/*
app.include_router(fluid_status.router)   # /fluid/*
app.include_router(admin_analytics.router)
app.include_router(research.router)       # /research/*
app.include_router(api_v1.router)         # /api/v1/*  (consumed by Next.js)
app.include_router(ocr.router)            # /ocr/*
app.include_router(api_next.router)       # /api/*     (additional Next.js APIs)
app.include_router(acm.router)            # /acm/*     (Anemia Control Model)
app.include_router(twin.router)           # /twin/*    (Digital Twin)
```

Inline routes on `app`:
- `GET /` → `dashboard.html` (Jinja2 dashboard)
- `GET /health` → readiness probe
- `GET /hospitalisations` → all-patient hospitalisation view
- `GET /icd` → ICD-10 lookup
- `GET /run-migrations?secret=` → one-shot Alembic upgrade

---

## ML Analytics Cache (in `main.py`)

```python
_ML_ANALYTICS_CACHE  = {}    # dict: key → (value, expiry_ts)
_ML_ANALYTICS_LOCK   = threading.Lock()
_ML_ANALYTICS_TTL    = 300   # 5 minutes
```

Populated at startup by `_warm_ml()`. Refreshed on cache miss by the dashboard route.
Keys: `"high_risk_count"`, `"cohort_analytics"`.

---

## Frontend Split (Architectural Boundary)

| Responsibility | Technology | Rule |
|----------------|------------|------|
| Data-entry forms | Jinja2 server-render | Validators run server-side before any DB write |
| Read dashboards | Next.js `/api/v1/*` | Client-side SWR, never call legacy `/analytics/api/*` |

**Never migrate** entry forms to Next.js — server-side validation is a deliberate safety feature.

---

## File Structure (Root-level key files)

```
main.py                  — FastAPI app, middleware, boot, dashboard route
config.py                — templates, serializer, pwd_context, limiter, cookie config
database.py              — legacy re-export of all ORM models + SessionLocal
db/
  engine.py              — create_engine(), SessionLocal, Base, set_tenant_context()
  models/
    patient.py           — Patient + 8 satellite 1:1 tables
    sessions.py          — SessionRecord, InterimLabRecord, AlertLog
    records.py           — MonthlyRecord, DryWeightAssessment, etc.
    clinical.py          — ClinicalEvent, HospitalisationEvent, AccessSurveillanceRecord
    ml.py                — MLPrediction, MLModelMetrics, ModelArtifact, ACMRecommendation, TwinSimulation
    auth.py              — User
    nutrition.py         — PatientMealRecord, PatientSymptomReport
    research.py          — ResearchRecord, ResearchProject
routers/                 — 21 router modules (see registry above)
services/                — 9 service modules (business logic separated from routers)
templates/               — Jinja2 HTML templates
static/                  — CSS, JS, images
frontend/                — Next.js app (TypeScript)
ml_*.py                  — ML inference/training modules (7 files)
tasks.py                 — Celery task definitions
celery_app.py            — Celery app config + beat schedule
alembic/                 — DB migrations
models/                  — Trained model artifacts (.joblib, .json, ode_params/)
```

---

## Multi-tenancy

- `db/engine.py::set_tenant_context(tenant_id)` — executes `SET LOCAL app.tenant_id = '...'` before queries
- Row-Level Security (RLS) policies live at Supabase level (not in SQLAlchemy models)
- Next.js passes tenant subdomain as HTTP header; FastAPI middleware reads and sets PG session variable
- Frontend has zero tenant-specific logic — isolation is fully at DB layer

---

## Config (`config.py`)

- `templates` — Jinja2 `TemplateResponse` factory
- `serializer` — `URLSafeTimedSerializer` for cookie signing
- `pwd_context` — `bcrypt` for password hashing
- `limiter` — slowapi rate limiter (applied per-route with `@limiter.limit(...)`)
- `COOKIE_SECURE` — read from env; must be `true` in production
- `SESSION_MAX_AGE` — absolute TTL in seconds (default 28800 = 8 h)
- `SESSION_IDLE_TTL` — idle TTL in seconds (default 7200 = 2 h)
