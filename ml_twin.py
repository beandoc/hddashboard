"""
ml_twin.py
==========
Digital Dialysis Twin (DDT) for hemodialysis patients — Phase 1: Integrated.

Implements a multi-domain mechanistic simulation engine where a single
prescription change propagates across ALL physiological subsystems simultaneously.

Modules (Phase 1):
1. Hb Kinetics        — ESA/iron → Hb trajectory (patient-calibrated OLS + population priors)
2. Dialysis Adequacy  — Session h / UF → spKt/V (Daugirdas), eKt/V, stdKt/V (Leypoldt)
3. IDH Risk           — UF rate / dialysate temp / Na → IDH probability (ml_idh.py)
4. Urea Kinetics      — Qb / Qd / session_h → dialyzer clearance Kd, eKt/V, std Kt/V
5. Phosphate Kinetics — Qb / session_h / PBE → pre-dialysis phosphate (2-pool RK4)

Cross-domain cascade rules (interdependencies):
    session_h ↑  →  spKt/V ↑, phosphate removal ↑, UF rate ↓ (→ IDH risk ↓)
    Qb ↑         →  dialyzer Kd ↑ → spKt/V ↑, phosphate clearance ↑
    Qd ↑         →  dialyzer Kd ↑ (modest) → Kt/V ↑, phosphate ↑
    UF rate ↑    →  IDH risk ↑, Kt/V ↑ (convective component)
    PBE ↑        →  pre-P ↓ (binder removes ~45 mg P per PBE unit per day)
    ESA dose ↑   →  Hb ↑ (months 1–3)
    Iron (TSAT↑) →  Hb ↑ (months 1–3)

All five modules run in one `run_scenario()` call. `build_twin_plotly_data()`
converts the result to JSON-serialisable Plotly traces.
"""
from __future__ import annotations

import logging
import math
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# ── Population-level Bayesian priors ─────────────────────────────────────────
# Derived from published HD cohort data (Locatelli et al., Nephrol Dial Trans;
# Fishbane & Spinowitz, AJKD 2018; Macdougall et al., NDT 2010).
#
# Gaussian conjugate prior: θ ~ N(μ₀, σ₀²)
# Posterior after n observations: μₙ = (μ₀/σ₀² + Σxᵢyᵢ/σ_ε²) / (1/σ₀² + Σxᵢ²/σ_ε²)
#
# k_gain  [g/dL per 1 IU/kg/wk per month]
_PRIOR_K_GAIN_MU    = 0.018   # population mean
_PRIOR_K_GAIN_VAR   = 0.007 ** 2  # population variance (SD ≈ 0.007)
_PRIOR_K_GAIN_MIN   = 0.003
_PRIOR_K_GAIN_MAX   = 0.10

# k_iron  [g/dL per 1% TSAT increase per month]
_PRIOR_K_IRON_MU    = 0.015
_PRIOR_K_IRON_VAR   = 0.006 ** 2
_PRIOR_K_IRON_MIN   = 0.0
_PRIOR_K_IRON_MAX   = 0.05

# Observation noise: month-to-month Hb variability unexplained by ESA/iron
_OBS_NOISE_VAR      = 0.25 ** 2  # SD ≈ 0.25 g/dL (measurement + biological)

# Legacy scalar constants (kept for backward compatibility)
_POP_HB_GAIN_PER_1000IU  = _PRIOR_K_GAIN_MU
_POP_HB_DECAY_RATE        = 0.04
_POP_HB_IRON_BOOST        = 0.003
_POP_HB_TSAT_BOOST        = _PRIOR_K_IRON_MU
_POP_HB_NADIR             = 8.0     # g/dL — physiologic minimum modelled

# Session physics
_UF_IDH_THRESHOLD_ML_KG_H = 10.0   # mL/kg/h — above this IDH risk rises steeply

