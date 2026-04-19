"""Execution listing, detail with logs, retry."""

import copy
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User, UserRole
from app.models.workflow import Workflow, WorkflowExecution
from app.schemas.workflow import ExecutionDetail, ExecutionRead, WorkflowLogRead
from app.services.engine import WorkflowEngine

router = APIRouter(prefix="/executions", tags=["executions"])


def _execution_visible(db: Session, user: User, execution_id: int) -> WorkflowExecution | None:
    row = db.query(WorkflowExecution).filter(WorkflowExecution.id == execution_id).first()
    if not row:
        return None
    wf = db.query(Workflow).filter(Workflow.id == row.workflow_id).first()
    if not wf:
        return None
    if user.role == UserRole.ADMIN:
        return row
    if wf.owner_id == user.id:
        return row
    return None


@router.get("", response_model=list[ExecutionRead])
def list_executions(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> list[WorkflowExecution]:
    q = db.query(WorkflowExecution).join(Workflow, Workflow.id == WorkflowExecution.workflow_id)
    if user.role != UserRole.ADMIN:
        q = q.filter(Workflow.owner_id == user.id)
    return q.order_by(WorkflowExecution.created_at.desc()).offset(skip).limit(limit).all()


@router.get("/{execution_id}", response_model=ExecutionDetail)
def get_execution(
    execution_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ExecutionDetail:
    row = _execution_visible(db, user, execution_id)
    if not row:
        raise HTTPException(status_code=404, detail="Execution not found")
    logs = [WorkflowLogRead.model_validate(l) for l in row.logs]
    return ExecutionDetail(
        id=row.id,
        workflow_id=row.workflow_id,
        trigger_type=row.trigger_type,
        status=row.status,
        started_at=row.started_at,
        completed_at=row.completed_at,
        execution_time_ms=row.execution_time_ms,
        error_message=row.error_message,
        retry_count=row.retry_count,
        created_at=row.created_at,
        trigger_data=row.trigger_data or {},
        node_results=row.node_results or {},
        logs=logs,
    )


@router.post("/{execution_id}/retry", response_model=ExecutionRead)
def retry_execution(
    execution_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> WorkflowExecution:
    if user.role == UserRole.VIEWER:
        raise HTTPException(status_code=403, detail="Viewers cannot retry executions")
    prev = _execution_visible(db, user, execution_id)
    if not prev:
        raise HTTPException(status_code=404, detail="Execution not found")
    wf = db.query(Workflow).filter(Workflow.id == prev.workflow_id).first()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    trigger_data = copy.deepcopy(prev.trigger_data or {})
    engine = WorkflowEngine()
    result = engine.execute_workflow(
        db,
        wf,
        trigger_data,
        trigger_type=f"retry:{prev.trigger_type}",
    )
    row = db.query(WorkflowExecution).filter(WorkflowExecution.id == result.execution_id).first()
    if row:
        row.retry_count = (prev.retry_count or 0) + 1
        db.commit()
        db.refresh(row)
    if not row:
        raise HTTPException(status_code=500, detail="Retry failed to persist")
    return row
