"""SQLite-backed embedding store and cosine similarity search."""

from __future__ import annotations

import json
import math
import sqlite3
from typing import Any


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(y * y for y in b))
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return dot / (mag_a * mag_b)


class VectorMemoryStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def replace_chunks(
        self,
        *,
        source_kind: str,
        source_id: int,
        source_ref: str | None,
        chunks: list[tuple[int, str, list[float]]],
        embedding_model: str,
    ) -> None:
        self._conn.execute(
            "DELETE FROM message_embeddings WHERE source_kind = ? AND source_id = ?",
            (source_kind, source_id),
        )
        for chunk_index, text_chunk, embedding in chunks:
            self._conn.execute(
                """
                INSERT INTO message_embeddings
                (source_kind, source_id, source_ref, chunk_index, text_chunk, embedding_json, embedding_model)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_kind,
                    source_id,
                    source_ref,
                    chunk_index,
                    text_chunk,
                    json.dumps(embedding, ensure_ascii=True),
                    embedding_model,
                ),
            )
        self._conn.commit()

    def search(
        self,
        *,
        query_embedding: list[float],
        source_kinds: list[str] | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        rows: list[sqlite3.Row]
        if source_kinds:
            placeholders = ", ".join(["?"] * len(source_kinds))
            rows = self._conn.execute(
                f"""
                SELECT id, source_kind, source_id, source_ref, chunk_index, text_chunk, embedding_json, embedding_model, created_at
                FROM message_embeddings
                WHERE source_kind IN ({placeholders})
                ORDER BY id DESC
                LIMIT 2000
                """,
                tuple(source_kinds),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT id, source_kind, source_id, source_ref, chunk_index, text_chunk, embedding_json, embedding_model, created_at
                FROM message_embeddings
                ORDER BY id DESC
                LIMIT 2000
                """
            ).fetchall()

        scored: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            try:
                emb = [float(v) for v in json.loads(item["embedding_json"])]
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            score = _cosine_similarity(query_embedding, emb)
            item.pop("embedding_json", None)
            item["score"] = score
            scored.append(item)

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[: max(1, limit)]
