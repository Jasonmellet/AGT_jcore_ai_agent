"""Fleet control plane utilities for child-node status and deployment orchestration."""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib import error, request

import yaml


class ControlPlane:
    def __init__(self, repo_root: Path, default_health_port: int = 8600) -> None:
        self._repo_root = repo_root
        self._nodes_file = repo_root / "config" / "nodes.yaml"
        self._deploy_all_script = repo_root / "scripts" / "deploy_all.sh"
        self._default_health_port = default_health_port

    def _load_nodes(self) -> dict[str, Any]:
        if not self._nodes_file.exists():
            return {}
        raw = yaml.safe_load(self._nodes_file.read_text(encoding="utf-8")) or {}
        return raw.get("nodes", {}) if isinstance(raw, dict) else {}

    def list_nodes(self) -> list[dict[str, Any]]:
        nodes = self._load_nodes()
        out: list[dict[str, Any]] = []
        for node_id, spec in nodes.items():
            if not isinstance(spec, dict):
                continue
            host = str(spec.get("host", "")).strip()
            profile = str(spec.get("profile", node_id)).strip()
            user = str(spec.get("user", "")).strip()
            configured = bool(host and not host.endswith(".TBD"))
            out.append(
                {
                    "node_id": str(node_id),
                    "profile": profile,
                    "host": host,
                    "user": user or None,
                    "configured": configured,
                }
            )
        return out

    def health_report(self, timeout_seconds: int = 2) -> dict[str, Any]:
        report_nodes: list[dict[str, Any]] = []
        for node in self.list_nodes():
            checked_at = int(time.time())
            if not node["configured"]:
                report_nodes.append(
                    {
                        **node,
                        "reachable": False,
                        "status": "unconfigured",
                        "last_seen": None,
                        "error": "host not configured",
                    }
                )
                continue
            url = f"http://{node['host']}:{self._default_health_port}/health"
            try:
                with request.urlopen(url, timeout=timeout_seconds) as resp:  # noqa: S310
                    payload = json.loads(resp.read().decode("utf-8"))
                report_nodes.append(
                    {
                        **node,
                        "reachable": True,
                        "status": payload.get("status", "unknown"),
                        "last_seen": checked_at,
                        "health": payload,
                    }
                )
            except (error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
                report_nodes.append(
                    {
                        **node,
                        "reachable": False,
                        "status": "down",
                        "last_seen": None,
                        "error": str(exc),
                    }
                )
        return {"checked_at": int(time.time()), "nodes": report_nodes}

    def deploy_all(self, timeout_seconds: int = 900) -> dict[str, Any]:
        if not self._deploy_all_script.exists():
            return {"ok": False, "error": f"Missing script: {self._deploy_all_script}"}
        proc = subprocess.run(  # noqa: S603
            [str(self._deploy_all_script)],
            cwd=str(self._repo_root),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": proc.stdout[-12000:],
            "stderr": proc.stderr[-12000:],
        }
