"""Shape the HTTP response returned to webhook callers (stored for API layer)."""

import json
from typing import Any

from app.services.nodes.base import BaseNode, NodeResult, NodeStatus


class WebhookResponseNode(BaseNode):
    type_name = "webhook_response"

    def execute(
        self,
        input_data: dict[str, Any],
        config: dict[str, Any],
        context: dict[str, Any],
    ) -> NodeResult:
        _ = context
        status_code = int(config.get("status_code", 200))
        headers = dict(config.get("headers") or {})
        body = config.get("body")
        if body is None:
            body_payload: Any = {**input_data}
        else:
            body_payload = body

        if isinstance(body_payload, (dict, list)):
            content = json.dumps(body_payload)
            headers.setdefault("content-type", "application/json")
        else:
            content = str(body_payload)

        return NodeResult(
            output_data={
                "http_status": status_code,
                "headers": headers,
                "body": content,
            },
            status=NodeStatus.SUCCESS,
        )
