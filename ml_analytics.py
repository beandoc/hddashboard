"""
ml_analytics.py
===============
Predictive analytics for hemodialysis patients.
Includes ML readiness gates, confidence intervals, and EPO dose normalization.
"""
import re
import statistics
import logging
from datetime import datetime
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc
from database import Patient, MonthlyRecord

try:
    from scipy.stats import t as t_dist
    _SCIPY_AVAILABLE = True
except ImportError:
    _SCIPY_AVAILABLE = False

logger = logging.getLogger(__name__)


# ── EPO Dose Normalization ────────────────────────────────────────────────────

def normalize_epo_dose(dose_str: str) -> dict:
    """Convert any EPO dose string to weekly IU equivalents."""
    if not dose_str:
        return {"weekly_iu": None, "original": None, "drug_type": None, "confidence": None}

    s = dose_str.lower()
    numbers = re.findall(r"\d+(?:\.\d+)?", s)
    if not numbers:
        return {"weekly_iu": None, "original": dose_str, "drug_type": "unknown", "confidence": "low"}

    dose_value = float(numbers[0])
    drug_type = "unknown"
    multiplier = 1.0

    if "mircera" in s or "peginesatide" in s:
        drug_type = "mircera"
        multiplier = 25.0          # 100 mcg/month → ~25 IU/week EPO equiv
    elif "darbepoetin" in s or "aranesp" in s:
        drug_type = "darbepoetin"
        multiplier = 200.0         # 1 mcg = ~200 IU EPO equiv
    elif "epo" in s or "epoetin" in s:
        drug_type = "epoetin"
        if "tiw" in s:
            dose_value *= 3        # 3×/week → weekly total
        elif "biw" in s:
            dose_value *= 2        # 2×/week → weekly total

    return {
        "weekly_iu": round(dose_value * multiplier, 2),
        "original": dose_str,
        "drug_type": drug_type,
        "confidence": "high" if drug_type != "unknown" else "low",
    }


def _parse_epo_dose(dose_str: Optional[str]) -> Optional[float]:
    return normalize_epo_dose(dose_str).get("weekly_iu")


# ── ML Readiness Gate ────────────────────────────────────────────────────────

