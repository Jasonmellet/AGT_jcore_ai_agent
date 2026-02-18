"""Persistent transcript store for Telegram inbound/outbound messages."""

from __future__ import annotations

import json
import sqlite3
from typing import Any


class TranscriptMemoryStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def record(
        self,
        *,
        chat_id: int,
        direction: str,
        text: str,
        message_type: str = "text",
        source: str = "telegram",
        metadata: dict[str, Any] | None = None,
    ) -> int:
        payload = metadata or {}
        cursor = self._conn.execute(
            """
            INSERT INTO telegram_messages (chat_id, direction, message_type, source, text, metadata)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                chat_id,
                direction,
                message_type,
                source,
                text,
                json.dumps(payload, ensure_ascii=True),
            ),
        )
        self._conn.commit()
        return int(cursor.lastrowid)

    def latest(self, *, limit: int = 100, chat_id: int | None = None) -> list[dict[str, Any]]:
        if chat_id is None:
            rows = self._conn.execute(
                """
                SELECT id, chat_id, direction, message_type, source, text, metadata, created_at
                FROM telegram_messages
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT id, chat_id, direction, message_type, source, text, metadata, created_at
                FROM telegram_messages
                WHERE chat_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (chat_id, limit),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["metadata"] = json.loads(item["metadata"])
            out.append(item)
        return out
