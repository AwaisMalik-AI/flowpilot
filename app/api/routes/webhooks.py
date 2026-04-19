"""Incoming webhooks and endpoint listing."""

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User, UserRole
from app.models.workflow import TriggerType, WebhookEndpoint, Workflow, WorkflowStatus
from app.schemas.workflow import WebhookEndpointRead
from app.services.engine import WorkflowEngine

router = APIRouter(tags=["webhooks"])


@router.post("/hooks/{path:path}")
async def incoming_webhook(
    path: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    x_flowpilot_token: Annotated[str | None, Header(alias="X-FlowPilot-Token")] = None,
) -> Response:
    """Trigger workflows by webhook path. Authenticate with ``X-FlowPilot-Token`` (endpoint secret)."""
    method = request.method.upper()
    normalized = path.strip("/")
    wh = (
        db.query(WebhookEndpoint)
        .filter(
            WebhookEndpoint.path == normalized,
            WebhookEndpoint.is_active.is_(True),
        )
        .first()
    )
    if not wh:
        raise HTTPException(status_code=404, detail="Unknown webhook path")
    if wh.method.value != method:
        raise HTTPException(status_code=405, detail="Method not allowed")

    token = x_flowpilot_token or request.query_params.get("token")
    if not token or token != wh.secret_token:
        raise HTTPException(status_code=401, detail="Invalid webhook token")

    wf = db.query(Workflow).filter(Workflow.id == wh.workflow_id).first()
    if not wf or wf.status != WorkflowStatus.ACTIVE or wf.trigger_type != TriggerType.WEBHOOK:
        raise HTTPException(status_code=400, detail="Workflow not active for webhooks")

    body: dict[str, Any] = {}
    try:
        if method == "POST":
            ct = request.headers.get("content-type", "")
            if "application/json" in ct:
                body = await request.json()
            else:
                raw = await request.body()
                text = raw.decode("utf-8", errors="replace")
                try:
                    body = json.loads(text) if text else {}
                except json.JSONDecodeError:
                    body = {"raw": text}
    except Exception:
        body = {}

    query = dict(request.query_params)
    trigger_data = {
        "headers": dict(request.headers),
        "query": query,
        "body": body,
        "method": method,
    }

    wh.total_invocations += 1
    db.add(wh)
    db.commit()

    engine = WorkflowEngine()
    result = engine.execute_workflow(db, wf, trigger_data, trigger_type=TriggerType.WEBHOOK.value)

    if result.webhook_response:
        wr = result.webhook_response
        return Response(
            content=wr.get("body", "{}"),
            status_code=int(wr.get("http_status", 200)),
            headers={k: str(v) for k, v in (wr.get("headers") or {}).items()},
            media_type=None,
        )

    return Response(
        content=json.dumps(
            {
                "execution_id": result.execution_id,
                "status": result.status.value,
                "error": result.error_message,
            }
        ),
        status_code=200,
        media_type="application/json",
    )


@router.get("/webhook-endpoints", response_model=list[WebhookEndpointRead])
def list_webhook_endpoints(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> list[WebhookEndpoint]:
    q = db.query(WebhookEndpoint).join(Workflow, Workflow.id == WebhookEndpoint.workflow_id)
    if user.role != UserRole.ADMIN:
        q = q.filter(Workflow.owner_id == user.id)
    return q.order_by(WebhookEndpoint.created_at.desc()).all()
