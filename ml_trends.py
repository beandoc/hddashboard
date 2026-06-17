"""
ml_trends.py
============
Clinical Trend Analysis Engine — Kalman Filter and OLS-based predictions
for Hb, Albumin, Iron Status, and ML Readiness assessment.
"""
import logging
from datetime import datetime
from typing import List, Dict, Optional

import numpy as np

try:
    import statsmodels.api as sm
    _STATSMODELS_AVAILABLE = True
except ImportError:
    _STATSMODELS_AVAILABLE = False

try:
    from scipy.stats import t as t_dist, norm as _norm
    _SCIPY_AVAILABLE = True
except ImportError:
    _SCIPY_AVAILABLE = False

logger = logging.getLogger(__name__)


def _month_to_ordinal(month_str: str) -> int:
    """Convert YYYY-MM to integer (months since epoch) for regression x-axis."""
    try:
        dt = datetime.strptime(month_str, "%Y-%m")
        return dt.year * 12 + dt.month
    except (ValueError, TypeError):
        raise ValueError(f"Invalid month format: {month_str!r}")


def compute_ml_readiness(df: List[Dict], param: str) -> dict:
    """
    Assess whether there is enough data to make a robust prediction for param.
    confidence: 'high' (8+), 'moderate' (5–7), 'low' (2–4), 'insufficient' (<2)
    """
    if not df:
        return {
            "ready": False, "n_points": 0, "completeness": 0,
            "confidence": "insufficient",
            "recommendation": "No historical data. Start entering monthly records.",
        }

    values = [r[param] for r in df if r.get(param) is not None]
    n = len(values)
    completeness = round((n / len(df)) * 100)

    if n < 2:
        return {
            "ready": False, "n_points": n, "completeness": completeness,
            "confidence": "insufficient",
            "recommendation": f"Only {n} {param} value(s). Need at least 2 to detect trends.",
        }
    if n <= 4:
        return {
            "ready": True, "n_points": n, "completeness": completeness,
            "confidence": "low",
            "recommendation": f"{n} data points recorded. Add more months for better confidence.",
        }
    if n <= 7:
        return {
            "ready": True, "n_points": n, "completeness": completeness,
            "confidence": "moderate",
            "recommendation": f"{n} months of {param} data. Predictions moderately reliable — collect {8 - n} more for high confidence.",
        }
    return {
        "ready": True, "n_points": n, "completeness": completeness,
        "confidence": "high",
        "recommendation": f"{n} months of {param} data. Predictions are robust.",
    }


