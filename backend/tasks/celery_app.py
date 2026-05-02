from celery import Celery
from celery.schedules import crontab

from config import settings

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
    "wizard-cleanup-abandoned-daily": {
        "task": "tasks.wizard_cleanup.cleanup_abandoned_sessions",
        "schedule": 86400.0,  # täglich
    },
}

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
    "tasks.voice_drift_task",
    "tasks.wizard_cleanup",
    "api.wizard",
]
