"""Read-only SQL execution against a configured DSN (use with care in production)."""

import re
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Result

from app.services.nodes.base import BaseNode, NodeResult, NodeStatus

_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|EXEC|EXECUTE|CALL)\b",
    re.IGNORECASE | re.DOTALL,
)


class DatabaseNode(BaseNode):
    type_name = "database"

    def execute(
        self,
        input_data: dict[str, Any],
        config: dict[str, Any],
        context: dict[str, Any],
    ) -> NodeResult:
        _ = context
        dsn = config.get("database_url") or config.get("dsn")
        sql = str(config.get("query") or config.get("sql") or "").strip()
        max_rows = int(config.get("max_rows", 1000))

        if not dsn or not sql:
            return NodeResult(status=NodeStatus.FAILURE, error="database_url and query are required")

        if ";" in sql.rstrip(";"):
            return NodeResult(status=NodeStatus.FAILURE, error="only a single statement is allowed")

        if _FORBIDDEN.search(sql):
            return NodeResult(status=NodeStatus.FAILURE, error="only read-only SELECT queries are allowed")

        if not re.match(r"^\s*SELECT\b", sql, re.IGNORECASE):
            return NodeResult(status=NodeStatus.FAILURE, error="query must start with SELECT")

        try:
            engine = create_engine(str(dsn), pool_pre_ping=True)
            with engine.connect() as conn:
                result: Result = conn.execute(text(sql))
                rows = result.mappings().fetchmany(max_rows + 1)
            if len(rows) > max_rows:
                return NodeResult(
                    status=NodeStatus.FAILURE,
                    error=f"result exceeded max_rows={max_rows}",
                )
            data = [dict(r) for r in rows]
            return NodeResult(output_data={"rows": data, "count": len(data)}, status=NodeStatus.SUCCESS)
        except Exception as e:
            return NodeResult(status=NodeStatus.FAILURE, error=str(e))
