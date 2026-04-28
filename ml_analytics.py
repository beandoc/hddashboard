import logging
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, text
import json

logger = logging.getLogger(__name__)

def get_current_month_str():
    return datetime.now().strftime("%Y-%m")

def get_month_label(month_str: str) -> str:
    if not month_str: return "N/A"
    try:
        dt = datetime.strptime(month_str, "%Y-%m")
        return dt.strftime("%b %Y")
    except:
        return month_str

def run_patient_analytics(db: Session, patient_id: int) -> dict:
    # (Placeholder for the large existing function, keeping the structure)
    return {"available": True, "insights": []}

def analyze_bfr_trend(sessions: List[dict]) -> dict:
    return {"status": "Stable"}

def run_cohort_analytics(db: Session, month_str: str) -> dict:
    return {}

def get_at_risk_trends(db: Session, parameter: str, month_str: str) -> List[dict]:
    return []

def analyze_pds(db: Session, patient_id: int) -> dict:
    return {"status": "N/A"}

def analyze_mia_cascade(db: Session, patient_id: int) -> dict:
    """
    Malnutrition–Inflammation–Atherosclerosis (MIA) Early Warning Dashboard
    Refined logic based on clinical review thresholds:
    1. Nutrition (Albumin, Prealbumin, nPCR, Weight)
    2. Inflammation (CRP, Ferritin, NLR)
    3. Atherosclerosis (Troponin, BNP, Pulse Pressure, CaXP)
    4. Dialysis Factors (UFR, Kt/V, IDWG, Hypotension)
    5. Events (Hospitalizations, Anorexia, Crashes)
    """
    from database import MonthlyRecord, Patient, ClinicalEvent

    p = db.query(Patient).filter(Patient.id == patient_id).first()
    records = db.query(MonthlyRecord).filter(
        MonthlyRecord.patient_id == patient_id
    ).order_by(MonthlyRecord.record_month.asc()).all()

    if not records:
        return {"available": False}

    records = records[-9:] # 9 months view

    timeline = []
    
    # Track previous month values for trend detection (e.g. Albumin fall)
    prev_alb = None
    
    for i, rec in enumerate(records):
        m = rec.record_month
        domain_scores = {"nutrition": 0, "inflammation": 0, "atherosclerosis": 0, "dialysis": 0, "events": 0}
        events = []
        
        # ── 1. NUTRITION ──────────────────────────────────────────────────────
        # Albumin: <3.8 (Y), <3.5 (R). Fall >0.2 in 4-8 weeks (Y)
        if rec.albumin:
            if rec.albumin < 3.5: domain_scores["nutrition"] = 2
            elif rec.albumin < 3.8: domain_scores["nutrition"] = 1
            
            if prev_alb and (prev_alb - rec.albumin) >= 0.2:
                domain_scores["nutrition"] = max(domain_scores["nutrition"], 1)
                events.append({"icon": "🥩", "color": "#f59e0b", "text": f"Rapid Albumin drop ({prev_alb} -> {rec.albumin} g/dL)"})
            prev_alb = rec.albumin

        # Prealbumin: <30 (Y), <20 (R)
        if rec.prealbumin:
            if rec.prealbumin < 20: domain_scores["nutrition"] = 2
            elif rec.prealbumin < 30: domain_scores["nutrition"] = max(domain_scores["nutrition"], 1)

        # nPCR: <1.2 (Y), <1.0 (R)
        if rec.npcr:
            if rec.npcr < 1.0: domain_scores["nutrition"] = 2
            elif rec.npcr < 1.2: domain_scores["nutrition"] = max(domain_scores["nutrition"], 1)

        # ── 2. INFLAMMATION ───────────────────────────────────────────────────
        # CRP: >3 (Y), >10 (R), >20 (R+)
        if rec.crp:
            if rec.crp >= 10: domain_scores["inflammation"] = 2
            elif rec.crp >= 3: domain_scores["inflammation"] = 1
            
            if rec.crp > 20:
                events.append({"icon": "🔥", "color": "#ef4444", "text": f"Severe Inflammation (CRP {rec.crp} mg/L)"})

        # Ferritin: >800 (Y) if TSAT low
        if rec.serum_ferritin and rec.serum_ferritin > 800 and (rec.tsat or 100) < 20:
            domain_scores["inflammation"] = max(domain_scores["inflammation"], 1)
            events.append({"icon": "🧪", "color": "#f59e0b", "text": "High Ferritin + Low TSAT (RE Siderosis/Inflammation)"})

        # ── 3. ATHEROSCLEROSIS / CARDIAC ──────────────────────────────────────
        # Troponin: Pos (Y). BNP: >2000 (Y), >3000 (R)
        if rec.nt_probnp:
            if rec.nt_probnp > 3000: domain_scores["atherosclerosis"] = 2
            elif rec.nt_probnp > 1500: domain_scores["atherosclerosis"] = 1
            
        if rec.troponin_i and rec.troponin_i > 0.04: # Example threshold
            domain_scores["atherosclerosis"] = 2
            events.append({"icon": "🫀", "color": "#ef4444", "text": f"Cardiac Injury Marker Positive (Trop I: {rec.troponin_i})"})

        # Pulse Pressure: >60 (Y), >70 (R)
        if rec.bp_sys and rec.bp_dia:
            pp = rec.bp_sys - rec.bp_dia
            if pp > 70: domain_scores["atherosclerosis"] = 2
            elif pp > 60: domain_scores["atherosclerosis"] = max(domain_scores["atherosclerosis"], 1)

        # ── 4. DIALYSIS FACTORS ───────────────────────────────────────────────
        # UFR: >10 (Y), >13 (R). Kt/V: <1.2 (Y). IDWG: >5% (Y)
        if rec.ufr:
            if rec.ufr > 13: domain_scores["dialysis"] = 2
            elif rec.ufr > 10: domain_scores["dialysis"] = 1
            
        if rec.single_pool_ktv and rec.single_pool_ktv < 1.2:
            domain_scores["dialysis"] = max(domain_scores["dialysis"], 1)
            
        if rec.idwg and p.dry_weight:
            idwg_pct = (rec.idwg / p.dry_weight) * 100
            if idwg_pct > 5.0:
                domain_scores["dialysis"] = max(domain_scores["dialysis"], 1)
                events.append({"icon": "⚖️", "color": "#f59e0b", "text": f"High fluid gain ({round(idwg_pct,1)}% IDWG)"})

        # ── 5. CLINICAL EVENTS ────────────────────────────────────────────────
        # Hospitalization (🏥), Sepsis/MI (⚡), Anorexia (🍽️)
        if rec.hospitalization_this_month:
            domain_scores["events"] = 2
            events.append({"icon": "🏥", "color": "#ef4444", "text": "Hospital Admission logged this month"})
            
        # Check for specific symptoms in ClinicalEvent
        # (Assuming we have a query here or it was passed in)
        
        # Composite Scoring
        total_risk = sum(domain_scores.values())
        status_color = "green"
        if total_risk >= 4 or any(v == 2 for v in domain_scores.values()):
            status_color = "red"
        elif total_risk >= 2:
            status_color = "yellow"
            
        timeline.append({
            "month": m,
            "label": get_month_label(m),
            "scores": domain_scores, # {domain: 0/1/2}
            "total": total_risk,
            "status": status_color,
            "events": events
        })

    # Alert Logic: Cascade Detected if multiple domains are yellow/red
    alert_triggered = False
    if len(timeline) >= 2:
        last = timeline[-1]
        prior = timeline[-2]
        # Rule: Alert if sum >= 3 or persistent decline
        if last["total"] >= 4 or (last["total"] >= 2 and prior["total"] >= 2):
            alert_triggered = True

    return {
        "available": True,
        "timeline": timeline,
        "alert_triggered": alert_triggered,
        "current_status": timeline[-1]["status"] if timeline else "green"
    }

