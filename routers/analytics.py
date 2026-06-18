from fastapi import APIRouter, Depends, Request, HTTPException, Form, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session
from typing import Optional
import asyncio
import logging

from datetime import date, datetime, timedelta
from database import get_db, SessionLocal, Patient, ClinicalEvent, SessionRecord, MonthlyRecord, MLModelMetrics
from config import templates, _csrf_signer
from dependencies import get_user, _require_analytics_access
from dashboard_logic import compute_dashboard, get_current_month_str, get_effective_month
# Heavy ML modules are deferred to first use so they don't block startup.
# The _LazyModule proxy is transparent — attr access triggers the real import
# exactly once, then delegates every subsequent access directly to the module.
class _LazyModule:
    __slots__ = ("_name", "_mod")
    def __init__(self, name): self._name = name; self._mod = None
    def __getattr__(self, attr):
        if attr in ("_name", "_mod"): raise AttributeError(attr)
        if self._mod is None:
            import importlib
            object.__setattr__(self, "_mod", importlib.import_module(self._name))
        return getattr(self._mod, attr)

_ml_analytics = _LazyModule("ml_analytics")
_ml_risk      = _LazyModule("ml_risk")
_ml_idh       = _LazyModule("ml_idh")

# Local aliases — same names the handlers already use, zero handler changes needed.
def run_patient_analytics(*a, **kw):      return _ml_analytics.run_patient_analytics(*a, **kw)
def analyze_bfr_trend(*a, **kw):          return _ml_analytics.analyze_bfr_trend(*a, **kw)
def analyze_idwg_velocity(*a, **kw):      return _ml_analytics.analyze_idwg_velocity(*a, **kw)
def analyze_pds(*a, **kw):                return _ml_analytics.analyze_pds(*a, **kw)
def analyze_mia_cascade(*a, **kw):        return _ml_analytics.analyze_mia_cascade(*a, **kw)
def analyze_cardiorenal_cascade(*a, **kw): return _ml_analytics.analyze_cardiorenal_cascade(*a, **kw)
def analyze_avf_maturation(*a, **kw):     return _ml_analytics.analyze_avf_maturation(*a, **kw)
def detect_occult_overload(*a, **kw):     return _ml_analytics.detect_occult_overload(*a, **kw)
def get_all_patients_mortality_risk(*a, **kw): return _ml_analytics.get_all_patients_mortality_risk(*a, **kw)
def run_cohort_analytics(*a, **kw):       return _ml_analytics.run_cohort_analytics(*a, **kw)
def get_deterioration_model_status(*a, **kw): return _ml_risk.get_deterioration_model_status(*a, **kw)
def get_idh_model_status(*a, **kw):       return _ml_idh.get_idh_model_status(*a, **kw)
def compute_idh_risk(*a, **kw):           return _ml_idh.compute_idh_risk(*a, **kw)

from constants import EVENT_TYPES, EVENT_TYPE_GROUPS

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/analytics", tags=["analytics"])
root_router = APIRouter(tags=["clinical-review"])

@router.get("/hb-variability", response_class=HTMLResponse)
@router.get("/hb-variability/", response_class=HTMLResponse)
async def hb_variability_report(request: Request, month: Optional[str] = None, db: Session = Depends(get_db)):
    _require_analytics_access(request)
    from dashboard_logic import compute_dashboard
    month_str, _ = get_effective_month(db, month)
    data = compute_dashboard(db, month_str)
    patient_rows = data.get("patient_rows", [])
    valid_rows = [r for r in patient_rows if r.get("hb_var_range") is not None]
    valid_rows.sort(key=lambda x: x["hb_var_range"], reverse=True)
    high_var = [r for r in valid_rows if r["hb_var_range"] > 2.5]
    stable = [r for r in valid_rows if r["hb_var_range"] <= 2.5]
    return templates.TemplateResponse("hb_variability_report.html", {
        "request": request, "month_str": month_str, "high_var": high_var, "stable": stable, "user": get_user(request)
    })

@router.get("/adherence", response_class=HTMLResponse)
@router.get("/adherence/", response_class=HTMLResponse)
async def adherence_report(request: Request, month: Optional[str] = None, db: Session = Depends(get_db)):
    _require_analytics_access(request)
    from dashboard_logic import compute_dashboard
    month_str, _ = get_effective_month(db, month)
    data = compute_dashboard(db, month_str)
    patient_rows = data.get("patient_rows", [])
    at_risk = [r for r in patient_rows if r.get("adherence_flags")]
    at_risk.sort(key=lambda x: len(x["adherence_flags"]), reverse=True)

    # Calculate stats for the dashboard summary
    skipped_count = sum(1 for r in at_risk if "Skipped Sessions" in r.get("adherence_flags", []))
    shortened_count = sum(1 for r in at_risk if "Shortened Sessions" in r.get("adherence_flags", []))

    return templates.TemplateResponse("adherence_report.html", {
        "request": request, 
        "month_str": month_str, 
        "at_risk": at_risk, 
        "skipped_count": skipped_count,
        "shortened_count": shortened_count,
        "user": get_user(request)
    })

@router.get("/census", response_class=HTMLResponse)
async def census_report(request: Request, month: Optional[str] = None, db: Session = Depends(get_db)):
    _require_analytics_access(request)
    from sqlalchemy.orm import joinedload
    month_str, _ = get_effective_month(db, month)

    # Eager-load outcomes in 2 queries (patients + outcomes IN-batch) to avoid
    # N+1 lazy loads when accessing current_survival_status / date_of_death
    patients = db.query(Patient).options(joinedload(Patient.outcomes)).all()
    active_patients = [p for p in patients if p.is_active]

    new_regs = [p for p in patients if p.created_at and p.created_at.strftime("%Y-%m") == month_str]
    deaths = [
        p for p in patients
        if p.current_survival_status == "Deceased"
        and p.date_of_death
        and p.date_of_death.strftime("%Y-%m") == month_str
    ]
    transfers = [
        p for p in patients
        if p.current_survival_status == "Transferred"
        and p.date_facility_transfer
        and p.date_facility_transfer.strftime("%Y-%m") == month_str
    ]

    monthly_recs = db.query(MonthlyRecord).filter(MonthlyRecord.record_month == month_str).all()
    hosp_count = sum(1 for r in monthly_recs if r.hospitalization_diagnosis or r.hospitalization_icd_diagnosis)
    hosp_rate = (hosp_count / len(active_patients) * 100) if active_patients else 0

    return templates.TemplateResponse("census_report.html", {
        "request": request,
        "month_str": month_str,
        "metrics": {
            "total_active": len(active_patients),
            "new_registrations": len(new_regs),
            "deaths": len(deaths),
            "transfers": len(transfers),
            "hospitalizations": hosp_count,
            "hosp_rate": round(hosp_rate, 1)
        },
        "new_patients": new_regs,
        "deceased_patients": deaths,
        "transferred_patients": transfers,
        "user": get_user(request)
    })

