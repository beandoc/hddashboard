"""Clinical Intelligence router.

Provides three analytics pages:
  GET /analytics/dialysis-adequacy   — HDF utilization % and eKt/V monthly monitoring
  GET /analytics/dry-weight          — Per-patient dry weight trajectory
  GET /analytics/vascular-intel      — Per-patient vascular access intelligence
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from config import templates
from database import Patient, get_db
from dependencies import get_user, _require_analytics_access
from dashboard_logic import get_effective_month

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["clinical-intelligence"])


# ── 1. Dialysis Adequacy (HDF utilization + eKt/V monitoring) ────────────────

@router.get("/dialysis-adequacy", response_class=HTMLResponse)
@router.get("/dialysis-adequacy/", response_class=HTMLResponse)
async def dialysis_adequacy(
    request: Request,
    month: Optional[str] = None,
    db: Session = Depends(get_db),
):
    _require_analytics_access(request)
    from services.hdf_analytics import (
        compute_unit_hdf_utilization,
        compute_ektv_monitoring,
        compute_urr_equivalence_table,
    )

    month_str, _ = get_effective_month(db, month)
    hdf_data = compute_unit_hdf_utilization(db, month_str)
    ektv_data = compute_ektv_monitoring(db, month_str)
    urr_table = compute_urr_equivalence_table()

    # Merge patient names
    patient_ids = {r["patient_id"] for r in hdf_data["patient_rows"]}
    patient_ids |= {r["patient_id"] for r in ektv_data["patient_rows"]}
    patients = {
        p.id: p
        for p in db.query(Patient).filter(Patient.id.in_(patient_ids)).all()
    }

    for row in hdf_data["patient_rows"]:
        p = patients.get(row["patient_id"])
        row["patient_name"] = p.name if p else "—"
        row["hid_no"] = p.hid_no if p else "—"

    for row in ektv_data["patient_rows"]:
        p = patients.get(row["patient_id"])
        row["patient_name"] = p.name if p else "—"
        row["hid_no"] = p.hid_no if p else "—"

    return templates.TemplateResponse(
        "dialysis_adequacy.html",
        {
            "request": request,
            "month_str": month_str,
            "hdf": hdf_data,
            "ektv": ektv_data,
            "urr_table": urr_table,
            "user": get_user(request),
        },
    )


# ── 2. Dry Weight Trajectory ──────────────────────────────────────────────────

@router.get("/dry-weight", response_class=HTMLResponse)
@router.get("/dry-weight/", response_class=HTMLResponse)
async def dry_weight_trajectory(
    request: Request,
    patient_id: Optional[int] = None,
    month: Optional[str] = None,
    db: Session = Depends(get_db),
):
    _require_analytics_access(request)
    from services.dry_weight_analytics import (
        compute_patient_dry_weight_trajectory,
        compute_unit_dry_weight_overview,
    )

    month_str, _ = get_effective_month(db, month)

    active_patients = (
        db.query(Patient)
        .filter(Patient.is_active == True)
        .order_by(Patient.name)
        .all()
    )

    selected_patient = None
    trajectory = None
    if patient_id:
        selected_patient = db.query(Patient).filter(Patient.id == patient_id).first()
        if selected_patient:
            trajectory = compute_patient_dry_weight_trajectory(db, patient_id)

    unit_overview = compute_unit_dry_weight_overview(db, month_str)

    # Enrich unit overview rows with patient names
    pid_map = {p.id: p for p in active_patients}
    for row in unit_overview["rows"]:
        p = pid_map.get(row["patient_id"])
        row["patient_name"] = p.name if p else "—"
        row["hid_no"] = p.hid_no if p else "—"
    for row in unit_overview["flagged"]:
        p = pid_map.get(row["patient_id"])
        row["patient_name"] = p.name if p else "—"
        row["hid_no"] = p.hid_no if p else "—"

    return templates.TemplateResponse(
        "dry_weight_trajectory.html",
        {
            "request": request,
            "month_str": month_str,
            "active_patients": active_patients,
            "selected_patient": selected_patient,
            "trajectory": trajectory,
            "unit_overview": unit_overview,
            "user": get_user(request),
        },
    )


# ── 3. Vascular Intelligence ──────────────────────────────────────────────────

@router.get("/vascular-intel", response_class=HTMLResponse)
@router.get("/vascular-intel/", response_class=HTMLResponse)
async def vascular_intelligence(
    request: Request,
    patient_id: Optional[int] = None,
    lookback: int = 3,
    db: Session = Depends(get_db),
):
    _require_analytics_access(request)
    from services.vascular_intelligence import compute_patient_vascular_intelligence

    active_patients = (
        db.query(Patient)
        .filter(Patient.is_active == True)
        .order_by(Patient.name)
        .all()
    )

    selected_patient = None
    intel = None
    if patient_id:
        selected_patient = db.query(Patient).filter(Patient.id == patient_id).first()
        if selected_patient:
            intel = compute_patient_vascular_intelligence(db, patient_id, lookback_months=lookback)

    return templates.TemplateResponse(
        "vascular_intelligence.html",
        {
            "request": request,
            "active_patients": active_patients,
            "selected_patient": selected_patient,
            "intel": intel,
            "lookback": lookback,
            "user": get_user(request),
        },
    )
