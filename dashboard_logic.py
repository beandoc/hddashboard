from datetime import datetime, date, timedelta
from database import Patient, MonthlyRecord
from sqlalchemy.orm import Session
import calendar

# CLINICALLY VALIDATED THRESHOLDS - Do not change without approval
THRESHOLDS = {
    "HB_MIN": 10.0,
    "HB_WARN": 11.5,
    "HB_DROP_MAX": 1.5,
    "ALB_MIN": 3.5,
    "ALB_BAD": 2.5,
    "PHOS_MAX": 5.5,
    "PHOS_EXTREME": 7.0,
    "IDWG_MAX": 2.5,
    "IPTH_MAX": 300,
    "VIT_D_MIN": 20,
    "PROTEIN_MIN": 1.0,
    "FERRITIN_MAX": 500,
    "TSAT_MIN": 30,
    "TSAT_BAD": 20,
    "ALAT_MAX": 40,
    "ASAT_MAX": 40,
}

def get_current_month_str():
    return datetime.now().strftime("%Y-%m")

def get_month_label(month_str):
    try:
        y, m = map(int, month_str.split("-"))
        return f"{calendar.month_name[m]} {y}"
    except:
        return month_str

def get_prev_month_str(month_str):
    y, m = map(int, month_str.split("-"))
    if m == 1:
        return f"{y-1}-12"
    else:
        return f"{y}-{m-1:02d}"

