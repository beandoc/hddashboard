from celery_app import celery_app
from database import SessionLocal, Patient, AlertLog, MonthlyRecord, MLPrediction, MLModelMetrics, PatientFeatureSnapshot
from dashboard_logic import get_patients_needing_alerts, get_month_label, get_current_month_str
from alerts import send_bulk_whatsapp_alerts, send_ward_email, build_schedule_message, send_whatsapp
import logging
import json
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# ── Calibration slope drift threshold ─────────────────────────────────────────
_SLOPE_DRIFT_THRESHOLD = 0.15   # alert when |slope - 1.0| > 15 %

@celery_app.task(bind=True, acks_late=True, reject_on_worker_lost=True,
                max_retries=3, default_retry_delay=60)
def task_send_bulk_whatsapp(self, month_str: str = None):
    db = SessionLocal()
    try:
        month = month_str or get_current_month_str()
        alert_patients = get_patients_needing_alerts(db, month)
        if not alert_patients:
            return "No alerts to send"

        results = send_bulk_whatsapp_alerts(alert_patients, get_month_label(month))
        failed = []
        for r in results.get("results", []):
            p = db.query(Patient).filter(Patient.name == r["name"]).first()
            if p:
                status = "sent" if r["status"] == "sent" else "failed"
                db.add(AlertLog(
                    patient_id=p.id,
                    alert_type="whatsapp",
                    status=status,
                    message_preview=r.get("sid") or r.get("error") or ""
                ))
                if status == "failed":
                    failed.append(r["name"])
        db.commit()
        if failed:
            logger.warning("WhatsApp delivery failed for: %s — will retry", failed)
            raise self.retry(exc=RuntimeError(f"delivery failed: {failed}"))
        return results["message"]
    except self.MaxRetriesExceededError:
        logger.error("task_send_bulk_whatsapp exhausted retries; routing to dead_letter")
        raise
    finally:
        db.close()


@celery_app.task(bind=True, acks_late=True, reject_on_worker_lost=True,
                max_retries=3, default_retry_delay=120)
def task_send_ward_email(self, month_str: str = None):
    db = SessionLocal()
    try:
        month = month_str or get_current_month_str()
        alert_patients = get_patients_needing_alerts(db, month)
        if not alert_patients:
            return "No alerts to send"

        success, detail = send_ward_email(alert_patients, get_month_label(month), month[:4])
        db.add(AlertLog(
            alert_type="email",
            alert_reason=f"Ward report {month}",
            status="sent" if success else "failed",
            message_preview=detail
        ))
        db.commit()
        if not success:
            raise self.retry(exc=RuntimeError(detail))
        return detail
    except self.MaxRetriesExceededError:
        logger.error("task_send_ward_email exhausted retries; routing to dead_letter")
        raise
    finally:
        db.close()

@celery_app.task
def task_send_schedule_reminder(patient_id: int):
    db = SessionLocal()
    try:
        p = db.query(Patient).filter(Patient.id == patient_id).first()
        if not p or not p.contact_no:
            return "Patient not found or no contact number"

        slots = [p.hd_slot_1, p.hd_slot_2, p.hd_slot_3]
        message = build_schedule_message(p.name, slots)
        success, detail = send_whatsapp(p.contact_no, message)

        log = AlertLog(
            patient_id=p.id,
            alert_type="whatsapp_schedule",
            status="sent" if success else "failed",
            message_preview=detail
        )
        db.add(log)
        db.commit()
        return "Sent" if success else detail
    finally:
        db.close()


# ── MLOps: weekly performance + calibration drift check ──────────────────────

