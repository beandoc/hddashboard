
import statistics
import logging
from datetime import datetime, date
from sqlalchemy.orm import Session
from database import Patient, MonthlyRecord
from ml_analytics import (
    predict_hb_trajectory, assess_albumin_decline, 
    predict_mortality_risk, compute_deterioration_risk,
    compute_target_score, detect_epo_hyporesponse
)
try:
    from sklearn.metrics import roc_auc_score as _roc_auc_score
    _SKLEARN_AVAILABLE = True
except ImportError:
    _SKLEARN_AVAILABLE = False

logger = logging.getLogger(__name__)

def get_model_performance_metrics(db: Session):
    """
    Computes all validation metrics for the Clinical Analytics Engine.
    """
    patients = db.query(Patient).all()
    
    hb_errors = []
    alb_errors = []
    
    mort_y_true = []
    mort_y_pred = []
    
    det_y_true = []
    det_y_pred = []
    
    for p in patients:
        records = db.query(MonthlyRecord).filter(MonthlyRecord.patient_id == p.id).order_by(MonthlyRecord.record_month.asc()).all()
        if not records:
            continue
            
        # 1. Hb & Albumin MAE (Walk-forward)
        if len(records) >= 5:
            for i in range(4, len(records)):
                train_records = records[:i]
                actual_hb = records[i].hb
                actual_alb = records[i].albumin
                
                # Hb Prediction
                if actual_hb is not None:
                    train_df = [{"month": r.record_month, "hb": r.hb} for r in train_records]
                    pred_hb = predict_hb_trajectory(train_df[::-1]).get("next_predicted")
                    if pred_hb is not None:
                        hb_errors.append(abs(actual_hb - pred_hb))
                        
                # Albumin Prediction
                if actual_alb is not None:
                    train_df = [{"month": r.record_month, "albumin": r.albumin} for r in train_records]
                    pred_alb = assess_albumin_decline(train_df[::-1]).get("predicted")
                    if pred_alb is not None:
                        alb_errors.append(abs(actual_alb - pred_alb))

        # 2. Mortality Calibration (baseline prediction vs 1-yr outcome)
        try:
            first_month_str = records[0].record_month
            first_date = datetime.strptime(first_month_str, "%Y-%m").date()
            
            baseline_df = [{"month": r.record_month, "hb": r.hb, "albumin": r.albumin, "wbc_count": r.wbc_count, "crp": r.crp, "hospitalization_this_month": r.hospitalization_this_month} for r in records[:1]]
            pt_info = {"age": p.age, "cad_status": p.cad_status, "dm_status": p.dm_status, "chf_status": p.chf_status, "ef": p.ejection_fraction}
            
            mort_prob = predict_mortality_risk(baseline_df, pt_info).get("risk_probability")
            
            died_within_1yr = False
            if p.current_survival_status == "Deceased" and p.date_of_death:
                days_to_death = (p.date_of_death - first_date).days
                if 0 <= days_to_death <= 365:
                    died_within_1yr = True
            
            is_valid_mort_sample = False
            if died_within_1yr:
                is_valid_mort_sample = True
            else:
                last_record_month = records[-1].record_month
                last_date = datetime.strptime(last_record_month, "%Y-%m").date()
                if (last_date - first_date).days >= 330:
                    is_valid_mort_sample = True
            
            if is_valid_mort_sample and mort_prob is not None:
                mort_y_pred.append(mort_prob)
                mort_y_true.append(1 if died_within_1yr else 0)
        except:
            pass

        # 3. Deterioration Risk AUC (Month T features vs T+1 hospitalization)
        if len(records) >= 2:
            for i in range(len(records) - 1):
                train_records = records[:i+1]
                next_record = records[i+1]
                
                # Features at T
                train_df = [{"month": r.record_month, "hb": r.hb, "albumin": r.albumin, "idwg": r.idwg, "target_dry_weight": r.target_dry_weight} for r in train_records]
                hb_res = predict_hb_trajectory(train_df[::-1])
                alb_res = assess_albumin_decline(train_df[::-1])
                target_sc = compute_target_score(train_df[::-1])
                epo_res = detect_epo_hyporesponse(train_df[::-1])
                
                pt_info = {"age": p.age}
                det_risk_res = compute_deterioration_risk(hb_res, alb_res, target_sc, epo_res, pt_info)
                
                # Use risk_score as probability (heuristic or model)
                score = det_risk_res.get("risk_score", 0) / 100.0
                
                # Outcome at T+1
                hosp = 1 if (next_record.hospitalization_this_month or next_record.hospitalization_diagnosis) else 0
                
                det_y_pred.append(score)
                det_y_true.append(hosp)

    # Aggregate Results
    results = {
        "hb_mae": statistics.mean(hb_errors) if hb_errors else None,
        "hb_n": len(hb_errors),
        "alb_mae": statistics.mean(alb_errors) if alb_errors else None,
        "alb_n": len(alb_errors),
        "mort_c_index": None,
        "mort_n": len(mort_y_true),
        "det_auc": None,
        "det_n": len(det_y_true)
    }
    
    if _SKLEARN_AVAILABLE and len(set(mort_y_true)) > 1:
        try: results["mort_c_index"] = _roc_auc_score(mort_y_true, mort_y_pred)
        except: pass

    if _SKLEARN_AVAILABLE and len(set(det_y_true)) > 1:
        try: results["det_auc"] = _roc_auc_score(det_y_true, det_y_pred)
        except: pass
        
    return results
