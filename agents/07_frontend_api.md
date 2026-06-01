# 07 — Frontend & API Layer

> Agent memory file · HD Dashboard · Last updated 2026-06-01

---

## The Architectural Boundary (Do Not Cross)

| Responsibility | Technology | Rule |
|---|---|---|
| **Data-entry forms** | Jinja2 server-rendered HTML | Server validation fires before DB write — never migrate to Next.js |
| **Read dashboards** | Next.js → `/api/v1/*` | Client-side SWR, richer charts — never call legacy `/analytics/api/*` |

---

## Jinja2-Owned Routes (Never Migrate)

| Route | Template | Router file |
|---|---|---|
| `GET / POST /entry/{patient_id}` | `entry_form.html` | `routers/entry.py` |
| `GET /entry/list` | `entry_list.html` | `routers/entry.py` |
| `GET/POST /patients/new` | `patient_form.html` | `routers/patients.py` |
| `GET/POST /patients/{id}/edit` | `patient_form.html` | `routers/patients.py` |
| `GET/POST /events/{patient_id}` | `events.html` | `routers/events.py` |
| `GET/POST /med-recon/{patient_id}` | `med_recon.html` | `routers/entry.py` |
| `GET/POST /fluid/{patient_id}` | `fluid_status.html` | `routers/fluid_status.py` |
| `GET /login` | `login.html` | `routers/auth.py` |
| `GET /change-password` | `change_password.html` | `routers/auth.py` |
| `GET /variables/manager` | `variable_manager.html` | `routers/variables.py` |
| `GET/POST /access-surveillance/{patient_id}` | `access_surveillance_form.html` | `routers/patients.py` |

---

## Next.js-Owned Routes (Current)

| Next.js route | API endpoint consumed | Replaces Jinja2 template |
|---|---|---|
| `/` (dashboard) | `GET /api/v1/dashboard` | `dashboard.html` |
| `/patients` | `GET /api/v1/patients` | `patients.html` |
| `/patients/[id]` | `GET /api/v1/patients/{id}/profile` | `patient_profile.html` |
| `/analytics` | `GET /api/v1/cohort-trends` | `analytics_hub.html` |
| `/analytics/patients` | `GET /api/v1/patients?analytics=1` | `analytics_patients.html` |
| `/analytics/mortality` | `GET /api/v1/patients/mortality-risk` | `mortality_risk.html` |
| `/research` | `GET /api/v1/research/projects` | `research_hub.html` |

---

## API Endpoints (`routers/api_v1.py` + `routers/api_next.py`)

### Core Patient Data
- `GET /api/v1/patients` — paginated patient list
- `GET /api/v1/patients/{id}/profile` — full patient profile (all satellites)
- `GET /api/v1/patients/{id}/feature-history` — feature snapshots per month (MLOps audit)
- `GET /api/v1/patients/mortality-risk` — all-patient XGBoost mortality scores
- `GET /api/v1/dashboard` — dashboard KPIs (cached, 5 min TTL)
- `GET /api/v1/cohort-trends` — Hb/albumin/phosphorus trends

### ACM / Digital Twin
- `GET /acm/{patient_id}` — generate ACM recommendation for current month
- `POST /acm/{patient_id}/decide` — clinician accept/modify/reject
- `GET /acm/audit` — fleet calibration: reliability diagram, ESA dose-response
- `GET /twin/{patient_id}` — load Digital Twin page (baseline scenario)
- `POST /twin/{patient_id}/simulate` — run a new scenario (JSON body = scenario params)
- `GET /twin/{patient_id}/history` — previously saved scenarios

### Admin
- `POST /admin/train-deterioration-model`
- `POST /analytics/admin/train-idh-model`
- `GET /admin/model-status`
- `GET /admin/users`
- `POST /admin/users/{username}/deactivate`

---

## Authentication Flow (Next.js ↔ FastAPI)

1. User POSTs credentials to `POST /login` (Jinja2) or `POST /api/login` (JSON)
2. FastAPI verifies password with bcrypt, sets `hd_session` cookie
3. Next.js passes `credentials: "include"` on every `fetch()` — cookie sent automatically
4. FastAPI `auth_middleware` validates cookie on every request (120 s identity cache)
5. Logout: `POST /logout` — invalidates cookie + `_USER_IDENTITY_CACHE`

**Cookie format**: `"{user_type}:{username}:{last_active_ts}"` signed with `URLSafeTimedSerializer`

**Two user roles in cookie**: `"staff"` (clinic staff/doctor) and `"patient"` (patient portal)

**Role-based access** in Jinja2 routes: `get_user(request)` returns the user object; `user.role` checked inline (`"admin"` | `"staff"` | `"doctor"` | `"patient"`).

---

## API Contract Rules

1. All Next.js pages consume `/api/v1/*` **exclusively**
2. Never call `/analytics/api/*` from Next.js — those are legacy Jinja2 aliases
3. All API responses are JSON; Jinja2 routes return HTML
4. All authenticated endpoints check `get_user(request)` and return 302 to `/login` if null

---

## Multi-tenancy in API Layer

- Tenant subdomain passed from Next.js as HTTP header (`X-Tenant-ID` or similar)
- FastAPI middleware reads header → calls `set_tenant_context(tenant_id)` → `SET LOCAL app.tenant_id`
- All SQL queries are automatically filtered by RLS at PostgreSQL level
- Next.js has **zero** tenant logic — fully DB-layer concern

---

## Next.js Frontend Structure (`/frontend/`)

```
frontend/
  pages/ (or app/)     — Next.js route pages
  components/           — Reusable React components
  lib/
    api.ts              — fetch wrapper with credentials: "include"
  styles/               — CSS modules / global styles
  public/               — Static assets
  next.config.js        — Proxy config for /api/* → FastAPI in dev
  package.json          — npm dependencies
```

**Dev proxy**: `next.config.js` rewrites `/api/*` → `http://localhost:8080/api/*` in development so Next.js and FastAPI run on different ports without CORS issues.

**Build**: `npm run build` in `/frontend/` produces static export.
**Dev**: `npm run dev` on port 3000 (or 3001 if 3000 occupied).

---

## OCR Integration (`routers/ocr.py`)

- `POST /ocr/upload` — multipart form with lab report image
- `services/ocr_service.py` — uses `pytesseract` for initial extraction, then `google-genai` to structure results
- Returns: structured JSON of lab values mapped to `monthly_records` column names
- Frontend (entry form): "Upload Report" button → OCR → pre-fills form fields

---

## Patient Portal Frontend (`routers/patient_portal.py`)

Separate mini-app for patients:
- `GET /patient/dashboard` — patient's own summary
- `GET /patient/meals` — food diary (24h / 3-day recall)
- `POST /patient/meals` — log meal → `patient_meal_records` table
- `GET /patient/symptoms` — symptom history
- `POST /patient/symptoms` — log post-dialysis symptoms → `patient_symptom_reports`
- `GET /patient/appointments` — view HD schedule

**Auth**: Same cookie, but `user_type = "patient"` in payload. Patients are redirected to `/patient/dashboard` instead of `/` on login.

---

## Sustainability Module (`routers/sustainability.py`)

Environmental impact reporting:
- Water consumption per session
- Carbon footprint estimates
- `GET /sustainability/report`
- Template: `sustainability.html`

---

## Research Module (`routers/research.py`)

- `GET /research/hub` — research project list
- `GET/POST /research/projects/{id}` — project detail / enrolment
- De-identified data exports for IRB-approved projects
- Linked to `research_records` and `research_projects` tables
