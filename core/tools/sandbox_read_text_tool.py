"""Tier 0: read text files from sandbox with bounded output."""

from __future__ import annotations

from typing import Any

from core.policy import ToolTier
from core.sandbox import Sandbox, SandboxError
from core.tools.base import BaseTool, ToolExecutionResult

MAX_PREVIEW_CHARS = 4000


class SandboxReadTextTool(BaseTool):
    name = "sandbox_read_text"
    tier = ToolTier.TIER0

    def __init__(self, sandbox: Sandbox) -> None:
        self._sandbox = sandbox

    def execute(self, payload: dict[str, Any]) -> ToolExecutionResult:
        path = str(payload.get("path", "")).strip()
        if not path:
            return ToolExecutionResult(ok=False, output={"error": "Missing 'path'"})
        try:
            target = self._sandbox.resolve_path(path)
        except SandboxError as err:
            return ToolExecutionResult(ok=False, output={"error": str(err)})
        if not target.exists():
            return ToolExecutionResult(ok=False, output={"error": f"Path does not exist: {target}"})
        if not target.is_file():
            return ToolExecutionResult(ok=False, output={"error": f"Not a file: {target}"})

        try:
            text = target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return ToolExecutionResult(ok=False, output={"error": "File is not UTF-8 text"})

        truncated = text[:MAX_PREVIEW_CHARS]
        return ToolExecutionResult(
            ok=True,
            output={
                "path": str(target),
                "chars": len(text),
                "truncated": len(text) > MAX_PREVIEW_CHARS,
                "preview": truncated,
            },
        )
