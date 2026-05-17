# Frontend Architecture

## The cutline

Two rendering technologies coexist. The boundary is permanent and explicit:

| Responsibility | Technology | Why |
|---|---|---|
| **Data-entry forms** | Jinja2 + server-rendered HTML | Server validation is a feature — hard/soft thresholds fire before the form submits, reducing round-trips and preventing bad data at the edge |
| **Read dashboards & patient profile** | Next.js → `/api/v1/*` | React state + SWR enables real-time refresh, client-side filtering, and richer interactive charts without a full page reload |

## Jinja2 owns (do not migrate)

These routes render HTML on the server and handle `POST` form submissions:

| Route | Template | Reason |
|---|---|---|
| `GET/POST /entry/{patient_id}` | `entry_form.html` | Monthly data-entry — validators.py hard limits run server-side |
| `GET /entry/list` | `entry_list.html` | Entry queue — clinical workflow, not a dashboard |
| `GET/POST /patients/new` | `patient_form.html` | Registration form with cascading validation |
| `GET/POST /patients/{id}/edit` | `patient_form.html` | Same |
| `GET/POST /events/{patient_id}` | `events.html` | Clinical event log entry |
| `GET/POST /med-recon/{patient_id}` | `med_recon.html` | Medication reconciliation form |
| `GET/POST /fluid/{patient_id}` | `fluid_status.html` | Fluid status assessment form |
| `GET /change-password` | `change_password.html` | Auth — stays server-rendered |
| `GET /login` | `login.html` | Auth — stays server-rendered |
| `GET /variables/manager` | `variable_manager.html` | Variable config UI — form-heavy |

## Next.js owns (migrate from Jinja2)

These are read-heavy dashboards that benefit from React's client-side interactivity:

| Route (Next.js) | Replaces Jinja2 template | API endpoint |
|---|---|---|
| `/` (dashboard) | `dashboard.html` | `GET /api/v1/dashboard` |
| `/patients` | `patients.html` | `GET /api/v1/patients` |
| `/patients/[id]` | `patient_profile.html` | `GET /api/v1/patients/{id}/profile` |
| `/analytics` | `analytics_hub.html` | `GET /api/v1/cohort-trends` |
| `/analytics/patients` | `analytics_patients.html` | `GET /api/v1/patients?analytics=1` |
| `/analytics/mortality` | `mortality_risk.html` | `GET /api/v1/patients/mortality-risk` |
| `/research` | `research_hub.html` | `GET /api/v1/research/projects` |

## Deletion schedule

Once each Next.js page ships and is verified in production, delete the corresponding Jinja2 template **and** remove its router endpoint (or convert it to a `301` redirect to the Next.js URL). Do not run both in parallel longer than one release cycle — dual maintenance is the failure mode we are avoiding.

## API contract

All Next.js pages consume `/api/v1/*` exclusively. Never call `/analytics/api/*` (legacy aliases) from Next.js — those exist only for backward compatibility with Jinja2 templates and will be removed when Jinja2 dashboard templates are deleted.

Next.js passes the session cookie via `credentials: "include"` on every fetch (see `lib/api.ts`). The FastAPI session middleware validates it identically to Jinja2 routes — no separate auth token needed.

## Multi-tenancy

When multi-tenancy is active, the tenant_id is injected by FastAPI middleware into `SET LOCAL app.tenant_id` before every async DB query. The Next.js frontend passes the tenant subdomain as a request header; the middleware reads it and sets the PostgreSQL session variable. The Next.js app itself has no tenant-specific logic — isolation is enforced at the DB layer via RLS.

## What to delete right now

The following are dead weight with no production user:

```
frontend/INTEGRATION_STATUS.md   — replaced by this file
```

The `scratch/` directory (20 debug scripts) should be deleted entirely — none are imported by production code.
