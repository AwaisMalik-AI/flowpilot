"""Schedule registration and due-workflow discovery for cron triggers."""

from datetime import datetime, timezone

from croniter import croniter
from sqlalchemy.orm import Session

from app.models.workflow import ScheduledTrigger, Workflow, WorkflowStatus


class SchedulerService:
    """Computes next run times and lists workflows due for execution."""

    @staticmethod
    def register_schedule(
        db: Session,
        workflow: Workflow,
        cron_expression: str,
        *,
        is_active: bool = True,
    ) -> ScheduledTrigger:
        itr = croniter(cron_expression, datetime.now(timezone.utc))
        nxt = itr.get_next(datetime)
        if nxt.tzinfo is None:
            nxt = nxt.replace(tzinfo=timezone.utc)
        row = ScheduledTrigger(
            workflow_id=workflow.id,
            cron_expression=cron_expression,
            next_run_at=nxt,
            is_active=is_active,
        )
        db.add(workflow)
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def unregister_schedule(db: Session, schedule_id: int) -> bool:
        row = db.query(ScheduledTrigger).filter(ScheduledTrigger.id == schedule_id).first()
        if not row:
            return False
        db.delete(row)
        db.commit()
        return True

    @staticmethod
    def get_due_workflows(db: Session, now: datetime | None = None) -> list[tuple[ScheduledTrigger, Workflow]]:
        now = now or datetime.now(timezone.utc)
        q = (
            db.query(ScheduledTrigger, Workflow)
            .join(Workflow, Workflow.id == ScheduledTrigger.workflow_id)
            .filter(
                ScheduledTrigger.is_active.is_(True),
                ScheduledTrigger.next_run_at <= now,
                Workflow.status == WorkflowStatus.ACTIVE,
            )
        )
        return list(q.all())

    @staticmethod
    def bump_next_run(db: Session, trigger: ScheduledTrigger, base_time: datetime | None = None) -> None:
        base = base_time or datetime.now(timezone.utc)
        itr = croniter(trigger.cron_expression, base)
        nxt = itr.get_next(datetime)
        if nxt.tzinfo is None:
            nxt = nxt.replace(tzinfo=timezone.utc)
        trigger.next_run_at = nxt
        trigger.last_run_at = base
        db.add(trigger)
        db.commit()