@celery_app.task(acks_late=True, reject_on_worker_lost=True)
def task_compute_model_metrics(model_name: str = "deterioration_v1", lookback_days: int = 90):
    """Compute PR-AUC, Brier score, and calibration slope for the trailing window.

    Runs every Monday via Celery beat.  Writes one MLModelMetrics row per call
    and sends an alert email when calibration slope drifts beyond ±15 % of 1.0.
    """
    try:
        import numpy as np
        from sklearn.metrics import (
            average_precision_score, brier_score_loss, roc_auc_score
        )
        import statsmodels.api as sm
    except ImportError as exc:
        logger.error("MLOps metrics task missing dependency: %s", exc)
        return f"dependency missing: {exc}"

    cutoff = datetime.utcnow() - timedelta(days=lookback_days)
    week_start = datetime.utcnow().strftime("%Y-%m-%d")

    db = SessionLocal()
    try:
        rows = (
            db.query(MLPrediction)
            .filter(
                MLPrediction.model_name == model_name,
                MLPrediction.created_at >= cutoff,
                MLPrediction.observed_outcome.isnot(None),
            )
            .all()
        )

        n_total = (
            db.query(MLPrediction)
            .filter(MLPrediction.model_name == model_name, MLPrediction.created_at >= cutoff)
            .count()
        )

        if len(rows) < 10:
            logger.info("MLOps[%s]: only %d labelled rows — skipping metrics", model_name, len(rows))
            return f"insufficient labelled data ({len(rows)} rows)"

        y_true = np.array([r.observed_outcome for r in rows], dtype=float)
        y_prob = np.array([r.prediction_score for r in rows], dtype=float)

        pr_auc   = float(average_precision_score(y_true, y_prob))
        brier    = float(brier_score_loss(y_true, y_prob))
        roc_auc  = float(roc_auc_score(y_true, y_prob)) if len(np.unique(y_true)) > 1 else None

        # Calibration slope via logistic regression of observed ~ logit(predicted)
        eps   = 1e-7
        logit = np.log(np.clip(y_prob, eps, 1 - eps) / (1 - np.clip(y_prob, eps, 1 - eps)))
        X_cal = sm.add_constant(logit)
        cal_model  = sm.Logit(y_true, X_cal).fit(disp=False)
        cal_intercept = float(cal_model.params[0])
        cal_slope     = float(cal_model.params[1])

        drift = abs(cal_slope - 1.0) > _SLOPE_DRIFT_THRESHOLD
        drift_detail = None
        if drift:
            drift_detail = json.dumps({
                "slope": round(cal_slope, 4),
                "delta": round(cal_slope - 1.0, 4),
                "threshold": _SLOPE_DRIFT_THRESHOLD,
                "n_rows": len(rows),
            })
            logger.warning(
                "MLOps DRIFT ALERT [%s]: calibration slope=%.3f (delta=%.3f, threshold=±%.2f)",
                model_name, cal_slope, cal_slope - 1.0, _SLOPE_DRIFT_THRESHOLD,
            )
            task_alert_model_drift.apply_async(
                kwargs={"model_name": model_name, "detail": drift_detail}
            )

        metric_row = MLModelMetrics(
            model_name=model_name,
            week_start=week_start,
            n_predictions=n_total,
            n_with_outcome=len(rows),
            pr_auc=pr_auc,
            brier_score=brier,
            calibration_slope=cal_slope,
            calibration_intercept=cal_intercept,
            roc_auc=roc_auc,
            drift_flagged=drift,
            drift_detail=drift_detail,
        )
        db.add(metric_row)

        # Back-fill observed_outcome for rows whose next month's record is now available
        _backfill_outcomes(db, model_name)

        db.commit()
        logger.info(
            "MLOps[%s] week=%s  PR-AUC=%.3f  Brier=%.4f  slope=%.3f  drift=%s",
            model_name, week_start, pr_auc, brier, cal_slope, drift,
        )
        return {
            "model": model_name, "week": week_start,
            "pr_auc": pr_auc, "brier": brier,
            "slope": cal_slope, "drift": drift,
        }
    finally:
        db.close()


def _backfill_outcomes(db, model_name: str) -> None:
    """Set observed_outcome on predictions whose follow-up month record exists."""
    pending = (
        db.query(MLPrediction)
        .filter(MLPrediction.model_name == model_name, MLPrediction.observed_outcome.is_(None))
        .all()
    )
    for pred in pending:
        if not pred.prediction_month:
            continue
        try:
            yr, mo = int(pred.prediction_month[:4]), int(pred.prediction_month[5:7])
            mo += 1
            if mo > 12:
                mo, yr = 1, yr + 1
            next_month = f"{yr:04d}-{mo:02d}"
        except (ValueError, IndexError):
            continue

        rec = (
            db.query(MonthlyRecord)
            .filter(
                MonthlyRecord.patient_id == pred.patient_id,
                MonthlyRecord.record_month == next_month,
            )
            .first()
        )
        if rec is not None:
            pred.observed_outcome = int(bool(rec.hospitalization_this_month))