# Unit conversion — clinics record serum urea (mg/dL total urea); Daugirdas
# formula expects BUN (blood urea nitrogen).  BUN = urea × (28 / 60).
# NOTE: since Daugirdas uses only the ratio R = post/pre, both pre and post must
# use the *same* units — so the factor always cancels in Kt/V.  The conversion
# is applied for correctness of the BUN values themselves (e.g. display, audit).
_UREA_MG_DL_TO_BUN = 28.0 / 60.0   # ≈ 0.4667

# ── Helper utilities ──────────────────────────────────────────────────────────


def _safe_float(v, default: float = float("nan")) -> float:
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


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
    from ml_esa import _resolve_weekly_iu_sc

    pairs = []
    recs  = [r for r in records if r.get("hb") is not None]
    for i in range(len(recs) - 1):
        newer, older = recs[i], recs[i + 1]
        delta_hb = _safe_float(newer.get("hb")) - _safe_float(older.get("hb"))
        iu_sc    = _resolve_weekly_iu_sc(older) or 0.0
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
    records:          List[Dict],
    esa_scenario_iu:  Optional[float] = None,
    iron_boost_tsat:  Optional[float] = None,
    horizon_months:   int = 3,
) -> Dict:
    """
    Simulate Hb trajectory under a hypothetical ESA and/or iron protocol.

    Uses Bayesian conjugate posterior for k_gain / k_iron, propagating
    parameter uncertainty into 80% posterior predictive intervals shown
    as a shaded band on the Hb chart.

    Args:
        records:          Patient monthly records, newest-first.
        esa_scenario_iu:  Proposed weekly SC IU dose. None = keep current.
        iron_boost_tsat:  Target TSAT % after IV iron repletion. None = keep current.
        horizon_months:   Simulation horizon (1–6 months).

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
    from ml_esa import _resolve_weekly_iu_sc

    if not records or records[0].get("hb") is None:
        return {"available": False, "error": "No baseline Hb available"}

    rec     = records[0]
    hb0     = _safe_float(rec.get("hb"))
    weight  = _safe_float(rec.get("last_prehd_weight") or rec.get("weight"), 70.0)
    tsat0   = _safe_float(rec.get("tsat"), 25.0)

    current_iu   = _resolve_weekly_iu_sc(rec) or 0.0
    current_norm = current_iu / weight if weight > 0 else 0.0

    params    = _calibrate_hb_kinetics(records)
    k_gain    = params["k_gain"]
    k_iron    = params["k_iron"]
    intercept = params["intercept"]

    # Bayesian uncertainty fields (always present after update)
    k_gain_std   = params.get("k_gain_std", _PRIOR_K_GAIN_VAR ** 0.5)
    k_iron_std   = params.get("k_iron_std", _PRIOR_K_IRON_VAR ** 0.5)
    pi_half_base = params.get("pi_half_width", 0.32)  # 80% PI half-width per month

    # Scenario inputs
    scenario_iu    = esa_scenario_iu if esa_scenario_iu is not None else current_iu
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
            "esa_weekly_iu": scenario_iu,
            "tsat_target":   scenario_tsat,
        },
        "baseline": {
            "esa_weekly_iu": current_iu,
            "tsat_current":  tsat0,
        },
    }


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

    risks = []
    for uf_rate in uf_rate_range:
        result = simulate_idh_risk(
            patient_info        = patient_info,
            baseline_session    = baseline_session,
            past_sessions       = past_sessions,
            monthly_data        = monthly_data,
            monthly_records_3mo = monthly_records_3mo,
            scenario_overrides  = {"uf_rate_ml_kg_h": uf_rate},
        )
        risks.append({
            "uf_rate":    uf_rate,
            "risk_pct":   result.get("scenario_risk_pct"),
            "risk_level": result.get("scenario_level"),
        })

    return {
        "available": True,
        "uf_rate_range": uf_rate_range,
        "risks": risks,
        "mortality_threshold_ml_kg_h": 4.0,
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
        # MCMC calibration metadata (Bangsgaard 2023)
        "mcmc_koa_ratio":  mcmc_koa_ratio,
        "mcmc_kc_scale":   mcmc_kc_scale,
        "mcmc_calibrated": mcmc_koa_ratio is not None,
        "mcmc_posterior":  mcmc_posterior,
    }


# ── Cross-domain cascade summary ──────────────────────────────────────────────


def _cascade_summary(scenario: dict, baseline: dict, results: dict) -> List[dict]:
    """
    Generate a human-readable list of cascade effects for the UI.
    Each item: {domain, direction, message, delta}.
    """
    items = []
    s = scenario or {}

    def _changed(key, default_val, base_keys=None):
        if key not in s:
            return False
        if base_keys is None:
            base_keys = [key]
        base_val = None
        for bk in base_keys:
            if bk in baseline and baseline[bk] is not None:
                base_val = baseline[bk]
                break
        if base_val is None:
            base_val = default_val
        try:
            return abs(float(s[key]) - float(base_val)) > 1e-7
        except (ValueError, TypeError):
            return s[key] != base_val

    session_changed = _changed("session_h", 4.0, ["session_duration_h", "session_h"])
    qb_changed      = _changed("qb_ml_min", 300.0, ["qb_ml_min", "qb"])
    uf_changed      = _changed("uf_rate_ml_kg_h", 10.0, ["uf_rate_ml_kg_h", "uf_rate"]) or _changed("uf_volume_L", 2.5, ["uf_volume_L", "uf_volume"])
    pbe_changed     = _changed("p_binder_pbe", 3.0, ["p_binder_pbe", "pbe"])
    temp_changed    = _changed("dialysate_temp", 36.5, ["dialysate_temp", "temp"])
    na_changed      = _changed("dialysate_sodium", 138.0, ["dialysate_sodium", "sodium"])

    ktv  = results.get("ktv_extended", {})
    phos = results.get("phosphate", {})
    idh  = results.get("idh_sim", {})

    if session_changed:
        new_h = _safe_float(s.get("session_h"), 4.0)
        old_h = _safe_float(baseline.get("session_h") or baseline.get("session_duration_h"), 4.0)
        dh = new_h - old_h
        d_ktv = ktv.get("delta_sp_ktv") or 0
        items.append({
            "domain": "Session duration",
            "direction": "up" if dh > 0 else "down",
            "message": (
                f"Session {new_h:.2g}h (+{dh:.2g}h) → "
                f"spKt/V {'+' if d_ktv >= 0 else ''}{d_ktv:.2f} · "
                f"phosphate removal {'↑' if dh > 0 else '↓'} · "
                f"effective UF rate {'↓' if dh > 0 else '↑'} (same fluid, more time)"
            ),
        })

    if qb_changed:
        new_qb = _safe_float(s.get("qb_ml_min"), 300.0)
        old_qb = _safe_float(baseline.get("qb_ml_min"), 300.0)
        d_kd = ktv.get("delta_kd") or 0
        items.append({
            "domain": "Blood flow (Qb)",
            "direction": "up" if new_qb > old_qb else "down",
            "message": (
                f"Qb {new_qb:.0f} mL/min → dialyzer Kd {'+' if d_kd >= 0 else ''}{d_kd:.0f} mL/min · "
                f"urea clearance {'↑' if new_qb > old_qb else '↓'} · "
                f"phosphate removal {'↑' if new_qb > old_qb else '↓'}"
            ),
        })

    if uf_changed:
        rate = _safe_float(s.get("uf_rate_ml_kg_h"), 10.0)
        d_idh = idh.get("delta_risk_pct") or 0
        items.append({
            "domain": "UF rate",
            "direction": "up" if d_idh > 0 else "down",
            "message": (
                f"UF {rate:.1f} mL/kg/h → IDH risk {'+' if d_idh >= 0 else ''}{d_idh:.1f}% · "
                f"convective phosphate removal {'↑' if rate > 10 else '↓'}"
            ),
        })

    if pbe_changed:
        d_p = phos.get("delta_p") or 0
        items.append({
            "domain": "Phosphate binder",
            "direction": "down",
            "message": (
                f"PBE {s.get('p_binder_pbe', '?')} units/day → "
                f"pre-P {'↑' if d_p > 0 else '↓'} {abs(d_p):.2f} mg/dL "
                f"({'above' if (phos.get('scenario_p') or 0) > 5.5 else 'below' if (phos.get('scenario_p') or 0) < 3.5 else 'within'} target)"
            ),
        })

    if temp_changed:
        t = _safe_float(s.get("dialysate_temp"), 36.5)
        d_idh = idh.get("delta_risk_pct") or 0
        items.append({
            "domain": "Dialysate temperature",
            "direction": "down" if t < 36.5 else "up",
            "message": (
                f"Dialysate {t}°C → IDH risk {'+' if d_idh >= 0 else ''}{d_idh:.1f}% "
                f"({'cooler dialysate reduces IDH risk' if t < 36.5 else 'warmer dialysate increases IDH risk'})"
            ),
        })

    if na_changed:
        na = _safe_float(s.get("dialysate_sodium"), 138.0)
        items.append({
            "domain": "Dialysate sodium",
            "direction": "up" if na > 138 else "down",
            "message": (
                f"Dialysate Na {na:.0f} mEq/L — "
                f"{'higher Na reduces osmotic gradient → less IDH but may worsen thirst/IDWG' if na > 138 else 'lower Na increases fluid shift → watch for cramps/IDH'}"
            ),
        })

    if not items:
        items.append({
            "domain": "No changes",
            "direction": "neutral",
            "message": "No prescription parameters changed from baseline.",
        })

    return items


# ── Integrated Scenario Runner ────────────────────────────────────────────────


def run_scenario(
    patient_id:          int,
    records:             List[Dict],
    patient_info:        dict,
    baseline_session:    dict,
    past_sessions:       list,
    monthly_data:        dict,
    monthly_records_3mo: list,
    scenario:            dict,
    db:                  Optional[Session] = None,
) -> Dict:
    """
    Phase 1 integrated scenario runner — all five modules with cross-domain cascade.

    A single prescription change propagates across Hb, Kt/V, phosphate, and IDH.

    scenario keys (all optional):
        esa_weekly_iu    — ESA dose IU/week SC
        iron_tsat_target — target TSAT % after iron repletion
        session_h        — session duration hours
        qb_ml_min        — blood flow rate mL/min
        qd_ml_min        — dialysate flow rate mL/min
        uf_volume_L      — UF volume litres
        uf_rate_ml_kg_h  — UF rate mL/kg/h
        dialysate_temp   — °C
        dialysate_sodium — mEq/L
        p_binder_pbe     — phosphate binder dose PBE units/day
        p_intake_mg_day  — dietary phosphate mg/day
        koa_urea         — dialyser KoA (urea)
    """
    from services.nutrition_service import get_7day_rolling_mean_phosphate
    
    # Query rolling mean dietary phosphate
    phosphate_data = {"value": 1200.0, "source": "default_1200mg"}
    if db is not None:
        try:
            from sqlalchemy.orm import Session
            phosphate_data = get_7day_rolling_mean_phosphate(db, patient_id)
        except Exception as e:
            logger.warning(f"Error querying dietary phosphate: {e}")
            
    baseline_p_intake = phosphate_data.get("value") or 1200.0
    source = phosphate_data.get("source", "default_1200mg")
    
    if "p_intake_mg_day" in scenario:
        source = "manual_entry"
        
    baseline_session = {**baseline_session, "p_intake_mg_day": baseline_p_intake}

    latest = records[0] if records else {}
    pre_bun  = _safe_float(latest.get("pre_dialysis_urea"))
    post_bun = _safe_float(latest.get("post_dialysis_urea"))
    # Convert from total urea (mg/dL) to BUN (mg/dL) — factor cancels in Kt/V ratio
    if not math.isnan(pre_bun):  pre_bun  *= _UREA_MG_DL_TO_BUN
    if not math.isnan(post_bun): post_bun *= _UREA_MG_DL_TO_BUN
    post_wt  = _safe_float(latest.get("last_prehd_weight") or latest.get("weight"), 70.0)
    base_h   = _safe_float(
        baseline_session.get("session_duration_h") or baseline_session.get("session_h"), 4.0
    )
    base_uf_L = _safe_float(baseline_session.get("uf_volume"), 2500) / 1000

    # ── 1. Hb kinetics ────────────────────────────────────────────────────────
    hb_sim = simulate_hb_trajectory(
        records          = records,
        esa_scenario_iu  = scenario.get("esa_weekly_iu"),
        iron_boost_tsat  = scenario.get("iron_tsat_target"),
        horizon_months   = 3,
    )

    # ── 2. Daugirdas spKt/V (simple, requires BUN) ────────────────────────────
    ktv_sim = simulate_ktv(
        pre_bun            = pre_bun if not math.isnan(pre_bun) else None,
        post_bun           = post_bun if not math.isnan(post_bun) else None,
        baseline_session_h = base_h,
        baseline_uf_L      = base_uf_L,
        post_weight_kg     = post_wt,
        scenario_session_h = scenario.get("session_h"),
        scenario_uf_L      = scenario.get("uf_volume_L"),
    )

    # ── 3. IDH risk — cascade: longer session → lower effective UF rate ───────
    # If session_h changes but UF volume is the same, effective UF rate decreases.
    scen_session_h  = scenario.get("session_h", base_h)
    scen_uf_volume  = scenario.get("uf_volume_L", base_uf_L) * 1000  # to mL
    weight_for_rate = post_wt or 70.0
    # Compute implied UF rate from volume + session duration
    implied_uf_rate = (scen_uf_volume / scen_session_h / weight_for_rate) if scen_session_h > 0 else None

    session_overrides: dict = {}
    if scenario.get("uf_rate_ml_kg_h") is not None:
        session_overrides["uf_rate_ml_kg_h"] = scenario["uf_rate_ml_kg_h"]
    elif implied_uf_rate is not None and "session_h" in scenario:
        # Longer session with same UF volume → lower rate → encode cascade
        session_overrides["uf_rate_ml_kg_h"] = round(implied_uf_rate, 2)
    if scenario.get("dialysate_temp") is not None:
        session_overrides["dialysate_temp"] = scenario["dialysate_temp"]
    if scenario.get("dialysate_sodium") is not None:
        session_overrides["dialysate_sodium"] = scenario["dialysate_sodium"]
    if scenario.get("uf_volume_L") is not None:
        session_overrides["uf_volume"] = scenario["uf_volume_L"] * 1000

    idh_sim = simulate_idh_risk(
        patient_info        = patient_info,
        baseline_session    = baseline_session,
        past_sessions       = past_sessions,
        monthly_data        = monthly_data,
        monthly_records_3mo = monthly_records_3mo,
        scenario_overrides  = session_overrides,
    )

    # ── 4. UF rate sweep (IDH heatmap) ────────────────────────────────────────
    uf_curve = simulate_uf_rate_idh_curve(
        patient_info        = patient_info,
        baseline_session    = baseline_session,
        past_sessions       = past_sessions,
        monthly_data        = monthly_data,
        monthly_records_3mo = monthly_records_3mo,
    )

    # ── 5. Extended urea kinetics (Module 4) ──────────────────────────────────
    ktv_extended = simulate_urea_kinetics(
        baseline     = baseline_session,
        scenario     = scenario,
        patient_info = patient_info,
        records      = records,
    )

    # ── 6. Phosphate kinetics (Module 5) ──────────────────────────────────────
    phosphate = simulate_phosphate(
        baseline     = baseline_session,
        scenario     = scenario,
        patient_info = patient_info,
        records      = records,
    )

    # ── 7. Two-compartment fluid/volume model (Abohtyra 2018) ─────────────────
    fluid_volume = {}
    try:
        from fluid_volume_model import simulate_fluid_volume, build_fluid_volume_plotly
        scen_uf_vol_ml = scenario.get("uf_volume_L", base_uf_L) * 1000
        scen_h = scenario.get("session_h", base_h)
        latest_albumin = monthly_data.get("albumin") if monthly_data else None
        fluid_sim = simulate_fluid_volume(
            weight_kg    = post_wt,
            session_h    = scen_h,
            uf_volume_ml = scen_uf_vol_ml,
            albumin_g_dl = float(latest_albumin) if latest_albumin else 3.8,
        )
        fluid_volume = build_fluid_volume_plotly(fluid_sim)
        fluid_volume["raw"] = fluid_sim
    except Exception as _fv_exc:
        logger.debug("Fluid volume model skipped: %s", _fv_exc)

    # ── 8. Cross-domain cascade summary ───────────────────────────────────────
    cascade = _cascade_summary(
        scenario  = scenario,
        baseline  = baseline_session,
        results   = {
            "ktv_extended": ktv_extended,
            "phosphate":    phosphate,
            "idh_sim":      idh_sim,
        },
    )

    # ── 8. Doppler Shunt & Hemodynamics ──────────────────────────────────────
    doppler = patient_info.get("doppler")
    qa = doppler.get("qa") if doppler else None
    
    # Estimate baseline Cardiac Output (CO)
    sex_co = str(patient_info.get("sex") or "m")
    age_co = _safe_float(patient_info.get("age"), 50.0)
    height_co = _safe_float(patient_info.get("height") or patient_info.get("height_cm"), 170.0)
    weight_co = _safe_float(patient_info.get("weight"), 70.0)
    co = patient_info.get("cardiac_output")
    if co is None:
        co = _estimate_cardiac_output(sex_co, age_co, height_co, weight_co)
    
    shunt_ratio = None
    cardiac_strain = "unknown"
    if qa is not None:
        qa_l_min = qa / 1000.0
        shunt_ratio = qa_l_min / co
        if qa > 1500.0 or shunt_ratio > 0.30:
            cardiac_strain = "high"
        elif qa < 600.0 or shunt_ratio < 0.20:
            cardiac_strain = "low"
        else:
            cardiac_strain = "moderate"
            
    hemodynamics = {
        "estimated_co": round(co, 2),
        "co_is_measured": patient_info.get("cardiac_output") is not None,
        "shunt_ratio":  round(shunt_ratio, 3) if shunt_ratio is not None else None,
        "cardiac_strain": cardiac_strain,
        "qa": qa,
    }

    return {
        "patient_id":   patient_id,
        "scenario":     scenario,
        "hb_sim":       hb_sim,
        "ktv_sim":      ktv_sim,
        "ktv_extended": ktv_extended,
        "phosphate":    phosphate,
        "idh_sim":      idh_sim,
        "uf_curve":     uf_curve,
        "cascade":      cascade,
        "hemodynamics": hemodynamics,
        "fluid_volume": fluid_volume,
        "bia":          patient_info.get("bia"),
        "doppler":      patient_info.get("doppler"),
        "dietary_phosphate_source": source,
    }


def build_twin_plotly_data(twin_result: Dict) -> Dict:
    """
    Convert run_scenario() output into Plotly chart traces (JSON-serialisable).
    Keys: hb_traces, ktv_bar_data, idh_gauge, uf_curve_traces,
          phosphate_bar_data, std_ktv_bar_data, cascade.
    """
    hb_sim      = twin_result.get("hb_sim", {})
    ktv_sim     = twin_result.get("ktv_sim", {})
    ktv_ext     = twin_result.get("ktv_extended", {})
    idh_sim     = twin_result.get("idh_sim", {})
    uf_curve    = twin_result.get("uf_curve", {})
    phosphate   = twin_result.get("phosphate", {})
    cascade     = twin_result.get("cascade", [])
    fluid_volume= twin_result.get("fluid_volume", {})

    # ── Hb trajectory + 80% prediction interval ──────────────────────────────
    months_labels = [f"Month +{m}" for m in hb_sim.get("months", [])]
    hb_traces = []
    if hb_sim.get("available"):
        # Baseline line
        hb_traces.append({
            "x": months_labels,
            "y": hb_sim.get("hb_baseline", []) or hb_sim.get("hb_ode_baseline", []),
            "name": "Current Protocol",
            "mode": "lines+markers",
            "line": {"dash": "dash", "color": "#6c757d"},
            "marker": {"size": 6},
        })
        # Scenario upper PI bound (filled area)
        pi_upper = hb_sim.get("pi_upper_scenario")
        pi_lower = hb_sim.get("pi_lower_scenario")
        if pi_upper and pi_lower:
            hb_traces.append({
                "x": months_labels + list(reversed(months_labels)),
                "y": pi_upper + list(reversed(pi_lower)),
                "fill": "toself",
                "fillcolor": "rgba(13,110,253,0.10)",
                "line": {"color": "rgba(0,0,0,0)"},
                "name": "80% Prediction Interval",
                "showlegend": True,
                "hoverinfo": "skip",
            })
        # Scenario point estimate
        hb_traces.append({
            "x": months_labels,
            "y": (hb_sim.get("hb_hybrid_scenario")
                  or hb_sim.get("hb_simulated")
                  or hb_sim.get("hb_ode_scenario", [])),
            "name": "Proposed Scenario",
            "mode": "lines+markers",
            "line": {"color": "#0d6efd"},
            "marker": {"size": 8},
        })
        # ODE warnings as annotation metadata
        ode_warnings = hb_sim.get("warnings", [])
        if ode_warnings:
            hb_traces.append({
                "__ode_warnings": ode_warnings,  # consumed by frontend JS
                "x": [], "y": [], "mode": "lines",
                "showlegend": False, "name": "__warnings__",
            })

    # ── spKt/V bar (Daugirdas) ────────────────────────────────────────────────
    ktv_bar_data = {}
    if ktv_sim.get("available"):
        scen_ktv = ktv_sim.get("scenario_ktv") or 0
        ktv_bar_data = {
            "categories": ["Baseline spKt/V", "Scenario spKt/V", "Target (≥1.2)"],
            "values":     [ktv_sim.get("baseline_ktv") or 0, scen_ktv, 1.2],
            "colors":     [
                "#6c757d",
                "#0d6efd" if scen_ktv >= 1.2 else "#dc3545",
                "#198754",
            ],
        }

    # ── Std Kt/V + eKt/V (extended urea kinetics) ────────────────────────────
    std_ktv_bar_data = {}
    if ktv_ext.get("available"):
        base = ktv_ext.get("baseline", {})
        scen = ktv_ext.get("scenario", {})
        std_ktv_bar_data = {
            "categories": [
                "Base eKt/V", "Scen eKt/V",
                "Base Std Kt/V", "Scen Std Kt/V",
                "Base Kd", "Scen Kd",
            ],
            "values": [
                base.get("e_ktv") or 0,
                scen.get("e_ktv") or 0,
                base.get("std_ktv") or 0,
                scen.get("std_ktv") or 0,
                (base.get("kd") or 0) / 100,   # scale for display alongside Kt/V
                (scen.get("kd") or 0) / 100,
            ],
            "base_kd":      base.get("kd"),
            "scenario_kd":  scen.get("kd"),
            "base_ektv":    base.get("e_ktv"),
            "scenario_ektv":scen.get("e_ktv"),
            "base_std":     base.get("std_ktv"),
            "scenario_std": scen.get("std_ktv"),
            "delta_sp_ktv": ktv_ext.get("delta_sp_ktv"),
            "delta_kd":     ktv_ext.get("delta_kd"),
        }

    # ── IDH gauge ─────────────────────────────────────────────────────────────
    idh_gauge = {}
    if idh_sim.get("available"):
        idh_gauge = {
            "baseline_pct":  idh_sim.get("baseline_risk_pct"),
            "scenario_pct":  idh_sim.get("scenario_risk_pct"),
            "delta":         idh_sim.get("delta_risk_pct"),
            "scenario_level":idh_sim.get("scenario_level"),
            "baseline_level":idh_sim.get("baseline_level"),
            "model_is_heuristic": idh_sim.get("model_is_heuristic", True),
            # MAPIE 80% conformal prediction interval on scenario probability
            "pi_lower_pct":  round(idh_sim.get("scenario_pi_lower", 0) * 100, 1) if idh_sim.get("scenario_pi_lower") is not None else None,
            "pi_upper_pct":  round(idh_sim.get("scenario_pi_upper", 0) * 100, 1) if idh_sim.get("scenario_pi_upper") is not None else None,
        }

    # ── UF rate sweep ─────────────────────────────────────────────────────────
    uf_curve_traces = []
    if uf_curve.get("available"):
        risks = uf_curve.get("risks", [])
        mortality_thresh = uf_curve.get("mortality_threshold_ml_kg_h", 4.0)
        uf_curve_traces = [
            {
                "x":    [r["uf_rate"] for r in risks],
                "y":    [r["risk_pct"] for r in risks],
                "name": "IDH Risk vs UF Rate",
                "mode": "lines+markers",
                "line": {"color": "#dc3545"},
                "marker": {"size": 6},
            },
            {
                # Vertical reference line at the Castro & Wu NDT 2024 mortality threshold
                "x":    [mortality_thresh, mortality_thresh],
                "y":    [0, 100],
                "name": f"Mortality threshold {mortality_thresh} mL/kg/h (Castro & Wu NDT 2024)",
                "mode": "lines",
                "line": {"color": "#6f42c1", "dash": "dash", "width": 2},
                "hovertemplate": f"UF ≤{mortality_thresh} mL/kg/h associated with lower mortality risk<extra></extra>",
            },
        ]

    # ── Phosphate comparison ──────────────────────────────────────────────────
    phosphate_bar_data = {}
    if phosphate.get("available"):
        base_p = phosphate.get("baseline_p") or 0
        scen_p = phosphate.get("scenario_p") or 0
        def _p_color(v):
            if v > 5.5: return "#dc3545"
            if v < 3.5: return "#f59e0b"
            return "#198754"
        phosphate_bar_data = {
            "categories":       ["Baseline pre-P", "Scenario pre-P", "Upper target (5.5)", "Lower target (3.5)"],
            "values":           [base_p, scen_p, 5.5, 3.5],
            "colors":           [_p_color(base_p), _p_color(scen_p), "#dc3545", "#f59e0b"],
            "baseline_p":       base_p,
            "scenario_p":       scen_p,
            "delta_p":          phosphate.get("delta_p"),
            "baseline_status":  phosphate.get("baseline_status"),
            "scenario_status":  phosphate.get("scenario_status"),
            "measured_p":       phosphate.get("p_measured"),
            "mcmc_posterior":   phosphate.get("mcmc_posterior"),
        }

    return {
        "hb_traces":         hb_traces,
        "ktv_bar_data":      ktv_bar_data,
        "std_ktv_bar_data":  std_ktv_bar_data,
        "idh_gauge":         idh_gauge,
        "uf_curve_traces":   uf_curve_traces,
        "phosphate_bar_data":phosphate_bar_data,
        "cascade":           cascade,
        "mortality_threshold_ml_kg_h": twin_result.get("uf_curve", {}).get("mortality_threshold_ml_kg_h", 4.0),
        "fluid_volume":      fluid_volume,
    }
