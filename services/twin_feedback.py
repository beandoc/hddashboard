"""
services/twin_feedback.py
=========================
Outcome backfill for the Digital Dialysis Twin feedback loop.

Matches completed TwinSimulation rows against the MonthlyRecord that
arrived in the month after the simulation was created, then writes a
versioned predicted-vs-actual comparison into actual_outcomes_json.

Idempotent — skips rows that already have actual_outcomes_json set.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


def backfill_twin_outcomes(db, patient_id: Optional[int] = None) -> int:
    """Back-fill actual_outcomes_json for completed simulations.

    Args:
        db: SQLAlchemy Session
        patient_id: if given, restrict to one patient; else process all.

    Returns:
        Number of rows updated.
    """
    from database import TwinSimulation, MonthlyRecord

    query = db.query(TwinSimulation).filter(
        TwinSimulation.actual_outcomes_json.is_(None),
        TwinSimulation.hb_sim_json.isnot(None),
    )
    if patient_id is not None:
        query = query.filter(TwinSimulation.patient_id == patient_id)

    sims = query.all()
    updated = 0

    for sim in sims:
        try:
            updated += _backfill_one(db, sim)
        except Exception as exc:
            logger.warning("twin_feedback: skipping sim %s: %s", sim.id, exc)

    return updated


def _backfill_one(db, sim) -> int:
    from database import MonthlyRecord

    created = sim.created_at
    if created is None:
        return 0

    # Look for the record from the month after the simulation was created
    if created.month == 12:
        target_year, target_month = created.year + 1, 1
    else:
        target_year, target_month = created.year, created.month + 1
    target_prefix = f"{target_year}-{target_month:02d}"

    actual_rec = (
        db.query(MonthlyRecord)
        .filter(
            MonthlyRecord.patient_id == sim.patient_id,
            MonthlyRecord.record_month.like(f"{target_prefix}%"),
        )
        .order_by(MonthlyRecord.record_month.desc())
        .first()
    )
    if actual_rec is None:
        return 0

    # Parse predicted values from stored JSON blobs
    predicted_hb      = _parse_predicted_hb(sim.hb_sim_json)
    predicted_sp_ktv  = _parse_predicted_ktv(sim.ktv_sim_json)
    predicted_p       = _parse_predicted_p(sim.uf_curve_json)

    actual_hb     = getattr(actual_rec, "hb", None)
    actual_sp_ktv = getattr(actual_rec, "single_pool_ktv", None)
    actual_p      = getattr(actual_rec, "phosphorus", None)

    outcomes = {"v": 1, "matched_month": target_prefix}

    if predicted_hb is not None and actual_hb is not None:
        outcomes["hb"] = {
            "predicted": round(predicted_hb, 2),
            "actual":    round(float(actual_hb), 2),
            "abs_error": round(abs(predicted_hb - float(actual_hb)), 2),
        }
    if predicted_sp_ktv is not None and actual_sp_ktv is not None:
        outcomes["sp_ktv"] = {
            "predicted": round(predicted_sp_ktv, 3),
            "actual":    round(float(actual_sp_ktv), 3),
            "abs_error": round(abs(predicted_sp_ktv - float(actual_sp_ktv)), 3),
        }
    if predicted_p is not None and actual_p is not None:
        outcomes["phosphorus"] = {
            "predicted": round(predicted_p, 2),
            "actual":    round(float(actual_p), 2),
            "abs_error": round(abs(predicted_p - float(actual_p)), 2),
        }

    sim.actual_outcomes_json = json.dumps(outcomes)
    db.add(sim)
    db.commit()
    return 1


def _parse_predicted_hb(hb_sim_json: str | None) -> float | None:
    if not hb_sim_json:
        return None
    try:
        data = json.loads(hb_sim_json)
        trajectory = data.get("hb_simulated") or data.get("trajectory") or []
        if trajectory:
            return float(trajectory[0])
    except Exception:
        pass
    return None


def _parse_predicted_ktv(ktv_sim_json: str | None) -> float | None:
    if not ktv_sim_json:
        return None
    try:
        data = json.loads(ktv_sim_json)
        ktv_ext = data.get("ktv_extended") or {}
        return float(ktv_ext.get("scenario", {}).get("sp_ktv") or 0) or None
    except Exception:
        pass
    return None


def _parse_predicted_p(uf_curve_json: str | None) -> float | None:
    if not uf_curve_json:
        return None
    try:
        data = json.loads(uf_curve_json)
        return float(data.get("phosphate", {}).get("scenario_p") or 0) or None
    except Exception:
        pass
    return None
