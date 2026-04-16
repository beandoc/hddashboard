from datetime import datetime, date, timedelta
import calendar
from sqlalchemy.orm import Session
from database import Patient, MonthlyRecord

try:
    import numpy as np
    from sklearn.linear_model import LinearRegression
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False

# CLINICALLY VALIDATED THRESHOLDS
THRESHOLDS = {
    "HB_MIN": 10.0, "HB_WARN": 11.5, "HB_DROP_MAX": 1.5,
    "ALB_MIN": 3.5, "ALB_BAD": 2.5, "PHOS_MAX": 5.5,
    "IDWG_MAX": 2.5, "IPTH_MAX": 300, "VIT_D_MIN": 20,
    "FERRITIN_MAX": 500, "TSAT_MIN": 30
}

def get_current_month_str():
    return datetime.now().strftime("%Y-%m")

def get_month_label(month_str):
    try:
        y, m = map(int, month_str.split("-"))
        return f"{calendar.month_name[m]} {y}"
    except: return month_str

def get_prev_month_str(month_str, months_ago=1):
    try:
        y, m = map(int, month_str.split("-"))
        total_months = y * 12 + (m - 1) - months_ago
        return f"{total_months // 12}-{(total_months % 12) + 1:02d}"
    except: return month_str

def compute_dashboard(db: Session, month_str: str):
    patients = db.query(Patient).filter(Patient.is_active == True).all()
    
    # --- BULK LOADING (Performance optimization to avoid N+1 queries) ---
    prev_m = get_prev_month_str(month_str)
    m3_m = get_prev_month_str(month_str, 3)
    
    records = {r.patient_id: r for r in db.query(MonthlyRecord).filter(MonthlyRecord.record_month == month_str).all()}
    prev_recs = {r.patient_id: r for r in db.query(MonthlyRecord).filter(MonthlyRecord.record_month==prev_m).all()}
    m3_recs = {r.patient_id: r for r in db.query(MonthlyRecord).filter(MonthlyRecord.record_month==m3_m).all()}

    metrics = {
        "total": len(patients),
        "male": len([p for p in patients if p.sex == "Male"]),
        "female": len([p for p in patients if p.sex == "Female"]),
        "todays_hd": {"count": 0, "names": []},
        "high_idwg": {"count": 0, "names": []},
        "low_albumin": {"count": 0, "names": []},
        "high_phosphorus": {"count": 0, "names": []},
        "hb_drop_alert": {"count": 0, "names": []},
        "iv_iron": {"count": 0, "names": []},
        "trend_hb": [], "trend_albumin": [], "trend_phosphorus": []
    }

    patient_rows = []
    today = date.today()
    curr_day = {0:"Mon", 1:"Tue", 2:"Wed", 3:"Thu", 4:"Fri", 5:"Sat", 6:"Sun"}[today.weekday()]

    for p in patients:
        r, prev_r, m3_r = records.get(p.id), prev_recs.get(p.id), m3_recs.get(p.id)
        row = {"id": p.id, "name": p.name, "hid": p.hid_no, "access": p.access_type, "has_record": r is not None, "alerts": []}

        # Slot Check
        if any(curr_day in str(s) for s in [p.hd_slot_1, p.hd_slot_2, p.hd_slot_3] if s):
            metrics["todays_hd"]["count"] += 1; metrics["todays_hd"]["names"].append(p.name)

        if r:
            row.update({"idwg": r.idwg, "hb": r.hb, "phosphorus": r.phosphorus, "albumin": r.albumin})
            
            # Clinical Logic
            if r.idwg and r.idwg > THRESHOLDS["IDWG_MAX"]: 
                metrics["high_idwg"]["count"] += 1; row["alerts"].append("High IDWG")
            if r.hb and r.hb < THRESHOLDS["HB_MIN"]: row["alerts"].append("Low Hb")
            if r.hb and prev_r and prev_r.hb and (prev_r.hb - r.hb) > THRESHOLDS["HB_DROP_MAX"]:
                metrics["hb_drop_alert"]["count"] += 1; row["alerts"].append("Hb Drop")
            if r.albumin and r.albumin < THRESHOLDS["ALB_MIN"]: 
                metrics["low_albumin"]["count"] += 1; row["alerts"].append("Low Albumin")
            
            # ERI calculation (O(1) with bulk map)
            if r.hb and m3_r and m3_r.hb and r.epo_weekly_units:
                units_1k = r.epo_weekly_units / 1000.0
                row["eri"] = round((r.hb - m3_r.hb) / units_1k, 3) if units_1k > 0 else 0
            else: row["eri"] = None

            # ML Block (Optimized)
            if ML_AVAILABLE:
                hbs = [rec.hb for rec in p.records if rec.hb is not None]
                if len(hbs) >= 3:
                    model = LinearRegression().fit(np.arange(len(hbs)).reshape(-1, 1), np.array(hbs))
                    pred = model.predict([[len(hbs)]])[0]
                    row["projected_hb"] = round(float(pred), 2)
                    if pred < 10.0: row["alerts"].append("🔮 Projected Low Hb")
            
            metrics["trend_hb"].append({"patient": p.name, "previous": prev_r.hb if prev_r else None, "current": r.hb})
        patient_rows.append(row)

    return {
        "metrics": metrics, "patient_rows": patient_rows,
        "month_label": get_month_label(month_str), 
        "prev_month_label": get_month_label(prev_m)
    }

def get_patients_needing_alerts(db: Session, month_str: str):
    data = compute_dashboard(db, month_str)
    alert_map = {row["id"]: row["alerts"] for row in data["patient_rows"] if row["alerts"]}
    if not alert_map: return []
    patients = db.query(Patient).filter(Patient.id.in_(alert_map.keys())).all()
    return [{"patient": p, "alerts": alert_map[p.id]} for p in patients]
