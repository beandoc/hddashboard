"""
services/twin_phosphate.py
==========================
Module 5 — Phosphate Kinetics: Qb / session_h / PBE → pre-dialysis phosphate.
Two-pool RK4 model (Daugirdas/Laursen) with optional PyMC MCMC patient calibration.
"""
from __future__ import annotations

import logging
import math
from typing import Dict, List, Optional

import numpy as np

from services.twin_utils import _safe_float
from services.twin_adequacy import _watson_volume

logger = logging.getLogger(__name__)

# ── Module 5: Phosphate Kinetics ──────────────────────────────────────────────


def _phosphate_simple_estimate(
    p_measured: float,
    session_h: float,
    pbe: float,
    p_intake_mg_day: float,
) -> float:
    """
    Linear fallback when the 2-pool RK4 solver diverges.

    Each extra hour of dialysis removes ~0.3 mg/dL of pre-P.
    Each PBE unit of binder reduces pre-P by ~0.1 mg/dL at steady state.
    Dietary intake above 900 mg/day raises pre-P by ~0.2 mg/dL per 200 mg increment.
    These coefficients are derived from KDIGO phosphate kinetics data (Daugirdas 2025).
    """
    base     = p_measured if (p_measured and not math.isnan(p_measured)) else 5.5
    session_delta  = (session_h - 4.0) * (-0.30)
    binder_delta   = (pbe - 3.0)       * (-0.10)
    intake_delta   = ((p_intake_mg_day - 900) / 200) * 0.20
    estimate = base + session_delta + binder_delta + intake_delta
    return round(max(1.0, min(12.0, estimate)), 2)


