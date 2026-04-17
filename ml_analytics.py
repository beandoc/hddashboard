"""
ml_analytics.py
===============
Predictive analytics for hemodialysis patients.
"""
import statistics
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc
from database import Patient, MonthlyRecord

logger = logging.getLogger(__name__)

def predict_hb_trajectory(df: List[Dict]) -> Dict:
    if len(df) < 2:
        return {"current": df[0]["hb"] if df else None, "predicted": None, "alert": False, "message": "Insufficient data"}
    
    hbs = [r["hb"] for r in df if r["hb"] is not None]
    if len(hbs) < 2: return {"current": hbs[0] if hbs else None, "predicted": None, "alert": False, "message": "Incomplete labs"}
    
    current, prev = hbs[0], hbs[1]
    diff = current - prev
    predicted = round(current + diff, 1)
    
    res = {
        "current": current,
        "next_predicted": predicted,
        "predicted": predicted,
        "alert_predicted_low": predicted < 10.0,
        "alert": predicted < 10.0
    }
    res["message"] = "Predicted to drop below 10 g/dL" if res["alert"] else "Hb trajectory acceptable"
    return res

def detect_epo_hyporesponse(df: List[Dict], hb_meta: Dict) -> Dict:
    if not df:
        return {"hypo_response": False, "status": "Adequate", "class": "success", "message": "No data"}

    latest = df[0]
    hb = latest.get("hb") or 0
    dose = latest.get("epo_weekly_units") or 0
    hypo_response = (0 < hb < 10.0) and (dose > 10000)
    
    severity = ("severe" if hb < 8.5 else "significant") if hypo_response else "none"
    recommendation = "Review iron stores and resistance." if hypo_response else "Responsive."

    return {
        "hypo_response": hypo_response,
        "severity": severity,
        "status": severity.capitalize() if hypo_response else "Adequate",
        "class": "danger" if severity == "severe" else "warning" if hypo_response else "success",
        "message": recommendation
    }

def assess_albumin_decline(df: List[Dict]) -> Dict:
    if len(df) < 2: return {"risk": False, "trend": "→"}
    albs = [r["albumin"] for r in df if r["albumin"] is not None]
    if len(albs) < 2: 
        curr = albs[0] if albs else 0
        return {"risk": curr < 3.5 and curr > 0, "trend": "→", "current": curr}
    
    current, prev = albs[0], albs[1]
    diff = current - prev
    predicted = round(current + diff, 2)
    risk = current < 3.5 or predicted < 3.5
    
    return {
        "current": current,
        "direction": "up" if diff > 0.05 else "down" if diff < -0.05 else "→",
        "trend": "up" if diff > 0.05 else "down" if diff < -0.05 else "→",
        "risk_crossing_35": risk,
        "risk": risk,
        "predicted_2m": predicted,
        "predicted": predicted
    }

def classify_iron_status(latest: Dict) -> Dict:
    fer, tsat = latest.get("serum_ferritin"), latest.get("tsat")
    if fer is None or tsat is None:
        return {"status": "Unknown", "class": "warning", "message": "Incomplete labs"}
    
    if (tsat or 0) < 20: status, rec = "Absolute Deficiency", "Initiate IV Iron Loading"
    elif (fer or 0) < 200: status, rec = "Iron Deficient", "Consider IV Iron"
    elif (fer or 0) > 800: status, rec = "Iron Overload", "Hold Iron"
    else: status, rec = "Adequate", "Maintenance dose"
    
    return {
        "status": status,
        "recommendation": rec,
        "message": rec,
        "class": "danger" if "Deficiency" in status else "warning" if ("Overload" in status or "Deficient" in status) else "success"
    }

def compute_target_score(df: List[Dict]) -> Dict:
    if not df: return {"score": 0, "status": "No Data"}
    latest = df[0]
    points = 0
    if (latest.get("hb") or 0) >= 10: points += 2
    if (latest.get("albumin") or 0) >= 3.5: points += 2
    if (latest.get("phosphorus") or 10) <= 5.5: points += 2
    if (latest.get("idwg") or 10) <= 2.5: points += 2
    if (latest.get("urr") or 0) >= 65: points += 2
    
    label = "Optimal" if points >= 8 else "Sub-optimal" if points >= 6 else "Critical"
    return {"score": points, "label": label, "status": label}

def compute_deterioration_risk(hb: Dict, alb: Dict, target: Dict) -> Dict:
    risk_score = 0
    factors = []
    if hb.get("alert"): risk_score += 40; factors.append("Falling Hb")
    if alb.get("risk"): risk_score += 30; factors.append("Declining Albumin")
    if target.get("score", 0) < 6: risk_score += 30; factors.append("Low Target")
    
    risk_level = "High" if risk_score >= 60 else "Moderate" if risk_score >= 30 else "Low"
    return {
        "available": True,
        "risk_score": risk_score, "score": risk_score,
        "risk_level": risk_level, "level": risk_level,
        "risk_factors": factors, "factors": factors
    }

def run_patient_analytics(db: Session, patient_id: int) -> Dict:
    records = db.query(MonthlyRecord).filter(MonthlyRecord.patient_id == patient_id).order_by(desc(MonthlyRecord.record_month)).limit(12).all()
    df = [{"month": r.record_month, "hb": r.hb, "albumin": r.albumin, "phosphorus": r.phosphorus, "idwg": r.idwg, "urr": r.urr, "serum_ferritin": r.serum_ferritin, "tsat": r.tsat, "epo_weekly_units": r.epo_weekly_units} for r in records]
    
    if not df: return {"status": "no_data"}

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
    records = db.query(MonthlyRecord).order_by(MonthlyRecord.record_month).all()
    if not records: return {"available": False}
    trends = {}
    for r in records:
        m = r.record_month
        if m not in trends: trends[m] = {"hb": [], "alb": [], "phos": []}
        if r.hb: trends[m]["hb"].append(r.hb)
        if r.albumin: trends[m]["alb"].append(r.albumin)
        if r.phosphorus: trends[m]["phos"].append(r.phosphorus)
        
    months = sorted(trends.keys())
    hb_stats, alb_stats, phos_stats = [], [], []
    for m in months:
        for key, stats_list in [("hb", hb_stats), ("alb", alb_stats), ("phos", phos_stats)]:
            vals = trends[m][key]
            if not vals: stats_list.append({"median": 0, "p25": 0, "p75": 0}); continue
            med = statistics.median(vals)
            sorted_vals = sorted(vals)
            n = len(sorted_vals)
            stats_list.append({"median": round(med, 1), "p25": round(sorted_vals[int(n*0.25)], 1), "p75": round(sorted_vals[int(n*0.75)], 1)})
    return {"available": True, "months": months, "hb": hb_stats, "alb": alb_stats, "phos": phos_stats, "latest_month": months[-1] if months else None}