def _linear_trend_with_ci(x: list, y: list, confidence_level: float = 0.95) -> dict:
    """
    Fit OLS linear regression and return:
      - next_predicted  : point estimate for the next time step
      - pi_lower/upper  : 95% Prediction Interval
      - slope           : trend direction per month
      - r_squared       : OLS R²
      - adj_r_squared   : Adjusted R²
      - p_value         : F-test p-value
      - durbin_watson   : Autocorrelation statistic
    """
    pairs = [(float(xi), float(yi)) for xi, yi in zip(x, y) if yi is not None]
    n = len(pairs)

    _null = {
        "slope": None, "next_predicted": None,
        "pi_lower": None, "pi_upper": None, "n_points": n,
        "r_squared": None, "adj_r_squared": None,
        "p_value": None, "durbin_watson": None,
    }
    if n < 2:
        return _null

    pairs.sort()  # Ensure chronological order
    x_min = pairs[0][0]
    xs = [p[0] - x_min for p in pairs]  # zero-indexed for numerical stability
    ys = [p[1] for p in pairs]

    # ── statsmodels path (full diagnostics) ───────────────────────────────────
    if _STATSMODELS_AVAILABLE and n >= 3:
        try:
            # BUG 1 FIX: import durbin_watson inside the statsmodels block
            from statsmodels.stats.stattools import durbin_watson

            X = sm.add_constant(np.array(xs, dtype=float))
            Y = np.array(ys, dtype=float)
            model = sm.OLS(Y, X).fit()

            slope     = float(model.params[1])
            intercept = float(model.params[0])
            next_x    = max(xs) + 1
            predicted = slope * next_x + intercept

            # 95% Prediction Interval at next_x
            x_pred = np.array([[1.0, next_x]])
            pred_result = model.get_prediction(x_pred)
            pi = pred_result.summary_frame(alpha=1 - confidence_level)
            pi_lower = float(pi["obs_ci_lower"].iloc[0])
            pi_upper = float(pi["obs_ci_upper"].iloc[0])

            # DW statistic on residuals
            dw = float(durbin_watson(model.resid))

            return {
                "slope":         round(slope, 4),
                "next_predicted": round(predicted, 2),
                "pi_lower":      round(pi_lower, 2),
                "pi_upper":      round(pi_upper, 2),
                "n_points":      n,
                "r_squared":     round(float(model.rsquared), 4),
                "adj_r_squared": round(float(model.rsquared_adj), 4),
                "p_value":       round(float(model.f_pvalue), 4),
                "durbin_watson": round(dw, 3),
            }
        except Exception as e:
            logger.warning("statsmodels OLS failed, falling back to manual OLS: %s", e)

    # ── Manual OLS fallback ───────────────────────────────────────────────────
    x_mean = sum(xs) / n
    y_mean = sum(ys) / n
    sxy = sum((xs[i] - x_mean) * (ys[i] - y_mean) for i in range(n))
    sxx = sum((xs[i] - x_mean) ** 2 for i in range(n))

    if sxx == 0:
        return {**_null, "slope": 0.0, "next_predicted": round(y_mean, 2)}

    slope     = sxy / sxx
    intercept = y_mean - slope * x_mean
    next_x    = max(xs) + 1
    predicted = slope * next_x + intercept

    if not _SCIPY_AVAILABLE or n <= 2:
        return {**_null, "slope": round(slope, 4), "next_predicted": round(predicted, 2)}

    y_hat = [slope * xs[i] + intercept for i in range(n)]
    rss   = sum((ys[i] - y_hat[i]) ** 2 for i in range(n))
    rse   = (rss / (n - 2)) ** 0.5
    t_crit = t_dist.ppf((1 + confidence_level) / 2, df=n - 2)
    margin = t_crit * rse * (1 + 1 / n + (next_x - x_mean) ** 2 / sxx) ** 0.5

    # Manual R² for the fallback path
    ss_tot = sum((yi - y_mean) ** 2 for yi in ys)
    r2 = round(1 - rss / ss_tot, 4) if ss_tot > 0 else None

    return {
        "slope":          round(slope, 4),
        "next_predicted": round(predicted, 2),
        "pi_lower":       round(predicted - margin, 2),
        "pi_upper":       round(predicted + margin, 2),
        "n_points":       n,
        "r_squared":      r2,
        "adj_r_squared":  None,  # not computed in fallback
        "p_value":        None,
        "durbin_watson":  None,
    }


def _kalman_trend(
    xs: list,
    ys: list,
    prior_level: float,
    prior_slope: float   = 0.0,
    P_level: float       = 4.0,
    P_slope: float       = 0.25,
    q_level: float       = 0.04,
    q_slope: float       = 0.001,
    r_obs: float         = 0.25,
    confidence_level: float = 0.95,
) -> dict:
    """
    Constant-velocity Kalman filter returning a next-step prediction with
    a 95% predictive interval.
    """
    # BUG 2 FIX: removed the `if not _STATSMODELS_AVAILABLE: return {}` guard
    # Kalman uses only numpy, which is always available.

    pairs = sorted(
        [(float(xi), float(yi)) for xi, yi in zip(xs, ys) if yi is not None]
    )
    n = len(pairs)
    if n < 1:
        return {}

    ts  = [p[0] for p in pairs]
    obs = [p[1] for p in pairs]

    # State and covariance
    x = np.array([prior_level, prior_slope], dtype=float)
    P = np.diag([P_level, P_slope])
    H = np.array([[1.0, 0.0]])
    Q_unit = np.diag([q_level, q_slope])   # per-month process noise

    for i, (t, y) in enumerate(zip(ts, obs)):
        dt = float(t - ts[i - 1]) if i > 0 else 1.0
        dt = max(dt, 1.0)

        F = np.array([[1.0, dt], [0.0, 1.0]])
        Q = Q_unit * dt

        # Predict
        x_p = F @ x
        P_p = F @ P @ F.T + Q

        # Update (innovation)
        S   = max(float(np.squeeze(H @ P_p @ H.T)) + r_obs, 1e-6)
        K   = (P_p @ H.T) / S
        x   = x_p + K.flatten() * (y - float(np.squeeze(H @ x_p)))
        P   = (np.eye(2) - np.outer(K.flatten(), H)) @ P_p

    # One-step-ahead prediction
    F1      = np.array([[1.0, 1.0], [0.0, 1.0]])
    x_next  = F1 @ x
    P_next  = F1 @ P @ F1.T + Q_unit

    # Predictive std = state uncertainty + measurement noise
    pred_var = float(P_next[0, 0]) + r_obs
    pred_std = pred_var ** 0.5

    z = _norm.ppf((1.0 + confidence_level) / 2.0) if _SCIPY_AVAILABLE else 1.96

    return {
        "method":          "Kalman",
        "slope":           round(float(x[1]), 4),
        "filtered_level":  round(float(x[0]), 2),
        "next_predicted":  round(float(x_next[0]), 2),
        "pi_lower":        round(float(x_next[0]) - z * pred_std, 2),
        "pi_upper":        round(float(x_next[0]) + z * pred_std, 2),
        "posterior_std":   round(pred_std, 3),
        "n_points":        n,
    }


