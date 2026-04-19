"""Abstract base for workflow nodes."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class NodeStatus(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    SKIPPED = "skipped"


@dataclass
class NodeResult:
    output_data: dict[str, Any] = field(default_factory=dict)
    status: NodeStatus = NodeStatus.SUCCESS
    error: str | None = None


class BaseNode(ABC):
    """Each node receives resolved input, config, and execution context."""

    type_name: str = "base"

    @abstractmethod
    def execute(
        self,
        input_data: dict[str, Any],
        config: dict[str, Any],
        context: dict[str, Any],
    ) -> NodeResult:
        """Run the node and return structured output."""
