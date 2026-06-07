"""Dry weight trajectory analytics.

Computes historical dry weight target history, drift rate (kg/month),
and a clinically-guided suggested target adjustment based on IDWG patterns
and BIA/IVC assessment data.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from database import DryWeightAssessment, MonthlyRecord, Patient


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

    # ── Formal assessments (BIA / IVC) ────────────────────────────────────────
    assessments_raw: List[DryWeightAssessment] = (
        db.query(DryWeightAssessment)
        .filter(DryWeightAssessment.patient_id == patient_id)
        .order_by(DryWeightAssessment.assessment_date)
        .all()
    )

    assessments = [
        {
            "date": str(a.assessment_date),
            "recommended_dw": a.recommended_dry_weight,
            "bia_fluid_overload_l": a.bia_fluid_overload_litres,
            "bia_overhydration_pct": a.bia_overhydration_percent,
            "bia_phase_angle": a.bia_phase_angle,
            "ivc_diameter_max": a.ivc_diameter_max,
            "ivc_collapsibility": a.ivc_collapsibility_index,
            "nt_probnp": a.nt_probnp,
            "edema_status": a.edema_status,
            "notes": a.assessment_notes,
        }
        for a in assessments_raw
    ]

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
