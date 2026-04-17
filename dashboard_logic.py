"""
dashboard_logic.py
==================
Core clinical calculation logic for the Hemodialysis Dashboard.
Locked - Do not modify without clinical validation.
"""
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import Patient, MonthlyRecord
from datetime import datetime
import logging
from ml_analytics import normalize_epo_dose

logger = logging.getLogger(__name__)

def get_current_month_str():
    return datetime.now().strftime("%Y-%m")

def get_month_label(month_str: str) -> str:
    dt = datetime.strptime(month_str, "%Y-%m")
    return dt.strftime("%B %Y")

def compute_dashboard(db: Session, month: str = None):
    """
    Computes all clinical metrics and alerts for the dashboard.
    Returns: dict of metric objects.
    """
    if not month:
        month = get_current_month_str()
        
    metrics = {
        'total_patients': {'count': 0, 'names': []},
        'male_patients': {'count': 0, 'names': []},
        'female_patients': {'count': 0, 'names': []},
        'non_avf': {'count': 0, 'names': [], 'types': {}},
        'idwg_high': {'count': 0, 'names': []},
        'albumin_low': {'count': 0, 'names': []},
        'calcium_low': {'count': 0, 'names': []},
        'phos_high': {'count': 0, 'names': []},
        'epo_hypo': {'count': 0, 'names': []},
        'iv_iron_rec': {'count': 0, 'names': []},
        'trend_hb': [],
        'trend_albumin': [],
        'trend_phosphorus': []
    }

    # Fetch all active patients
    active_patients = db.query(Patient).filter(Patient.is_active == True).all()
    patient_map = {p.id: p for p in active_patients}
    
    # Process Demographics
    for p in active_patients:
        metrics['total_patients']['count'] += 1
        metrics['total_patients']['names'].append(p.name)
        
        s = (p.sex or "Unknown").strip()
        if s == "Male":
            metrics['male_patients']['count'] += 1
            metrics['male_patients']['names'].append(p.name)
        elif s == "Female":
            metrics['female_patients']['count'] += 1
            metrics['female_patients']['names'].append(p.name)

    # Fetch Clinical Records for selected month
    records = db.query(MonthlyRecord).filter(MonthlyRecord.record_month == month).all()
    record_map = {r.patient_id: r for r in records}
    
    patient_rows = []

    for p in active_patients:
        r = record_map.get(p.id)
        row = {
            "id": p.id,
            "name": p.name,
            "hid": p.hid_no,
            "has_record": r is not None,
            "access": r.access_type if r else p.access_type,
            "idwg": r.idwg if r else None,
            "hb": r.hb if r else None,
            "ferritin": r.serum_ferritin if r else None,
            "tsat": r.tsat if r else None,
            "corrected_ca": r.calcium if r else None, # Placeholder for corr logic 
            "phosphorus": r.phosphorus if r else None,
            "albumin": r.albumin if r else None,
            "ipth": r.ipth if r else None,
            "vit_d": r.vit_d if r else None,
            "protein": r.av_daily_protein if r else None,
            "alerts": []
        }
        
        if r:
            name = p.name
            # 1. Non-AVF Access
            raw_access = (r.access_type or "").strip()
            access = "Permacath" if raw_access in ("P/Cath", "P-Cath", "Permacath", "PCATH") else raw_access
            if access and access.upper() != "AVF":
                metrics['non_avf']['count'] += 1
                metrics['non_avf']['names'].append(name)
                if access not in metrics['non_avf']['types']:
                    metrics['non_avf']['types'][access] = {"count": 0, "names": []}
                metrics['non_avf']['types'][access]["count"] += 1
                metrics['non_avf']['types'][access]["names"].append(name)
                row["alerts"].append("Non-AVF")
                
            # 2. IDWG > 2.5kg
            if r.idwg and r.idwg > 2.5:
                metrics['idwg_high']['count'] += 1
                metrics['idwg_high']['names'].append(name)
                metrics['trend_hb'].append({"name": name, "current": r.idwg})
                row["alerts"].append("High IDWG")
                
            # 3. Albumin < 3.5 g/dL
            if r.albumin and r.albumin < 3.5:
                metrics['albumin_low']['count'] += 1
                metrics['albumin_low']['names'].append(name)
                metrics['trend_albumin'].append({"name": name, "current": r.albumin})
                row["alerts"].append("Low Albumin")

            # 4. Corrected Calcium < 8.5 mg/dL
            if r.calcium and r.calcium < 8.5:
                metrics['calcium_low']['count'] += 1
                metrics['calcium_low']['names'].append(name)
                row["alerts"].append("Low Calcium")
                
            # 5. Phosphorus > 5.5 mg/dL
            if r.phosphorus and r.phosphorus > 5.5:
                metrics['phos_high']['count'] += 1
                metrics['phos_high']['names'].append(name)
                metrics['trend_phosphorus'].append({"name": name, "current": r.phosphorus})
                row["alerts"].append("High Phos")

            # 6. EPO Hypo-response (normalise Mircera/Darbepoetin to weekly IU equiv)
            _epo_iu = r.epo_weekly_units
            if _epo_iu is None and r.epo_mircera_dose:
                _parsed = normalize_epo_dose(r.epo_mircera_dose)
                if _parsed.get("confidence") == "high":
                    _epo_iu = _parsed.get("weekly_iu")
            if r.hb and r.hb < 10 and _epo_iu and _epo_iu > 10000:
                metrics['epo_hypo']['count'] += 1
                metrics['epo_hypo']['names'].append(name)
                row["alerts"].append("EPO Hypo")
        
        patient_rows.append(row)

    return {
        "metrics": metrics,
        "patient_rows": patient_rows,
        "month_label": get_month_label(month),
        "total_active": len(active_patients)
    }


def get_patients_needing_alerts(db: Session, month: str = None):
    if not month:
        month = get_current_month_str()

    active_patients = db.query(Patient).filter(Patient.is_active == True).all()
    records = db.query(MonthlyRecord).filter(MonthlyRecord.record_month == month).all()
    record_map = {r.patient_id: r for r in records}

    result = []
    for p in active_patients:
        r = record_map.get(p.id)
        if not r:
            continue
        alerts = []
        raw_access = (r.access_type or "").strip()
        access = "Permacath" if raw_access in ("P/Cath", "P-Cath", "Permacath", "PCATH") else raw_access
        if access and access.upper() != "AVF":
            alerts.append("Non-AVF")
        if r.idwg and r.idwg > 2.5:
            alerts.append("High IDWG")
        if r.albumin and r.albumin < 3.5:
            alerts.append("Low Albumin")
        if r.calcium and r.calcium < 8.5:
            alerts.append("Low Calcium")
        if r.phosphorus and r.phosphorus > 5.5:
            alerts.append("High Phos")
        _epo_iu = r.epo_weekly_units
        if _epo_iu is None and r.epo_mircera_dose:
            _parsed = normalize_epo_dose(r.epo_mircera_dose)
            if _parsed.get("confidence") == "high":
                _epo_iu = _parsed.get("weekly_iu")
        if r.hb and r.hb < 10 and _epo_iu and _epo_iu > 10000:
            alerts.append("EPO Hypo")
        if alerts:
            result.append({
                "patient": p,
                "alerts": alerts,
                "record": {
                    "hb": r.hb,
                    "albumin": r.albumin,
                    "phosphorus": r.phosphorus,
                    "corrected_ca": r.calcium,
                    "idwg": r.idwg,
                    "ipth": r.ipth,
                },
            })
    return result
