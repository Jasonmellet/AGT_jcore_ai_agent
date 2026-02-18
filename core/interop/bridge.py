"""Secure cross-node messaging bridge with signed envelopes and replay protection."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
import time
from base64 import b64decode, b64encode
from pathlib import Path
from typing import Any
from urllib import error, request

import yaml

from core.skills.package import build_skill_bundle

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

    def _load_config(self) -> dict[str, Any]:
        if not self._nodes_file.exists():
            return {}
        raw = yaml.safe_load(self._nodes_file.read_text(encoding="utf-8")) or {}
        return raw if isinstance(raw, dict) else {}

    def _load_nodes(self) -> dict[str, Any]:
        config = self._load_config()
        return config.get("nodes", {}) if isinstance(config, dict) else {}

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

    def _routing_hub_profile(self) -> str | None:
        config = self._load_config()
        routing = config.get("routing", {}) if isinstance(config, dict) else {}
        hub_profile = str(routing.get("hub_profile", "")).strip() if isinstance(routing, dict) else ""
        if hub_profile:
            return hub_profile
        targets = self._configured_targets()
        return "jason" if "jason" in targets or self._profile_name == "jason" else None

    def hub_profile(self) -> str | None:
        return self._routing_hub_profile()

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

    def _identity_mode(self) -> str:
        raw = (self._secrets_dir / "interop_identity_mode.txt").read_text(encoding="utf-8").strip() if (
            self._secrets_dir / "interop_identity_mode.txt"
        ).exists() else "compat"
        return raw if raw in {"compat", "provenance", "strict"} else "compat"

    def _identity_private_key_bytes(self) -> bytes | None:
        key_path = self._secrets_dir / "interop_signing_private_key.pem"
        if not key_path.exists():
            return None
        raw = key_path.read_bytes()
        return raw or None

    def _identity_public_key_for_profile(self, profile_name: str) -> str | None:
        for _, spec in self._load_nodes().items():
            if not isinstance(spec, dict):
                continue
            profile = str(spec.get("profile", "")).strip()
            if profile == profile_name:
                value = str(spec.get("signing_public_key", "")).strip()
                return value or None
        return None

    def _sign_v2(self, envelope: dict[str, Any]) -> str | None:
        private_pem = self._identity_private_key_bytes()
        if private_pem is None:
            return None
        try:
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        except ImportError:
            return None
        key = serialization.load_pem_private_key(private_pem, password=None)
        if not isinstance(key, Ed25519PrivateKey):
            return None
        sig = key.sign(self._canonical_payload(envelope).encode("utf-8"))
        return sig.hex()

    def _verify_v2(self, envelope: dict[str, Any]) -> bool:
        signature_v2 = str(envelope.get("signature_v2", "")).strip()
        signer = str(envelope.get("signer", envelope.get("source", ""))).strip()
        if not signature_v2 or not signer:
            return False
        pub_b64 = self._identity_public_key_for_profile(signer)
        if not pub_b64:
            return False
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        except ImportError:
            return False
        try:
            pub_key = Ed25519PublicKey.from_public_bytes(b64decode(pub_b64))
            pub_key.verify(bytes.fromhex(signature_v2), self._canonical_payload(envelope).encode("utf-8"))
            return True
        except Exception:
            return False

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

    def build_envelope(
        self,
        target: str,
        task_type: str,
        payload: dict[str, Any],
        *,
        source_override: str | None = None,
    ) -> dict[str, Any]:
        envelope = {
            "source": source_override or self._profile_name,
            "target": target,
            "task_type": task_type,
            "payload": payload,
            "nonce": secrets.token_hex(16),
            "timestamp": int(time.time()),
        }
        envelope["signature"] = self._sign(envelope)
        identity_sig = self._sign_v2(envelope)
        if identity_sig:
            envelope["signer"] = envelope["source"]
            envelope["signature_v2"] = identity_sig
            envelope["signature_v2_alg"] = "ed25519"
        return envelope

    def _post_envelope(self, host: str, envelope: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps({"envelope": envelope}).encode("utf-8")
        url = f"http://{host}:{self._health_port}/interop/inbox"
        req = request.Request(
            url,
            method="POST",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with request.urlopen(req, timeout=10) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8"))

    def _send_route_via_hub(
        self,
        *,
        target_profile: str,
        envelope: dict[str, Any],
        payload_for_log: dict[str, Any],
    ) -> dict[str, Any]:
        hub_profile = self._routing_hub_profile()
        if not hub_profile or hub_profile == self._profile_name:
            raise RuntimeError("Routing hub not configured for this profile")
        hub_target = self._configured_targets().get(hub_profile)
        if hub_target is None:
            raise RuntimeError(f"Hub profile is not configured as target: {hub_profile}")
        relay_payload = {"envelope": envelope}
        relay_envelope = self.build_envelope(hub_profile, "route_envelope", relay_payload)
        response_payload = self._post_envelope(hub_target["host"], relay_envelope)
        self._record_message(
            direction="outbox",
            source=self._profile_name,
            target=target_profile,
            task_type=envelope["task_type"],
            payload=payload_for_log,
            nonce=envelope["nonce"],
            status=f"sent:routed:{hub_profile}",
        )
        return {"sent": True, "target": target_profile, "routed_via": hub_profile, "response": response_payload}

    def send_task(
        self,
        target_profile: str,
        task_type: str,
        payload: dict[str, Any],
        *,
        route_via: str = "auto",
    ) -> dict[str, Any]:
        targets = self._configured_targets()
        target = targets.get(target_profile)
        if target is None:
            raise RuntimeError(f"Target not allowlisted/configured: {target_profile}")

        envelope = self.build_envelope(target_profile, task_type, payload)
        payload_for_log = self._payload_for_log(payload)
        if route_via == "hub":
            return self._send_route_via_hub(target_profile=target_profile, envelope=envelope, payload_for_log=payload_for_log)
        try:
            response_payload = self._post_envelope(target["host"], envelope)
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
            if route_via == "auto" and target_profile != (self.hub_profile() or ""):
                try:
                    return self._send_route_via_hub(
                        target_profile=target_profile,
                        envelope=envelope,
                        payload_for_log=payload_for_log,
                    )
                except RuntimeError:
                    pass
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
                "skills_manifest": self.local_skills_manifest(),
            }
            try:
                result = self.send_task(target_profile, "skills_checkin", payload)
                results.append({"target": target_profile, "ok": True, "result": result})
            except RuntimeError as exc:
                results.append({"target": target_profile, "ok": False, "error": str(exc)})
        return results

    def local_skills_manifest(self) -> list[dict[str, Any]]:
        manifest_path = Path.home() / "agent_skills" / "manifest.yaml"
        if not manifest_path.exists():
            return []
        raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        skills = raw.get("skills", []) if isinstance(raw, dict) else []
        return [dict(item) for item in skills if isinstance(item, dict)]

    def _validate_envelope(
        self,
        envelope: dict[str, Any],
        *,
        expected_target: str | None = None,
        verify_replay: bool = True,
    ) -> dict[str, Any]:
        required = {"source", "target", "task_type", "payload", "nonce", "timestamp", "signature"}
        missing = sorted(required.difference(envelope.keys()))
        if missing:
            raise RuntimeError(f"Envelope missing fields: {', '.join(missing)}")
        expected = expected_target or self._profile_name
        if envelope["target"] != expected:
            raise RuntimeError(f"Envelope target mismatch: expected {expected}")

        now = int(time.time())
        ts = int(envelope["timestamp"])
        if abs(now - ts) > MAX_CLOCK_SKEW_SECONDS:
            raise RuntimeError("Envelope timestamp outside allowed skew window")

        expected_signature = self._sign(envelope)
        if not hmac.compare_digest(expected_signature, str(envelope["signature"])):
            raise RuntimeError("Envelope signature invalid")
        identity_mode = self._identity_mode()
        v2_valid = self._verify_v2(envelope)
        has_v2 = bool(str(envelope.get("signature_v2", "")).strip())
        if identity_mode == "strict" and not v2_valid:
            raise RuntimeError("Envelope identity signature invalid or missing (strict mode)")
        if identity_mode == "provenance" and has_v2 and not v2_valid:
            raise RuntimeError("Envelope identity signature invalid (provenance mode)")

        nonce = str(envelope["nonce"])
        if verify_replay:
            if self._is_replay(nonce):
                raise RuntimeError("Replay detected: nonce already seen")
            self._record_nonce(nonce, str(envelope["source"]), str(envelope["target"]))
        return {
            "source": str(envelope["source"]),
            "target": str(envelope["target"]),
            "task_type": str(envelope["task_type"]),
            "payload": dict(envelope["payload"]),
            "nonce": nonce,
            "identity_signature_valid": v2_valid,
        }

    def receive_envelope(self, envelope: dict[str, Any]) -> dict[str, Any]:
        accepted = self._validate_envelope(envelope, expected_target=self._profile_name, verify_replay=True)
        self._record_message(
            direction="inbox",
            source=accepted["source"],
            target=accepted["target"],
            task_type=accepted["task_type"],
            payload=accepted["payload"],
            nonce=accepted["nonce"],
            status="received",
        )
        return {"accepted": True, **accepted}

    def forward_relay_envelope(self, *, relayer_source: str, inner_envelope: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(inner_envelope, dict):
            raise RuntimeError("Relay payload missing inner envelope")
        inner_source = str(inner_envelope.get("source", "")).strip()
        if inner_source != relayer_source:
            raise RuntimeError("Relay envelope source mismatch")
        target_profile = str(inner_envelope.get("target", "")).strip()
        target = self._configured_targets().get(target_profile)
        if not target:
            raise RuntimeError(f"Relay target not configured: {target_profile}")
        validated = self._validate_envelope(inner_envelope, expected_target=target_profile, verify_replay=False)
        response_payload = self._post_envelope(target["host"], inner_envelope)
        self._record_message(
            direction="relay",
            source=validated["source"],
            target=validated["target"],
            task_type=validated["task_type"],
            payload=validated["payload"],
            nonce=validated["nonce"],
            status=f"forwarded_by:{self._profile_name}",
        )
        return {"forwarded": True, "target": target_profile, "response": response_payload}

    def recent_successful_skill_installs(self, *, target_profile: str, within_seconds: int = 86400) -> int:
        row = self._conn.execute(
            """
            SELECT COUNT(*) AS c
            FROM skill_install_events
            WHERE profile_name = ?
              AND status = 'ok'
              AND created_at >= datetime('now', ?)
            """,
            (target_profile, f"-{int(within_seconds)} seconds"),
        ).fetchone()
        return int(row["c"]) if row and row["c"] is not None else 0

    def record_skill_install_event(
        self,
        *,
        profile_name: str,
        skill_id: str,
        version: str,
        status: str,
        details: dict[str, Any],
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO skill_install_events (profile_name, skill_id, version, status, details_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (profile_name, skill_id, version, status, json.dumps(details, ensure_ascii=True)),
        )
        self._conn.commit()

    def record_skill_registry(
        self,
        *,
        profile_name: str,
        skill_id: str,
        version: str,
        checksum: str,
        manifest: dict[str, Any],
        installed_from: str | None,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO skill_registry (profile_name, skill_id, version, checksum, manifest_json, installed_from)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                profile_name,
                skill_id,
                version,
                checksum,
                json.dumps(manifest, ensure_ascii=True),
                installed_from,
            ),
        )
        self._conn.commit()

    def request_skill_transfer(
        self,
        *,
        hub_profile: str,
        source_profile: str,
        target_profile: str,
        skill_id: str,
        version: str,
        permissions_requested: list[str] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "from_agent": source_profile,
            "to_agent": target_profile,
            "skill_id": skill_id,
            "version": version,
            "permissions_requested": permissions_requested or [],
            "requested_at": int(time.time()),
        }
        return self.send_task(hub_profile, "skill_request", payload, route_via="auto")

    def deliver_skill_bundle(
        self,
        *,
        target_profile: str,
        skill_root: Path,
        skill_id: str,
        version: str,
        name: str,
        description: str,
        entrypoints: list[str],
        dependencies: list[str],
        permissions_requested: list[str],
        signed_by: str | None = None,
        route_via: str = "auto",
        override_approved: bool = False,
    ) -> dict[str, Any]:
        bundle_dir = self._secrets_dir.parent / "skill_packages"
        bundle_path = bundle_dir / f"{skill_id}-{version}.tar.gz"
        checksum = build_skill_bundle(skill_root=skill_root, output_bundle=bundle_path)
        bundle_b64 = b64encode(bundle_path.read_bytes()).decode("utf-8")
        payload = {
            "skill_id": skill_id,
            "name": name,
            "version": version,
            "description": description,
            "entrypoints": entrypoints,
            "dependencies": dependencies,
            "permissions_requested": permissions_requested,
            "checksum": checksum,
            "bundle_b64": bundle_b64,
            "signed_by": signed_by or self._profile_name,
            "override_approved": override_approved,
        }
        return self.send_task(target_profile, "skill_deliver", payload, route_via=route_via)

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
