"""
fluid_volume_model.py
=====================
Two-compartment plasma refilling / fluid-volume model for intradialytic
haemodynamic stability prediction.

Reference:
    Abohtyra et al. "A Two-Compartment Model of Fluid Exchange During
    Haemodialysis." IEEE Trans Biomed Eng 2018.
    (34% IDH reduction demonstrated in closed-loop UF control study.)

Model overview
--------------
Compartment 1 — Plasma (intravascular):
    V_p(t)   — plasma volume (mL)
    C_p(t)   — plasma protein concentration (g/dL, surrogate for oncotic pressure)

Compartment 2 — Interstitium (extravascular):
    V_i(t)   — interstitial volume (mL)

Fluid exchange:
    J_refill = k_r × (σ × Δ_oncotic - Δ_hydrostatic)   [Starling equation]
    σ        — reflection coefficient (default 0.9 for albumin)
    k_r      — filtration coefficient (mL/min/mmHg per patient weight)

Ultrafiltration removal from plasma:
    dV_p/dt = J_refill - UF_rate   [mL/min]

Relative Blood Volume (RBV):
    RBV(t) = V_p(t) / V_p(0)

IDH is predicted when RBV drops below the critical threshold (default 0.85).
The model returns the recommended maximum UF rate that keeps RBV ≥ threshold
throughout the session.
"""
from __future__ import annotations

import math
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# ── Default physiological parameters (Abohtyra 2018, Table I) ────────────────

_SIGMA          = 0.90    # Staverman reflection coefficient for albumin
_K_R_PER_KG    = 0.006   # mL/min/mmHg/kg  — filtration coefficient (weight-scaled)
_ONCOTIC_SLOPE  = 0.47   # mmHg per g/dL albumin (Landis–Pappenheimer approx.)
_HYDROSTATIC_BASELINE = 3.0  # mmHg — net hydrostatic pressure at start
_HYDROSTATIC_SLOPE    = 0.04 # mmHg drop per mL of UF removed
_RBV_CRITICAL   = 0.85   # critical threshold below which IDH risk rises steeply

# Plasma volume fraction of TBW (Watson) — roughly 1/13 of body weight in L
_PLASMA_VOL_FRACTION = 1.0 / 13.0   # ≈ 76 mL/kg


def _initial_plasma_volume(weight_kg: float, hematocrit: float = 0.35) -> float:
    """Estimate initial plasma volume from weight and hematocrit (Dill & Costill 1974)."""
    tbv = weight_kg * _PLASMA_VOL_FRACTION * 1000  # mL
    return tbv * (1.0 - hematocrit)


def _oncotic_pressure(albumin_g_dl: float) -> float:
    """Approximate colloid oncotic pressure from serum albumin (Landis–Pappenheimer)."""
    return _ONCOTIC_SLOPE * (albumin_g_dl ** 1.6)


def simulate_fluid_volume(
    weight_kg:          float,
    session_h:          float,
    uf_volume_ml:       float,
    albumin_g_dl:       float = 3.8,
    hematocrit:         float = 0.35,
    k_r_override:       Optional[float] = None,
    dt_min:             float = 1.0,
) -> Dict:
    """
    Simulate plasma volume and RBV over a dialysis session.

    Parameters
    ----------
    weight_kg       : Patient weight (kg)
    session_h       : Session duration (hours)
    uf_volume_ml    : Total ultrafiltration volume (mL)
    albumin_g_dl    : Serum albumin (g/dL) — drives oncotic pressure
    hematocrit      : Fractional haematocrit (default 0.35)
    k_r_override    : Override filtration coefficient (mL/min/mmHg). If None,
                      computed from weight × _K_R_PER_KG.
    dt_min          : Integration step (minutes)

    Returns
    -------
    dict with keys:
        rbv_curve           list of RBV values at each time step
        time_min            list of time points (minutes)
        v_plasma_curve      list of plasma volumes (mL)
        rbv_nadir           minimum RBV reached
        rbv_nadir_time_min  time (minutes) when nadir occurred
        idh_predicted       bool — RBV fell below _RBV_CRITICAL
        optimal_uf_rate_ml_kg_h  UF rate that keeps RBV ≥ threshold
        uf_rate_ml_kg_h     actual UF rate used in simulation
        plasma_refilling_rate_ml_min  mean J_refill over session
        available           True
    """
    if weight_kg <= 0 or session_h <= 0 or uf_volume_ml < 0:
        return {"available": False, "error": "Invalid input parameters"}

    session_min = session_h * 60.0
    uf_rate_ml_min = uf_volume_ml / session_min
    uf_rate_ml_kg_h = (uf_rate_ml_min * 60.0) / weight_kg

    k_r = k_r_override if k_r_override is not None else weight_kg * _K_R_PER_KG

    v_p0 = _initial_plasma_volume(weight_kg, hematocrit)
    oncotic_p0 = _oncotic_pressure(albumin_g_dl)

    v_p = v_p0
    total_uf_removed = 0.0
    refill_total = 0.0
    steps = 0

    time_curve = []
    rbv_curve  = []
    vp_curve   = []
    rbv_nadir  = 1.0
    nadir_time = 0.0

    t = 0.0
    while t <= session_min:
        rbv = v_p / v_p0
        time_curve.append(round(t, 1))
        rbv_curve.append(round(rbv, 4))
        vp_curve.append(round(v_p, 1))

        if rbv < rbv_nadir:
            rbv_nadir = rbv
            nadir_time = t

        if t >= session_min:
            break

        # Current oncotic pressure: rises as plasma concentrates during UF
        # Approximation: albumin dilution inverse of volume change
        volume_ratio = v_p0 / max(v_p, v_p0 * 0.5)
        albumin_conc = albumin_g_dl * volume_ratio
        oncotic_p = _oncotic_pressure(albumin_conc)

        # Net hydrostatic pressure decreases as fluid is removed
        hydrostatic_p = max(0.0, _HYDROSTATIC_BASELINE - _HYDROSTATIC_SLOPE * total_uf_removed)

        # Starling transcapillary refilling
        driving_force = _SIGMA * oncotic_p - hydrostatic_p
        j_refill = k_r * max(driving_force, 0.0)

        # Euler integration
        dv_p = (j_refill - uf_rate_ml_min) * dt_min
        v_p = max(v_p + dv_p, v_p0 * 0.3)   # floor at 30% initial volume

        total_uf_removed += uf_rate_ml_min * dt_min
        refill_total += j_refill * dt_min
        steps += 1
        t += dt_min

    mean_refill_rate = (refill_total / session_min) if session_min > 0 else 0.0
    idh_predicted = rbv_nadir < _RBV_CRITICAL

    # Compute optimal UF rate (bisection) that keeps RBV ≥ threshold
    optimal_uf_ml_min = _solve_safe_uf_rate(weight_kg, session_min, albumin_g_dl, hematocrit, k_r, dt_min)
    optimal_uf_ml_kg_h = (optimal_uf_ml_min * 60.0) / weight_kg

    return {
        "available":                  True,
        "rbv_curve":                  rbv_curve,
        "time_min":                   time_curve,
        "v_plasma_curve":             vp_curve,
        "rbv_nadir":                  round(rbv_nadir, 3),
        "rbv_nadir_time_min":         round(nadir_time, 1),
        "idh_predicted":              idh_predicted,
        "uf_rate_ml_kg_h":            round(uf_rate_ml_kg_h, 2),
        "optimal_uf_rate_ml_kg_h":    round(optimal_uf_ml_kg_h, 2),
        "plasma_refilling_rate_ml_min": round(mean_refill_rate, 2),
        "rbv_critical_threshold":     _RBV_CRITICAL,
        "v_plasma_initial_ml":        round(v_p0, 1),
    }


