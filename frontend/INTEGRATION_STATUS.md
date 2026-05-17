# Frontend Integration Status

## Current state

The Next.js app in this directory is **not deployed**. `render.yaml` only runs
the Python/Jinja2 backend. The frontend is built but has never served production
traffic.

## Auth incompatibility

| Layer | Mechanism |
|---|---|
| Jinja2 backend | Session cookie (`itsdangerous` signed token) |
| Next.js `apiFetch()` | `Authorization: Bearer <token>` from `localStorage` |

The backend has no token-issuance endpoint. Hitting any `/api/v1/*` route from
the React client will return **403** because the session cookie won't be present.
Resolving this requires either: (a) adding a `/api/v1/token` endpoint that issues
a JWT the frontend can store, or (b) switching the frontend to a cookie-based
flow with CSRF protection.

## Missing backend endpoints

The frontend calls these routes which **do not exist** on the backend:

| Frontend call | File | Status |
|---|---|---|
| `POST /api/entries/bulk` | `src/app/entry/page.tsx` | Not implemented |
| `GET /api/patients/{id}/timeline` | `src/app/patients/[id]/page.tsx` | Not implemented |
| `POST /api/send-schedule/{id}` | `src/components/Shell.tsx` | Not implemented |

## What does exist — versioned API

`/api/v1/` endpoints (session-cookie auth, OpenAPI schema at `/docs`):

- `GET /api/v1/patients` — patient list with optional name filter
- `GET /api/v1/dashboard` — current-month aggregate stats
- `GET /api/v1/cohort-trends` — population-level trend data
- `GET /api/v1/at-risk-trends?parameter=hb` — at-risk counts by parameter
- `GET /api/v1/patients/{id}/latest-monthly` — latest monthly record
- `GET /api/v1/schema-version` — version handshake

The unversioned equivalents under `/analytics/api/*` remain for the existing
Jinja2 inline JS and should not be removed until those templates are migrated.

## Recommended path to deploy the frontend

1. Add `POST /api/v1/token` (issues a short-lived JWT from valid session credentials)
2. Add the three missing endpoints above
3. Add a `services` entry in `render.yaml` for Node.js, pointing at this directory
4. Set `NEXT_PUBLIC_API_URL` to the Python service URL in Render env vars
