# Claude Developer Guide — HD Dashboard

This guide provides the core commands, architectural conventions, and code styles for the HD Dashboard application. Always read this file and refer to the specialized agent memory in [agents/README.md](file:///Users/sachinsrivastava/Downloads/HD%20Dashboard/agents/README.md) before making modifications.

---

## 🛠️ Build & Run Commands

### Backend (FastAPI)
- **Install dependencies**: `pip install -r requirements.txt` (or update `requirements.in` and run `pip-compile`)
- **Run development server**: `uvicorn main:app --reload --port 8000`
- **Database migrations**: Run `python scripts/pre_deploy.py` (which runs `alembic upgrade head`)
  > [!WARNING]
  > Never run `alembic` commands that introspect live schema inside sandbox environments as it might trigger access errors. Use raw sql or `sqlalchemy.inspect` for introspection.
- **Pre-deployment checks**: `python scripts/pre_deploy.py`

### Frontend (Next.js)
- **Install dependencies**: `npm install` (run in `frontend/`)
- **Run development server**: `npm run dev` (run in `frontend/`)
- **Build production bundle**: `npm run build` (run in `frontend/`)
- **Lint check**: `npm run lint` (run in `frontend/`)

---

## 🧪 Testing Commands

- **Run all Python tests**: `pytest`
- **Run a specific test file**: `pytest tests/test_clinical_logic.py`
- **Run tests and print output**: `pytest -s`
- **Verify migrations**: `pytest tests/test_twin_upgrade.py`

---

## 🛡️ Critical Guidelines & Protected Files

### Protected Files (DO NOT MODIFY DIRECTLY)
The following core engine files are locked to prevent clinical logic breakdown or production failure:
- [dashboard_logic.py](file:///Users/sachinsrivastava/Downloads/HD%20Dashboard/dashboard_logic.py) — clinical calculations
- [database.py](file:///Users/sachinsrivastava/Downloads/HD%20Dashboard/database.py) — SQLAlchemy models
- [alerts.py](file:///Users/sachinsrivastava/Downloads/HD%20Dashboard/alerts.py) — deterministic KDIGO alert rules
- [ml_analytics.py](file:///Users/sachinsrivastava/Downloads/HD%20Dashboard/ml_analytics.py) — core ML risk engines
- [dynamic_vars.py](file:///Users/sachinsrivastava/Downloads/HD%20Dashboard/dynamic_vars.py) — dynamic patient variables system

*To add features:* Create a new module (e.g., `services/my_feature.py`), expose it via `routers/`, or import/subclass within safe areas.

### Database Constraints
- The `REQUIRED_DB_VERSION` is defined in [main.py](file:///Users/sachinsrivastava/Downloads/HD%20Dashboard/main.py). It must match the current migration head.
- Ensure any database schema modifications have a corresponding Alembic migration and are manually verified before pushing.

### Clinical Safety & Verification Guardrails
1. **Never bypass KDIGO validation**: Any code writing dialysis session records, patient forms, or lab results MUST validate inputs against [validation_engine.py](file:///Users/sachinsrivastava/Downloads/HD%20Dashboard/validation_engine.py).
2. **Physiological bounds checks**: Ensure entered values (e.g. dialysate temp, cardiac output parameters) lie within reasonable human limits. Extreme values must trigger warning indicators, not app crashes.
3. **Log critical alerts**: When warning flags or deterioration risks spike, verify that a corresponding entry is created in `patient_alerts` and the appropriate ward notification routine is called.

---

## ✍️ Code Style & Conventions

### Python (Backend)
- **Typing**: Use PEP 484 type hints for all new function definitions (e.g., `def calculate_ktv(volume: float, clearance: float) -> float:`).
- **Database Sessions**: Always use dependency injection (`db: Session = Depends(get_db)`) in FastAPI router paths. Always wrap manual database transactions in `try...except` and ensure the session is properly closed.
- **Error Handling**: Use HTTP exceptions (`HTTPException(status_code=400, detail=...)`) for client errors. Use structured logging for unexpected backend errors.

### Frontend (Next.js / HTML Templates)
- **Next.js**: Refer to [AGENTS.md](file:///Users/sachinsrivastava/Downloads/HD%20Dashboard/frontend/AGENTS.md) when writing TSX. Use strict typescript rules and proper layouts.
- **Templates**: Jinja2 templates are in [templates/](file:///Users/sachinsrivastava/Downloads/HD%20Dashboard/templates/). Ensure forms use correct CSRF protection and CSS classes match the dark-mode glassmorphic theme.
