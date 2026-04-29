"""
dynamic_vars.py
===============
Entity-Attribute-Value system for user-defined clinical variables.
Allows adding new variables through the UI with no code changes.
"""
from sqlalchemy import (Column, Integer, String, Float, Boolean,
                        DateTime, Text, ForeignKey, UniqueConstraint)
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base


class VariableDefinition(Base):
    """
    A user-defined clinical variable.
    e.g. CRP, Blood Transfusion count, Bicarbonate, custom scores
    """
    __tablename__ = "variable_definitions"

    id           = Column(Integer, primary_key=True, index=True)
    name         = Column(String, nullable=False, unique=True)  # "CRP"
    display_name = Column(String, nullable=False)               # "C-Reactive Protein"
    unit         = Column(String)                               # "mg/L"
    category     = Column(String, default="Lab")                # Lab / Vitals / Clinical / Score
    data_type    = Column(String, default="number")             # number / integer / text / boolean
    
    # Thresholds for alerting and colour coding
    threshold_low      = Column(Float)   # below this = alert (e.g. Hb < 10)
    threshold_high     = Column(Float)   # above this = alert (e.g. CRP > 10)
    target_low         = Column(Float)   # green zone lower bound
    target_high        = Column(Float)   # green zone upper bound
    
    # Display
    description        = Column(Text)    # clinical notes about this variable
    is_active          = Column(Boolean, default=True)
    show_in_dashboard  = Column(Boolean, default=True)
    show_in_timeline   = Column(Boolean, default=True)
    alert_direction    = Column(String, default="both")  # high / low / both / none
    decimal_places     = Column(Integer, default=1)
    
    created_at   = Column(DateTime, default=datetime.utcnow)
    created_by   = Column(String)

    values = relationship("VariableValue", back_populates="variable",
                          cascade="all, delete-orphan")


class VariableValue(Base):
    """
    A single monthly data point for a user-defined variable.
    One row per patient per month per variable.
    """
    __tablename__ = "variable_values"
    __table_args__ = (
        UniqueConstraint("patient_id", "record_month", "variable_id",
                         name="uq_patient_month_variable"),
    )

    id           = Column(Integer, primary_key=True, index=True)
    patient_id   = Column(Integer, ForeignKey("patients.id"), nullable=False)
    record_month = Column(String, nullable=False)   # YYYY-MM
    variable_id  = Column(Integer, ForeignKey("variable_definitions.id"), nullable=False)
    value_num    = Column(Float)    # for number/integer types
    value_text   = Column(String)   # for text/boolean types
    entered_by   = Column(String)
    entered_at   = Column(DateTime, default=datetime.utcnow)

    variable = relationship("VariableDefinition", back_populates="values")


# ── PRESET VARIABLES ─────────────────────────────────────────────────────────
# These are seeded on first run — user can add more through the UI

