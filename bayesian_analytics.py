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


# ── KDOQI/KDIGO-informed priors ───────────────────────────────────────────────
# Beta(α, β): prior mean = α/(α+β).  Strength (α+β = 10) is deliberately weak
# so that 3-4 real observations dominate the prior.
# Alert rates derived from published HD cohort literature (India/China, 2018-2023):
#   Hb < 10:    ~30% months out of range  → Beta(3, 7)
#   Alb < 3.5:  ~20% months out of range  → Beta(2, 8)
#   Phos > 5.5: ~40% months out of range  → Beta(4, 6)
#   IDWG > 2.5: ~30% months out of range  → Beta(3, 7)

PRIORS: Dict[str, Dict] = {
    "hb":         {"alpha": 3.0, "beta": 7.0, "threshold": 10.0, "direction": "low",  "label": "Hb < 10 g/dL"},
    "albumin":    {"alpha": 2.0, "beta": 8.0, "threshold": 3.5,  "direction": "low",  "label": "Albumin < 3.5 g/dL"},
    "phosphorus": {"alpha": 4.0, "beta": 6.0, "threshold": 5.5,  "direction": "high", "label": "Phos > 5.5 mg/dL"},
    "idwg":       {"alpha": 3.0, "beta": 7.0, "threshold": 2.5,  "direction": "high", "label": "IDWG > 2.5 kg"},
}

# ── Intervention effect table ─────────────────────────────────────────────────
# pseudo_beta: equivalent on-target pseudo-observations added to the posterior.
# Represents clinical confidence that the intervention will correct the deficit.
# Decays linearly to 0 at max_months after the intervention month.
_INTERVENTION_EFFECTS: Dict[str, Dict] = {
    "iv_iron":          {"affects": "hb",         "pseudo_beta": 2.0, "max_months": 2},
    "epo_increase":     {"affects": "hb",         "pseudo_beta": 1.5, "max_months": 2},
    "phosphate_binder": {"affects": "phosphorus", "pseudo_beta": 1.5, "max_months": 2},
}

# Composite alert score weights (must sum to 1.0)
_WEIGHTS = {"hb": 0.35, "albumin": 0.30, "phosphorus": 0.20, "idwg": 0.15}


# ── Internal helpers ──────────────────────────────────────────────────────────

