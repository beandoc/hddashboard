"""
dynamic_vars.py
===============
User-defined clinical variable system.

Storage: MonthlyRecord.dynamic_data (JSONB, GIN-indexed).
Shape:   {"<var_name>": {"v": <float|null>, "t": "<text|null>", "by": "<entered_by>"}}

VariableDefinition stays as the schema registry (thresholds, display metadata,
alerting rules). VariableValue EAV table was removed in migration 0004.
"""
from __future__ import annotations

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text
from sqlalchemy.orm import Session
from datetime import datetime
from database import Base, MonthlyRecord


class VariableDefinition(Base):
    """Schema registry for user-defined clinical variables."""
    __tablename__ = "variable_definitions"

    id           = Column(Integer, primary_key=True, index=True)
    name         = Column(String, nullable=False, unique=True)
    display_name = Column(String, nullable=False)
    unit         = Column(String)
    category     = Column(String, default="Lab")
    data_type    = Column(String, default="number")

    threshold_low  = Column(Float)
    threshold_high = Column(Float)
    target_low     = Column(Float)
    target_high    = Column(Float)

    description           = Column(Text)
    normal_range          = Column(Text)
    clinical_significance = Column(Text)
    is_active         = Column(Boolean, default=True)
    show_in_dashboard = Column(Boolean, default=True)
    show_in_timeline  = Column(Boolean, default=True)
    alert_direction   = Column(String, default="both")
    decimal_places    = Column(Integer, default=1)

    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String)


# ── JSONB helpers ─────────────────────────────────────────────────────────────

def get_dynamic_value(db: Session, patient_id: int, month_str: str, var_name: str) -> dict | None:
    """Return the JSONB entry for one variable, or None."""
    rec = db.query(MonthlyRecord).filter(
        MonthlyRecord.patient_id == patient_id,
        MonthlyRecord.record_month == month_str,
    ).first()
    if rec is None or not rec.dynamic_data:
        return None
    return rec.dynamic_data.get(var_name)


def upsert_variable_value(
    db: Session,
    patient_id: int,
    month_str: str,
    variable_id: int,
    value_num=None,
    value_text=None,
    entered_by: str = "",
) -> None:
    """Write (or overwrite) a dynamic variable value into MonthlyRecord.dynamic_data."""
    vdef = db.query(VariableDefinition).filter(VariableDefinition.id == variable_id).first()
    if vdef is None:
        raise ValueError(f"VariableDefinition id={variable_id} not found")

    rec = db.query(MonthlyRecord).filter(
        MonthlyRecord.patient_id == patient_id,
        MonthlyRecord.record_month == month_str,
    ).first()
    if rec is None:
        rec = MonthlyRecord(patient_id=patient_id, record_month=month_str, entered_by=entered_by)
        db.add(rec)
        db.flush()

    current = dict(rec.dynamic_data) if rec.dynamic_data else {}
    entry: dict = {}
    if value_num is not None:
        entry["v"] = value_num
    if value_text is not None:
        entry["t"] = value_text
    if entered_by:
        entry["by"] = entered_by
    current[vdef.name] = entry

    # Re-assign to trigger SQLAlchemy change detection on JSONB columns.
    rec.dynamic_data = current
    db.commit()


def get_patient_all_dynamic_values(db: Session, patient_id: int, month_str: str) -> dict:
    """Return all dynamic variable values for a patient in a given month.

    Returns {var_name: {"value": float, "text": str, "display_name": str, "unit": str}}
    """
    rec = db.query(MonthlyRecord).filter(
        MonthlyRecord.patient_id == patient_id,
        MonthlyRecord.record_month == month_str,
    ).first()
    if rec is None or not rec.dynamic_data:
        return {}

    # Build a name→definition lookup for metadata
    names = list(rec.dynamic_data.keys())
    defs = {
        vd.name: vd
        for vd in db.query(VariableDefinition).filter(VariableDefinition.name.in_(names)).all()
    }

    result = {}
    for var_name, entry in rec.dynamic_data.items():
        vd = defs.get(var_name)
        result[var_name] = {
            "value":        entry.get("v"),
            "text":         entry.get("t"),
            "display_name": vd.display_name if vd else var_name,
            "unit":         vd.unit if vd else "",
        }
    return result