def simulate_phosphate(
    baseline:     dict,
    scenario:     dict,
    patient_info: dict,
    records:      List[Dict],
) -> Dict:
    """
    Module 5 — Two-pool phosphate kinetics using phosphate_model.py.

    Simulates pre-dialysis phosphate under baseline and scenario prescriptions
    via 14-day RK4 steady-state simulation (Daugirdas / Laursen model).

    Scenario keys consumed:
        session_h       — session duration hours
        qb_ml_min       — blood flow rate
        qd_ml_min       — dialysate flow rate
        p_binder_pbe    — phosphate binder dose (PBE units/day)
        koa_urea        — dialyser KoA for urea (phosphate KoA = 0.5 × urea KoA)
    """
    from phosphate_model import estimate_phosphate_kinetics

    latest  = records[0] if records else {}
    weight  = _safe_float(
        latest.get("last_prehd_weight") or latest.get("weight")
        or patient_info.get("weight"), 70.0
    )
    sex     = str(patient_info.get("sex") or "m")
    age     = _safe_float(patient_info.get("age"), 50.0)
    height  = _safe_float(patient_info.get("height") or 170.0)
    
    # Use measured BIA volume if available, else Watson
    bia_data = patient_info.get("bia")
    if bia_data and bia_data.get("tbw_l") is not None:
        v_urea = bia_data["tbw_l"]
    else:
        v_urea = _watson_volume(sex, age, height, weight)

    p_pre_measured = _safe_float(latest.get("phosphorus"), 5.0)
    if math.isnan(p_pre_measured):
        p_pre_measured = 5.0

    # Use MCMC-calibrated ODE parameters when available (Bangsgaard 2023)
    mcmc_kc_scale  = None
    mcmc_koa_ratio = None
    mcmc_posterior = None
    try:
        from phosphate_mcmc import get_patient_phosphate_posterior
        pid = patient_info.get("id")
        if pid:
            from database import SessionLocal as _SL
            _pdb = _SL()
            try:
                mcmc_post = get_patient_phosphate_posterior(pid, _pdb)
                if mcmc_post:
                    mcmc_kc_scale  = mcmc_post.get("kc_scale_mean")
                    mcmc_koa_ratio = mcmc_post.get("koa_ratio_mean")
                    mcmc_posterior = mcmc_post
            finally:
                _pdb.close()
    except Exception:
        pass

    def _run(p: dict) -> Optional[float]:
        qb        = _safe_float(p.get("qb_ml_min"), 300.0)
        qd        = _safe_float(p.get("qd_ml_min"), 500.0)
        session_h = _safe_float(p.get("session_h") or p.get("session_duration_h"), 4.0)
        session_min = session_h * 60.0
        koa       = _safe_float(p.get("koa_urea"), 700.0)
        pbe       = _safe_float(p.get("p_binder_pbe"), 3.0)
        schedule  = str(p.get("schedule", "135"))   # Mon/Wed/Fri
        krp       = _safe_float(p.get("krp_ml_min"), 0.0)
        p_intake  = _safe_float(p.get("p_intake_mg_day"), 900.0)

        # Quality gate: validate session inputs before simulation
        try:
            from ml_quality_gate import validate_session_inputs
            qr = validate_session_inputs({
                "qb_ml_min": qb, "qd_ml_min": qd,
                "session_h": session_h, "p_binder_pbe": pbe,
            })
            if qr.has_errors:
                p2 = qr.cleaned_record
                qb, qd, session_h, pbe = (
                    p2.get("qb_ml_min", qb), p2.get("qd_ml_min", qd),
                    p2.get("session_h", session_h), p2.get("p_binder_pbe", pbe),
                )
        except Exception:
            pass

        try:
            # Use MCMC-calibrated koa_p_ratio when available (Bangsgaard 2023)
            koa_p_ratio_use = mcmc_koa_ratio if mcmc_koa_ratio is not None else 0.5
            kc_scale_use = mcmc_kc_scale if mcmc_kc_scale is not None else 1.0
            result = estimate_phosphate_kinetics(
                sex             = sex,
                weight          = weight,
                v_urea          = v_urea,
                koa_urea        = koa,
                qb              = qb,
                qd              = qd,
                td              = session_min,
                schedule        = schedule,
                p_pre_measured  = p_pre_measured,
                p_intake_mg_day = p_intake,
                p_binder_pbe    = pbe,
                krp_ml_min      = krp,
                solve_for       = "p_pre",
                koa_p_ratio     = koa_p_ratio_use,
                kc_scale        = kc_scale_use,
            )
            val = result.get("modeled_p_pre")
            # Guard: RK4 can diverge to NaN/Inf with extreme inputs
            if val is None or (isinstance(val, float) and (math.isnan(val) or math.isinf(val))):
                return _phosphate_simple_estimate(p_pre_measured, session_h, pbe, p_intake)
            return val
        except Exception as e:
            logger.debug(f"Phosphate simulation error: {e}")
            return _phosphate_simple_estimate(p_pre_measured, session_h, pbe, p_intake)

    scenario_params = {**baseline, **{
        k: scenario[k] for k in (
            "session_h", "qb_ml_min", "qd_ml_min", "p_binder_pbe", "koa_urea",
            "p_intake_mg_day",
        ) if k in scenario
    }}
    if "session_h" in scenario:
        scenario_params["session_h"] = scenario["session_h"]

    base_p = _run(baseline)
    scen_p = _run(scenario_params)

    target_p_high = 5.5   # mg/dL — KDIGO upper limit
    target_p_low  = 3.5

    def _status(p):
        if p is None: return "unknown"
        if p > target_p_high: return "above_target"
        if p < target_p_low:  return "below_target"
        return "on_target"

    return {
        "available":       True,
        "baseline_p":      round(base_p, 2) if base_p else None,
        "scenario_p":      round(scen_p, 2) if scen_p else None,
        "delta_p":         round((scen_p or 0) - (base_p or 0), 2) if (base_p and scen_p) else None,
        "baseline_status": _status(base_p),
        "scenario_status": _status(scen_p),
        "target_range":    [target_p_low, target_p_high],
        "p_measured":      p_pre_measured,
        "baseline_p_intake": baseline.get("p_intake_mg_day", 1200.0),
        "baseline_pbe":    baseline.get("p_binder_pbe"),
        "scenario_pbe":    scenario_params.get("p_binder_pbe"),
        # MCMC calibration metadata (Bangsgaard 2023)
        "mcmc_koa_ratio":  mcmc_koa_ratio,
        "mcmc_kc_scale":   mcmc_kc_scale,
        "mcmc_calibrated": mcmc_koa_ratio is not None,
        "mcmc_posterior":  mcmc_posterior,
    }


