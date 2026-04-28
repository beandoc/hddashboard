from sqlalchemy.orm import Session
from datetime import datetime
import re
from typing import Optional

from database import Patient
from utils import calculate_cci

def _d(s: Optional[str]) -> Optional[datetime.date]:
    return datetime.strptime(s, "%Y-%m-%d").date() if s else None

def create_patient_record(db: Session, data: dict) -> Patient:
    # Check if HID already exists
    existing = db.query(Patient).filter(Patient.hid_no == data["hid_no"]).first()
    if existing:
        raise ValueError(f"HID {data['hid_no']} already exists.")

    _cn = re.sub(r"\D", "", data.get("contact_no", "").strip()) if data.get("contact_no") else ""
    whatsapp_link = f"https://wa.me/91{_cn}" if len(_cn) == 10 else ""

    p = Patient(
        hid_no=data["hid_no"],
        name=data["name"],
        relation=data.get("relation", ""),
        relation_type=data.get("relation_type", ""),
        sex=data["sex"],
        contact_no=data.get("contact_no", ""),
        email=data.get("email", ""),
        diagnosis=data.get("diagnosis", ""),
        hd_wef_date=_d(data.get("hd_wef_date")),
        height=data.get("height"),
        education_level=data.get("education_level", ""),
        healthcare_facility=data.get("healthcare_facility", ""),
        primary_renal_disease=data.get("primary_renal_disease", ""),
        date_esrd_diagnosis=_d(data.get("date_esrd_diagnosis")),
        native_kidney_biopsy=data.get("native_kidney_biopsy", ""),
        native_kidney_biopsy_date=_d(data.get("native_kidney_biopsy_date")),
        native_kidney_biopsy_report=data.get("native_kidney_biopsy_report", ""),
        dm_status=data.get("dm_status", ""),
        dm_end_organ_damage=data.get("dm_end_organ_damage", False),
        htn_status=data.get("htn_status", False),
        cad_status=data.get("cad_status", False),
        chf_status=data.get("chf_status", False),
        history_of_stroke=data.get("history_of_stroke", False),
        history_of_pvd=data.get("history_of_pvd", False),
        history_of_dementia=data.get("history_of_dementia", False),
        history_of_cpd=data.get("history_of_cpd", False),
        history_of_ctd=data.get("history_of_ctd", False),
        history_of_pud=data.get("history_of_pud", False),
        liver_disease=data.get("liver_disease", ""),
        hemiplegia=data.get("hemiplegia", False),
        solid_tumor=data.get("solid_tumor", ""),
        leukemia=data.get("leukemia", False),
        lymphoma=data.get("lymphoma", False),
        smoking_status=data.get("smoking_status", ""),
        alcohol_consumption=data.get("alcohol_consumption", ""),
        charlson_comorbidity_index=calculate_cci(
            age=data.get("age"),
            cad_status=data.get("cad_status", False),
            chf_status=data.get("chf_status", False),
            history_of_pvd=data.get("history_of_pvd", False),
            history_of_stroke=data.get("history_of_stroke", False),
            history_of_dementia=data.get("history_of_dementia", False),
            history_of_cpd=data.get("history_of_cpd", False),
            history_of_ctd=data.get("history_of_ctd", False),
            history_of_pud=data.get("history_of_pud", False),
            liver_disease=data.get("liver_disease", ""),
            dm_status=data.get("dm_status", ""),
            dm_end_organ_damage=data.get("dm_end_organ_damage", False),
            hemiplegia=data.get("hemiplegia", False),
            solid_tumor=data.get("solid_tumor", ""),
            leukemia=data.get("leukemia", False),
            lymphoma=data.get("lymphoma", False),
            viral_hiv=data.get("viral_hiv", "")
        ),
        comorbidities=data.get("comorbidities", ""),
        drug_allergies=data.get("drug_allergies", ""),
        clinical_background=data.get("clinical_background", ""),
        dialysis_modality=data.get("dialysis_modality", ""),
        previous_krt_modality=data.get("previous_krt_modality", ""),
        history_of_renal_transplant=data.get("history_of_renal_transplant", False),
        transplant_prospect=data.get("transplant_prospect", ""),
        viral_markers=data.get("viral_markers", ""),
        viral_hbsag=data.get("viral_hbsag", ""),
        viral_anti_hcv=data.get("viral_anti_hcv", ""),
        viral_hiv=data.get("viral_hiv", ""),
        hep_b_status=data.get("hep_b_status", ""),
        hep_b_dose1_date=_d(data.get("hep_b_dose1_date")),
        hep_b_dose2_date=_d(data.get("hep_b_dose2_date")),
        hep_b_dose3_date=_d(data.get("hep_b_dose3_date")),
        hep_b_dose4_date=_d(data.get("hep_b_dose4_date")),
        hep_b_titer_date=_d(data.get("hep_b_titer_date")),
        pcv13_date=_d(data.get("pcv13_date")),
        ppsv23_date=_d(data.get("ppsv23_date")),
        hz_dose1_date=_d(data.get("hz_dose1_date")),
        hz_dose2_date=_d(data.get("hz_dose2_date")),
        influenza_date=_d(data.get("influenza_date")),
        access_type=data.get("access_type", ""),
        access_date=_d(data.get("access_date")),
        date_first_cannulation=_d(data.get("date_first_cannulation")),
        history_of_access_thrombosis=data.get("history_of_access_thrombosis", False),
        access_intervention_history=data.get("access_intervention_history", ""),
        catheter_type=data.get("catheter_type", ""),
        catheter_insertion_site=data.get("catheter_insertion_site", ""),
        age=data.get("age"),
        ejection_fraction=data.get("ejection_fraction") if data.get("ejection_fraction") is not None else 60.0,
        echo_date=_d(data.get("echo_date")),
        echo_report=data.get("echo_report", ""),
        dry_weight=data.get("dry_weight"),
        hd_frequency=data.get("hd_frequency", 2),
        hd_day_1=data.get("hd_day_1", ""),
        hd_day_2=data.get("hd_day_2", ""),
        hd_day_3=data.get("hd_day_3", ""),
        hd_slot_1=data.get("hd_slot_1", ""),
        hd_slot_2=data.get("hd_slot_2", ""),
        hd_slot_3=data.get("hd_slot_3", ""),
        blood_group=data.get("blood_group", ""),
        current_survival_status=data.get("current_survival_status", ""),
        date_of_death=_d(data.get("date_of_death")),
        primary_cause_of_death=data.get("primary_cause_of_death", ""),
        withdrawal_from_dialysis=data.get("withdrawal_from_dialysis", False),
        date_facility_transfer=_d(data.get("date_facility_transfer")),
        whatsapp_link=whatsapp_link,
        whatsapp_notify=data.get("whatsapp_notify", False),
        mail_trigger=data.get("mail_trigger", False),
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p

def update_patient_record(db: Session, patient_id: int, data: dict) -> Patient:
    p = db.query(Patient).filter(Patient.id == patient_id).first()
    if not p:
        raise ValueError("Patient not found")

    p.hid_no = data["hid_no"]
    p.name = data["name"]
    p.relation = data.get("relation", "")
    p.relation_type = data.get("relation_type", "")
    p.sex = data["sex"]
    p.contact_no = data.get("contact_no", "")
    p.email = data.get("email", "")
    p.diagnosis = data.get("diagnosis", "")
    p.hd_wef_date = _d(data.get("hd_wef_date"))
    p.height = data.get("height")
    p.education_level = data.get("education_level", "")
    p.healthcare_facility = data.get("healthcare_facility", "")
    p.primary_renal_disease = data.get("primary_renal_disease", "")
    p.date_esrd_diagnosis = _d(data.get("date_esrd_diagnosis"))
    p.native_kidney_biopsy = data.get("native_kidney_biopsy", "")
    p.native_kidney_biopsy_date = _d(data.get("native_kidney_biopsy_date"))
    p.native_kidney_biopsy_report = data.get("native_kidney_biopsy_report", "")
    p.dm_status = data.get("dm_status", "")
    p.dm_end_organ_damage = data.get("dm_end_organ_damage", False)
    p.htn_status = data.get("htn_status", False)
    p.cad_status = data.get("cad_status", False)
    p.chf_status = data.get("chf_status", False)
    p.history_of_stroke = data.get("history_of_stroke", False)
    p.history_of_pvd = data.get("history_of_pvd", False)
    p.history_of_dementia = data.get("history_of_dementia", False)
    p.history_of_cpd = data.get("history_of_cpd", False)
    p.history_of_ctd = data.get("history_of_ctd", False)
    p.history_of_pud = data.get("history_of_pud", False)
    p.liver_disease = data.get("liver_disease", "")
    p.hemiplegia = data.get("hemiplegia", False)
    p.solid_tumor = data.get("solid_tumor", "")
    p.leukemia = data.get("leukemia", False)
    p.lymphoma = data.get("lymphoma", False)
    p.smoking_status = data.get("smoking_status", "")
    p.alcohol_consumption = data.get("alcohol_consumption", "")
    p.charlson_comorbidity_index = calculate_cci(
        age=data.get("age"),
        cad_status=data.get("cad_status", False),
        chf_status=data.get("chf_status", False),
        history_of_pvd=data.get("history_of_pvd", False),
        history_of_stroke=data.get("history_of_stroke", False),
        history_of_dementia=data.get("history_of_dementia", False),
        history_of_cpd=data.get("history_of_cpd", False),
        history_of_ctd=data.get("history_of_ctd", False),
        history_of_pud=data.get("history_of_pud", False),
        liver_disease=data.get("liver_disease", ""),
        dm_status=data.get("dm_status", ""),
        dm_end_organ_damage=data.get("dm_end_organ_damage", False),
        hemiplegia=data.get("hemiplegia", False),
        solid_tumor=data.get("solid_tumor", ""),
        leukemia=data.get("leukemia", False),
        lymphoma=data.get("lymphoma", False),
        viral_hiv=data.get("viral_hiv", "")
    )
    p.comorbidities = data.get("comorbidities", "")
    p.drug_allergies = data.get("drug_allergies", "")
    p.clinical_background = data.get("clinical_background", "")
    p.dialysis_modality = data.get("dialysis_modality", "")
    p.previous_krt_modality = data.get("previous_krt_modality", "")
    p.history_of_renal_transplant = data.get("history_of_renal_transplant", False)
    p.transplant_prospect = data.get("transplant_prospect", "")
    p.viral_markers = data.get("viral_markers", "")
    p.viral_hbsag = data.get("viral_hbsag", "")
    p.viral_anti_hcv = data.get("viral_anti_hcv", "")
    p.viral_hiv = data.get("viral_hiv", "")
    p.hep_b_status = data.get("hep_b_status", "")
    p.hep_b_dose1_date = _d(data.get("hep_b_dose1_date"))
    p.hep_b_dose2_date = _d(data.get("hep_b_dose2_date"))
    p.hep_b_dose3_date = _d(data.get("hep_b_dose3_date"))
    p.hep_b_dose4_date = _d(data.get("hep_b_dose4_date"))
    p.hep_b_titer_date = _d(data.get("hep_b_titer_date"))
    p.pcv13_date = _d(data.get("pcv13_date"))
    p.ppsv23_date = _d(data.get("ppsv23_date"))
    p.hz_dose1_date = _d(data.get("hz_dose1_date"))
    p.hz_dose2_date = _d(data.get("hz_dose2_date"))
    p.influenza_date = _d(data.get("influenza_date"))
    p.access_type = data.get("access_type", "")
    p.access_date = _d(data.get("access_date"))
    p.date_first_cannulation = _d(data.get("date_first_cannulation"))
    p.history_of_access_thrombosis = data.get("history_of_access_thrombosis", False)
    p.access_intervention_history = data.get("access_intervention_history", "")
    p.catheter_type = data.get("catheter_type", "")
    p.catheter_insertion_site = data.get("catheter_insertion_site", "")
    p.age = data.get("age")
    p.ejection_fraction = data.get("ejection_fraction") if data.get("ejection_fraction") is not None else (p.ejection_fraction or 60.0)
    p.echo_date = _d(data.get("echo_date"))
    p.echo_report = data.get("echo_report", "")
    p.dry_weight = data.get("dry_weight")
    p.hd_frequency = data.get("hd_frequency", 2)
    p.hd_day_1 = data.get("hd_day_1", "")
    p.hd_day_2 = data.get("hd_day_2", "")
    p.hd_day_3 = data.get("hd_day_3", "")
    p.hd_slot_1 = data.get("hd_slot_1", "")
    p.hd_slot_2 = data.get("hd_slot_2", "")
    p.hd_slot_3 = data.get("hd_slot_3", "")
    p.blood_group = data.get("blood_group", "")
    p.current_survival_status = data.get("current_survival_status", "")
    p.date_of_death = _d(data.get("date_of_death"))
    p.primary_cause_of_death = data.get("primary_cause_of_death", "")
    p.withdrawal_from_dialysis = data.get("withdrawal_from_dialysis", False)
    p.date_facility_transfer = _d(data.get("date_facility_transfer"))
    
    _cn = re.sub(r"\D", "", data.get("contact_no", "").strip()) if data.get("contact_no") else ""
    p.whatsapp_link = f"https://wa.me/91{_cn}" if len(_cn) == 10 else ""
    p.whatsapp_notify = data.get("whatsapp_notify", False)
    p.mail_trigger = data.get("mail_trigger", False)
    p.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(p)
    return p