def _hb_endo(hb: float, transfusion_units: int) -> float:
    """
    Estimate endogenous Hb by subtracting expected transfusion contribution.
    Assumption: 1 PRBC unit raises Hb by ~1 g/dL.
    Floored at 5.0 g/dL to avoid physiologically impossible values.
    """
    return max(hb - float(transfusion_units), 5.0)


def _hb_kalman(xs: list, ys: list) -> dict:
    """Kalman filter with Hb-specific KDOQI priors."""
    return _kalman_trend(
        xs, ys,
        prior_level = 11.0,   # KDOQI Hb target centre (g/dL)
        prior_slope = 0.0,
        P_level     = 4.0,    # ±2 g/dL initial level uncertainty (2σ)
        P_slope     = 0.25,   # ±0.5 g/dL/month initial slope uncertainty
        q_level     = 0.04,   # ~0.2 g/dL random walk per month
        q_slope     = 0.001,  # slope evolves slowly
        r_obs       = 0.25,   # ±0.5 g/dL lab measurement noise (1σ)
    )


def _albumin_kalman(xs: list, ys: list) -> dict:
    """Kalman filter with Albumin-specific clinical priors."""
    return _kalman_trend(
        xs, ys,
        prior_level = 3.8,    # centre of normal HD albumin range (g/dL)
        prior_slope = 0.0,
        P_level     = 0.36,   # ±0.6 g/dL initial level uncertainty
        P_slope     = 0.04,   # ±0.2 g/dL/month initial slope uncertainty
        q_level     = 0.01,   # albumin changes slowly (~0.1 g/dL/month)
        q_slope     = 0.0005,
        r_obs       = 0.04,   # ±0.2 g/dL lab measurement noise (1σ)
    )


def _hb_trajectory_severity(current: Optional[float]) -> str:
    """Classify Hb severity based on current level."""
    if current is None: return "unknown"
    if current > 13.0:  return "critical_high"  # Risk: Stroke, Thrombosis
    if current < 7.0:   return "critical"
    if current < 9.0:   return "high"
    if current < 10.0:  return "watch"
    if 10.0 <= current <= 12.0: return "optimal"
    return "stable"


