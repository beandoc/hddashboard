"""
services/twin_idh_sim.py
========================
Module 3 — IDH Risk Simulator: UF rate / dialysate temp / Na → IDH probability.
Thin wrapper around ml_idh.compute_idh_risk exposing scenario-level simulation.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# ── Module 3: IDH Risk Simulator ─────────────────────────────────────────────


def simulate_idh_risk(
    patient_info:        dict,
    baseline_session:    dict,
    past_sessions:       list,
    monthly_data:        dict,
    monthly_records_3mo: list,
    scenario_overrides:  dict,
) -> Dict:
    """
    Compute IDH risk probability for a proposed session prescription change.

    scenario_overrides may contain any keys from session_plan:
        uf_volume, uf_rate_ml_kg_h, dialysate_temp, dialysate_sodium,
        pre_hd_sbp (if hypothetically modified)

    Returns dict with baseline and scenario IDH risk scores.
    """
    try:
        from ml_idh import compute_idh_risk
    except ImportError:
        return {"available": False, "error": "ml_idh module not available"}

    # Baseline risk
    baseline_result = compute_idh_risk(
        session_plan        = baseline_session,
        patient_info        = patient_info,
        past_sessions_list  = past_sessions,
        monthly_data        = monthly_data,
        monthly_records_3mo = monthly_records_3mo,
        log_prediction      = False,
    )

    # Scenario risk — merge overrides into session plan
    scenario_session = {**baseline_session, **scenario_overrides}
    scenario_result  = compute_idh_risk(
        session_plan        = scenario_session,
        patient_info        = patient_info,
        past_sessions_list  = past_sessions,
        monthly_data        = monthly_data,
        monthly_records_3mo = monthly_records_3mo,
        log_prediction      = False,
    )

    base_prob = baseline_result.get("data", {}).get("risk_probability", None) if baseline_result.get("available") else None
    scen_prob = scenario_result.get("data", {}).get("risk_probability", None) if scenario_result.get("available") else None

    return {
        "available":         True,
        "baseline_risk_pct": round(base_prob * 100, 1) if base_prob is not None else None,
        "scenario_risk_pct": round(scen_prob * 100, 1) if scen_prob is not None else None,
        "delta_risk_pct":    round((scen_prob - base_prob) * 100, 1) if (base_prob is not None and scen_prob is not None) else None,
        "baseline_level":    baseline_result.get("data", {}).get("risk_level"),
        "scenario_level":    scenario_result.get("data", {}).get("risk_level"),
        "scenario_overrides": scenario_overrides,
        "baseline_full":     baseline_result,
        "scenario_full":     scenario_result,
        "model_is_heuristic": baseline_result.get("data", {}).get("model_is_heuristic", True) or scenario_result.get("data", {}).get("model_is_heuristic", True),
        "scenario_pi_lower": scenario_result.get("data", {}).get("pi_lower"),
        "scenario_pi_upper": scenario_result.get("data", {}).get("pi_upper"),
    }


def simulate_uf_rate_idh_curve(
    patient_info:        dict,
    baseline_session:    dict,
    past_sessions:       list,
    monthly_data:        dict,
    monthly_records_3mo: list,
    uf_rate_range:       Optional[List[float]] = None,
) -> Dict:
    """
    Sweep UF rate from min to max and return IDH risk at each point.
    Used to plot the UF rate vs IDH risk curve in the twin sandbox.
    """
    if uf_rate_range is None:
        # Extend lower bound to 3.5 mL/kg/h to capture the Castro & Wu NDT 2024
        # mortality-reduction threshold of 4 mL/kg/h within the sweep range.
        uf_rate_range = [round(v, 1) for v in np.arange(3.5, 16.5, 0.5)]

    try:
        from ml_idh import compute_idh_risk
    except ImportError:
        return {"available": False, "error": "ml_idh module not available"}

    risks = []
    for uf_rate in uf_rate_range:
        scenario_session = {**baseline_session, "uf_rate_ml_kg_h": uf_rate}
        scen_result = compute_idh_risk(
            session_plan        = scenario_session,
            patient_info        = patient_info,
            past_sessions_list  = past_sessions,
            monthly_data        = monthly_data,
            monthly_records_3mo = monthly_records_3mo,
            log_prediction      = False,
        )
        scen_prob = scen_result.get("data", {}).get("risk_probability") if scen_result.get("available") else None
        risks.append({
            "uf_rate":    uf_rate,
            "risk_pct":   round(scen_prob * 100, 1) if scen_prob is not None else None,
            "risk_level": scen_result.get("data", {}).get("risk_level"),
        })

    return {
        "available": True,
        "uf_rate_range": uf_rate_range,
        "risks": risks,
        "mortality_threshold_ml_kg_h": 4.0,
    }


