"""Backup status helpers for code/data cron jobs."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _read_last_line(path: Path) -> str | None:
    if not path.exists():
        return None
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if not lines:
        return None
    return lines[-1]


def _entry_status(last_line: str | None) -> str:
    if last_line is None:
        return "missing"
    upper = last_line.upper()
    if "ERROR" in upper or "FAILED" in upper:
        return "error"
    return "ok"


class BackupStatusProvider:
    def __init__(self, profile_data_dir: Path) -> None:
        self._logs_dir = profile_data_dir / "logs"

    def summary(self) -> dict[str, Any]:
        code_log = self._logs_dir / "backup_code.log"
        data_log = self._logs_dir / "backup_data.log"

        code_last = _read_last_line(code_log)
        data_last = _read_last_line(data_log)

        return {
            "code_backup": {
                "log_path": str(code_log),
                "status": _entry_status(code_last),
                "last_line": code_last,
            },
            "data_backup": {
                "log_path": str(data_log),
                "status": _entry_status(data_last),
                "last_line": data_last,
            },
        }