@router.get("/vascular-access", response_class=HTMLResponse)
async def vascular_access_quality(request: Request, month: Optional[str] = None, db: Session = Depends(get_db)):
    _require_analytics_access(request)
    from datetime import datetime
    from ml_analytics import analyze_avf_maturation
    from services.access_surveillance_service import (
        compute_access_action_items, compute_unit_benchmarks, _load_config,
    )
    month_str, _ = get_effective_month(db, month)

    from sqlalchemy.orm import joinedload
    patients = (
        db.query(Patient)
        .options(
            joinedload(Patient.vascular_access),
            joinedload(Patient.comorbidity_profile),
            joinedload(Patient.cardiac),
        )
        .filter(
            Patient.is_active == True,
        )
        .all()
    )
    total_prevalent = len(patients)

    # 1. Prevalent AVF Rate (All active patients)
    prevalent_avf = [p for p in patients if p.access_type and "AVF" in p.access_type.upper()]
    prevalent_rate = (len(prevalent_avf) / total_prevalent * 100) if total_prevalent else 0

    # 2. Incident AVF Rate (Started this month)
    incident_patients = [p for p in patients if p.hd_wef_date and p.hd_wef_date.strftime("%Y-%m") == month_str]
    incident_avf = [p for p in incident_patients if p.access_type and "AVF" in p.access_type.upper()]
    incident_rate = (len(incident_avf) / len(incident_patients) * 100) if incident_patients else 0

    today = datetime.now().date()

    # ── Batch pre-fetch config once (shared across all per-patient calls) ────
    unit_config = _load_config(db)

    # ── Bulk Prefetching for N+1 Query Elimination ───────────────────────────
    active_patient_ids = [p.id for p in patients]

    from db.models.clinical import AccessEpisode, AccessEvent
    from db.models.sessions import SessionRecord

    # 1. Fetch current access episodes
    all_current_episodes = (
        db.query(AccessEpisode)
        .filter(
            AccessEpisode.patient_id.in_(active_patient_ids),
            AccessEpisode.is_current == True,
        )
        .all()
    )
    current_episodes_by_pid = {ep.patient_id: ep for ep in all_current_episodes}

    # 2. Fetch all TCC episodes (for CRBSI rate calculation)
    all_tcc_episodes = (
        db.query(AccessEpisode)
        .filter(
            AccessEpisode.patient_id.in_(active_patient_ids),
            AccessEpisode.access_class == "TCC",
        )
        .all()
    )
    tcc_episodes_by_pid = {}
    for ep in all_tcc_episodes:
        tcc_episodes_by_pid.setdefault(ep.patient_id, []).append(ep)

    # 3. Fetch all access events
    all_events = (
        db.query(AccessEvent)
        .filter(AccessEvent.patient_id.in_(active_patient_ids))
        .all()
    )
    events_by_pid = {}
    for ev in all_events:
        events_by_pid.setdefault(ev.patient_id, []).append(ev)

    # 4. Fetch last 20 session records per patient (limit 20 is sufficient for cannulation alert)
    all_recent_sessions = (
        db.query(SessionRecord)
        .filter(SessionRecord.patient_id.in_(active_patient_ids))
        .order_by(SessionRecord.patient_id, SessionRecord.session_date.desc())
        .all()
    )
    sessions_by_pid = {}
    for s in all_recent_sessions:
        sessions_by_pid.setdefault(s.patient_id, [])
        if len(sessions_by_pid[s.patient_id]) < 20:
            sessions_by_pid[s.patient_id].append(s)

    # 3. Watchlists & Intelligence — now all from pre-fetched data
    maturation_watchlist = []
    functional_watchlist = []
    conversion_watchlist = []

    for p in patients:
        # a) Late Conversion Watchlist (>90 days on HD with non-AVF access)
        if p.access_type and "AVF" not in p.access_type.upper():
            if p.hd_wef_date:
                days_on_hd = (today - p.hd_wef_date).days
                if days_on_hd > 90:
                    conversion_watchlist.append({
                        "patient": p,
                        "days": days_on_hd,
                        "vintage": p.hd_wef_date.strftime("%b %Y")
                    })

        # b) Intelligence Engine — use pre-fetched episode data (no per-patient DB calls)
        try:
            status = analyze_avf_maturation(
                db, p.id, patient_obj=p,
                recent_sessions=sessions_by_pid.get(p.id, [])[:5]
            )
            if status.get("available"):
                data = status.get("data", {})
                if data.get("maturation_failure"):
                    maturation_watchlist.append({"patient": p, "status": status})
                if data.get("suboptimal_flow") or data.get("high_recirculation"):
                    functional_watchlist.append({"patient": p, "status": status})
        except Exception:
            logging.exception("analyze_avf_maturation failed for patient %s", p.id)

    # ── KDOQI 2019 action board — pass pre-loaded config to avoid repeat DB hits
    action_board_urgent: list = []
    action_board_this_week: list = []
    action_board_routine: list = []

    for p in patients:
        try:
            items = compute_access_action_items(
                db, p.id, config=unit_config,
                current_episode=current_episodes_by_pid.get(p.id),
                recent_sessions=sessions_by_pid.get(p.id, []),
                all_events=events_by_pid.get(p.id, []),
                all_episodes=tcc_episodes_by_pid.get(p.id, []),
            )
            for item in items:
                item["patient_name"] = p.name
                item["patient_id"] = p.id
                item["hid_no"] = p.hid_no
                if item["priority"] == "urgent":
                    action_board_urgent.append(item)
                elif item["priority"] == "this_week":
                    action_board_this_week.append(item)
                else:
                    action_board_routine.append(item)
        except Exception:
            logging.exception("compute_access_action_items failed for patient %s", p.id)

    try:
        unit_benchmarks = compute_unit_benchmarks(db, month_str, config=unit_config)
    except Exception:
        logging.exception("compute_unit_benchmarks failed")
        unit_benchmarks = []

    # Split benchmarks by access class for template display
    benchmarks_avf = [b for b in unit_benchmarks if b["access_class"] == "AVF"]
    benchmarks_avg = [b for b in unit_benchmarks if b["access_class"] == "AVG"]
    benchmarks_tcc = [b for b in unit_benchmarks if b["access_class"] == "TCC"]

    # ── ML: Access-loss risk scores & chart data ───────────────────────────────
    from services.access_surveillance_service import (
        compute_unit_access_risk, compute_unit_qa_distribution, compute_avf_rate_trend,
    )
    import json as _json

    try:
        access_risk_rows = compute_unit_access_risk(db, config=unit_config)
    except Exception:
        logging.exception("compute_unit_access_risk failed")
        access_risk_rows = []

    try:
        qa_distribution = compute_unit_qa_distribution(db)
    except Exception:
        logging.exception("compute_unit_qa_distribution failed")
        qa_distribution = []

    try:
        avf_trend = compute_avf_rate_trend(db, n_months=6)
    except Exception:
        logging.exception("compute_avf_rate_trend failed")
        avf_trend = []

    # Access mix counts for donut chart
    avf_n = sum(1 for p in patients if p.access_type and "AVF" in p.access_type.upper())
    avg_n = sum(1 for p in patients if p.access_type and ("AVG" in p.access_type.upper() or "GRAFT" in p.access_type.upper()))
    tcc_n = sum(1 for p in patients if p.access_type and any(k in p.access_type.upper() for k in ("TCC", "PERMACATH")))
    other_n = total_prevalent - avf_n - avg_n - tcc_n

    # Confirmed event type counts for bar chart (last 6 months)
    from db.models.clinical import AccessEvent as _AE
    from datetime import timedelta as _td
    six_months_ago = today - _td(days=180)
    recent_events = (
        db.query(_AE)
        .filter(_AE.status == "confirmed", _AE.event_date >= six_months_ago)
        .all()
    )
    event_counts: dict = {}
    for ev in recent_events:
        label = (ev.event_type or "unknown").replace("_", " ").title()
        event_counts[label] = event_counts.get(label, 0) + 1
    event_chart = sorted(
        [{"type": k, "count": v} for k, v in event_counts.items()],
        key=lambda x: x["count"], reverse=True
    )[:10]

    return templates.TemplateResponse("access_quality.html", {
        "request": request,
        "month_str": month_str,
        "metrics": {
            "prevalent_rate": round(prevalent_rate, 1),
            "incident_rate": round(incident_rate, 1),
            "watchlist_count": len(conversion_watchlist),
            "maturation_failure_count": len(maturation_watchlist),
            "functional_alert_count": len(functional_watchlist),
            "target_prevalent": 90.0,
            "target_incident": 65.0,
            "action_board_urgent_count": len(action_board_urgent),
            "action_board_this_week_count": len(action_board_this_week),
            "action_board_routine_count": len(action_board_routine),
            "total_patients": total_prevalent,
        },
        "watchlist": conversion_watchlist,
        "maturation_watchlist": maturation_watchlist,
        "functional_watchlist": functional_watchlist,
        "action_board_urgent": action_board_urgent,
        "action_board_this_week": action_board_this_week,
        "action_board_routine": action_board_routine,
        "benchmarks_avf": benchmarks_avf,
        "benchmarks_avg": benchmarks_avg,
        "benchmarks_tcc": benchmarks_tcc,
        # ── Charts & ML ────────────────────────────────────────────────────────
        "access_risk_rows": access_risk_rows,
        "access_risk_json": _json.dumps(access_risk_rows[:20]),
        "qa_distribution_json": _json.dumps(qa_distribution),
        "avf_trend_json": _json.dumps(avf_trend),
        "access_mix_json": _json.dumps([
            {"label": "AVF", "value": avf_n, "color": "#10b981"},
            {"label": "AVG", "value": avg_n, "color": "#f59e0b"},
            {"label": "TCC / Permacath", "value": tcc_n, "color": "#ef4444"},
            {"label": "Other / Unknown", "value": other_n, "color": "#94a3b8"},
        ]),
        "event_chart_json": _json.dumps(event_chart),
        "user": get_user(request)
    })


@router.get("/vascular-access/action-board", response_class=JSONResponse)
async def vascular_access_action_board(request: Request, patient_id: Optional[int] = None, db: Session = Depends(get_db)):
    """Return action items for one patient or all patients (JSON)."""
    _require_analytics_access(request)
    from services.access_surveillance_service import compute_access_action_items
    from database import Patient

    if patient_id:
        items = compute_access_action_items(db, patient_id)
        return JSONResponse(content=items)

    from sqlalchemy.orm import joinedload
    patients = (
        db.query(Patient)
        .options(joinedload(Patient.vascular_access))
        .filter(
            Patient.is_active == True,
        )
        .all()
    )

    # ── Bulk Prefetching for N+1 Query Elimination ───────────────────────────
    active_patient_ids = [p.id for p in patients]

    from db.models.clinical import AccessEpisode, AccessEvent
    from db.models.sessions import SessionRecord

    # 1. Fetch current access episodes
    all_current_episodes = (
        db.query(AccessEpisode)
        .filter(
            AccessEpisode.patient_id.in_(active_patient_ids),
            AccessEpisode.is_current == True,
        )
        .all()
    )
    current_episodes_by_pid = {ep.patient_id: ep for ep in all_current_episodes}

    # 2. Fetch all TCC episodes
    all_tcc_episodes = (
        db.query(AccessEpisode)
        .filter(
            AccessEpisode.patient_id.in_(active_patient_ids),
            AccessEpisode.access_class == "TCC",
        )
        .all()
    )
    tcc_episodes_by_pid = {}
    for ep in all_tcc_episodes:
        tcc_episodes_by_pid.setdefault(ep.patient_id, []).append(ep)

    # 3. Fetch all access events
    all_events = (
        db.query(AccessEvent)
        .filter(AccessEvent.patient_id.in_(active_patient_ids))
        .all()
    )
    events_by_pid = {}
    for ev in all_events:
        events_by_pid.setdefault(ev.patient_id, []).append(ev)

    # 4. Fetch last 20 session records per patient
    all_recent_sessions = (
        db.query(SessionRecord)
        .filter(SessionRecord.patient_id.in_(active_patient_ids))
        .order_by(SessionRecord.patient_id, SessionRecord.session_date.desc())
        .all()
    )
    sessions_by_pid = {}
    for s in all_recent_sessions:
        sessions_by_pid.setdefault(s.patient_id, [])
        if len(sessions_by_pid[s.patient_id]) < 20:
            sessions_by_pid[s.patient_id].append(s)

    all_items = []
    for p in patients:
        try:
            items = compute_access_action_items(
                db, p.id,
                current_episode=current_episodes_by_pid.get(p.id),
                recent_sessions=sessions_by_pid.get(p.id, []),
                all_events=events_by_pid.get(p.id, []),
                all_episodes=tcc_episodes_by_pid.get(p.id, []),
            )
            for item in items:
                item["patient_name"] = p.name
                item["hid_no"] = p.hid_no
            all_items.extend(items)
        except Exception:
            pass
    return JSONResponse(content=all_items)


@router.get("/vascular-access/benchmarks", response_class=JSONResponse)
async def vascular_access_benchmarks(request: Request, month: Optional[str] = None, db: Session = Depends(get_db)):
    """Return unit benchmarks for a given month (JSON)."""
    _require_analytics_access(request)
    from services.access_surveillance_service import compute_unit_benchmarks
    month_str, _ = get_effective_month(db, month)
    benchmarks = compute_unit_benchmarks(db, month_str)
    return JSONResponse(content=benchmarks)


@router.get("/vascular-access/episodes/{patient_id}", response_class=JSONResponse)
async def patient_access_episodes(patient_id: int, request: Request, db: Session = Depends(get_db)):
    """Return all access episodes for a patient with patency calculations."""
    _require_analytics_access(request)
    from db.models.clinical import AccessEpisode, AccessEvent, AccessSurveillanceRecord
    from services.access_surveillance_service import compute_access_patency
    from fastapi.encoders import jsonable_encoder

    episodes = (
        db.query(AccessEpisode)
        .filter(AccessEpisode.patient_id == patient_id)
        .order_by(AccessEpisode.creation_date.desc())
        .all()
    )
    result = []
    for ep in episodes:
        patency = compute_access_patency(db, ep.id)
        events = (
            db.query(AccessEvent)
            .filter(AccessEvent.episode_id == ep.id)
            .order_by(AccessEvent.event_date.desc())
            .all()
        )
        surveillance = (
            db.query(AccessSurveillanceRecord)
            .filter(AccessSurveillanceRecord.episode_id == ep.id)
            .order_by(AccessSurveillanceRecord.surveillance_date.desc())
            .all()
        )
        result.append({
            "episode": jsonable_encoder(ep),
            "patency": patency,
            "events": jsonable_encoder(events),
            "surveillance": jsonable_encoder(surveillance),
        })
    return JSONResponse(content=result)


