"""Celery application and beat schedule for scheduled triggers."""

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "flowpilot",
    broker=str(settings.CELERY_BROKER_URL),
    backend=str(settings.CELERY_RESULT_BACKEND),
    include=["app.tasks.execution_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=settings.EXECUTION_TIMEOUT_SECONDS + 60,
    task_soft_time_limit=settings.EXECUTION_TIMEOUT_SECONDS,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
)

if settings.CELERY_TASK_ALWAYS_EAGER:
    celery_app.conf.task_always_eager = True

celery_app.conf.beat_schedule = {
    "check-scheduled-workflows-every-minute": {
        "task": "app.tasks.execution_tasks.check_scheduled_workflows",
        "schedule": crontab(minute="*"),
    },
}