def _hb_trajectory_message(
    severity: str, current: float, predicted: float,
    prev_hb: float, has_transfusion: bool, transfusion_months: list,
    p_value: Optional[float] = None,
    slope: Optional[float] = None,
    n_points: Optional[int] = None,
) -> str:
    """Generate human-readable clinical message for Hb trajectory."""
    transfusion_note = (
        f" (trajectory based on endogenous Hb — transfusions in {', '.join(transfusion_months)} excluded)"
        if has_transfusion else ""
    )

    predicting_improvement = (predicted is not None and current is not None and predicted > current)
    alert_predicted = predicted is not None and predicted < 10.0

    if severity == "critical_high":
        return f"🚨 HIGH RISK: Hb {current} g/dL exceeds 13.0 g/dL. Risk of thrombosis/stroke. Reduce/hold ESA dosage immediately."

    if severity == "critical":
        if predicting_improvement:
            return (
                f"CRITICAL: Current Hb {current} g/dL — immediate intervention required. "
                f"Model projects partial recovery to {predicted:.1f} g/dL next month, but current level demands urgent action.{transfusion_note}"
                if predicted is not None else
                f"CRITICAL: Current Hb {current} g/dL — immediate intervention required.{transfusion_note}"
            )
        return (
            f"CRITICAL: Current Hb {current} g/dL — immediate intervention required. "
            f"Predicted to remain critically low at {predicted:.1f} g/dL.{transfusion_note}"
            if predicted is not None else
            f"CRITICAL: Current Hb {current} g/dL — immediate intervention required.{transfusion_note}"
        )

    if severity in ("high", "watch") and alert_predicted:
        stat_significant = p_value is not None and p_value < 0.05
        large_decline = slope is not None and slope < -0.15  # >0.15 g/dL/month is clinically meaningful
        sufficient_data = n_points is not None and n_points >= 4

        # Clinically meaningful improvement scales with how far the patient is below target.
        # Rule: ≥15% of the gap to 10 g/dL (min 0.2 g/dL), OR crossing the 10.0 g/dL threshold.
        # e.g. Hb 6→7 (gap 4.0): need ≥0.60; Hb 7→7.5 (gap 3.0): need ≥0.45; Hb 9.7→10.0: crosses target.
        delta = (predicted - current) if (predicted is not None and current is not None) else 0.0
        gap_to_target = max(10.0 - (current or 0.0), 0.0)
        min_delta = max(gap_to_target * 0.15, 0.2)
        crosses_target = (current is not None and current < 10.0 and predicted is not None and predicted >= 10.0)
        meaningful_improvement = crosses_target or delta >= min_delta
        # Any visible upward movement (>0.1 g/dL) even if insufficient to be "meaningful"
        any_rise = delta > 0.1

        if severity == "high":
            # Hb < 9.0 g/dL — the current level itself demands action; trend direction modifies the message only.
            if current < 8.0:
                if meaningful_improvement:
                    return (
                        f"Hb critically low at {current} g/dL — ESA and iron review required. "
                        f"Model projects improvement to {predicted:.1f} g/dL; target is ≥10 g/dL.{transfusion_note}"
                    )
                if stat_significant and large_decline and sufficient_data:
                    return (
                        f"Hb critically low at {current} g/dL with a significant declining trend — predicted {predicted:.1f} g/dL. "
                        f"Escalate urgently.{transfusion_note}"
                    )
                if any_rise:
                    return (
                        f"Hb critically low at {current} g/dL — predicted rise to {predicted:.1f} g/dL is inadequate (target ≥10 g/dL). "
                        f"Active ESA and iron review required.{transfusion_note}"
                    )
                return (
                    f"Hb critically low at {current} g/dL — essentially flat despite ESA therapy. "
                    f"Immediate review of ESA dose, iron stores, and adherence required.{transfusion_note}"
                )
            else:
                # Hb 8.0–9.0
                if meaningful_improvement:
                    return (
                        f"Hb at {current} g/dL — below target. Predicted improvement to {predicted:.1f} g/dL; "
                        f"still below 10 g/dL. Review ESA efficacy and iron.{transfusion_note}"
                    )
                if stat_significant and large_decline and sufficient_data:
                    return (
                        f"Hb at {current} g/dL with a significant declining trend — escalate ESA dose.{transfusion_note}"
                    )
                if any_rise:
                    return (
                        f"Hb at {current} g/dL — predicted rise to {predicted:.1f} g/dL is below the expected response. "
                        f"Review ESA dose and iron stores.{transfusion_note}"
                    )
                return (
                    f"Hb at {current} g/dL — below target with inadequate ESA response. "
                    f"Review ESA dose and iron stores.{transfusion_note}"
                )

        # severity == "watch": Hb 9.0–10.0 — gate urgency on trend statistics.
        if meaningful_improvement:
            return (
                f"Hb at {current} g/dL — below target. Predicted improvement to {predicted:.1f} g/dL"
                f"{'; crosses 10 g/dL target' if crosses_target else '; monitor to confirm'}. "
                f"Continue current regimen.{transfusion_note}"
            )
        if stat_significant and large_decline and sufficient_data:
            return (
                f"Hb at {current} g/dL (below target) with a statistically significant declining trend → {predicted:.1f} g/dL. "
                f"Review and escalate ESA dose.{transfusion_note}"
            )
        # Flat or non-significant trend — do not over-alarm.
        p_note = f"p={p_value:.2f}" if p_value is not None else "trend uncertain"
        n_note = f"n={n_points}" if n_points is not None else "limited data"
        return (
            f"Hb at {current} g/dL — below target. Predicted {predicted:.1f} g/dL next month "
            f"({p_note}, {n_note} — trend not significant). Continue current regimen and reassess.{transfusion_note}"
            if predicted is not None else
            f"Hb at {current} g/dL — below target. Monitor closely and reassess.{transfusion_note}"
        )

    # Below target now, but predicted to cross 10.0 g/dL — good trajectory not captured above
    if severity in ("high", "watch") and predicted is not None and predicted >= 10.0:
        return (
            f"Hb at {current} g/dL — predicted to reach {predicted:.1f} g/dL next month, "
            f"crossing the 10 g/dL target. Continue current regimen.{transfusion_note}"
        )

    if alert_predicted:
        # current >= 10 but predicted to fall below
        return (
            f"Predicted to drop below 10 g/dL (→ {predicted:.1f} g/dL) — review urgently.{transfusion_note}"
            if predicted is not None else
            f"Predicted to drop below 10 g/dL — review urgently.{transfusion_note}"
        )

    if current is not None and prev_hb is not None and current < prev_hb and prev_hb > 13.0 and current >= 10.0:
        return f"✅ Favorable Trend: Controlled downtitration from {prev_hb} to {current} g/dL (Target 10-12 g/dL).{transfusion_note}"

    if severity == "optimal":
        return f"✅ Optimal: Hb {current} g/dL is within the target range (10-12 g/dL).{transfusion_note}"

    return f"Hb trajectory acceptable.{transfusion_note}"


