"""
services/twin_hb.py
===================
Module 1 — Hb Kinetics: ESA/iron → Hb trajectory.
Patient-calibrated OLS regression with Bayesian conjugate Gaussian priors.
"""
from __future__ import annotations

import logging
import math
from typing import Dict, List, Optional

import numpy as np

from services.twin_utils import (
    _safe_float,
    _PRIOR_K_GAIN_MU, _PRIOR_K_GAIN_VAR, _PRIOR_K_GAIN_MIN, _PRIOR_K_GAIN_MAX,
    _PRIOR_K_IRON_MU, _PRIOR_K_IRON_VAR, _PRIOR_K_IRON_MIN, _PRIOR_K_IRON_MAX,
    _OBS_NOISE_VAR,
    _POP_HB_GAIN_PER_1000IU, _POP_HB_DECAY_RATE, _POP_HB_IRON_BOOST,
    _POP_HB_TSAT_BOOST, _POP_HB_NADIR, _UF_IDH_THRESHOLD_ML_KG_H,
)

logger = logging.getLogger(__name__)

# ── Module 1: Hb Kinetics ─────────────────────────────────────────────────────


def _calibrate_hb_kinetics(records: List[Dict]) -> Dict:
    """
    Bayesian conjugate Gaussian estimation of patient-specific Hb kinetic
    parameters from monthly history.

    Model:
        ΔHb ≈ k_gain × esa_iu_norm × 1000 + k_iron × Δ_TSAT + intercept + ε
        ε ~ N(0, σ_ε²)  (observation noise)

    Prior (population):
        k_gain ~ N(μ₀_gain, σ₀²_gain)
        k_iron ~ N(μ₀_iron, σ₀²_iron)

    Posterior (conjugate Gaussian, closed-form, NO sampling):
        Updated independently per parameter to keep computation O(n).
        When n < 3 data pairs the prior dominates and the posterior stays
        wide — giving honest uncertainty rather than a sharp wrong estimate.

    Returns:
        k_gain           — posterior mean
        k_iron           — posterior mean
        intercept        — derived from decay rate
        k_gain_std       — posterior std (credible interval half-width)
        k_iron_std       — posterior std
        obs_noise_std    — sqrt(observation noise variance)
        calibrated       — True if at least 1 data pair was available
        bayes_updated    — True (always for this function)
        n_pairs          — number of data pairs used
        confidence_label — human-readable UI string
        pi_half_width    — 80% posterior predictive half-width per month
    """
    from ml_esa import resolve_esa_weekly_iu, resolve_desidustat_weekly_iu

    pairs = []
    recs  = [r for r in records if r.get("hb") is not None]
    for i in range(len(recs) - 1):
        newer, older = recs[i], recs[i + 1]
        delta_hb = _safe_float(newer.get("hb")) - _safe_float(older.get("hb"))
        iu_sc    = (resolve_esa_weekly_iu(older) or 0.0) + (resolve_desidustat_weekly_iu(older) or 0.0)
        weight   = _safe_float(older.get("last_prehd_weight") or older.get("weight"), 70.0)
        iu_norm  = iu_sc / weight if weight > 0 else 0.0
        tsat_new = _safe_float(newer.get("tsat"), float("nan"))
        tsat_old = _safe_float(older.get("tsat"), float("nan"))
        delta_tsat = (tsat_new - tsat_old) if not (math.isnan(tsat_new) or math.isnan(tsat_old)) else 0.0

        if not (math.isnan(delta_hb) or math.isnan(iu_norm)):
            pairs.append((delta_hb, iu_norm, delta_tsat))

    n = len(pairs)

    # ── Conjugate Gaussian posterior update ───────────────────────────────────
    # For θ ~ N(μ₀, σ₀²) and y_i | θ ~ N(θ·x_i, σ_ε²):
    #   posterior precision: τₙ = 1/σ₀² + Σxᵢ²/σ_ε²
    #   posterior mean:      μₙ = (μ₀/σ₀² + Σxᵢyᵢ/σ_ε²) / τₙ
    #
    # We treat k_gain and k_iron as independent 1-D updates:
    #   x_gain_i = iu_norm_i × 1000
    #   y_gain_i = delta_hb_i − k_iron_prior × delta_tsat_i  (residual)
    #   x_iron_i = delta_tsat_i
    #   y_iron_i = delta_hb_i − k_gain_prior × x_gain_i      (residual)

    sigma2_eps = _OBS_NOISE_VAR

    # k_gain posterior
    prior_gain_prec = 1.0 / _PRIOR_K_GAIN_VAR
    sum_x2_gain     = sum((p[1] * 1000) ** 2 for p in pairs) / sigma2_eps
    sum_xy_gain     = sum((p[1] * 1000) * (p[0] - _PRIOR_K_IRON_MU * p[2]) for p in pairs) / sigma2_eps
    post_gain_prec  = prior_gain_prec + sum_x2_gain
    post_gain_mu    = (prior_gain_prec * _PRIOR_K_GAIN_MU + sum_xy_gain) / post_gain_prec
    post_gain_var   = 1.0 / post_gain_prec
    k_gain          = float(np.clip(post_gain_mu, _PRIOR_K_GAIN_MIN, _PRIOR_K_GAIN_MAX))
    k_gain_std      = max(float(math.sqrt(post_gain_var)), 1e-10)

    # k_iron posterior
    prior_iron_prec = 1.0 / _PRIOR_K_IRON_VAR
    sum_x2_iron     = sum(p[2] ** 2 for p in pairs) / sigma2_eps
    sum_xy_iron     = sum(p[2] * (p[0] - k_gain * p[1] * 1000) for p in pairs) / sigma2_eps
    post_iron_prec  = prior_iron_prec + sum_x2_iron
    post_iron_mu    = (prior_iron_prec * _PRIOR_K_IRON_MU + sum_xy_iron) / post_iron_prec
    post_iron_var   = 1.0 / post_iron_prec
    k_iron          = float(np.clip(post_iron_mu, _PRIOR_K_IRON_MIN, _PRIOR_K_IRON_MAX))
    k_iron_std      = max(float(math.sqrt(post_iron_var)), 1e-10)

    # Intercept: anchored to population decay rate (not estimated from data to
    # avoid overfitting on sparse records)
    hb_ref    = _safe_float(recs[0].get("hb") if recs else None, 10.0)
    intercept = -_POP_HB_DECAY_RATE * hb_ref

    # ── 80% posterior predictive interval half-width ───────────────────────────
    # Posterior predictive variance per simulated month:
    #   σ_pred² ≈ σ_ε² + σ_k_gain² × x_gain² + σ_k_iron² × x_iron²
    #
    # Use the actual mean x_gain from the observed data (or typical clinical
    # value if no data) — avoids the prior-only path understating uncertainty.
    if pairs:
        mean_x_gain = float(np.mean([abs(p[1] * 1000) for p in pairs]))
        mean_x_iron = float(np.mean([abs(p[2]) for p in pairs])) or 5.0
    else:
        mean_x_gain = 0.050 * 1000   # typical: 50 IU/kg/wk × 1000
        mean_x_iron = 5.0            # typical: 5% TSAT change

    pred_var      = (sigma2_eps
                     + post_gain_var * mean_x_gain ** 2
                     + post_iron_var * mean_x_iron ** 2)
    # 80% PI: z ≈ 1.282. Floor at obs noise alone (min meaningful uncertainty)
    pi_half_width = float(max(1.282 * math.sqrt(pred_var),
                              1.282 * math.sqrt(sigma2_eps)))

    # ── Confidence label for UI ───────────────────────────────────────────────
    if n == 0:
        confidence_label = "Prior only — no patient data yet"
    elif n == 1:
        confidence_label = f"1 data point — prior-informed estimate"
    elif n < 3:
        confidence_label = f"{n} data points — prior updating"
    elif n < 6:
        confidence_label = f"{n} data points — partially calibrated"
    else:
        confidence_label = f"{n} data points — patient-calibrated"

    # CI strings: use scientific notation when posterior is data-dominated
    def _ci_str(mu, std):
        hw = 1.645 * std
        if hw < 1e-4:
            return f"{mu:.4f} ± {hw:.2e}  (90% CI, data-dominated)"
        return f"{mu:.4f} ± {hw:.4f}  (90% CI)"

    return {
        "k_gain":           k_gain,
        "k_iron":           k_iron,
        "intercept":        float(intercept),
        "k_gain_std":       k_gain_std,          # raw float — floored at 1e-10
        "k_iron_std":       k_iron_std,          # raw float — floored at 1e-10
        "obs_noise_std":    math.sqrt(sigma2_eps),
        "pi_half_width":    round(pi_half_width, 3),
        "calibrated":       n >= 3,
        "bayes_updated":    True,
        "n_pairs":          n,
        "confidence_label": confidence_label,
        "k_gain_ci":        _ci_str(k_gain, k_gain_std),
        "k_iron_ci":        _ci_str(k_iron, k_iron_std),
    }


