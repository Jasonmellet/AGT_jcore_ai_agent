"""Skill packaging utilities."""

from __future__ import annotations

import tarfile
from pathlib import Path

from core.skills.manifest import sha256_file


def build_skill_bundle(*, skill_root: Path, output_bundle: Path) -> str:
    if not skill_root.exists() or not skill_root.is_dir():
        raise RuntimeError(f"Skill root missing: {skill_root}")
    output_bundle.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output_bundle, "w:gz") as tar:
        tar.add(skill_root, arcname=skill_root.name)
    return sha256_file(output_bundle)


def extract_skill_bundle(*, bundle_path: Path, target_dir: Path) -> Path:
    if not bundle_path.exists():
        raise RuntimeError(f"Bundle missing: {bundle_path}")
    target_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(bundle_path, "r:gz") as tar:
        tar.extractall(path=target_dir)
        roots = [member for member in tar.getmembers() if member.name and "/" not in member.name.strip("/")]
    if not roots:
        raise RuntimeError("Bundle did not contain a top-level skill directory")
    top = roots[0].name.split("/")[0]
    return target_dir / top