@router.post("/vascular-access/episodes/{patient_id}", response_class=JSONResponse)
async def create_access_episode(patient_id: int, request: Request, db: Session = Depends(get_db)):
    """Create a new AccessEpisode for a patient."""
    _require_analytics_access(request)
    from db.models.clinical import AccessEpisode
    from fastapi.encoders import jsonable_encoder

    user = get_user(request)
    body = await request.json()

    # Mark previous current episode as no longer current if creating a new one
    if body.get("is_current", True):
        db.query(AccessEpisode).filter(
            AccessEpisode.patient_id == patient_id,
            AccessEpisode.is_current == True,
        ).update({"is_current": False})

    ep = AccessEpisode(
        patient_id=patient_id,
        access_class=body["access_class"],
        access_subtype=body.get("access_subtype"),
        creation_date=date.fromisoformat(body["creation_date"]),
        first_cannulation_date=date.fromisoformat(body["first_cannulation_date"]) if body.get("first_cannulation_date") else None,
        insertion_site=body.get("insertion_site"),
        catheter_type=body.get("catheter_type"),
        is_current=body.get("is_current", True),
        succession_plan=body.get("succession_plan"),
        notes=body.get("notes"),
        entered_by=getattr(user, "username", "clinician"),
    )
    db.add(ep)
    db.commit()
    db.refresh(ep)
    return JSONResponse(content=jsonable_encoder(ep), status_code=201)


