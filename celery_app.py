import os
from celery import Celery
from celery.schedules import crontab
from dotenv import load_dotenv

load_dotenv()

REDIS_URL     = os.getenv("REDIS_URL",     "redis://localhost:6379/0")
# Separate DB index so result backend doesn't pollute task broker queue
REDIS_BACKEND = os.getenv("REDIS_BACKEND", REDIS_URL.rstrip("/0") + "/1"
                           if REDIS_URL.endswith("/0") else REDIS_URL)

celery_app = Celery(
    "hd_dashboard",
    broker=REDIS_URL,
    backend=REDIS_BACKEND,
)

celery_app.conf.update(
    # ── Serialization ──────────────────────────────────────────────────────
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",

    # ── Clock ─────────────────────────────────────────────────────────────
    timezone="UTC",
    enable_utc=True,

    # ── Durability: never lose a task on worker crash ──────────────────────
    # acks_late=True: message only ACKed after the task function returns.
    # reject_on_worker_lost=True: re-queues the task when a worker dies mid-run.
    task_acks_late=True,
    task_reject_on_worker_lost=True,

    # ── Result persistence ─────────────────────────────────────────────────
    result_persistent=True,          # results survive broker restart
    result_expires=604800,           # 7 days in seconds

    # ── Dead-letter: tasks that fail all retries go to a separate queue ────
    task_queues={
        "default": {
            "exchange": "default",
            "routing_key": "default",
        },
        "dead_letter": {
            "exchange": "dead_letter",
            "routing_key": "dead_letter",
        },
    },
    task_default_queue="default",

    # ── Retry policy for transient alert delivery failures ─────────────────
    # Tasks that explicitly call self.retry() will back off up to 3 attempts.
    task_max_retries=3,
    task_default_retry_delay=60,     # seconds between retries

    # ── Prefetch: process one task at a time so long-running analytics
    #    tasks don't starve the worker queue ────────────────────────────────
    worker_prefetch_multiplier=1,

    # ── Beat schedule: nightly MLOps metrics every day at 00:30 UTC ────────
    beat_schedule={
        "mlops-nightly-metrics": {
            "task":     "tasks.task_compute_model_metrics",
            "schedule": crontab(hour=0, minute=30),
            "kwargs":   {"model_name": "deterioration_v1", "lookback_days": 90},
        },
        # Feature store: refresh current-month snapshots nightly at 01:00 UTC.
        # Runs after mlops-nightly-metrics so drift detection has already fired.
        "feature-store-nightly-refresh": {
            "task":     "tasks.task_refresh_feature_snapshots",
            "schedule": crontab(hour=1, minute=0),
            "kwargs":   {},
        },
        # Data integrity report: email record counts + last-24h saves at 06:00 UTC (11:30 IST).
        "daily-data-integrity-report": {
            "task":     "tasks.task_daily_data_integrity_report",
            "schedule": crontab(hour=6, minute=0),
        },
        # ACM pipeline — runs every Monday:
        #   03:00 back-fill observed Hb outcomes
        #   03:30 compute calibration metrics (needs back-fill to have run first)
        #   04:00 retrain hybrid ODE+MLP (needs calibration to flag drift)
        "acm-backfill-outcomes": {
            "task":     "tasks.task_backfill_acm_outcomes",
            "schedule": crontab(hour=3, minute=0, day_of_week=1),
        },
        "acm-compute-calibration": {
            "task":     "tasks.task_compute_acm_calibration",
            "schedule": crontab(hour=3, minute=30, day_of_week=1),
        },
        "acm-train-model": {
            "task":     "tasks.task_train_acm_model",
            "schedule": crontab(hour=4, minute=0, day_of_week=1),
        },
        # Phosphate MCMC calibration — Sunday 02:00 UTC (for all active patients)
        "phosphate-mcmc-calibration": {
            "task":     "tasks.task_phosphate_mcmc_calibration",
            "schedule": crontab(hour=2, minute=0, day_of_week=0),
        },
        # Access failure risk scoring — Sunday 02:30 UTC
        "access-failure-risk": {
            "task":     "tasks.task_compute_access_failure_risk",
            "schedule": crontab(hour=2, minute=30, day_of_week=0),
        },
    },
)


def route_task_to_dead_letter(task_id, task, args, kwargs, options, task_name, **kw):
    """Redirect tasks that have exhausted all retries to the dead_letter queue."""
    retries = options.get("retries", 0)
    if retries >= celery_app.conf.task_max_retries:
        return {"queue": "dead_letter"}
    return None


celery_app.conf.task_routes = (route_task_to_dead_letter,)
