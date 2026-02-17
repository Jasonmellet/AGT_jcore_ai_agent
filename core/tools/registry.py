"""Tool registry with policy and approval gating."""

from __future__ import annotations

from typing import Any

from core.approval.engine import ApprovalEngine
from core.memory.episodic_memory import EpisodicMemoryStore
from core.policy import PolicyDecision, PolicyEngine
from core.tools.base import BaseTool, ToolExecutionResult


class ToolRegistry:
    def __init__(
        self,
        policy_engine: PolicyEngine,
        approval_engine: ApprovalEngine,
        episodic_memory: EpisodicMemoryStore,
        profile_name: str,
    ) -> None:
        self._policy = policy_engine
        self._approval = approval_engine
        self._episodic = episodic_memory
        self._profile_name = profile_name
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def count(self) -> int:
        return len(self._tools)

    def list_tools(self) -> list[str]:
        return sorted(self._tools.keys())

    def execute(self, tool_name: str, payload: dict[str, Any]) -> ToolExecutionResult:
        tool = self._tools.get(tool_name)
        if tool is None:
            return ToolExecutionResult(ok=False, output={"error": f"Unknown tool: {tool_name}"})

        policy = self._policy.check(tool_name, tool.tier)
        if policy.decision == PolicyDecision.DENY:
            self._episodic.record(
                "tool_denied",
                {"tool_name": tool_name, "reason": policy.reason, "payload": payload},
                tool_name=tool_name,
                decision=policy.decision.value,
            )
            return ToolExecutionResult(ok=False, output={"error": policy.reason})

        if policy.decision == PolicyDecision.REQUIRE_APPROVAL:
            approval_id = self._approval.enqueue(
                profile_name=self._profile_name,
                tool_name=tool_name,
                tier=tool.tier.value,
                payload=payload,
            )
            self._episodic.record(
                "tool_queued_for_approval",
                {"approval_id": approval_id, "tool_name": tool_name, "payload": payload},
                tool_name=tool_name,
                decision=policy.decision.value,
            )
            return ToolExecutionResult(
                ok=False,
                output={
                    "approval_required": True,
                    "approval_id": approval_id,
                    "reason": policy.reason,
                },
            )

        result = tool.execute(payload)
        self._episodic.record(
            "tool_executed",
            {"tool_name": tool_name, "payload": payload, "output": result.output},
            tool_name=tool_name,
            decision=policy.decision.value,
        )
        return result

    def execute_approved(self, approval_id: int) -> ToolExecutionResult:
        approval = self._approval.get(approval_id)
        if approval is None:
            return ToolExecutionResult(ok=False, output={"error": "Approval not found"})
        if approval["status"] != "approved":
            return ToolExecutionResult(
                ok=False,
                output={"error": f"Approval {approval_id} is not approved"},
            )
        if approval.get("execution_status") == "executed":
            return ToolExecutionResult(
                ok=True,
                output={
                    "already_executed": True,
                    "approval_id": approval_id,
                    "execution_result": approval.get("execution_result") or {},
                },
            )

        tool_name = str(approval["tool_name"])
        payload = dict(approval["payload"])
        tool = self._tools.get(tool_name)
        if tool is None:
            return ToolExecutionResult(ok=False, output={"error": f"Unknown tool: {tool_name}"})

        result = tool.execute(payload)
        persisted = self._approval.mark_executed(
            approval_id,
            {"ok": result.ok, "output": result.output},
        )
        self._episodic.record(
            "tool_executed_after_approval",
            {
                "approval_id": approval_id,
                "tool_name": tool_name,
                "payload": payload,
                "result": result.output,
                "execution_status_persisted": persisted,
            },
            tool_name=tool_name,
            decision=PolicyDecision.ALLOW.value,
        )
        return result
