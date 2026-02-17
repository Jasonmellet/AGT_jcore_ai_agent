"""Tier 0: return current time (read-only)."""

from __future__ import annotations

import time
from typing import Any

from core.policy import ToolTier
from core.tools.base import BaseTool, ToolExecutionResult


class GetTimeTool(BaseTool):
    name = "get_time"
    tier = ToolTier.TIER0

    def execute(self, payload: dict[str, Any]) -> ToolExecutionResult:
        t = time.time()
        return ToolExecutionResult(
            ok=True,
            output={
                "epoch_seconds": t,
                "iso8601": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t)),
            },
        )
