"""
services/twin_adequacy.py
=========================
Modules 2 + 4 — Dialysis Adequacy & Urea Kinetics:
  - Daugirdas spKt/V, Leypoldt eKt/V / stdKt/V  (Module 2)
  - Two-pool urea kinetics: Qb/Qd → Kd → spKt/V / eKt/V  (Module 4)
"""
from __future__ import annotations

import logging
import math
from typing import Dict, List, Optional

import numpy as np

from services.twin_utils import _safe_float, _UREA_MG_DL_TO_BUN

logger = logging.getLogger(__name__)

# ── Module 2: Dialysis Adequacy (Kt/V) Simulator ─────────────────────────────


def calculate_ktv_daugirdas(
    pre_bun:       float,
    post_bun:      float,
    session_time_h: float,
    uf_volume_L:   float,
    post_weight_kg: float,
) -> Optional[float]:
    """
    Daugirdas single-pool Kt/V (spKt/V) formula.

    spKt/V = -ln(R - 0.008 × t) + (4 - 3.5 × R) × UF / W
    where R = post_BUN / pre_BUN, t = hours, UF in L, W = post-weight kg.

    Returns None if inputs are invalid.
    """
    if None in (pre_bun, post_bun, session_time_h, uf_volume_L, post_weight_kg):
        return None
    if pre_bun <= 0 or post_weight_kg <= 0 or session_time_h <= 0:
        return None

    R = post_bun / pre_bun
    if R <= 0 or R >= 1.5:
        return None

    inner = R - 0.008 * session_time_h
    if inner <= 0:
        return None

    ktv = -math.log(inner) + (4 - 3.5 * R) * (uf_volume_L / post_weight_kg)
    return round(ktv, 3)


def simulate_ktv(
    pre_bun:        float,
    post_bun:       float,
    baseline_session_h:    float,
    baseline_uf_L:  float,
    post_weight_kg: float,
    scenario_session_h:    Optional[float] = None,
    scenario_uf_L:  Optional[float] = None,
) -> Dict:
    """
    Simulate Kt/V for baseline and a scenario with different session length or UF.

    Returns:
        {
            baseline_ktv:  float,
            scenario_ktv:  float,
            adequacy_met:  bool (KDIGO target ≥ 1.2),
            delta_ktv:     float,
        }
    """
    baseline_ktv = calculate_ktv_daugirdas(
        pre_bun, post_bun, baseline_session_h, baseline_uf_L, post_weight_kg
    )

    sc_session_h = scenario_session_h if scenario_session_h is not None else baseline_session_h
    sc_uf_L      = scenario_uf_L if scenario_uf_L is not None else baseline_uf_L

    scenario_ktv = calculate_ktv_daugirdas(
        pre_bun, post_bun, sc_session_h, sc_uf_L, post_weight_kg
    )

    return {
        "available":     baseline_ktv is not None,
        "baseline_ktv":  baseline_ktv,
        "scenario_ktv":  scenario_ktv,
        "adequacy_met":  (scenario_ktv is not None and scenario_ktv >= 1.2),
        "delta_ktv":     round((scenario_ktv or 0) - (baseline_ktv or 0), 3),
        "target_ktv":    1.2,
        "scenario": {
            "session_h": sc_session_h,
            "uf_L":      sc_uf_L,
        },
        "baseline": {
            "session_h": baseline_session_h,
            "uf_L":      baseline_uf_L,
        },
    }



# ── Module 4: Urea Kinetics Extended ─────────────────────────────────────────


def _watson_volume(sex: str, age: float, height_cm: float, weight_kg: float) -> float:
    """Watson (1980) total body water estimation (litres)."""
    try:
        if sex.lower().startswith("m"):
            return 2.447 - 0.09156 * age + 0.1074 * height_cm + 0.3362 * weight_kg
        else:
            return -2.097 + 0.1069 * height_cm + 0.2466 * weight_kg
    except Exception:
        return weight_kg * 0.55  # rough fallback: 55% body weight


