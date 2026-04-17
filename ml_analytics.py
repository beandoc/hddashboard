"""
ml_analytics.py
===============
Predictive analytics for hemodialysis patients.
"""
import statistics
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc
from database import Patient, MonthlyRecord

logger = logging.getLogger(__name__)

# ─── MODELS ──────────────────────────────────────────────────────────────────

def predict_hb_trajectory(df: List[Dict]) -> Dict:
    """Predicts next month Hb based on last 3-6 months."""
    if len(df) < 2:
        return {"current": df[0]["hb"] if df else None, "predicted": None, "trend": "flat", "alert": False, "message": "Insufficient data"}
    
    hbs = [r["hb"] for r in df if r["hb"] is not None]
    if len(hbs) < 2: 
        return {"current": hbs[0] if hbs else None, "predicted": None, "trend": "flat", "alert": False, "message": "Insufficient data"}
    
    # Simple linear trend
    current = hbs[0]
    prev = hbs[1]
    diff = current - prev
    predicted = round(current + diff, 1)
    
    trend = "improving" if diff > 0.2 else "declining" if diff < -0.2 else "stable"
    alert = predicted < 10.0
    
    return {
        "current": current,
        "predicted": predicted,
        "trend": trend,
        "alert": alert,
        "message": "Predicted to drop below 10 g/dL" if alert else "Hb trajectory acceptable"
    }

def detect_epo_hyporesponse(df: List[Dict], hb_meta: Dict) -> Dict:
    """Identifies poor responders to EPO."""
    if not df or not hb_meta.get("current"):
        return {"hypo_response": False, "status": "Adequate", "class": "ok", "message": "No data"}

    latest = df[0]
    hb = latest["hb"]
    # Simple heuristic: Hb < 10 despite high dose
    # Note: Using epo_weekly_units if available
    dose = latest.get("epo_weekly_units") or 0
    
    hypo_response = hb < 10.0 and dose > 10000
    severity = "severe" if hb < 8.5 else "mild"
    recommendation = "Review iron stores and secondary causes of resistance." if hypo_response else "Responsive to therapy."

    return {
        "hypo_response": hypo_response,
        "severity": severity,
        "status": severity.capitalize() if hypo_response else "Adequate",
        "class": "danger" if severity == "severe" and hypo_response else "warning" if hypo_response else "ok",
        "message": recommendation
    }

def assess_albumin_decline(df: List[Dict]) -> Dict:
    """Detects downward albumin trend."""
    if len(df) < 2: return {"risk": False, "trend": "stable"}
    
    albs = [r["albumin"] for r in df if r["albumin"] is not None]
    if len(albs) < 2: return {"risk": False, "trend": "stable"}
    
    current = albs[0]
    prev = albs[1]
    diff = current - prev
    
    predicted = round(current + diff, 2)
    risk = current < 3.5 or predicted < 3.5
    
    return {
        "current": current,
        "trend": "down" if diff < -0.1 else "up" if diff > 0.1 else "stable",
        "predicted": predicted,
        "alert": risk,
        "risk": risk
    }

def classify_iron_status(latest: Dict) -> Dict:
    """Classifies iron status from Ferritin and TSAT."""
    fer = latest.get("serum_ferritin")
    tsat = latest.get("tsat")
    
    if fer is None or tsat is None:
        return {"status": "Unknown", "class": "secondary", "message": "Incomplete labs"}
    
    if tsat < 20:
        res = {"status": "Absolute Deficiency", "class": "danger", "recommendation": "Initiate IV Iron Loading"}
    elif fer < 200:
        res = {"status": "Iron Deficient", "class": "warning", "recommendation": "Consider IV Iron"}
    elif fer > 800:
        res = {"status": "Iron Overload", "class": "danger", "recommendation": "Hold Iron, review EPO"}
    else:
        res = {"status": "Adequate", "class": "success", "recommendation": "Maintain maintenance dose"}
    
    res["message"] = res["recommendation"]
    return res

