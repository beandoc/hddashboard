from celery_app import celery_app
from database import SessionLocal, Patient, AlertLog, MonthlyRecord, MLPrediction, MLModelMetrics, PatientFeatureSnapshot
from dashboard_logic import get_patients_needing_alerts, get_month_label, get_current_month_str
from alerts import send_bulk_whatsapp_alerts, send_ward_email, build_schedule_message, send_whatsapp
import logging
import json
import os
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from sqlalchemy import func

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
                raw_vec = _extract_record_features_for_training(rec, p, db)
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
                    "num_recent_hospitalizations_90d": raw_vec[10],
                    "recent_infection_events": raw_vec[11],
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


# ── ML model retraining task ──────────────────────────────────────────────────

@celery_app.task(acks_late=True, reject_on_worker_lost=True)
def task_train_deterioration_model():
    """Async Celery task to train (or retrain) the deterioration risk model.

    Called via .delay() from the admin POST endpoint so the HTTP request returns
    immediately.  Persists the model to disk and registers a ModelArtifact row.
    """
    from ml_risk import train_deterioration_model
    db = SessionLocal()
    try:
        result = train_deterioration_model(db)
        if result.get("success"):
            logger.info(
                "task_train_deterioration_model: training complete — "
                "cv_auc=%.3f n_samples=%d",
                result.get("cv_auc", 0), result.get("n_samples", 0),
            )
        else:
            logger.error(
                "task_train_deterioration_model: training failed — %s",
                result.get("error", "unknown error"),
            )
        return result
    except Exception as exc:
        logger.exception("task_train_deterioration_model: unhandled exception")
        raise
    finally:
        db.close()


# ── IDH Model Tasks ───────────────────────────────────────────────────────────

@celery_app.task(acks_late=True, reject_on_worker_lost=True)
def task_train_idh_model():
    """Async Celery task to train (or retrain) the IDH prediction model.

    Called via .delay() from POST /analytics/admin/train-idh-model.
    Training may take 30–90 seconds depending on session volume.
    Persists the model to idh_model.joblib and registers a ModelArtifact row.
    """
    from ml_idh import train_idh_model
    db = SessionLocal()
    try:
        result = train_idh_model(db)
        if result.get("success"):
            logger.info(
                "task_train_idh_model: training complete — cv_auc=%.3f n_sessions=%d n_events=%d algo=%s",
                result.get("cv_auc", 0), result.get("n_samples", 0),
                result.get("n_events", 0), result.get("algorithm", "?"),
            )
        else:
            logger.error(
                "task_train_idh_model: training failed — %s",
                result.get("error", "unknown error"),
            )
        return result
    except Exception as exc:
        logger.exception("task_train_idh_model: unhandled exception")
        raise
    finally:
        db.close()


def _backfill_idh_outcomes(db) -> int:
    """
    Back-fill observed_outcome on IDH ml_predictions rows after the session
    has been completed and its data entered.

    The outcome is 1 if the completed session had IDH (hybrid label),
    matched by patient_id and prediction_month (YYYY-MM).
    """
    from database import SessionRecord
    from ml_idh import _compute_idh_label

    pending = (
        db.query(MLPrediction)
        .filter(
            MLPrediction.model_name == "idh_v1",
            MLPrediction.observed_outcome.is_(None),
        )
        .all()
    )
    filled = 0
    for pred in pending:
        if not pred.prediction_month:
            continue
        # Find sessions for this patient in the prediction month
        sessions = (
            db.query(SessionRecord)
            .filter(
                SessionRecord.patient_id == pred.patient_id,
                SessionRecord.record_month == pred.prediction_month,
            )
            .all()
        )
        if not sessions:
            continue
        # If ANY session in the month had IDH, mark the month's prediction as positive
        idh_occurred = any(_compute_idh_label(s) for s in sessions)
        pred.observed_outcome = int(idh_occurred)
        filled += 1
    return filled


@celery_app.task(acks_late=True, reject_on_worker_lost=True)
def task_backfill_idh_outcomes():
    """
    Nightly task: back-fill IDH observed outcomes into ml_predictions.

    Runs after sessions are entered so that MLOps metrics can be computed.
    Safe to run repeatedly — only processes rows where observed_outcome is NULL.
    """
    db = SessionLocal()
    try:
        filled = _backfill_idh_outcomes(db)
        db.commit()
        logger.info("task_backfill_idh_outcomes: filled %d rows", filled)
        return {"filled": filled}
    except Exception as exc:
        logger.exception("task_backfill_idh_outcomes failed")
        raise
    finally:
        db.close()


@celery_app.task(acks_late=True, reject_on_worker_lost=True)
def task_compute_idh_model_metrics(lookback_days: int = 90):
    """
    Compute MLOps performance metrics for the IDH model.
    Delegates to the generic task_compute_model_metrics with model_name='idh_v1'.
    """
    return task_compute_model_metrics("idh_v1", lookback_days)


