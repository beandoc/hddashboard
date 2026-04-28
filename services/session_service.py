from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional

from database import Patient, SessionRecord, InterimLabRecord

def promote_session_labs(db: Session, sess: SessionRecord):
    """Hybrid logic: promote session labs to the longitudinal InterimLabRecord table."""
    params = [
        ("hb", sess.interim_hb, "g/dL"),
        ("potassium", sess.interim_k, "mEq/L"),
        ("calcium", sess.interim_ca, "mg/dL"),
    ]
    trigger = sess.interim_trigger or "Routine Recheck (Session)"
    
    for param_name, val, unit in params:
        if val is not None:
            existing = db.query(InterimLabRecord).filter(
                InterimLabRecord.session_id == sess.id,
                InterimLabRecord.parameter == param_name
            ).first()
            if existing:
                existing.value = val
                existing.trigger = trigger
            else:
                interim = InterimLabRecord(
                    patient_id=sess.patient_id,
                    session_id=sess.id,
                    lab_date=sess.session_date,
                    record_month=sess.record_month,
                    parameter=param_name,
                    value=val,
                    unit=unit,
                    trigger=trigger,
                    entered_by=sess.entered_by
                )
                db.add(interim)
    db.commit()

def create_session_record(db: Session, patient_id: int, data: dict) -> SessionRecord:
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise ValueError("Patient not found")
        
    session_date = data["session_date"]
    month_str = session_date[:7]
    
    rec = SessionRecord(
        patient_id=patient_id,
        session_date=datetime.strptime(session_date, "%Y-%m-%d").date(),
        record_month=month_str,
        entered_by=data.get("entered_by", ""),
        blood_flow_rate=data.get("blood_flow_rate"),
        actual_blood_flow_rate=data.get("actual_blood_flow_rate"),
        dialysate_flow=data.get("dialysate_flow"),
        duration_hours=data.get("duration_hours"),
        duration_minutes=data.get("duration_minutes"),
        weight_pre=data.get("weight_pre"),
        weight_post=data.get("weight_post"),
        bp_pre_sys=data.get("bp_pre_sys"),
        bp_pre_dia=data.get("bp_pre_dia"),
        bp_post_sys=data.get("bp_post_sys"),
        bp_post_dia=data.get("bp_post_dia"),
        arterial_line_pressure=data.get("arterial_line_pressure"),
        venous_line_pressure=data.get("venous_line_pressure"),
        access_location=data.get("access_location", ""),
        access_condition=data.get("access_condition", ""),
        needle_gauge=data.get("needle_gauge", ""),
        cannulation_technique=data.get("cannulation_technique", ""),
        access_complications=data.get("access_complications", ""),
        vascular_interventions=data.get("vascular_interventions", ""),
        anticoagulation=data.get("anticoagulation", ""),
        anticoagulation_dose=data.get("anticoagulation_dose"),
        early_termination=data.get("early_termination", False),
        dialyzer_type=data.get("dialyzer_type", ""),
        interim_hb=data.get("interim_hb"),
        interim_k=data.get("interim_k"),
        interim_ca=data.get("interim_ca"),
        interim_trigger=data.get("interim_trigger"),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    promote_session_labs(db, rec)
    return rec

def update_session_record(db: Session, session_id: int, data: dict) -> SessionRecord:
    sess = db.query(SessionRecord).filter(SessionRecord.id == session_id).first()
    if not sess:
        raise ValueError("Session not found")
        
    session_date = data["session_date"]
    sess.session_date = datetime.strptime(session_date, "%Y-%m-%d").date()
    sess.record_month = session_date[:7]
    sess.entered_by = data.get("entered_by", "")
    sess.blood_flow_rate = data.get("blood_flow_rate")
    sess.actual_blood_flow_rate = data.get("actual_blood_flow_rate")
    sess.dialysate_flow = data.get("dialysate_flow")
    sess.duration_hours = data.get("duration_hours")
    sess.duration_minutes = data.get("duration_minutes")
    sess.weight_pre = data.get("weight_pre")
    sess.weight_post = data.get("weight_post")
    sess.bp_pre_sys = data.get("bp_pre_sys")
    sess.bp_pre_dia = data.get("bp_pre_dia")
    sess.bp_post_sys = data.get("bp_post_sys")
    sess.bp_post_dia = data.get("bp_post_dia")
    sess.arterial_line_pressure = data.get("arterial_line_pressure")
    sess.venous_line_pressure = data.get("venous_line_pressure")
    sess.access_location = data.get("access_location", "")
    sess.access_condition = data.get("access_condition", "")
    sess.needle_gauge = data.get("needle_gauge", "")
    sess.cannulation_technique = data.get("cannulation_technique", "")
    sess.access_complications = data.get("access_complications", "")
    sess.vascular_interventions = data.get("vascular_interventions", "")
    sess.anticoagulation = data.get("anticoagulation", "")
    sess.anticoagulation_dose = data.get("anticoagulation_dose")
    sess.idh_episode = data.get("idh_episode", False)
    sess.muscle_cramps = data.get("muscle_cramps", False)
    sess.early_termination = data.get("early_termination", False)
    sess.dialyzer_type = data.get("dialyzer_type", "")
    sess.interim_hb = data.get("interim_hb")
    sess.interim_k = data.get("interim_k")
    sess.interim_ca = data.get("interim_ca")
    sess.interim_trigger = data.get("interim_trigger")
    
    db.commit()
    db.refresh(sess)
    promote_session_labs(db, sess)
    return sess