PRESET_VARIABLES = [
    {
        "name": "crp",
        "display_name": "C-Reactive Protein",
        "unit": "mg/L",
        "category": "Lab",
        "data_type": "number",
        "threshold_high": 10.0,
        "target_high": 5.0,
        "alert_direction": "high",
        "decimal_places": 1,
        "description": "Marker of inflammation. High CRP explains EPO hypo-response and albumin decline.",
        "show_in_dashboard": True,
    },
    {
        "name": "blood_transfusion_units",
        "display_name": "Blood Transfusion",
        "unit": "units/month",
        "category": "Clinical",
        "data_type": "integer",
        "threshold_high": 0,
        "alert_direction": "high",
        "decimal_places": 0,
        "description": "Number of packed red cell units transfused this month.",
        "show_in_dashboard": True,
    },
    {
        "name": "kt_v",
        "display_name": "Kt/V",
        "unit": "",
        "category": "Adequacy",
        "data_type": "number",
        "threshold_low": 1.2,
        "target_low": 1.2,
        "target_high": 1.8,
        "alert_direction": "low",
        "decimal_places": 2,
        "description": "Dialysis adequacy index. KDIGO target ≥ 1.2.",
        "show_in_dashboard": True,
    },
    {
        "name": "bicarbonate",
        "display_name": "Serum Bicarbonate",
        "unit": "mmol/L",
        "category": "Lab",
        "data_type": "number",
        "threshold_low": 22.0,
        "target_low": 22.0,
        "target_high": 26.0,
        "alert_direction": "low",
        "decimal_places": 1,
        "description": "Pre-dialysis serum bicarbonate. Target 22-26 mmol/L.",
        "show_in_dashboard": False,
    },
    {
        "name": "systolic_bp_pre",
        "display_name": "Pre-dialysis SBP",
        "unit": "mmHg",
        "category": "Vitals",
        "data_type": "integer",
        "threshold_high": 160.0,
        "threshold_low": 90.0,
        "alert_direction": "both",
        "decimal_places": 0,
        "description": "Average pre-dialysis systolic blood pressure this month.",
        "show_in_dashboard": False,
    },
    {
        "name": "intradialytic_hypotension",
        "display_name": "Intradialytic Hypotension",
        "unit": "episodes/month",
        "category": "Clinical",
        "data_type": "integer",
        "threshold_high": 2,
        "alert_direction": "high",
        "decimal_places": 0,
        "description": "Number of IDH episodes requiring intervention this month.",
        "show_in_dashboard": True,
    },
    {
        "name": "uric_acid",
        "display_name": "Uric Acid",
        "unit": "mg/dL",
        "category": "Lab",
        "data_type": "number",
        "threshold_high": 8.0,
        "alert_direction": "high",
        "decimal_places": 1,
        "description": "Serum uric acid.",
        "show_in_dashboard": False,
    },
    {
        "name": "npcr_dynamic",
        "display_name": "nPCR",
        "unit": "g/kg/day",
        "category": "Nutrition",
        "data_type": "number",
        "decimal_places": 2,
        "description": "Normalized Protein Catabolic Rate.",
    },
    {
        "name": "handgrip_strength",
        "display_name": "Handgrip Strength",
        "unit": "kg",
        "category": "Nutrition",
        "data_type": "number",
        "decimal_places": 1,
        "description": "Assessment of muscle strength and nutritional status.",
    },
    {
        "name": "crbsi",
        "display_name": "CRBSI",
        "unit": "episodes/quarter",
        "category": "Infection",
        "data_type": "integer",
        "threshold_high": 0.0,
        "alert_direction": "high",
        "decimal_places": 0,
        "description": "Catheter-Related Blood Stream Infections.",
    },
    {
        "name": "access_thrombosis",
        "display_name": "Access Thrombosis",
        "unit": "count/month",
        "category": "Safety",
        "data_type": "integer",
        "threshold_high": 0.0,
        "alert_direction": "high",
        "decimal_places": 0,
        "description": "AVF / AVG Thrombosis Episodes.",
    },
    {
        "name": "facit_fatigue",
        "display_name": "FACIT Fatigue Score",
        "unit": "0-52",
        "category": "Quality of Life",
        "data_type": "number",
        "threshold_low": 30.0,
        "alert_direction": "low",
        "decimal_places": 0,
        "description": "Fatigue Assessment of Chronic Illness Therapy.",
    },
    {
        "name": "psqi_sleep",
        "display_name": "PSQI Sleep Quality",
        "unit": "0-21",
        "category": "Quality of Life",
        "data_type": "number",
        "threshold_high": 5.0,
        "alert_direction": "high",
        "decimal_places": 0,
        "description": "Pittsburgh Sleep Quality Index.",
    },
    {
        "name": "phq9_depression",
        "display_name": "PHQ-9 Depression Score",
        "unit": "0-27",
        "category": "Quality of Life",
        "data_type": "number",
        "threshold_high": 9.0,
        "alert_direction": "high",
        "decimal_places": 0,
        "description": "Patient Health Questionnaire-9.",
    },
    {
        "name": "rls_severity",
        "display_name": "RLS Severity",
        "unit": "0-40",
        "category": "Quality of Life",
        "data_type": "number",
        "threshold_high": 10.0,
        "alert_direction": "high",
        "decimal_places": 0,
        "description": "Restless Legs Syndrome Severity.",
    },
    {
        "name": "karnofsky_status",
        "display_name": "Karnofsky Status",
        "unit": "0-100",
        "category": "Quality of Life",
        "data_type": "number",
        "threshold_low": 60.0,
        "alert_direction": "low",
        "decimal_places": 0,
        "description": "Functional Status assessment.",
    },
    {
        "name": "mis_score_dynamic",
        "display_name": "MIS Score",
        "unit": "score",
        "category": "Nutrition",
        "data_type": "number",
        "threshold_high": 5.0,
        "alert_direction": "high",
        "decimal_places": 0,
        "description": "Malnutrition-Inflammation Score.",
    },
    {
        "name": "eri",
        "display_name": "ESA Resistance Index (ERI)",
        "unit": "IU/kg/week/g/dL",
        "category": "Anemia",
        "data_type": "number",
        "threshold_high": 10.0,
        "alert_direction": "high",
        "decimal_places": 1,
        "description": "Erythropoiesis-Stimulating Agent Resistance Index.",
    },
]


