import os

from celery import Celery
from celery.schedules import crontab
from celery.signals import setup_logging as setup_logging_signal
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
    # #155 Cost-Monitoring: stündliche Alert-Checks
    "check-cost-alerts-hourly": {
        "task": "tasks.cost_alert_task.check_cost_alerts",
        "schedule": crontab(minute=30),  # :30 — kein Konflikt mit drift (:00) und memory (:15)
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
    "p06-profile-extractor-nightly": {
        "task": "tasks.p06_profile_extractor_task.run_all",
        "schedule": crontab(hour=3, minute=15),  # nightly 03:15 (nach memory-backfill)
    },
    "deletion-purge-daily": {
        "task": "tasks.deletion_purge_task.purge_expired",
        "schedule": crontab(hour=4, minute=0),  # daily 04:00 hard-delete
    },
    # #150 Embedding-Drift-Monitor: wöchentlich Montag 03:15
    "embedding-drift-monitor-weekly": {
        "task": "tasks.drift_monitor_task.run_embedding_drift_monitor",
        "schedule": crontab(day_of_week=1, hour=3, minute=15),
    },
    # Vektorlos-Wächter: täglich 03:45 — nach dem nightly-Backfill (03:15),
    # damit gemeldet wird, was der Backfill NICHT reparieren konnte.
    "embedding-health-daily": {
        "task": "tasks.embedding_health_task.check_missing_embeddings",
        "schedule": crontab(hour=3, minute=45),
    },
    # Bot-Sessions hatten kein TTL — eine unbeantwortete Session blieb fuer immer
    # 'active' und verschluckte jede spaetere Nachricht als "Antwort" auf eine
    # Frage von vorgestern. :45 ist frei (drift :00, memory :15, cost :30).
    "expire-stale-bot-sessions-hourly": {
        "task": "tasks.session_timeout_task.expire_stale_sessions",
        "schedule": crontab(minute=45),
    },
}

# ---------------------------------------------------------------------------
# Optionaler Telegram-Poller via Beat (standardmäßig DEAKTIVIERT).
# Nur aktivieren wenn KEIN Standalone-Runner (telegram_runner.py) läuft —
# sonst würden beide doppelt pollen. Für den VPN-only-Betrieb ist der
# Standalone-Runner (python backend/telegram_runner.py) empfohlen.
# Aktivierung: TELEGRAM_POLLING_ENABLED=true in der Beat-Umgebung setzen.
# ---------------------------------------------------------------------------
if os.environ.get("TELEGRAM_POLLING_ENABLED", "false").lower() in ("1", "true", "yes", "on"):
    celery_app.conf.beat_schedule["telegram-poll-active-bots-every-5s"] = {
        "task": "tasks.telegram_poll_task.poll_all_active_bots",
        "schedule": 5.0,
    }


# ---------------------------------------------------------------------------
# Logging — Worker und Beat konfigurieren sich wie das Backend.
#
# Bis 04.08.2026 rief nur main.py logging_config.setup_logging() auf. Der Worker
# lief damit auf Celerys Default-Konfiguration: httpx auf INFO und OHNE den
# SensitiveDataFilter — 2486 Zeilen Bot-Token im Klartext in einer Stunde
# (`HTTP Request: GET https://api.telegram.org/file/bot<ID>:<TOKEN>/voice/…`).
#
# Der `setup_logging`-Empfänger ist die einzige Stelle, an der sich Celerys
# eigene Root-Logger-Konfiguration verhindern lässt: celery/app/log.py wertet
# `if not receivers:` aus und lässt den Root-Logger in Ruhe, sobald jemand
# angemeldet ist. `after_setup_logger` wäre zu spät — dort steht die Hijack-
# Konfiguration bereits.
# ---------------------------------------------------------------------------
@setup_logging_signal.connect
def _configure_worker_logging(loglevel=None, **kwargs) -> None:
    from logging_config import setup_logging

    # loglevel kommt als int aus Celerys `-l`-Flag; None → Default INFO.
    setup_logging(level=loglevel)


# ---------------------------------------------------------------------------
# Logging context — contextvars are NOT inherited across process boundaries.
# Set correlation_id from task_id and clear tenant_id for every task run.
# ---------------------------------------------------------------------------
@task_prerun.connect
def _setup_logging_context(task_id: str = "", **kwargs) -> None:
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
    "tasks.session_post_task",
    "tasks.session_timeout_task",
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
    "tasks.p05_industry_task",
    "tasks.p06_profile_extractor_task",
    "tasks.deletion_purge_task",
    "tasks.cost_alert_task",
    "tasks.reembed_task",
    "tasks.drift_monitor_task",
    "tasks.embedding_health_task",
    "tasks.values_backfill_task",
    "tasks.telegram_poll_task",
    # Beide werden aus api/telegram.py per .delay() aus dem Button-Callback
    # angestoßen (C7 „Idee ausarbeiten", C8 „Neue Ideen generieren"). Ohne
    # Eintrag hier hängt die Registrierung im Worker davon ab, ob irgendein
    # anderer Codepfad das Modul im selben Prozess schon importiert hat —
    # sonst NotRegistered. Beide haben nur leichte Modul-Importe (sqlalchemy,
    # models.base, celery_app), also kein Zirkel-Risiko beim Worker-Start.
    "tasks.p13_variants_task",
    "tasks.p09_chat_ideas_task",
    # Gleicher Defekt, seit PR #135 live: „✏️ Nochmal anders" (cmd:regenerate)
    # enqueued regenerate_post_from_feedback aus demselben Callback-Pfad. Ohne
    # Eintrag verwirft der Worker die Nachricht als unregistered — der Tester liest
    # „kommt gleich" und bekommt nie etwas. Auch hier nur leichte Modul-Importe.
    "tasks.post_feedback_task",
    "api.wizard",
]
