from fastapi import APIRouter, Depends, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session
from typing import Optional
import asyncio
import logging

from datetime import date, datetime, timedelta
from database import get_db, SessionLocal, Patient, ClinicalEvent, SessionRecord, MonthlyRecord, MLModelMetrics
from config import templates
from dependencies import get_user, _require_analytics_access
from dashboard_logic import compute_dashboard, get_current_month_str, get_effective_month
from ml_analytics import (
    run_patient_analytics, analyze_bfr_trend,
    analyze_pds, analyze_mia_cascade,
    analyze_cardiorenal_cascade, analyze_avf_maturation, detect_occult_overload,
    get_deterioration_model_status,
    get_all_patients_mortality_risk,
)
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
    month_str, _ = get_effective_month(db, month)
    
    patients = db.query(Patient).filter(Patient.is_active == True).all()
    total_prevalent = len(patients)
    
    # 1. Prevalent AVF Rate (All active patients)
    prevalent_avf = [p for p in patients if p.access_type and "AVF" in p.access_type.upper()]
    prevalent_rate = (len(prevalent_avf) / total_prevalent * 100) if total_prevalent else 0
    
    # 2. Incident AVF Rate (Started this month)
    incident_patients = [p for p in patients if p.hd_wef_date and p.hd_wef_date.strftime("%Y-%m") == month_str]
    incident_avf = [p for p in incident_patients if p.access_type and "AVF" in p.access_type.upper()]
    incident_rate = (len(incident_avf) / len(incident_patients) * 100) if incident_patients else 0
    
    # 3. Watchlists & Intelligence
    maturation_watchlist = []
    functional_watchlist = []
    conversion_watchlist = []
    
    today = datetime.now().date()
    
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
        
        # b) Intelligence Engine (Maturation & Functional)
        status = analyze_avf_maturation(db, p.id)
        if status.get("available"):
            if status.get("maturation_failure"):
                maturation_watchlist.append({
                    "patient": p,
                    "status": status
                })
            if status.get("suboptimal_flow") or status.get("high_recirculation"):
                functional_watchlist.append({
                    "patient": p,
                    "status": status
                })

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
            "target_incident": 65.0
        },
        "watchlist": conversion_watchlist,
        "maturation_watchlist": maturation_watchlist,
        "functional_watchlist": functional_watchlist,
        "user": get_user(request)
    })

@router.get("/mortality-risk", response_class=HTMLResponse)
async def mortality_risk_list(request: Request, db: Session = Depends(get_db)):
    _require_analytics_access(request)
    rows = get_all_patients_mortality_risk(db)

    # Sort: no-data patients last, then descending by 1-yr probability
    rows.sort(key=lambda r: (r["prob_1yr"] is None, -(r["prob_1yr"] or 0)))

    high_risk   = [r for r in rows if r["risk_level"] in ("High", "Very High")]
    moderate    = [r for r in rows if r["risk_level"] == "Moderate"]
    low_risk    = [r for r in rows if r["risk_level"] == "Low"]
    no_data     = [r for r in rows if not r["mort"].get("available")]

    return templates.TemplateResponse("mortality_risk.html", {
        "request":   request,
        "rows":      rows,
        "high_risk": high_risk,
        "moderate":  moderate,
        "low_risk":  low_risk,
        "no_data":   no_data,
        "user":      get_user(request),
    })


@router.get("", response_class=HTMLResponse)
async def analytics_hub(request: Request, db: Session = Depends(get_db)):
    _require_analytics_access(request)
    from dashboard_logic import get_current_month_str
    from ml_analytics import run_cohort_analytics
    
    month_str, _ = get_effective_month(db)
    data = compute_dashboard(db, month_str)
    patient_rows = data.get("patient_rows", [])
    
    return templates.TemplateResponse("analytics_hub.html", {
        "request": request,
        "patients": patient_rows,
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
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient: raise HTTPException(status_code=404)
    try:
        analytics = run_patient_analytics(db, patient_id)
        occult_overload = detect_occult_overload(db, patient_id)
        if occult_overload:
            analytics["occult_alert"] = occult_overload
        pt_events = db.query(ClinicalEvent).filter(ClinicalEvent.patient_id == patient_id).order_by(ClinicalEvent.event_date.desc()).all()
        recent_sessions = db.query(SessionRecord).filter(SessionRecord.patient_id == patient_id).order_by(SessionRecord.session_date.desc()).limit(20).all()

        session_dicts = [
            {
                "session_date": str(s.session_date),
                "blood_flow_rate": s.blood_flow_rate,
                "actual_blood_flow_rate": s.actual_blood_flow_rate,
                "access_condition": s.access_condition,
                "arterial_line_pressure": s.arterial_line_pressure,
                "venous_line_pressure": s.venous_line_pressure,
            }
            for s in recent_sessions
        ]
        bfr_analytics = analyze_bfr_trend(session_dicts)
        pds_analytics = analyze_pds(db, patient_id)
        mia_cascade = analyze_mia_cascade(db, patient_id)
        cardiorenal_cascade = analyze_cardiorenal_cascade(db, patient_id)
        avf_cascade = analyze_avf_maturation(db, patient_id)
    except Exception as exc:
        logging.exception("patient_analytics_page error for patient_id=%s", patient_id)
        raise HTTPException(status_code=500, detail=str(exc))

    return templates.TemplateResponse("patient_analytics.html", {
        "request": request, "patient": patient, "analytics": analytics,
        "pt_events": pt_events, "event_types": EVENT_TYPES, "event_type_groups": EVENT_TYPE_GROUPS,
        "bfr_analytics": bfr_analytics, "recent_sessions": recent_sessions,
        "pds_analytics": pds_analytics,
        "mia_cascade": mia_cascade,
        "cardiorenal_cascade": cardiorenal_cascade,
        "avf_cascade": avf_cascade,
        "user": get_user(request),
        "doctor_note": db.query(MonthlyRecord).filter(
            MonthlyRecord.patient_id == patient_id,
            MonthlyRecord.record_month == get_current_month_str()
        ).first(),
        "current_month": get_current_month_str(),
        "note_saved": success == "note_saved",
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

    def _compute():
        db = SessionLocal()
        try:
            return get_at_risk_trends(db, parameter, month)
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
async def admin_train_deterioration_model():
    """
    Queue an async Celery task to train (or retrain) the logistic regression
    deterioration risk model against all current MonthlyRecord data.

    Returns immediately with a queued confirmation.  Poll
    GET /admin/deterioration-model-status after ~30 seconds to see results.
    """
    try:
        from tasks import task_train_deterioration_model
        task_train_deterioration_model.delay()
    except Exception as e:
        logger.exception("Failed to queue deterioration model training task")
        raise HTTPException(status_code=500, detail=str(e))
    return JSONResponse(content={"queued": True, "message": "Training job queued. Refresh in ~30 seconds."})


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
