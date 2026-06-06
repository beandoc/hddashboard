"""
routers/acm.py
==============
Anemia Control Model (ACM) HTTP endpoints.

Routes:
    GET  /acm/{patient_id}           — render per-patient ACM dashboard
    POST /acm/{patient_id}/generate  — generate / refresh recommendation
    POST /acm/{patient_id}/decide    — clinician accept / modify / reject
    GET  /acm/audit                  — fleet-wide audit dashboard (staff/admin)
"""
import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from config import templates
from database import (
    ACMRecommendation,
    MLModelMetrics,
    MonthlyRecord,
    Patient,
    get_db,
)
from dependencies import get_user, _require_staff_role
from ml_acm import generate_acm_recommendation, get_acm_model_status, get_fleet_acm_summary, _row_to_dict

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/acm", tags=["acm"])


# ── Helpers ───────────────────────────────────────────────────────────────────


def _records_for_patient(db: Session, patient_id: int, limit: int = 18) -> list:
    """Return newest-first merged sequence of monthly + interim Hb records.

    Monthly records carry the full clinical feature set; interim Hb entries
    (recorded between monthly visits via the patient-profile modal) are injected
    at their exact dates so the ODE sees the real Hb trajectory, not a monthly
    summary.  Clinical features are forward-filled from the nearest preceding
    monthly record by merge_hb_sequence.
    """
    from services.interim_hb_service import get_interim_hbs, merge_hb_sequence

    recs = (
        db.query(MonthlyRecord)
        .filter(MonthlyRecord.patient_id == patient_id)
        .order_by(MonthlyRecord.record_month.desc())
        .limit(limit)
        .all()
    )
    monthly_dicts = [_row_to_dict(rec) for rec in recs]

    interim_hbs = get_interim_hbs(db, patient_id, limit=limit * 3)
    return merge_hb_sequence(monthly_dicts, interim_hbs)


