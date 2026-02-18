"""Project memory store for idea and project records."""

from __future__ import annotations

import sqlite3
from typing import Any


class ProjectMemoryStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create(self, title: str, body: str, status: str = "active") -> int:
        cursor = self._conn.execute(
            """
            INSERT INTO project_memory (title, body, status)
            VALUES (?, ?, ?)
            """,
            (title, body, status),
        )
        self._conn.commit()
        return int(cursor.lastrowid)

    def update(
        self,
        project_id: int,
        *,
        title: str | None = None,
        body: str | None = None,
        status: str | None = None,
    ) -> bool:
        fields: list[str] = []
        values: list[str | int] = []
        if title is not None:
            fields.append("title = ?")
            values.append(title)
        if body is not None:
            fields.append("body = ?")
            values.append(body)
        if status is not None:
            fields.append("status = ?")
            values.append(status)
        if not fields:
            return False

        values.append(project_id)
        query = f"""
            UPDATE project_memory
            SET {", ".join(fields)}, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """
        cursor = self._conn.execute(query, values)
        self._conn.commit()
        return cursor.rowcount > 0

    def delete(self, project_id: int) -> bool:
        cursor = self._conn.execute("DELETE FROM project_memory WHERE id = ?", (project_id,))
        self._conn.commit()
        return cursor.rowcount > 0

    def list_all(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT id, title, body, status, created_at, updated_at
            FROM project_memory
            ORDER BY updated_at DESC
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def latest(self, *, limit: int = 20, status: str | None = None) -> list[dict[str, Any]]:
        if status:
            rows = self._conn.execute(
                """
                SELECT id, title, body, status, created_at, updated_at
                FROM project_memory
                WHERE status = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (status, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT id, title, body, status, created_at, updated_at
                FROM project_memory
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get(self, project_id: int) -> dict[str, Any] | None:
        row = self._conn.execute(
            """
            SELECT id, title, body, status, created_at, updated_at
            FROM project_memory
            WHERE id = ?
            """,
            (project_id,),
        ).fetchone()
        return dict(row) if row else None

    def search_like(self, query: str, *, limit: int = 20) -> list[dict[str, Any]]:
        term = f"%{query.strip()}%"
        rows = self._conn.execute(
            """
            SELECT id, title, body, status, created_at, updated_at
            FROM project_memory
            WHERE title LIKE ? OR body LIKE ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (term, term, limit),
        ).fetchall()
        return [dict(row) for row in rows]
