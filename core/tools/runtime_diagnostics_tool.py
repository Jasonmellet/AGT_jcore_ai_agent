"""Tier 0: lightweight runtime diagnostics."""

from __future__ import annotations

import os
import platform
import time
from pathlib import Path
from typing import Any

from core.policy import ToolTier
from core.profile import Profile
from core.tools.base import BaseTool, ToolExecutionResult


class RuntimeDiagnosticsTool(BaseTool):
    name = "runtime_diagnostics"
    tier = ToolTier.TIER0

    def __init__(self, profile: Profile) -> None:
        self._profile = profile

    def execute(self, payload: dict[str, Any]) -> ToolExecutionResult:
        _ = payload
        load_avg: tuple[float, float, float] | None
        try:
            load_avg = os.getloadavg()
        except (OSError, AttributeError):
            load_avg = None
        return ToolExecutionResult(
            ok=True,
            output={
                "profile": self._profile.name,
                "host": platform.node(),
                "platform": platform.platform(),
                "python": platform.python_version(),
                "cwd": str(Path.cwd()),
                "timestamp": int(time.time()),
                "load_avg": list(load_avg) if load_avg else None,
            },
        )
