"""Skill manifest helpers."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml

_REQUIRED_FIELDS = {
    "skill_id",
    "name",
    "version",
    "description",
    "entrypoints",
    "dependencies",
    "permissions_requested",
    "checksum",
}


class SkillManifestManager:
    def __init__(self, manifest_path: Path) -> None:
        self._manifest_path = manifest_path
        self._manifest_path.parent.mkdir(parents=True, exist_ok=True)
        if not self._manifest_path.exists():
            self._manifest_path.write_text("skills: []\n", encoding="utf-8")

    @property
    def manifest_path(self) -> Path:
        return self._manifest_path

    def load(self) -> list[dict[str, Any]]:
        raw = yaml.safe_load(self._manifest_path.read_text(encoding="utf-8")) or {}
        skills = raw.get("skills", []) if isinstance(raw, dict) else []
        out: list[dict[str, Any]] = []
        for item in skills:
            if isinstance(item, dict):
                out.append(dict(item))
        return out

    def save(self, skills: list[dict[str, Any]]) -> None:
        payload = {"skills": skills}
        self._manifest_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    def list_ids(self) -> set[str]:
        return {str(item.get("skill_id", "")).strip() for item in self.load() if str(item.get("skill_id", "")).strip()}

    def upsert(self, skill: dict[str, Any]) -> None:
        entry = self._normalize(skill)
        skills = self.load()
        idx = next((i for i, item in enumerate(skills) if item.get("skill_id") == entry["skill_id"]), None)
        if idx is None:
            skills.append(entry)
        else:
            skills[idx] = entry
        self.save(skills)

    def diff(self, remote_skills: list[dict[str, Any]]) -> dict[str, Any]:
        local = {str(item.get("skill_id")): item for item in self.load() if item.get("skill_id")}
        remote = {str(item.get("skill_id")): item for item in remote_skills if item.get("skill_id")}
        added = []
        updated = []
        removed = []
        for skill_id, remote_item in remote.items():
            if skill_id not in local:
                added.append(remote_item)
                continue
            local_item = local[skill_id]
            if (
                str(local_item.get("version", "")) != str(remote_item.get("version", ""))
                or str(local_item.get("checksum", "")) != str(remote_item.get("checksum", ""))
            ):
                updated.append(
                    {
                        "skill_id": skill_id,
                        "from_version": local_item.get("version"),
                        "to_version": remote_item.get("version"),
                    }
                )
        for skill_id, local_item in local.items():
            if skill_id not in remote:
                removed.append({"skill_id": skill_id, "version": local_item.get("version")})
        return {"added": added, "updated": updated, "removed": removed}

    def _normalize(self, skill: dict[str, Any]) -> dict[str, Any]:
        missing = sorted(_REQUIRED_FIELDS.difference(skill.keys()))
        if missing:
            raise ValueError(f"Skill manifest item missing required fields: {', '.join(missing)}")
        out = dict(skill)
        out["entrypoints"] = list(skill.get("entrypoints", []))
        out["dependencies"] = list(skill.get("dependencies", []))
        out["permissions_requested"] = list(skill.get("permissions_requested", []))
        out["signed_by"] = str(skill.get("signed_by", "")).strip() or None
        return out


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()
