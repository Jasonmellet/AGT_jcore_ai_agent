"""Tier 0: list files inside sandbox safely."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.policy import ToolTier
from core.sandbox import Sandbox, SandboxError
from core.tools.base import BaseTool, ToolExecutionResult


class SandboxListTool(BaseTool):
    name = "sandbox_list"
    tier = ToolTier.TIER0

    def __init__(self, sandbox: Sandbox) -> None:
        self._sandbox = sandbox

    def execute(self, payload: dict[str, Any]) -> ToolExecutionResult:
        subpath = str(payload.get("subpath", "."))
        max_entries = int(payload.get("max_entries", 100))
        max_entries = max(1, min(500, max_entries))
        try:
            target = self._sandbox.resolve_path(subpath)
        except SandboxError as err:
            return ToolExecutionResult(ok=False, output={"error": str(err)})
        if not target.exists():
            return ToolExecutionResult(ok=False, output={"error": f"Path does not exist: {target}"})
        if not target.is_dir():
            return ToolExecutionResult(ok=False, output={"error": f"Not a directory: {target}"})

        entries: list[dict[str, Any]] = []
        for child in sorted(target.iterdir(), key=lambda p: p.name)[:max_entries]:
            rel = child.relative_to(self._sandbox.root)
            entries.append(
                {
                    "name": child.name,
                    "relative_path": str(rel),
                    "kind": "dir" if child.is_dir() else "file",
                    "size_bytes": child.stat().st_size if child.is_file() else None,
                }
            )

        return ToolExecutionResult(
            ok=True,
            output={
                "root": str(self._sandbox.root),
                "target": str(target),
                "count": len(entries),
                "entries": entries,
            },
        )
