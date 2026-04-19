"""Evaluate conditions and emit branch for downstream routing."""

import re
from typing import Any

from app.services.nodes.base import BaseNode, NodeResult, NodeStatus


def _get_path(data: Any, path: str) -> Any:
    cur: Any = data
    for part in path.split("."):
        if cur is None:
            return None
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


class ConditionNode(BaseNode):
    type_name = "condition"

    def execute(
        self,
        input_data: dict[str, Any],
        config: dict[str, Any],
        context: dict[str, Any],
    ) -> NodeResult:
        _ = context
        rules = config.get("rules") or []
        if not isinstance(rules, list) or not rules:
            return NodeResult(
                output_data={"branch": "default", "matched": False},
                status=NodeStatus.SUCCESS,
            )

        for rule in rules:
            if not isinstance(rule, dict):
                continue
            op = str(rule.get("operator", "equals")).lower()
            left_path = rule.get("left", "")
            right = rule.get("right")
            branch = str(rule.get("branch", "default"))

            left = _get_path(input_data, str(left_path)) if left_path else input_data

            ok = False
            if op == "equals":
                ok = left == right
            elif op == "contains":
                ok = right is not None and str(right) in str(left)
            elif op == "greater_than":
                try:
                    ok = float(left) > float(right)
                except (TypeError, ValueError):
                    ok = False
            elif op == "regex":
                try:
                    ok = re.search(str(right), str(left)) is not None
                except re.error:
                    ok = False
            elif op == "exists":
                ok = left is not None
            else:
                ok = False

            if ok:
                return NodeResult(
                    output_data={"branch": branch, "matched": True, "operator": op},
                    status=NodeStatus.SUCCESS,
                )

        default_branch = str(config.get("default_branch", "else"))
        return NodeResult(
            output_data={"branch": default_branch, "matched": False},
            status=NodeStatus.SUCCESS,
        )
