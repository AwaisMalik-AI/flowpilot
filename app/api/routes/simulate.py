from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.deps import get_current_user
from app.models.user import User
from app.services.dry_run import simulate

router = APIRouter(prefix="/simulate", tags=["simulate"])


class SimulateRequest(BaseModel):
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)


@router.post("")
def dry_run(body: SimulateRequest, _: Annotated[User, Depends(get_current_user)]) -> dict[str, Any]:
    return {"kind": "workflow_dry_run", **simulate(body.nodes, body.edges)}