@router.post("/vascular-access/events/{patient_id}", response_class=JSONResponse)
async def log_access_event(patient_id: int, request: Request, db: Session = Depends(get_db)):
    """Log a structured AccessEvent against the patient's current episode."""
    _require_analytics_access(request)
    from db.models.clinical import AccessEpisode, AccessEvent
    from fastapi.encoders import jsonable_encoder

    user = get_user(request)
    body = await request.json()

    episode_id = body.get("episode_id")
    if not episode_id:
        current_ep = db.query(AccessEpisode).filter(
            AccessEpisode.patient_id == patient_id,
            AccessEpisode.is_current == True,
        ).order_by(AccessEpisode.creation_date.desc()).first()
        if not current_ep:
            raise HTTPException(status_code=400, detail="No current access episode found")
        episode_id = current_ep.id
        access_class = current_ep.access_class
    else:
        ep = db.query(AccessEpisode).filter(AccessEpisode.id == episode_id).first()
        if not ep:
            raise HTTPException(status_code=404, detail="Episode not found")
        access_class = ep.access_class

    event = AccessEvent(
        patient_id=patient_id,
        episode_id=episode_id,
        event_date=date.fromisoformat(body["event_date"]),
        event_type=body["event_type"],
        access_class=access_class,
        severity=body.get("severity"),
        steal_grade=body.get("steal_grade"),
        cannulation_injury_grade=body.get("cannulation_injury_grade"),
        affected_segment=body.get("affected_segment"),
        action_taken=body.get("action_taken"),
        outcome=body.get("outcome"),
        status=body.get("status", "pending_review"),
        notes=body.get("notes"),
        entered_by=getattr(user, "username", "clinician"),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return JSONResponse(content=jsonable_encoder(event), status_code=201)


@router.post("/vascular-access/surveillance/{patient_id}", response_class=JSONResponse)
async def log_surveillance_record(patient_id: int, request: Request, db: Session = Depends(get_db)):
    """Log a clinically-triggered imaging/Doppler surveillance record."""
    _require_analytics_access(request)
    from db.models.clinical import AccessEpisode, AccessSurveillanceRecord
    from fastapi.encoders import jsonable_encoder

    user = get_user(request)
    body = await request.json()

    episode_id = body.get("episode_id")
    if not episode_id:
        current_ep = db.query(AccessEpisode).filter(
            AccessEpisode.patient_id == patient_id,
            AccessEpisode.is_current == True,
        ).order_by(AccessEpisode.creation_date.desc()).first()
        if not current_ep:
            raise HTTPException(status_code=400, detail="No current access episode found")
        episode_id = current_ep.id

    if not body.get("clinical_trigger"):
        raise HTTPException(status_code=400, detail="clinical_trigger is required (KDOQI: surveillance must be clinically indicated)")

    rec = AccessSurveillanceRecord(
        patient_id=patient_id,
        episode_id=episode_id,
        surveillance_date=date.fromisoformat(body["surveillance_date"]),
        clinical_trigger=body["clinical_trigger"],
        modality=body.get("modality"),
        qa_by_imaging=body.get("qa_by_imaging"),
        qa_baseline_at_test=body.get("qa_baseline_at_test"),
        psv_at_stenosis=body.get("psv_at_stenosis"),
        stenosis_pct=body.get("stenosis_pct"),
        finding=body.get("finding"),
        recommendation=body.get("recommendation"),
        next_due_date=date.fromisoformat(body["next_due_date"]) if body.get("next_due_date") else None,
        performed_by=body.get("performed_by"),
        status=body.get("status", "pending_review"),
        notes=body.get("notes"),
        entered_by=getattr(user, "username", "clinician"),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return JSONResponse(content=jsonable_encoder(rec), status_code=201)


@router.get("/vascular-access/surveillance/{patient_id}/new", response_class=HTMLResponse)
async def new_surveillance_form(patient_id: int, request: Request, db: Session = Depends(get_db)):
    _require_analytics_access(request)
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    from db.models.clinical import AccessEpisode
    current_ep = db.query(AccessEpisode).filter(
        AccessEpisode.patient_id == patient_id,
        AccessEpisode.is_current == True,
    ).order_by(AccessEpisode.creation_date.desc()).first()
    
    return templates.TemplateResponse("access_surveillance_form.html", {
        "request": request,
        "patient": patient,
        "current_ep": current_ep,
        "user": get_user(request),
    })


@router.post("/vascular-access/surveillance/{patient_id}/new")
async def create_surveillance_record(
    patient_id: int,
    request: Request,
    db: Session = Depends(get_db),
    surveillance_date: str = Form(...),
    clinical_trigger: str = Form(...),
    modality: Optional[str] = Form(None),
    qa_by_imaging: Optional[float] = Form(None),
    qa_baseline_at_test: Optional[float] = Form(None),
    psv_at_stenosis: Optional[float] = Form(None),
    stenosis_pct: Optional[float] = Form(None),
    finding: Optional[str] = Form(None),
    recommendation: Optional[str] = Form(None),
    next_due_date: Optional[str] = Form(None),
    performed_by: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
):
    _require_analytics_access(request)
    from db.models.clinical import AccessEpisode, AccessSurveillanceRecord
    user = get_user(request)
    
    current_ep = db.query(AccessEpisode).filter(
        AccessEpisode.patient_id == patient_id,
        AccessEpisode.is_current == True,
    ).order_by(AccessEpisode.creation_date.desc()).first()
    if not current_ep:
        raise HTTPException(status_code=400, detail="No current access episode found. Create one first.")
        
    rec = AccessSurveillanceRecord(
        patient_id=patient_id,
        episode_id=current_ep.id,
        surveillance_date=date.fromisoformat(surveillance_date),
        clinical_trigger=clinical_trigger,
        modality=modality,
        qa_by_imaging=qa_by_imaging,
        qa_baseline_at_test=qa_baseline_at_test,
        psv_at_stenosis=psv_at_stenosis,
        stenosis_pct=stenosis_pct,
        finding=finding,
        recommendation=recommendation,
        next_due_date=date.fromisoformat(next_due_date) if next_due_date else None,
        performed_by=performed_by,
        status="pending_review",
        notes=notes,
        entered_by=getattr(user, "username", "clinician"),
    )
    db.add(rec)
    db.commit()
    return RedirectResponse(url=f"/patients/{patient_id}/profile", status_code=303)


@router.patch("/vascular-access/events/{event_id}/status", response_class=JSONResponse)
async def update_access_event_status(event_id: int, request: Request, db: Session = Depends(get_db)):
    """Confirm or rule out an access event (governance workflow)."""
    _require_analytics_access(request)
    from db.models.clinical import AccessEvent
    from fastapi.encoders import jsonable_encoder

    user = get_user(request)
    body = await request.json()
    status = body.get("status")
    if status not in ("confirmed", "ruled_out", "pending_review"):
        raise HTTPException(status_code=400, detail="status must be confirmed, ruled_out, or pending_review")

    event = db.query(AccessEvent).filter(AccessEvent.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    event.status = status
    event.reviewed_by = getattr(user, "username", "clinician")
    event.reviewed_at = datetime.now()
    db.commit()
    return JSONResponse(content=jsonable_encoder(event))


@router.patch("/vascular-access/episodes/{episode_id}/life-plan", response_class=JSONResponse)
async def update_life_plan(episode_id: int, request: Request, db: Session = Depends(get_db)):
    """Update ESKD Life-Plan fields on an access episode."""
    _require_analytics_access(request)
    from db.models.clinical import AccessEpisode
    from fastapi.encoders import jsonable_encoder

    body = await request.json()
    ep = db.query(AccessEpisode).filter(AccessEpisode.id == episode_id).first()
    if not ep:
        raise HTTPException(status_code=404, detail="Episode not found")

    if "succession_plan" in body:
        ep.succession_plan = body["succession_plan"]
    if "life_plan_reviewed_at" in body:
        ep.life_plan_reviewed_at = date.fromisoformat(body["life_plan_reviewed_at"])
    if "access_reviewed_at" in body:
        ep.access_reviewed_at = date.fromisoformat(body["access_reviewed_at"])

    db.commit()
    return JSONResponse(content=jsonable_encoder(ep))


@router.post("/vascular-access/alerts/override", response_class=JSONResponse)
async def override_access_alert(request: Request, db: Session = Depends(get_db)):
    """Log an alert override / acknowledgement (governance audit trail)."""
    _require_analytics_access(request)
    from db.models.clinical import AccessAlertOverride
    from fastapi.encoders import jsonable_encoder

    user = get_user(request)
    body = await request.json()

    if body.get("action") == "overridden" and not body.get("override_reason"):
        raise HTTPException(status_code=400, detail="override_reason is required when action=overridden")

    override = AccessAlertOverride(
        patient_id=body["patient_id"],
        alert_type=body["alert_type"],
        alert_generated_at=datetime.fromisoformat(body["alert_generated_at"]),
        alert_reason=body.get("alert_reason"),
        action=body["action"],
        override_reason=body.get("override_reason"),
        actioned_by=getattr(user, "username", "clinician"),
    )
    db.add(override)
    db.commit()
    db.refresh(override)
    return JSONResponse(content=jsonable_encoder(override), status_code=201)


@router.post("/vascular-access/surveillance/{record_id}/upload-image", response_class=JSONResponse)
async def upload_surveillance_image(
    record_id: int,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload a Doppler / fistulogram report image and attach it to a surveillance record.

    Accepts JPEG, PNG, WebP, PDF. Stored at static/uploads/surveillance/<record_id>_<filename>.
    Returns the public URL path.
    """
    _require_analytics_access(request)
    import os, uuid
    from db.models.clinical import AccessSurveillanceRecord
    from fastapi.encoders import jsonable_encoder

    rec = db.query(AccessSurveillanceRecord).filter(AccessSurveillanceRecord.id == record_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Surveillance record not found")

    content_type = file.content_type or ""
    allowed = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
    if content_type not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{content_type}'. Upload JPEG, PNG, WebP, or PDF.",
        )

    ext_map = {
        "image/jpeg": ".jpg", "image/png": ".png",
        "image/webp": ".webp", "application/pdf": ".pdf",
    }
    ext = ext_map.get(content_type, ".bin")
    safe_name = f"{record_id}_{uuid.uuid4().hex[:8]}{ext}"
    upload_dir = os.path.join("static", "uploads", "surveillance")
    os.makedirs(upload_dir, exist_ok=True)
    dest_path = os.path.join(upload_dir, safe_name)

    contents = await file.read()
    with open(dest_path, "wb") as f_out:
        f_out.write(contents)

    public_path = f"/static/uploads/surveillance/{safe_name}"
    rec.report_image_path = public_path
    db.commit()
    return JSONResponse(content={"url": public_path, "record_id": record_id})


@router.get("/vascular-access/analytics/{patient_id}", response_class=HTMLResponse)
async def vascular_access_analytics(patient_id: int, request: Request, db: Session = Depends(get_db)):
    """Per-patient vascular access analytics page with Plotly trend visualisations."""
    _require_analytics_access(request)
    from db.models.clinical import AccessEpisode, AccessEvent, AccessSurveillanceRecord
    from services.access_surveillance_service import (
        compute_access_action_items, compute_access_patency, compute_av_intervention_count,
    )
    from fastapi.encoders import jsonable_encoder

    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404)

    # Load access_failure_risk from the latest feature snapshot
    access_failure_risk = None
    try:
        from database import PatientFeatureSnapshot
        import json
        snap = (
            db.query(PatientFeatureSnapshot)
            .filter(PatientFeatureSnapshot.patient_id == patient_id)
            .order_by(PatientFeatureSnapshot.computed_at.desc())
            .first()
        )
        if snap and snap.feature_vector:
            features = snap.feature_vector
            if isinstance(features, str):
                features = json.loads(features)
            access_failure_risk = features.get("access_failure_risk")
    except Exception as exc:
        pass

    # All episodes, most recent first
    episodes = (
        db.query(AccessEpisode)
        .filter(AccessEpisode.patient_id == patient_id)
        .order_by(AccessEpisode.creation_date.desc())
        .all()
    )

    current_ep = next((e for e in episodes if e.is_current), episodes[0] if episodes else None)

    # Last 60 sessions — Qa, recirculation, thrill/bruit, cannulation difficulty
    sessions_raw = (
        db.query(SessionRecord)
        .filter(SessionRecord.patient_id == patient_id)
        .order_by(SessionRecord.session_date.asc())
        .limit(60)
        .all()
    )

    # All confirmed events for timeline
    events = (
        db.query(AccessEvent)
        .filter(AccessEvent.patient_id == patient_id, AccessEvent.status == "confirmed")
        .order_by(AccessEvent.event_date.asc())
        .all()
    )

    # All surveillance records with images
    surveillance = (
        db.query(AccessSurveillanceRecord)
        .filter(AccessSurveillanceRecord.patient_id == patient_id)
        .order_by(AccessSurveillanceRecord.surveillance_date.desc())
        .all()
    )
    latest_doppler = next(
        (s for s in surveillance if s.modality == "duplex_doppler"), None
    )

    # Action items for this patient
    action_items = []
    try:
        action_items = compute_access_action_items(db, patient_id)
    except Exception:
        pass

    # Patency for current episode
    patency = {}
    if current_ep:
        patency = compute_access_patency(db, current_ep.id)

    # Intervention count vs KDOQI 1-2-3
    intervention_establish = {}
    intervention_annual = {}
    if current_ep:
        intervention_establish = compute_av_intervention_count(db, current_ep.id, "establish")
        intervention_annual = compute_av_intervention_count(db, current_ep.id, "annual")

    # Serialisable chart data
    chart_sessions = [
        {
            "date": str(s.session_date),
            "qa": s.access_flow_qa,
            "recirc": s.access_recirculation_percent,
            "bfr_actual": s.actual_blood_flow_rate,
            "bfr_prescribed": s.blood_flow_rate,
            "thrill": s.thrill_grade,
            "bruit": s.bruit_grade,
            "cannulation_difficulty": s.cannulation_difficulty,
            "aneurysm_flag": s.aneurysm_flag,
            "steal_flag": s.steal_signs_flag,
        }
        for s in sessions_raw
    ]
    chart_events = [
        {
            "date": str(e.event_date),
            "type": e.event_type,
            "severity": e.severity,
            "steal_grade": e.steal_grade,
            "action": e.action_taken,
        }
        for e in events
    ]
    chart_surveillance = [
        {
            "date": str(s.surveillance_date),
            "qa": s.qa_by_imaging,
            "baseline": s.qa_baseline_at_test,
            "stenosis_pct": s.stenosis_pct,
            "psv": s.psv_at_stenosis,
            "finding": s.finding,
            "recommendation": s.recommendation,
            "image_url": s.report_image_path,
            "trigger": s.clinical_trigger,
            "modality": s.modality,
            "notes": s.notes,
            "record_id": s.id,
        }
        for s in surveillance
    ]

    import json as _json
    return templates.TemplateResponse("vascular_access_analytics.html", {
        "request": request,
        "patient": patient,
        "episodes": episodes,
        "current_ep": current_ep,
        "patency": patency,
        "action_items": action_items,
        "intervention_establish": intervention_establish,
        "intervention_annual": intervention_annual,
        "latest_doppler": latest_doppler,
        "surveillance": surveillance,
        "chart_sessions_json": _json.dumps(chart_sessions),
        "chart_events_json": _json.dumps(chart_events),
        "chart_surveillance_json": _json.dumps(chart_surveillance),
        "user": get_user(request),
        "access_failure_risk": access_failure_risk,
    })


@router.get("/mortality-risk", response_class=HTMLResponse)
async def mortality_risk_list(
    request: Request,
    page: int = 1,
    limit: int = 10,
    tier: str = "all",
    search: str = "",
    db: Session = Depends(get_db)
):
    _require_analytics_access(request)
    rows = get_all_patients_mortality_risk(db)

    # Sort: no-data patients last, then descending by 1-yr probability
    rows.sort(key=lambda r: (r["prob_1yr"] is None, -(r["prob_1yr"] or 0)))

    # Compute overall cohort counts
    total_high = len([r for r in rows if r["risk_level"] in ("High", "Very High")])
    total_moderate = len([r for r in rows if r["risk_level"] == "Moderate"])
    total_low = len([r for r in rows if r["risk_level"] == "Low"])
    total_no_data = len([r for r in rows if not r["mort"].get("available")])

    # Filter by risk tier
    filtered_rows = rows
    if tier == "high":
        filtered_rows = [r for r in rows if r["risk_level"] in ("High", "Very High")]
    elif tier == "moderate":
        filtered_rows = [r for r in rows if r["risk_level"] == "Moderate"]
    elif tier == "low":
        filtered_rows = [r for r in rows if r["risk_level"] == "Low"]
    elif tier == "no_data":
        filtered_rows = [r for r in rows if not r["mort"].get("available")]

    # Filter by search string
    if search:
        search_lower = search.strip().lower()
        filtered_rows = [
            r for r in filtered_rows
            if search_lower in r["patient"].name.lower() or search_lower in r["patient"].hid_no.lower()
        ]

    # Paginate results
    import math
    total_items = len(filtered_rows)
    total_pages = max(1, math.ceil(total_items / limit))
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * limit
    end_idx = start_idx + limit
    paginated_rows = filtered_rows[start_idx:end_idx]

    return templates.TemplateResponse("mortality_risk.html", {
        "request":   request,
        "rows":      paginated_rows,
        "current_page": page,
        "total_pages": total_pages,
        "total_items": total_items,
        "limit":     limit,
        "tier":      tier,
        "search":    search,
        "total_high": total_high,
        "total_moderate": total_moderate,
        "total_low":  total_low,
        "total_no_data": total_no_data,
        "user":      get_user(request),
        "calibration_source": "literature_dopps_india",
    })


@router.get("/pressure-trends", response_class=HTMLResponse)
async def pressure_trends(request: Request, db: Session = Depends(get_db)):
    """Fleet-wide circuit pressure trend dashboard.

    Shows arterial/venous/TMP signals across recent sessions for all active
    patients and surfaces early access failure risk flags.
    """
    _require_analytics_access(request)
    from dashboard_logic import _fetch_recent_n_sessions
    from services.pressure_analysis import compute_fleet_pressure_signals

    active = db.query(Patient).filter(Patient.is_active == True).order_by(Patient.name).all()
    recent_sessions = _fetch_recent_n_sessions(db, [p.id for p in active], n=8)

    signals = compute_fleet_pressure_signals(db, active, recent_sessions)

    alert_count   = sum(1 for s in signals if s.max_risk == "alert")
    warning_count = sum(1 for s in signals if s.max_risk == "warning")
    combined_count = sum(1 for s in signals if s.combined_risk)

    return templates.TemplateResponse("pressure_trends.html", {
        "request":        request,
        "user":           get_user(request),
        "signals":        signals,
        "total_patients": len(active),
        "with_data":      len(signals),
        "alert_count":    alert_count,
        "warning_count":  warning_count,
        "combined_count": combined_count,
    })


@router.get("", response_class=HTMLResponse)
async def analytics_hub(request: Request, db: Session = Depends(get_db)):
    _require_analytics_access(request)
    from dashboard_logic import get_current_month_str

    month_str, _ = get_effective_month(db)
    data = compute_dashboard(db, month_str)
    patient_rows = data.get("patient_rows", [])

    # ── Vascular access summary (fast — counts from already-loaded patients) ──
    from sqlalchemy.orm import joinedload
    active_patients = (
        db.query(Patient)
        .options(joinedload(Patient.vascular_access))
        .filter(
            Patient.is_active == True,
        )
        .all()
    )
    total = len(active_patients)
    avf_count = sum(1 for p in active_patients if p.access_type and "AVF" in p.access_type.upper())
    non_avf_count = total - avf_count
    prevalent_avf_rate = round(avf_count / total * 100, 1) if total else 0

    # Urgent action item count (one query — count confirmed events needing review)
    from db.models.clinical import AccessEpisode
    from datetime import date as _date
    # Count patients on non-tunnelled CVC (always urgent)
    urgent_cvc = sum(
        1 for p in active_patients
        if p.access_type and any(k in p.access_type.upper() for k in ("NON-TUNNELLED", "NON_TUNNELLED", "NTCC", "TEMPORARY"))
    )

    # Count active maturation failures: no cannulation > 180 days from episode creation
    from sqlalchemy import and_
    late_episodes = (
        db.query(AccessEpisode)
        .filter(
            AccessEpisode.is_current == True,
            AccessEpisode.first_cannulation_date.is_(None),
            AccessEpisode.creation_date <= (_date.today() - timedelta(days=180)),
        )
        .count()
    )

    va_summary = {
        "prevalent_avf_rate": prevalent_avf_rate,
        "avf_count": avf_count,
        "non_avf_count": non_avf_count,
        "total": total,
        "maturation_failures": late_episodes,
        "urgent_cvc": urgent_cvc,
        "target_prevalent": 90.0,
    }

    return templates.TemplateResponse("analytics_hub.html", {
        "request": request,
        "patients": patient_rows,
        "va_summary": va_summary,
        "user": get_user(request)
    })

@root_router.get("/review", response_class=HTMLResponse)
@root_router.get("/review/", response_class=HTMLResponse)
async def clinical_review_queue(request: Request, db: Session = Depends(get_db)):
    _require_analytics_access(request)
    user = get_user(request)

    # Run the two expensive synchronous computations concurrently in the thread
    # pool so neither blocks the event loop or serialises behind the other.
    # Each gets its own DB session to avoid SQLAlchemy cross-thread conflicts.
    loop = asyncio.get_event_loop()

    def _run_dashboard():
        _db = SessionLocal()
        try:
            return compute_dashboard(_db)
        finally:
            _db.close()

    def _run_mortality():
        _db = SessionLocal()
        try:
            return get_all_patients_mortality_risk(_db)
        finally:
            _db.close()

    dash_data, mort_data = await asyncio.gather(
        loop.run_in_executor(None, _run_dashboard),
        loop.run_in_executor(None, _run_mortality),
    )
    mort_map = {r['patient'].id: r for r in mort_data}

    active_patients = [r['patient'] for r in mort_data]
    patient_ids = [p.id for p in active_patients]

    flagged = {}  # patient_id -> {patient, flags, priority}

    # ── Batch pre-fetch everything used inside the per-patient loop ───────────
    current_month = get_current_month_str()
    y, mo = int(current_month[:4]), int(current_month[5:7])
    prev_month = f"{y-1}-12" if mo == 1 else f"{y}-{mo-1:02d}"

    curr_recs = {r.patient_id: r for r in db.query(MonthlyRecord).filter(MonthlyRecord.record_month == current_month).all()}
    prev_recs = {r.patient_id: r for r in db.query(MonthlyRecord).filter(MonthlyRecord.record_month == prev_month).all()}

    # Last 3 monthly records per patient (for occult overload albumin trend)
    # Filter to last 3 months — only 3 records per patient are ever used
    mr_cutoff_month = (date.today().replace(day=1) - timedelta(days=90)).strftime('%Y-%m')
    recent_mr_all = (
        db.query(MonthlyRecord)
        .filter(
            MonthlyRecord.patient_id.in_(patient_ids),
            MonthlyRecord.albumin.isnot(None),
            MonthlyRecord.record_month >= mr_cutoff_month,
        )
        .order_by(MonthlyRecord.patient_id, MonthlyRecord.record_month.desc())
        .all()
    )
    recent_mr_by_pid: dict = {}
    for r in recent_mr_all:
        recent_mr_by_pid.setdefault(r.patient_id, [])
        if len(recent_mr_by_pid[r.patient_id]) < 3:
            recent_mr_by_pid[r.patient_id].append(r)

    # Recent sessions per patient (for dyspnea / emergency check)
    # Limit to last 90 days — avoids loading full session history for every patient
    sessions_cutoff = date.today() - timedelta(days=90)
    recent_sessions_all = (
        db.query(SessionRecord)
        .filter(
            SessionRecord.patient_id.in_(patient_ids),
            SessionRecord.session_date >= sessions_cutoff,
        )
        .order_by(SessionRecord.patient_id, SessionRecord.session_date.desc())
        .all()
    )
    recent_sessions_by_pid: dict = {}
    for s in recent_sessions_all:
        recent_sessions_by_pid.setdefault(s.patient_id, [])
        if len(recent_sessions_by_pid[s.patient_id]) < 10:
            recent_sessions_by_pid[s.patient_id].append(s)

    # Fluid status assessments — latest per patient (single query, no per-patient lookups)
    fluid_events_raw = (
        db.query(ClinicalEvent)
        .filter(
            ClinicalEvent.patient_id.in_(patient_ids),
            ClinicalEvent.event_type == "Fluid Status Assessment",
        )
        .order_by(ClinicalEvent.event_date.desc())
        .all()
    )
    last_fluid_by_pid: dict = {}
    for ev in fluid_events_raw:
        last_fluid_by_pid.setdefault(ev.patient_id, ev)  # first = most recent

    # Last clinical review per patient
    review_events_raw = (
        db.query(ClinicalEvent)
        .filter(
            ClinicalEvent.patient_id.in_(patient_ids),
            ClinicalEvent.event_type == "Clinical Review",
        )
        .order_by(ClinicalEvent.event_date.desc())
        .all()
    )
    last_review_by_pid: dict = {}
    for ev in review_events_raw:
        last_review_by_pid.setdefault(ev.patient_id, ev)

    # Pre-build O(1) lookups — avoids O(n²) linear scans inside the per-patient loop
    hb_trend_map = {item['id']: item for item in dash_data['metrics']['trend_hb']}
    alb_trend_map = {item['id']: item for item in dash_data['metrics']['trend_albumin']}
    idwg_high_names = set(dash_data['metrics']['idwg_high']['names'])

    for p in active_patients:
        p_flags = []
        priority = 0
        m = mort_map.get(p.id)
        bay = (m or {}).get("bay_profile", {})
        bay_summary = bay.get("summary", {}) if bay.get("available") else {}

        # A. High Mortality Risk (P >= 0.40)
        if m and m.get('prob_1yr') and m['prob_1yr'] >= 0.40:
            p_flags.append("High Mortality Risk")
            priority += 3

        # B. Hb — tiered severity: Critical (<7) > Acute drop (>3 g/dL fall) > Low (<9)
        hb_trend = hb_trend_map.get(p.id)
        if hb_trend:
            hb_val  = hb_trend.get("current") or 0
            hb_drop_mag = hb_trend.get("drop") or 0
            if hb_val < 7:
                p_flags.append(f"Critical Hb ({hb_val} g/dL)")
                priority += 8
            elif hb_drop_mag >= 3:
                p_flags.append(f"Acute Hb Drop ({hb_val} g/dL, ↓{hb_drop_mag:.1f})")
                priority += 5
            else:
                p_flags.append("Hb Drop (<9)")
                priority += 2

        # C. Low Albumin
        alb_trend = alb_trend_map.get(p.id)
        if alb_trend:
            p_flags.append("Low Albumin")
            priority += 2

        # D. High IDWG
        if p.name in idwg_high_names:
            p_flags.append("High IDWG (>2.5kg)")
            priority += 1

        # D2. Significant Dry Weight Change (±2.0 kg)
        curr_r = curr_recs.get(p.id)
        prev_r = prev_recs.get(p.id)
        if curr_r and prev_r and curr_r.target_dry_weight and prev_r.target_dry_weight:
            weight_diff = curr_r.target_dry_weight - prev_r.target_dry_weight
            if abs(weight_diff) >= 2.0:
                dir_str = "Reduction" if weight_diff < 0 else "Increase"
                p_flags.append(f"Dry Weight {dir_str} ({abs(weight_diff):.1f}kg)")
                priority += 3 if weight_diff < 0 else 2 # Drops are higher priority for malnutrition

        # E. Occult Overload — computed from pre-fetched data, no extra queries
        recs_3 = recent_mr_by_pid.get(p.id, [])
        alb_decline = len(recs_3) >= 2 and recs_3[0].albumin < recs_3[-1].albumin
        p_sessions = recent_sessions_by_pid.get(p.id, [])
        breathless = any(
            (s.pre_hd_dyspnea_likert and s.pre_hd_dyspnea_likert >= 3) or
            (s.post_hd_dyspnea_likert and s.post_hd_dyspnea_likert >= 3)
            for s in p_sessions
        )
        freq_emergency = any(
            s.is_emergency and s.reason_emergency in ("Fluid Overload", "Pulmonary Oedema", "Severe Dyspnea")
            for s in p_sessions
        )
        curr_r = curr_recs.get(p.id)
        if alb_decline and (breathless or freq_emergency) and curr_r and curr_r.idwg and curr_r.idwg > 2.5:
            p_flags.append("Occult Fluid Overload")
            priority += 4

        # F. Fluid Status Pending — from pre-fetched map
        last_fs = last_fluid_by_pid.get(p.id)
        if not last_fs or (datetime.now().date() - last_fs.event_date).days > 90:
            p_flags.append("Fluid Assessment Pending")
            priority += 1

        # G. Bayesian persistence flags — only added when Bayesian data is available
        #    and the flag is not already captured by the point-in-time checks above.
        if bay.get("available"):
            hb_bay  = bay.get("hb", {})
            alb_bay = bay.get("albumin", {})
            phos_bay = bay.get("phosphorus", {})

            # High Hb persistence: prob of being low for 3+ months >= 40%
            # Skip if any Hb flag already present (Critical Hb, Acute Hb Drop, or plain Hb Drop)
            if hb_bay.get("prob_persistent_3", 0) >= 0.40 and not any("Hb" in f for f in p_flags):
                pct = round(hb_bay["prob_persistent_3"] * 100)
                p_flags.append(f"P(Hb Low×3) {pct}%")
                priority += 2

            # High Albumin persistence: prob >= 35%
            if alb_bay.get("prob_persistent_3", 0) >= 0.35 and "Low Albumin" not in p_flags:
                pct = round(alb_bay["prob_persistent_3"] * 100)
                p_flags.append(f"P(Alb Low×3) {pct}%")
                priority += 2

            # High Phosphorus persistence: prob >= 45%
            if phos_bay.get("prob_persistent_3", 0) >= 0.45:
                pct = round(phos_bay["prob_persistent_3"] * 100)
                p_flags.append(f"P(Phos High×3) {pct}%")
                priority += 1

            # Elevated composite alert score — catch multi-parameter borderline patients
            # who pass each individual threshold but are flagged together
            if bay_summary.get("composite_alert_score", 0) >= 0.55 and not p_flags:
                p_flags.append("Composite Risk Elevated")
                priority += 2

        if p_flags:
            last_review = last_review_by_pid.get(p.id)
            flagged[p.id] = {
                "patient": p,
                "flags": p_flags,
                "priority": priority,
                "mort_prob": m['prob_1yr'] if m else 0,
                "last_review": last_review.event_date if last_review else None,
                "bay_profile": bay,
                "bay_signal": (m.get("mort", {}) or {}).get("bay_signal") if m else None,
                "det_shap": m.get("det_shap") if m else None,
            }

    # Sort by priority desc, then Bayesian composite desc, then mortality risk desc
    review_list = sorted(
        flagged.values(),
        key=lambda x: (
            -x['priority'],
            -(x.get('bay_profile', {}).get('summary', {}).get('composite_alert_score') or 0),
            -(x['mort_prob'] or 0),
            x['patient'].name,
        )
    )

    return templates.TemplateResponse("review_queue.html", {
        "request": request,
        "user": user,
        "review_list": review_list,
        "generated_at": datetime.now()
    })

@router.get("/patients", response_class=HTMLResponse)
async def analytics_patient_list(request: Request, db: Session = Depends(get_db), filter: str = None, month: Optional[str] = None):
    _require_analytics_access(request)
    user = get_user(request)

    # Use the dashboard logic to get consistent clinical data
    month_str, _ = get_effective_month(db, month)
    dash_data = compute_dashboard(db, month_str)

    # Map of filter keys to alert/category keywords
    filter_map = {
        "epo_resistant": ["HypoR1", "HypoR2", "HypoR3"],
        "iv_iron": ["IV Iron Rec"],
        "idwg_high": ["High Interdialytic Weight Gain"],
        "albumin_low": ["Low Albumin"],
        "hb_high": ["High Hb (>13)"],
        "calcium_low": ["Low Corrected Calcium"],
        "phos_high": ["High Phos"],
        "non_avf": ["Non-AVF"]
    }
    

    # Get mortality risk for each for the risk badges
    from ml_analytics import get_all_patients_mortality_risk
    mort_data = get_all_patients_mortality_risk(db)
    mort_map = {r['patient'].id: r for r in mort_data}

    enriched_patients = []
    for row in dash_data.get("patient_rows", []):
        matches_filter = True
        if filter:
            matches_filter = False
            keywords = filter_map.get(filter, [])
            if any(kw in row.get("alerts", []) for kw in keywords):
                matches_filter = True
            if filter == "vascular" and "Non-AVF" in row.get("alerts", []):
                matches_filter = True

        if matches_filter:
            enriched_patients.append({
                "id": row["id"],
                "name": row["name"],
                "hid_no": row["hid"],
                "latest_hb": row["hb"],
                "latest_alb": row["albumin"],
                "latest_phos": row["phosphorus"],
                "alerts": row["alerts"],
                "mortality_risk": mort_map.get(row["id"])
            })
        
    return templates.TemplateResponse("analytics_patients.html", {
        "request": request,
        "user": user,
        "patients": enriched_patients,
        "active_filter": filter
    })

@router.get("/patients/{patient_id}", response_class=HTMLResponse)
async def patient_analytics_page(patient_id: int, request: Request, db: Session = Depends(get_db), success: Optional[str] = None):
    _require_analytics_access(request)
    from sqlalchemy.orm import joinedload
    patient = (
        db.query(Patient)
        .options(
            joinedload(Patient.vascular_access),
            joinedload(Patient.comorbidity_profile),
            joinedload(Patient.cardiac),
        )
        .filter(Patient.id == patient_id)
        .first()
    )
    if not patient: raise HTTPException(status_code=404)
    try:
        from database import MonthlyRecord, PatientSymptomReport, InterimLabRecord, DryWeightAssessment
        prefetched_records = (
            db.query(MonthlyRecord)
            .filter(MonthlyRecord.patient_id == patient_id)
            .order_by(MonthlyRecord.record_month.asc())
            .all()
        )
        _raw = (
            db.query(SessionRecord)
            .options(joinedload(SessionRecord.symptom_report))
            .filter(SessionRecord.patient_id == patient_id)
            .order_by(SessionRecord.session_date.desc(), SessionRecord.id.desc())
            .limit(90)
            .all()
        )
        _seen_dates: set = set()
        recent_sessions = []
        for _s in _raw:
            if _s.session_date not in _seen_dates:
                _seen_dates.add(_s.session_date)
                recent_sessions.append(_s)
                if len(recent_sessions) >= 30:
                    break
        prefetched_reports = (
            db.query(PatientSymptomReport)
            .filter(PatientSymptomReport.patient_id == patient_id)
            .order_by(PatientSymptomReport.reported_at.desc())
            .limit(20)
            .all()
        )
        prefetched_interims = (
            db.query(InterimLabRecord)
            .filter(InterimLabRecord.patient_id == patient_id)
            .order_by(InterimLabRecord.lab_date.desc())
            .all()
        )
        prefetched_bia = (
            db.query(DryWeightAssessment)
            .filter(DryWeightAssessment.patient_id == patient_id,
                    DryWeightAssessment.bia_fluid_overload_litres != None)
            .order_by(DryWeightAssessment.assessment_date.desc())
            .first()
        )

        analytics = run_patient_analytics(
            db,
            patient_id,
            prefetched_records=prefetched_records,
            recent_sessions=recent_sessions,
            prefetched_interims=prefetched_interims,
        )
        occult_overload = detect_occult_overload(
            db,
            patient_id,
            prefetched_records=prefetched_records,
            recent_sessions=recent_sessions,
        )
        if occult_overload:
            analytics["occult_alert"] = occult_overload
        pt_events = db.query(ClinicalEvent).filter(ClinicalEvent.patient_id == patient_id).order_by(ClinicalEvent.event_date.desc()).all()
        
        recent_sessions_20 = recent_sessions[:20]
        session_dicts = [
            {
                "session_date": str(s.session_date),
                "blood_flow_rate": s.blood_flow_rate,
                "actual_blood_flow_rate": s.actual_blood_flow_rate,
                "access_condition": s.access_condition,
                "arterial_line_pressure": s.arterial_line_pressure,
                "venous_line_pressure": s.venous_line_pressure,
                "weight_pre": s.weight_pre,
                "weight_post": s.weight_post,
                "uf_volume": s.uf_volume,
                "uf_rate": s.uf_rate,
                "bp_pre_sys": s.bp_pre_sys,
                "bp_pre_dia": s.bp_pre_dia,
                "bp_post_sys": s.bp_post_sys,
                "bp_post_dia": s.bp_post_dia,
                "idh_episode": s.idh_episode,
                "is_emergency": s.is_emergency,
                "early_termination": s.early_termination,
                "pre_hd_dyspnea_likert": s.pre_hd_dyspnea_likert,
                "post_hd_dyspnea_likert": s.post_hd_dyspnea_likert,
                "anticoagulation": s.anticoagulation,
                "duration_hours": s.duration_hours,
                "duration_minutes": s.duration_minutes,
            }
            for s in recent_sessions_20
        ]
        bfr_analytics = analyze_bfr_trend(session_dicts)
        idwg_analytics = analyze_idwg_velocity(session_dicts, patient.dry_weight)
        pds_analytics = analyze_pds(db, patient_id, prefetched_reports=prefetched_reports, recent_sessions=recent_sessions)
        mia_cascade = analyze_mia_cascade(db, patient_id, prefetched_records=prefetched_records, recent_sessions=recent_sessions)
        cardiorenal_cascade = analyze_cardiorenal_cascade(
            db,
            patient_id,
            prefetched_records=prefetched_records,
            prefetched_bia=prefetched_bia,
        )
        avf_cascade_raw = analyze_avf_maturation(db, patient_id, patient_obj=patient, recent_sessions=recent_sessions[:5])
        avf_cascade = {**avf_cascade_raw, **avf_cascade_raw.get("data", {})}
    except Exception as exc:
        logging.exception("patient_analytics_page error for patient_id=%s", patient_id)
        raise HTTPException(status_code=500, detail=str(exc))

    current_month_str = get_current_month_str()
    doctor_note = next((r for r in prefetched_records if r.record_month == current_month_str), None)
    csrf_token = _csrf_signer.sign("events-new").decode()

    return templates.TemplateResponse("patient_analytics.html", {
        "request": request, "patient": patient, "analytics": analytics,
        "pt_events": pt_events, "event_types": EVENT_TYPES, "event_type_groups": EVENT_TYPE_GROUPS,
        "csrf_token": csrf_token,
        "bfr_analytics": bfr_analytics, "idwg_analytics": idwg_analytics, "recent_sessions": recent_sessions_20,
        "pds_analytics": pds_analytics,
        "mia_cascade": mia_cascade,
        "cardiorenal_cascade": cardiorenal_cascade,
        "avf_cascade": avf_cascade,
        "user": get_user(request),
        "doctor_note": doctor_note,
        "current_month": current_month_str,
        "note_saved": success == "note_saved",
    })

@router.get("/patients/{patient_id}/session-trends", response_class=HTMLResponse)
async def patient_session_trends_page(patient_id: int, request: Request, limit: int = 20, db: Session = Depends(get_db)):
    _require_analytics_access(request)
    from sqlalchemy.orm import joinedload
    
    if limit not in (10, 20, 30, 50):
        limit = 20

    patient = (
        db.query(Patient)
        .options(
            joinedload(Patient.vascular_access),
            joinedload(Patient.comorbidity_profile),
            joinedload(Patient.cardiac),
        )
        .filter(Patient.id == patient_id)
        .first()
    )
    if not patient:
        raise HTTPException(status_code=404)

    _raw_sessions = (
        db.query(SessionRecord)
        .options(joinedload(SessionRecord.symptom_report))
        .filter(SessionRecord.patient_id == patient_id)
        .order_by(SessionRecord.session_date.desc(), SessionRecord.id.desc())
        .limit(limit * 3)
        .all()
    )
    _seen_dates: set = set()
    recent_sessions = []
    for _s in _raw_sessions:
        if _s.session_date not in _seen_dates:
            _seen_dates.add(_s.session_date)
            recent_sessions.append(_s)
            if len(recent_sessions) >= limit:
                break

    session_dicts = [
        {
            "session_date": str(s.session_date),
            "blood_flow_rate": s.blood_flow_rate,
            "actual_blood_flow_rate": s.actual_blood_flow_rate,
            "access_condition": s.access_condition,
            "arterial_line_pressure": s.arterial_line_pressure,
            "venous_line_pressure": s.venous_line_pressure,
            "weight_pre": s.weight_pre,
            "weight_post": s.weight_post,
            "uf_volume": s.uf_volume,
            "uf_rate": s.uf_rate,
            "bp_pre_sys": s.bp_pre_sys,
            "bp_pre_dia": s.bp_pre_dia,
            "bp_post_sys": s.bp_post_sys,
            "bp_post_dia": s.bp_post_dia,
            "idh_episode": s.idh_episode,
            "is_emergency": s.is_emergency,
            "early_termination": s.early_termination,
            "pre_hd_dyspnea_likert": s.pre_hd_dyspnea_likert,
            "post_hd_dyspnea_likert": s.post_hd_dyspnea_likert,
            "anticoagulation": s.anticoagulation,
            "duration_hours": s.duration_hours,
            "duration_minutes": s.duration_minutes,
        }
        for s in recent_sessions
    ]

    bfr_analytics = analyze_bfr_trend(session_dicts)
    idwg_analytics = analyze_idwg_velocity(session_dicts, patient.dry_weight)

    idh_last_5 = [s.idh_episode for s in recent_sessions[:5] if s.idh_episode]
    idh_alarm_active = len(idh_last_5) >= 2

    # ── IDH Pre-Session Risk ──────────────────────────────────────────────────
    try:
        from alerts import compute_idh_alert_for_patient
        from database import MonthlyRecord as _MR
        recent_mr = (
            db.query(_MR)
            .filter(_MR.patient_id == patient_id)
            .order_by(_MR.record_month.desc())
            .first()
        )
        mr3 = (
            db.query(_MR)
            .filter(_MR.patient_id == patient_id)
            .order_by(_MR.record_month.desc())
            .limit(3)
            .all()
        )
        idh_risk = compute_idh_alert_for_patient(patient, recent_sessions, recent_mr, mr3)
    except Exception:
        idh_risk = {"has_alert": False}

    return templates.TemplateResponse("session_trends.html", {
        "request": request,
        "patient": patient,
        "recent_sessions": recent_sessions,
        "bfr_analytics": bfr_analytics,
        "idwg_analytics": idwg_analytics,
        "limit": limit,
        "idh_alarm_active": idh_alarm_active,
        "idh_risk": idh_risk,
        "user": get_user(request),
    })


@router.post("/patients/{patient_id}/note")
async def save_doctor_note(
    patient_id: int,
    note: str = Form(...),
    record_month: str = Form(...),
    db: Session = Depends(get_db),
    request: Request = None
):
    _require_analytics_access(request)
    user = get_user(request)
    
    record = db.query(MonthlyRecord).filter(
        MonthlyRecord.patient_id == patient_id,
        MonthlyRecord.record_month == record_month
    ).first()
    
    if not record:
        record = MonthlyRecord(
            patient_id=patient_id,
            record_month=record_month,
            entered_by=getattr(user, "username", "doctor")
        )
        db.add(record)
    
    record.doctor_notes = note
    reviewer = getattr(user, "full_name", getattr(user, "username", "Doctor"))
    record.reviewed_by = reviewer
    record.reviewed_at = datetime.now()

    # Upsert a ClinicalEvent so the Review Queue picks up the updated last_review date.
    # One "Clinical Review" event per patient per day — update notes if one already exists today.
    today = date.today()
    review_event = db.query(ClinicalEvent).filter(
        ClinicalEvent.patient_id == patient_id,
        ClinicalEvent.event_type == "Clinical Review",
        ClinicalEvent.event_date == today,
    ).first()
    if review_event:
        review_event.notes = note
        review_event.created_by = reviewer
    else:
        db.add(ClinicalEvent(
            patient_id=patient_id,
            event_date=today,
            event_type="Clinical Review",
            severity="Low",
            notes=note,
            created_by=reviewer,
        ))

    db.commit()
    return RedirectResponse(url=f"/analytics/patients/{patient_id}?success=note_saved", status_code=303)

# ── Legacy /analytics/api/* (Direct unwrapped JSON responses for HTML templates) ──
# The HTML templates fetch these legacy routes. We return the unwrapped format
# directly to maintain full template compatibility without breaking versioned api_v1.

@router.get("/api/dashboard")
async def _legacy_dashboard(month: Optional[str] = None):
    # Runs compute_dashboard (sync, DB-heavy) in the thread pool so the event
    # loop is free to serve other requests during the cohort aggregation.
    from fastapi.encoders import jsonable_encoder
    from dashboard_logic import get_current_month_str
    month_str = month or get_current_month_str()

    def _compute():
        db = SessionLocal()
        try:
            return compute_dashboard(db, month_str)
        finally:
            db.close()

    try:
        data = await asyncio.to_thread(_compute)
        return JSONResponse(content=jsonable_encoder(data))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/api/cohort-trends")
async def _legacy_cohort_trends():
    from fastapi.encoders import jsonable_encoder
    from ml_analytics import run_cohort_analytics

    def _compute():
        db = SessionLocal()
        try:
            return run_cohort_analytics(db)
        finally:
            db.close()

    try:
        data = await asyncio.to_thread(_compute)
        return JSONResponse(content=jsonable_encoder(data))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/api/at-risk-trends")
async def _legacy_at_risk_trends(parameter: str = "", month: Optional[str] = None):
    from fastapi.encoders import jsonable_encoder
    from ml_analytics import get_at_risk_trends
    from dashboard_logic import get_effective_month

    # Parameters where lower value = worse (min-threshold); others are max-threshold.
    _MIN_PARAMS = {"hb", "albumin", "serum_ferritin", "tsat", "single_pool_ktv", "urr"}

    def _compute():
        from sqlalchemy import func as _sqlfunc
        db = SessionLocal()
        try:
            effective_month = month
            if not effective_month:
                effective_month, _ = get_effective_month(db, None)

            base_result = get_at_risk_trends(db, parameter, effective_month)

            # Also evaluate the newest month in the database.  Some patients enter
            # labs early — their newest record may be weeks ahead of the cohort's
            # effective month, meaning an acute deterioration (e.g. Hb 8.5 → 5.9)
            # is invisible to the effective-month query.
            newest_month = (
                db.query(_sqlfunc.max(MonthlyRecord.record_month)).scalar()
            )
            if newest_month and newest_month > effective_month:
                newer_result = get_at_risk_trends(db, parameter, newest_month)
                newer_patients = newer_result.get("patients", [])
                if newer_patients:
                    base_map = {p["id"]: p for p in base_result.get("patients", [])}
                    is_min = parameter in _MIN_PARAMS
                    for np_ in newer_patients:
                        pid = np_["id"]
                        newer_trend = np_.get("trend") or []
                        newer_latest = next(
                            (v for v in reversed(newer_trend) if v is not None), None
                        )
                        if pid in base_map:
                            base_trend = base_map[pid].get("trend") or []
                            base_latest = next(
                                (v for v in reversed(base_trend) if v is not None), None
                            )
                            if newer_latest is not None and base_latest is not None:
                                is_worse = (newer_latest < base_latest) if is_min else (newer_latest > base_latest)
                                if is_worse:
                                    base_map[pid] = np_
                        else:
                            base_map[pid] = np_
                    base_result["patients"] = list(base_map.values())

            return base_result
        finally:
            db.close()

    try:
        data = await asyncio.to_thread(_compute)
        return JSONResponse(content=jsonable_encoder(data))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/api/patients")
async def _legacy_patients(q: str = "", db: Session = Depends(get_db)):
    from fastapi.encoders import jsonable_encoder
    patients = db.query(Patient).filter(Patient.name.contains(q)).all()
    return JSONResponse(content=jsonable_encoder([{"id": p.id, "name": p.name, "hid_no": p.hid_no} for p in patients]))


@router.post("/admin/train-deterioration-model")
async def admin_train_deterioration_model(db: Session = Depends(get_db)):
    """
    Train (or retrain) the logistic regression deterioration risk model.

    Tries to queue an async Celery task first; if Celery/Redis is unavailable,
    falls back to running training synchronously within the request.
    """
    # Try async path first
    try:
        from tasks import task_train_deterioration_model
        task_train_deterioration_model.delay()
        return JSONResponse(content={"queued": True, "message": "Training job queued. Refresh in ~30 seconds."})
    except Exception:
        logger.warning("Celery unavailable — falling back to synchronous training")

    # Synchronous fallback
    try:
        from ml_risk import train_deterioration_model
        result = train_deterioration_model(db)
        return JSONResponse(content=result)
    except Exception as e:
        logger.exception("Synchronous deterioration model training failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/deterioration-model-status")
async def admin_deterioration_model_status(db: Session = Depends(get_db)):
    """
    Return metadata about the currently deployed deterioration model:
    training date, sample count, cross-validated AUC, feature list,
    latest MLOps metrics (PR-AUC, Brier score, calibration slope, drift),
    and count of MonthlyRecord rows entered since the model was last trained.
    Returns a 'not trained' sentinel if no model has been trained yet.
    """
    try:
        status = get_deterioration_model_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Merge latest MLModelMetrics row (Fix 2)
    try:
        latest_metrics = (
            db.query(MLModelMetrics)
            .filter(MLModelMetrics.model_name == "deterioration_v1")
            .order_by(MLModelMetrics.computed_at.desc())
            .first()
        )
        if latest_metrics:
            status["pr_auc"] = latest_metrics.pr_auc
            status["brier_score"] = latest_metrics.brier_score
            status["calibration_slope"] = latest_metrics.calibration_slope
            status["drift_flagged"] = latest_metrics.drift_flagged
            status["drift_detail"] = latest_metrics.drift_detail
        else:
            status["pr_auc"] = None
            status["brier_score"] = None
            status["calibration_slope"] = None
            status["drift_flagged"] = None
            status["drift_detail"] = None
    except Exception:
        pass

    # Count MonthlyRecord rows entered after the last training run (Fix 4)
    try:
        trained_at_str = status.get("trained_at")
        if trained_at_str:
            from datetime import datetime as _dt
            trained_at_dt = _dt.fromisoformat(trained_at_str)
            new_records = (
                db.query(MonthlyRecord)
                .filter(MonthlyRecord.timestamp > trained_at_dt)
                .count()
            )
        else:
            new_records = db.query(MonthlyRecord).count()
        status["new_records_since_training"] = new_records
    except Exception:
        status["new_records_since_training"] = None

    # When not trained, surface event counts so the UI can show progress toward threshold
    if not status.get("trained"):
        try:
            all_records = db.query(MonthlyRecord).all()
            n_events = sum(
                1 for r in all_records
                if bool(r.hospitalization_this_month)
                or bool(r.hospitalization_diagnosis)
                or bool(r.hospitalization_icd_code)
            )
            from ml_risk import DETERIORATION_FEATURE_NAMES
            n_features   = len(DETERIORATION_FEATURE_NAMES)
            epf_min      = 5
            events_needed = n_features * epf_min
            status["n_events"]      = n_events
            status["events_needed"] = events_needed
            status["n_features"]    = n_features
        except Exception:
            pass

    return JSONResponse(content=status)


@router.get("/admin/model-card")
async def admin_model_card(request: Request):
    """Return the model card JSON for the deterioration risk model (Fix 5)."""
    from dependencies import get_user
    user = get_user(request)
    if not user or user.get("role") not in ("admin", "superadmin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    import json as _json, os as _os
    card_path = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), "models", "model_card_deterioration.json")
    if not _os.path.exists(card_path):
        raise HTTPException(status_code=404, detail="Model card not found. Train the model first.")
    try:
        with open(card_path) as f:
            card = _json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not read model card: {e}")
    return JSONResponse(content=card)

@router.get("/krcrw", response_class=HTMLResponse)
async def krcrw_calculator(request: Request, db: Session = Depends(get_db)):
    _require_analytics_access(request)
    from database import Patient
    patients = db.query(Patient).filter(Patient.is_active == True).order_by(Patient.name).all()
    return templates.TemplateResponse("krcrw_calculator.html", {
        "request": request,
        "patients": patients,
        "user": get_user(request)
    })

@router.post("/api/krcrw")
async def _legacy_krcrw():
    return RedirectResponse(url="/api/v1/krcrw", status_code=308)

@router.post("/api/krcrw/set-baseline")
async def _legacy_krcrw_set_baseline():
    return RedirectResponse(url="/api/v1/krcrw/set-baseline", status_code=308)

@router.get("/phosphate-modeling", response_class=HTMLResponse)
async def phosphate_calculator(request: Request, db: Session = Depends(get_db)):
    _require_analytics_access(request)
    from database import Patient
    patients = db.query(Patient).filter(Patient.is_active == True).order_by(Patient.name).all()
    return templates.TemplateResponse("phosphate_calculator.html", {
        "request": request,
        "patients": patients,
        "user": get_user(request)
    })

@router.get("/urea-modeling", response_class=HTMLResponse)
async def urea_modeling(request: Request, db: Session = Depends(get_db)):
    _require_analytics_access(request)
    from database import Patient
    patients = db.query(Patient).filter(Patient.is_active == True).order_by(Patient.name).all()
    return templates.TemplateResponse("urea_calculator.html", {
        "request": request,
        "patients": patients,
        "user": get_user(request)
    })

@router.get("/api/patients/{patient_id}/latest-monthly")
async def _legacy_patient_latest_monthly(patient_id: int):
    return RedirectResponse(url=f"/api/v1/patients/{patient_id}/latest-monthly", status_code=301)

@router.post("/api/ukm/clearance")
async def _legacy_ukm_clearance():
    return RedirectResponse(url="/api/v1/ukm/clearance", status_code=308)

@router.post("/api/ukm/adequacy")
async def _legacy_ukm_adequacy():
    return RedirectResponse(url="/api/v1/ukm/adequacy", status_code=308)

@router.post("/api/phosphate/calculate")
async def _legacy_phosphate_calculate():
    return RedirectResponse(url="/api/v1/phosphate/calculate", status_code=308)


# ── IDH Prediction Model Endpoints ────────────────────────────────────────────

@router.post("/admin/train-idh-model")
async def admin_train_idh_model():
    """
    Queue an async Celery task to train (or retrain) the IDH prediction model
    against all current SessionRecord data.

    Returns immediately with a queued confirmation.
    Poll GET /analytics/admin/idh-model-status after ~60 seconds.
    """
    try:
        from tasks import task_train_idh_model
        task_train_idh_model.delay()
    except Exception as e:
        logger.exception("Failed to queue IDH model training task")
        raise HTTPException(status_code=500, detail=str(e))
    return JSONResponse(content={
        "queued": True,
        "message": "IDH training job queued. Refresh in ~60 seconds.",
    })


@router.get("/admin/idh-model-status")
async def admin_idh_model_status(db: Session = Depends(get_db)):
    """
    Return metadata about the currently deployed IDH model:
    training date, sample/event counts, cross-validated AUC, feature list,
    latest MLOps metrics, and count of new sessions since last training.
    """
    try:
        status = get_idh_model_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Merge latest MLModelMetrics row
    try:
        latest_metrics = (
            db.query(MLModelMetrics)
            .filter(MLModelMetrics.model_name == "idh_v1")
            .order_by(MLModelMetrics.computed_at.desc())
            .first()
        )
        if latest_metrics:
            status["pr_auc"]              = latest_metrics.pr_auc
            status["brier_score"]         = latest_metrics.brier_score
            status["calibration_slope"]   = latest_metrics.calibration_slope
            status["drift_flagged"]       = latest_metrics.drift_flagged
            status["drift_detail"]        = latest_metrics.drift_detail
        else:
            status.update({"pr_auc": None, "brier_score": None,
                           "calibration_slope": None, "drift_flagged": None, "drift_detail": None})
    except Exception:
        pass

    # Count SessionRecords entered after last training
    try:
        from database import SessionRecord as _SR
        trained_at_str = status.get("trained_at")
        if trained_at_str:
            from datetime import datetime as _dt
            trained_at_dt = _dt.fromisoformat(trained_at_str)
            new_sessions = db.query(_SR).filter(_SR.timestamp > trained_at_dt).count()
        else:
            new_sessions = db.query(_SR).count()
        status["new_sessions_since_training"] = new_sessions
    except Exception:
        status["new_sessions_since_training"] = None

    return JSONResponse(content=status)


@router.get("/api/v1/patients/{patient_id}/idh-risk")
async def patient_idh_risk(
    patient_id: int,
    request: Request,
    db: Session = Depends(get_db),
    session_date: Optional[str] = None,
    uf_volume: Optional[float] = None,
    duration_hours: Optional[int] = None,
    pre_hd_sbp: Optional[float] = None,
    dialysate_temp: Optional[float] = None,
    dialysate_sodium: Optional[float] = None,
    antihypertensive_prehd: Optional[bool] = None,
):
    """
    Compute pre-session IDH risk for a patient's upcoming dialysis session.

    All query parameters are optional — they represent the planned session
    prescription. When omitted, values are taken from the most recent session
    or imputed with safe clinical defaults.

    Returns risk_score (0–100), risk_level, risk_factors, recommended actions,
    and SHAP feature attributions (if model is trained).
    """
    _require_analytics_access(request)
    from sqlalchemy.orm import joinedload as _jl

    patient = (
        db.query(Patient)
        .options(
            _jl(Patient.comorbidity_profile),
            _jl(Patient.cardiac),
        )
        .filter(Patient.id == patient_id)
        .first()
    )
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # Past sessions (last 10, desc)
    past_sessions = (
        db.query(SessionRecord)
        .filter(SessionRecord.patient_id == patient_id)
        .order_by(SessionRecord.session_date.desc())
        .limit(10)
        .all()
    )

    # Most recent monthly record
    recent_mr = (
        db.query(MonthlyRecord)
        .filter(MonthlyRecord.patient_id == patient_id)
        .order_by(MonthlyRecord.record_month.desc())
        .first()
    )

    # Last 3 monthly records for albumin slope
    mr3 = (
        db.query(MonthlyRecord)
        .filter(MonthlyRecord.patient_id == patient_id)
        .order_by(MonthlyRecord.record_month.desc())
        .limit(3)
        .all()
    )

    # If no session plan provided, use last session as template
    last_sess = past_sessions[0] if past_sessions else None

    session_plan = {
        "session_date":              session_date,
        "pre_hd_sbp":                pre_hd_sbp or (last_sess.bp_pre_sys if last_sess else None),
        "uf_volume":                 uf_volume or (last_sess.uf_volume if last_sess else None),
        "duration_hours":            duration_hours or (last_sess.duration_hours if last_sess else 4),
        "duration_minutes":          (last_sess.duration_minutes if last_sess else 0),
        "dialysate_temp":            dialysate_temp or (last_sess.dialysate_temperature if last_sess else None),
        "dialysate_sodium":          dialysate_sodium or (last_sess.dialysate_sodium if last_sess else None),
        "antihypertensive_prehd":    antihypertensive_prehd,
        "weight_pre":                (last_sess.weight_pre if last_sess else None),
        "intradialytic_meals_planned": None,
    }

    patient_info = {
        "id":                  patient.id,
        "age":                 patient.age,
        "dm_status":           patient.dm_status,
        "chf_status":          patient.chf_status,
        "cad_status":          patient.cad_status,
        "history_of_pvd":      patient.history_of_pvd,
        "af_status":           patient.af_status,
        "liver_disease":       patient.liver_disease,
        "ejection_fraction":   patient.ejection_fraction,
        "diastolic_dysfunction": patient.diastolic_dysfunction,
        "dry_weight":          patient.dry_weight,
        "hd_frequency":        patient.hd_frequency,
        "hd_wef_date":         patient.hd_wef_date,
    }

    monthly_data = {
        "albumin":               recent_mr.albumin if recent_mr else None,
        "antihypertensive_count": recent_mr.antihypertensive_count if recent_mr else None,
        "hb":                    recent_mr.hb if recent_mr else None,
        "calcium":               recent_mr.calcium if recent_mr else None,
        "phosphorus":            recent_mr.phosphorus if recent_mr else None,
    }

    try:
        result = await asyncio.to_thread(
            compute_idh_risk,
            session_plan, patient_info, past_sessions, monthly_data, mr3,
        )
    except Exception as exc:
        logger.exception("IDH risk computation failed for patient %s", patient_id)
        raise HTTPException(status_code=500, detail=str(exc))

    from fastapi.encoders import jsonable_encoder
    return JSONResponse(content=jsonable_encoder(result))