def predict_hb_trajectory(df: List[Dict]) -> Dict:
    # T1-4: Defensive sort descending
    df = sorted(df, key=lambda x: x.get("month", ""), reverse=True)
    readiness = compute_ml_readiness(df, "hb")
    current = next((r["hb"] for r in df if r.get("hb") is not None), None)
    prev_hb = df[1]["hb"] if len(df) > 1 and df[1].get("hb") is not None else None

    # Identify months where a blood transfusion was given
    transfusion_months = [
        r["month"] for r in df
        if r.get("transfusion_units") and r.get("month")
    ]
    has_transfusion = bool(transfusion_months)
    _severity = _hb_trajectory_severity(current)

    base = {
        "current": current,
        "confidence": readiness["confidence"],
        "n_points": readiness["n_points"],
        "completeness": readiness["completeness"],
        "recommendation": readiness["recommendation"],
        "alert": current is not None and current < 10.0,
        "severity": _severity,
        "transfusion_months": transfusion_months,
        "has_transfusion_confounding": has_transfusion,
    }

    if not readiness["ready"]:
        return {
            "available": False,
            "error":     readiness["recommendation"],
            "data": {
                **base,
                "ready_for_prediction": False,
                "predicted": None, "next_predicted": None,
                "pi_lower": None, "pi_upper": None,
                "r_squared": None, "adj_r_squared": None,
                "p_value": None, "durbin_watson": None,
                "alert_predicted_low": False,
                "message": readiness["recommendation"],
            }
        }

    # Use endogenous (transfusion-corrected) Hb for trajectory fitting.
    pairs = [
        (
            _month_to_ordinal(r["month"]),
            _hb_endo(r["hb"], r.get("transfusion_units") or 0),
        )
        for r in df
        if r.get("hb") is not None and r.get("month")
    ]
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]

    kal   = _hb_kalman(xs, ys)
    ols   = _linear_trend_with_ci(xs, ys)

    predicted = kal.get("next_predicted") or ols.get("next_predicted")
    message = _hb_trajectory_message(
        _severity, current, predicted, prev_hb, has_transfusion, transfusion_months,
        p_value=ols.get("p_value"),
        slope=kal.get("slope") or ols.get("slope"),
        n_points=kal.get("n_points") or ols.get("n_points"),
    )

    return {
        "available": True,
        "error":     None,
        "data": {
            **base,
            "ready_for_prediction": True,
            "predicted":       predicted,
            "next_predicted":  predicted,
            "slope":           kal.get("slope") or ols.get("slope"),
            "filtered_level":  kal.get("filtered_level"),
            "pi_lower":        kal.get("pi_lower"),
            "pi_upper":        kal.get("pi_upper"),
            "posterior_std":   kal.get("posterior_std"),
            "method":          kal.get("method", "OLS"),
            "r_squared":       ols.get("r_squared"),
            "adj_r_squared":   ols.get("adj_r_squared"),
            "p_value":         ols.get("p_value"),
            "durbin_watson":   ols.get("durbin_watson"),
            "n_points":        kal.get("n_points") or ols.get("n_points"),
            "alert_predicted_low": bool(predicted is not None and predicted < 10.0),
            "message": message,
        }
    }


