"""Approval queue engine."""

from __future__ import annotations

import json
import sqlite3
from typing import Any


class ApprovalEngine:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def enqueue(
        self,
        *,
        profile_name: str,
        tool_name: str,
        tier: str,
        payload: dict[str, Any],
    ) -> int:
        cursor = self._conn.execute(
            """
            INSERT INTO approval_queue (profile_name, tool_name, tier, payload)
            VALUES (?, ?, ?, ?)
            """,
            (profile_name, tool_name, tier, json.dumps(payload, ensure_ascii=True)),
        )
        self._conn.commit()
        return int(cursor.lastrowid)

    def list_pending(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT id, profile_name, tool_name, tier, payload, status, created_at, reviewed_at,
                   execution_status, executed_at, execution_result
            FROM approval_queue
            WHERE status = 'pending'
            ORDER BY id ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        records = []
        for row in rows:
            record = dict(row)
            record["payload"] = json.loads(record["payload"])
            if record.get("execution_result"):
                record["execution_result"] = json.loads(record["execution_result"])
            records.append(record)
        return records

    def list_recent(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT id, profile_name, tool_name, tier, payload, status, created_at, reviewed_at,
                   execution_status, executed_at, execution_result
            FROM approval_queue
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        records = []
        for row in rows:
            record = dict(row)
            record["payload"] = json.loads(record["payload"])
            if record.get("execution_result"):
                record["execution_result"] = json.loads(record["execution_result"])
            records.append(record)
        return records

    def get(self, approval_id: int) -> dict[str, Any] | None:
        row = self._conn.execute(
            """
            SELECT id, profile_name, tool_name, tier, payload, status, created_at, reviewed_at,
                   execution_status, executed_at, execution_result
            FROM approval_queue
            WHERE id = ?
            """,
            (approval_id,),
        ).fetchone()
        if row is None:
            return None
        record = dict(row)
        record["payload"] = json.loads(record["payload"])
        if record.get("execution_result"):
            record["execution_result"] = json.loads(record["execution_result"])
        return record

    def resolve(self, approval_id: int, approve: bool) -> bool:
        status = "approved" if approve else "rejected"
        cursor = self._conn.execute(
            """
            UPDATE approval_queue
            SET status = ?, reviewed_at = CURRENT_TIMESTAMP
            WHERE id = ? AND status = 'pending'
            """,
            (status, approval_id),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def mark_executed(self, approval_id: int, result: dict[str, Any]) -> bool:
        cursor = self._conn.execute(
            """
            UPDATE approval_queue
            SET execution_status = 'executed',
                executed_at = CURRENT_TIMESTAMP,
                execution_result = ?
            WHERE id = ? AND status = 'approved' AND execution_status != 'executed'
            """,
            (json.dumps(result, ensure_ascii=True), approval_id),
        )
        self._conn.commit()
        return cursor.rowcount > 0
