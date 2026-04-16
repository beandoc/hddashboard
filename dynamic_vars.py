from sqlalchemy.orm import Session
from database import VariableDefinition, VariableValue, Patient
from datetime import datetime
from typing import List, Dict, Optional

def seed_preset_variables(db: Session):
    """Pre-seed the system with research-aligned clinical markers."""
    presets = [
        {"name": "crp", "display_name": "C-Reactive Protein", "unit": "mg/dL", "category": "Inflammation", "threshold_high": 2.0},
        {"name": "bt_units", "display_name": "Blood Transfusion", "unit": "Units", "category": "Anemia", "threshold_high": 1.0},
        {"name": "kt_v", "display_name": "Kt/V", "unit": "", "category": "Adequacy", "threshold_low": 1.2, "show_in_dashboard": True},
        {"name": "bicarbonate", "display_name": "Bicarbonate", "unit": "mmol/L", "category": "Electrolytes", "threshold_low": 22.0, "threshold_high": 26.0},
        {"name": "sbp_pre", "display_name": "Pre-dialysis SBP", "unit": "mmHg", "category": "Vitals", "threshold_high": 160.0, "show_in_dashboard": True},
        {"name": "idh_events", "display_name": "IDH Events", "unit": "Count", "category": "Safety", "threshold_high": 1.0},
        {"name": "uric_acid", "display_name": "Uric Acid", "unit": "mg/dL", "category": "Metabolic", "threshold_high": 7.0},
    ]
    for p in presets:
        existing = db.query(VariableDefinition).filter(VariableDefinition.name == p["name"]).first()
        if not existing:
            new_v = VariableDefinition(**p)
            db.add(new_v)
    db.commit()

def get_all_variables(db: Session, active_only: bool = True):
    """List all defined clinical variables."""
    q = db.query(VariableDefinition)
    if active_only:
        q = q.filter(VariableDefinition.is_active == True)
    return q.order_by(VariableDefinition.category, VariableDefinition.display_name).all()

def get_patient_variable_history(db: Session, patient_id: int, variable_id: int):
    """Pull longitudinal history for a specific variable for a patient."""
    return db.query(VariableValue).filter(
        VariableValue.patient_id == patient_id,
        VariableValue.variable_id == variable_id
    ).order_by(VariableValue.record_month).all()

def upsert_variable_value(db: Session, patient_id: int, month_str: str, variable_id: int, value_num: Optional[float] = None, value_text: Optional[str] = None, entered_by: str = ""):
    """Save or update a clinical variable value."""
    existing = db.query(VariableValue).filter(
        VariableValue.patient_id == patient_id,
        VariableValue.variable_id == variable_id,
        VariableValue.record_month == month_str
    ).first()
    
    if existing:
        existing.value_num = value_num
        existing.value_text = value_text
        existing.entered_by = entered_by
        existing.timestamp = datetime.utcnow()
    else:
        new_v = VariableValue(
            patient_id=patient_id, record_month=month_str,
            variable_id=variable_id, value_num=value_num,
            value_text=value_text, entered_by=entered_by
        )
        db.add(new_v)
    db.commit()