def seed_preset_variables(db):
    """Seed preset variables on first run if they don't exist."""
    from database import SessionLocal
    for vdef in PRESET_VARIABLES:
        existing = db.query(VariableDefinition).filter(
            VariableDefinition.name == vdef["name"]
        ).first()
        if not existing:
            db.add(VariableDefinition(**vdef, created_by="system"))
    db.commit()


# ── QUERY HELPERS ─────────────────────────────────────────────────────────────

def get_all_variables(db, active_only=True):
    q = db.query(VariableDefinition)
    if active_only:
        q = q.filter(VariableDefinition.is_active == True)
    return q.order_by(VariableDefinition.category, VariableDefinition.display_name).all()


def get_patient_variable_history(db, patient_id: int, variable_id: int) -> list:
    """Get all monthly values for one patient, one variable, sorted by month."""
    rows = (
        db.query(VariableValue)
        .filter(
            VariableValue.patient_id == patient_id,
            VariableValue.variable_id == variable_id,
        )
        .order_by(VariableValue.record_month.asc())
        .all()
    )
    return [{"month": r.record_month, "value": r.value_num, "text": r.value_text}
            for r in rows]


def get_patient_all_dynamic_values(db, patient_id: int, month_str: str) -> dict:
    """Get all dynamic variable values for a patient in a given month."""
    rows = (
        db.query(VariableValue, VariableDefinition)
        .join(VariableDefinition)
        .filter(
            VariableValue.patient_id == patient_id,
            VariableValue.record_month == month_str,
        )
        .all()
    )
    return {
        row.VariableDefinition.name: {
            "value": row.VariableValue.value_num,
            "text": row.VariableValue.value_text,
            "display_name": row.VariableDefinition.display_name,
            "unit": row.VariableDefinition.unit,
        }
        for row in rows
    }


def upsert_variable_value(db, patient_id: int, month_str: str,
                           variable_id: int, value_num=None,
                           value_text=None, entered_by=""):
    """Insert or update a single variable value."""
    existing = db.query(VariableValue).filter(
        VariableValue.patient_id == patient_id,
        VariableValue.record_month == month_str,
        VariableValue.variable_id == variable_id,
    ).first()

    if existing:
        existing.value_num  = value_num
        existing.value_text = value_text
        existing.entered_by = entered_by
        existing.entered_at = datetime.utcnow()
    else:
        db.add(VariableValue(
            patient_id=patient_id,
            record_month=month_str,
            variable_id=variable_id,
            value_num=value_num,
            value_text=value_text,
            entered_by=entered_by,
        ))
    db.commit()
