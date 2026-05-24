from sqlalchemy import (
    Column, Integer, String, Float, Boolean, Date, DateTime, Text,
    ForeignKey, Index, UniqueConstraint, select,
)
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import relationship
from datetime import datetime

from db.engine import Base


class PatientCredentials(Base):
    """Patient portal auth — all credential fields live here, not on patients.

    login_username is the indexed lookup key for patient-portal auth.  Keeping
    it here (rather than on patients) means clinical reads never load credentials.
    reset_token is a URL-safe random token; token_expires is its UTC deadline.
    """
    __tablename__ = "patient_credentials"

    patient_id      = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), primary_key=True)
    login_username  = Column(String, unique=True, index=True, nullable=True)
    hashed_password = Column(String)
    reset_token     = Column(String, nullable=True, index=True)
    token_expires   = Column(DateTime, nullable=True)


class PatientComorbidities(Base):
    """Structured comorbidity profile + Charlson index.  Updated on every CRUD edit."""
    __tablename__ = "patient_comorbidities"

    patient_id                = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), primary_key=True)
    dm_status                 = Column(String)
    dm_end_organ_damage       = Column(Boolean)
    htn_status                = Column(Boolean)
    cad_status                = Column(Boolean)
    chf_status                = Column(Boolean)
    history_of_stroke         = Column(Boolean)
    history_of_pvd            = Column(Boolean)
    history_of_dementia       = Column(Boolean)
    history_of_cpd            = Column(Boolean)
    history_of_ctd            = Column(Boolean)
    history_of_pud            = Column(Boolean)
    liver_disease             = Column(String)
    hemiplegia                = Column(Boolean)
    solid_tumor               = Column(String)
    leukemia                  = Column(Boolean)
    lymphoma                  = Column(Boolean)
    smoking_status            = Column(String)
    alcohol_consumption       = Column(String)
    charlson_comorbidity_index = Column(Integer)
    comorbidities             = Column(Text)
    drug_allergies            = Column(String)
    clinical_background       = Column(Text)


class PatientRenalProfile(Base):
    """Primary renal diagnosis, KRT history, and KRCRw baseline parameters."""
    __tablename__ = "patient_renal_profile"

    patient_id                   = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), primary_key=True)
    primary_renal_disease        = Column(String)
    native_kidney_disease        = Column(String)
    date_esrd_diagnosis          = Column(Date)
    native_kidney_biopsy         = Column(String)
    native_kidney_biopsy_date    = Column(Date)
    native_kidney_biopsy_report  = Column(Text)
    dialysis_modality            = Column(String)
    previous_dialysis_modality   = Column(String)
    previous_krt_modality        = Column(String)
    history_of_renal_transplant  = Column(Boolean)
    transplant_prospect          = Column(String)
    baseline_gcr                 = Column(Float)
    baseline_vdcr                = Column(Float)
    is_black                     = Column(Boolean, default=False)


class PatientViralMarkers(Base):
    """HBsAg, Anti-HCV, HIV serology — accessed by infection-control workflows."""
    __tablename__ = "patient_viral_markers"

    patient_id    = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), primary_key=True)
    viral_markers = Column(String)
    viral_hbsag   = Column(String)
    viral_anti_hcv = Column(String)
    viral_hiv     = Column(String)


class PatientVaccination(Base):
    """Vaccination schedule and completion dates."""
    __tablename__ = "patient_vaccination"

    patient_id        = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), primary_key=True)
    hep_b_status      = Column(String)
    hep_b_dose1_date  = Column(Date)
    hep_b_dose2_date  = Column(Date)
    hep_b_dose3_date  = Column(Date)
    hep_b_dose4_date  = Column(Date)
    hep_b_titer_date  = Column(Date)
    pcv13_date        = Column(Date)
    ppsv23_date       = Column(Date)
    hz_dose1_date     = Column(Date)
    hz_dose2_date     = Column(Date)
    influenza_date    = Column(Date)


