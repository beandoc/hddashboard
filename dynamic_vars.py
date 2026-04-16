from sqlalchemy.orm import Session
from database import DynamicVariableDefinition, DynamicVariableValue, Patient
from datetime import datetime
import pandas as pd
from typing import List, Dict, Optional

def seed_default_variables(db: Session):
    """Pre-seed the system with research-aligned clinical markers."""
    defaults = [
        {"name": "crp", "display_name": "C-Reactive Protein", "unit": "mg/dL", "category": "Inflammation", "threshold_high": 2.0},
        {"name": "bt_units", "display_name": "Blood Transfusion", "unit": "Units", "category": "Anemia", "threshold_high": 1.0},
        {"name": "kt_v", "display_name": "Kt/V", "unit": "", "category": "Adequacy", "threshold_low": 1.2},
        {"name": "bicarbonate", "display_name": "Bicarbonate", "unit": "mmol/L", "category": "Electrolytes", "threshold_low": 22.0, "threshold_high": 26.0},
        {"name": "sbp_pre", "display_name": "Pre-dialysis SBP", "unit": "mmHg", "category": "Vitals", "threshold_high": 160.0},
        {"name": "idh_events", "display_name": "IDH Events", "unit": "Count", "category": "Safety", "threshold_high": 1.0},
        {"name": "uric_acid", "display_name": "Uric Acid", "unit": "mg/dL", "category": "Metabolic", "threshold_high": 7.0},
    ]
    for d in defaults:
        existing = db.query(DynamicVariableDefinition).filter(DynamicVariableDefinition.name == d["name"]).first()
        if not existing:
            new_v = DynamicVariableDefinition(**d)
            db.add(new_v)
    db.commit()

def get_variable_data_grid(db: Session, variable_id: int, months: List[str]):
    """Returns a grid structure for bulk entry: Rows=Patients, Cols=Months."""
    patients = db.query(Patient).filter(Patient.is_active == True).order_by(Patient.name).all()
    values = db.query(DynamicVariableValue).filter(
        DynamicVariableValue.variable_id == variable_id,
        DynamicVariableValue.record_month.in_(months)
    ).all()
    
    val_map = {(v.patient_id, v.record_month): v.value for v in values}
    
    grid = []
    for p in patients:
        row = {"id": p.id, "name": p.name, "hid": p.hid_no, "values": {}}
        for m in months:
            row["values"][m] = val_map.get((p.id, m))
        grid.append(row)
    return grid

def save_variable_values(db: Session, variable_id: int, updates: List[Dict]):
    """Bulk saves variable values from the UI grid."""
    for item in updates:
        pid = item.get("patient_id")
        month = item.get("month")
        val = item.get("value")
        
        if val is None or val == "":
            # Delete if empty string provided? Usually safer to just not update or delete.
            continue
            
        existing = db.query(DynamicVariableValue).filter(
            DynamicVariableValue.variable_id == variable_id,
            DynamicVariableValue.patient_id == pid,
            DynamicVariableValue.record_month == month
        ).first()
        
        try:
            numeric_val = float(val)
            if existing:
                existing.value = numeric_val
                existing.timestamp = datetime.utcnow()
            else:
                db.add(DynamicVariableValue(
                    patient_id=pid, variable_id=variable_id, 
                    record_month=month, value=numeric_val
                ))
        except (ValueError, TypeError):
            continue
    db.commit()

def get_dynamic_variable_analytics(db: Session, variable_id: int):
    """Calculates cohort-wide distribution and trends for a dynamic variable."""
    defn = db.query(DynamicVariableDefinition).filter(DynamicVariableDefinition.id == variable_id).first()
    if not defn: return None
    
    # Get all values for last 12 months
    values = db.query(DynamicVariableValue).filter(
        DynamicVariableValue.variable_id == variable_id
    ).order_by(DynamicVariableValue.record_month).all()
    
    if not values: return {"name": defn.display_name, "has_data": False}
    
    df = pd.DataFrame([{
        "month": v.record_month, "val": v.value, "pid": v.patient_id
    } for v in values])
    
    # Latest month stats
    latest_month = df["month"].max()
    latest_df = df[df["month"] == latest_month]
    
    # Trends
    trend_stats = df.groupby("month")["val"].agg(["median", lambda x: x.quantile(0.25), lambda x: x.quantile(0.75)]).reset_index()
    trend_stats.columns = ["month", "median", "p25", "p75"]
    
    return {
        "definition": {
            "name": defn.name, "display_name": defn.display_name, "unit": defn.unit,
            "threshold_low": defn.threshold_low, "threshold_high": defn.threshold_high
        },
        "latest": {
            "month": latest_month,
            "values": latest_df["val"].tolist(),
            "avg": round(latest_df["val"].mean(), 2),
            "count": len(latest_df)
        },
        "trends": {
            "months": trend_stats["month"].tolist(),
            "median": trend_stats["median"].tolist(),
            "p25": trend_stats["p25"].tolist(),
            "p75": trend_stats["p75"].tolist()
        }
    }