def _months_between(from_str: str, to_str: str) -> int:
    """Return (to - from) in whole months. Returns 99 on parse error."""
    try:
        y1, m1 = map(int, to_str.split("-"))
        y2, m2 = map(int, from_str.split("-"))
        return (y1 - y2) * 12 + (m1 - m2)
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
) -> Tuple[float, float, int, int]:
    """
    Conjugate Beta update from observed monthly records.
    Returns (alpha_post, beta_post, n_alert, n_observed).
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
    return (prior_alpha + n_alert, prior_beta + n_ok, n_alert, n_alert + n_ok)


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

        for record in df:
            rec_month = record.get("month", "")
            ago = _months_between(rec_month, current_month)
            if ago < 0 or ago > cfg["max_months"]:
                continue

            detected = False
            if effect_key == "iv_iron" and record.get("iv_iron_dose"):
                detected = True
            elif effect_key == "phosphate_binder" and record.get("phosphate_binder_type"):
                detected = True
            elif effect_key == "epo_increase" and df.index(record) < len(df) - 1:
                cur_epo = record.get("epo_weekly_units") or 0
                prev_epo = df[df.index(record) + 1].get("epo_weekly_units") or 0
                if prev_epo > 0 and cur_epo > prev_epo * 1.20:
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


# ── Public API ────────────────────────────────────────────────────────────────

def compute_bayesian_alert_profile(
    df: List[Dict],
    patient_info: Optional[Dict] = None,
) -> Dict:
    """
    Compute Beta-Binomial posterior alert probabilities for all monitored parameters.

    Parameters
    ----------
    df : Monthly records, most-recent-first. Each dict must contain at minimum:
         month, hb, albumin, phosphorus, idwg.
         For intervention adjustment also: iv_iron_dose, epo_weekly_units,
         phosphate_binder_type.
    patient_info : Optional patient-level metadata (unused currently, reserved
                   for age/sex priors in future versions).

    Returns
    -------
    Dict with one entry per parameter plus a 'summary' key:
      {
        "hb": {
          "prob_alert_next": 0.72,       P(Hb < 10 next month)
          "prob_persistent_3": 0.37,     P(Hb < 10 for 3 consecutive months)
          "ci_95": (0.48, 0.90),
          "n_alert": 3,
          "n_observed": 5,
          "intervention_adjusted": True,
          "posterior_alpha": 6.0,
          "posterior_beta": 5.5,
          "label": "Hb < 10 g/dL",
        },
        ...
        "summary": {
          "max_persistence_param": "hb",
          "max_persistence_prob": 0.37,
          "any_high_persistence": True,
          "composite_alert_score": 0.61,
        },
        "available": True
      }
    """
    if not df:
        return {"available": False}

    result: Dict = {}
    max_pers = 0.0
    max_pers_param: Optional[str] = None
    composite = 0.0

    for param, cfg in PRIORS.items():
        alpha_post, beta_post, n_alert, n_obs = _beta_posterior(
            df, param,
            cfg["alpha"], cfg["beta"],
            cfg["threshold"], cfg["direction"],
        )

        extra_beta, adjusted = _intervention_pseudo_beta(df, param)
        beta_post += extra_beta

        prob_next = alpha_post / (alpha_post + beta_post)
        # P(persistent for k months) = prob_next^k under IID Bernoulli model
        prob_pers3 = round(prob_next ** 3, 4)
        ci = _credible_interval_95(alpha_post, beta_post)

        result[param] = {
            "prob_alert_next": round(prob_next, 3),
            "prob_persistent_3": prob_pers3,
            "ci_95": ci,
            "n_alert": n_alert,
            "n_observed": n_obs,
            "intervention_adjusted": adjusted,
            "posterior_alpha": round(alpha_post, 2),
            "posterior_beta": round(beta_post, 2),
            "label": cfg["label"],
            "threshold": cfg["threshold"],
            "direction": cfg["direction"],
        }

        composite += _WEIGHTS.get(param, 0.1) * prob_next
        if prob_pers3 > max_pers:
            max_pers = prob_pers3
            max_pers_param = param

    result["summary"] = {
        "max_persistence_param": max_pers_param,
        "max_persistence_prob": round(max_pers, 3),
        "any_high_persistence": max_pers >= 0.35,
        "composite_alert_score": round(composite, 3),
    }
    result["available"] = True
    return result


def augment_mortality_risk(mort: Dict, bay_profile: Dict) -> Dict:
    """
    Attach a Bayesian persistence signal to an existing predict_mortality_risk()
    output dict. Does NOT replace the XGBoost probability — adds 'bay_signal'.

    Rationale: persistent Hb < 10 and persistent Albumin < 3.5 are independent
    mortality predictors that cross-sectional XGBoost features may underweight
    when a patient is borderline but deteriorating longitudinally.
    """
    if not bay_profile.get("available") or not mort:
        return mort

    summary = bay_profile.get("summary", {})
    composite = summary.get("composite_alert_score", 0.0)
    max_prob = summary.get("max_persistence_prob", 0.0)
    max_param = summary.get("max_persistence_param")

    if composite >= 0.55 or max_prob >= 0.55:
        tier, css = "elevated", "danger"
    elif composite >= 0.40 or max_prob >= 0.35:
        tier, css = "moderate", "warning"
    else:
        tier, css = "low", "success"

    mort["bay_signal"] = {
        "tier": tier,
        "css": css,
        "composite_score": composite,
        "max_persistence_param": max_param,
        "max_persistence_prob": max_prob,
        "hb_prob_next": bay_profile.get("hb", {}).get("prob_alert_next"),
        "hb_prob_persistent_3": bay_profile.get("hb", {}).get("prob_persistent_3"),
        "alb_prob_next": bay_profile.get("albumin", {}).get("prob_alert_next"),
        "alb_prob_persistent_3": bay_profile.get("albumin", {}).get("prob_persistent_3"),
        "hb_intervention_adjusted": bay_profile.get("hb", {}).get("intervention_adjusted", False),
        "phos_prob_next": bay_profile.get("phosphorus", {}).get("prob_alert_next"),
    }
    return mort