def assess_albumin_decline(df: List[Dict]) -> Dict:
    readiness = compute_ml_readiness(df, "albumin")
    current = next((r["albumin"] for r in df if r.get("albumin") is not None), None)

    base = {
        "current": current,
        "risk": current is not None and current < 3.5,
        "confidence": readiness["confidence"],
        "n_points": readiness["n_points"],
        "message": readiness["recommendation"],
    }

    if not readiness["ready"]:
        return {
            "available": False,
            "error":     readiness["recommendation"],
            "data": {
                **base,
                "trend": "→", "direction": "→",
                "predicted": None, "predicted_2m": None,
                "pi_lower": None, "pi_upper": None,
                "r_squared": None, "adj_r_squared": None,
                "p_value": None, "durbin_watson": None,
                "risk_crossing_35": base["risk"],
                "inputs_missing": [f"Albumin ({2 - readiness['n_points']} more required)"]
            }
        }

    pairs = [
        (_month_to_ordinal(r["month"]), r["albumin"])
        for r in df
        if r.get("albumin") is not None and r.get("month")
    ]
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]

    kal   = _albumin_kalman(xs, ys)
    ols   = _linear_trend_with_ci(xs, ys)

    slope     = kal.get("slope") or ols.get("slope") or 0
    predicted = kal.get("next_predicted") or ols.get("next_predicted")
    direction = "↑" if slope > 0.05 else "↓" if slope < -0.05 else "→"
    risk = base["risk"] or (predicted is not None and predicted < 2.5)

    return {
        "available": True,
        "error":     None,
        "data": {
            **base,
            "risk": risk,
            "trend": direction,
            "direction": direction,
            "predicted": predicted,
            "predicted_2m": predicted,
            "filtered_level":  kal.get("filtered_level"),
            "pi_lower":        kal.get("pi_lower"),
            "pi_upper":        kal.get("pi_upper"),
            "posterior_std":   kal.get("posterior_std"),
            "method":          kal.get("method", "OLS"),
            "r_squared":       ols.get("r_squared"),
            "adj_r_squared":   ols.get("adj_r_squared"),
            "p_value":         ols.get("p_value"),
            "durbin_watson":   ols.get("durbin_watson"),
            "n_points":        kal.get("n_points") or ols.get("n_points", readiness["n_points"]),
            "risk_crossing_35": risk,
        }
    }


def classify_iron_status(latest: Dict, staleness: Dict = None) -> Dict:
    """
    Classify iron status per KDIGO 2012 §3.4, conditioned on ESA therapy status.

    KDIGO 2012 key distinctions:
      - ESA-treated : target TSAT ≥ 30%, Ferritin ≥ 500 µg/L
      - ESA-naive   : supplement iron before starting ESA (TSAT < 20% or Ferritin < 100)
      - High Ferritin + Low TSAT → likely inflammation-driven sequestration (not iron overload)
    """
    staleness = staleness or {}
    fer, tsat = latest.get("serum_ferritin"), latest.get("tsat")
    if fer is None or tsat is None:
        missing = []
        if fer is None: missing.append("Ferritin")
        if tsat is None: missing.append("TSAT")
        return {
            "available": False,
            "error":     "Incomplete labs (Ferritin/TSAT).",
            "data": {
                "status": "Unknown",
                "class": "warning",
                "message": "Incomplete labs — enter Ferritin + TSAT",
                "inputs_missing": missing
            }
        }

    # ── ESA therapy status detection ─────────────────────────────────────────
    epo_active = bool(
        latest.get("epo_weekly_units") or
        latest.get("epo_mircera_dose") or
        latest.get("desidustat_dose")
    )

    # ── KDIGO 2012 §3.4 Iron Status Classification ───────────────────────────
    # Pattern 1: Inflammation-driven sequestration (high Ferritin + low TSAT)
    # Ferritin is an acute-phase reactant → elevated Ferritin with low TSAT
    # does NOT mean iron overload; it means iron is trapped in RES
    inflam_sequestration = (fer or 0) > 500 and (tsat or 0) < 20

    if inflam_sequestration:
        status = "Inflammation-driven Iron Sequestration"
        rec = (
            "High Ferritin with low TSAT — iron trapped in RES due to inflammation. "
            "Address CRP/inflammation before IV iron. Check WBC, CRP trend. "
            "Do NOT interpret as iron overload (KDIGO 2012 §3.4.3)."
        )
        css = "warning"

    elif (tsat or 0) < 20:
        # Absolute deficiency — same threshold regardless of ESA status
        status = "Absolute Iron Deficiency"
        if epo_active:
            rec = (
                "Initiate IV Iron loading — TSAT <20% in ESA-treated patient. "
                "Target: TSAT ≥30%, Ferritin ≥500 µg/L (KDIGO 2012 §3.4.2). "
                "Hold ESA dose escalation until iron replete."
            )
        else:
            rec = (
                "Initiate IV Iron before starting ESA — TSAT <20%. "
                "Target: TSAT ≥20%, Ferritin ≥100 µg/L before ESA initiation (KDIGO 2012 §3.4.1)."
            )
        css = "danger"

    elif (tsat or 0) < 30 and (fer or 0) < 500 and epo_active:
        # Functional deficiency — only meaningful in ESA-treated patients
        status = "Functional Iron Deficiency (ESA-treated)"
        rec = (
            "IV Iron recommended — TSAT <30% and Ferritin <500 µg/L in ESA-treated patient. "
            "Functional deficiency: insufficient iron mobilisation for erythropoiesis despite "
            "adequate stores. Target TSAT ≥30% (KDIGO 2012 §3.4.2)."
        )
        css = "danger"

    elif (tsat or 0) < 30 and (fer or 0) < 500 and not epo_active:
        # Iron insufficient in non-ESA patient — different recommendation
        status = "Iron Insufficient (Pre-ESA)"
        rec = (
            "Iron supplementation recommended before ESA initiation. "
            "TSAT <30% and Ferritin <500 µg/L — replenish iron stores first. "
            "Recheck labs in 4-6 weeks (KDIGO 2012 §3.4.1)."
        )
        css = "warning"

    elif (fer or 0) > 800:
        # Possible overload — but rule out inflammation first
        status = "Iron Overload Risk"
        rec = (
            "Hold IV Iron — Ferritin >800 µg/L. "
            "Rule out infection/inflammation (CRP) as cause of ferritin elevation. "
            "Recheck TSAT + Ferritin in 3 months (KDIGO 2012 §3.4.3)."
        )
        css = "warning"

    elif (fer or 0) > 500 and epo_active:
        # Replete in ESA-treated context
        status = "Iron Replete (ESA-treated)"
        rec = (
            "Iron stores adequate — Ferritin >500 µg/L and TSAT ≥30%. "
            "Continue maintenance IV iron dosing. No iron loading required (KDIGO 2012 §3.4.2)."
        )
        css = "success"

    elif (fer or 0) > 200:
        status = "Adequate Iron Stores"
        rec = (
            "Iron stores adequate for current ESA regime. "
            "Continue monitoring TSAT and Ferritin monthly."
        )
        css = "success"

    else:
        # Borderline — Ferritin 100–200
        status = "Borderline Iron Stores"
        rec = (
            "Ferritin 100–200 µg/L — borderline adequate. "
            "Consider oral or low-dose IV iron supplementation. "
            "Recheck in 4–6 weeks."
        )
        css = "warning"

    # ── Staleness warning ────────────────────────────────────────────────────
    stale_months = max(staleness.get("serum_ferritin", 0), staleness.get("tsat", 0))
    stale_warning = f" (⚠ Data is {stale_months} months old — recheck recommended)" if stale_months > 3 else ""

    # ── ESA context note ─────────────────────────────────────────────────────
    esa_context = (
        "ESA therapy active — applying KDIGO 2012 §3.4.2 targets (TSAT ≥30%, Ferritin ≥500)."
        if epo_active else
        "No active ESA detected — applying KDIGO 2012 §3.4.1 pre-ESA targets (TSAT ≥20%, Ferritin ≥100)."
    )

    return {
        "available": True,
        "error":     None,
        "data": {
            "status":           status,
            "recommendation":   rec,
            "message":          rec + stale_warning,
            "esa_context":      esa_context,
            "esa_active":       epo_active,
            "inflam_pattern":   inflam_sequestration,
            "class":            css,
            "ferritin":         fer,
            "tsat":             tsat,
            "inputs_missing":   []
        }
    }


