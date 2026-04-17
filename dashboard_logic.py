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

logger = logging.getLogger(__name__)

def get_current_month_str():
    return datetime.now().strftime("%Y-%m")

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
        'unknown_sex': {'count': 0, 'names': []},
        'non_avf': {'count': 0, 'names': []},
        'idwg_high': {'count': 0, 'names': []},
        'albumin_low': {'count': 0, 'names': []},
        'calcium_low': {'count': 0, 'names': []},
        'phos_high': {'count': 0, 'names': []},
        'epo_hypo': {'count': 0, 'names': []},
        'iv_iron_rec': {'count': 0, 'names': []}
    }

    # Fetch all active patients
    active_patients = db.query(Patient).filter(Patient.is_active == True).all()
    patient_map = {p.id: p.name for p in active_patients}
    
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
        else:
            metrics['unknown_sex']['count'] += 1
            metrics['unknown_sex']['names'].append(p.name)

    # Fetch Clinical Records for selected month
    records = db.query(MonthlyRecord).filter(MonthlyRecord.record_month == month).all()
    
    for r in records:
        name = patient_map.get(r.patient_id, "Unknown")
        
        # 1. Non-AVF Access
        if r.access_type and r.access_type != "AVF":
            metrics['non_avf']['count'] += 1
            metrics['non_avf']['names'].append(name)
            
        # 2. IDWG > 2.5kg
        if r.idwg and r.idwg > 2.5:
            metrics['idwg_high']['count'] += 1
            metrics['idwg_high']['names'].append(name)
            
        # 3. Albumin < 3.5 g/dL
        if r.albumin and r.albumin < 3.5:
            metrics['albumin_low']['count'] += 1
            metrics['albumin_low']['names'].append(name)

        # 4. Corrected Calcium < 8.5 mg/dL
        if r.calcium and r.calcium < 8.5:
            metrics['calcium_low']['count'] += 1
            metrics['calcium_low']['names'].append(name)
            
        # 5. Phosphorus > 5.5 mg/dL
        if r.phosphorus and r.phosphorus > 5.5:
            metrics['phos_high']['count'] += 1
            metrics['phos_high']['names'].append(name)

        # 6. EPO Hypo-response (Hb < 10 despite >10k units)
        if r.hb and r.hb < 10 and r.epo_weekly_units and r.epo_weekly_units > 10000:
            metrics['epo_hypo']['count'] += 1
            metrics['epo_hypo']['names'].append(name)

    return metrics
