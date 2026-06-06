# Claude Agent Memory — HD Dashboard

> **How to use this folder:**
> When starting any new coding task on this application, read the relevant
> agent memory file(s) listed below **before** making any changes.  Each file
> is a self-contained knowledge snapshot.  They are living documents — update
> them whenever architecture, clinical decisions, DB schema, or ML pipelines
> change significantly.
>
> Last updated: 2026-06-01

---

## Memory Files Index

| File | What it covers | When to read |
|------|---------------|--------------|
| [01_architecture.md](01_architecture.md) | Full-stack layout, middleware, routers, authentication, deployment | Any new feature / routing change |
| [02_database_schema.md](02_database_schema.md) | All SQLAlchemy models, relationships, key columns, Alembic migration state | Any DB change, new model, new column |
| [03_clinical_workflow.md](03_clinical_workflow.md) | Clinical information architecture: patient lifecycle, data-entry flow, KDIGO targets | Data-entry forms, alerts, event logging |
| [04_ml_pipelines.md](04_ml_pipelines.md) | All ML models: deterioration risk, IDH, ACM/ODE, mortality risk, feature stores | Any ML model change, retraining, inference |
| [05_digital_twin.md](05_digital_twin.md) | Digital Dialysis Twin: 5-domain physics, Bayesian priors, run_scenario(), Plotly | Any digital twin UI or model change |
| [06_celery_mlops.md](06_celery_mlops.md) | Celery beat schedule, MLOps tasks, drift detection, feature store refresh | Background tasks, scheduled jobs |
| [07_frontend_api.md](07_frontend_api.md) | Next.js / Jinja2 split, API contract, auth flow, multi-tenancy | Frontend pages, API endpoints |
| [08_analytics_alerts.md](08_analytics_alerts.md) | Cohort analytics, mortality risk, alert rules, WhatsApp/email notifications | Analytics dashboard, alert system |
| [09_vascular_access.md](09_vascular_access.md) | Access surveillance, KRCRw model, Doppler workflow, bedside screen | Vascular access forms, IDH features |
| [10_known_issues_next_steps.md](10_known_issues_next_steps.md) | Bugs, gaps, phase-2 roadmap, clinical validation targets | Before planning any major feature |

---

## Specialized Subagent Roles

When tackling a specific type of task, you can ask Claude to adopt one of these specialized subagent personas:

| Subagent File | Specialized Persona | Focus Area |
|---------------|---------------------|------------|
| [db_migrator.md](subagents/db_migrator.md) | Database Migrator & Schema Agent | alembic migrations, database.py, DB schemas, PostgreSQL |
| [twin_simulator.md](subagents/twin_simulator.md) | Digital Twin Simulator Agent | ml_twin.py, ODE models, scenarios, Plotly dashboard |
| [clinical_safety_controller.md](subagents/clinical_safety_controller.md) | Clinical Safety & Validation Agent | alerts.py, KDIGO rules, validation_engine.py, medical safety |
| [ml_ops_pipeline_engineer.md](subagents/ml_ops_pipeline_engineer.md) | ML & MLOps Pipeline Agent | XGBoost training, celery tasks, model drift, artifacts registry |
| [frontend_ui_developer.md](subagents/frontend_ui_developer.md) | Frontend UI & Clinical UX Agent | Jinja2 templates, static CSS, Next.js dashboard, form calculators |

---

## Project One-Liner

> **HD Dashboard** is a FastAPI + Jinja2 / Next.js nephrology clinical dashboard
> for an Indian haemodialysis unit.  It integrates rule-based KDIGO alerts,
> a hybrid ODE+MLP Anemia Control Model (ACM), an XGBoost IDH predictor,
> a calibrated logistic regression deterioration/mortality risk engine, and a
> 5-domain Digital Dialysis Twin — all connected to a Supabase PostgreSQL
> backend with row-level security and a weekly Celery MLOps pipeline.

---

## Required DB Schema Version

```
REQUIRED_DB_VERSION = "8b92695a7472"   # main.py
```

Run `alembic upgrade head` (or `scripts/pre_deploy.py`) before booting after
any migration.

---

## Key Environment Variables

| Var | Purpose |
|-----|---------|
| `DATABASE_URL` | Supabase PostgreSQL connection string |
| `SECRET_KEY` | Cookie signing (itsdangerous) |
| `REDIS_URL` | Celery broker |
| `REDIS_BACKEND` | Celery result store (separate DB index) |
| `SMTP_HOST/PORT/USER/PASSWORD` | Ward email alerts |
| `DOCTOR_EMAIL` | Daily data-integrity report target |
| `ADMIN_EMAIL` | ML drift alert target |
| `TWILIO_ACCOUNT_SID/AUTH_TOKEN/FROM_NUMBER` | WhatsApp alerts |
| `MIGRATE_SECRET` | One-shot `/run-migrations` endpoint guard |
| `COOKIE_SECURE` | Set `true` in production (HTTPS) |

---

## Deployment

- **Platform**: Render (Web Service + Redis)
- **Pre-deploy**: `python scripts/pre_deploy.py` (runs `alembic upgrade head`)
- **Start command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- **Celery**: separate Render worker process (see `Procfile`)
- **Config**: `render.yaml`, `nixpacks.toml`, `runtime.txt`
