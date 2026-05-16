from sqlalchemy.orm import Session
from datetime import datetime
import json
import logging
from typing import Optional

from database import Patient, MonthlyRecord
from alerts import send_entry_alert_email, check_critical_labs, send_critical_lab_alert_email
from dashboard_logic import get_month_label
from validators import validate_hard_limits, validate_lab_values
from services import audit_service

logger = logging.getLogger(__name__)

def _d(s: Optional[str]) -> Optional[datetime.date]:
    return datetime.strptime(s, "%Y-%m-%d").date() if s else None

def save_monthly_record(
    db: Session,
    patient_id: int,
    data: dict,
    actor: str = "unknown",
) -> MonthlyRecord:
    try:
        # Hard limits — physiologically impossible values. Raises ValueError.
        # This propagates to the router which returns a user-visible 400 error.
        validate_hard_limits(data)

        # Soft warnings — outside typical range but not impossible. Logged only.
        for w in validate_lab_values(data):
            logger.warning("Patient %s: %s", patient_id, w)

        month_str = data.get("month_str")
        if not month_str:
            raise ValueError("month_str is required")

        idwg = data.get("idwg")
        if idwg is not None:
            try:
                idwg = float(idwg)
                if idwg > 15:
                    raise ValueError(
                        f"IDWG value {idwg} kg exceeds physiological maximum of 15 kg. "
                        "Please verify the measurement."
                    )
            except ValueError:
                raise
            except TypeError:
                idwg = None

        # Handle antihypertensive medications
        meds_list = []
        names = data.get("antihypertensive_name", [])
        if isinstance(names, str): names = [names]
        doses = data.get("antihypertensive_dose", [])
        if isinstance(doses, str): doses = [doses]
        freqs = data.get("antihypertensive_freq", [])
        if isinstance(freqs, str): freqs = [freqs]

        for n, d, f in zip(names, doses, freqs):
            if n and str(n).strip():
                meds_list.append({
                    "name": str(n).strip(), 
                    "dose": str(d).strip() if d else "", 
                    "freq": str(f).strip() if f else ""
                })
        antihypertensive_details_json = json.dumps(meds_list) if meds_list else ""

        # Handle multiple hospitalizations
        hosp_list = []
        h_dates = data.get("hospitalization_date", [])
        if isinstance(h_dates, str): h_dates = [h_dates]
        h_diags = data.get("hospitalization_diagnosis", [])
        if isinstance(h_diags, str): h_diags = [h_diags]
        h_codes = data.get("hospitalization_icd_code", [])
        if isinstance(h_codes, str): h_codes = [h_codes]
        h_icds  = data.get("hospitalization_icd_diagnosis", [])
        if isinstance(h_icds, str): h_icds = [h_icds]
        
        for dt, dg, cd, ic in zip(h_dates, h_diags, h_codes, h_icds):
            if (dg and str(dg).strip()) or (cd and str(cd).strip()):
                hosp_list.append({
                    "date": str(dt) if dt else "",
                    "diagnosis": str(dg).strip() if dg else "",
                    "icd_code": str(cd).strip() if cd else "",
                    "icd_diagnosis": str(ic).strip() if ic else ""
                })
        hosp_details_json = json.dumps(hosp_list) if hosp_list else ""

        rec = db.query(MonthlyRecord).filter(
            MonthlyRecord.patient_id == patient_id,
            MonthlyRecord.record_month == month_str
        ).first()

        fields = dict(
            access_type=data.get("access_type", ""),
            target_dry_weight=data.get("target_dry_weight"),
            idwg=idwg,
            last_prehd_weight=data.get("last_prehd_weight"),
            hb=data.get("hb"),
            bp_sys=data.get("bp_sys"),
            bp_dia=data.get("bp_dia"),
            serum_ferritin=data.get("serum_ferritin"),
            tsat=data.get("tsat"),
            serum_iron=data.get("serum_iron"),
            epo_mircera_dose=data.get("epo_mircera_dose", ""),
            desidustat_dose=data.get("desidustat_dose", ""),
            epo_weekly_units=data.get("epo_weekly_units"),
            esa_type=data.get("esa_type", ""),
            calcium=data.get("calcium"),
            alkaline_phosphate=data.get("alkaline_phosphate"),
            phosphorus=data.get("phosphorus"),
            albumin=data.get("albumin"),
            prealbumin=data.get("prealbumin"),
            npcr=data.get("npcr"),
            sga_score=data.get("sga_score", ""),
            mis_score=data.get("mis_score"),
            ast=data.get("ast"),
            alt=data.get("alt"),
            vit_d=data.get("vit_d"),
            ipth=data.get("ipth"),
            av_daily_calories=data.get("av_daily_calories"),
            av_daily_protein=data.get("av_daily_protein"),
            urr=data.get("urr"),
            crp=data.get("crp"),
            issues=data.get("issues", ""),
            entered_by=data.get("entered_by", ""),
            single_pool_ktv=data.get("single_pool_ktv"),
            equilibrated_ktv=data.get("equilibrated_ktv"),
            pre_dialysis_urea=data.get("pre_dialysis_urea"),
            post_dialysis_urea=data.get("post_dialysis_urea"),
            serum_creatinine=data.get("serum_creatinine"),
            residual_urine_output=data.get("residual_urine_output"),
            tibc=data.get("tibc"),
            iv_iron_product=data.get("iv_iron_product", ""),
            iv_iron_dose=data.get("iv_iron_dose"),
            iv_iron_date=_d(data.get("iv_iron_date")),
            serum_sodium=data.get("serum_sodium"),
            serum_potassium=data.get("serum_potassium"),
            serum_bicarbonate=data.get("serum_bicarbonate"),
            serum_uric_acid=data.get("serum_uric_acid"),
            total_cholesterol=data.get("total_cholesterol"),
            ldl_cholesterol=data.get("ldl_cholesterol"),
            wbc_count=data.get("wbc_count"),
            neutrophil_count=data.get("neutrophil_count"),
            platelet_count=data.get("platelet_count"),
            hba1c=data.get("hba1c"),
            vitamin_d_analog_dose=data.get("vitamin_d_analog_dose", ""),
            phosphate_binder_type=data.get("phosphate_binder_type", ""),
            pb_strength=data.get("pb_strength"),
            phosphate_binder_dose_mg=data.get("phosphate_binder_dose_mg"),
            phosphate_binder_freq=data.get("phosphate_binder_freq", ""),
            nt_probnp=data.get("nt_probnp"),
            ejection_fraction=data.get("ejection_fraction"),
            diastolic_dysfunction=data.get("diastolic_dysfunction", ""),
            echo_date=_d(data.get("echo_date")),
            antihypertensive_count=len(meds_list) if meds_list else data.get("antihypertensive_count"),
            antihypertensive_details=antihypertensive_details_json,
            hrqol_score=data.get("hrqol_score"),
            hospitalization_this_month=data.get("hospitalization_this_month", False),
            hospitalization_date=_d(hosp_list[0]["date"]) if hosp_list else None,
            hospitalization_diagnosis=hosp_list[0]["diagnosis"] if hosp_list else "",
            hospitalization_icd_code=hosp_list[0]["icd_code"] if hosp_list else "",
            hospitalization_icd_diagnosis=hosp_list[0]["icd_diagnosis"] if hosp_list else "",
            hospitalization_details=hosp_details_json,
            blood_transfusion_units=data.get("blood_transfusion_units"),
            transfusion_date=data.get("transfusion_date") or None,
        )

        is_new = rec is None
        if rec:
            for k, v in fields.items():
                setattr(rec, k, v)
            rec.timestamp = datetime.utcnow()
        else:
            rec = MonthlyRecord(patient_id=patient_id, record_month=month_str, **fields)
            db.add(rec)

        # Sync certain fields back to Patient model
        p = db.query(Patient).filter(Patient.id == patient_id).first()
        if p:
            if data.get("access_type"):
                p.access_type = data["access_type"]
            if data.get("target_dry_weight") is not None:
                p.dry_weight = data["target_dry_weight"]
            if data.get("clinical_background"):
                p.clinical_background = data["clinical_background"]
            if data.get("ejection_fraction") is not None:
                p.ejection_fraction = data["ejection_fraction"]
            if data.get("diastolic_dysfunction"):
                p.diastolic_dysfunction = data["diastolic_dysfunction"]
            if data.get("echo_date"):
                p.echo_date = _d(data["echo_date"])

        # Flush assigns rec.id for new records before we write the audit row.
        # The audit log and the business record then commit atomically.
        db.flush()
        audit_service.log_write(
            db,
            table="monthly_records",
            record_id=rec.id,
            action="create" if is_new else "update",
            actor=actor,
            changes={"patient_id": patient_id, "record_month": month_str},
        )

        try:
            db.commit()
            db.refresh(rec)
        except Exception as commit_err:
            db.rollback()
            logger.error(f"COMMIT FAILED for patient {patient_id}: {commit_err}")
            raise commit_err

        # Automated alerting (safe-wrapped in try/except)
        try:
            if p:
                _alerts = []
                _raw_access = (data.get("access_type") or p.access_type or "").upper()
                if _raw_access and "AVF" not in _raw_access:
                    _alerts.append("Non-AVF Access")
                
                hb_val = data.get("hb")
                if hb_val and float(hb_val) < 9:
                    _alerts.append("Low Hb (<9)")
                    
                alb_val = data.get("albumin")
                if alb_val and float(alb_val) < 2.5:
                    _alerts.append("Low Albumin")
                    
                phos_val = data.get("phosphorus")
                if phos_val and float(phos_val) > 5.5:
                    _alerts.append("High Phosphorus")
                    
                ca_val = data.get("calcium")
                _corr_ca = (float(ca_val) + 0.8 * (4.0 - float(alb_val))) if (ca_val and alb_val) else (float(ca_val) if ca_val else None)
                if _corr_ca and _corr_ca < 8.0:
                    _alerts.append("Low Corrected Calcium")
                    
                if idwg and idwg > 2.5:
                    _alerts.append("High Interdialytic Weight Gain")

                bt_units = data.get("blood_transfusion_units")
                if bt_units and int(bt_units) > 0:
                    _alerts.append(f"Blood Transfusion this month ({bt_units} PRBC unit(s))")

                if p.mail_trigger and _alerts:
                    from alerts import send_entry_alert_email
                    send_entry_alert_email(
                        patient_name=p.name,
                        hid=p.hid_no,
                        month_label=get_month_label(month_str),
                        alerts=_alerts,
                        labs={
                            "hb": hb_val,
                            "albumin": alb_val,
                            "phosphorus": phos_val,
                            "corrected_ca": _corr_ca,
                            "idwg": idwg,
                            "ipth": data.get("ipth")
                        },
                        entered_by=data.get("entered_by", "")
                    )

                if p.mail_trigger:
                    critical_hits = check_critical_labs(data)
                    if critical_hits:
                        from alerts import send_critical_lab_alert_email
                        send_critical_lab_alert_email(
                            patient_name=p.name,
                            hid=p.hid_no,
                            month_label=get_month_label(month_str),
                            critical_hits=critical_hits,
                            entered_by=data.get("entered_by", "")
                        )
        except Exception as alert_err:
            logger.error(f"Alerting failed (non-critical): {alert_err}")

        return rec

    except Exception as e:
        import traceback
        logger.error(f"CRITICAL ERROR in save_monthly_record for patient {patient_id}: {e}")
        logger.error(traceback.format_exc())
        raise e
