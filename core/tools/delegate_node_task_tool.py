"""Tier 2: delegate a bounded task to another family node via interop bridge."""

from __future__ import annotations

from typing import Any

from core.interop.bridge import InteropBridge
from core.policy import ToolTier
from core.tools.base import BaseTool, ToolExecutionResult


class DelegateNodeTaskTool(BaseTool):
    name = "delegate_node_task"
    tier = ToolTier.TIER2

    def __init__(self, bridge: InteropBridge) -> None:
        self._bridge = bridge

    def execute(self, payload: dict[str, Any]) -> ToolExecutionResult:
        target = str(payload.get("target_profile", "")).strip()
        task_type = str(payload.get("task_type", "")).strip()
        task_payload = payload.get("task_payload")
        if not target:
            return ToolExecutionResult(ok=False, output={"error": "Missing target_profile"})
        if not task_type:
            return ToolExecutionResult(ok=False, output={"error": "Missing task_type"})
        if not isinstance(task_payload, dict):
            return ToolExecutionResult(ok=False, output={"error": "task_payload must be an object"})
        try:
            result = self._bridge.send_task(target, task_type, task_payload)
            return ToolExecutionResult(ok=True, output=result)
        except RuntimeError as exc:
            return ToolExecutionResult(ok=False, output={"error": str(exc)})
