from celery import Celery
from celery.schedules import crontab
from celery.signals import task_prerun

from config import settings

# Initialize Sentry early (before any tasks are registered)
try:
    import sentry_config
    sentry_config.init_sentry()
except Exception:
    pass

celery_app = Celery("content_autopilot", broker=settings.redis_url, backend=settings.redis_url)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/Berlin",
    enable_utc=True,
    task_track_started=True,
    worker_max_tasks_per_child=100,
)

# Periodic tasks
celery_app.conf.beat_schedule = {
    "monitor-sources-check-due": {
        "task": "tasks.monitor_task.monitor_all_sources",
        "schedule": 60.0,  # Check every minute, but only poll sources that are due
    },
    "update-views-every-3h": {
        "task": "tasks.views_task.update_all_views",
        "schedule": 10800.0,
    },
    "batch-transcribe-every-30min": {
        "task": "tasks.transcribe_task.batch_transcribe",
        "schedule": 1800.0,
    },
    "cleanup-media-every-6h": {
        "task": "tasks.cleanup_task.cleanup_media_files",
        "schedule": 21600.0,
    },
    "publish-scheduled-posts-every-minute": {
        "task": "tasks.publish_task.publish_scheduled_posts",
        "schedule": 60.0,
    },
    "reset-daily-costs-midnight": {
        "task": "tasks.cost_reset_task.reset_daily_costs",
        "schedule": 86400.0,  # Once per day
    },
    "pipeline-pump-every-10min": {
        "task": "tasks.pipeline_pump_task.pump_pipeline",
        "schedule": 600.0,  # Every 10 minutes
    },
    "resume-paused-pipelines-midnight": {
        "task": "tasks.setup_pipeline_task.resume_paused_pipelines",
        "schedule": 86400.0,  # täglich
    },
    "check-voice-drift-triggers-hourly": {
        "task": "tasks.voice_drift_task.check_drift_triggers",
        "schedule": crontab(minute=0),  # jede volle Stunde
    },
    "check-model-availability-daily": {
        "task": "tasks.model_check_task.check_model_availability",
        "schedule": crontab(hour=6, minute=0),  # täglich 06:00
    },
    "wizard-cleanup-abandoned-daily": {
        "task": "tasks.wizard_cleanup.cleanup_abandoned_sessions",
        "schedule": 86400.0,  # täglich
    },
    "check-random-smart-triggers-every-5min": {
        "task": "tasks.random_smart_scheduler.check_random_smart_triggers",
        "schedule": 300.0,  # Every 5 minutes
    },
    "check-reviewer-queue-backlog-daily": {
        "task": "tasks.reviewer_queue_cron.check_reviewer_queue_backlog",
        "schedule": crontab(hour=8, minute=30),  # täglich 08:30
    },
    "p07-research-twice-weekly": {
        "task": "tasks.p07_research_task.run_research_all_tenants",
        "schedule": crontab(day_of_week="tue,fri", hour=6, minute=30),
    },
    "memory-backfill-hourly": {
        "task": "tasks.memory_backfill_task.run_backfill",
        "schedule": crontab(minute=15),  # stündlich :15 (kein Konflikt mit Drift)
        "kwargs": {"limit": 100},
    },
}

# ---------------------------------------------------------------------------
# Logging context — contextvars are NOT inherited across process boundaries.
# Set correlation_id from task_id and clear tenant_id for every task run.
# ---------------------------------------------------------------------------
@task_prerun.connect
def _setup_logging_context(task_id: str = "", **kwargs) -> None:  # noqa: ANN001
    try:
        from logging_config import correlation_id_var, tenant_id_var
        correlation_id_var.set(task_id or "")
        tenant_id_var.set("")
    except Exception:  # pragma: no cover — never crash a task over logging
        pass


# Explicit task module imports
celery_app.conf.include = [
    "tasks.monitor_task",
    "tasks.transcribe_task",
    "tasks.generate_task",
    "tasks.views_task",
    "tasks.ideation_task",
    "tasks.cleanup_task",
    "tasks.publish_task",
    "tasks.cost_reset_task",
    "tasks.pipeline_pump_task",
    "tasks.questions_task",
    "tasks.setup_pipeline_task",
    "tasks.p12_task",
    "tasks.p12b_task",
    "tasks.p12c_task",
    "tasks.voice_drift_task",
    "tasks.model_check_task",
    "tasks.backtest_task",
    "tasks.wizard_cleanup",
    "tasks.random_smart_scheduler",
    "tasks.reviewer_queue_cron",
    "tasks.telegram_task",
    "tasks.memory_backfill_task",
    "tasks.p12_variants_task",
    "tasks.p07_research_task",
    "api.wizard",
]