@celery_app.task(acks_late=True, reject_on_worker_lost=True)
def task_daily_data_integrity_report():
    """Daily task: email a record-count summary so silent save failures are caught.

    Runs at 06:00 UTC (11:30 IST). Reports:
    - Total active patients
    - Monthly records saved per month (last 3 months)
    - Records saved in the last 24 hours (audit trail)
    """
    db = SessionLocal()
    try:
        smtp_user = os.getenv("SMTP_USER", "")
        smtp_pass = os.getenv("SMTP_PASSWORD", "")
        doctor_email = os.getenv("DOCTOR_EMAIL", "")
        smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))

        if not smtp_user or not smtp_pass or not doctor_email:
            logger.warning("task_daily_data_integrity_report: SMTP not configured, skipping")
            return "SMTP not configured"

        now = datetime.utcnow()
        today_str = now.strftime("%Y-%m-%d")

        # Active patient count
        active_count = db.query(func.count(Patient.id)).filter(Patient.is_active == True).scalar() or 0

        # Monthly record counts for last 3 months
        current_month = get_current_month_str()
        year, mon = map(int, current_month.split("-"))
        months = []
        for i in range(3):
            m = mon - i
            y = year
            if m <= 0:
                m += 12
                y -= 1
            months.append(f"{y}-{m:02d}")

        month_rows = []
        for m in months:
            count = (
                db.query(func.count(MonthlyRecord.id))
                .filter(MonthlyRecord.record_month == m)
                .scalar() or 0
            )
            month_rows.append(f"<tr><td>{get_month_label(m)}</td><td style='text-align:center;font-weight:700;color:#0284c7;'>{count}</td><td style='text-align:center;color:#64748b;'>{active_count}</td><td style='text-align:center;'><span style='color:{'#10b981' if count >= active_count * 0.8 else '#ef4444'};font-weight:700;'>{'✓ Good' if count >= active_count * 0.8 else '⚠ Low'}</span></td></tr>")

        # Records saved in last 24 hours
        cutoff = now - timedelta(hours=24)
        recent = (
            db.query(MonthlyRecord)
            .filter(MonthlyRecord.timestamp >= cutoff)
            .order_by(MonthlyRecord.timestamp.desc())
            .limit(50)
            .all()
        )
        recent_rows = ""
        for r in recent:
            p = db.query(Patient).filter(Patient.id == r.patient_id).first()
            name = p.name if p else f"ID {r.patient_id}"
            ts = r.timestamp.strftime("%H:%M UTC") if r.timestamp else "—"
            recent_rows += f"<tr><td>{name}</td><td>{r.record_month}</td><td>{r.entered_by or '—'}</td><td>{ts}</td></tr>"

        if not recent_rows:
            recent_rows = "<tr><td colspan='4' style='text-align:center;color:#64748b;'>No records saved in last 24 hours</td></tr>"

        html = f"""
        <html><body style="font-family:Arial,sans-serif;max-width:700px;margin:0 auto;padding:20px;">
        <h2 style="color:#0284c7;">HD Dashboard — Daily Data Integrity Report</h2>
        <p style="color:#64748b;">Generated {today_str} · Active patients: <strong>{active_count}</strong></p>

        <h3 style="color:#334155;">Records Saved by Month</h3>
        <table style="width:100%;border-collapse:collapse;margin-bottom:24px;">
          <thead><tr style="background:#f1f5f9;">
            <th style="padding:8px;text-align:left;">Month</th>
            <th style="padding:8px;">Records Saved</th>
            <th style="padding:8px;">Active Patients</th>
            <th style="padding:8px;">Status</th>
          </tr></thead>
          <tbody>{''.join(month_rows)}</tbody>
        </table>

        <h3 style="color:#334155;">Records Saved in Last 24 Hours</h3>
        <table style="width:100%;border-collapse:collapse;">
          <thead><tr style="background:#f1f5f9;">
            <th style="padding:8px;text-align:left;">Patient</th>
            <th style="padding:8px;text-align:left;">Month</th>
            <th style="padding:8px;text-align:left;">Entered By</th>
            <th style="padding:8px;text-align:left;">Time</th>
          </tr></thead>
          <tbody>{recent_rows}</tbody>
        </table>

        <p style="margin-top:24px;font-size:0.85em;color:#94a3b8;">
          To download a full backup, go to Admin → Database → Export JSON.<br>
          This report is sent daily at 06:00 UTC (11:30 IST).
        </p>
        </body></html>
        """

        msg = MIMEText(html, "html")
        msg["Subject"] = f"HD Dashboard — Data Integrity Report {today_str}"
        msg["From"] = smtp_user
        msg["To"] = doctor_email

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, doctor_email, msg.as_string())

        logger.info("task_daily_data_integrity_report: sent to %s", doctor_email)
        return f"Sent to {doctor_email}: {active_count} active patients, {len(recent)} records in last 24h"

    except Exception as exc:
        logger.exception("task_daily_data_integrity_report failed: %s", exc)
        raise
    finally:
        db.close()
