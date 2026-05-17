# Thin re-export shim — all existing `from database import X` statements continue to work.
# The implementation has been split into the db/ package:
#   db/engine.py      — Base, engines, sessions, get_db, get_async_db
#   db/security.py    — compute_patient_id_hash
#   db/utils.py       — to_dict
#   db/migrations.py  — create_tables
#   db/models/        — all SQLAlchemy model classes

from db.engine import (
    Base,
    DATABASE_URL,
    engine,
    SessionLocal,
    async_engine,
    AsyncSessionLocal,
    get_db,
    get_async_db,
    set_tenant_context,
    _is_sqlite,
)

from db.security import compute_patient_id_hash, _audit_hmac_key

from db.utils import to_dict

from db.migrations import create_tables

from db.models import (
    Patient,
    PatientCredentials,
    PatientComorbidities,
    PatientRenalProfile,
    PatientViralMarkers,
    PatientVaccination,
    PatientVascularAccess,
    PatientCardiac,
    PatientOutcomes,
    User,
    MonthlyRecord,
    SustainabilityRecord,
    DryWeightAssessment,
    SessionRecord,
    InterimLabRecord,
    AlertLog,
    PatientReminder,
    ClinicalEvent,
    PatientSymptomReport,
    HospitalisationEvent,
    PatientMealRecord,
    FoodDatabaseItem,
    ResearchProject,
    ResearchRecord,
    AuditLog,
    MLPrediction,
    MLModelMetrics,
    ModelArtifact,
    ClinicalOverrideLog,
    PatientFeatureSnapshot,
)

__all__ = [
    "Base",
    "DATABASE_URL",
    "engine",
    "SessionLocal",
    "async_engine",
    "AsyncSessionLocal",
    "get_db",
    "get_async_db",
    "set_tenant_context",
    "_is_sqlite",
    "compute_patient_id_hash",
    "_audit_hmac_key",
    "to_dict",
    "create_tables",
    "Patient",
    "PatientCredentials",
    "PatientComorbidities",
    "PatientRenalProfile",
    "PatientViralMarkers",
    "PatientVaccination",
    "PatientVascularAccess",
    "PatientCardiac",
    "PatientOutcomes",
    "User",
    "MonthlyRecord",
    "SustainabilityRecord",
    "DryWeightAssessment",
    "SessionRecord",
    "InterimLabRecord",
    "AlertLog",
    "PatientReminder",
    "ClinicalEvent",
    "PatientSymptomReport",
    "HospitalisationEvent",
    "PatientMealRecord",
    "FoodDatabaseItem",
    "ResearchProject",
    "ResearchRecord",
    "AuditLog",
    "MLPrediction",
    "MLModelMetrics",
    "ModelArtifact",
    "ClinicalOverrideLog",
    "PatientFeatureSnapshot",
]
