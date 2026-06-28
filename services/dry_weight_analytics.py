"""Dry weight trajectory analytics.

Computes historical dry weight target history, drift rate (kg/month),
and a clinically-guided suggested target adjustment based on IDWG patterns
and BIA/IVC assessment data.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import json as _json

from sqlalchemy.orm import Session

from database import DryWeightAssessment, MonthlyRecord, Patient
from db.models.research import ResearchRecord


# ── Thresholds ────────────────────────────────────────────────────────────────
_IDWG_HIGH_KG: float = 2.0   # Consistent IDWG > 2 kg → consider increasing DW
_IDWG_LOW_KG: float = 0.5    # Consistent IDWG < 0.5 kg → consider decreasing DW
_DW_STEP_KG: float = 0.5     # Suggested adjustment step size


def compute_patient_dry_weight_trajectory(
    db: Session,
    patient_id: int,
    lookback_months: int = 12,
) -> Dict[str, Any]:
    """
    Full dry weight trajectory for a single patient.

    Returns:
      history        – monthly (month, target_weight, idwg) records ascending
      drift_kg_month – average change in target weight per month (last 3 months)
      trend_dir      – 'increasing' | 'decreasing' | 'stable' | 'insufficient_data'
      current_target – most recent target_dry_weight
      suggested_target – clinician-aid suggestion (not a prescription)
      assessments    – list of formal DryWeightAssessment records
    """
    records: List[MonthlyRecord] = (
        db.query(MonthlyRecord)
        .filter(
            MonthlyRecord.patient_id == patient_id,
            MonthlyRecord.target_dry_weight.isnot(None),
        )
        .order_by(MonthlyRecord.record_month)
        .all()
    )

    history = [
        {
            "month": r.record_month,
            "target_weight": r.target_dry_weight,
            "idwg": r.idwg,
            "last_prehd_weight": r.last_prehd_weight,
        }
        for r in records
    ]

    # ── Drift calculation (last 3 data points) ────────────────────────────────
    drift_kg_month: Optional[float] = None
    trend_dir = "insufficient_data"
    if len(history) >= 2:
        recent = history[-3:]
        weights = [h["target_weight"] for h in recent]
        n = len(weights)
        drift_kg_month = round((weights[-1] - weights[0]) / max(1, n - 1), 2)
        if drift_kg_month > 0.1:
            trend_dir = "increasing"
        elif drift_kg_month < -0.1:
            trend_dir = "decreasing"
        else:
            trend_dir = "stable"

    # ── Suggested target (IDWG-guided) ────────────────────────────────────────
    current_target = history[-1]["target_weight"] if history else None
    suggested_target: Optional[float] = current_target

    if history and current_target is not None:
        recent_3 = history[-3:]
        valid_idwg = [h["idwg"] for h in recent_3 if h["idwg"] is not None]
        if valid_idwg:
            avg_idwg = sum(valid_idwg) / len(valid_idwg)
            if avg_idwg > _IDWG_HIGH_KG:
                suggested_target = round(current_target + _DW_STEP_KG, 1)
            elif avg_idwg < _IDWG_LOW_KG:
                suggested_target = round(current_target - _DW_STEP_KG, 1)

    # ── Formal assessments (DryWeightAssessment table) ───────────────────────
    assessments_raw: List[DryWeightAssessment] = (
        db.query(DryWeightAssessment)
        .filter(DryWeightAssessment.patient_id == patient_id)
        .order_by(DryWeightAssessment.assessment_date)
        .all()
    )

    assessments = [
        {
            "date": str(a.assessment_date),
            "source": "clinical",
            "recommended_dw": a.recommended_dry_weight,
            "bia_fluid_overload_l": a.bia_fluid_overload_litres,
            "bia_overhydration_pct": a.bia_overhydration_percent,
            "bia_phase_angle": a.bia_phase_angle,
            "bia_tbw_l": a.bia_total_body_water,
            "ivc_diameter_max": a.ivc_diameter_max,
            "ivc_collapsibility": a.ivc_collapsibility_index,
            "nt_probnp": a.nt_probnp,
            "edema_status": a.edema_status,
            "notes": a.assessment_notes,
            # Research-only fields absent in clinical records
            "body_fat_mass": None,
            "fat_free_mass": None,
            "skeletal_muscle_mass": None,
            "obesity_degree": None,
            "pct_body_fat": None,
        }
        for a in assessments_raw
    ]

    # ── BIA records from the Research section (ResearchRecord, test_type BIA) ─
    research_bia = (
        db.query(ResearchRecord)
        .filter(
            ResearchRecord.patient_id == patient_id,
            ResearchRecord.test_type.ilike("%BIA%"),
        )
        .order_by(ResearchRecord.test_date)
        .all()
    )

    for r in research_bia:
        d: dict = {}
        if r.data:
            try:
                d = _json.loads(r.data)
            except Exception:
                pass

        def _f(key: str) -> Optional[float]:
            v = d.get(key)
            try:
                return float(v) if v not in (None, "", "None") else None
            except (TypeError, ValueError):
                return None

        assessments.append({
            "date": str(r.test_date),
            "source": "research",
            "recommended_dw": None,
            "bia_fluid_overload_l": None,
            "bia_overhydration_pct": None,
            "bia_phase_angle": _f("phase_angle"),
            "bia_tbw_l": _f("tbw_liters"),
            "ivc_diameter_max": None,
            "ivc_collapsibility": None,
            "nt_probnp": None,
            "edema_status": None,
            "notes": r.notes,
            "body_fat_mass": _f("body_fat_mass"),
            "fat_free_mass": _f("fat_free_mass"),
            "skeletal_muscle_mass": _f("skeletal_muscle_mass"),
            "obesity_degree": _f("obesity_degree"),
            "pct_body_fat": _f("percentage_body_fat"),
        })

    assessments.sort(key=lambda x: x["date"])

    return {
        "patient_id": patient_id,
        "history": history,
        "drift_kg_month": drift_kg_month,
        "trend_dir": trend_dir,
        "current_target": current_target,
        "suggested_target": suggested_target,
        "assessments": assessments,
    }


def compute_unit_dry_weight_overview(db: Session, month_str: str) -> Dict[str, Any]:
    """
    Cohort-level overview of dry weight targets and IDWG for the current month.
    Highlights patients where target may need review.
    """
    records: List[MonthlyRecord] = (
        db.query(MonthlyRecord)
        .filter(MonthlyRecord.record_month == month_str)
        .all()
    )

    rows = []
    for r in records:
        if r.target_dry_weight is None:
            continue
        idwg = r.idwg
        flag = None
        if idwg is not None:
            if idwg > _IDWG_HIGH_KG:
                flag = "high_idwg"
            elif idwg < _IDWG_LOW_KG:
                flag = "low_idwg"
        rows.append({
            "patient_id": r.patient_id,
            "target_dry_weight": r.target_dry_weight,
            "idwg": idwg,
            "flag": flag,
        })

    flagged = [r for r in rows if r["flag"]]
    return {
        "month_str": month_str,
        "total_patients": len(rows),
        "flagged_count": len(flagged),
        "rows": rows,
        "flagged": flagged,
    }
