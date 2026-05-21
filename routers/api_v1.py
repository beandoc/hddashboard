"""
routers/api_v1.py
=================
Versioned JSON API — /api/v1/

All endpoints here carry explicit Pydantic response_model declarations so
FastAPI validates output and generates an accurate OpenAPI schema at /docs.

Auth: session-cookie, same as the Jinja2 backend (not Bearer tokens).
The Next.js frontend uses Bearer tokens — see frontend/INTEGRATION_STATUS.md
before wiring the React client to these endpoints.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import MonthlyRecord, Patient, PatientFeatureSnapshot, get_db
from dependencies import _get_role, get_user

router = APIRouter(prefix="/api/v1", tags=["api-v1"])


# ── Auth dependency ───────────────────────────────────────────────────────────

def _require_staff(request: Request):
    user = get_user(request)
    if not user or _get_role(user) not in ("staff", "doctor", "admin"):
        raise HTTPException(status_code=403, detail="Access denied")
    return user


# ── Response schemas ──────────────────────────────────────────────────────────

class PatientSummary(BaseModel):
    id: int
    name: str
    hid_no: Optional[str] = None

    model_config = {"from_attributes": True}


class PatientListResponse(BaseModel):
    count: int
    patients: List[PatientSummary]


class AlertSummary(BaseModel):
    patient_id: int
    patient_name: str
    parameter: str
    value: Optional[float] = None
    threshold: Optional[float] = None
    message: str


class DashboardStats(BaseModel):
    total_patients: Optional[int] = None
    hb_below_target: Optional[int] = None
    albumin_below_target: Optional[int] = None
    phosphorus_above_target: Optional[int] = None
    ktv_below_target: Optional[int] = None
    alerts: List[AlertSummary] = Field(default_factory=list)
    month: Optional[str] = None


class DashboardResponse(BaseModel):
    available: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class CohortTrendsResponse(BaseModel):
    available: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class AtRiskTrendsResponse(BaseModel):
    available: bool
    parameter: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class LatestMonthlyResponse(BaseModel):
    available: bool
    phosphorus: Optional[float] = None
    phosphate_binder_type: Optional[str] = None
    phosphate_binder_dose_mg: Optional[float] = None
    v_urea: Optional[float] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get(
    "/patients",
    response_model=PatientListResponse,
    summary="Search patients",
    description="Return patients whose name matches the query string. Empty query returns all patients.",
)
async def v1_patients(
    q: str = Query(default="", description="Name substring filter"),
    db: Session = Depends(get_db),
    _user=Depends(_require_staff),
):
    patients = db.query(Patient).filter(Patient.name.contains(q)).all()
    return PatientListResponse(
        count=len(patients),
        patients=[PatientSummary(id=p.id, name=p.name, hid_no=p.hid_no) for p in patients],
    )


class PatientSearchResult(BaseModel):
    id: int
    name: str
    hid_no: Optional[str] = None
    last_hb: Optional[float] = None
    risk_level: str = "stable"  # "high" | "moderate" | "stable" | "unknown"


class PatientSearchResponse(BaseModel):
    count: int
    results: List[PatientSearchResult]


@router.get(
    "/patients/search",
    response_model=PatientSearchResponse,
    summary="Fuzzy patient search with clinical context",
)
async def v1_patients_search(
    q: str = Query(default="", description="Name or HID fuzzy filter"),
    limit: int = Query(default=8, le=20),
    db: Session = Depends(get_db),
    _user=Depends(_require_staff),
):
    from sqlalchemy import or_, func
    from db.models.records import MonthlyRecord as MR

    q = q.strip()
    base = db.query(Patient).filter(Patient.is_active == True)
    if q:
        base = base.filter(
            or_(
                Patient.name.ilike(f"%{q}%"),
                Patient.hid_no.ilike(f"%{q}%"),
            )
        )
    patients = base.order_by(Patient.name).limit(limit).all()

    results = []
    for p in patients:
        latest = (
            db.query(MR)
            .filter(MR.patient_id == p.id)
            .order_by(MR.record_month.desc())
            .first()
        )
        last_hb = latest.hb if latest else None
        albumin = latest.albumin if latest else None

        if last_hb is not None and last_hb < 8:
            risk = "high"
        elif last_hb is not None and last_hb < 10:
            risk = "moderate"
        elif albumin is not None and albumin < 3.5:
            risk = "moderate"
        elif latest is None:
            risk = "unknown"
        else:
            risk = "stable"

        results.append(PatientSearchResult(
            id=p.id, name=p.name, hid_no=p.hid_no,
            last_hb=last_hb, risk_level=risk,
        ))
    return PatientSearchResponse(count=len(results), results=results)


@router.get(
    "/dashboard",
    summary="Dashboard aggregate stats",
    description="Compute and return the current-month dashboard statistics.",
)
async def v1_dashboard(
    month: Optional[str] = Query(default=None, description="YYYY-MM; defaults to current month"),
    db: Session = Depends(get_db),
    _user=Depends(_require_staff),
):
    from dashboard_logic import compute_dashboard, get_current_month_str

    month_str = month or get_current_month_str()
    try:
        data = compute_dashboard(db, month_str)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return JSONResponse(content={"available": True, "data": jsonable_encoder(data), "error": None})


@router.get(
    "/cohort-trends",
    summary="Cohort-level trend analytics",
    description="Return population-level Hb, albumin, phosphorus, and Kt/V trend data.",
)
async def v1_cohort_trends(
    db: Session = Depends(get_db),
    _user=Depends(_require_staff),
):
    from ml_analytics import run_cohort_analytics

    try:
        data = run_cohort_analytics(db)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return JSONResponse(content={"available": True, "data": jsonable_encoder(data), "error": None})


@router.get(
    "/at-risk-trends",
    summary="At-risk patient trends by parameter",
    description="Return monthly counts of patients below/above target for the given parameter.",
)
async def v1_at_risk_trends(
    parameter: str = Query(..., description="Parameter name, e.g. 'hb', 'albumin', 'phosphorus'"),
    month: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    _user=Depends(_require_staff),
):
    from ml_analytics import get_at_risk_trends

    try:
        data = get_at_risk_trends(db, parameter, month)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return JSONResponse(
        content={"available": True, "parameter": parameter, "data": jsonable_encoder(data), "error": None}
    )


@router.get(
    "/patients/{patient_id}/latest-monthly",
    response_model=LatestMonthlyResponse,
    summary="Latest monthly record for a patient",
)
async def v1_patient_latest_monthly(
    patient_id: int,
    db: Session = Depends(get_db),
    _user=Depends(_require_staff),
):
    rec = (
        db.query(MonthlyRecord)
        .filter(MonthlyRecord.patient_id == patient_id)
        .order_by(MonthlyRecord.record_month.desc())
        .first()
    )
    if not rec:
        return LatestMonthlyResponse(available=False)
    return LatestMonthlyResponse(
        available=True,
        phosphorus=rec.phosphorus,
        phosphate_binder_type=rec.phosphate_binder_type,
        phosphate_binder_dose_mg=rec.phosphate_binder_dose_mg,
        v_urea=rec.single_pool_ktv,
    )


# ── Calculator endpoints (moved from /analytics/api/*) ───────────────────────

@router.post("/krcrw", summary="Estimate KRCRw residual kidney clearance")
async def v1_krcrw(payload: Dict[str, Any], _user=Depends(_require_staff)):
    from krcrw_model import estimate_krcrw
    try:
        return estimate_krcrw(
            sex=payload["sex"],
            age=payload["age"],
            weight=payload["weight"],
            g_creat_input=payload["g_creat"],
            lab_day=payload["lab_day"],
            schedule=payload["schedule"],
            pre_creat_measured=payload["pre_creat"],
            ivp2=payload["ivp2"],
            qb=payload["qb"],
            qd=payload["qd"],
            td=payload["td"],
            weekly_fluid_l=payload["weekly_fluid"],
            k_code=payload["k_code"],
            koa=payload["koa"],
            is_black=payload.get("is_black", False),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/krcrw/set-baseline", summary="Save KRCRw baseline for a patient")
async def v1_krcrw_set_baseline(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    _user=Depends(_require_staff),
):
    from database import Patient as _Patient
    p = db.query(_Patient).filter(_Patient.id == payload["patient_id"]).first()
    if not p:
        raise HTTPException(status_code=404)
    p.baseline_gcr = payload["g_creat"]
    p.baseline_vdcr = payload["vdcr"]
    db.commit()
    return {"ok": True}


@router.post("/ukm/clearance", summary="Calculate dialyzer urea clearance")
async def v1_ukm_clearance(payload: Dict[str, Any], _user=Depends(_require_staff)):
    from urea_model import calculate_dialyzer_clearance
    try:
        return calculate_dialyzer_clearance(
            koa_invitro=payload["koa_invitro"],
            qb=payload["qb"],
            qd=payload["qd"],
            td=payload["td"],
            weight_loss_kg=payload["weight_loss_kg"],
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/ukm/adequacy", summary="Calculate std Kt/V adequacy")
async def v1_ukm_adequacy(payload: Dict[str, Any], _user=Depends(_require_staff)):
    from urea_model import calculate_std_ktv, calculate_san_std_ktv
    try:
        res = calculate_std_ktv(
            sp_ktv=payload["sp_ktv"],
            td=payload["td"],
            sessions_per_week=payload["sessions_per_week"],
            weight_gain_weekly_l=payload["weight_gain_weekly_l"],
            v_watson=payload["v_watson"],
        )
        res["san_std_ktv"] = calculate_san_std_ktv(
            std_ktv=res["std_ktv_adjusted"],
            v_watson=payload["v_watson"],
            bsa_dubois=payload.get("bsa", 0),
            m_ratio=payload.get("m_ratio", 20.0),
        )
        return res
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/phosphate/calculate", summary="Phosphate kinetics modelling")
async def v1_phosphate_calculate(payload: Dict[str, Any], _user=Depends(_require_staff)):
    from phosphate_model import estimate_phosphate_kinetics
    try:
        return estimate_phosphate_kinetics(
            sex=payload["sex"],
            weight=payload["weight"],
            v_urea=payload["v_urea"],
            koa_urea=payload["koa_urea"],
            qb=payload["qb"],
            qd=payload["qd"],
            td=payload["td"],
            schedule=payload["schedule"],
            p_pre_measured=payload["p_pre"],
            p_intake_mg_day=payload["p_intake"],
            p_binder_pbe=payload["p_binder"],
            krp_ml_min=payload["krp"],
            solve_for=payload.get("solve_for", "p_pre"),
            koa_p_ratio=payload.get("koa_ratio", 0.5),
            hdf_pre=payload.get("hdf_pre", 0.0),
            hdf_post=payload.get("hdf_post", 0.0),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Schema version endpoint ───────────────────────────────────────────────────

class APIVersionResponse(BaseModel):
    version: str
    schema_version: int
    endpoints: List[str]


@router.get(
    "/schema-version",
    response_model=APIVersionResponse,
    summary="API schema version",
    include_in_schema=True,
)
async def v1_schema_version():
    return APIVersionResponse(
        version="1.0.0",
        schema_version=1,
        endpoints=[
            "GET /api/v1/patients",
            "GET /api/v1/patients/{patient_id}/profile",
            "GET /api/v1/dashboard",
            "GET /api/v1/cohort-trends",
            "GET /api/v1/at-risk-trends",
            "GET /api/v1/patients/{patient_id}/latest-monthly",
            "GET /api/v1/patients/{patient_id}/feature-history",
        ],
    )


@router.get("/patients/{patient_id}/profile", summary="Full patient profile for Next.js patient page")
async def v1_patient_profile(
    patient_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Aggregate endpoint consumed by the Next.js /patients/[id] page.

    Returns identity, latest labs, Hb/albumin trends, active alerts, and
    the current-month mortality risk snapshot — all in one round-trip.
    """
    _require_staff(request)

    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # ── Latest monthly record ─────────────────────────────────────────────────
    from dashboard_logic import get_current_month_str
    latest_rec = (
        db.query(MonthlyRecord)
        .filter(MonthlyRecord.patient_id == patient_id)
        .order_by(MonthlyRecord.record_month.desc())
        .first()
    )

    # ── Trend data (last 12 months, ascending) ────────────────────────────────
    trend_recs = (
        db.query(MonthlyRecord)
        .filter(MonthlyRecord.patient_id == patient_id)
        .order_by(MonthlyRecord.record_month.asc())
        .limit(12)
        .all()
    )
    trend_hb      = [{"month": r.record_month, "value": r.hb}      for r in trend_recs if r.hb is not None]
    trend_albumin = [{"month": r.record_month, "value": r.albumin}  for r in trend_recs if r.albumin is not None]

    # ── Mortality risk snapshot ───────────────────────────────────────────────
    snap = (
        db.query(PatientFeatureSnapshot)
        .filter(
            PatientFeatureSnapshot.patient_id == patient_id,
            PatientFeatureSnapshot.stale == False,
        )
        .order_by(PatientFeatureSnapshot.as_of_month.desc())
        .first()
    )

    mort_risk: dict = {"available": False, "prob_1yr": None, "risk_level": "Unknown", "feature_hash": None}
    if snap:
        try:
            from ml_risk import get_snapshot_feature_vector, _load_deterioration_model
            import numpy as np
            model = _load_deterioration_model()
            if model is not None:
                feats = get_snapshot_feature_vector(db, patient_id, snap.as_of_month)
                if feats:
                    prob = float(model.predict_proba(np.array([feats]))[0][1])
                    level = (
                        "Very High" if prob >= 0.60 else
                        "High"      if prob >= 0.40 else
                        "Moderate"  if prob >= 0.20 else "Low"
                    )
                    mort_risk = {
                        "available":    True,
                        "prob_1yr":     round(prob, 4),
                        "risk_level":   level,
                        "feature_hash": snap.feature_hash,
                    }
        except Exception:
            pass  # graceful degradation — model artifacts may not be present in all envs

    # ── Clinical alerts from latest record ────────────────────────────────────
    alerts: list[str] = []
    if latest_rec:
        if latest_rec.hb is not None and latest_rec.hb < 10:
            alerts.append(f"Low Hb ({latest_rec.hb} g/dL)")
        if latest_rec.albumin is not None and latest_rec.albumin < 3.5:
            alerts.append(f"Low Albumin ({latest_rec.albumin} g/dL)")
        if latest_rec.phosphorus is not None and latest_rec.phosphorus > 5.5:
            alerts.append(f"High Phosphorus ({latest_rec.phosphorus} mg/dL)")
        if latest_rec.idwg is not None and latest_rec.idwg > 2.5:
            alerts.append(f"High IDWG ({latest_rec.idwg} kg)")
        if latest_rec.single_pool_ktv is not None and latest_rec.single_pool_ktv < 1.2:
            alerts.append(f"Low Kt/V ({latest_rec.single_pool_ktv})")

    r = latest_rec
    return jsonable_encoder({
        "id":           patient.id,
        "hid_no":       patient.hid_no,
        "name":         patient.name,
        "age":          patient.age,
        "sex":          patient.sex,
        "diagnosis":    patient.diagnosis,
        "hd_wef_date":  str(patient.hd_wef_date) if patient.hd_wef_date else None,
        "access_type":  patient.access_type,
        "hd_frequency": patient.hd_frequency,
        "hd_slot_1":    patient.hd_slot_1,
        "dry_weight":   patient.dry_weight,
        "is_active":    patient.is_active,
        "latest_labs": {
            "hb":               r.hb              if r else None,
            "albumin":          r.albumin          if r else None,
            "phosphorus":       r.phosphorus       if r else None,
            "calcium":          r.calcium          if r else None,
            "ipth":             r.ipth             if r else None,
            "ferritin":         r.serum_ferritin   if r else None,
            "tsat":             r.tsat             if r else None,
            "kt_v":             r.single_pool_ktv  if r else None,
            "urr":              r.urr              if r else None,
            "idwg":             r.idwg             if r else None,
            "crp":              r.crp              if r else None,
            "wbc_count":        r.wbc_count        if r else None,
            "creatinine":       r.serum_creatinine if r else None,
            "potassium":        r.serum_potassium  if r else None,
            "sodium":           r.serum_sodium     if r else None,
            "nt_probnp":        r.nt_probnp        if r else None,
            "ejection_fraction": r.ejection_fraction if r else None,
            "record_month":     r.record_month     if r else None,
        },
        "mortality_risk": mort_risk,
        "alerts":         alerts,
        "trend_hb":       trend_hb,
        "trend_albumin":  trend_albumin,
    })


@router.get("/patients/{patient_id}/feature-history", summary="Audit: what the model saw per month")
async def v1_patient_feature_history(
    patient_id: int,
    request: Request,
    db: Session = Depends(get_db),
    limit: int = Query(default=12, le=60),
):
    """Return the materialized feature snapshots for a patient, newest first.

    Clinicians use this to verify exactly what input features drove each
    monthly prediction — the feature_hash links the snapshot to the MLPrediction row.
    """
    _require_staff(request)
    snaps = (
        db.query(PatientFeatureSnapshot)
        .filter(PatientFeatureSnapshot.patient_id == patient_id)
        .order_by(PatientFeatureSnapshot.as_of_month.desc())
        .limit(limit)
        .all()
    )
    return jsonable_encoder([
        {
            "as_of_month":    s.as_of_month,
            "feature_vector": s.feature_vector,
            "feature_hash":   s.feature_hash,
            "model_version":  s.model_version,
            "stale":          s.stale,
            "computed_at":    str(s.computed_at) if s.computed_at else None,
        }
        for s in snaps
    ])