def _phosphorus_kalman(xs: list, ys: list) -> dict:
    """Kalman filter with phosphorus-specific clinical priors."""
    return _kalman_trend(
        xs, ys,
        prior_level = 4.5,    # target range 3.5–5.5 mg/dL
        prior_slope = 0.0,
        P_level     = 2.25,   # variance corresponding to ±1.5 mg/dL initial uncertainty
        P_slope     = 0.25,   # initial slope uncertainty
        q_level     = 0.05,   # phosphorus changes moderately quickly due to diet/compliance
        q_slope     = 0.005,
        r_obs       = 0.16,   # ±0.4 mg/dL lab measurement noise (1σ)
    )


def _phosphorus_trajectory_severity(current: Optional[float]) -> str:
    """Classify phosphorus severity based on current level."""
    if current is None: return "unknown"
    if current > 7.0:   return "critical_high" # Risk of calciphylaxis, vascular calcification
    if current > 5.5:   return "high"          # Above KDOQI target
    if current < 3.0:   return "critical"      # Malnutrition or over-suppressed
    if current < 3.5:   return "watch"         # Borderline low
    if 3.5 <= current <= 5.5: return "optimal"
    return "stable"


def _phosphorus_trajectory_message(
    severity: str, current: float, predicted: float
) -> str:
    """Generate human-readable clinical message for Phosphorus trajectory."""
    predicting_improvement = (predicted is not None and current is not None and predicted < current)
    predicting_increase = (predicted is not None and current is not None and predicted > current)

    if severity == "critical_high":
        return f"🚨 CRITICAL HIGH: Phosphorus {current:.1f} mg/dL is severely elevated (target 3.5-5.5). High risk of calciphylaxis/cardiovascular calcification. Limit dietary phosphate and verify binder adherence/dosage immediately."

    if severity == "high":
        if predicting_improvement:
            return f"Phosphorus is elevated at {current:.1f} mg/dL, but predicted to decline to {predicted:.1f} mg/dL next month. Continue current binder regimen and monitor diet."
        return f"Phosphorus is elevated at {current:.1f} mg/dL and projected to remain high at {predicted:.1f} mg/dL. Review phosphate binder dosage and reinforce dietary restriction."

    if severity == "critical":
        return f"🚨 CRITICAL LOW: Phosphorus is low at {current:.1f} mg/dL (target 3.5-5.5). Risk of malnutrition or over-suppression of PTH. Consider decreasing phosphate binder dose."

    if severity == "watch":
        if predicting_increase:
            return f"Phosphorus is borderline low at {current:.1f} mg/dL, but projected to rise to {predicted:.1f} mg/dL. Monitor closely without altering therapy."
        return f"Phosphorus is borderline low at {current:.1f} mg/dL and predicted to stay low. Review nutritional intake and consider tapering phosphate binders."

    if severity == "optimal":
        if predicted is not None and predicted > 5.5:
            return f"✅ Optimal: Current Phosphorus is {current:.1f} mg/dL, but projected to rise above target to {predicted:.1f} mg/dL next month. Monitor dietary intake."
        if predicted is not None and predicted < 3.5:
            return f"✅ Optimal: Current Phosphorus is {current:.1f} mg/dL, but projected to drop to {predicted:.1f} mg/dL next month. Review binder therapy."
        return f"✅ Optimal: Phosphorus is {current:.1f} mg/dL, within target range (3.5-5.5 mg/dL)."

    return "Phosphorus trajectory stable."