def get_patient_variable_history(db: Session, patient_id: int, variable_id: int) -> list:
    """Return [{month, value, text}] sorted ascending for one patient + variable."""
    vdef = db.query(VariableDefinition).filter(VariableDefinition.id == variable_id).first()
    if vdef is None:
        return []

    recs = (
        db.query(MonthlyRecord)
        .filter(
            MonthlyRecord.patient_id == patient_id,
            MonthlyRecord.dynamic_data[vdef.name].isnot(None),
        )
        .order_by(MonthlyRecord.record_month.asc())
        .all()
    )
    return [
        {
            "month": r.record_month,
            "value": (r.dynamic_data.get(vdef.name) or {}).get("v"),
            "text":  (r.dynamic_data.get(vdef.name) or {}).get("t"),
        }
        for r in recs
    ]


def get_all_variable_values_for_cohort(
    db: Session,
    var_name: str,
    patient_ids: list[int],
    from_m: str,
    to_m: str,
) -> dict:
    """Return {patient_id: {month: float}} for a variable across a cohort.

    Single query via JSONB path extraction — replaces the N-join EAV pattern.
    """
    from sqlalchemy import text, cast
    from sqlalchemy.dialects.postgresql import JSONB as _JSONB

    recs = (
        db.query(MonthlyRecord)
        .filter(
            MonthlyRecord.patient_id.in_(patient_ids),
            MonthlyRecord.record_month >= from_m,
            MonthlyRecord.record_month <= to_m,
            MonthlyRecord.dynamic_data[var_name].isnot(None),
        )
        .all()
    )
    out: dict = {}
    for r in recs:
        entry = (r.dynamic_data or {}).get(var_name, {})
        val = entry.get("v") if isinstance(entry, dict) else None
        if val is not None:
            out.setdefault(r.patient_id, {})[r.record_month] = val
    return out


# ── Preset seed ───────────────────────────────────────────────────────────────

