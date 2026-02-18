from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib import error

from core.interop.bridge import InteropBridge
from core.memory.engine import MemoryEngine


class InteropBridgeRoutingTests(unittest.TestCase):
    def _new_bridge(self, tempdir: str) -> InteropBridge:
        root = Path(tempdir)
        secrets_dir = root / "secrets"
        secrets_dir.mkdir(parents=True, exist_ok=True)
        (secrets_dir / "interop_shared_key.txt").write_text("test-key\n", encoding="utf-8")
        nodes_file = root / "nodes.yaml"
        nodes_file.write_text(
            "\n".join(
                [
                    "routing:",
                    "  hub_profile: jason",
                    "nodes:",
                    "  jason:",
                    "    host: hub.local",
                    "    profile: jason",
                    "  kiera:",
                    "    host: kiera.local",
                    "    profile: kiera",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        memory = MemoryEngine(root / "memory.db")
        memory.initialize()
        conn: sqlite3.Connection = memory.connect()
        return InteropBridge(
            conn=conn,
            profile_name="scarlet",
            secrets_dir=secrets_dir,
            nodes_file=nodes_file,
            health_port=8600,
        )

    def test_send_task_auto_fallback_routes_via_hub(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            bridge = self._new_bridge(tmpdir)

            calls: list[str] = []

            def fake_post(host: str, envelope: dict[str, object]) -> dict[str, object]:
                calls.append(host)
                if host == "kiera.local":
                    raise error.URLError("no route")
                self.assertEqual(host, "hub.local")
                self.assertEqual(envelope.get("task_type"), "route_envelope")
                return {"ok": True}

            with patch.object(bridge, "_post_envelope", side_effect=fake_post):
                result = bridge.send_task("kiera", "skills_checkin", {"question": "hi"}, route_via="auto")
            self.assertTrue(result["sent"])
            self.assertEqual(result.get("routed_via"), "jason")
            self.assertEqual(calls, ["kiera.local", "hub.local"])

    def test_forward_relay_envelope_rejects_source_spoof(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            bridge = self._new_bridge(tmpdir)
            inner = bridge.build_envelope("kiera", "skills_checkin", {"question": "hello"}, source_override="jason")
            with self.assertRaises(RuntimeError):
                bridge.forward_relay_envelope(relayer_source="scarlet", inner_envelope=inner)


if __name__ == "__main__":
    unittest.main()