def compute_ml_readiness(df: List[Dict], param: str) -> dict:
    """
    Assess whether there is enough data to make a robust prediction for param.
    Returns confidence: 'high' (6+), 'moderate' (3-5), 'low' (2), 'insufficient' (<2).
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
    if n == 2:
        return {
            "ready": True, "n_points": n, "completeness": completeness,
            "confidence": "low",
            "recommendation": f"{n} data points recorded. Add more months for better confidence.",
        }
    if n < 6:
        return {
            "ready": True, "n_points": n, "completeness": completeness,
            "confidence": "moderate",
            "recommendation": f"{n} months of {param} data. Predictions moderately reliable — collect 3+ more for high confidence.",
        }
    return {
        "ready": True, "n_points": n, "completeness": completeness,
        "confidence": "high",
        "recommendation": f"{n} months of {param} data. Predictions are robust.",
    }


# ── Linear Regression with 95% Confidence Interval ───────────────────────────

def _linear_trend_with_ci(x: list, y: list, confidence_level: float = 0.95) -> dict:
    """Fit OLS linear regression and return prediction + CI for next time point."""
    pairs = [(float(xi), float(yi)) for xi, yi in zip(x, y) if yi is not None]
    n = len(pairs)
    if n < 2:
        return {"slope": None, "next_predicted": None, "ci_lower": None, "ci_upper": None, "n_points": n}

    x_min = pairs[0][0]
    xs = [p[0] - x_min for p in pairs]
    ys = [p[1] for p in pairs]

    x_mean = sum(xs) / n
    y_mean = sum(ys) / n
    sxy = sum((xs[i] - x_mean) * (ys[i] - y_mean) for i in range(n))
    sxx = sum((xs[i] - x_mean) ** 2 for i in range(n))

    if sxx == 0:
        return {"slope": 0.0, "next_predicted": round(y_mean, 2),
                "ci_lower": None, "ci_upper": None, "n_points": n}

    slope = sxy / sxx
    intercept = y_mean - slope * x_mean
    next_x = max(xs) + 1
    predicted = slope * next_x + intercept

    if n <= 2 or not _SCIPY_AVAILABLE:
        return {"slope": round(slope, 4), "next_predicted": round(predicted, 2),
                "ci_lower": None, "ci_upper": None, "n_points": n}

    y_hat = [slope * xs[i] + intercept for i in range(n)]
    rss = sum((ys[i] - y_hat[i]) ** 2 for i in range(n))
    rse = (rss / (n - 2)) ** 0.5
    t_crit = t_dist.ppf((1 + confidence_level) / 2, df=n - 2)
    margin = t_crit * rse * (1 + 1 / n + (next_x - x_mean) ** 2 / sxx) ** 0.5

    return {
        "slope": round(slope, 4),
        "next_predicted": round(predicted, 2),
        "ci_lower": round(predicted - margin, 2),
        "ci_upper": round(predicted + margin, 2),
        "n_points": n,
    }


# ── Hb Trajectory ────────────────────────────────────────────────────────────

def predict_hb_trajectory(df: List[Dict]) -> Dict:
    readiness = compute_ml_readiness(df, "hb")
    current = next((r["hb"] for r in df if r.get("hb") is not None), None)

    base = {
        "current": current,
        "confidence": readiness["confidence"],
        "n_points": readiness["n_points"],
        "completeness": readiness["completeness"],
        "recommendation": readiness["recommendation"],
        "alert": current is not None and current < 10.0,
    }

    if not readiness["ready"]:
        return {
            **base,
            "ready_for_prediction": False,
            "predicted": None, "next_predicted": None,
            "ci_lower": None, "ci_upper": None,
            "alert_predicted_low": False,
            "message": readiness["recommendation"],
        }

    pairs = [(i, r["hb"]) for i, r in enumerate(reversed(df)) if r.get("hb") is not None]
    trend = _linear_trend_with_ci([p[0] for p in pairs], [p[1] for p in pairs])
    predicted = trend["next_predicted"]
    alert_predicted = predicted is not None and predicted < 10.0

    return {
        **base,
        "ready_for_prediction": True,
        "predicted": predicted,
        "next_predicted": predicted,
        "ci_lower": trend.get("ci_lower"),
        "ci_upper": trend.get("ci_upper"),
        "alert_predicted_low": alert_predicted,
        "message": "Predicted to drop below 10 g/dL — review urgently." if alert_predicted else "Hb trajectory acceptable.",
    }


# ── EPO Hypo-Response ─────────────────────────────────────────────────────────

def detect_epo_hyporesponse(df: List[Dict], hb_meta: Dict) -> Dict:
    if not df:
        return {"hypo_response": False, "status": "No Data", "class": "warning",
                "message": "No records.", "ready": False, "confidence": "insufficient"}

    # Gate: require 3+ months with BOTH Hb and an EPO dose entry
    complete_pairs = [
        r for r in df
        if r.get("hb") is not None
        and (r.get("epo_weekly_units") is not None or r.get("epo_mircera_dose"))
    ]

    if len(complete_pairs) < 3:
        return {
            "hypo_response": False,
            "status": "Insufficient Data",
            "class": "warning",
            "ready": False,
            "confidence": "insufficient",
            "message": (
                f"Need 3+ months with both Hb and EPO dose recorded "
                f"(currently have {len(complete_pairs)})."
            ),
        }

    latest = df[0]
    hb = latest.get("hb") or 0
    dose = latest.get("epo_weekly_units")
    if dose is None and latest.get("epo_mircera_dose"):
        dose = _parse_epo_dose(latest["epo_mircera_dose"]) or 0
    dose = dose or 0

    hypo_response = (0 < hb < 10.0) and (dose > 10000)
    severity = ("severe" if hb < 8.5 else "significant") if hypo_response else "none"
    confidence = "high" if len(complete_pairs) >= 6 else "moderate"

    return {
        "hypo_response": hypo_response,
        "severity": severity,
        "status": severity.capitalize() if hypo_response else "Adequate",
        "class": "danger" if severity == "severe" else "warning" if hypo_response else "success",
        "ready": True,
        "confidence": confidence,
        "n_points": len(complete_pairs),
        "message": "Review iron stores and resistance." if hypo_response else "Responsive to EPO therapy.",
    }


# ── Albumin Decline ───────────────────────────────────────────────────────────

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
        return {**base, "trend": "→", "direction": "→", "predicted": None,
                "predicted_2m": None, "ci_lower": None, "ci_upper": None,
                "risk_crossing_35": base["risk"]}

    pairs = [(i, r["albumin"]) for i, r in enumerate(reversed(df)) if r.get("albumin") is not None]
    trend = _linear_trend_with_ci([p[0] for p in pairs], [p[1] for p in pairs])
    slope = trend.get("slope") or 0
    predicted = trend["next_predicted"]
    direction = "up" if slope > 0.05 else "down" if slope < -0.05 else "→"
    risk = base["risk"] or (predicted is not None and predicted < 3.5)

    return {
        **base,
        "risk": risk,
        "trend": direction,
        "direction": direction,
        "predicted": predicted,
        "predicted_2m": predicted,
        "ci_lower": trend.get("ci_lower"),
        "ci_upper": trend.get("ci_upper"),
        "risk_crossing_35": risk,
    }


# ── Iron Status ───────────────────────────────────────────────────────────────

def classify_iron_status(latest: Dict) -> Dict:
    fer, tsat = latest.get("serum_ferritin"), latest.get("tsat")
    if fer is None or tsat is None:
        return {"status": "Unknown", "class": "warning", "message": "Incomplete labs — enter Ferritin + TSAT"}

    if (tsat or 0) < 20:
        status, rec = "Absolute Deficiency", "Initiate IV Iron Loading"
    elif (fer or 0) < 200:
        status, rec = "Iron Deficient", "Consider IV Iron"
    elif (fer or 0) > 800:
        status, rec = "Iron Overload", "Hold Iron"
    else:
        status, rec = "Adequate", "Maintenance dose"

    return {
        "status": status, "recommendation": rec, "message": rec,
        "class": "danger" if "Deficiency" in status
                 else "warning" if ("Overload" in status or "Deficient" in status)
                 else "success",
    }


# ── Target Achievement Score ──────────────────────────────────────────────────

def compute_target_score(df: List[Dict]) -> Dict:
    if not df:
        return {"score": 0, "status": "No Data"}
    latest = df[0]
    points = 0
    if (latest.get("hb") or 0) >= 10:          points += 2
    if (latest.get("albumin") or 0) >= 3.5:    points += 2
    if (latest.get("phosphorus") or 10) <= 5.5: points += 2
    if (latest.get("idwg") or 10) <= 2.5:      points += 2
    if (latest.get("urr") or 0) >= 65:         points += 2
    label = "Optimal" if points >= 8 else "Sub-optimal" if points >= 6 else "Critical"
    return {"score": points, "label": label, "status": label}


# ── Deterioration Risk ────────────────────────────────────────────────────────

def compute_deterioration_risk(hb: Dict, alb: Dict, target: Dict) -> Dict:
    risk_score = 0
    factors = []
    if hb.get("alert"):              risk_score += 40; factors.append("Falling Hb")
    if alb.get("risk"):              risk_score += 30; factors.append("Declining Albumin")
    if target.get("score", 0) < 6:  risk_score += 30; factors.append("Low Target Score")
    risk_level = "High" if risk_score >= 60 else "Moderate" if risk_score >= 30 else "Low"
    return {
        "available": True,
        "risk_score": risk_score, "score": risk_score,
        "risk_level": risk_level, "level": risk_level,
        "risk_factors": factors, "factors": factors,
    }


# ── Main Entry Points ─────────────────────────────────────────────────────────

def run_patient_analytics(db: Session, patient_id: int) -> Dict:
    records = (
        db.query(MonthlyRecord)
        .filter(MonthlyRecord.patient_id == patient_id)
        .order_by(desc(MonthlyRecord.record_month))
        .limit(12)
        .all()
    )
    df = [
        {
            "month": r.record_month,
            "hb": r.hb,
            "albumin": r.albumin,
            "phosphorus": r.phosphorus,
            "idwg": r.idwg,
            "urr": r.urr,
            "serum_ferritin": r.serum_ferritin,
            "tsat": r.tsat,
            "epo_weekly_units": r.epo_weekly_units,
            "epo_mircera_dose": r.epo_mircera_dose,
        }
        for r in records
    ]

    if not df:
        return {"status": "no_data"}

    hb_traj    = predict_hb_trajectory(df)
    epo_resp   = detect_epo_hyporesponse(df, hb_traj)
    alb_risk   = assess_albumin_decline(df)
    iron_stat  = classify_iron_status(df[0])
    target_sc  = compute_target_score(df)
    det_risk   = compute_deterioration_risk(hb_traj, alb_risk, target_sc)

    return {
        "status": "ok",
        "hb_trajectory": hb_traj,
        "epo_response": epo_resp,
        "albumin_risk": alb_risk,
        "iron_status": iron_stat,
        "target_score": target_sc,
        "deterioration_risk": det_risk,
        "history_count": len(df),
        "n_months": len(df),
    }


def run_cohort_analytics(db: Session) -> Dict:
    records = db.query(MonthlyRecord).order_by(MonthlyRecord.record_month).all()
    if not records:
        return {"available": False}

    trends: Dict = {}
    for r in records:
        m = r.record_month
        if m not in trends:
            trends[m] = {"hb": [], "alb": [], "phos": []}
        if r.hb:        trends[m]["hb"].append(r.hb)
        if r.albumin:   trends[m]["alb"].append(r.albumin)
        if r.phosphorus: trends[m]["phos"].append(r.phosphorus)

    months = sorted(trends.keys())
    hb_stats, alb_stats, phos_stats = [], [], []
    for m in months:
        for key, stats_list in [("hb", hb_stats), ("alb", alb_stats), ("phos", phos_stats)]:
            vals = trends[m][key]
            if not vals:
                stats_list.append({"median": 0, "p25": 0, "p75": 0})
                continue
            med = statistics.median(vals)
            sv = sorted(vals)
            n = len(sv)
            stats_list.append({
                "median": round(med, 1),
                "p25": round(sv[int(n * 0.25)], 1),
                "p75": round(sv[int(n * 0.75)], 1),
            })

    return {
        "available": True,
        "months": months,
        "hb": hb_stats,
        "alb": alb_stats,
        "phos": phos_stats,
        "latest_month": months[-1] if months else None,
    }
