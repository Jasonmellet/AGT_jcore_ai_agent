"""Sandbox directory management and path safety checks."""

from __future__ import annotations

from pathlib import Path

from core.profile import Profile


class SandboxError(PermissionError):
    """Raised when a path violates sandbox boundaries."""


class Sandbox:
    def __init__(self, profile: Profile) -> None:
        self._profile = profile
        self._root = profile.paths.sandbox_dir.resolve()

    @property
    def root(self) -> Path:
        return self._root

    def ensure(self) -> None:
        self._root.mkdir(parents=True, exist_ok=True)

    def resolve_path(self, relative_or_absolute: str) -> Path:
        """Resolve a path and guarantee it remains inside sandbox root."""
        candidate = Path(relative_or_absolute)
        if candidate.is_absolute():
            resolved = candidate.resolve()
        else:
            resolved = (self._root / candidate).resolve()

        self._assert_allowed(resolved)
        return resolved

    def _assert_allowed(self, target: Path) -> None:
        try:
            target.relative_to(self._root)
        except ValueError as err:
            raise SandboxError(f"Path escapes sandbox: {target}") from err

        protected_prefixes = (
            (Path.home() / ".ssh").resolve(),
            (Path.home() / "Library" / "Keychains").resolve(),
            (Path.home() / "Library" / "Safari").resolve(),
        )
        for prefix in protected_prefixes:
            try:
                target.relative_to(prefix)
                raise SandboxError(f"Path targets protected location: {target}")
            except ValueError:
                continue

        # Prevent accidental cross-profile access.
        agentdata_root = (Path.home() / "agentdata").resolve()
        if agentdata_root in target.parents:
            allowed_profile_root = self._profile.paths.base_data_dir.resolve()
            try:
                target.relative_to(allowed_profile_root)
            except ValueError as err:
                raise SandboxError(f"Path targets another profile: {target}") from err