def _solve_safe_uf_rate(
    weight_kg: float,
    session_min: float,
    albumin_g_dl: float,
    hematocrit: float,
    k_r: float,
    dt_min: float,
) -> float:
    """
    Bisection search for the maximum UF rate (mL/min) that keeps RBV ≥ threshold.
    Returns the safe UF rate in mL/min.
    """
    def _nadir(uf_ml_min: float) -> float:
        v_p0 = _initial_plasma_volume(weight_kg, hematocrit)
        v_p  = v_p0
        nadir = 1.0
        total_uf = 0.0
        t = 0.0
        while t < session_min:
            volume_ratio = v_p0 / max(v_p, v_p0 * 0.5)
            albumin_conc = albumin_g_dl * volume_ratio
            oncotic_p    = _oncotic_pressure(albumin_conc)
            hydrostatic_p = max(0.0, _HYDROSTATIC_BASELINE - _HYDROSTATIC_SLOPE * total_uf)
            j_refill      = k_r * max(_SIGMA * oncotic_p - hydrostatic_p, 0.0)
            dv_p = (j_refill - uf_ml_min) * dt_min
            v_p  = max(v_p + dv_p, v_p0 * 0.3)
            total_uf += uf_ml_min * dt_min
            nadir = min(nadir, v_p / v_p0)
            t += dt_min
        return nadir

    lo, hi = 0.0, weight_kg * 20.0 / 60.0   # 0 → 20 mL/kg/h in mL/min
    for _ in range(30):
        mid = (lo + hi) / 2.0
        if _nadir(mid) >= _RBV_CRITICAL:
            lo = mid
        else:
            hi = mid
    return lo


def build_fluid_volume_plotly(result: Dict) -> Dict:
    """Convert simulate_fluid_volume() output to a Plotly-ready trace dict."""
    if not result.get("available"):
        return {}

    threshold_line = [_RBV_CRITICAL] * len(result["time_min"])

    return {
        "rbv_trace": {
            "x":    result["time_min"],
            "y":    result["rbv_curve"],
            "name": "Relative Blood Volume (RBV)",
            "mode": "lines",
            "line": {"color": "#3b9ede", "width": 2},
            "hovertemplate": "t=%{x:.0f} min  RBV=%{y:.3f}<extra></extra>",
        },
        "threshold_trace": {
            "x":    result["time_min"],
            "y":    threshold_line,
            "name": f"IDH threshold (RBV = {_RBV_CRITICAL})",
            "mode": "lines",
            "line": {"color": "#dc3545", "dash": "dash", "width": 1.5},
        },
        "summary": {
            "rbv_nadir":               result["rbv_nadir"],
            "nadir_time_min":          result["rbv_nadir_time_min"],
            "idh_predicted":           result["idh_predicted"],
            "optimal_uf_rate_ml_kg_h": result["optimal_uf_rate_ml_kg_h"],
            "actual_uf_rate_ml_kg_h":  result["uf_rate_ml_kg_h"],
        },
    }
