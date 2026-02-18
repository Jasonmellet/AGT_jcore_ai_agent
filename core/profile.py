"""Profile configuration loader and path resolver."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class ProfilePaths:
    base_data_dir: Path
    db_path: Path
    logs_dir: Path
    secrets_dir: Path
    sandbox_dir: Path


@dataclass(frozen=True)
class Profile:
    name: str
    display_name: str
    policy_tier: str
    allowed_tool_tiers: list[str]
    health_port: int
    llm_default_model: str
    public_readonly_mode: bool
    public_readonly_get_endpoints: list[str]
    paths: ProfilePaths


class ProfileError(ValueError):
    """Raised when profile configuration is invalid."""


def _validate_raw_profile(raw: dict[str, Any], expected_name: str) -> None:
    required = {"name", "display_name", "policy_tier", "allowed_tool_tiers"}
    missing = required.difference(raw.keys())
    if missing:
        missing_joined = ", ".join(sorted(missing))
        raise ProfileError(f"Missing required profile keys: {missing_joined}")

    if raw["name"] != expected_name:
        raise ProfileError(
            f"Profile filename/name mismatch: expected '{expected_name}', got '{raw['name']}'"
        )

    if not isinstance(raw["allowed_tool_tiers"], list) or not raw["allowed_tool_tiers"]:
        raise ProfileError("allowed_tool_tiers must be a non-empty list")


def load_profile(profile_name: str, repo_root: Path | None = None) -> Profile:
    """Load a profile from config and resolve data paths."""
    if repo_root is None:
        repo_root = Path(__file__).resolve().parent.parent

    profile_path = repo_root / "config" / "profiles" / f"{profile_name}.yaml"
    if not profile_path.exists():
        raise ProfileError(f"Profile not found: {profile_path}")

    with profile_path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    if not isinstance(raw, dict):
        raise ProfileError(f"Profile file must contain a mapping: {profile_path}")

    _validate_raw_profile(raw, profile_name)

    base_data_dir = Path.home() / "agentdata" / profile_name
    paths = ProfilePaths(
        base_data_dir=base_data_dir,
        db_path=base_data_dir / "memory.db",
        logs_dir=base_data_dir / "logs",
        secrets_dir=base_data_dir / "secrets",
        sandbox_dir=base_data_dir / "sandbox",
    )

    return Profile(
        name=raw["name"],
        display_name=raw["display_name"],
        policy_tier=raw["policy_tier"],
        allowed_tool_tiers=list(raw["allowed_tool_tiers"]),
        health_port=int(raw.get("health_port", 8600)),
        llm_default_model=str(raw.get("llm_default_model", "gpt-4o-mini")).strip() or "gpt-4o-mini",
        public_readonly_mode=bool(raw.get("public_readonly_mode", False)),
        public_readonly_get_endpoints=list(
            raw.get(
                "public_readonly_get_endpoints",
                ["/health", "/status", "/api-usage", "/backup/status"],
            )
        ),
        paths=paths,
    )


def ensure_profile_directories(profile: Profile) -> None:
    """Create profile directories without touching existing data."""
    profile.paths.base_data_dir.mkdir(parents=True, exist_ok=True)
    profile.paths.logs_dir.mkdir(parents=True, exist_ok=True)
    profile.paths.secrets_dir.mkdir(parents=True, exist_ok=True)
    profile.paths.sandbox_dir.mkdir(parents=True, exist_ok=True)
