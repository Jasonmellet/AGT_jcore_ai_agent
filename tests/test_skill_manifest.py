from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.skills.manifest import SkillManifestManager


class SkillManifestTests(unittest.TestCase):
    def test_upsert_and_diff(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "manifest.yaml"
            manager = SkillManifestManager(manifest_path)
            manager.upsert(
                {
                    "skill_id": "planner",
                    "name": "Planner",
                    "version": "1.0.0",
                    "description": "Planning helper",
                    "entrypoints": ["run"],
                    "dependencies": [],
                    "permissions_requested": ["network_external"],
                    "checksum": "abc",
                    "signed_by": "jcore",
                }
            )
            diff = manager.diff(
                [
                    {
                        "skill_id": "planner",
                        "name": "Planner",
                        "version": "1.1.0",
                        "description": "Planning helper",
                        "entrypoints": ["run"],
                        "dependencies": [],
                        "permissions_requested": ["network_external"],
                        "checksum": "def",
                    },
                    {
                        "skill_id": "summarizer",
                        "name": "Summarizer",
                        "version": "1.0.0",
                        "description": "Summary helper",
                        "entrypoints": ["summarize"],
                        "dependencies": [],
                        "permissions_requested": [],
                        "checksum": "ghi",
                    },
                ]
            )
            self.assertEqual(len(diff["updated"]), 1)
            self.assertEqual(diff["updated"][0]["skill_id"], "planner")
            self.assertEqual(len(diff["added"]), 1)
            self.assertEqual(diff["added"][0]["skill_id"], "summarizer")


if __name__ == "__main__":
    unittest.main()
