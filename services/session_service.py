from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional

from database import Patient, SessionRecord, InterimLabRecord, PatientSymptomReport

_SONG_HD_KEYS = [
    'dialysis_recovery_time_mins', 'tiredness_score', 'energy_level_score',
    'sleepiness_severity', 'daily_activity_impact', 'cognitive_alertness',
    'post_hd_mood', 'symptoms', 'symptom_notes', 'severity',
    'missed_social_or_work_event',
]

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
    
    # Compute UF volume and rate from weight delta or explicit input
    weight_pre = data.get("weight_pre")
    weight_post = data.get("weight_post")
    duration_hours = data.get("duration_hours")
    duration_minutes = data.get("duration_minutes")
    
    uf_volume = data.get("uf_volume")
    if uf_volume is None or uf_volume == "":
        if weight_pre is not None and weight_post is not None:
            uf_volume = round((float(weight_pre) - float(weight_post)) * 1000, 1)  # mL
        else:
            uf_volume = None
    else:
        uf_volume = float(uf_volume)
        
    actual_uf_volume = data.get("actual_uf_volume")
    if actual_uf_volume is None or actual_uf_volume == "":
        if uf_volume is not None:
            actual_uf_volume = uf_volume
        elif weight_pre is not None and weight_post is not None:
            actual_uf_volume = round((float(weight_pre) - float(weight_post)) * 1000, 1)  # mL
        else:
            actual_uf_volume = None
    else:
        actual_uf_volume = float(actual_uf_volume)

    uf_rate = None
    if actual_uf_volume is not None and weight_pre is not None:
        total_hours = (float(duration_hours or 0) + float(duration_minutes or 0) / 60) or None
        if total_hours and float(weight_pre) > 0:
            uf_rate = round(actual_uf_volume / (float(weight_pre) * total_hours), 2)  # mL/kg/hr

    rec = SessionRecord(
        patient_id=patient_id,
        session_date=datetime.strptime(session_date, "%Y-%m-%d").date(),
        record_month=month_str,
        entered_by=data.get("entered_by", ""),
        blood_flow_rate=data.get("blood_flow_rate"),
        actual_blood_flow_rate=data.get("actual_blood_flow_rate"),
        dialysate_flow=data.get("dialysate_flow"),
        dialysate_flow_direction=data.get("dialysate_flow_direction"),
        duration_hours=data.get("duration_hours"),
        duration_minutes=data.get("duration_minutes"),
        weight_pre=data.get("weight_pre"),
        weight_post=data.get("weight_post"),
        bp_pre_sys=data.get("bp_pre_sys"),
        bp_pre_dia=data.get("bp_pre_dia"),
        bp_post_sys=data.get("bp_post_sys"),
        bp_post_dia=data.get("bp_post_dia"),
        bp_nadir_sys=data.get("bp_nadir_sys"),
        bp_nadir_dia=data.get("bp_nadir_dia"),
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
        intradialytic_exercise_mins=data.get("intradialytic_exercise_mins"),
        intradialytic_meals_eaten=data.get("intradialytic_meals_eaten", False),
        pre_hd_dyspnea_likert=data.get("pre_hd_dyspnea_likert"),
        post_hd_dyspnea_likert=data.get("post_hd_dyspnea_likert"),
        is_emergency=data.get("is_emergency", False),
        reason_emergency=data.get("reason_emergency"),
        idh_episode=data.get("idh_episode", False),
        muscle_cramps=data.get("muscle_cramps", False),
        urea_peripheral_s=data.get("urea_peripheral_s"),
        urea_arterial_a=data.get("urea_arterial_a"),
        urea_venous_v=data.get("urea_venous_v"),
        access_recirculation_percent=data.get("access_recirculation_percent"),
        access_flow_qa=data.get("access_flow_qa"),
        thrill_grade=data.get("thrill_grade") or "normal",
        bruit_grade=data.get("bruit_grade") or "normal",
        aneurysm_flag=data.get("aneurysm_flag", False),
        steal_signs_flag=data.get("steal_signs_flag", False),
        cannulation_difficulty=data.get("cannulation_difficulty") or "routine",
        cannulation_attempts=data.get("cannulation_attempts"),
        needle_infiltration=data.get("needle_infiltration", False),
        uf_volume=uf_volume,
        actual_uf_volume=actual_uf_volume,
        uf_rate=uf_rate,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    
    # Process symptom report if any symptom data is provided
    if any(data.get(k) is not None and data.get(k) != "" for k in _SONG_HD_KEYS):
        symptom_report = PatientSymptomReport(
            patient_id=patient_id,
            session_date=rec.session_date,
            session_id=rec.id,
            dialysis_recovery_time_mins=data.get("dialysis_recovery_time_mins"),
            tiredness_score=data.get("tiredness_score"),
            energy_level_score=data.get("energy_level_score"),
            sleepiness_severity=data.get("sleepiness_severity"),
            daily_activity_impact=data.get("daily_activity_impact"),
            cognitive_alertness=data.get("cognitive_alertness"),
            post_hd_mood=data.get("post_hd_mood"),
            symptoms=data.get("symptoms", ""),
            severity=data.get("severity"),
            missed_social_or_work_event=data.get("missed_social_or_work_event", False),
            notes=data.get("symptom_notes")
        )
        db.add(symptom_report)
        db.commit()

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
    sess.dialysate_flow_direction = data.get("dialysate_flow_direction")
    sess.duration_hours = data.get("duration_hours")
    sess.duration_minutes = data.get("duration_minutes")
    sess.weight_pre = data.get("weight_pre")
    sess.weight_post = data.get("weight_post")
    sess.bp_pre_sys = data.get("bp_pre_sys")
    sess.bp_pre_dia = data.get("bp_pre_dia")
    sess.bp_post_sys = data.get("bp_post_sys")
    sess.bp_post_dia = data.get("bp_post_dia")
    sess.bp_nadir_sys = data.get("bp_nadir_sys")
    sess.bp_nadir_dia = data.get("bp_nadir_dia")
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
    sess.intradialytic_exercise_mins = data.get("intradialytic_exercise_mins")
    sess.intradialytic_meals_eaten = data.get("intradialytic_meals_eaten", False)
    sess.pre_hd_dyspnea_likert = data.get("pre_hd_dyspnea_likert")
    sess.post_hd_dyspnea_likert = data.get("post_hd_dyspnea_likert")
    sess.is_emergency = data.get("is_emergency", False)
    sess.reason_emergency = data.get("reason_emergency")
    sess.urea_peripheral_s = data.get("urea_peripheral_s")
    sess.urea_arterial_a = data.get("urea_arterial_a")
    sess.urea_venous_v = data.get("urea_venous_v")
    sess.access_recirculation_percent = data.get("access_recirculation_percent")
    sess.access_flow_qa = data.get("access_flow_qa")
    sess.thrill_grade = data.get("thrill_grade") or "normal"
    sess.bruit_grade = data.get("bruit_grade") or "normal"
    sess.aneurysm_flag = data.get("aneurysm_flag", False)
    sess.steal_signs_flag = data.get("steal_signs_flag", False)
    sess.cannulation_difficulty = data.get("cannulation_difficulty") or "routine"
    sess.cannulation_attempts = data.get("cannulation_attempts")
    sess.needle_infiltration = data.get("needle_infiltration", False)

    _wp = data.get("weight_pre")
    _wpo = data.get("weight_post")
    _dh = data.get("duration_hours")
    _dm = data.get("duration_minutes")
    
    _uf_target = data.get("uf_volume")
    if _uf_target is None or _uf_target == "":
        if _wp is not None and _wpo is not None:
            sess.uf_volume = round((float(_wp) - float(_wpo)) * 1000, 1)
        else:
            sess.uf_volume = None
    else:
        sess.uf_volume = float(_uf_target)
        
    _uf_actual = data.get("actual_uf_volume")
    if _uf_actual is None or _uf_actual == "":
        if sess.uf_volume is not None:
            sess.actual_uf_volume = sess.uf_volume
        elif _wp is not None and _wpo is not None:
            sess.actual_uf_volume = round((float(_wp) - float(_wpo)) * 1000, 1)
        else:
            sess.actual_uf_volume = None
    else:
        sess.actual_uf_volume = float(_uf_actual)

    if sess.actual_uf_volume is not None and _wp is not None:
        _total_h = (float(_dh or 0) + float(_dm or 0) / 60) or None
        if _total_h and float(_wp) > 0:
            sess.uf_rate = round(sess.actual_uf_volume / (float(_wp) * _total_h), 2)
        else:
            sess.uf_rate = None
    else:
        sess.uf_rate = None

    # Process symptom report
    symptom_report = db.query(PatientSymptomReport).filter(PatientSymptomReport.session_id == session_id).first()
    if any(data.get(k) is not None and data.get(k) != "" for k in _SONG_HD_KEYS):
        if not symptom_report:
            symptom_report = PatientSymptomReport(
                patient_id=sess.patient_id,
                session_date=sess.session_date,
                session_id=session_id
            )
            db.add(symptom_report)
            
        symptom_report.dialysis_recovery_time_mins = data.get("dialysis_recovery_time_mins")
        symptom_report.tiredness_score = data.get("tiredness_score")
        symptom_report.energy_level_score = data.get("energy_level_score")
        symptom_report.sleepiness_severity = data.get("sleepiness_severity")
        symptom_report.daily_activity_impact = data.get("daily_activity_impact")
        symptom_report.cognitive_alertness = data.get("cognitive_alertness")
        symptom_report.post_hd_mood = data.get("post_hd_mood")
        symptom_report.symptoms = data.get("symptoms", "")
        symptom_report.severity = data.get("severity")
        symptom_report.missed_social_or_work_event = data.get("missed_social_or_work_event", False)
        symptom_report.notes = data.get("symptom_notes")
    elif symptom_report:
        db.delete(symptom_report)

    db.commit()
    db.refresh(sess)
    promote_session_labs(db, sess)
    return sess
