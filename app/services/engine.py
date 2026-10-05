"""DAG workflow execution with branching and variable interpolation."""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.workflow import ExecutionStatus, LogStatus, Workflow, WorkflowExecution, WorkflowLog
from app.services.nodes import (
    CodeNode,
    ConditionNode,
    CrewNode,
    DatabaseNode,
    DelayNode,
    EmailNode,
    HTTPRequestNode,
    LLMAgentNode,
    NodeResult,
    NodeStatus,
    TransformNode,
    WebhookResponseNode,
)

logger = logging.getLogger(__name__)

_VAR_PATTERN = re.compile(r"\{\{\s*([^}]+?)\s*\}\}")


def _get_by_path(root: Any, path: str) -> Any:
    cur: Any = root
    for part in path.split("."):
        if cur is None:
            return None
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def build_interpolation_roots(trigger_data: dict[str, Any], node_outputs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    roots: dict[str, Any] = {"trigger": trigger_data}
    for nid, out in node_outputs.items():
        roots[nid] = {"output": out}
    return roots


def interpolate_value(value: Any, roots: dict[str, Any]) -> Any:
    if isinstance(value, str):

        def repl(m: re.Match[str]) -> str:
            path = m.group(1).strip()
            resolved = _get_by_path(roots, path)
            if resolved is None:
                return ""
            if isinstance(resolved, (dict, list)):
                return json.dumps(resolved)
            return str(resolved)

        return _VAR_PATTERN.sub(repl, value)
    if isinstance(value, dict):
        return {k: interpolate_value(v, roots) for k, v in value.items()}
    if isinstance(value, list):
        return [interpolate_value(v, roots) for v in value]
    return value


@dataclass
class EngineResult:
    execution_id: int
    status: ExecutionStatus
    node_results: dict[str, Any]
    error_message: str | None
    webhook_response: dict[str, Any] | None


class WorkflowEngine:
    def __init__(self) -> None:
        self._registry: dict[str, Any] = {
            HTTPRequestNode.type_name: HTTPRequestNode(),
            ConditionNode.type_name: ConditionNode(),
            TransformNode.type_name: TransformNode(),
            EmailNode.type_name: EmailNode(),
            DelayNode.type_name: DelayNode(),
            CodeNode.type_name: CodeNode(),
            DatabaseNode.type_name: DatabaseNode(),
            WebhookResponseNode.type_name: WebhookResponseNode(),
            LLMAgentNode.type_name: LLMAgentNode(),
            CrewNode.type_name: CrewNode(),
        }

    def resolve_node(self, node_type: str):
        handler = self._registry.get(node_type)
        if handler is None:
            raise ValueError(f"Unknown node type: {node_type}")
        return handler

    def evaluate_edges(
        self,
        source_id: str,
        source_output: dict[str, Any],
        source_status: NodeStatus,
        edges: list[dict[str, Any]],
    ) -> list[str]:
        next_ids: list[str] = []
        for edge in edges:
            if not isinstance(edge, dict) or edge.get("source") != source_id:
                continue
            target = edge.get("target")
            if not target:
                continue
            cond = edge.get("condition")
            branch = edge.get("branch")
            if branch is not None:
                out_branch = source_output.get("branch")
                if str(out_branch) != str(branch):
                    continue
            if cond == "on_success" and source_status != NodeStatus.SUCCESS:
                continue
            if cond == "on_failure" and source_status != NodeStatus.FAILURE:
                continue
            next_ids.append(str(target))
        return next_ids

    def execute_workflow(
        self,
        db: Session,
        workflow: Workflow,
        trigger_data: dict[str, Any],
        *,
        trigger_type: str = "manual",
        execution_row: WorkflowExecution | None = None,
    ) -> EngineResult:
        nodes = workflow.nodes or []
        edges = workflow.edges or []
        node_by_id = {str(n["id"]): n for n in nodes if isinstance(n, dict) and n.get("id")}

        all_ids = set(node_by_id.keys())

        preds: dict[str, list[str]] = {nid: [] for nid in all_ids}
        for e in edges:
            if not isinstance(e, dict):
                continue
            s, t = e.get("source"), e.get("target")
            if s and t and str(t) in preds:
                preds[str(t)].append(str(s))

        if execution_row is None:
            execution_row = WorkflowExecution(
                workflow_id=workflow.id,
                trigger_type=trigger_type,
                trigger_data=trigger_data,
                status=ExecutionStatus.RUNNING,
                started_at=datetime.now(timezone.utc),
            )
            db.add(execution_row)
            db.flush()
        else:
            execution_row.status = ExecutionStatus.RUNNING
            execution_row.started_at = datetime.now(timezone.utc)
            execution_row.error_message = None

        exec_id = execution_row.id
        node_outputs: dict[str, dict[str, Any]] = {}
        completed: set[str] = set()
        failed = False
        error_message: str | None = None
        webhook_response: dict[str, Any] | None = None

        steps = 0
        deadline = time.monotonic() + float(settings.EXECUTION_TIMEOUT_SECONDS)

        def ready(nid: str) -> bool:
            return all(p in completed for p in preds.get(nid, []))

        roots = sorted(nid for nid in all_ids if not preds.get(nid))
        if not roots and all_ids:
            roots = [sorted(all_ids)[0]]
        pending: set[str] = set(roots)

        try:
            while pending and not failed:
                if time.monotonic() > deadline:
                    failed = True
                    error_message = "execution timed out"
                    break
                steps += 1
                if steps > settings.MAX_WORKFLOW_STEPS:
                    failed = True
                    error_message = "max workflow steps exceeded"
                    break

                ready_nodes = sorted(n for n in pending if ready(n))
                if not ready_nodes:
                    failed = True
                    error_message = "deadlock or cycle in workflow graph"
                    break

                nid = ready_nodes[0]
                pending.discard(nid)

                spec = node_by_id[nid]
                ntype = str(spec.get("type", ""))
                raw_config = spec.get("config") or {}

                roots_map = build_interpolation_roots(trigger_data, node_outputs)
                config = interpolate_value(raw_config, roots_map)

                merged_input: dict[str, Any] = {"trigger": trigger_data}
                for p in preds.get(nid, []):
                    merged_input[p] = node_outputs.get(p, {})

                exec_context = {
                    "trigger": trigger_data,
                    "nodes": node_outputs,
                    "workflow_id": workflow.id,
                    "execution_id": exec_id,
                }

                t0 = time.perf_counter()
                try:
                    handler = self.resolve_node(ntype)
                    result: NodeResult = handler.execute(merged_input, config, exec_context)
                except ValueError as e:
                    result = NodeResult(status=NodeStatus.FAILURE, error=str(e))
                except Exception as e:
                    logger.exception("node execution error")
                    result = NodeResult(status=NodeStatus.FAILURE, error=str(e))

                elapsed_ms = int((time.perf_counter() - t0) * 1000)
                node_outputs[nid] = result.output_data
                log_end_status = (
                    LogStatus.COMPLETED
                    if result.status == NodeStatus.SUCCESS
                    else LogStatus.FAILED
                    if result.status == NodeStatus.FAILURE
                    else LogStatus.SKIPPED
                )
                db.add(
                    WorkflowLog(
                        execution_id=exec_id,
                        node_id=nid,
                        node_type=ntype,
                        status=log_end_status,
                        input_data=merged_input,
                        output_data=result.output_data,
                        error_message=result.error,
                        execution_time_ms=elapsed_ms,
                    )
                )

                if ntype == WebhookResponseNode.type_name and result.status == NodeStatus.SUCCESS:
                    webhook_response = result.output_data

                if result.status == NodeStatus.FAILURE:
                    failed = True
                    error_message = result.error or f"node {nid} failed"
                    completed.add(nid)
                    break

                completed.add(nid)
                for nxt in self.evaluate_edges(nid, result.output_data, result.status, edges):
                    if nxt in node_by_id:
                        pending.add(nxt)

            if not failed and pending:
                failed = True
                error_message = error_message or "deadlock or cycle in workflow graph"

        finally:
            ended = datetime.now(timezone.utc)
            execution_row.completed_at = ended
            execution_row.node_results = {
                k: {"output": v, "status": "ok"} for k, v in node_outputs.items()
            }
            if failed:
                if error_message == "execution timed out":
                    execution_row.status = ExecutionStatus.TIMED_OUT
                else:
                    execution_row.status = ExecutionStatus.FAILED
                execution_row.error_message = error_message
            else:
                execution_row.status = ExecutionStatus.COMPLETED
            if execution_row.started_at:
                execution_row.execution_time_ms = int(
                    (ended - execution_row.started_at).total_seconds() * 1000
                )
            db.commit()

        return EngineResult(
            execution_id=exec_id,
            status=execution_row.status,
            node_results=execution_row.node_results or {},
            error_message=execution_row.error_message,
            webhook_response=webhook_response,
        )
