"""HTTP request node with templated URL, headers, and body."""

import json
import re
import time
from typing import Any

import httpx

from app.services.nodes.base import BaseNode, NodeResult, NodeStatus


class HTTPRequestNode(BaseNode):
    type_name = "http_request"

    def execute(
        self,
        input_data: dict[str, Any],
        config: dict[str, Any],
        context: dict[str, Any],
    ) -> NodeResult:
        _ = context
        method = str(config.get("method", "GET")).upper()
        url = str(config.get("url", ""))
        if not url:
            return NodeResult(status=NodeStatus.FAILURE, error="url is required")

        timeout = float(config.get("timeout_seconds", 30))
        headers = dict(config.get("headers") or {})
        body = config.get("body")
        follow_redirects = bool(config.get("follow_redirects", True))

        try:
            started = time.perf_counter()
            with httpx.Client(timeout=timeout, follow_redirects=follow_redirects) as client:
                kwargs: dict[str, Any] = {"method": method, "url": url, "headers": headers}
                if method in ("POST", "PUT", "PATCH", "DELETE") and body is not None:
                    if isinstance(body, (dict, list)):
                        kwargs["json"] = body
                    else:
                        kwargs["content"] = str(body).encode()
                resp = client.request(**kwargs)
            elapsed_ms = int((time.perf_counter() - started) * 1000)

            parse_as = str(config.get("parse_response_as", "auto")).lower()
            content_type = resp.headers.get("content-type", "")
            text = resp.text
            parsed: Any = text
            if parse_as == "json" or (
                parse_as == "auto" and "application/json" in content_type.lower()
            ):
                try:
                    parsed = resp.json()
                except json.JSONDecodeError:
                    parsed = {"raw": text}
            elif parse_as == "auto" and re.search(r"^\s*[\[{]", text):
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    pass

            output = {
                "status_code": resp.status_code,
                "headers": dict(resp.headers),
                "body": parsed,
                "elapsed_ms": elapsed_ms,
                "ok": resp.is_success,
            }
            if not resp.is_success and config.get("fail_on_error", True):
                return NodeResult(
                    output_data=output,
                    status=NodeStatus.FAILURE,
                    error=f"HTTP {resp.status_code}",
                )
            return NodeResult(output_data=output, status=NodeStatus.SUCCESS)
        except Exception as e:
            return NodeResult(status=NodeStatus.FAILURE, error=str(e))
