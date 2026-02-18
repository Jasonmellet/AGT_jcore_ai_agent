"""Policy engine for tool-tier enforcement."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from core.profile import Profile


class ToolTier(str, Enum):
    TIER0 = "tier0"
    TIER1 = "tier1"
    TIER2 = "tier2"


class PolicyDecision(str, Enum):
    ALLOW = "allow"
    REQUIRE_APPROVAL = "require_approval"
    DENY = "deny"


@dataclass(frozen=True)
class PolicyResult:
    decision: PolicyDecision
    reason: str


class PolicyEngine:
    """Evaluates whether a profile can execute a given tool tier."""

    def __init__(self, profile: Profile) -> None:
        self._profile = profile
        self._allowed = {ToolTier(value) for value in profile.allowed_tool_tiers}

    def check(self, tool_name: str, tier: ToolTier) -> PolicyResult:
        """Return ALLOW, REQUIRE_APPROVAL, or DENY for a tool call."""
        if tier == ToolTier.TIER0:
            if ToolTier.TIER0 in self._allowed:
                return PolicyResult(PolicyDecision.ALLOW, f"{tool_name} is Tier 0")
            return PolicyResult(PolicyDecision.DENY, "Tier 0 is not permitted for this profile")

        if tier == ToolTier.TIER1:
            if ToolTier.TIER1 in self._allowed:
                return PolicyResult(
                    PolicyDecision.REQUIRE_APPROVAL,
                    f"{tool_name} requires human approval (Tier 1)",
                )
            return PolicyResult(PolicyDecision.DENY, "Tier 1 is not permitted for this profile")

        if tier == ToolTier.TIER2:
            if ToolTier.TIER2 in self._allowed:
                return PolicyResult(
                    PolicyDecision.REQUIRE_APPROVAL,
                    f"{tool_name} requires Jason Core approval (Tier 2)",
                )
            return PolicyResult(PolicyDecision.DENY, "Tier 2 is restricted to Jason Core")

        return PolicyResult(PolicyDecision.DENY, "Unknown tool tier")

    def check_skill_permissions(self, permissions_requested: list[str]) -> PolicyResult:
        risky = {"screen", "filesystem_write", "network_external", "secrets_access"}
        requested = {perm for perm in permissions_requested if perm}
        risky_found = sorted(requested.intersection(risky))
        if not risky_found:
            return PolicyResult(PolicyDecision.ALLOW, "No risky skill permissions requested")
        return PolicyResult(
            PolicyDecision.REQUIRE_APPROVAL,
            f"Skill permissions require approval: {', '.join(risky_found)}",
        )
