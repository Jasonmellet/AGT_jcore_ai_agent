"""Profile memory store for explicit key/value facts."""

from __future__ import annotations

import sqlite3
from typing import Any


class ProfileMemoryStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def set_fact(self, key: str, value: str) -> None:
        self._conn.execute(
            """
            INSERT INTO profile_memory (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value=excluded.value,
                updated_at=CURRENT_TIMESTAMP
            """,
            (key, value),
        )
        self._conn.commit()

    def get_fact(self, key: str) -> str | None:
        row = self._conn.execute(
            "SELECT value FROM profile_memory WHERE key = ?",
            (key,),
        ).fetchone()
        return None if row is None else str(row["value"])

    def delete_fact(self, key: str) -> bool:
        cursor = self._conn.execute("DELETE FROM profile_memory WHERE key = ?", (key,))
        self._conn.commit()
        return cursor.rowcount > 0

    def list_facts(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT key, value, updated_at FROM profile_memory ORDER BY key ASC"
        ).fetchall()
        return [dict(row) for row in rows]