@celery_app.task(acks_late=True, reject_on_worker_lost=True)
def task_alert_model_drift(model_name: str, detail: str):
    """Send a drift-alert email to the configured admin address."""
    import os
    admin_email = os.getenv("ADMIN_EMAIL") or os.getenv("SMTP_USER")
    if not admin_email:
        logger.warning("MLOps drift alert: ADMIN_EMAIL not set, skipping email")
        return "no admin email configured"

    try:
        detail_dict = json.loads(detail)
    except Exception:
        detail_dict = {"raw": detail}

    slope   = detail_dict.get("slope", "?")
    delta   = detail_dict.get("delta", "?")
    n_rows  = detail_dict.get("n_rows", "?")
    subject = f"[HD Dashboard] Model drift alert — {model_name} calibration slope={slope}"
    body = (
        f"<h2>Calibration drift detected</h2>"
        f"<p>Model: <strong>{model_name}</strong></p>"
        f"<table border='1' cellpadding='6'>"
        f"<tr><th>Metric</th><th>Value</th></tr>"
        f"<tr><td>Calibration slope</td><td>{slope}</td></tr>"
        f"<tr><td>Δ from ideal (1.0)</td><td>{delta}</td></tr>"
        f"<tr><td>Labelled rows used</td><td>{n_rows}</td></tr>"
        f"<tr><td>Drift threshold (±)</td><td>{_SLOPE_DRIFT_THRESHOLD}</td></tr>"
        f"</table>"
        f"<p>Review the model card and consider retraining. "
        f"Trigger retraining via <code>POST /admin/train-deterioration-model</code>.</p>"
    )

    import smtplib, os as _os
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    smtp_host = _os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(_os.getenv("SMTP_PORT", "587"))
    smtp_user = _os.getenv("SMTP_USER", "")
    smtp_pass = _os.getenv("SMTP_PASSWORD", "")
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = smtp_user
        msg["To"]      = admin_email
        msg.attach(MIMEText(body, "html"))
        with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as s:
            s.ehlo(); s.starttls(); s.login(smtp_user, smtp_pass)
            s.sendmail(smtp_user, [admin_email], msg.as_string())
        logger.info("Drift alert email sent to %s", admin_email)
        return "sent"
    except Exception as exc:
        logger.error("Drift alert email failed: %s", exc)
        return f"failed: {exc}"


# ── Feature store: nightly materialization ────────────────────────────────────

@celery_app.task(acks_late=True, reject_on_worker_lost=True)
def task_refresh_feature_snapshots(month_str: str = None, force: bool = False):
    """Materialize patient_feature_snapshot rows for the given month.

    Runs nightly via Celery beat (see celery_app.py beat_schedule).
    Each row stores the engineered feature vector that the ML model will use
    for that patient-month, keyed by SHA-256 hash for audit traceability.

    Setting force=True rebuilds all rows regardless of the stale flag —
    use after a model retrain or feature engineering change.
    """
    import hashlib, json as _json, numpy as np
    from ml_risk import _extract_record_features_for_training

    month = month_str or get_current_month_str()
    db = SessionLocal()
    refreshed = skipped = errors = 0

    try:
        patients = db.query(Patient).filter(Patient.is_active == True).all()

        for p in patients:
            try:
                rec = (
                    db.query(MonthlyRecord)
                    .filter(
                        MonthlyRecord.patient_id == p.id,
                        MonthlyRecord.record_month == month,
                    )
                    .first()
                )
                if rec is None:
                    skipped += 1
                    continue

                # Check stale flag — skip if fresh and not forced
                existing = (
                    db.query(PatientFeatureSnapshot)
                    .filter(
                        PatientFeatureSnapshot.patient_id == p.id,
                        PatientFeatureSnapshot.as_of_month == month,
                    )
                    .first()
                )
                if existing and not existing.stale and not force:
                    skipped += 1
                    continue

                # Build the same feature vector the model uses at inference time
                raw_vec = _extract_record_features_for_training(rec, p)
                feature_vector = {
                    "hb_alert":     raw_vec[0],
                    "hb":           raw_vec[1],
                    "alb_alert":    raw_vec[2],
                    "albumin":      raw_vec[3],
                    "target_score": raw_vec[4],
                    "epo_hypo":     raw_vec[5],
                    "age":          raw_vec[6],
                    "cad":          raw_vec[7],
                    "chf":          raw_vec[8],
                    "dm_type":      raw_vec[9],
                }
                vec_json   = _json.dumps(feature_vector, sort_keys=True)
                vec_hash   = hashlib.sha256(vec_json.encode()).hexdigest()

                if existing:
                    existing.feature_vector = feature_vector
                    existing.feature_hash   = vec_hash
                    existing.stale          = False
                    existing.computed_at    = datetime.utcnow()
                else:
                    db.add(PatientFeatureSnapshot(
                        patient_id     = p.id,
                        as_of_month    = month,
                        feature_vector = feature_vector,
                        feature_hash   = vec_hash,
                        stale          = False,
                        computed_at    = datetime.utcnow(),
                    ))
                refreshed += 1

            except Exception as exc:
                logger.error(
                    "task_refresh_feature_snapshots: patient_id=%s month=%s error=%s",
                    p.id, month, exc,
                )
                errors += 1

        db.commit()
        logger.info(
            "task_refresh_feature_snapshots month=%s refreshed=%d skipped=%d errors=%d",
            month, refreshed, skipped, errors,
        )
        return {"month": month, "refreshed": refreshed, "skipped": skipped, "errors": errors}
    finally:
        db.close()
