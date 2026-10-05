"""Crew node — sequential specialist handoffs inside a workflow."""

from __future__ import annotations

from typing import Any

from app.services.nodes.base import BaseNode, NodeResult, NodeStatus
from app.services.nodes.llm_agent_node import LLMAgentNode


class CrewNode(BaseNode):
    type_name = "ai_crew"

    def execute(
        self,
        input_data: dict[str, Any],
        config: dict[str, Any],
        context: dict[str, Any],
    ) -> NodeResult:
        roles = config.get("roles") or ["researcher", "planner", "critic"]
        goal = str(config.get("goal") or input_data.get("trigger") or "complete the workflow step")
        agent = LLMAgentNode()
        steps: list[dict[str, Any]] = []
        memory = ""
        for role in roles:
            result = agent.execute(
                input_data,
                {"role": str(role), "prompt": f"Goal: {goal}\nPrior: {memory}"},
                context,
            )
            text = (result.output_data or {}).get("text", "")
            memory = text
            steps.append({"role": role, "text": text})
        return NodeResult(
            output_data={"goal": goal, "steps": steps, "final": memory},
            status=NodeStatus.SUCCESS,
        )
