"""Dry-run a workflow DAG without executing side-effect nodes."""

from __future__ import annotations

from typing import Any

SAFE = {"condition", "transform", "delay", "llm_agent", "ai_crew", "webhook_response"}
SIDE_EFFECT = {"http_request", "email", "code", "database"}


def simulate(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, Any]:
    plan = []
    blocked = []
    for node in nodes:
        ntype = str(node.get("type", ""))
        item = {"id": node.get("id"), "type": ntype, "would_run": ntype in SAFE or ntype in SIDE_EFFECT}
        if ntype in SIDE_EFFECT:
            item["mode"] = "skipped_side_effect"
            blocked.append(str(node.get("id")))
        else:
            item["mode"] = "simulated"
        plan.append(item)
    return {
        "nodes": len(nodes),
        "edges": len(edges),
        "plan": plan,
        "skipped_side_effects": blocked,
        "safe": True,
    }