class PatientVascularAccess(Base):
    """Patient-level (semi-static) vascular access record.  Per-session data is in SessionRecord."""
    __tablename__ = "patient_vascular_access"

    patient_id                    = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), primary_key=True)
    access_type                   = Column(String)
    access_date                   = Column(Date)
    date_first_cannulation        = Column(Date)
    history_of_access_thrombosis  = Column(Boolean)
    access_intervention_history   = Column(Text)
    catheter_type                 = Column(String)
    catheter_insertion_site       = Column(String)


class PatientCardiac(Base):
    """Echocardiographic parameters and functional capacity markers."""
    __tablename__ = "patient_cardiac"

    patient_id           = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), primary_key=True)
    ejection_fraction    = Column(Float, default=60.0)
    diastolic_dysfunction = Column(String)
    handgrip_strength    = Column(Float)
    echo_date            = Column(Date)
    echo_report          = Column(Text)


class PatientOutcomes(Base):
    """Survival status, death, transplant, withdrawal, and transfer — updated by deactivation flow."""
    __tablename__ = "patient_outcomes"

    patient_id               = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), primary_key=True)
    current_survival_status  = Column(String)
    date_of_death            = Column(Date)
    primary_cause_of_death   = Column(String)
    date_of_transplant       = Column(Date)
    withdrawal_from_dialysis = Column(Boolean)
    withdrawal_date          = Column(Date)
    withdrawal_reason        = Column(String)
    withdrawal_clinician     = Column(String)
    date_facility_transfer   = Column(Date)


# ─────────────────────────────────────────────────────────────────────────────
# PATIENT  (core identity + scheduling only — ~30 columns)
# ─────────────────────────────────────────────────────────────────────────────

