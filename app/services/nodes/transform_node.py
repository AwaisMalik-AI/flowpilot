"""Field mapping, JSONPath-like keys, templates, and type coercion."""

import json
import re
from typing import Any

from app.services.nodes.base import BaseNode, NodeResult, NodeStatus


def _get_nested(obj: Any, path: str) -> Any:
    cur = obj
    for key in path.split("."):
        if cur is None:
            return None
        if isinstance(cur, dict):
            cur = cur.get(key)
        elif isinstance(cur, list) and key.isdigit():
            idx = int(key)
            cur = cur[idx] if 0 <= idx < len(cur) else None
        else:
            return None
    return cur


def _set_nested(target: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    cur: Any = target
    for p in parts[:-1]:
        if p not in cur or not isinstance(cur[p], dict):
            cur[p] = {}
        cur = cur[p]
    cur[parts[-1]] = value


class TransformNode(BaseNode):
    type_name = "transform"

    def execute(
        self,
        input_data: dict[str, Any],
        config: dict[str, Any],
        context: dict[str, Any],
    ) -> NodeResult:
        merge_input = bool(config.get("merge_input", True))
        out: dict[str, Any] = dict(input_data) if merge_input else {}

        # field_map: { "target.path": "source.path" }
        field_map = config.get("field_map") or {}
        if isinstance(field_map, dict):
            for target, source in field_map.items():
                val = _get_nested(input_data, str(source))
                _set_nested(out, str(target), val)

        extractions = config.get("extractions") or []
        if isinstance(extractions, list):
            for item in extractions:
                if not isinstance(item, dict):
                    continue
                src = str(item.get("from", ""))
                to = str(item.get("to", src))
                val = _get_nested(input_data, src)
                _set_nested(out, to, val)

        template_str = config.get("template")
        if template_str:
            rendered = self._interpolate(str(template_str), {**context, "input": input_data, "output": out})
            out["rendered"] = rendered

        conversions = config.get("conversions") or []
        if isinstance(conversions, list):
            for c in conversions:
                if not isinstance(c, dict):
                    continue
                path = str(c.get("path", ""))
                to_type = str(c.get("to", "str")).lower()
                raw = _get_nested(out, path)
                try:
                    if to_type == "int":
                        coerced = int(raw)
                    elif to_type == "float":
                        coerced = float(raw)
                    elif to_type == "bool":
                        coerced = str(raw).lower() in ("1", "true", "yes", "on")
                    elif to_type == "json":
                        coerced = json.loads(str(raw))
                    else:
                        coerced = str(raw)
                    _set_nested(out, path, coerced)
                except (ValueError, TypeError, json.JSONDecodeError):
                    return NodeResult(
                        status=NodeStatus.FAILURE,
                        error=f"conversion failed for {path}",
                    )

        return NodeResult(output_data=out, status=NodeStatus.SUCCESS)

    def _interpolate(self, template: str, ctx: dict[str, Any]) -> str:
        def repl(m: re.Match[str]) -> str:
            key = m.group(1).strip()
            val = _get_nested(ctx, key)
            return "" if val is None else str(val)

        return re.sub(r"\{\{\s*([^}]+?)\s*\}\}", repl, template)
