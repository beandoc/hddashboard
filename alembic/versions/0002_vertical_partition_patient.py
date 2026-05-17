"""Vertical partition of patients table into satellite tables.

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-17

What this migration does
────────────────────────
1. Creates 8 satellite tables (patient_id as PK + FK → CASCADE DELETE):
     patient_credentials, patient_comorbidities, patient_renal_profile,
     patient_viral_markers, patient_vaccination, patient_vascular_access,
     patient_cardiac, patient_outcomes

2. Copies every row from patients into the matching satellite (data preserved).

3. Drops the moved columns from patients (PostgreSQL only — SQLite does not
   support DROP COLUMN and is used for local dev only; SQLite instances will
   be rebuilt from scratch by the new ORM schema).

Rationale
─────────
The monolithic patients table had ~170 columns spanning auth credentials,
comorbidities, viral markers, vaccination, vascular access, cardiac parameters,
renal profile, and outcomes.  Every PHI read was loading hashed passwords;
every auth check was loading clinical history.  Row size was degrading the
PostgreSQL shared-buffer cache.

Rollback
────────
downgrade() copies data back into patients, then drops the satellite tables.
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _is_pg(bind) -> bool:
    return bind.dialect.name == "postgresql"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    existing_tables = set(inspector.get_table_names())

    # ── 1. Create satellite tables ────────────────────────────────────────────

    if "patient_credentials" not in existing_tables:
        op.create_table(
            "patient_credentials",
            sa.Column("patient_id", sa.Integer, sa.ForeignKey("patients.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("hashed_password", sa.String),
        )

    if "patient_comorbidities" not in existing_tables:
        op.create_table(
            "patient_comorbidities",
            sa.Column("patient_id", sa.Integer, sa.ForeignKey("patients.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("dm_status", sa.String),
            sa.Column("dm_end_organ_damage", sa.Boolean),
            sa.Column("htn_status", sa.Boolean),
            sa.Column("cad_status", sa.Boolean),
            sa.Column("chf_status", sa.Boolean),
            sa.Column("history_of_stroke", sa.Boolean),
            sa.Column("history_of_pvd", sa.Boolean),
            sa.Column("history_of_dementia", sa.Boolean),
            sa.Column("history_of_cpd", sa.Boolean),
            sa.Column("history_of_ctd", sa.Boolean),
            sa.Column("history_of_pud", sa.Boolean),
            sa.Column("liver_disease", sa.String),
            sa.Column("hemiplegia", sa.Boolean),
            sa.Column("solid_tumor", sa.String),
            sa.Column("leukemia", sa.Boolean),
            sa.Column("lymphoma", sa.Boolean),
            sa.Column("smoking_status", sa.String),
            sa.Column("alcohol_consumption", sa.String),
            sa.Column("charlson_comorbidity_index", sa.Integer),
            sa.Column("comorbidities", sa.Text),
            sa.Column("drug_allergies", sa.String),
            sa.Column("clinical_background", sa.Text),
        )

    if "patient_renal_profile" not in existing_tables:
        op.create_table(
            "patient_renal_profile",
            sa.Column("patient_id", sa.Integer, sa.ForeignKey("patients.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("primary_renal_disease", sa.String),
            sa.Column("native_kidney_disease", sa.String),
            sa.Column("date_esrd_diagnosis", sa.Date),
            sa.Column("native_kidney_biopsy", sa.String),
            sa.Column("native_kidney_biopsy_date", sa.Date),
            sa.Column("native_kidney_biopsy_report", sa.Text),
            sa.Column("dialysis_modality", sa.String),
            sa.Column("previous_dialysis_modality", sa.String),
            sa.Column("previous_krt_modality", sa.String),
            sa.Column("history_of_renal_transplant", sa.Boolean),
            sa.Column("transplant_prospect", sa.String),
            sa.Column("baseline_gcr", sa.Float),
            sa.Column("baseline_vdcr", sa.Float),
            sa.Column("is_black", sa.Boolean, server_default=sa.text("false")),
        )

    if "patient_viral_markers" not in existing_tables:
        op.create_table(
            "patient_viral_markers",
            sa.Column("patient_id", sa.Integer, sa.ForeignKey("patients.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("viral_markers", sa.String),
            sa.Column("viral_hbsag", sa.String),
            sa.Column("viral_anti_hcv", sa.String),
            sa.Column("viral_hiv", sa.String),
        )

    if "patient_vaccination" not in existing_tables:
        op.create_table(
            "patient_vaccination",
            sa.Column("patient_id", sa.Integer, sa.ForeignKey("patients.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("hep_b_status", sa.String),
            sa.Column("hep_b_dose1_date", sa.Date),
            sa.Column("hep_b_dose2_date", sa.Date),
            sa.Column("hep_b_dose3_date", sa.Date),
            sa.Column("hep_b_dose4_date", sa.Date),
            sa.Column("hep_b_titer_date", sa.Date),
            sa.Column("pcv13_date", sa.Date),
            sa.Column("ppsv23_date", sa.Date),
            sa.Column("hz_dose1_date", sa.Date),
            sa.Column("hz_dose2_date", sa.Date),
            sa.Column("influenza_date", sa.Date),
        )

    if "patient_vascular_access" not in existing_tables:
        op.create_table(
            "patient_vascular_access",
            sa.Column("patient_id", sa.Integer, sa.ForeignKey("patients.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("access_type", sa.String),
            sa.Column("access_date", sa.Date),
            sa.Column("date_first_cannulation", sa.Date),
            sa.Column("history_of_access_thrombosis", sa.Boolean),
            sa.Column("access_intervention_history", sa.Text),
            sa.Column("catheter_type", sa.String),
            sa.Column("catheter_insertion_site", sa.String),
        )

    if "patient_cardiac" not in existing_tables:
        op.create_table(
            "patient_cardiac",
            sa.Column("patient_id", sa.Integer, sa.ForeignKey("patients.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("ejection_fraction", sa.Float, server_default=sa.text("60")),
            sa.Column("diastolic_dysfunction", sa.String),
            sa.Column("handgrip_strength", sa.Float),
            sa.Column("echo_date", sa.Date),
            sa.Column("echo_report", sa.Text),
        )

    if "patient_outcomes" not in existing_tables:
        op.create_table(
            "patient_outcomes",
            sa.Column("patient_id", sa.Integer, sa.ForeignKey("patients.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("current_survival_status", sa.String),
            sa.Column("date_of_death", sa.Date),
            sa.Column("primary_cause_of_death", sa.String),
            sa.Column("date_of_transplant", sa.Date),
            sa.Column("withdrawal_from_dialysis", sa.Boolean),
            sa.Column("withdrawal_date", sa.Date),
            sa.Column("withdrawal_reason", sa.String),
            sa.Column("withdrawal_clinician", sa.String),
            sa.Column("date_facility_transfer", sa.Date),
        )

    # ── 2. Copy data from patients into each satellite ────────────────────────
    # INSERT … SELECT is idempotent if re-run on an empty satellite (no rows
    # exist yet).  We guard with "WHERE NOT EXISTS" to handle partial runs.

    bind.execute(sa.text("""
        INSERT INTO patient_credentials (patient_id, hashed_password)
        SELECT id, hashed_password
        FROM patients
        WHERE hashed_password IS NOT NULL
          AND NOT EXISTS (
            SELECT 1 FROM patient_credentials pc WHERE pc.patient_id = patients.id
          )
    """))

    bind.execute(sa.text("""
        INSERT INTO patient_comorbidities (
            patient_id, dm_status, dm_end_organ_damage, htn_status, cad_status,
            chf_status, history_of_stroke, history_of_pvd, history_of_dementia,
            history_of_cpd, history_of_ctd, history_of_pud, liver_disease,
            hemiplegia, solid_tumor, leukemia, lymphoma, smoking_status,
            alcohol_consumption, charlson_comorbidity_index, comorbidities,
            drug_allergies, clinical_background
        )
        SELECT
            id, dm_status, dm_end_organ_damage, htn_status, cad_status,
            chf_status, history_of_stroke, history_of_pvd, history_of_dementia,
            history_of_cpd, history_of_ctd, history_of_pud, liver_disease,
            hemiplegia, solid_tumor, leukemia, lymphoma, smoking_status,
            alcohol_consumption, charlson_comorbidity_index, comorbidities,
            drug_allergies, clinical_background
        FROM patients
        WHERE NOT EXISTS (
            SELECT 1 FROM patient_comorbidities pc WHERE pc.patient_id = patients.id
        )
    """))

    bind.execute(sa.text("""
        INSERT INTO patient_renal_profile (
            patient_id, primary_renal_disease, native_kidney_disease,
            date_esrd_diagnosis, native_kidney_biopsy, native_kidney_biopsy_date,
            native_kidney_biopsy_report, dialysis_modality, previous_dialysis_modality,
            previous_krt_modality, history_of_renal_transplant, transplant_prospect,
            baseline_gcr, baseline_vdcr, is_black
        )
        SELECT
            id, primary_renal_disease, native_kidney_disease,
            date_esrd_diagnosis, native_kidney_biopsy, native_kidney_biopsy_date,
            native_kidney_biopsy_report, dialysis_modality, previous_dialysis_modality,
            previous_krt_modality, history_of_renal_transplant, transplant_prospect,
            baseline_gcr, baseline_vdcr,
            COALESCE(is_black, false)
        FROM patients
        WHERE NOT EXISTS (
            SELECT 1 FROM patient_renal_profile pr WHERE pr.patient_id = patients.id
        )
    """))

    bind.execute(sa.text("""
        INSERT INTO patient_viral_markers (patient_id, viral_markers, viral_hbsag, viral_anti_hcv, viral_hiv)
        SELECT id, viral_markers, viral_hbsag, viral_anti_hcv, viral_hiv
        FROM patients
        WHERE NOT EXISTS (
            SELECT 1 FROM patient_viral_markers pv WHERE pv.patient_id = patients.id
        )
    """))

    bind.execute(sa.text("""
        INSERT INTO patient_vaccination (
            patient_id, hep_b_status, hep_b_dose1_date, hep_b_dose2_date,
            hep_b_dose3_date, hep_b_dose4_date, hep_b_titer_date,
            pcv13_date, ppsv23_date, hz_dose1_date, hz_dose2_date, influenza_date
        )
        SELECT
            id, hep_b_status, hep_b_dose1_date, hep_b_dose2_date,
            hep_b_dose3_date, hep_b_dose4_date, hep_b_titer_date,
            pcv13_date, ppsv23_date, hz_dose1_date, hz_dose2_date, influenza_date
        FROM patients
        WHERE NOT EXISTS (
            SELECT 1 FROM patient_vaccination pv WHERE pv.patient_id = patients.id
        )
    """))

    bind.execute(sa.text("""
        INSERT INTO patient_vascular_access (
            patient_id, access_type, access_date, date_first_cannulation,
            history_of_access_thrombosis, access_intervention_history,
            catheter_type, catheter_insertion_site
        )
        SELECT
            id, access_type, access_date, date_first_cannulation,
            history_of_access_thrombosis, access_intervention_history,
            catheter_type, catheter_insertion_site
        FROM patients
        WHERE NOT EXISTS (
            SELECT 1 FROM patient_vascular_access pv WHERE pv.patient_id = patients.id
        )
    """))

    bind.execute(sa.text("""
        INSERT INTO patient_cardiac (
            patient_id, ejection_fraction, diastolic_dysfunction,
            handgrip_strength, echo_date, echo_report
        )
        SELECT
            id,
            COALESCE(ejection_fraction, 60),
            diastolic_dysfunction, handgrip_strength, echo_date, echo_report
        FROM patients
        WHERE NOT EXISTS (
            SELECT 1 FROM patient_cardiac pc WHERE pc.patient_id = patients.id
        )
    """))

    bind.execute(sa.text("""
        INSERT INTO patient_outcomes (
            patient_id, current_survival_status, date_of_death,
            primary_cause_of_death, date_of_transplant, withdrawal_from_dialysis,
            withdrawal_date, withdrawal_reason, withdrawal_clinician,
            date_facility_transfer
        )
        SELECT
            id, current_survival_status, date_of_death,
            primary_cause_of_death, date_of_transplant, withdrawal_from_dialysis,
            withdrawal_date, withdrawal_reason, withdrawal_clinician,
            date_facility_transfer
        FROM patients
        WHERE NOT EXISTS (
            SELECT 1 FROM patient_outcomes po WHERE po.patient_id = patients.id
        )
    """))

    # ── 3. Drop moved columns from patients (PostgreSQL only) ─────────────────
    # SQLite does not support DROP COLUMN.  Local dev databases are rebuilt
    # from scratch using the new schema (create_tables / alembic upgrade head
    # on a clean DB).  Production runs on PostgreSQL.

    if _is_pg(bind):
        cols_to_drop = [
            # credentials
            "hashed_password",
            # comorbidities
            "dm_status", "dm_end_organ_damage", "htn_status", "cad_status",
            "chf_status", "history_of_stroke", "history_of_pvd", "history_of_dementia",
            "history_of_cpd", "history_of_ctd", "history_of_pud", "liver_disease",
            "hemiplegia", "solid_tumor", "leukemia", "lymphoma", "smoking_status",
            "alcohol_consumption", "charlson_comorbidity_index", "comorbidities",
            "drug_allergies", "clinical_background",
            # renal profile
            "primary_renal_disease", "native_kidney_disease", "date_esrd_diagnosis",
            "native_kidney_biopsy", "native_kidney_biopsy_date", "native_kidney_biopsy_report",
            "dialysis_modality", "previous_dialysis_modality", "previous_krt_modality",
            "history_of_renal_transplant", "transplant_prospect",
            "baseline_gcr", "baseline_vdcr", "is_black",
            # viral markers
            "viral_markers", "viral_hbsag", "viral_anti_hcv", "viral_hiv",
            # vaccination
            "hep_b_status", "hep_b_dose1_date", "hep_b_dose2_date", "hep_b_dose3_date",
            "hep_b_dose4_date", "hep_b_titer_date", "pcv13_date", "ppsv23_date",
            "hz_dose1_date", "hz_dose2_date", "influenza_date",
            # vascular access
            "access_type", "access_date", "date_first_cannulation",
            "history_of_access_thrombosis", "access_intervention_history",
            "catheter_type", "catheter_insertion_site",
            # cardiac
            "ejection_fraction", "diastolic_dysfunction", "handgrip_strength",
            "echo_date", "echo_report",
            # outcomes
            "current_survival_status", "date_of_death", "primary_cause_of_death",
            "date_of_transplant", "withdrawal_from_dialysis", "withdrawal_date",
            "withdrawal_reason", "withdrawal_clinician", "date_facility_transfer",
        ]
        existing_cols = {c["name"] for c in inspector.get_columns("patients")}
        for col in cols_to_drop:
            if col in existing_cols:
                op.drop_column("patients", col)


def downgrade() -> None:
    bind = op.get_bind()

    if _is_pg(bind):
        # Re-add columns to patients
        op.add_column("patients", sa.Column("hashed_password", sa.String))
        op.add_column("patients", sa.Column("dm_status", sa.String))
        op.add_column("patients", sa.Column("dm_end_organ_damage", sa.Boolean))
        op.add_column("patients", sa.Column("htn_status", sa.Boolean))
        op.add_column("patients", sa.Column("cad_status", sa.Boolean))
        op.add_column("patients", sa.Column("chf_status", sa.Boolean))
        op.add_column("patients", sa.Column("history_of_stroke", sa.Boolean))
        op.add_column("patients", sa.Column("history_of_pvd", sa.Boolean))
        op.add_column("patients", sa.Column("history_of_dementia", sa.Boolean))
        op.add_column("patients", sa.Column("history_of_cpd", sa.Boolean))
        op.add_column("patients", sa.Column("history_of_ctd", sa.Boolean))
        op.add_column("patients", sa.Column("history_of_pud", sa.Boolean))
        op.add_column("patients", sa.Column("liver_disease", sa.String))
        op.add_column("patients", sa.Column("hemiplegia", sa.Boolean))
        op.add_column("patients", sa.Column("solid_tumor", sa.String))
        op.add_column("patients", sa.Column("leukemia", sa.Boolean))
        op.add_column("patients", sa.Column("lymphoma", sa.Boolean))
        op.add_column("patients", sa.Column("smoking_status", sa.String))
        op.add_column("patients", sa.Column("alcohol_consumption", sa.String))
        op.add_column("patients", sa.Column("charlson_comorbidity_index", sa.Integer))
        op.add_column("patients", sa.Column("comorbidities", sa.Text))
        op.add_column("patients", sa.Column("drug_allergies", sa.String))
        op.add_column("patients", sa.Column("clinical_background", sa.Text))
        op.add_column("patients", sa.Column("primary_renal_disease", sa.String))
        op.add_column("patients", sa.Column("native_kidney_disease", sa.String))
        op.add_column("patients", sa.Column("date_esrd_diagnosis", sa.Date))
        op.add_column("patients", sa.Column("native_kidney_biopsy", sa.String))
        op.add_column("patients", sa.Column("native_kidney_biopsy_date", sa.Date))
        op.add_column("patients", sa.Column("native_kidney_biopsy_report", sa.Text))
        op.add_column("patients", sa.Column("dialysis_modality", sa.String))
        op.add_column("patients", sa.Column("previous_dialysis_modality", sa.String))
        op.add_column("patients", sa.Column("previous_krt_modality", sa.String))
        op.add_column("patients", sa.Column("history_of_renal_transplant", sa.Boolean))
        op.add_column("patients", sa.Column("transplant_prospect", sa.String))
        op.add_column("patients", sa.Column("baseline_gcr", sa.Float))
        op.add_column("patients", sa.Column("baseline_vdcr", sa.Float))
        op.add_column("patients", sa.Column("is_black", sa.Boolean))
        op.add_column("patients", sa.Column("viral_markers", sa.String))
        op.add_column("patients", sa.Column("viral_hbsag", sa.String))
        op.add_column("patients", sa.Column("viral_anti_hcv", sa.String))
        op.add_column("patients", sa.Column("viral_hiv", sa.String))
        op.add_column("patients", sa.Column("hep_b_status", sa.String))
        op.add_column("patients", sa.Column("hep_b_dose1_date", sa.Date))
        op.add_column("patients", sa.Column("hep_b_dose2_date", sa.Date))
        op.add_column("patients", sa.Column("hep_b_dose3_date", sa.Date))
        op.add_column("patients", sa.Column("hep_b_dose4_date", sa.Date))
        op.add_column("patients", sa.Column("hep_b_titer_date", sa.Date))
        op.add_column("patients", sa.Column("pcv13_date", sa.Date))
        op.add_column("patients", sa.Column("ppsv23_date", sa.Date))
        op.add_column("patients", sa.Column("hz_dose1_date", sa.Date))
        op.add_column("patients", sa.Column("hz_dose2_date", sa.Date))
        op.add_column("patients", sa.Column("influenza_date", sa.Date))
        op.add_column("patients", sa.Column("access_type", sa.String))
        op.add_column("patients", sa.Column("access_date", sa.Date))
        op.add_column("patients", sa.Column("date_first_cannulation", sa.Date))
        op.add_column("patients", sa.Column("history_of_access_thrombosis", sa.Boolean))
        op.add_column("patients", sa.Column("access_intervention_history", sa.Text))
        op.add_column("patients", sa.Column("catheter_type", sa.String))
        op.add_column("patients", sa.Column("catheter_insertion_site", sa.String))
        op.add_column("patients", sa.Column("ejection_fraction", sa.Float))
        op.add_column("patients", sa.Column("diastolic_dysfunction", sa.String))
        op.add_column("patients", sa.Column("handgrip_strength", sa.Float))
        op.add_column("patients", sa.Column("echo_date", sa.Date))
        op.add_column("patients", sa.Column("echo_report", sa.Text))
        op.add_column("patients", sa.Column("current_survival_status", sa.String))
        op.add_column("patients", sa.Column("date_of_death", sa.Date))
        op.add_column("patients", sa.Column("primary_cause_of_death", sa.String))
        op.add_column("patients", sa.Column("date_of_transplant", sa.Date))
        op.add_column("patients", sa.Column("withdrawal_from_dialysis", sa.Boolean))
        op.add_column("patients", sa.Column("withdrawal_date", sa.Date))
        op.add_column("patients", sa.Column("withdrawal_reason", sa.String))
        op.add_column("patients", sa.Column("withdrawal_clinician", sa.String))
        op.add_column("patients", sa.Column("date_facility_transfer", sa.Date))

        # Copy data back from satellites
        bind.execute(sa.text("UPDATE patients p SET hashed_password = pc.hashed_password FROM patient_credentials pc WHERE p.id = pc.patient_id"))
        bind.execute(sa.text("""
            UPDATE patients p SET
                dm_status = c.dm_status, dm_end_organ_damage = c.dm_end_organ_damage,
                htn_status = c.htn_status, cad_status = c.cad_status, chf_status = c.chf_status,
                history_of_stroke = c.history_of_stroke, history_of_pvd = c.history_of_pvd,
                history_of_dementia = c.history_of_dementia, history_of_cpd = c.history_of_cpd,
                history_of_ctd = c.history_of_ctd, history_of_pud = c.history_of_pud,
                liver_disease = c.liver_disease, hemiplegia = c.hemiplegia,
                solid_tumor = c.solid_tumor, leukemia = c.leukemia, lymphoma = c.lymphoma,
                smoking_status = c.smoking_status, alcohol_consumption = c.alcohol_consumption,
                charlson_comorbidity_index = c.charlson_comorbidity_index,
                comorbidities = c.comorbidities, drug_allergies = c.drug_allergies,
                clinical_background = c.clinical_background
            FROM patient_comorbidities c WHERE p.id = c.patient_id
        """))
        bind.execute(sa.text("""
            UPDATE patients p SET
                primary_renal_disease = r.primary_renal_disease,
                native_kidney_disease = r.native_kidney_disease,
                date_esrd_diagnosis = r.date_esrd_diagnosis,
                native_kidney_biopsy = r.native_kidney_biopsy,
                native_kidney_biopsy_date = r.native_kidney_biopsy_date,
                native_kidney_biopsy_report = r.native_kidney_biopsy_report,
                dialysis_modality = r.dialysis_modality,
                previous_dialysis_modality = r.previous_dialysis_modality,
                previous_krt_modality = r.previous_krt_modality,
                history_of_renal_transplant = r.history_of_renal_transplant,
                transplant_prospect = r.transplant_prospect,
                baseline_gcr = r.baseline_gcr, baseline_vdcr = r.baseline_vdcr,
                is_black = r.is_black
            FROM patient_renal_profile r WHERE p.id = r.patient_id
        """))
        bind.execute(sa.text("""
            UPDATE patients p SET
                viral_markers = v.viral_markers, viral_hbsag = v.viral_hbsag,
                viral_anti_hcv = v.viral_anti_hcv, viral_hiv = v.viral_hiv
            FROM patient_viral_markers v WHERE p.id = v.patient_id
        """))
        bind.execute(sa.text("""
            UPDATE patients p SET
                hep_b_status = v.hep_b_status,
                hep_b_dose1_date = v.hep_b_dose1_date, hep_b_dose2_date = v.hep_b_dose2_date,
                hep_b_dose3_date = v.hep_b_dose3_date, hep_b_dose4_date = v.hep_b_dose4_date,
                hep_b_titer_date = v.hep_b_titer_date, pcv13_date = v.pcv13_date,
                ppsv23_date = v.ppsv23_date, hz_dose1_date = v.hz_dose1_date,
                hz_dose2_date = v.hz_dose2_date, influenza_date = v.influenza_date
            FROM patient_vaccination v WHERE p.id = v.patient_id
        """))
        bind.execute(sa.text("""
            UPDATE patients p SET
                access_type = a.access_type, access_date = a.access_date,
                date_first_cannulation = a.date_first_cannulation,
                history_of_access_thrombosis = a.history_of_access_thrombosis,
                access_intervention_history = a.access_intervention_history,
                catheter_type = a.catheter_type, catheter_insertion_site = a.catheter_insertion_site
            FROM patient_vascular_access a WHERE p.id = a.patient_id
        """))
        bind.execute(sa.text("""
            UPDATE patients p SET
                ejection_fraction = c.ejection_fraction,
                diastolic_dysfunction = c.diastolic_dysfunction,
                handgrip_strength = c.handgrip_strength,
                echo_date = c.echo_date, echo_report = c.echo_report
            FROM patient_cardiac c WHERE p.id = c.patient_id
        """))
        bind.execute(sa.text("""
            UPDATE patients p SET
                current_survival_status = o.current_survival_status,
                date_of_death = o.date_of_death,
                primary_cause_of_death = o.primary_cause_of_death,
                date_of_transplant = o.date_of_transplant,
                withdrawal_from_dialysis = o.withdrawal_from_dialysis,
                withdrawal_date = o.withdrawal_date,
                withdrawal_reason = o.withdrawal_reason,
                withdrawal_clinician = o.withdrawal_clinician,
                date_facility_transfer = o.date_facility_transfer
            FROM patient_outcomes o WHERE p.id = o.patient_id
        """))

    # Drop satellite tables
    for tbl in [
        "patient_outcomes", "patient_cardiac", "patient_vascular_access",
        "patient_vaccination", "patient_viral_markers", "patient_renal_profile",
        "patient_comorbidities", "patient_credentials",
    ]:
        op.drop_table(tbl)