def compute_dashboard(db: Session, month_str: str):
    patients = db.query(Patient).filter(Patient.is_active == True).all()
    records = db.query(MonthlyRecord).filter(MonthlyRecord.record_month == month_str).all()
    record_map = {r.patient_id: r for r in records}
    
    prev_month_str = get_prev_month_str(month_str)
    prev_records = db.query(MonthlyRecord).filter(MonthlyRecord.record_month == prev_month_str).all()
    prev_record_map = {r.patient_id: r for r in prev_records}

    metrics = {
        "total": len(patients),
        "male": len([p for p in patients if p.sex == "Male"]),
        "female": len([p for p in patients if p.sex == "Female"]),
        "unknown_sex": len([p for p in patients if p.sex not in ["Male", "Female"]]),
        "non_avf": {"count": 0, "names": [], "types": {}},
        "high_idwg": {"count": 0, "names": []},
        "low_albumin": {"count": 0, "names": []},
        "low_calcium": {"count": 0, "names": []},
        "high_phosphorus": {"count": 0, "names": []},
        "iv_iron": {"count": 0, "names": []},
        "todays_hd": {"count": 0, "names": []},
        "hb_drop_alert": {"count": 0, "names": []},
        "dialysis_intensification": {"count": 0, "names": []},
        "high_ipth": {"count": 0, "names": []},
        "low_vit_d": {"count": 0, "names": []},
        "low_protein": {"count": 0, "names": []},
        "elevated_liver": {"count": 0, "names": []},
        "vaccine_due": {"count": 0, "names": []},
        "trend_hb": [],
        "trend_albumin": [],
        "trend_phosphorus": []
    }

    patient_rows = []
    
    # helper for corrected calcium: Ca + 0.8 × (4.0 − Albumin)
    def get_corr_ca(ca, alb):
        if ca is not None and alb is not None:
            return round(ca + 0.8 * (4.0 - alb), 2)
        return ca

    today = date.today()
    day_map = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri", 5: "Sat", 6: "Sun"}
    curr_day = day_map[today.weekday()]

    for p in patients:
        r = record_map.get(p.id)
        prev_r = prev_record_map.get(p.id)
        
        row = {
            "id": p.id,
            "name": p.name,
            "hid": p.hid_no,
            "access": p.access_type,
            "has_record": r is not None,
            "alerts": []
        }

        # Today's HD Patients (Day-based Recurring)
        p_slots = [p.hd_slot_1, p.hd_slot_2, p.hd_slot_3]
        if any(curr_day in str(s) for s in p_slots if s):
            metrics["todays_hd"]["count"] += 1
            metrics["todays_hd"]["names"].append(p.name)

        # Vaccination Alerts
        vac_alert = False
        if p.hep_b_status == "Non-Immune":
            row["alerts"].append("Hep B Non-Immune")
            vac_alert = True
        elif p.hep_b_status == "Unknown" or not p.hep_b_status:
            row["alerts"].append("Hep B Status Unknown")
            vac_alert = True
        
        if p.hep_b_date and (today - p.hep_b_date).days > 365:
            row["alerts"].append("Hep B Titer/Booster Due")
            vac_alert = True
            
        if not p.pneumococcal_date:
            row["alerts"].append("Pneumo Vaccine Needed")
            vac_alert = True
        elif p.pneumococcal_date and (today - p.pneumococcal_date).days > (365 * 5):
            row["alerts"].append("Pneumo Booster Due")
            vac_alert = True
            
        if vac_alert:
            metrics["vaccine_due"]["count"] += 1
            metrics["vaccine_due"]["names"].append(p.name)

        if r:
            row.update({
                "idwg": r.idwg,
                "hb": r.hb,
                "ferritin": r.serum_ferritin,
                "tsat": r.tsat,
                "phosphorus": r.phosphorus,
                "albumin": r.albumin,
                "ipth": r.ipth,
                "vit_d": r.vit_d,
                "protein": r.av_daily_protein,
                "corrected_ca": get_corr_ca(r.calcium, r.albumin)
            })
            
            # Metric logic using THRESHOLDS
            if r.idwg and r.idwg > THRESHOLDS["IDWG_MAX"]:
                metrics["high_idwg"]["count"] += 1
                metrics["high_idwg"]["names"].append(p.name)
                row["alerts"].append("High IDWG")
                
            if r.hb and r.hb < THRESHOLDS["HB_MIN"]:
                row["alerts"].append("Low Hb")
            
            if r.hb and prev_r and prev_r.hb and (prev_r.hb - r.hb) > THRESHOLDS["HB_DROP_MAX"]:
                metrics["hb_drop_alert"]["count"] += 1
                metrics["hb_drop_alert"]["names"].append(p.name)
                row["alerts"].append("Hb Drop")

            if r.albumin and r.albumin < THRESHOLDS["ALB_MIN"]:
                if r.albumin < THRESHOLDS["ALB_BAD"]:
                    metrics["low_albumin"]["count"] += 1
                    metrics["low_albumin"]["names"].append(p.name)
                row["alerts"].append("Low Albumin")

            corr_ca = row["corrected_ca"]
            if corr_ca and corr_ca < 8.5:
                metrics["low_calcium"]["count"] += 1
                metrics["low_calcium"]["names"].append(p.name)
                row["alerts"].append("Low Calcium")

            if r.phosphorus and r.phosphorus > THRESHOLDS["PHOS_MAX"]:
                metrics["high_phosphorus"]["count"] += 1
                metrics["high_phosphorus"]["names"].append(p.name)
                row["alerts"].append("High Phosphorus")
                
                # Dialysis Intensification: Phosphorus rising AND IDWG rising or above 2.5 AND no third HD slot
                phos_rising = prev_r and r.phosphorus > prev_r.phosphorus
                idwg_issue = r.idwg and r.idwg > THRESHOLDS["IDWG_MAX"]
                if phos_rising and idwg_issue and not p.hd_slot_3:
                    metrics["dialysis_intensification"]["count"] += 1
                    metrics["dialysis_intensification"]["names"].append(p.name)
                    row["alerts"].append("Intensify Dialysis")

            # IV Iron Criteria: Hb < 10 AND (Ferritin < 500 OR TSAT < 30)
            hb_low = r.hb and r.hb < THRESHOLDS["HB_MIN"]
            iron_deplete = (r.serum_ferritin and r.serum_ferritin < THRESHOLDS["FERRITIN_MAX"]) or \
                           (r.tsat and r.tsat < THRESHOLDS["TSAT_MIN"])
            if hb_low and iron_deplete:
                metrics["iv_iron"]["count"] += 1
                metrics["iv_iron"]["names"].append(p.name)
                row["alerts"].append("IV Iron Rec")

            if r.ipth and r.ipth > THRESHOLDS["IPTH_MAX"]:
                metrics["high_ipth"]["count"] += 1
                metrics["high_ipth"]["names"].append(p.name)
                row["alerts"].append("High iPTH")

            if r.vit_d and r.vit_d < THRESHOLDS["VIT_D_MIN"]:
                metrics["low_vit_d"]["count"] += 1
                metrics["low_vit_d"]["names"].append(p.name)
                row["alerts"].append("Low Vit D")

            if r.av_daily_protein and r.av_daily_protein < THRESHOLDS["PROTEIN_MIN"]:
                metrics["low_protein"]["count"] += 1
                metrics["low_protein"]["names"].append(p.name)
                row["alerts"].append("Low Protein")

            if (r.ast and r.ast > THRESHOLDS["ASAT_MAX"]) or (r.alt and r.alt > THRESHOLDS["ALAT_MAX"]):
                metrics["elevated_liver"]["count"] += 1
                metrics["elevated_liver"]["names"].append(p.name)
                row["alerts"].append("Elevated LFTs")

            # Trends for chart
            metrics["trend_hb"].append({"patient": p.name, "previous": prev_r.hb if prev_r else None, "current": r.hb})
            metrics["trend_albumin"].append({"patient": p.name, "previous": prev_r.albumin if prev_r else None, "current": r.albumin})
            metrics["trend_phosphorus"].append({"patient": p.name, "previous": prev_r.phosphorus if prev_r else None, "current": r.phosphorus})

        patient_rows.append(row)

    return {
        "metrics": metrics,
        "patient_rows": patient_rows,
        "month_label": get_month_label(month_str),
        "prev_month_label": get_month_label(prev_month_str)
    }

def get_patients_needing_alerts(db: Session, month_str: str):
    data = compute_dashboard(db, month_str)
    patients_with_alerts = []
    alert_map = {row["id"]: row["alerts"] for row in data["patient_rows"] if row["alerts"]}
    
    if not alert_map: return []
    patients = db.query(Patient).filter(Patient.id.in_(alert_map.keys())).all()
    for p in patients:
        patients_with_alerts.append({"patient": p, "alerts": alert_map[p.id]})
    return patients_with_alerts
