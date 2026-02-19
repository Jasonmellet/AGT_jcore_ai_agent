"""Load soul.md and family protocol for agent identity and interaction guidelines."""

from __future__ import annotations

from pathlib import Path


def get_soul_content(profile_name: str, repo_root: Path | None = None) -> str:
    """Return combined soul + family protocol text for system prompts. Empty if no files."""
    if repo_root is None:
        repo_root = Path(__file__).resolve().parent.parent
    souls_dir = repo_root / "config" / "souls"
    parts: list[str] = []
    protocol_file = souls_dir / "family_protocol.md"
    if protocol_file.exists():
        parts.append(protocol_file.read_text(encoding="utf-8").strip())
    soul_file = souls_dir / f"{profile_name}.md"
    if soul_file.exists():
        parts.append(soul_file.read_text(encoding="utf-8").strip())
    if not parts:
        return ""
    return "\n\n---\n\n".join(parts)