def simulate_hb_trajectory(
    records:                List[Dict],
    esa_scenario_iu:        Optional[float] = None,
    desidustat_scenario_iu: Optional[float] = None,
    iron_boost_tsat:        Optional[float] = None,
    horizon_months:         int = 3,
) -> Dict:
    """
    Simulate Hb trajectory under a hypothetical ESA and/or iron protocol.

    Uses Bayesian conjugate posterior for k_gain / k_iron, propagating
    parameter uncertainty into 80% posterior predictive intervals shown
    as a shaded band on the Hb chart.

    Args:
        records:                Patient monthly records, newest-first.
        esa_scenario_iu:        Proposed ESA weekly SC IU. None = keep current.
        desidustat_scenario_iu: Proposed Desidustat weekly IU equivalent. None = keep current.
                                Pass 0 to simulate stopping Desidustat entirely.
        iron_boost_tsat:        Target TSAT % after IV iron repletion. None = keep current.
        horizon_months:         Simulation horizon (1–6 months).

    Returns:
        {
            months, hb_simulated, hb_baseline,
            pi_upper_scenario, pi_lower_scenario,  # 80% predictive interval
            credible_interval,                     # dict of CI strings for UI
            confidence_label,                      # human-readable string
            params,
            confidence: "patient-calibrated" | "bayes-informed" | "prior-only",
        }
    """
    from ml_esa import resolve_esa_weekly_iu, resolve_desidustat_weekly_iu

    if not records or records[0].get("hb") is None:
        return {"available": False, "error": "No baseline Hb available"}

    rec     = records[0]
    hb0     = _safe_float(rec.get("hb"))
    weight  = _safe_float(rec.get("last_prehd_weight") or rec.get("weight"), 70.0)
    tsat0   = _safe_float(rec.get("tsat"), 25.0)

    current_esa_iu  = resolve_esa_weekly_iu(rec) or 0.0
    current_desd_iu = resolve_desidustat_weekly_iu(rec) or 0.0
    current_iu      = current_esa_iu + current_desd_iu
    current_norm    = current_iu / weight if weight > 0 else 0.0

    params    = _calibrate_hb_kinetics(records)
    k_gain    = params["k_gain"]
    k_iron    = params["k_iron"]
    intercept = params["intercept"]

    # Bayesian uncertainty fields (always present after update)
    k_gain_std   = params.get("k_gain_std", _PRIOR_K_GAIN_VAR ** 0.5)
    k_iron_std   = params.get("k_iron_std", _PRIOR_K_IRON_VAR ** 0.5)
    pi_half_base = params.get("pi_half_width", 0.32)  # 80% PI half-width per month

    # Scenario inputs — each drug independently overridable; None = keep current
    scenario_esa   = esa_scenario_iu          if esa_scenario_iu          is not None else current_esa_iu
    scenario_desd  = desidustat_scenario_iu   if desidustat_scenario_iu   is not None else current_desd_iu
    scenario_iu    = scenario_esa + scenario_desd
    scenario_norm  = scenario_iu / weight if weight > 0 else 0.0
    scenario_tsat  = iron_boost_tsat if iron_boost_tsat is not None else tsat0
    tsat_delta     = scenario_tsat - tsat0

    # Predictive uncertainty grows with horizon (sqrt of cumulative variance)
    # σ_pred(m) = sqrt(m) × σ_pred(1)  [independent monthly errors]
    months_sim, months_base = [], []
    pi_upper, pi_lower = [], []
    hb_sim  = hb0
    hb_base = hb0

    for m in range(1, horizon_months + 1):
        # Simulated scenario
        delta_sim  = k_gain * scenario_norm * 1000 + k_iron * tsat_delta + intercept
        hb_sim     = float(np.clip(hb_sim + delta_sim, _POP_HB_NADIR, 18.0))

        # Baseline (no change)
        delta_base = k_gain * current_norm * 1000 + intercept
        hb_base    = float(np.clip(hb_base + delta_base, _POP_HB_NADIR, 18.0))

        # 80% posterior predictive interval: grows as sqrt(m)
        spread = pi_half_base * math.sqrt(m)
        pi_upper.append(round(min(hb_sim + spread, 18.0), 2))
        pi_lower.append(round(max(hb_sim - spread, _POP_HB_NADIR), 2))

        months_sim.append(round(hb_sim, 2))
        months_base.append(round(hb_base, 2))

    # Confidence level string
    n = params.get("n_pairs", 0)
    if n == 0:
        confidence = "prior-only"
    elif params.get("calibrated"):
        confidence = "patient-calibrated"
    else:
        confidence = "bayes-informed"

    return {
        "available":             True,
        "months":                list(range(1, horizon_months + 1)),
        "hb_simulated":          months_sim,
        "hb_baseline":           months_base,
        "pi_upper_scenario":     pi_upper,
        "pi_lower_scenario":     pi_lower,
        "hb_current":            round(hb0, 2),
        "params":                params,
        "confidence":            confidence,
        "confidence_label":      params.get("confidence_label", ""),
        "credible_interval": {
            "k_gain":  params.get("k_gain_ci", ""),
            "k_iron":  params.get("k_iron_ci", ""),
            "n_pairs": n,
        },
        "scenario": {
            "esa_weekly_iu":        scenario_esa,
            "desidustat_weekly_iu": scenario_desd,
            "total_epo_equiv_iu":   scenario_iu,
            "tsat_target":          scenario_tsat,
        },
        "baseline": {
            "esa_weekly_iu":        current_esa_iu,
            "desidustat_weekly_iu": current_desd_iu,
            "total_epo_equiv_iu":   current_iu,
            "tsat_current":         tsat0,
        },
    }