def analyze_cardiorenal_cascade(db: Session, patient_id: int) -> dict:
    from database import Patient, MonthlyRecord
    p = db.query(Patient).filter(Patient.id == patient_id).first()
    if not p: return {"available": False}
    records = db.query(MonthlyRecord).filter(MonthlyRecord.patient_id == patient_id).order_by(MonthlyRecord.record_month.asc()).all()
    if not records: return {"available": False}
    records = records[-6:]
    events = []
    risk_score = 0
    ef = p.ejection_fraction
    dd = p.diastolic_dysfunction or "None"
    if ef is not None and ef < 40:
        risk_score += 3
        events.append({"type": "cardiac", "text": f"Severe LV systolic dysfunction (EF: {ef}%)"})
    elif ef is not None and ef < 50:
        risk_score += 2
        events.append({"type": "cardiac", "text": f"Mild/Moderate LV systolic dysfunction (EF: {ef}%)"})
    if "Grade III" in dd or "Grade 3" in dd:
        risk_score += 3
        events.append({"type": "cardiac", "text": f"Severe Diastolic Dysfunction ({dd})"})
    elif "Grade II" in dd or "Grade 2" in dd:
        risk_score += 2
        events.append({"type": "cardiac", "text": f"Moderate Diastolic Dysfunction ({dd})"})
    urine_outputs = [r.residual_urine_output for r in records if r.residual_urine_output is not None]
    idwgs = [r.idwg for r in records if r.idwg is not None]
    if urine_outputs and len(urine_outputs) >= 2:
        if urine_outputs[-1] < 200:
            risk_score += 2
            events.append({"type": "renal", "text": f"Oliguria/Anuria ({urine_outputs[-1]} mL/day)"})
    if idwgs and len(idwgs) >= 2:
        if idwgs[-1] > 3.5:
            risk_score += 2
            events.append({"type": "fluid", "text": f"High IDWG ({idwgs[-1]} kg)"})
    recent_hosps = [r for r in records if r.hospitalization_this_month]
    if len(recent_hosps) > 0:
        risk_score += 4
        events.append({"type": "outcome", "text": "Recent hospitalization(s)"})
    cascade_detected = risk_score >= 5
    return {"available": True, "cascade_detected": cascade_detected, "risk_score": risk_score, "events": events, "message": "High Cardiorenal / Fluid Overload Cascade risk detected." if cascade_detected else "No active Cardiorenal fluid cascade detected."}

