"""Async workflow execution and cron polling."""

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.workflow import TriggerType, Workflow, WorkflowStatus
from app.services.engine import WorkflowEngine
from app.services.scheduler import SchedulerService
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.execution_tasks.execute_workflow_task", bind=True, max_retries=3)
def execute_workflow_task(self, workflow_id: int, trigger_data: dict[str, Any], trigger_type: str) -> dict[str, Any]:
    db: Session = SessionLocal()
    try:
        wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
        if not wf or wf.status != WorkflowStatus.ACTIVE:
            return {"ok": False, "error": "workflow not found or inactive"}
        engine = WorkflowEngine()
        result = engine.execute_workflow(db, wf, trigger_data, trigger_type=trigger_type)
        return {
            "ok": True,
            "execution_id": result.execution_id,
            "status": result.status.value,
            "error": result.error_message,
        }
    except Exception as e:
        logger.exception("execute_workflow_task failed")
        raise self.retry(exc=e, countdown=30) from e
    finally:
        db.close()


@celery_app.task(name="app.tasks.execution_tasks.check_scheduled_workflows")
def check_scheduled_workflows() -> dict[str, Any]:
    db: Session = SessionLocal()
    fired = 0
    try:
        due = SchedulerService.get_due_workflows(db)
        for trigger, wf in due:
            trigger_data = {"cron": trigger.cron_expression, "trigger_id": trigger.id}
            execute_workflow_task.delay(wf.id, trigger_data, TriggerType.SCHEDULE.value)
            SchedulerService.bump_next_run(db, trigger)
            fired += 1
        return {"checked": len(due), "enqueued": fired}
    finally:
        db.close()
