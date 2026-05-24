from sqlalchemy.orm import Session, joinedload
from datetime import datetime
import json
import logging
from typing import Optional

from database import Patient, MonthlyRecord, PatientMealRecord, ResearchRecord, SessionRecord, HospitalisationEvent
from alerts import send_entry_alert_email, check_critical_labs, send_critical_lab_alert_email
from dashboard_logic import get_month_label
from validators import validate_hard_limits, validate_lab_values
from services import audit_service

logger = logging.getLogger(__name__)

def _d(s: Optional[str]) -> Optional[datetime.date]:
    return datetime.strptime(s, "%Y-%m-%d").date() if s else None

def calculate_monthly_session_aggregates(db: Session, patient_id: int, month_str: str) -> dict:
    all_sessions = db.query(SessionRecord).filter(
        SessionRecord.patient_id == patient_id
    ).order_by(SessionRecord.session_date.asc()).all()

    month_sessions = [s for s in all_sessions if s.record_month == month_str]
    if not month_sessions:
        return {
            "bp_sys": None,
            "bp_dia": None,
            "idwg": None,
            "ufr": None
        }

    # 1. BP Sys and BP Dia (Average of bp_pre_sys and bp_pre_dia)
    bp_sys_list = [s.bp_pre_sys for s in month_sessions if s.bp_pre_sys is not None]
    bp_dia_list = [s.bp_pre_dia for s in month_sessions if s.bp_pre_dia is not None]
    
    avg_bp_sys = round(sum(bp_sys_list) / len(bp_sys_list), 1) if bp_sys_list else None
    avg_bp_dia = round(sum(bp_dia_list) / len(bp_dia_list), 1) if bp_dia_list else None

    # 2. IDWG (Average of pre-HD weight minus the previous session's post-HD weight)
    idwg_list = []
    for idx, s in enumerate(all_sessions):
        if s.record_month == month_str:
            if idx > 0:
                prev_s = all_sessions[idx - 1]
                if s.weight_pre is not None and prev_s.weight_post is not None:
                    idwg_list.append(s.weight_pre - prev_s.weight_post)
            
    avg_idwg = round(sum(idwg_list) / len(idwg_list), 2) if idwg_list else None

    # 3. UFR (Average ultrafiltration rate: uf_volume / treatment hours / dry_weight * 1000)
    ufr_list = []
    for s in month_sessions:
        if s.uf_rate is not None:
            ufr_list.append(s.uf_rate)
        else:
            duration = (s.duration_hours or 0) + (s.duration_minutes or 0) / 60
            if s.uf_volume is not None and duration > 0:
                p = s.patient
                dry_w = p.dry_weight if p else None
                if dry_w and dry_w > 0:
                    ufr_val = (s.uf_volume * 1000) / duration / dry_w
                    ufr_list.append(ufr_val)
                else:
                    w = s.weight_pre or 70.0
                    ufr_val = (s.uf_volume * 1000) / duration / w
                    ufr_list.append(ufr_val)

    avg_ufr = round(sum(ufr_list) / len(ufr_list), 2) if ufr_list else None

    return {
        "bp_sys": avg_bp_sys,
        "bp_dia": avg_bp_dia,
        "idwg": avg_idwg,
        "ufr": avg_ufr
    }


