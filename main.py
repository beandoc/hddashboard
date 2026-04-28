from fastapi import FastAPI, Depends, Request, Form, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from typing import Optional
import logging

from database import engine, Base, get_db, Patient
from config import templates
from dependencies import get_user
from dashboard_logic import compute_dashboard, get_current_month_str, get_month_label
from routers import auth, patients, entry, sessions, analytics, events, variables, admin, patient_portal, schedule, alerts

# ─────────────────────────────────────────────────────────────────────────────
# APP INITIALIZATION
# ─────────────────────────────────────────────────────────────────────────────

# Create DB tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Hemodialysis Dashboard", version="2.0.0")

# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Routers
app.include_router(auth.router)
app.include_router(patients.router)
app.include_router(entry.router)
app.include_router(sessions.router)
app.include_router(analytics.router)
app.include_router(events.router)
app.include_router(variables.router)
app.include_router(admin.router)
app.include_router(patient_portal.router)
app.include_router(schedule.router)
app.include_router(alerts.router)

# ─────────────────────────────────────────────────────────────────────────────
# CORE ROUTES (Dashboard)
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard_index(request: Request, month: Optional[str] = None, db: Session = Depends(get_db)):
    month_str = month or get_current_month_str()
    try:
        data = compute_dashboard(db, month_str)
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
            "patient_rows": [], 
            "month_label": get_month_label(month_str),
            "prev_month_label": "N/A", 
            "total_active": 0
        }
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "data": data,
        "month_str": month_str,
        "current_month": get_current_month_str(),
        "user": get_user(request),
    })

# Root health check
@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "2.0.0"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
