"""
bayesian_analytics.py
=====================
Lightweight Bayesian alert-persistence layer for hemodialysis patient monitoring.

Model: Beta-Binomial conjugate update.
  - Prior: Beta(α₀, β₀) — KDOQI/KDIGO-informed population alert rates.
  - Update: each observed month either increments α (alert) or β (on-target).
  - Posterior predictive: P(alert next month) = α_post / (α_post + β_post).
  - Persistence: P(alert for k consecutive months) ≈ prob_next^k.

Intervention posterior adjustment:
  - IV iron given recently → add pseudo-observations to β (shifts posterior
    toward "less likely to remain in alert zone").
  - EPO dose increase → same shift for Hb.
  - Phosphate binder → same shift for Phosphorus.

No external dependencies — pure Python stdlib + math.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple


# ── Beta-Binomial priors (albumin, phosphorus, IDWG only) ────────────────────
# Hb uses a Normal-Normal conjugate instead — see _HB_PRIOR below.
# Beta(α, β): prior mean = α/(α+β).  Strength (α+β = 20) provides ~20 phantom
# population months so 6 real observations shift the posterior meaningfully.
# Alert rates from published HD cohort literature (India/China, 2018-2023):
#   Alb < 3.5:  ~20% months out of range  → Beta(4, 16)   [mean = 0.20]
#   Phos > 5.5: ~40% months out of range  → Beta(8, 12)   [mean = 0.40]
#   IDWG > 2.5: ~30% months out of range  → Beta(6, 14)   [mean = 0.30]

PRIORS: Dict[str, Dict] = {
    "albumin":    {"alpha": 4.0, "beta": 16.0, "threshold": 3.5,  "direction": "low",  "label": "Albumin < 3.5 g/dL"},
    "phosphorus": {"alpha": 8.0, "beta": 12.0, "threshold": 5.5,  "direction": "high", "label": "Phos > 5.5 mg/dL"},
    "idwg":       {"alpha": 6.0, "beta": 14.0, "threshold": 2.5,  "direction": "high", "label": "IDWG > 2.5 kg"},
}

# ── Intervention effect table ─────────────────────────────────────────────────
# pseudo_beta: equivalent on-target pseudo-observations added to the posterior.
# Represents clinical confidence that the intervention will correct the deficit.
# Decays linearly to 0 at max_months after the intervention month.
_INTERVENTION_EFFECTS: Dict[str, Dict] = {
    "iv_iron":          {"affects": "hb",         "pseudo_beta": 2.0, "max_months": 2},
    "epo_increase":     {"affects": "hb",         "pseudo_beta": 1.5, "max_months": 2},
    # Mircera (CERA) has t½ ≈ 130–140 h vs ~24 h for short-acting EPO.
    # Effect persists for up to 3 months after a dose escalation, so max_months=3.
    # pseudo_beta=2.0 reflects the stronger and longer erythropoietic drive.
    # Detection uses weekly-equivalent dose (mcg/week = dose / interval_days * 7)
    # to compare across different dosing intervals (monthly vs every-10-days etc.).
    "mircera_increase": {"affects": "hb",         "pseudo_beta": 2.0, "max_months": 3},
    "phosphate_binder": {"affects": "phosphorus", "pseudo_beta": 1.5, "max_months": 2},
}

# Composite alert score weights — reflect relative mortality contribution per HD cohort literature.
# Hb/albumin dominate because hypoalbuminaemia + anaemia are the two strongest all-cause mortality
# predictors in HD (Kalantar-Zadeh et al. AJKD 2005; Locatelli et al. NDT 2004).
# Phos and IDWG are meaningful but secondary (Block et al. AJKD 1998; Flythe et al. JASN 2011).
# HEURISTIC — weights are not calibrated against an outcomes cohort; treat as clinical prior.
_WEIGHTS = {"hb": 0.35, "albumin": 0.30, "phosphorus": 0.20, "idwg": 0.15}

# Risk tier thresholds — single source of truth used by both compute_bayesian_alert_profile
# and attach_bayesian_signal.  Cutpoints are UNCALIBRATED heuristics pending ROC analysis
# against adverse outcomes (hospitalisation, transfusion, mortality).
_RISK_TIERS = {
    "elevated": {"composite": 0.55, "persistence": 0.55},
    "moderate": {"composite": 0.40, "persistence": 0.35},
}

# ── AR(1) autocorrelation coefficients ───────────────────────────────────────
# HD lab parameters show strong month-to-month autocorrelation.
# Sources: Kalantar-Zadeh et al. CJASN 2011; Turner et al. NDT 2019.
_AUTOCORR: Dict[str, float] = {
    "hb":         0.75,
    "albumin":    0.65,
    "phosphorus": 0.60,
    "idwg":       0.55,
}

# ── Normal-Normal prior for Hb (g/dL) ────────────────────────────────────────
# Hb is modelled as a continuous outcome — the Normal-Normal conjugate gives a
# predictive distribution over actual g/dL values, enabling P(Hb < 9),
# P(Hb 10–12 target), P(Hb > 12), and a point estimate.
#   mu:        10.5 g/dL — centre of KDIGO target range (10–12)
#   tau:        1.5 g/dL — prior SD; yields to patient data after ~3 months
#   sigma_obs:  1.1 g/dL — within-patient monthly SD per DOPPS (1.0–1.4 range);
#               0.8 was too tight and produced over-confident zone probabilities
_HB_PRIOR = {"mu": 10.5, "tau": 1.5, "sigma_obs": 1.1}


def _classify_risk_tier(composite: float, max_persistence: float) -> Tuple[str, str]:
    """Return (tier, css_class) from composite score and max persistence prob."""
    if composite >= _RISK_TIERS["elevated"]["composite"] or max_persistence >= _RISK_TIERS["elevated"]["persistence"]:
        return "elevated", "danger"
    if composite >= _RISK_TIERS["moderate"]["composite"] or max_persistence >= _RISK_TIERS["moderate"]["persistence"]:
        return "moderate", "warning"
    return "low", "success"


def _prob_persistent_k(prob: float, rho_c: float, k: int) -> float:
    """P(k consecutive alert months) under AR(1) Markov model.

    rho_c is the continuous-series AR(1) coefficient from _AUTOCORR.
    It is converted to the binary-indicator correlation ρ_b via the
    bivariate-Normal transformation (_binary_rho) before entering the
    Markov formula.  Using ρ_c directly overstates persistence because
    the indicator correlation is always smaller than the continuous
    correlation for thresholds away from the median.

    Example — p=0.274, ρ_c=0.75:
        ρ_b  ≈ 0.56   (via Φ₂ at z*=−0.60)
        transition = 0.56 + 0.44×0.274 = 0.681
        P(3 consec) = 0.274 × 0.681² ≈ 12.7%   (was 18.4% with ρ_c directly)
    """
    if prob <= 0.0:
        return 0.0
    rho_b      = _binary_rho(rho_c, prob)
    transition = rho_b + (1.0 - rho_b) * prob
    return round(prob * (transition ** (k - 1)), 4)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _normal_cdf(z: float) -> float:
    """Standard Normal CDF via complementary error function."""
    return 0.5 * math.erfc(-z / math.sqrt(2.0))


def _normal_ppf(p: float) -> float:
    """Inverse standard Normal CDF.
    Abramowitz-Stegun 26.2.16 rational approximation — max |error| < 4.5e-4.
    """
    if p <= 0.0: return -8.0
    if p >= 1.0: return  8.0
    if p > 0.5:
        return -_normal_ppf(1.0 - p)
    t = math.sqrt(-2.0 * math.log(p))
    num = 2.515517 + 0.802853 * t + 0.010328 * t * t
    den = 1.0 + 1.432788 * t + 0.189269 * t * t + 0.001308 * t * t * t
    return -(t - num / den)


def _bvn_equal_threshold(h: float, rho: float) -> float:
    """P(X < h, Y < h) for standard bivariate Normal with correlation rho.

    Numerical integration (200-point Simpson's rule):
        ∫_{-6}^{h} Φ((h − ρx) / √(1−ρ²)) · φ(x) dx

    Pure stdlib; ~200 ops — negligible at dashboard latency.
    """
    if abs(rho) < 1e-9:
        return _normal_cdf(h) ** 2
    sqrt1r = math.sqrt(1.0 - rho * rho)
    n_steps = 200  # must be even for Simpson's rule
    lo = -6.0
    step = (h - lo) / n_steps
    inv_sqrt2pi = 1.0 / math.sqrt(2.0 * math.pi)
    s = 0.0
    for i in range(n_steps + 1):
        x = lo + i * step
        phi_x = inv_sqrt2pi * math.exp(-0.5 * x * x)
        cdf_c = _normal_cdf((h - rho * x) / sqrt1r)
        w = 1 if (i == 0 or i == n_steps) else (4 if i % 2 else 2)
        s += w * phi_x * cdf_c
    return s * step / 3.0


def _binary_rho(rho_c: float, p_alert: float) -> float:
    """Convert continuous AR(1) ρ_c to binary-indicator correlation ρ_b.

    For a stationary Gaussian AR(1) process, the lag-1 correlation of the
    binary indicator I(value < threshold) is NOT equal to ρ_c.  The two are
    related by the bivariate-Normal CDF at the threshold z* = Φ⁻¹(p_alert):

        ρ_b = (Φ₂(z*, z*; ρ_c) − p²) / (p · (1−p))

    ρ_b < ρ_c always when p ≠ 0.5.  Using ρ_c directly in the Markov
    persistence formula overstates P(consecutive alerts) by up to 5 pp
    at typical HD alert rates (p ≈ 0.25–0.40).

    For Beta-Binomial parameters the underlying lab values are not exactly
    Gaussian, but the probit approximation z* = Φ⁻¹(p) is adequate.
    """
    if p_alert <= 1e-6 or p_alert >= 1.0 - 1e-6:
        return 0.0
    z_star  = _normal_ppf(p_alert)
    p_joint = _bvn_equal_threshold(z_star, rho_c)
    denom   = p_alert * (1.0 - p_alert)
    if denom < 1e-10:
        return 0.0
    return max(-1.0, min(1.0, (p_joint - p_alert ** 2) / denom))


def _months_between(from_str: str, to_str: str) -> int:
    """Return (to - from) in whole months. Returns 99 on parse error."""
    try:
        from datetime import datetime
        dt1 = datetime.strptime(to_str, "%Y-%m")
        dt2 = datetime.strptime(from_str, "%Y-%m")
        return (dt1.year - dt2.year) * 12 + (dt1.month - dt2.month)
    except Exception:
        return 99


def _is_in_alert(value: Optional[float], threshold: float, direction: str) -> Optional[bool]:
    """True if in alert zone, None if value missing."""
    if value is None:
        return None
    return value < threshold if direction == "low" else value > threshold


def _beta_posterior(
    df: List[Dict],
    param: str,
    prior_alpha: float,
    prior_beta: float,
    threshold: float,
    direction: str,
    rho: float = 0.0,
) -> Tuple[float, float, int, int, float]:
    """
    Conjugate Beta update from observed monthly records.

    Returns (alpha_post, beta_post, n_alert_raw, n_observed_raw, n_eff).

    rho: AR(1) autocorrelation coefficient from _AUTOCORR. Correlated months
    contribute less information than independent draws — the effective sample
    size is n_eff = n × (1-ρ)/(1+ρ). Alert and on-target counts are scaled
    proportionally before being added to the prior, so the posterior reflects
    genuine information content rather than inflated raw counts.
    df is most-recent-first.
    """
    n_alert = n_ok = 0
    for record in df:
        alert = _is_in_alert(record.get(param), threshold, direction)
        if alert is None:
            continue
        if alert:
            n_alert += 1
        else:
            n_ok += 1

    n_total = n_alert + n_ok
    if n_total == 0:
        return (prior_alpha, prior_beta, 0, 0, 0.0)

    # ESS correction: correlated months carry less information than independent ones.
    rho_clamped = max(0.0, min(rho, 0.999))
    n_eff = n_total * (1.0 - rho_clamped) / (1.0 + rho_clamped)

    alert_rate = n_alert / n_total
    n_eff_alert = n_eff * alert_rate
    n_eff_ok    = n_eff * (1.0 - alert_rate)

    return (
        prior_alpha + n_eff_alert,
        prior_beta  + n_eff_ok,
        n_alert,
        n_total,
        round(n_eff, 2),
    )


def _intervention_pseudo_beta(df: List[Dict], param: str) -> Tuple[float, bool]:
    """
    Return (extra_beta, adjusted) from recent intervention records.
    Applies linear decay: full effect when intervention is in the most recent
    record, zero effect at max_months.
    """
    if not df:
        return 0.0, False

    current_month = df[0].get("month", "")
    extra = 0.0

    for effect_key, cfg in _INTERVENTION_EFFECTS.items():
        if cfg["affects"] != param:
            continue

        for idx, record in enumerate(df):
            rec_month = record.get("month", "")
            ago = _months_between(rec_month, current_month)
            if ago < 0 or ago > cfg["max_months"]:
                continue

            detected = False
            if effect_key == "iv_iron" and record.get("iv_iron_dose"):
                detected = True
            elif effect_key == "phosphate_binder" and idx < len(df) - 1:
                # Fire only on binder initiation or type-change, not on maintenance.
                # A patient stable on calcium acetate for 2 years should NOT
                # trigger a pseudo-observation every month.
                cur_binder  = record.get("phosphate_binder_type") or ""
                prev_binder = df[idx + 1].get("phosphate_binder_type") or ""
                if cur_binder and cur_binder != prev_binder:
                    detected = True
            elif effect_key == "epo_increase" and idx < len(df) - 1:
                cur_epo = record.get("epo_weekly_units") or 0
                prev_epo = df[idx + 1].get("epo_weekly_units") or 0
                if prev_epo > 0 and cur_epo > prev_epo * 1.20:
                    detected = True
            elif effect_key == "mircera_increase" and idx < len(df) - 1:
                # Weekly-equivalent dose = mcg / interval_days * 7.
                # Default interval 30 days (monthly) when field is absent.
                def _mircera_weekly(r: Dict) -> float:
                    dose_val = r.get("epo_mircera_dose")
                    if not dose_val:
                        return 0.0
                    if isinstance(dose_val, (int, float)):
                        dose = float(dose_val)
                    else:
                        import re
                        numbers = re.findall(r"\d+(?:\.\d+)?", str(dose_val))
                        if not numbers:
                            return 0.0
                        dose = float(numbers[0])
                    
                    interval_val = r.get("epo_mircera_interval_days")
                    if not interval_val:
                        interval = 30.0
                    else:
                        try:
                            interval = float(interval_val)
                        except (ValueError, TypeError):
                            interval = 30.0
                            
                    return dose / interval * 7.0 if interval > 0 else 0.0
                cur_wk  = _mircera_weekly(record)
                prev_wk = _mircera_weekly(df[idx + 1])
                if prev_wk > 0 and cur_wk > prev_wk * 1.20:
                    detected = True
                elif prev_wk == 0 and cur_wk > 0:
                    # New Mircera initiation (switching from short-acting EPO)
                    detected = True

            if detected:
                decay = 1.0 - (ago / cfg["max_months"]) if cfg["max_months"] > 0 else 1.0
                extra += cfg["pseudo_beta"] * decay

    return round(extra, 3), extra > 0


def _credible_interval_95(alpha: float, beta: float) -> Tuple[float, float]:
    """
    95% CI for Beta(α, β) posterior via Normal approximation.
    Adequate for α+β ≥ 10; our posteriors typically reach 12-22.
    """
    mu = alpha / (alpha + beta)
    n = alpha + beta
    se = math.sqrt(max(mu * (1.0 - mu) / n, 1e-9))
    return (round(max(0.0, mu - 1.96 * se), 3), round(min(1.0, mu + 1.96 * se), 3))


def _hb_normal_bayesian(df: List[Dict]) -> Dict:
    """
    Normal-Normal conjugate model for Hb.

    Predicts next-month Hb (g/dL) and computes three-zone probabilities:
      P(Hb < 9)    — severe anemia / transfusion threshold
      P(10–12)     — KDIGO target zone
      P(Hb > 12)   — over-correction / CV risk zone

    Intervention adjustment: iv_iron or EPO increase adds pseudo-observations
    at the HD target (11.0 g/dL), pulling the posterior toward the target.
    """
    mu0       = _HB_PRIOR["mu"]
    tau0      = _HB_PRIOR["tau"]
    sigma_obs = _HB_PRIOR["sigma_obs"]

    # Exclude Hb readings from months with a transfusion — transfusions
    # produce acute Hb spikes (1–3 g/dL) that mask underlying anemia trajectory.
    # Records signal this via transfusion=True or transfusion_units > 0.
    def _transfusion_flag(r: Dict) -> bool:
        return bool(r.get("transfusion")) or (r.get("transfusion_units") or 0) > 0

    obs_records = [r for r in df if r.get("hb") is not None and not _transfusion_flag(r)]
    obs = [r["hb"] for r in obs_records]
    n   = len(obs)
    n_transfusion_censored = sum(1 for r in df if r.get("hb") is not None and _transfusion_flag(r))

    # Intervention: pseudo-observations placed at HD target Hb = 11.0 g/dL
    extra_beta, adjusted = _intervention_pseudo_beta(df, "hb")
    pseudo_n   = extra_beta
    pseudo_sum = extra_beta * 11.0

    # ESS correction for autocorrelated monthly Hb values.
    # Monthly Hb in HD is ESA-driven and highly autocorrelated (ρ=0.75, Kalantar-Zadeh
    # CJASN 2011). Treating 6 monthly draws as 6 independent observations inflates
    # posterior precision ~7× relative to the honest information content.
    # n_eff_obs = n × (1-ρ)/(1+ρ):  6 obs → ~0.86 independent-equivalent obs.
    # Pseudo-observations from interventions are NOT deflated — they represent
    # discrete clinical events, not serially correlated lab measurements.
    # NOTE: ρ is fixed from literature; per-patient estimation requires ≥20 obs
    # to be reliable (SE ≈ 1/√n). Validate against registry data when available.
    rho_hb    = _AUTOCORR["hb"]
    n_eff_obs = n * (1.0 - rho_hb) / (1.0 + rho_hb) if n > 0 else 0.0
    # Effective sum: scale raw sum proportionally to n_eff_obs
    eff_sum_obs = (sum(obs) / n) * n_eff_obs if n > 0 else 0.0

    # Normal-Normal posterior update
    kappa0      = 1.0 / (tau0 ** 2)
    kappa_l     = 1.0 / (sigma_obs ** 2)
    n_total_eff = n_eff_obs + pseudo_n

    if n_total_eff > 0:
        mu_post     = (kappa0 * mu0 + kappa_l * (eff_sum_obs + pseudo_sum)) / (kappa0 + n_total_eff * kappa_l)
        tau_post_sq = 1.0 / (kappa0 + n_total_eff * kappa_l)
    else:
        mu_post, tau_post_sq = mu0, tau0 ** 2

    # σ_pred = √(τ²_post + σ²_obs) is the MARGINAL predictive variance.
    # It integrates over posterior uncertainty in μ and iid observation noise.
    # This is correct under the exchangeable-observation framing used here.
    # It is NOT the one-step-ahead conditional AR(1) forecast variance
    # σ²(1−ρ²) ≈ 0.53 g/dL², which applies only in the DLM state-space
    # formulation.  Do not "fix" this to the conditional form without also
    # replacing the full conjugate model with a Kalman-filter update.
    sigma_pred = math.sqrt(tau_post_sq + sigma_obs ** 2)

    # Fraction of posterior weight coming from pseudo-observations (interventions).
    # If > 0.5 the posterior is driven more by clinical assumptions than by
    # patient data — flag for sensitivity review when pseudo weights are uncalibrated.
    pseudo_weight_frac = round(pseudo_n / n_total_eff, 3) if n_total_eff > 0 else 0.0

    def _p_below(threshold: float) -> float:
        return _normal_cdf((threshold - mu_post) / sigma_pred)

    p_lt9   = round(_p_below(9.0),  3)
    p_lt10  = round(_p_below(10.0), 3)
    p_lt12  = round(_p_below(12.0), 3)
    p_gt12  = round(1.0 - p_lt12,   3)
    p_10_12 = round(p_lt12 - p_lt10, 3)

    # 80% predictive interval (z = 1.282)
    hb_ci_80 = (
        round(mu_post - 1.282 * sigma_pred, 1),
        round(mu_post + 1.282 * sigma_pred, 1),
    )

    prob_pers3 = _prob_persistent_k(p_lt10, _AUTOCORR["hb"], 3)
    n_lt10     = sum(1 for x in obs if x < 10.0)

    # ── Conditional one-step-ahead prediction ────────────────────────────────
    # The marginal posterior predictive (above) integrates over all historical
    # data and the prior — it answers "where in the stationary distribution
    # will next month's Hb be?"
    #
    # When the most recent Hb is far from the posterior mean (e.g. acute crash
    # to 6.8 when history was ~10.5), the marginal prediction is structurally
    # optimistic because Bayesian shrinkage to the prior dominates.
    #
    # The conditional AR(1) forecast answers the clinically urgent question:
    # "given I know today's Hb is y_latest, where will it be next month?"
    #
    #   E[Hb_{t+1} | Hb_t = y] = ρ·y + (1−ρ)·μ_post
    #   Var[Hb_{t+1} | Hb_t = y] = σ²_obs·(1−ρ²)     ← conditional variance
    #
    # Both sets of probabilities are returned. The UI should prefer the
    # conditional prediction when current_state_divergence > 1.5 (current Hb
    # is more than 1.5 predictive SDs from the posterior mean).
    y_latest = obs[0] if obs else None
    if y_latest is not None:
        mu_cond  = rho_hb * y_latest + (1.0 - rho_hb) * mu_post
        sig_cond = sigma_obs * math.sqrt(1.0 - rho_hb ** 2)

        def _p_below_cond(threshold: float) -> float:
            return _normal_cdf((threshold - mu_cond) / sig_cond)

        p_lt9_c  = round(_p_below_cond(9.0),  3)
        p_lt10_c = round(_p_below_cond(10.0), 3)
        p_lt12_c = round(_p_below_cond(12.0), 3)
        p_gt12_c = round(1.0 - p_lt12_c, 3)
        p_1012_c = round(p_lt12_c - p_lt10_c, 3)
        ci80_cond = (
            round(mu_cond - 1.282 * sig_cond, 1),
            round(mu_cond + 1.282 * sig_cond, 1),
        )
        divergence = round(abs(y_latest - mu_post) / sigma_pred, 2)
    else:
        mu_cond = sig_cond = None
        p_lt9_c = p_lt10_c = p_gt12_c = p_1012_c = None
        ci80_cond = None
        divergence = 0.0

    return {
        # ── Marginal posterior predictive (integrates over history + prior) ──
        "predicted_hb":      round(mu_post, 1),
        "hb_ci_80":          hb_ci_80,
        "prob_hb_lt9":       p_lt9,
        "prob_hb_10_to_12":  p_10_12,
        "prob_hb_gt12":      p_gt12,
        # Backward-compatible keys (derived from Normal predictive distribution)
        "prob_alert_next":   p_lt10,
        "prob_persistent_3": prob_pers3,
        # ── Conditional one-step-ahead (given current Hb = y_latest) ─────────
        "hb_current":                round(y_latest, 1) if y_latest is not None else None,
        "predicted_hb_conditional":  round(mu_cond, 1) if mu_cond is not None else None,
        "hb_ci_80_conditional":      ci80_cond,
        "prob_hb_lt9_conditional":   p_lt9_c,
        "prob_hb_10_to_12_conditional": p_1012_c,
        "prob_hb_gt12_conditional":  p_gt12_c,
        "prob_alert_conditional":    p_lt10_c,
        "current_state_divergence":  divergence,
        "use_conditional":           divergence > 1.5,
        # Metadata
        "n_alert":                  n_lt10,
        "n_observed":               n,
        "n_eff":                    round(n_eff_obs, 2),
        "n_transfusion_censored":   n_transfusion_censored,
        "pseudo_weight_frac":       pseudo_weight_frac,
        "intervention_adjusted":    adjusted,
        "label":             "Hb < 10 g/dL",
        "threshold":         10.0,
        "direction":         "low",
        "posterior_mean":    round(mu_post, 3),
        "posterior_sd":      round(math.sqrt(tau_post_sq), 3),
    }


# ── Public API ────────────────────────────────────────────────────────────────

def compute_bayesian_alert_profile(
    df: List[Dict],
    patient_info: Optional[Dict] = None,
) -> Dict:
    """
    Compute Bayesian posterior alert probabilities for all monitored parameters.

    Hb uses a Normal-Normal conjugate (continuous prediction in g/dL).
    Albumin, Phosphorus, IDWG use Beta-Binomial (binary threshold model).

    Parameters
    ----------
    df : Monthly records, most-recent-first. Each dict must contain at minimum:
         month, hb, albumin, phosphorus, idwg.
         For intervention adjustment also: iv_iron_dose, epo_weekly_units,
         phosphate_binder_type.
    patient_info : Optional patient-level metadata (reserved for future use).

    Returns
    -------
    Dict with one entry per parameter plus a 'summary' key:
      {
        "hb": {
          "predicted_hb": 9.6,            # g/dL point estimate
          "hb_ci_80": (8.5, 10.7),        # 80% predictive interval (g/dL)
          "prob_hb_lt9": 0.24,            # P(Hb < 9)
          "prob_hb_10_to_12": 0.33,       # P(10 ≤ Hb ≤ 12) — in-target
          "prob_hb_gt12": 0.01,           # P(Hb > 12) — over-correction
          "prob_alert_next": 0.66,        # P(Hb < 10) — kept for compatibility
          "prob_persistent_3": 0.28,      # AR(1) persistence
          ...
        },
        "albumin": {
          "prob_alert_next": 0.40,
          "prob_persistent_3": 0.19,
          "ci_95": (0.22, 0.60),
          ...
        },
        "summary": {
          "max_persistence_param": "hb",
          "max_persistence_prob": 0.28,
          "any_high_persistence": False,
          "composite_alert_score": 0.51,
        },
        "available": True
      }
    """
    if not df:
        return {
            "available": False,
            "error":     "No monthly records for Bayesian analysis.",
            "data":      {"available": False}
        }

    result: Dict = {}
    max_pers = 0.0
    max_pers_param: Optional[str] = None
    # Collect weighted alert contributions for independent failure composite.
    # _components[param] = w_i * p_i; composite = 1 - prod(1 - w_i*p_i).
    # This avoids double-counting correlated risks (e.g. MIA syndrome drives
    # both low Hb and low albumin simultaneously) that a plain linear sum inflates.
    _components: Dict[str, float] = {}

    # ── Hb: Normal-Normal conjugate ──────────────────────────────────────────
    hb_result = _hb_normal_bayesian(df)
    result["hb"] = hb_result
    _components["hb"] = _WEIGHTS["hb"] * hb_result["prob_alert_next"]
    if hb_result["prob_persistent_3"] > max_pers:
        max_pers = hb_result["prob_persistent_3"]
        max_pers_param = "hb"

    # ── Albumin / Phosphorus / IDWG: Beta-Binomial ───────────────────────────
    for param, cfg in PRIORS.items():
        rho = _AUTOCORR.get(param, 0.60)
        alpha_post, beta_post, n_alert, n_obs, n_eff = _beta_posterior(
            df, param,
            cfg["alpha"], cfg["beta"],
            cfg["threshold"], cfg["direction"],
            rho=rho,
        )

        extra_beta, adjusted = _intervention_pseudo_beta(df, param)
        beta_post += extra_beta

        prob_next  = alpha_post / (alpha_post + beta_post)
        prob_pers3 = _prob_persistent_k(prob_next, rho, 3)
        ci = _credible_interval_95(alpha_post, beta_post)

        result[param] = {
            "prob_alert_next":    round(prob_next, 3),
            "prob_persistent_3":  prob_pers3,
            "ci_95":              ci,
            "n_alert":            n_alert,
            "n_observed":         n_obs,
            "n_eff":              n_eff,
            "intervention_adjusted": adjusted,
            "posterior_alpha":    round(alpha_post, 2),
            "posterior_beta":     round(beta_post, 2),
            "label":              cfg["label"],
            "threshold":          cfg["threshold"],
            "direction":          cfg["direction"],
        }

        _components[param] = _WEIGHTS.get(param, 0.1) * prob_next
        if prob_pers3 > max_pers:
            max_pers = prob_pers3
            max_pers_param = param

    # Independent failure composite: P(at least one parameter alerts) under
    # independence assumption.  Always ≤ linear sum, so existing tier cutpoints
    # are conservative — recalibrate against outcomes data when available.
    composite = 1.0
    for v in _components.values():
        composite *= (1.0 - v)
    composite = round(1.0 - composite, 3)

    # Fréchet-Hoeffding sanity bounds on the composite:
    #   lower (full positive correlation): max single component — if all four
    #     alert risks are perfectly correlated, composite = dominant component.
    #   upper (Boole / linear sum): Σ w_i·p_i — assumes full independence;
    #     our independent-failure model sits strictly between the two bounds.
    # Large gap between lb and ub signals that correlation structure matters
    # and the composite should be interpreted cautiously.
    frechet_lb  = round(max(_components.values()), 3)
    linear_ub   = round(sum(_components.values()), 3)

    tier, css = _classify_risk_tier(composite, max_pers)

    result["summary"] = {
        "max_persistence_param":   max_pers_param,
        "max_persistence_prob":    round(max_pers, 3),
        "any_high_persistence":    max_pers >= _RISK_TIERS["moderate"]["persistence"],
        "composite_alert_score":   composite,
        "composite_components":    {k: round(v, 4) for k, v in _components.items()},
        "composite_frechet_lb":    frechet_lb,
        "composite_linear_ub":     linear_ub,
        "risk_tier":               tier,
        "risk_tier_css":           css,
        "score_is_heuristic":      True,
    }
    result["available"] = True
    return {
        "available": True,
        "error":     None,
        "data":      result
    }


def attach_bayesian_signal(mort: Dict, bay_profile: Dict) -> Dict:
    """
    Attach a Bayesian persistence signal to an existing predict_mortality_risk()
    output dict as a 'bay_signal' sidecar. Does NOT modify the XGBoost probability.
    """
    # Handle standardized inputs
    mort_data = mort.get("data", mort)
    bay_data  = bay_profile.get("data", bay_profile)

    if not bay_profile.get("available") or not mort:
        return mort

    summary   = bay_data.get("summary", {})
    composite = summary.get("composite_alert_score", 0.0)
    max_prob  = summary.get("max_persistence_prob", 0.0)
    max_param = summary.get("max_persistence_param")

    tier, css = _classify_risk_tier(composite, max_prob)

    hb_bay = bay_data.get("hb", {})
    mort_data["bay_signal"] = {
        "tier": tier,
        "css": css,
        "composite_score": composite,
        "max_persistence_param": max_param,
        "max_persistence_prob": max_prob,
        # Hb — Normal-Normal outputs
        "hb_predicted":          hb_bay.get("predicted_hb"),
        "hb_ci_80":              hb_bay.get("hb_ci_80"),
        "hb_prob_lt9":           hb_bay.get("prob_hb_lt9"),
        "hb_prob_target":        hb_bay.get("prob_hb_10_to_12"),
        "hb_prob_gt12":          hb_bay.get("prob_hb_gt12"),
        "hb_prob_next":          hb_bay.get("prob_alert_next"),
        "hb_prob_persistent_3":  hb_bay.get("prob_persistent_3"),
        "hb_intervention_adjusted": hb_bay.get("intervention_adjusted", False),
        # Albumin / Phosphorus — Beta-Binomial
        "alb_prob_next":         bay_data.get("albumin", {}).get("prob_alert_next"),
        "alb_prob_persistent_3": bay_data.get("albumin", {}).get("prob_persistent_3"),
        "phos_prob_next":        bay_data.get("phosphorus", {}).get("prob_alert_next"),
    }
    
    # If it was standardized, return the wrapper, otherwise return the modified data
    if "data" in mort:
        mort["data"] = mort_data
        return mort
    return mort_data