def compute_target_score(df: List[Dict]) -> Dict:
    """Composite 0-10 wellness score."""
    if not df: return {"score": 0, "status": "No Data"}
    latest = df[0]
    points = 0
    if latest.get("hb", 0) >= 10: points += 2
    if latest.get("albumin", 0) >= 3.5: points += 2
    if latest.get("phosphorus", 0) <= 5.5: points += 2
    if latest.get("idwg", 10) <= 2.5: points += 2
    if latest.get("urr", 0) >= 65: points += 2
    
    return {
        "score": points,
        "status": "Green" if points >= 8 else "Amber" if points >= 6 else "Red"
    }

def compute_deterioration_risk(hb: Dict, alb: Dict, target: Dict) -> Dict:
    """Combined risk flag."""
    risk_score = 0
    factors = []
    
    if hb.get("alert"): 
        risk_score += 40
        factors.append("Falling Hemoglobin")
    if alb.get("risk"):
        risk_score += 30
        factors.append("Declining Albumin")
    if target.get("score") < 6:
        risk_score += 30
        factors.append("Low Target Achievement")
        
    level = "High" if risk_score >= 60 else "Moderate" if risk_score >= 30 else "Low"
    
    return {
        "available": True,
        "risk_score": risk_score,
        "score": risk_score,
        "risk_level": level,
        "level": level,
        "factors": factors,
        "risk_factors": factors
    }

# ─── RUNNERS ─────────────────────────────────────────────────────────────────

def run_patient_analytics(db: Session, patient_id: int) -> Dict:
    """Aggregated analytics for timeline."""
    records = db.query(MonthlyRecord).filter(MonthlyRecord.patient_id == patient_id).order_by(desc(MonthlyRecord.record_month)).limit(12).all()
    df = []
    for r in records:
        df.append({
            "month": r.record_month,
            "hb": r.hb,
            "albumin": r.albumin,
            "phosphorus": r.phosphorus,
            "idwg": r.idwg,
            "urr": r.urr,
            "serum_ferritin": r.serum_ferritin,
            "tsat": r.tsat,
            "epo_weekly_units": r.epo_weekly_units
        })
    
    if not df:
        return {"status": "no_data"}

    hb_traj = predict_hb_trajectory(df)
    epo_resp = detect_epo_hyporesponse(df, hb_traj)
    alb_risk = assess_albumin_decline(df)
    iron_stat = classify_iron_status(df[0])
    target_score = compute_target_score(df)
    det_risk = compute_deterioration_risk(hb_traj, alb_risk, target_score)

    return {
        "status": "ok",
        "hb_trajectory": hb_traj,
        "epo_response": epo_resp,
        "albumin_risk": alb_risk,
        "iron_status": iron_stat,
        "target_score": target_score,
        "deterioration_risk": det_risk,
        "history_count": len(df)
    }

def run_cohort_analytics(db: Session) -> Dict:
    """Aggregated metrics for charts."""
    records = db.query(MonthlyRecord).order_by(MonthlyRecord.record_month).all()
    if not records:
        return {"available": False}
    
    trends = {}
    for r in records:
        m = r.record_month
        if m not in trends: trends[m] = {"hb": [], "alb": [], "phos": []}
        if r.hb: trends[m]["hb"].append(r.hb)
        if r.albumin: trends[m]["alb"].append(r.albumin)
        if r.phosphorus: trends[m]["phos"].append(r.phosphorus)
        
    months = sorted(trends.keys())
    hb_stats = []
    alb_stats = []
    phos_stats = []
    
    for m in months:
        for key, stats_list in [("hb", hb_stats), ("alb", alb_stats), ("phos", phos_stats)]:
            vals = trends[m][key]
            if not vals:
                stats_list.append({"median": 0, "p25": 0, "p75": 0})
                continue
            med = statistics.median(vals)
            sorted_vals = sorted(vals)
            n = len(sorted_vals)
            p25 = sorted_vals[int(n*0.25)]
            p75 = sorted_vals[int(n*0.75)]
            stats_list.append({"median": round(med, 1), "p25": round(p25, 1), "p75": round(p75, 1)})

    return {
        "available": True,
        "months": months,
        "hb": hb_stats,
        "alb": alb_stats,
        "phos": phos_stats,
        "latest_month": months[-1] if months else None
    }
