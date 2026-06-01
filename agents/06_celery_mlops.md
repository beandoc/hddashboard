# 06 — Celery & MLOps Pipeline

> Agent memory file · HD Dashboard · Last updated 2026-06-01

---

## Infrastructure

| Component | Config |
|-----------|--------|
| Broker | Redis (`REDIS_URL`, default `redis://localhost:6379/0`) |
| Backend | Redis DB index 1 (`REDIS_BACKEND`) |
| Serializer | JSON (all tasks) |
| Timezone | UTC |
| Durability | `task_acks_late=True`, `task_reject_on_worker_lost=True` |
| Result expiry | 7 days |
| Max retries | 3 per task |
| Retry delay | 60 s |
| Prefetch | 1 (prevents queue starvation from long analytics tasks) |

### Dead-letter Queue
Tasks that exhaust all retries are routed to `"dead_letter"` exchange via `route_task_to_dead_letter()`.

---

## Beat Schedule (All Times UTC)

| Cron | Task | Purpose |
|------|------|---------|
| Daily 00:30 | `task_compute_model_metrics` | MLOps: PR-AUC, Brier, calibration slope for `deterioration_v1` (90-day lookback) |
| Daily 01:00 | `task_refresh_feature_snapshots` | Feature store: rebuild current-month `patient_feature_snapshot` rows |
| Daily 06:00 | `task_daily_data_integrity_report` | Email record-count summary (11:30 IST) to `DOCTOR_EMAIL` |
| Mon 03:00 | `task_backfill_acm_outcomes` | ACM: fill `observed_hb_1mo/3mo` when follow-up record exists |
| Mon 03:30 | `task_compute_acm_calibration` | ACM: slope/MAE/R² + ESA dose-response regression |
| Mon 04:00 | `task_train_acm_model` | ACM: refit ODE params + retrain residual MLP |

---

## Task Catalogue (`tasks.py`)

### Alert / Notification Tasks

| Task | Trigger | What it does |
|------|---------|-------------|
| `task_send_bulk_whatsapp` | Manual / ad-hoc | Sends WhatsApp alerts for all flagged patients |
| `task_send_ward_email` | Manual / ad-hoc | Sends HTML ward report email |
| `task_send_schedule_reminder` | Manual | Sends HD schedule reminder WhatsApp to a specific patient |

### MLOps Tasks

| Task | Trigger | What it does |
|------|---------|-------------|
| `task_compute_model_metrics` | Nightly 00:30 | PR-AUC, Brier, calibration slope; calls `task_alert_model_drift` if drifting |
| `task_alert_model_drift` | Triggered by above | Sends HTML drift-alert email to `ADMIN_EMAIL` |
| `task_refresh_feature_snapshots` | Nightly 01:00 | Materialises `patient_feature_snapshot` rows using `_extract_record_features_for_training()` |
| `task_train_deterioration_model` | Admin POST | Trains / retrains calibrated logistic regression; registers `ModelArtifact` row |
| `task_train_idh_model` | Admin POST | Trains / retrains XGBoost IDH model; registers artifact |
| `task_backfill_idh_outcomes` | Nightly | Fills `ml_predictions.observed_outcome` for IDH model rows |
| `task_compute_idh_model_metrics` | Nightly | Delegates to `task_compute_model_metrics("idh_v1")` |

### ACM Tasks

| Task | Trigger | What it does |
|------|---------|-------------|
| `task_backfill_acm_outcomes` | Mon 03:00 | Fills `acm_recommendations.observed_hb_1mo/3mo/mae` |
| `task_compute_acm_calibration` | Mon 03:30 | OLS calibration slope + ESA dose-response regression; writes `ml_model_metrics` row |
| `task_train_acm_model` | Mon 04:00 | Re-fits per-patient ODE params + retrains residual MLP |

### Audit / Integrity Tasks

| Task | Trigger | What it does |
|------|---------|-------------|
| `task_daily_data_integrity_report` | Daily 06:00 UTC | Emails: active patient count, records/month (last 3), last-24h saves |

---

## Calibration Drift Detection

```python
_SLOPE_DRIFT_THRESHOLD = 0.15   # tasks.py

# Drift condition:
if abs(calibration_slope - 1.0) > _SLOPE_DRIFT_THRESHOLD:
    drift_flagged = True
    task_alert_model_drift.apply_async(kwargs={"model_name": ..., "detail": ...})
```

Calibration slope is computed via logistic regression of `observed ~ logit(predicted)`.
Ideal slope = 1.0.  Slope < 1 → over-confident model; slope > 1 → under-confident.

### ACM Drift Conditions (more lenient)
```python
drift = abs(slope - 1.0) > 0.15 or mae > 1.5
```
MAE > 1.5 g/dL for Hb prediction triggers drift regardless of slope.

---

## Feature Store (`patient_feature_snapshot`)

Nightly materialisation ensures:
1. **Inference speed**: O(1) JSONB lookup vs. O(N SQL joins) per request
2. **Training/serving parity**: training sees the same vector that inference used at that time
3. **Audit surface**: clinicians can view exact model inputs via `/api/v1/patients/{id}/feature-history`

Stale mechanism:
- `stale = True` is set when underlying monthly_record is updated
- Nightly task rebuilds stale rows; `force=True` rebuilds all (use after feature engineering changes)

Feature vector ordering for deterioration model (12 fields):
```python
["hb_alert", "hb", "alb_alert", "albumin", "target_score", "epo_hypo",
 "age", "cad", "chf", "dm_type", "num_recent_hospitalizations_90d", "recent_infection_events"]
```

---

## Outcome Back-fill Logic

### Deterioration Model
`_backfill_outcomes(db, model_name)` — matches `ml_predictions` to the following month's `monthly_records.hospitalization_this_month`.

### IDH Model  
`_backfill_idh_outcomes(db)` — matches IDH prediction month to any `session_records` in that month; marks positive if ANY session had IDH (hybrid label).

### ACM Model
`task_backfill_acm_outcomes()` — matches `acm_recommendations` to 1-month and 3-month follow-up `monthly_records.hb`; computes `hb_prediction_mae_1mo`.

---

## Model Retraining Admin Endpoints

| Endpoint | Task triggered |
|----------|---------------|
| `POST /admin/train-deterioration-model` | `task_train_deterioration_model.delay()` |
| `POST /analytics/admin/train-idh-model` | `task_train_idh_model.delay()` |
| (ACM runs on schedule only) | `task_train_acm_model` |

---

## Celery Worker Start Command (`Procfile`)

```
worker: celery -A celery_app.celery_app worker --loglevel=info -Q default,dead_letter
beat: celery -A celery_app.celery_app beat --loglevel=info
```

On Render: separate worker dyno running these commands.

---

## Alert Email Architecture

All email sending uses `smtplib.SMTP` with STARTTLS (port 587).
Config from env: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`.

Recipients:
- `DOCTOR_EMAIL` — ward reports, data integrity
- `ADMIN_EMAIL` — ML drift alerts
- Per-patient contact — WhatsApp (Twilio)

WhatsApp config: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`.
