"""Tier 1: request to send an email (enqueues for human approval)."""

from __future__ import annotations

from typing import Any

from core.policy import ToolTier
from core.tools.base import BaseTool, ToolExecutionResult


class RequestEmailTool(BaseTool):
    name = "request_email"
    tier = ToolTier.TIER1

    def execute(self, payload: dict[str, Any]) -> ToolExecutionResult:
        to = payload.get("to") or ""
        subject = (payload.get("subject") or "").strip()
        body = (payload.get("body") or "").strip()
        if not to:
            return ToolExecutionResult(ok=False, output={"error": "Missing 'to' address"})
        return ToolExecutionResult(
            ok=True,
            output={
                "message": "Email request queued for approval",
                "to": to,
                "subject": subject,
                "body_preview": body[:200] + ("..." if len(body) > 200 else ""),
            },
        )