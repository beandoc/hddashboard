# Import all models so they register with Base.metadata before create_all is called.
# Order: patient first (other models reference it via FK), then dependents.

from db.models.patient import (
    PatientCredentials,
    PatientComorbidities,
    PatientRenalProfile,
    PatientViralMarkers,
    PatientVaccination,
    PatientVascularAccess,
    PatientCardiac,
    PatientOutcomes,
    Patient,
)
from db.models.auth import User
from db.models.records import MonthlyRecord, SustainabilityRecord, DryWeightAssessment
from db.models.sessions import SessionRecord, InterimLabRecord, AlertLog
from db.models.clinical import (
    PatientReminder,
    ClinicalEvent,
    PatientSymptomReport,
    HospitalisationEvent,
    AccessEpisode,
    AccessEvent,
    AccessSurveillanceRecord,
    AccessAlertOverride,
)
from db.models.nutrition import PatientMealRecord, FoodDatabaseItem
from db.models.research import ResearchProject, ResearchRecord
from db.models.ml import (
    AuditLog,
    MLPrediction,
    MLModelMetrics,
    ModelArtifact,
    ClinicalOverrideLog,
    PatientFeatureSnapshot,
    ACMRecommendation,
    TwinSimulation,
    DiaSenseCalibration,
)

__all__ = [
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
    "AccessEpisode",
    "AccessEvent",
    "AccessSurveillanceRecord",
    "AccessAlertOverride",
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
    "ACMRecommendation",
    "TwinSimulation",
    "DiaSenseCalibration",
]

