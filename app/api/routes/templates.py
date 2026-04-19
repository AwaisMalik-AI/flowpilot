"""Workflow templates: list, create, instantiate."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User, UserRole
from app.models.workflow import TriggerType, Workflow, WorkflowStatus, WorkflowTemplate
from app.schemas.workflow import TemplateCreate, TemplateRead, TemplateUseResponse, WorkflowRead

router = APIRouter(prefix="/templates", tags=["templates"])


@router.get("", response_model=list[TemplateRead])
def list_templates(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    category: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> list[WorkflowTemplate]:
    _ = user
    q = db.query(WorkflowTemplate)
    if category:
        q = q.filter(WorkflowTemplate.category == category)
    return q.order_by(WorkflowTemplate.usage_count.desc()).offset(skip).limit(limit).all()


@router.post("", response_model=TemplateRead, status_code=status.HTTP_201_CREATED)
def create_template(
    payload: TemplateCreate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> WorkflowTemplate:
    if user.role == UserRole.VIEWER:
        raise HTTPException(status_code=403, detail="Forbidden")
    nodes: list = []
    edges: list = []
    if payload.workflow_id is not None:
        wf = db.query(Workflow).filter(Workflow.id == payload.workflow_id).first()
        if not wf or (user.role != UserRole.ADMIN and wf.owner_id != user.id):
            raise HTTPException(status_code=404, detail="Workflow not found")
        nodes = list(wf.nodes or [])
        edges = list(wf.edges or [])
    tpl = WorkflowTemplate(
        name=payload.name,
        description=payload.description,
        category=payload.category,
        nodes=nodes,
        edges=edges,
        created_by=user.id,
    )
    db.add(tpl)
    db.commit()
    db.refresh(tpl)
    return tpl


@router.post("/{template_id}/use", response_model=TemplateUseResponse)
def use_template(
    template_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> TemplateUseResponse:
    if user.role == UserRole.VIEWER:
        raise HTTPException(status_code=403, detail="Forbidden")
    tpl = db.query(WorkflowTemplate).filter(WorkflowTemplate.id == template_id).first()
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")
    wf = Workflow(
        name=f"{tpl.name} (from template)",
        description=tpl.description,
        owner_id=user.id,
        status=WorkflowStatus.DRAFT,
        trigger_type=TriggerType.MANUAL,
        trigger_config={},
        nodes=list(tpl.nodes or []),
        edges=list(tpl.edges or []),
        version=1,
        is_template=False,
    )
    db.add(wf)
    tpl.usage_count = (tpl.usage_count or 0) + 1
    db.add(tpl)
    db.commit()
    db.refresh(wf)
    return TemplateUseResponse(workflow=WorkflowRead.model_validate(wf))