def save_monthly_record(
    db: Session,
    patient_id: int,
    data: dict,
    actor: str = "unknown",
) -> MonthlyRecord:
    try:
        # Convert TLC from /cmm to thousands at the boundary
        wbc = data.get("wbc_count")
        if wbc is not None and wbc != "":
            try:
                wbc_val = float(wbc)
                if wbc_val > 150.0:  # Entered in /cmm, e.g. 6500
                    data["wbc_count"] = wbc_val / 1000.0
            except (ValueError, TypeError):
                pass

        # Convert Platelet Count from lacs/cmm to ×10³/µL (multiply by 100)
        # User enters e.g. 2.5 (lacs) → stored as 250 (×10³/µL)
        plt = data.get("platelet_count")
        if plt is not None and plt != "":
            try:
                plt_val = float(plt)
                if plt_val > 0:
                    data["platelet_count"] = round(plt_val * 100.0, 1)
            except (ValueError, TypeError):
                pass

        # Convert Neutrophils from % to absolute count (x10^3/uL) at the boundary
        neut = data.get("neutrophil_count")
        if neut is not None and neut != "":
            try:
                neut_val = float(neut)
                if neut_val > 1.0:  # Entered as %, e.g. 65
                    wbc_abs = data.get("wbc_count")
                    if wbc_abs is not None:
                        data["neutrophil_count"] = round(float(wbc_abs) * (neut_val / 100.0), 3)
                    else:
                        data["neutrophil_count"] = None # Cannot calc absolute without WBC
            except (ValueError, TypeError):
                pass

        month_str = data.get("month_str")

        # Sequential fetches on the main DB session (fast, thread-safe, and compatible with SQLite)
        p_obj = db.query(Patient).options(joinedload(Patient.vascular_access)).filter(Patient.id == patient_id).first()
        sessions_this_month = (
            db.query(SessionRecord)
            .filter(
                SessionRecord.patient_id == patient_id,
                SessionRecord.record_month == month_str,
            )
            .order_by(SessionRecord.session_date.asc())
            .all()
            if month_str
            else []
        )
        _prior_rec_cache = (
            db.query(MonthlyRecord)
            .filter(
                MonthlyRecord.patient_id == patient_id,
                MonthlyRecord.record_month < month_str,
            )
            .order_by(MonthlyRecord.record_month.desc())
            .first()
            if month_str
            else None
        )

        # 1. Residual Urine Output Carry-Forward
        ruo = data.get("residual_urine_output")
        if month_str and (ruo is None or ruo == ""):
            if _prior_rec_cache and _prior_rec_cache.residual_urine_output is not None:
                data["residual_urine_output"] = _prior_rec_cache.residual_urine_output

        # 1.5 Calculate monthly BP, IDWG, and UFR from sessions dynamically
        if month_str:

            if sessions_this_month:
                sys_vals = [s.bp_pre_sys for s in sessions_this_month if s.bp_pre_sys is not None]
                dia_vals = [s.bp_pre_dia for s in sessions_this_month if s.bp_pre_dia is not None]
                
                if sys_vals:
                    data["bp_sys"] = round(sum(sys_vals) / len(sys_vals), 1)
                if dia_vals:
                    data["bp_dia"] = round(sum(dia_vals) / len(dia_vals), 1)
                
                idwg_vals = []
                ufr_vals = []
                
                for i, s in enumerate(sessions_this_month):
                    # IDWG: Try weight_pre - previous weight_post, fallback to weight_pre - dry_weight
                    s_idwg = None
                    if s.weight_pre is not None:
                        if i > 0 and sessions_this_month[i-1].weight_post is not None:
                            s_idwg = s.weight_pre - sessions_this_month[i-1].weight_post
                        elif p_obj and p_obj.dry_weight:
                            s_idwg = s.weight_pre - p_obj.dry_weight
                    
                    if s_idwg is not None and s_idwg >= 0:
                        idwg_vals.append(s_idwg)
                    
                    # UFR: UF volume / duration / weight
                    uf_vol = None
                    if s.weight_pre is not None and s.weight_post is not None:
                        uf_vol = s.weight_pre - s.weight_post
                    elif s_idwg is not None:
                        uf_vol = s_idwg
                    
                    hrs = (s.duration_hours or 0) + (s.duration_minutes or 0) / 60.0
                    if uf_vol and uf_vol > 0 and hrs > 0:
                        ref_w = s.weight_post or (p_obj.dry_weight if p_obj else None) or s.weight_pre
                        if ref_w and ref_w > 0:
                            s_ufr = (uf_vol * 1000) / hrs / ref_w
                            ufr_vals.append(s_ufr)
                
                if idwg_vals:
                    data["idwg"] = round(sum(idwg_vals) / len(idwg_vals), 2)
                if ufr_vals:
                    data["ufr"] = round(sum(ufr_vals) / len(ufr_vals), 2)

        # 2. Backend spKt/V and eKt/V Calculation
        pre_urea = data.get("pre_dialysis_urea")
        post_urea = data.get("post_dialysis_urea")
        idwg_val = data.get("idwg")
        pre_weight = data.get("last_prehd_weight")
        dry_weight = data.get("target_dry_weight")

        sp_ktv = None
        e_ktv = None

        if pre_urea and post_urea:
            try:
                pre_u = float(pre_urea)
                post_u = float(post_urea)
                if pre_u > 0 and post_u > 0 and pre_u > post_u:
                    R = post_u / pre_u
                    data["urr"] = round((1 - R) * 100, 1)
                    if R > 0.03:
                        w = None
                        if dry_weight is not None:
                            try: w = float(dry_weight)
                            except: pass
                        if (w is None or w <= 0) and pre_weight is not None:
                            try:
                                pre_w = float(pre_weight)
                                uf = float(idwg_val) if idwg_val is not None else 0.0
                                w = pre_w - uf
                            except:
                                pass
                        if (w is None or w <= 0) and pre_weight is not None:
                            try: w = float(pre_weight)
                            except: pass
                            
                        if w and w > 0:
                            uf_vol = 0.0
                            if idwg_val is not None:
                                try: uf_vol = float(idwg_val)
                                except: pass
                            import math
                            term1 = -math.log(R - 0.03)
                            term2 = (4.0 - 3.5 * R) * (uf_vol / w)
                            sp_ktv = round(term1 + term2, 2)
                            if sp_ktv > 0:
                                e_ktv = round(0.945 * sp_ktv + 0.04, 2)
            except Exception as ktv_err:
                logger.error(f"Error calculating Kt/V on backend: {ktv_err}")

        if sp_ktv is not None:
            data["single_pool_ktv"] = sp_ktv
        if e_ktv is not None:
            data["equilibrated_ktv"] = e_ktv

        # 3. Backend Phosphate Binder Daily Dose Calculation
        pb_strength = data.get("pb_strength")
        pb_freq = data.get("phosphate_binder_freq")
        pb_dose = data.get("phosphate_binder_dose_mg")
        
        if pb_strength and pb_freq and (pb_dose is None or pb_dose == ""):
            try:
                strength = float(pb_strength)
                multiplier = 0
                if pb_freq == "OD": multiplier = 1
                elif pb_freq == "BD": multiplier = 2
                elif pb_freq == "TDS": multiplier = 3
                elif pb_freq == "QID": multiplier = 4
                
                data["phosphate_binder_dose_mg"] = strength * multiplier
            except Exception as pb_err:
                logger.error(f"Error calculating phosphate binder dose on backend: {pb_err}")

        # 4. Backend Nutrition Averages and Carry-Forward
        p_dry_weight = None
        if dry_weight is not None:
            try: p_dry_weight = float(dry_weight)
            except: pass
        if (p_dry_weight is None or p_dry_weight <= 0) and p_obj:
            p_dry_weight = p_obj.dry_weight

        avg_cal = None
        avg_prot = None
        
        if month_str:
            try:
                year, month = map(int, month_str.split("-"))
                import calendar
                from datetime import date
                _, last_day = calendar.monthrange(year, month)
                start_date = date(year, month, 1)
                end_date = date(year, month, last_day)
                
                meal_records = db.query(PatientMealRecord).filter(
                    PatientMealRecord.patient_id == patient_id,
                    PatientMealRecord.date >= start_date,
                    PatientMealRecord.date <= end_date
                ).all()
                
                if meal_records:
                    daily_stats = {}
                    for mr in meal_records:
                        d_key = mr.date
                        if d_key not in daily_stats:
                            daily_stats[d_key] = {"calories": 0.0, "protein": 0.0}
                        daily_stats[d_key]["calories"] += (mr.calories or 0.0)
                        daily_stats[d_key]["protein"] += (mr.protein or 0.0)
                        
                    num_days = len(daily_stats)
                    sum_cal = sum(s["calories"] for s in daily_stats.values())
                    sum_prot = sum(s["protein"] for s in daily_stats.values())
                    avg_cal = round(sum_cal / num_days, 1)
                    avg_prot_g = sum_prot / num_days
                    
                    if p_dry_weight and p_dry_weight > 0:
                        avg_prot = round(avg_prot_g / p_dry_weight, 2)
                    else:
                        avg_prot = round(avg_prot_g, 2)
            except Exception as nutrition_err:
                logger.error(f"Error calculating nutrition averages on backend: {nutrition_err}")

        if avg_cal is not None:
            data["av_daily_calories"] = avg_cal
        if avg_prot is not None:
            data["av_daily_protein"] = avg_prot

        if month_str and (data.get("av_daily_calories") is None or data.get("av_daily_calories") == ""):
            if _prior_rec_cache and _prior_rec_cache.av_daily_calories is not None:
                data["av_daily_calories"] = _prior_rec_cache.av_daily_calories
                data["av_daily_protein"] = _prior_rec_cache.av_daily_protein

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

        user_role = data.get("role")
        if user_role is None:
            user_role = "admin"

        if user_role in ["admin", "doctor"]:
            issues_val = data.get("issues", "")
        else:
            issues_val = rec.issues if rec else ""

        # Protect NT-ProBNP (research variable) from being cleared if hidden in the UI
        is_research = db.query(ResearchRecord).filter(ResearchRecord.patient_id == patient_id).first() is not None
        if is_research:
            nt_probnp_val = data.get("nt_probnp")
        else:
            nt_probnp_val = rec.nt_probnp if rec else None

        fields = dict(
            idwg=data.get("idwg"),
            bp_sys=data.get("bp_sys"),
            bp_dia=data.get("bp_dia"),
            ufr=data.get("ufr"),
            av_daily_calories=data.get("av_daily_calories"),
            av_daily_protein=data.get("av_daily_protein"),
            last_prehd_weight=data.get("last_prehd_weight"),
            hb=data.get("hb"),
            hct=data.get("hct"),
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
            ast=data.get("ast"),
            alt=data.get("alt"),
            vit_d=data.get("vit_d"),
            ipth=data.get("ipth"),
            urr=data.get("urr"),
            crp=data.get("crp"),
            issues=issues_val,
            entered_by=data.get("entered_by", ""),
            single_pool_ktv=data.get("single_pool_ktv"),
            equilibrated_ktv=data.get("equilibrated_ktv"),
            pre_dialysis_urea=data.get("pre_dialysis_urea"),
            post_dialysis_urea=data.get("post_dialysis_urea"),
            serum_creatinine=data.get("serum_creatinine"),
            post_dialysis_creatinine=data.get("post_dialysis_creatinine"),
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
            antihypertensive_count=len(meds_list) if meds_list else data.get("antihypertensive_count"),
            antihypertensive_details=antihypertensive_details_json,
            hospitalization_details=hosp_details_json if hosp_details_json else (rec.hospitalization_details if rec else ""),
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

        # Sync certain fields back to Patient model — re-fetch in the main db session
        # so SQLAlchemy can lazy-load relations (p_obj came from a closed thread session).
        p = db.query(Patient).filter(Patient.id == patient_id).first()
        if p:
            if user_role in ["admin", "doctor"]:
                if "clinical_background" in data:
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

        # Save total_protein, triglycerides, hdl_cholesterol into dynamic_data
        _dd = dict(rec.dynamic_data) if rec.dynamic_data else {}
        for _key in ("total_protein", "triglycerides", "hdl_cholesterol", "bs_fasting", "bs_pp"):
            _val = data.get(_key)
            if _val is not None and _val != "":
                try:
                    _dd[_key] = float(_val)
                except (ValueError, TypeError):
                    pass
        rec.dynamic_data = _dd

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
