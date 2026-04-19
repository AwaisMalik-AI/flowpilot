from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.workflow import (
    ExecutionStatus,
    LogStatus,
    TriggerType,
    WebhookMethod,
    WorkflowStatus,
)


class WorkflowCreate(BaseModel):
    name: str = Field(max_length=255)
    description: str | None = None
    status: WorkflowStatus = WorkflowStatus.DRAFT
    trigger_type: TriggerType = TriggerType.MANUAL
    trigger_config: dict[str, Any] = Field(default_factory=dict)
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)
    is_template: bool = False


class WorkflowUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    description: str | None = None
    status: WorkflowStatus | None = None
    trigger_type: TriggerType | None = None
    trigger_config: dict[str, Any] | None = None
    nodes: list[dict[str, Any]] | None = None
    edges: list[dict[str, Any]] | None = None
    is_template: bool | None = None


class WorkflowRead(BaseModel):
    id: int
    name: str
    description: str | None
    owner_id: int
    status: WorkflowStatus
    trigger_type: TriggerType
    trigger_config: dict[str, Any]
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    version: int
    is_template: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WorkflowListItem(BaseModel):
    id: int
    name: str
    status: WorkflowStatus
    trigger_type: TriggerType
    version: int
    created_at: datetime

    model_config = {"from_attributes": True}


class WorkflowLogRead(BaseModel):
    id: int
    execution_id: int
    node_id: str
    node_type: str
    status: LogStatus
    input_data: dict[str, Any] | None
    output_data: dict[str, Any] | None
    error_message: str | None
    execution_time_ms: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ExecutionRead(BaseModel):
    id: int
    workflow_id: int
    trigger_type: str
    status: ExecutionStatus
    started_at: datetime | None
    completed_at: datetime | None
    execution_time_ms: int | None
    error_message: str | None
    retry_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ExecutionDetail(ExecutionRead):
    trigger_data: dict[str, Any]
    node_results: dict[str, Any]
    logs: list[WorkflowLogRead] = []


class ManualExecuteRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)


class WebhookEndpointCreate(BaseModel):
    path: str = Field(max_length=255, pattern=r"^[a-zA-Z0-9_\-/]+$")
    method: WebhookMethod = WebhookMethod.POST


class WebhookEndpointRead(BaseModel):
    id: int
    workflow_id: int
    path: str
    method: WebhookMethod
    is_active: bool
    total_invocations: int
    created_at: datetime

    model_config = {"from_attributes": True}


class WebhookEndpointWithSecret(WebhookEndpointRead):
    """Returned once when a webhook endpoint is created — store the secret securely."""

    secret_token: str


class ScheduledTriggerCreate(BaseModel):
    cron_expression: str = Field(max_length=128)
    is_active: bool = True


class ScheduledTriggerRead(BaseModel):
    id: int
    workflow_id: int
    cron_expression: str
    next_run_at: datetime
    last_run_at: datetime | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class TemplateCreate(BaseModel):
    name: str = Field(max_length=255)
    description: str | None = None
    category: str = Field(default="general", max_length=128)
    workflow_id: int | None = Field(
        default=None,
        description="If set, copy nodes/edges from this workflow",
    )


class TemplateRead(BaseModel):
    id: int
    name: str
    description: str | None
    category: str
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    created_by: int
    usage_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class TemplateUseResponse(BaseModel):
    workflow: WorkflowRead
