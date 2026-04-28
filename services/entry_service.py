from sqlalchemy.orm import Session
from datetime import datetime
import json
from typing import Optional

from database import Patient, MonthlyRecord
from alerts import send_entry_alert_email
from dashboard_logic import get_month_label

def _d(s: Optional[str]) -> Optional[datetime.date]:
    return datetime.strptime(s, "%Y-%m-%d").date() if s else None

def save_monthly_record(db: Session, patient_id: int, data: dict) -> MonthlyRecord:
    month_str = data["month_str"]
    idwg = data.get("idwg")
    if idwg is not None and idwg > 15:
        idwg = None

    # Handle antihypertensive medications
    meds_list = []
    names = data.get("antihypertensive_name", [])
    doses = data.get("antihypertensive_dose", [])
    freqs = data.get("antihypertensive_freq", [])
    for n, d, f in zip(names, doses, freqs):
        if n.strip():
            meds_list.append({"name": n.strip(), "dose": d.strip(), "freq": f.strip()})
    antihypertensive_details_json = json.dumps(meds_list) if meds_list else ""

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
        platelet_count=data.get("platelet_count"),
        hba1c=data.get("hba1c"),
        vitamin_d_analog_dose=data.get("vitamin_d_analog_dose", ""),
        phosphate_binder_type=data.get("phosphate_binder_type", ""),
        antihypertensive_count=len(meds_list) if meds_list else data.get("antihypertensive_count"),
        antihypertensive_details=antihypertensive_details_json,
        hrqol_score=data.get("hrqol_score"),
        hospitalization_this_month=data.get("hospitalization_this_month", False),
        hospitalization_date=_d(data.get("hospitalization_date")),
        hospitalization_icd_code=data.get("hospitalization_icd_code", ""),
    )

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

    db.commit()
    db.refresh(rec)

    # Automated alerting
    if p:
        _alerts = []
        _raw = (data.get("access_type") or p.access_type or "").upper()
        if _raw and "AVF" not in _raw:
            _alerts.append("Non-AVF Access")
        
        hb = data.get("hb")
        if hb and hb < 9:
            _alerts.append("Low Hb (<9)")
            
        alb = data.get("albumin")
        if alb and alb < 2.5:
            _alerts.append("Low Albumin")
            
        phos = data.get("phosphorus")
        if phos and phos > 5.5:
            _alerts.append("High Phosphorus")
            
        ca = data.get("calcium")
        _corr_ca = (ca + 0.8 * (4.0 - alb)) if (ca and alb) else ca
        if _corr_ca and _corr_ca < 8.0:
            _alerts.append("Low Corrected Calcium")
            
        if idwg and idwg > 2.5:
            _alerts.append("High Interdialytic Weight Gain")

        if _alerts:
            send_entry_alert_email(
                patient_name=p.name,
                hid=p.hid_no,
                month_label=get_month_label(month_str),
                alerts=_alerts,
                labs={
                    "hb": hb,
                    "albumin": alb,
                    "phosphorus": phos,
                    "corrected_ca": _corr_ca,
                    "idwg": idwg,
                    "ipth": data.get("ipth")
                },
                entered_by=data.get("entered_by", "")
            )

    return rec
