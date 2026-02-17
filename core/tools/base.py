"""Base interface for tools."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from core.policy import ToolTier


@dataclass(frozen=True)
class ToolExecutionResult:
    ok: bool
    output: dict[str, Any]


class BaseTool(ABC):
    name: str
    tier: ToolTier

    @abstractmethod
    def execute(self, payload: dict[str, Any]) -> ToolExecutionResult:
        """Run tool with validated payload."""
