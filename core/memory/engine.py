"""SQLite memory engine and schema management."""

from __future__ import annotations

import sqlite3
from pathlib import Path


class MemoryEngine:
    """Owns the SQLite connection and table lifecycle."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None

    @property
    def db_path(self) -> Path:
        return self._db_path

    def connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def initialize(self) -> None:
        conn = self.connect()
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS profile_memory (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS project_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS episodic_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                tool_name TEXT,
                decision TEXT,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS approval_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_name TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                tier TEXT NOT NULL,
                payload TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                reviewed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS interop_nonces (
                nonce TEXT PRIMARY KEY,
                source_node TEXT NOT NULL,
                target_node TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS interop_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                direction TEXT NOT NULL,
                source_node TEXT NOT NULL,
                target_node TEXT NOT NULL,
                task_type TEXT NOT NULL,
                payload TEXT NOT NULL,
                nonce TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        # Lightweight migrations for approval execution lifecycle.
        for stmt in (
            "ALTER TABLE approval_queue ADD COLUMN execution_status TEXT NOT NULL DEFAULT 'not_executed'",
            "ALTER TABLE approval_queue ADD COLUMN executed_at TEXT",
            "ALTER TABLE approval_queue ADD COLUMN execution_result TEXT",
        ):
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError:
                # Column already exists.
                pass
        conn.commit()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
