"""Pause execution for a configured duration."""

import time
from typing import Any

from app.services.nodes.base import BaseNode, NodeResult, NodeStatus


class DelayNode(BaseNode):
    type_name = "delay"

    def execute(
        self,
        input_data: dict[str, Any],
        config: dict[str, Any],
        context: dict[str, Any],
    ) -> NodeResult:
        _ = context
        seconds = float(config.get("seconds", config.get("duration_seconds", 0)))
        max_sleep = float(config.get("max_seconds", 300))
        seconds = max(0, min(seconds, max_sleep))
        time.sleep(seconds)
        return NodeResult(
            output_data={**input_data, "delayed_seconds": seconds},
            status=NodeStatus.SUCCESS,
        )
