"""Workflow CRUD, manual execution, activation, clone."""

import copy
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User, UserRole
from app.models.workflow import (
    ScheduledTrigger,
    TriggerType,
    WebhookEndpoint,
    Workflow,
    WorkflowExecution,
    WorkflowStatus,
)
from app.schemas.workflow import (
    ExecutionRead,
    ManualExecuteRequest,
    ScheduledTriggerCreate,
    ScheduledTriggerRead,
    WebhookEndpointCreate,
    WebhookEndpointWithSecret,
    WorkflowCreate,
    WorkflowListItem,
    WorkflowRead,
    WorkflowUpdate,
)
from app.services.engine import WorkflowEngine
from app.services.scheduler import SchedulerService

router = APIRouter(prefix="/workflows", tags=["workflows"])


def _can_write(user: User, wf: Workflow) -> bool:
    return user.role == UserRole.ADMIN or wf.owner_id == user.id


def _can_read_workflow(user: User, wf: Workflow) -> bool:
    if user.role == UserRole.ADMIN:
        return True
    if user.role == UserRole.VIEWER and wf.owner_id == user.id:
        return True
    if user.role == UserRole.DEVELOPER and wf.owner_id == user.id:
        return True
    return False


@router.get("", response_model=list[WorkflowListItem])
def list_workflows(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> list[Workflow]:
    q = db.query(Workflow)
    if user.role != UserRole.ADMIN:
        q = q.filter(Workflow.owner_id == user.id)
    return q.order_by(Workflow.created_at.desc()).offset(skip).limit(limit).all()


@router.post("", response_model=WorkflowRead, status_code=status.HTTP_201_CREATED)
def create_workflow(
    payload: WorkflowCreate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> Workflow:
    if user.role == UserRole.VIEWER:
        raise HTTPException(status_code=403, detail="Viewers cannot create workflows")
    wf = Workflow(
        name=payload.name,
        description=payload.description,
        owner_id=user.id,
        status=payload.status,
        trigger_type=payload.trigger_type,
        trigger_config=payload.trigger_config,
        nodes=payload.nodes,
        edges=payload.edges,
        is_template=payload.is_template,
    )
    db.add(wf)
    db.commit()
    db.refresh(wf)
    return wf


@router.get("/{workflow_id}", response_model=WorkflowRead)
def get_workflow(
    workflow_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> Workflow:
    wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not wf or not _can_read_workflow(user, wf):
        raise HTTPException(status_code=404, detail="Workflow not found")
    return wf


@router.patch("/{workflow_id}", response_model=WorkflowRead)
def update_workflow(
    workflow_id: int,
    payload: WorkflowUpdate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> Workflow:
    wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not wf or not _can_write(user, wf):
        raise HTTPException(status_code=404, detail="Workflow not found")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(wf, k, v)
    db.commit()
    db.refresh(wf)
    return wf


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workflow(
    workflow_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> None:
    wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not wf or not _can_write(user, wf):
        raise HTTPException(status_code=404, detail="Workflow not found")
    db.delete(wf)
    db.commit()


@router.post("/{workflow_id}/execute", response_model=ExecutionRead)
def execute_manual(
    workflow_id: int,
    payload: ManualExecuteRequest,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> WorkflowExecution:
    if user.role == UserRole.VIEWER:
        raise HTTPException(status_code=403, detail="Viewers cannot execute workflows")
    wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not wf or not _can_read_workflow(user, wf):
        raise HTTPException(status_code=404, detail="Workflow not found")
    if wf.status != WorkflowStatus.ACTIVE and user.role != UserRole.ADMIN:
        raise HTTPException(status_code=400, detail="Workflow is not active")
    engine = WorkflowEngine()
    result = engine.execute_workflow(db, wf, payload.payload, trigger_type=TriggerType.MANUAL.value)
    row = db.query(WorkflowExecution).filter(WorkflowExecution.id == result.execution_id).first()
    if not row:
        raise HTTPException(status_code=500, detail="Execution not persisted")
    return row


@router.get("/{workflow_id}/executions", response_model=list[ExecutionRead])
def list_executions(
    workflow_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> list[WorkflowExecution]:
    wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not wf or not _can_read_workflow(user, wf):
        raise HTTPException(status_code=404, detail="Workflow not found")
    return (
        db.query(WorkflowExecution)
        .filter(WorkflowExecution.workflow_id == workflow_id)
        .order_by(WorkflowExecution.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.post("/{workflow_id}/activate", response_model=WorkflowRead)
def activate(
    workflow_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> Workflow:
    wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not wf or not _can_write(user, wf):
        raise HTTPException(status_code=404, detail="Workflow not found")
    wf.status = WorkflowStatus.ACTIVE
    db.commit()
    db.refresh(wf)
    return wf


@router.post("/{workflow_id}/deactivate", response_model=WorkflowRead)
def deactivate(
    workflow_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> Workflow:
    wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not wf or not _can_write(user, wf):
        raise HTTPException(status_code=404, detail="Workflow not found")
    wf.status = WorkflowStatus.INACTIVE
    db.commit()
    db.refresh(wf)
    return wf


@router.post(
    "/{workflow_id}/schedules",
    response_model=ScheduledTriggerRead,
    status_code=status.HTTP_201_CREATED,
)
def register_schedule(
    workflow_id: int,
    payload: ScheduledTriggerCreate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> ScheduledTrigger:
    if user.role == UserRole.VIEWER:
        raise HTTPException(status_code=403, detail="Forbidden")
    wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not wf or not _can_write(user, wf):
        raise HTTPException(status_code=404, detail="Workflow not found")
    wf.trigger_type = TriggerType.SCHEDULE
    st = SchedulerService.register_schedule(
        db,
        wf,
        payload.cron_expression,
        is_active=payload.is_active,
    )
    db.refresh(st)
    return st


@router.post(
    "/{workflow_id}/webhook-endpoints",
    response_model=WebhookEndpointWithSecret,
    status_code=status.HTTP_201_CREATED,
)
def register_webhook_endpoint(
    workflow_id: int,
    payload: WebhookEndpointCreate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> WebhookEndpointWithSecret:
    if user.role == UserRole.VIEWER:
        raise HTTPException(status_code=403, detail="Forbidden")
    wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not wf or not _can_write(user, wf):
        raise HTTPException(status_code=404, detail="Workflow not found")
    wf.trigger_type = TriggerType.WEBHOOK
    path = payload.path.strip("/")
    existing = db.query(WebhookEndpoint).filter(WebhookEndpoint.path == path).first()
    if existing:
        raise HTTPException(status_code=400, detail="Path already taken")
    wh = WebhookEndpoint(
        workflow_id=wf.id,
        path=path,
        method=payload.method,
        secret_token=secrets.token_urlsafe(32),
        is_active=True,
    )
    db.add(wh)
    db.commit()
    db.refresh(wh)
    return WebhookEndpointWithSecret(
        id=wh.id,
        workflow_id=wh.workflow_id,
        path=wh.path,
        method=wh.method,
        is_active=wh.is_active,
        total_invocations=wh.total_invocations,
        created_at=wh.created_at,
        secret_token=wh.secret_token,
    )


@router.post("/{workflow_id}/clone", response_model=WorkflowRead)
def clone_workflow(
    workflow_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> Workflow:
    if user.role == UserRole.VIEWER:
        raise HTTPException(status_code=403, detail="Viewers cannot clone workflows")
    wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not wf or not _can_read_workflow(user, wf):
        raise HTTPException(status_code=404, detail="Workflow not found")
    new_wf = Workflow(
        name=f"{wf.name} (copy)",
        description=wf.description,
        owner_id=user.id,
        status=WorkflowStatus.DRAFT,
        trigger_type=wf.trigger_type,
        trigger_config=copy.deepcopy(wf.trigger_config),
        nodes=copy.deepcopy(wf.nodes),
        edges=copy.deepcopy(wf.edges),
        version=1,
        is_template=False,
    )
    db.add(new_wf)
    db.commit()
    db.refresh(new_wf)
    if wf.trigger_type == TriggerType.WEBHOOK:
        for wh in db.query(WebhookEndpoint).filter(WebhookEndpoint.workflow_id == wf.id).all():
            db.add(
                WebhookEndpoint(
                    workflow_id=new_wf.id,
                    path=f"{wh.path}-{secrets.token_hex(4)}",
                    method=wh.method,
                    secret_token=secrets.token_urlsafe(32),
                    is_active=wh.is_active,
                )
            )
        db.commit()
    db.refresh(new_wf)
    return new_wf