def predict_phosphorus_trajectory(df: List[Dict]) -> Dict:
    # Sort descending
    df = sorted(df, key=lambda x: x.get("month", ""), reverse=True)
    readiness = compute_ml_readiness(df, "phosphorus")
    current = next((r["phosphorus"] for r in df if r.get("phosphorus") is not None), None)

    _severity = _phosphorus_trajectory_severity(current)

    base = {
        "current": current,
        "confidence": readiness["confidence"],
        "n_points": readiness["n_points"],
        "completeness": readiness["completeness"],
        "recommendation": readiness["recommendation"],
        "alert": current is not None and (current > 5.5 or current < 3.0),
        "severity": _severity,
    }

    if not readiness["ready"]:
        return {
            "available": False,
            "error":     readiness["recommendation"],
            "data": {
                **base,
                "ready_for_prediction": False,
                "predicted": None, "next_predicted": None,
                "pi_lower": None, "pi_upper": None,
                "r_squared": None, "adj_r_squared": None,
                "p_value": None, "durbin_watson": None,
                "alert_predicted_high": False,
                "alert_predicted_low": False,
                "message": readiness["recommendation"],
                "inputs_missing": [f"Phosphorus ({2 - readiness['n_points']} more required)"]
            }
        }

    pairs = [
        (
            _month_to_ordinal(r["month"]),
            r["phosphorus"],
        )
        for r in df
        if r.get("phosphorus") is not None and r.get("month")
    ]
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]

    kal   = _phosphorus_kalman(xs, ys)
    ols   = _linear_trend_with_ci(xs, ys)

    predicted = kal.get("next_predicted") or ols.get("next_predicted")
    message = _phosphorus_trajectory_message(_severity, current, predicted)

    return {
        "available": True,
        "error":     None,
        "data": {
            **base,
            "ready_for_prediction": True,
            "predicted":       predicted,
            "next_predicted":  predicted,
            "slope":           kal.get("slope") or ols.get("slope"),
            "filtered_level":  kal.get("filtered_level"),
            "pi_lower":        kal.get("pi_lower"),
            "pi_upper":        kal.get("pi_upper"),
            "posterior_std":   kal.get("posterior_std"),
            "method":          kal.get("method", "OLS"),
            "r_squared":       ols.get("r_squared"),
            "adj_r_squared":   ols.get("adj_r_squared"),
            "p_value":         ols.get("p_value"),
            "durbin_watson":   ols.get("durbin_watson"),
            "n_points":        kal.get("n_points") or ols.get("n_points"),
            "alert_predicted_high": bool(predicted is not None and predicted > 5.5),
            "alert_predicted_low": bool(predicted is not None and predicted < 3.0),
            "message": message,
            "inputs_missing": []
        }
    }
