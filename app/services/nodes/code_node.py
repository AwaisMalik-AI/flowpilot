"""Evaluate a restricted Python expression against input and context."""

import platform
import signal
from contextlib import contextmanager
from typing import Any

from app.services.nodes.base import BaseNode, NodeResult, NodeStatus

_ALLOWED_BUILTINS = {
    "abs": abs,
    "min": min,
    "max": max,
    "sum": sum,
    "len": len,
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "list": list,
    "dict": dict,
    "tuple": tuple,
    "set": set,
    "enumerate": enumerate,
    "zip": zip,
    "range": range,
    "round": round,
    "sorted": sorted,
    "any": any,
    "all": all,
    "isinstance": isinstance,
    "repr": repr,
}


class _Timeout(Exception):
    pass


@contextmanager
def _time_limit(seconds: float):
    if seconds <= 0 or platform.system() == "Windows":
        yield
        return

    def handler(signum, frame):
        raise _Timeout("code_node timeout")

    previous = signal.signal(signal.SIGALRM, handler)
    signal.setitimer(signal.ITIMER_REAL, float(seconds))
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


class CodeNode(BaseNode):
    type_name = "code"

    def execute(
        self,
        input_data: dict[str, Any],
        config: dict[str, Any],
        context: dict[str, Any],
    ) -> NodeResult:
        expression = config.get("expression") or config.get("code")
        if not expression:
            return NodeResult(status=NodeStatus.FAILURE, error="expression is required")
        expr_str = str(expression)
        max_len = int(config.get("max_expression_length", 4000))
        if len(expr_str) > max_len:
            return NodeResult(status=NodeStatus.FAILURE, error="expression too long")
        timeout = float(config.get("timeout_seconds", 2))

        local_ns = {
            "input": input_data,
            "context": context,
            "trigger": context.get("trigger"),
            "nodes": context.get("nodes"),
        }
        global_ns = {"__builtins__": _ALLOWED_BUILTINS}

        try:
            if platform.system() != "Windows" and hasattr(signal, "SIGALRM"):
                with _time_limit(timeout):
                    result = eval(expr_str, global_ns, local_ns)
            else:
                result = eval(expr_str, global_ns, local_ns)
        except _Timeout:
            return NodeResult(status=NodeStatus.FAILURE, error="expression timed out")
        except Exception as e:
            return NodeResult(status=NodeStatus.FAILURE, error=str(e))

        if not isinstance(result, dict):
            result = {"value": result}
        return NodeResult(output_data=result, status=NodeStatus.SUCCESS)