def _get_patient_or_404(db: Session, patient_id: int) -> Patient:
    p = db.query(Patient).filter(Patient.id == patient_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")
    return p


def _patient_meta(patient: Patient) -> dict:
    return {
        "age":    getattr(patient, "age", None),
        "sex":    getattr(patient, "sex", None) or getattr(patient, "gender", None),
        "height": getattr(patient, "height", None),
    }


def _hb_chart_data(records: list) -> dict:
    """Build Plotly-ready Hb history trace from monthly records."""
    months, hb_vals = [], []
    for r in reversed(records):
        if r.get("hb") is not None:
            months.append(r["record_month"])
            hb_vals.append(r["hb"])
    return {"months": months, "hb_vals": hb_vals}


# ── Audit dashboard (fleet level) ─────────────────────────────────────────────


@router.get("/audit", response_class=HTMLResponse)
async def acm_audit(request: Request, db: Session = Depends(get_db)):
    _require_staff_role(request)
    user = get_user(request)

    summary      = get_fleet_acm_summary(db)
    model_status = get_acm_model_status()

    try:
        from ml_acm_ode import get_ode_model_status
        ode_status = get_ode_model_status()
    except Exception:
        ode_status = {}

    # Recent recommendations (last 20)
    recent = (
        db.query(ACMRecommendation)
        .order_by(ACMRecommendation.generated_at.desc())
        .limit(20)
        .all()
    )

    # Latest calibration metrics row for acm_v1
    calib_row = (
        db.query(MLModelMetrics)
        .filter(MLModelMetrics.model_name == "acm_v1")
        .order_by(MLModelMetrics.computed_at.desc())
        .first()
    )
    calib = {}
    if calib_row and calib_row.drift_detail:
        try:
            calib = json.loads(calib_row.drift_detail)
            calib["slope"]          = calib_row.calibration_slope
            calib["intercept"]      = calib_row.calibration_intercept
            calib["mae"]            = calib_row.brier_score   # stored as MAE
            calib["r2"]             = calib_row.roc_auc        # stored as R²
            calib["drift_flagged"]  = calib_row.drift_flagged
            calib["week_start"]     = calib_row.week_start
        except Exception:
            pass

    # Scatter data: predicted vs observed Hb (for reliability diagram)
    scatter_rows = (
        db.query(ACMRecommendation)
        .filter(
            ACMRecommendation.predicted_hb_1mo.isnot(None),
            ACMRecommendation.observed_hb_1mo.isnot(None),
        )
        .order_by(ACMRecommendation.generated_at.desc())
        .limit(200)
        .all()
    )
    scatter_data = [
        {
            "predicted": r.predicted_hb_1mo,
            "observed":  r.observed_hb_1mo,
            "mae":       r.hb_prediction_mae_1mo,
            "decision":  r.clinician_decision or "pending",
        }
        for r in scatter_rows
    ]

    # ESA dose-response data: accepted recs with esa_change_pct and delta_hb
    esa_rows = (
        db.query(ACMRecommendation)
        .filter(
            ACMRecommendation.clinician_decision == "accept",
            ACMRecommendation.esa_change_pct.isnot(None),
            ACMRecommendation.current_hb.isnot(None),
            ACMRecommendation.observed_hb_1mo.isnot(None),
        )
        .limit(200)
        .all()
    )
    esa_response_data = [
        {
            "esa_change_pct": r.esa_change_pct,
            "delta_hb":       round(r.observed_hb_1mo - r.current_hb, 2),
        }
        for r in esa_rows
    ]

    return templates.TemplateResponse("acm_audit.html", {
        "request":          request,
        "user":             user,
        "summary":          summary,
        "model_status":     model_status,
        "ode_status":       ode_status,
        "recent_recs":      recent,
        "calib":            calib,
        "scatter_data":     json.dumps(scatter_data),
        "esa_response_data":json.dumps(esa_response_data),
    })


# ── Per-patient ACM dashboard ─────────────────────────────────────────────────


@router.get("/{patient_id}", response_class=HTMLResponse)
async def acm_patient_dashboard(
    patient_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    _require_staff_role(request)
    user    = get_user(request)
    patient = _get_patient_or_404(db, patient_id)
    records = _records_for_patient(db, patient_id)

    # Latest stored recommendation (if any)
    stored_rec = (
        db.query(ACMRecommendation)
        .filter(ACMRecommendation.patient_id == patient_id)
        .order_by(ACMRecommendation.generated_at.desc())
        .first()
    )

    # Generate a fresh recommendation if none exists or last one is from a prior month
    from dashboard_logic import get_current_month_str
    current_month = get_current_month_str()
    need_fresh = (
        stored_rec is None or
        stored_rec.recommendation_month != current_month
    )
    fresh_rec = None
    if need_fresh and records:
        try:
            fresh_rec = generate_acm_recommendation(patient_id, records, patient_meta=_patient_meta(patient))
        except Exception as e:
            logger.warning(f"ACM generation failed for patient {patient_id}: {e}")

    # Historical Hb chart data
    chart_data = _hb_chart_data(records)

    # Prediction overlay — build from stored or fresh rec
    prediction_overlay = None
    rec_to_show = fresh_rec or (
        {
            "available": True,
            "current_hb": stored_rec.current_hb,
            "hb_status": stored_rec.hb_status,
            "predicted_hb_1mo": stored_rec.predicted_hb_1mo,
            "predicted_hb_2mo": stored_rec.predicted_hb_2mo,
            "predicted_hb_3mo": stored_rec.predicted_hb_3mo,
            "esa_recommendation": {
                "action": stored_rec.esa_action,
                "esa_change_pct": stored_rec.esa_change_pct,
                "recommended_iu_sc": stored_rec.recommended_iu_sc,
                "rationale": stored_rec.esa_rationale,
                "safety_flags": json.loads(stored_rec.safety_flags_json or "[]"),
            },
            "iron_recommendation": {
                "action": stored_rec.iron_action,
                "rationale": stored_rec.iron_rationale,
                "safety_flags": [],
            },
            "safety_flags": json.loads(stored_rec.safety_flags_json or "[]"),
            "confidence": stored_rec.confidence,
            "recommendation_month": stored_rec.recommendation_month,
        } if stored_rec else None
    )

    if rec_to_show and rec_to_show.get("available") and rec_to_show.get("predicted_hb_1mo"):
        prediction_overlay = {
            "months":    [f"+1 mo", "+2 mo", "+3 mo"],
            "hb_values": [
                rec_to_show.get("predicted_hb_1mo"),
                rec_to_show.get("predicted_hb_2mo"),
                rec_to_show.get("predicted_hb_3mo"),
            ],
        }

    return templates.TemplateResponse("acm_dashboard.html", {
        "request":            request,
        "user":               user,
        "patient":            patient,
        "recommendation":     rec_to_show,
        "stored_rec":         stored_rec,
        "chart_data":         json.dumps(chart_data),
        "prediction_overlay": json.dumps(prediction_overlay) if prediction_overlay else "null",
        "current_month":      current_month,
    })


# ── Generate / refresh recommendation ────────────────────────────────────────


@router.post("/{patient_id}/generate")
async def acm_generate(
    patient_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    _require_staff_role(request)
    patient = _get_patient_or_404(db, patient_id)
    records = _records_for_patient(db, patient_id)

    if not records:
        raise HTTPException(status_code=422, detail="No monthly records available to generate recommendation")

    rec = generate_acm_recommendation(patient_id, records, patient_meta=_patient_meta(patient))
    if not rec.get("available"):
        raise HTTPException(status_code=422, detail=rec.get("error", "Generation failed"))

    from dashboard_logic import get_current_month_str
    current_month = get_current_month_str()

    # Upsert into ACMRecommendation table
    existing = (
        db.query(ACMRecommendation)
        .filter(
            ACMRecommendation.patient_id == patient_id,
            ACMRecommendation.recommendation_month == current_month,
        )
        .first()
    )

    esa = rec.get("esa_recommendation", {})
    iron = rec.get("iron_recommendation", {})

    if existing:
        # Refresh — preserve clinician decision if already made
        existing.current_hb           = rec.get("current_hb")
        existing.predicted_hb_1mo     = rec.get("predicted_hb_1mo")
        existing.predicted_hb_2mo     = rec.get("predicted_hb_2mo")
        existing.predicted_hb_3mo     = rec.get("predicted_hb_3mo")
        existing.hb_status            = rec.get("hb_status")
        existing.confidence           = rec.get("confidence")
        existing.esa_action           = esa.get("action")
        existing.esa_change_pct       = esa.get("esa_change_pct")
        existing.recommended_iu_sc    = esa.get("recommended_iu_sc")
        existing.esa_rationale        = esa.get("rationale")
        existing.iron_action          = iron.get("action")
        existing.iron_rationale       = iron.get("rationale")
        existing.safety_flags_json    = json.dumps(rec.get("safety_flags", []))
        existing.generated_at         = datetime.utcnow()
    else:
        db_rec = ACMRecommendation(
            patient_id            = patient_id,
            recommendation_month  = current_month,
            current_hb            = rec.get("current_hb"),
            predicted_hb_1mo      = rec.get("predicted_hb_1mo"),
            predicted_hb_2mo      = rec.get("predicted_hb_2mo"),
            predicted_hb_3mo      = rec.get("predicted_hb_3mo"),
            hb_status             = rec.get("hb_status"),
            confidence            = rec.get("confidence"),
            esa_action            = esa.get("action"),
            esa_change_pct        = esa.get("esa_change_pct"),
            recommended_iu_sc     = esa.get("recommended_iu_sc"),
            esa_rationale         = esa.get("rationale"),
            iron_action           = iron.get("action"),
            iron_rationale        = iron.get("rationale"),
            safety_flags_json     = json.dumps(rec.get("safety_flags", [])),
        )
        db.add(db_rec)

    db.commit()
    return RedirectResponse(url=f"/acm/{patient_id}", status_code=303)


# ── Clinician decision (accept / modify / reject) ─────────────────────────────


@router.post("/{patient_id}/decide")
async def acm_decide(
    patient_id:     int,
    request:        Request,
    rec_id:         int                  = Form(...),
    decision:       str                  = Form(...),
    notes:          Optional[str]        = Form(None),
    modified_iu_sc: Optional[float]      = Form(None),
    modified_iron:  Optional[str]        = Form(None),
    db:             Session              = Depends(get_db),
):
    _require_staff_role(request)
    user = get_user(request)

    if decision not in ("accept", "modify", "reject"):
        raise HTTPException(status_code=422, detail="decision must be accept | modify | reject")

    db_rec = db.query(ACMRecommendation).filter(
        ACMRecommendation.id == rec_id,
        ACMRecommendation.patient_id == patient_id,
    ).first()

    if not db_rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")

    db_rec.clinician_decision   = decision
    db_rec.clinician_notes      = notes
    db_rec.clinician_id         = getattr(user, "username", str(user)) if user else "unknown"
    db_rec.decided_at           = datetime.utcnow()
    db_rec.modified_iu_sc       = modified_iu_sc if decision == "modify" else None
    db_rec.modified_iron_action = modified_iron if decision == "modify" else None

    db.commit()
    logger.info(f"ACM decision '{decision}' recorded for patient {patient_id} by {db_rec.clinician_id}")
    return RedirectResponse(url=f"/acm/{patient_id}", status_code=303)
