"""Episodic memory store for action/event history."""

from __future__ import annotations

import json
import sqlite3
from typing import Any


class EpisodicMemoryStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def record(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        tool_name: str | None = None,
        decision: str | None = None,
    ) -> int:
        cursor = self._conn.execute(
            """
            INSERT INTO episodic_memory (event_type, tool_name, decision, payload)
            VALUES (?, ?, ?, ?)
            """,
            (event_type, tool_name, decision, json.dumps(payload, ensure_ascii=True)),
        )
        self._conn.commit()
        return int(cursor.lastrowid)

    def latest(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT id, event_type, tool_name, decision, payload, created_at
            FROM episodic_memory
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        events: list[dict[str, Any]] = []
        for row in rows:
            event = dict(row)
            event["payload"] = json.loads(event["payload"])
            events.append(event)
        return events
