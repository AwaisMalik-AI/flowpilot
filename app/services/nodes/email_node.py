"""Send email via SMTP using template variables in subject/body."""

import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from app.services.nodes.base import BaseNode, NodeResult, NodeStatus


def _flatten(prefix: str, obj: Any, bag: dict[str, str]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            _flatten(f"{prefix}.{k}" if prefix else k, v, bag)
    elif isinstance(obj, list):
        bag[prefix] = ",".join(str(x) for x in obj)
    else:
        bag[prefix] = "" if obj is None else str(obj)


def _render(template: str, variables: dict[str, str]) -> str:
    def repl(m: re.Match[str]) -> str:
        key = m.group(1).strip()
        return variables.get(key, m.group(0))

    return re.sub(r"\{\{\s*([^}]+?)\s*\}\}", repl, template)


class EmailNode(BaseNode):
    type_name = "email"

    def execute(
        self,
        input_data: dict[str, Any],
        config: dict[str, Any],
        context: dict[str, Any],
    ) -> NodeResult:
        host = config.get("smtp_host")
        port = int(config.get("smtp_port", 587))
        user = config.get("smtp_user")
        password = config.get("smtp_password")
        use_tls = bool(config.get("use_tls", True))
        from_addr = config.get("from_address")
        to_addrs = config.get("to_addresses") or []
        if isinstance(to_addrs, str):
            to_addrs = [to_addrs]
        subject_t = str(config.get("subject", ""))
        body_t = str(config.get("body", ""))
        html = bool(config.get("html", False))

        if not host or not from_addr or not to_addrs:
            return NodeResult(
                status=NodeStatus.FAILURE,
                error="smtp_host, from_address, and to_addresses are required",
            )

        bag: dict[str, str] = {}
        _flatten("input", input_data, bag)
        _flatten("trigger", context.get("trigger") or {}, bag)
        for k, v in (context.get("nodes") or {}).items():
            if isinstance(v, dict):
                _flatten(f"nodes.{k}", v, bag)

        subject = _render(subject_t, bag)
        body = _render(body_t, bag)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = ", ".join(str(x) for x in to_addrs)
        msg.attach(MIMEText(body, "html" if html else "plain"))

        try:
            with smtplib.SMTP(host, port, timeout=30) as server:
                if use_tls:
                    server.starttls()
                if user and password:
                    server.login(str(user), str(password))
                server.sendmail(from_addr, [str(x) for x in to_addrs], msg.as_string())
        except Exception as e:
            return NodeResult(status=NodeStatus.FAILURE, error=str(e))

        return NodeResult(
            output_data={"sent": True, "recipients": list(to_addrs)},
            status=NodeStatus.SUCCESS,
        )