PRESET_VARIABLES = [
    {"name": "crp", "display_name": "C-Reactive Protein", "unit": "mg/L", "category": "Lab",
     "data_type": "number", "threshold_high": 10.0, "target_high": 5.0,
     "alert_direction": "high", "decimal_places": 1,
     "description": "Marker of inflammation. High CRP explains EPO hypo-response and albumin decline.",
     "show_in_dashboard": True},
    {"name": "blood_transfusion_units", "display_name": "Blood Transfusion", "unit": "units/month",
     "category": "Clinical", "data_type": "integer", "threshold_high": 0,
     "alert_direction": "high", "decimal_places": 0,
     "description": "Number of packed red cell units transfused this month.",
     "show_in_dashboard": True},
    {"name": "kt_v", "display_name": "Kt/V", "unit": "", "category": "Adequacy",
     "data_type": "number", "threshold_low": 1.2, "target_low": 1.2, "target_high": 1.8,
     "alert_direction": "low", "decimal_places": 2,
     "description": "Dialysis adequacy index. KDIGO target ≥ 1.2.", "show_in_dashboard": True},
    {"name": "bicarbonate", "display_name": "Serum Bicarbonate", "unit": "mmol/L", "category": "Lab",
     "data_type": "number", "threshold_low": 22.0, "target_low": 22.0, "target_high": 26.0,
     "alert_direction": "low", "decimal_places": 1,
     "description": "Pre-dialysis serum bicarbonate. Target 22-26 mmol/L.", "show_in_dashboard": False},
    {"name": "systolic_bp_pre", "display_name": "Pre-dialysis SBP", "unit": "mmHg",
     "category": "Vitals", "data_type": "integer",
     "threshold_high": 160.0, "threshold_low": 90.0, "alert_direction": "both",
     "decimal_places": 0,
     "description": "Average pre-dialysis systolic blood pressure this month.", "show_in_dashboard": False},
    {"name": "intradialytic_hypotension", "display_name": "Intradialytic Hypotension",
     "unit": "episodes/month", "category": "Clinical", "data_type": "integer",
     "threshold_high": 2, "alert_direction": "high", "decimal_places": 0,
     "description": "Number of IDH episodes requiring intervention this month.", "show_in_dashboard": True},
    {"name": "uric_acid", "display_name": "Uric Acid", "unit": "mg/dL", "category": "Lab",
     "data_type": "number", "threshold_high": 8.0, "alert_direction": "high", "decimal_places": 1,
     "description": "Serum uric acid.", "show_in_dashboard": False},
    {"name": "npcr_dynamic", "display_name": "nPCR", "unit": "g/kg/day", "category": "Nutrition",
     "data_type": "number", "decimal_places": 2, "description": "Normalized Protein Catabolic Rate."},
    {"name": "handgrip_strength", "display_name": "Handgrip Strength", "unit": "kg",
     "category": "Nutrition", "data_type": "number", "decimal_places": 1,
     "description": "Assessment of muscle strength and nutritional status."},
    {"name": "crbsi", "display_name": "CRBSI", "unit": "episodes/quarter",
     "category": "Infection", "data_type": "integer", "threshold_high": 0.0,
     "alert_direction": "high", "decimal_places": 0,
     "description": "Catheter-Related Blood Stream Infections."},
    {"name": "access_thrombosis", "display_name": "Access Thrombosis", "unit": "count/month",
     "category": "Safety", "data_type": "integer", "threshold_high": 0.0,
     "alert_direction": "high", "decimal_places": 0, "description": "AVF / AVG Thrombosis Episodes."},
    {"name": "facit_fatigue", "display_name": "FACIT Fatigue Score", "unit": "0-52",
     "category": "Quality of Life", "data_type": "number", "threshold_low": 30.0,
     "alert_direction": "low", "decimal_places": 0,
     "description": "Fatigue Assessment of Chronic Illness Therapy."},
    {"name": "psqi_sleep", "display_name": "PSQI Sleep Quality", "unit": "0-21",
     "category": "Quality of Life", "data_type": "number", "threshold_high": 5.0,
     "alert_direction": "high", "decimal_places": 0,
     "description": "Pittsburgh Sleep Quality Index."},
    {"name": "phq9_depression", "display_name": "PHQ-9 Depression Score", "unit": "0-27",
     "category": "Quality of Life", "data_type": "number", "threshold_high": 9.0,
     "alert_direction": "high", "decimal_places": 0, "description": "Patient Health Questionnaire-9."},
    {"name": "rls_severity", "display_name": "RLS Severity", "unit": "0-40",
     "category": "Quality of Life", "data_type": "number", "threshold_high": 10.0,
     "alert_direction": "high", "decimal_places": 0, "description": "Restless Legs Syndrome Severity."},
    {"name": "karnofsky_status", "display_name": "Karnofsky Status", "unit": "0-100",
     "category": "Quality of Life", "data_type": "number", "threshold_low": 60.0,
     "alert_direction": "low", "decimal_places": 0, "description": "Functional Status assessment."},
    {"name": "mis_score_dynamic", "display_name": "MIS Score", "unit": "score",
     "category": "Nutrition", "data_type": "number", "threshold_high": 5.0,
     "alert_direction": "high", "decimal_places": 0, "description": "Malnutrition-Inflammation Score."},
    {"name": "eri", "display_name": "ESA Resistance Index (ERI)", "unit": "IU/kg/week/g/dL",
     "category": "Anemia", "data_type": "number", "threshold_high": 10.0,
     "alert_direction": "high", "decimal_places": 1,
     "description": "Erythropoiesis-Stimulating Agent Resistance Index."},
]


def seed_preset_variables(db: Session) -> None:
    for vdef in PRESET_VARIABLES:
        if not db.query(VariableDefinition).filter(VariableDefinition.name == vdef["name"]).first():
            db.add(VariableDefinition(**vdef, created_by="system"))
    db.commit()


def get_all_variables(db: Session, active_only: bool = True) -> list:
    q = db.query(VariableDefinition)
    if active_only:
        q = q.filter(VariableDefinition.is_active == True)
    return q.order_by(VariableDefinition.category, VariableDefinition.display_name).all()