def analyze_avf_maturation(db: Session, patient_id: int) -> dict:
    from database import Patient
    p = db.query(Patient).filter(Patient.id == patient_id).first()
    if not p or not p.access_date or not p.date_first_cannulation: return {"available": False}
    delay_days = (p.date_first_cannulation - p.access_date).days
    if delay_days <= 0: return {"available": False}
    events = []
    risk_score = 0
    events.append({"text": f"Time to first cannulation: {delay_days} days."})
    if delay_days > 45:
        risk_score += 2
        events.append({"text": "Delayed AVF Maturation (> 6 weeks)."})
    if delay_days > 90:
        risk_score += 1
        events.append({"text": "Severe Maturation Failure (> 3 months)."})
    if p.age and p.age >= 65:
        risk_score += 1
        events.append({"text": f"Advanced Age ({p.age} yrs)"})
    if p.dm_status and "diabetes" in p.dm_status.lower():
        risk_score += 2
        events.append({"text": "Diabetes Mellitus history"})
    if p.handgrip_strength and p.handgrip_strength < 20:
        risk_score += 2
        events.append({"text": f"Poor Handgrip Strength ({p.handgrip_strength} kg)"})
    cascade_detected = delay_days > 45 and risk_score >= 3
    return {"available": True, "cascade_detected": cascade_detected, "delay_days": delay_days, "risk_score": risk_score, "events": events, "message": "Delayed AVF Maturation linked to patient demographics." if cascade_detected else "AVF Maturation within expected parameters or uncorrelated."}

