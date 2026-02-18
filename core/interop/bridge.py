"""Secure cross-node messaging bridge with signed envelopes and replay protection."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any
from urllib import error, request

import yaml

MAX_CLOCK_SKEW_SECONDS = 300


class InteropBridge:
    def __init__(
        self,
        *,
        conn: sqlite3.Connection,
        profile_name: str,
        secrets_dir: Path,
        nodes_file: Path,
        health_port: int = 8600,
    ) -> None:
        self._conn = conn
        self._profile_name = profile_name
        self._secrets_dir = secrets_dir
        self._nodes_file = nodes_file
        self._health_port = health_port

    def _load_nodes(self) -> dict[str, Any]:
        if not self._nodes_file.exists():
            return {}
        raw = yaml.safe_load(self._nodes_file.read_text(encoding="utf-8")) or {}
        return raw.get("nodes", {}) if isinstance(raw, dict) else {}

    def _configured_targets(self) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for node_id, spec in self._load_nodes().items():
            if not isinstance(spec, dict):
                continue
            profile = str(spec.get("profile", node_id)).strip()
            host = str(spec.get("host", "")).strip()
            if not profile or not host or host.endswith(".TBD") or profile == self._profile_name:
                continue
            out[profile] = {"node_id": str(node_id), "host": host}
        return out

    def _shared_key(self) -> bytes:
        key_path = self._secrets_dir / "interop_shared_key.txt"
        if not key_path.exists():
            raise RuntimeError(f"Missing shared interop key: {key_path}")
        raw = key_path.read_text(encoding="utf-8").strip()
        if not raw:
            raise RuntimeError(f"Empty shared interop key: {key_path}")
        return raw.encode("utf-8")

    def _canonical_payload(self, envelope: dict[str, Any]) -> str:
        body = {
            "source": envelope["source"],
            "target": envelope["target"],
            "task_type": envelope["task_type"],
            "payload": envelope["payload"],
            "nonce": envelope["nonce"],
            "timestamp": envelope["timestamp"],
        }
        return json.dumps(body, sort_keys=True, separators=(",", ":"))

    def _sign(self, envelope: dict[str, Any]) -> str:
        msg = self._canonical_payload(envelope).encode("utf-8")
        digest = hmac.new(self._shared_key(), msg, hashlib.sha256).hexdigest()
        return digest

    def _is_replay(self, nonce: str) -> bool:
        row = self._conn.execute(
            "SELECT nonce FROM interop_nonces WHERE nonce = ?",
            (nonce,),
        ).fetchone()
        return row is not None

    def _record_nonce(self, nonce: str, source: str, target: str) -> None:
        self._conn.execute(
            """
            INSERT INTO interop_nonces (nonce, source_node, target_node)
            VALUES (?, ?, ?)
            """,
            (nonce, source, target),
        )
        self._conn.commit()

    def _record_message(
        self,
        *,
        direction: str,
        source: str,
        target: str,
        task_type: str,
        payload: dict[str, Any],
        nonce: str,
        status: str,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO interop_messages (direction, source_node, target_node, task_type, payload, nonce, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (direction, source, target, task_type, json.dumps(payload, ensure_ascii=True), nonce, status),
        )
        self._conn.commit()

    def _payload_for_log(self, payload: dict[str, Any], response_payload: dict[str, Any] | None = None) -> dict[str, Any]:
        out = dict(payload)
        if isinstance(response_payload, dict):
            reply = response_payload.get("reply")
            if isinstance(reply, dict):
                reply_copy = dict(reply)
                msg = reply_copy.get("message")
                if isinstance(msg, str) and len(msg) > 600:
                    reply_copy["message"] = msg[:597] + "..."
                out["reply"] = reply_copy
        return out

    def _last_outbox_timestamp(self, target: str, task_type: str) -> int | None:
        row = self._conn.execute(
            """
            SELECT CAST(strftime('%s', created_at) AS INTEGER) AS ts
            FROM interop_messages
            WHERE direction = 'outbox' AND target_node = ? AND task_type = ? AND status = 'sent'
            ORDER BY id DESC
            LIMIT 1
            """,
            (target, task_type),
        ).fetchone()
        if row is None:
            return None
        value = row["ts"]
        return int(value) if value is not None else None

    def build_envelope(self, target: str, task_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        envelope = {
            "source": self._profile_name,
            "target": target,
            "task_type": task_type,
            "payload": payload,
            "nonce": secrets.token_hex(16),
            "timestamp": int(time.time()),
        }
        envelope["signature"] = self._sign(envelope)
        return envelope

    def send_task(self, target_profile: str, task_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        targets = self._configured_targets()
        target = targets.get(target_profile)
        if target is None:
            raise RuntimeError(f"Target not allowlisted/configured: {target_profile}")

        envelope = self.build_envelope(target_profile, task_type, payload)
        body = json.dumps({"envelope": envelope}).encode("utf-8")
        url = f"http://{target['host']}:{self._health_port}/interop/inbox"
        req = request.Request(
            url,
            method="POST",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        try:
            with request.urlopen(req, timeout=10) as resp:  # noqa: S310
                response_payload = json.loads(resp.read().decode("utf-8"))
            payload_for_log = self._payload_for_log(payload, response_payload if isinstance(response_payload, dict) else None)
            self._record_message(
                direction="outbox",
                source=self._profile_name,
                target=target_profile,
                task_type=task_type,
                payload=payload_for_log,
                nonce=envelope["nonce"],
                status="sent",
            )
            return {"sent": True, "target": target_profile, "response": response_payload}
        except (error.URLError, json.JSONDecodeError) as exc:
            self._record_message(
                direction="outbox",
                source=self._profile_name,
                target=target_profile,
                task_type=task_type,
                payload=payload,
                nonce=envelope["nonce"],
                status=f"failed:{exc}",
            )
            raise RuntimeError(f"Failed to send interop message: {exc}") from exc

    def send_daily_skills_checkins(self, *, interval_seconds: int = 86400) -> list[dict[str, Any]]:
        """
        Send at-most-once-per-interval lightweight skills check-ins to configured targets.
        Uses existing interop_messages table for scheduling state.
        """
        now = int(time.time())
        results: list[dict[str, Any]] = []
        for target_profile in self._configured_targets().keys():
            last_sent = self._last_outbox_timestamp(target_profile, "skills_checkin")
            if last_sent is not None and (now - last_sent) < interval_seconds:
                continue
            payload = {
                "kind": "daily_skills_checkin",
                "question": "Hey, do you have any cool new skills today?",
                "requested_at": now,
            }
            try:
                result = self.send_task(target_profile, "skills_checkin", payload)
                results.append({"target": target_profile, "ok": True, "result": result})
            except RuntimeError as exc:
                results.append({"target": target_profile, "ok": False, "error": str(exc)})
        return results

    def receive_envelope(self, envelope: dict[str, Any]) -> dict[str, Any]:
        required = {"source", "target", "task_type", "payload", "nonce", "timestamp", "signature"}
        missing = sorted(required.difference(envelope.keys()))
        if missing:
            raise RuntimeError(f"Envelope missing fields: {', '.join(missing)}")
        if envelope["target"] != self._profile_name:
            raise RuntimeError(f"Envelope target mismatch: expected {self._profile_name}")

        now = int(time.time())
        ts = int(envelope["timestamp"])
        if abs(now - ts) > MAX_CLOCK_SKEW_SECONDS:
            raise RuntimeError("Envelope timestamp outside allowed skew window")

        expected_signature = self._sign(envelope)
        if not hmac.compare_digest(expected_signature, str(envelope["signature"])):
            raise RuntimeError("Envelope signature invalid")

        nonce = str(envelope["nonce"])
        if self._is_replay(nonce):
            raise RuntimeError("Replay detected: nonce already seen")
        self._record_nonce(nonce, str(envelope["source"]), str(envelope["target"]))
        self._record_message(
            direction="inbox",
            source=str(envelope["source"]),
            target=str(envelope["target"]),
            task_type=str(envelope["task_type"]),
            payload=dict(envelope["payload"]),
            nonce=nonce,
            status="received",
        )
        return {
            "accepted": True,
            "source": envelope["source"],
            "target": envelope["target"],
            "task_type": envelope["task_type"],
            "payload": dict(envelope["payload"]),
            "nonce": nonce,
        }

    def recent_messages(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT id, direction, source_node, target_node, task_type, payload, nonce, status, created_at
            FROM interop_messages
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item["payload"])
            out.append(item)
        return out