class Patient(Base):
    __tablename__ = "patients"

    id       = Column(Integer, primary_key=True, index=True)
    hid_no   = Column(String, unique=True, index=True, nullable=False)
    name     = Column(String, nullable=False)
    relation      = Column(String)
    relation_type = Column(String)
    sex           = Column(String)
    contact_no    = Column(String)
    email         = Column(String)
    diagnosis     = Column(String)
    hd_wef_date   = Column(Date)

    education_level    = Column(String)
    height             = Column(Float)
    blood_group        = Column(String)
    age                = Column(Integer)
    dry_weight         = Column(Float)
    healthcare_facility = Column(String)

    hd_frequency = Column(Integer, default=2)
    hd_day_1     = Column(String)
    hd_day_2     = Column(String)
    hd_day_3     = Column(String)
    hd_slot_1    = Column(String)
    hd_slot_2    = Column(String)
    hd_slot_3    = Column(String)

    whatsapp_link   = Column(String)
    whatsapp_notify = Column(Boolean, default=True)
    mail_trigger    = Column(Boolean, default=False)
    is_active       = Column(Boolean, default=True)
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # ── 1:1 satellite relationships ──────────────────────────────────────────
    credentials    = relationship("PatientCredentials",  uselist=False, cascade="all, delete-orphan")
    comorbidity_profile = relationship("PatientComorbidities", uselist=False, cascade="all, delete-orphan")
    renal_profile  = relationship("PatientRenalProfile",  uselist=False, cascade="all, delete-orphan")
    viral_markers_ = relationship("PatientViralMarkers",  uselist=False, cascade="all, delete-orphan")
    vaccination    = relationship("PatientVaccination",   uselist=False, cascade="all, delete-orphan")
    vascular_access = relationship("PatientVascularAccess", uselist=False, cascade="all, delete-orphan")
    cardiac        = relationship("PatientCardiac",       uselist=False, cascade="all, delete-orphan")
    outcomes       = relationship("PatientOutcomes",      uselist=False, cascade="all, delete-orphan")

    # ── 1:many relationships ─────────────────────────────────────────────────
    records              = relationship("MonthlyRecord",         back_populates="patient", cascade="all, delete-orphan")
    sessions             = relationship("SessionRecord",         back_populates="patient", cascade="all, delete-orphan")
    interim_labs         = relationship("InterimLabRecord",      back_populates="patient", cascade="all, delete-orphan")
    meal_records         = relationship("PatientMealRecord",     back_populates="patient", cascade="all, delete-orphan")
    symptom_reports      = relationship("PatientSymptomReport",  back_populates="patient", cascade="all, delete-orphan")
    reminders            = relationship("PatientReminder",       back_populates="patient", cascade="all, delete-orphan")
    dry_weight_assessments = relationship("DryWeightAssessment", back_populates="patient", cascade="all, delete-orphan")
    events               = relationship("ClinicalEvent",         back_populates="patient", cascade="all, delete-orphan")
    research_records     = relationship("ResearchRecord",        back_populates="patient")
    hospitalisations     = relationship("HospitalisationEvent",  back_populates="patient", cascade="all, delete-orphan")
    access_episodes      = relationship("AccessEpisode",          back_populates="patient", cascade="all, delete-orphan")
    access_events        = relationship("AccessEvent",            back_populates="patient", cascade="all, delete-orphan")
    surveillance_records = relationship("AccessSurveillanceRecord", back_populates="patient", cascade="all, delete-orphan")
    access_alert_overrides = relationship("AccessAlertOverride",  back_populates="patient", cascade="all, delete-orphan")

    # ── Backward-compatible property proxies ─────────────────────────────────

    # credentials
    @hybrid_property
    def login_username(self):
        return self.credentials.login_username if self.credentials else None

    @login_username.setter
    def login_username(self, value):
        if self.credentials is None:
            self.credentials = PatientCredentials(login_username=value)
        else:
            self.credentials.login_username = value

    @login_username.expression
    def login_username(cls):
        return (
            select(PatientCredentials.login_username)
            .where(PatientCredentials.patient_id == cls.id)
            .correlate(cls)
            .scalar_subquery()
        )

    @property
    def hashed_password(self):
        return self.credentials.hashed_password if self.credentials else None

    @hashed_password.setter
    def hashed_password(self, value):
        if self.credentials is None:
            self.credentials = PatientCredentials(hashed_password=value)
        else:
            self.credentials.hashed_password = value

    # comorbidities
    def _ensure_comorbidities(self):
        if self.comorbidity_profile is None:
            self.comorbidity_profile = PatientComorbidities()
        return self.comorbidity_profile

    @property
    def dm_status(self):
        return self.comorbidity_profile.dm_status if self.comorbidity_profile else None

    @dm_status.setter
    def dm_status(self, v):
        self._ensure_comorbidities().dm_status = v

    @property
    def dm_end_organ_damage(self):
        return self.comorbidity_profile.dm_end_organ_damage if self.comorbidity_profile else None

    @dm_end_organ_damage.setter
    def dm_end_organ_damage(self, v):
        self._ensure_comorbidities().dm_end_organ_damage = v

    @property
    def htn_status(self):
        return self.comorbidity_profile.htn_status if self.comorbidity_profile else None

    @htn_status.setter
    def htn_status(self, v):
        self._ensure_comorbidities().htn_status = v

    @property
    def cad_status(self):
        return self.comorbidity_profile.cad_status if self.comorbidity_profile else None

    @cad_status.setter
    def cad_status(self, v):
        self._ensure_comorbidities().cad_status = v

    @property
    def chf_status(self):
        return self.comorbidity_profile.chf_status if self.comorbidity_profile else None

    @chf_status.setter
    def chf_status(self, v):
        self._ensure_comorbidities().chf_status = v

    @property
    def history_of_stroke(self):
        return self.comorbidity_profile.history_of_stroke if self.comorbidity_profile else None

    @history_of_stroke.setter
    def history_of_stroke(self, v):
        self._ensure_comorbidities().history_of_stroke = v

    @property
    def history_of_pvd(self):
        return self.comorbidity_profile.history_of_pvd if self.comorbidity_profile else None

    @history_of_pvd.setter
    def history_of_pvd(self, v):
        self._ensure_comorbidities().history_of_pvd = v

    @property
    def history_of_dementia(self):
        return self.comorbidity_profile.history_of_dementia if self.comorbidity_profile else None

    @history_of_dementia.setter
    def history_of_dementia(self, v):
        self._ensure_comorbidities().history_of_dementia = v

    @property
    def history_of_cpd(self):
        return self.comorbidity_profile.history_of_cpd if self.comorbidity_profile else None

    @history_of_cpd.setter
    def history_of_cpd(self, v):
        self._ensure_comorbidities().history_of_cpd = v

    @property
    def history_of_ctd(self):
        return self.comorbidity_profile.history_of_ctd if self.comorbidity_profile else None

    @history_of_ctd.setter
    def history_of_ctd(self, v):
        self._ensure_comorbidities().history_of_ctd = v

    @property
    def history_of_pud(self):
        return self.comorbidity_profile.history_of_pud if self.comorbidity_profile else None

    @history_of_pud.setter
    def history_of_pud(self, v):
        self._ensure_comorbidities().history_of_pud = v

    @property
    def liver_disease(self):
        return self.comorbidity_profile.liver_disease if self.comorbidity_profile else None

    @liver_disease.setter
    def liver_disease(self, v):
        self._ensure_comorbidities().liver_disease = v

    @property
    def hemiplegia(self):
        return self.comorbidity_profile.hemiplegia if self.comorbidity_profile else None

    @hemiplegia.setter
    def hemiplegia(self, v):
        self._ensure_comorbidities().hemiplegia = v

    @property
    def solid_tumor(self):
        return self.comorbidity_profile.solid_tumor if self.comorbidity_profile else None

    @solid_tumor.setter
    def solid_tumor(self, v):
        self._ensure_comorbidities().solid_tumor = v

    @property
    def leukemia(self):
        return self.comorbidity_profile.leukemia if self.comorbidity_profile else None

    @leukemia.setter
    def leukemia(self, v):
        self._ensure_comorbidities().leukemia = v

    @property
    def lymphoma(self):
        return self.comorbidity_profile.lymphoma if self.comorbidity_profile else None

    @lymphoma.setter
    def lymphoma(self, v):
        self._ensure_comorbidities().lymphoma = v

    @property
    def smoking_status(self):
        return self.comorbidity_profile.smoking_status if self.comorbidity_profile else None

    @smoking_status.setter
    def smoking_status(self, v):
        self._ensure_comorbidities().smoking_status = v

    @property
    def alcohol_consumption(self):
        return self.comorbidity_profile.alcohol_consumption if self.comorbidity_profile else None

    @alcohol_consumption.setter
    def alcohol_consumption(self, v):
        self._ensure_comorbidities().alcohol_consumption = v

    @property
    def charlson_comorbidity_index(self):
        return self.comorbidity_profile.charlson_comorbidity_index if self.comorbidity_profile else None

    @charlson_comorbidity_index.setter
    def charlson_comorbidity_index(self, v):
        self._ensure_comorbidities().charlson_comorbidity_index = v

    @property
    def comorbidities(self):
        return self.comorbidity_profile.comorbidities if self.comorbidity_profile else None

    @comorbidities.setter
    def comorbidities(self, v):
        self._ensure_comorbidities().comorbidities = v

    @property
    def drug_allergies(self):
        return self.comorbidity_profile.drug_allergies if self.comorbidity_profile else None

    @drug_allergies.setter
    def drug_allergies(self, v):
        self._ensure_comorbidities().drug_allergies = v

    @property
    def clinical_background(self):
        return self.comorbidity_profile.clinical_background if self.comorbidity_profile else None

    @clinical_background.setter
    def clinical_background(self, v):
        self._ensure_comorbidities().clinical_background = v

    # renal profile
    def _ensure_renal_profile(self):
        if self.renal_profile is None:
            self.renal_profile = PatientRenalProfile()
        return self.renal_profile

    @property
    def primary_renal_disease(self):
        return self.renal_profile.primary_renal_disease if self.renal_profile else None

    @primary_renal_disease.setter
    def primary_renal_disease(self, v):
        self._ensure_renal_profile().primary_renal_disease = v

    @property
    def native_kidney_disease(self):
        return self.renal_profile.native_kidney_disease if self.renal_profile else None

    @native_kidney_disease.setter
    def native_kidney_disease(self, v):
        self._ensure_renal_profile().native_kidney_disease = v

    @property
    def date_esrd_diagnosis(self):
        return self.renal_profile.date_esrd_diagnosis if self.renal_profile else None

    @date_esrd_diagnosis.setter
    def date_esrd_diagnosis(self, v):
        self._ensure_renal_profile().date_esrd_diagnosis = v

    @property
    def native_kidney_biopsy(self):
        return self.renal_profile.native_kidney_biopsy if self.renal_profile else None

    @native_kidney_biopsy.setter
    def native_kidney_biopsy(self, v):
        self._ensure_renal_profile().native_kidney_biopsy = v

    @property
    def native_kidney_biopsy_date(self):
        return self.renal_profile.native_kidney_biopsy_date if self.renal_profile else None

    @native_kidney_biopsy_date.setter
    def native_kidney_biopsy_date(self, v):
        self._ensure_renal_profile().native_kidney_biopsy_date = v

    @property
    def native_kidney_biopsy_report(self):
        return self.renal_profile.native_kidney_biopsy_report if self.renal_profile else None

    @native_kidney_biopsy_report.setter
    def native_kidney_biopsy_report(self, v):
        self._ensure_renal_profile().native_kidney_biopsy_report = v

    @property
    def dialysis_modality(self):
        return self.renal_profile.dialysis_modality if self.renal_profile else None

    @dialysis_modality.setter
    def dialysis_modality(self, v):
        self._ensure_renal_profile().dialysis_modality = v

    @property
    def previous_dialysis_modality(self):
        return self.renal_profile.previous_dialysis_modality if self.renal_profile else None

    @previous_dialysis_modality.setter
    def previous_dialysis_modality(self, v):
        self._ensure_renal_profile().previous_dialysis_modality = v

    @property
    def previous_krt_modality(self):
        return self.renal_profile.previous_krt_modality if self.renal_profile else None

    @previous_krt_modality.setter
    def previous_krt_modality(self, v):
        self._ensure_renal_profile().previous_krt_modality = v

    @property
    def history_of_renal_transplant(self):
        return self.renal_profile.history_of_renal_transplant if self.renal_profile else None

    @history_of_renal_transplant.setter
    def history_of_renal_transplant(self, v):
        self._ensure_renal_profile().history_of_renal_transplant = v

    @property
    def transplant_prospect(self):
        return self.renal_profile.transplant_prospect if self.renal_profile else None

    @transplant_prospect.setter
    def transplant_prospect(self, v):
        self._ensure_renal_profile().transplant_prospect = v

    @property
    def baseline_gcr(self):
        return self.renal_profile.baseline_gcr if self.renal_profile else None

    @baseline_gcr.setter
    def baseline_gcr(self, v):
        self._ensure_renal_profile().baseline_gcr = v

    @property
    def baseline_vdcr(self):
        return self.renal_profile.baseline_vdcr if self.renal_profile else None

    @baseline_vdcr.setter
    def baseline_vdcr(self, v):
        self._ensure_renal_profile().baseline_vdcr = v

    @property
    def is_black(self):
        return self.renal_profile.is_black if self.renal_profile else False

    @is_black.setter
    def is_black(self, v):
        self._ensure_renal_profile().is_black = v

    # viral markers
    def _ensure_viral(self):
        if self.viral_markers_ is None:
            self.viral_markers_ = PatientViralMarkers()
        return self.viral_markers_

    @property
    def viral_markers(self):
        return self.viral_markers_.viral_markers if self.viral_markers_ else None

    @viral_markers.setter
    def viral_markers(self, v):
        self._ensure_viral().viral_markers = v

    @property
    def viral_hbsag(self):
        return self.viral_markers_.viral_hbsag if self.viral_markers_ else None

    @viral_hbsag.setter
    def viral_hbsag(self, v):
        self._ensure_viral().viral_hbsag = v

    @property
    def viral_anti_hcv(self):
        return self.viral_markers_.viral_anti_hcv if self.viral_markers_ else None

    @viral_anti_hcv.setter
    def viral_anti_hcv(self, v):
        self._ensure_viral().viral_anti_hcv = v

    @property
    def viral_hiv(self):
        return self.viral_markers_.viral_hiv if self.viral_markers_ else None

    @viral_hiv.setter
    def viral_hiv(self, v):
        self._ensure_viral().viral_hiv = v

    # vaccination
    def _ensure_vaccination(self):
        if self.vaccination is None:
            self.vaccination = PatientVaccination()
        return self.vaccination

    @property
    def hep_b_status(self):
        return self.vaccination.hep_b_status if self.vaccination else None

    @hep_b_status.setter
    def hep_b_status(self, v):
        self._ensure_vaccination().hep_b_status = v

    @property
    def hep_b_dose1_date(self):
        return self.vaccination.hep_b_dose1_date if self.vaccination else None

    @hep_b_dose1_date.setter
    def hep_b_dose1_date(self, v):
        self._ensure_vaccination().hep_b_dose1_date = v

    @property
    def hep_b_dose2_date(self):
        return self.vaccination.hep_b_dose2_date if self.vaccination else None

    @hep_b_dose2_date.setter
    def hep_b_dose2_date(self, v):
        self._ensure_vaccination().hep_b_dose2_date = v

    @property
    def hep_b_dose3_date(self):
        return self.vaccination.hep_b_dose3_date if self.vaccination else None

    @hep_b_dose3_date.setter
    def hep_b_dose3_date(self, v):
        self._ensure_vaccination().hep_b_dose3_date = v

    @property
    def hep_b_dose4_date(self):
        return self.vaccination.hep_b_dose4_date if self.vaccination else None

    @hep_b_dose4_date.setter
    def hep_b_dose4_date(self, v):
        self._ensure_vaccination().hep_b_dose4_date = v

    @property
    def hep_b_titer_date(self):
        return self.vaccination.hep_b_titer_date if self.vaccination else None

    @hep_b_titer_date.setter
    def hep_b_titer_date(self, v):
        self._ensure_vaccination().hep_b_titer_date = v

    @property
    def pcv13_date(self):
        return self.vaccination.pcv13_date if self.vaccination else None

    @pcv13_date.setter
    def pcv13_date(self, v):
        self._ensure_vaccination().pcv13_date = v

    @property
    def ppsv23_date(self):
        return self.vaccination.ppsv23_date if self.vaccination else None

    @ppsv23_date.setter
    def ppsv23_date(self, v):
        self._ensure_vaccination().ppsv23_date = v

    @property
    def hz_dose1_date(self):
        return self.vaccination.hz_dose1_date if self.vaccination else None

    @hz_dose1_date.setter
    def hz_dose1_date(self, v):
        self._ensure_vaccination().hz_dose1_date = v

    @property
    def hz_dose2_date(self):
        return self.vaccination.hz_dose2_date if self.vaccination else None

    @hz_dose2_date.setter
    def hz_dose2_date(self, v):
        self._ensure_vaccination().hz_dose2_date = v

    @property
    def influenza_date(self):
        return self.vaccination.influenza_date if self.vaccination else None

    @influenza_date.setter
    def influenza_date(self, v):
        self._ensure_vaccination().influenza_date = v

    # vascular access
    def _ensure_vascular(self):
        if self.vascular_access is None:
            self.vascular_access = PatientVascularAccess()
        return self.vascular_access

    @property
    def access_type(self):
        return self.vascular_access.access_type if self.vascular_access else None

    @access_type.setter
    def access_type(self, v):
        self._ensure_vascular().access_type = v

    @property
    def access_date(self):
        return self.vascular_access.access_date if self.vascular_access else None

    @access_date.setter
    def access_date(self, v):
        self._ensure_vascular().access_date = v

    @property
    def date_first_cannulation(self):
        return self.vascular_access.date_first_cannulation if self.vascular_access else None

    @date_first_cannulation.setter
    def date_first_cannulation(self, v):
        self._ensure_vascular().date_first_cannulation = v

    @property
    def history_of_access_thrombosis(self):
        return self.vascular_access.history_of_access_thrombosis if self.vascular_access else None

    @history_of_access_thrombosis.setter
    def history_of_access_thrombosis(self, v):
        self._ensure_vascular().history_of_access_thrombosis = v

    @property
    def access_intervention_history(self):
        return self.vascular_access.access_intervention_history if self.vascular_access else None

    @access_intervention_history.setter
    def access_intervention_history(self, v):
        self._ensure_vascular().access_intervention_history = v

    @property
    def catheter_type(self):
        return self.vascular_access.catheter_type if self.vascular_access else None

    @catheter_type.setter
    def catheter_type(self, v):
        self._ensure_vascular().catheter_type = v

    @property
    def catheter_insertion_site(self):
        return self.vascular_access.catheter_insertion_site if self.vascular_access else None

    @catheter_insertion_site.setter
    def catheter_insertion_site(self, v):
        self._ensure_vascular().catheter_insertion_site = v

    # cardiac
    def _ensure_cardiac(self):
        if self.cardiac is None:
            self.cardiac = PatientCardiac()
        return self.cardiac

    @property
    def ejection_fraction(self):
        return self.cardiac.ejection_fraction if self.cardiac else 60.0

    @ejection_fraction.setter
    def ejection_fraction(self, v):
        self._ensure_cardiac().ejection_fraction = v

    @property
    def diastolic_dysfunction(self):
        return self.cardiac.diastolic_dysfunction if self.cardiac else None

    @diastolic_dysfunction.setter
    def diastolic_dysfunction(self, v):
        self._ensure_cardiac().diastolic_dysfunction = v

    @property
    def handgrip_strength(self):
        return self.cardiac.handgrip_strength if self.cardiac else None

    @handgrip_strength.setter
    def handgrip_strength(self, v):
        self._ensure_cardiac().handgrip_strength = v

    @property
    def echo_date(self):
        return self.cardiac.echo_date if self.cardiac else None

    @echo_date.setter
    def echo_date(self, v):
        self._ensure_cardiac().echo_date = v

    @property
    def echo_report(self):
        return self.cardiac.echo_report if self.cardiac else None

    @echo_report.setter
    def echo_report(self, v):
        self._ensure_cardiac().echo_report = v

    # outcomes
    def _ensure_outcomes(self):
        if self.outcomes is None:
            self.outcomes = PatientOutcomes()
        return self.outcomes

    @property
    def current_survival_status(self):
        return self.outcomes.current_survival_status if self.outcomes else None

    @current_survival_status.setter
    def current_survival_status(self, v):
        self._ensure_outcomes().current_survival_status = v

    @property
    def date_of_death(self):
        return self.outcomes.date_of_death if self.outcomes else None

    @date_of_death.setter
    def date_of_death(self, v):
        self._ensure_outcomes().date_of_death = v

    @property
    def primary_cause_of_death(self):
        return self.outcomes.primary_cause_of_death if self.outcomes else None

    @primary_cause_of_death.setter
    def primary_cause_of_death(self, v):
        self._ensure_outcomes().primary_cause_of_death = v

    @property
    def date_of_transplant(self):
        return self.outcomes.date_of_transplant if self.outcomes else None

    @date_of_transplant.setter
    def date_of_transplant(self, v):
        self._ensure_outcomes().date_of_transplant = v

    @property
    def withdrawal_from_dialysis(self):
        return self.outcomes.withdrawal_from_dialysis if self.outcomes else None

    @withdrawal_from_dialysis.setter
    def withdrawal_from_dialysis(self, v):
        self._ensure_outcomes().withdrawal_from_dialysis = v

    @property
    def withdrawal_date(self):
        return self.outcomes.withdrawal_date if self.outcomes else None

    @withdrawal_date.setter
    def withdrawal_date(self, v):
        self._ensure_outcomes().withdrawal_date = v

    @property
    def withdrawal_reason(self):
        return self.outcomes.withdrawal_reason if self.outcomes else None

    @withdrawal_reason.setter
    def withdrawal_reason(self, v):
        self._ensure_outcomes().withdrawal_reason = v

    @property
    def withdrawal_clinician(self):
        return self.outcomes.withdrawal_clinician if self.outcomes else None

    @withdrawal_clinician.setter
    def withdrawal_clinician(self, v):
        self._ensure_outcomes().withdrawal_clinician = v

    @property
    def date_facility_transfer(self):
        return self.outcomes.date_facility_transfer if self.outcomes else None

    @date_facility_transfer.setter
    def date_facility_transfer(self, v):
        self._ensure_outcomes().date_facility_transfer = v
