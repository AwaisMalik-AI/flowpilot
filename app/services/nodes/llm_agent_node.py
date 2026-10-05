"""LLM agent node — optional model call with deterministic fallback."""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings
from app.services.nodes.base import BaseNode, NodeResult, NodeStatus


class LLMAgentNode(BaseNode):
    type_name = "llm_agent"

    def execute(
        self,
        input_data: dict[str, Any],
        config: dict[str, Any],
        context: dict[str, Any],
    ) -> NodeResult:
        _ = context
        role = str(config.get("role", "analyst"))
        prompt = str(config.get("prompt") or config.get("instruction") or "")
        if not prompt:
            prompt = str(input_data.get("trigger") or input_data)
        temperature = float(config.get("temperature", 0.2))
        text, used = self._complete(role, prompt, input_data, temperature)
        return NodeResult(
            output_data={"role": role, "text": text, "used_llm": used},
            status=NodeStatus.SUCCESS,
        )

    def _complete(
        self,
        role: str,
        prompt: str,
        input_data: dict[str, Any],
        temperature: float,
    ) -> tuple[str, bool]:
        api_key = getattr(settings, "LLM_API_KEY", None)
        if not api_key:
            return f"[{role}] {prompt[:280]} | input_keys={list(input_data)[:8]}", False
        url = (getattr(settings, "LLM_BASE_URL", None) or "https://api.openai.com/v1").rstrip("/") + "/chat/completions"
        model = getattr(settings, "LLM_MODEL", "gpt-4o-mini")
        try:
            with httpx.Client(timeout=45.0) as client:
                resp = client.post(
                    url,
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={
                        "model": model,
                        "temperature": temperature,
                        "messages": [
                            {"role": "system", "content": f"You are a workflow {role} agent."},
                            {"role": "user", "content": prompt},
                        ],
                    },
                )
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"], True
        except Exception as exc:
            return f"[{role} fallback] {prompt[:200]} ({exc})", False