def _estimate_cardiac_output(sex: str, age: float, height_cm: float, weight_kg: float) -> float:
    """Estimate baseline Cardiac Output (L/min) using BSA and a normal Cardiac Index of 3.0 L/min/m2."""
    try:
        if height_cm is None or math.isnan(height_cm) or height_cm <= 0:
            height_cm = 170.0
        if weight_kg is None or math.isnan(weight_kg) or weight_kg <= 0:
            weight_kg = 70.0
        if height_cm < 3.0:
            height_cm = height_cm * 100.0
        
        # DuBois Formula
        bsa = 0.007184 * (weight_kg ** 0.425) * (height_cm ** 0.725)
        co = bsa * 3.0
        return max(3.0, min(10.0, co))
    except Exception:
        return 5.0


def simulate_urea_kinetics(
    baseline: dict,
    scenario: dict,
    patient_info: dict,
    records: List[Dict],
) -> Dict:
    """
    Module 4 — Extended urea kinetics using urea_model.py.

    Computes dialyzer clearance (Kd), eKt/V, and standardised Kt/V for
    both the baseline prescription and the proposed scenario.

    Parameters drawn from baseline dict:
        qb_ml_min        — blood flow rate (default 300)
        qd_ml_min        — dialysate flow rate (default 500)
        session_h        — session duration hours
        uf_volume_L      — fluid removal litres
        sessions_per_week — dialysis frequency (default 3)
        koa_urea         — dialyser KoA (default 700)
        idwg_kg          — interdialytic weight gain kg

    Scenario may override any of these.
    """
    from urea_model import calculate_dialyzer_clearance, calculate_std_ktv

    latest = records[0] if records else {}
    weight = _safe_float(
        latest.get("last_prehd_weight") or latest.get("weight")
        or patient_info.get("weight"), 70.0
    )
    sex    = str(patient_info.get("sex") or "m")
    age    = _safe_float(patient_info.get("age"), 50.0)
    height = _safe_float(patient_info.get("height") or patient_info.get("height_cm"), 170.0)
    
    # Use measured BIA volume if available, else Watson
    bia_data = patient_info.get("bia")
    if bia_data and bia_data.get("tbw_l") is not None:
        v_distribution = bia_data["tbw_l"]
    else:
        v_distribution = _watson_volume(sex, age, height, weight)

    # Fetch latest Doppler access flow
    doppler = patient_info.get("doppler")
    qa = doppler.get("qa") if doppler else None

    def _run(p: dict) -> dict:
        qb          = _safe_float(p.get("qb_ml_min"), 300.0)
        qd          = _safe_float(p.get("qd_ml_min"), 500.0)
        session_h   = _safe_float(p.get("session_h") or p.get("session_duration_h"), 4.0)
        session_min = session_h * 60.0
        uf_L        = _safe_float(p.get("uf_volume_L") or p.get("uf_volume", 2500) / 1000, 2.5)
        koa         = _safe_float(p.get("koa_urea"), 700.0)
        idwg        = _safe_float(p.get("idwg_kg"), uf_L)
        spw         = int(p.get("sessions_per_week") or 3)

        try:
            kd_result = calculate_dialyzer_clearance(
                koa_invitro  = koa,
                qb           = qb,
                qd           = qd,
                td           = session_min,
                weight_loss_kg = uf_L,
            )
            kd = kd_result["kd"]
        except Exception:
            kd = None

        # Calculate Access Recirculation
        ar_fraction = 0.0
        if qa is not None and qb > qa:
            ar_fraction = (qb - qa) / qb
            
        kd_effective = kd * (1.0 - ar_fraction) if kd else None

        # spKt/V from Daugirdas — stored values are total urea (mg/dL); convert to BUN
        pre_bun  = _safe_float(latest.get("pre_dialysis_urea"))
        post_bun = _safe_float(latest.get("post_dialysis_urea"))
        if not math.isnan(pre_bun):  pre_bun  *= _UREA_MG_DL_TO_BUN
        if not math.isnan(post_bun): post_bun *= _UREA_MG_DL_TO_BUN

        sp_ktv_daugirdas = calculate_ktv_daugirdas(
            pre_bun if not math.isnan(pre_bun) else None,
            post_bun if not math.isnan(post_bun) else None,
            session_h, uf_L,
            weight - uf_L,
        )
        
        # Scale spKt/V by effective clearance changes if Qb changes
        if sp_ktv_daugirdas is not None:
            baseline_qb = _safe_float(baseline.get("qb_ml_min"), 300.0)
            baseline_qd = _safe_float(baseline.get("qd_ml_min"), 500.0)
            baseline_koa = _safe_float(baseline.get("koa_urea"), 700.0)
            baseline_session_h = _safe_float(baseline.get("session_h") or baseline.get("session_duration_h"), 4.0)
            try:
                kd_base_res = calculate_dialyzer_clearance(
                    koa_invitro  = baseline_koa,
                    qb           = baseline_qb,
                    qd           = baseline_qd,
                    td           = baseline_session_h * 60.0,
                    weight_loss_kg = uf_L,
                )
                kd_base = kd_base_res["kd"]
            except Exception:
                kd_base = 300.0
                
            ar_base = 0.0
            if qa is not None and baseline_qb > qa:
                ar_base = (baseline_qb - qa) / baseline_qb
            kd_base_effective = kd_base * (1.0 - ar_base)
            
            if kd_base_effective > 0 and kd_effective is not None:
                sp_ktv = round(sp_ktv_daugirdas * (kd_effective / kd_base_effective), 3)
            else:
                sp_ktv = sp_ktv_daugirdas
        else:
            if kd_effective and v_distribution > 0:
                sp_ktv = round(kd_effective * session_min / (v_distribution * 1000), 3)
            else:
                sp_ktv = None

        std_result = None
        if sp_ktv:
            try:
                std_result = calculate_std_ktv(
                    sp_ktv             = sp_ktv,
                    td                 = session_min,
                    sessions_per_week  = spw,
                    weight_gain_weekly_l = idwg * spw,
                    v_watson           = v_distribution,
                )
            except Exception:
                pass

        return {
            "kd":           round(kd, 1) if kd else None,
            "kd_effective": round(kd_effective, 1) if kd_effective else None,
            "ar_fraction":  round(ar_fraction, 3),
            "sp_ktv":       sp_ktv,
            "e_ktv":        std_result["ektv"] if std_result else None,
            "std_ktv":      std_result["std_ktv_fixed"] if std_result else None,
            "std_ktv_adj":  std_result["std_ktv_adjusted"] if std_result else None,
            "session_h":    session_h,
            "qb":           qb,
            "qd":           qd,
        }

    # Merge baseline with scenario overrides for simulation
    scenario_params = {**baseline, **{
        k: scenario[k] for k in (
            "session_h", "qb_ml_min", "qd_ml_min", "uf_volume_L", "koa_urea"
        ) if k in scenario
    }}
    # Also handle session_h from the generic "session_h" scenario key
    if "session_h" in scenario:
        scenario_params["session_h"] = scenario["session_h"]

    base_result = _run(baseline)
    scen_result = _run(scenario_params)

    return {
        "available":    True,
        "baseline":     base_result,
        "scenario":     scen_result,
        "delta_sp_ktv": round((scen_result["sp_ktv"] or 0) - (base_result["sp_ktv"] or 0), 3),
        "delta_std_ktv":round((scen_result["std_ktv"] or 0) - (base_result["std_ktv"] or 0), 3),
        "delta_kd":     round((scen_result["kd"] or 0) - (base_result["kd"] or 0), 1),
        "adequacy_met": (scen_result["sp_ktv"] or 0) >= 1.2,
    }


