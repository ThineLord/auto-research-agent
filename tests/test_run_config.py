from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from src.run_config import collect_prompt_file_hashes, read_run_config


class RunConfigTests(unittest.TestCase):
    def test_collect_prompt_file_hashes_records_markdown_prompt_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            prompt_dir = Path(tmp) / "prompts"
            prompt_dir.mkdir()
            draft_text = "Draft prompt\n"
            (prompt_dir / "draft.md").write_text(draft_text, encoding="utf-8")
            (prompt_dir / "ignore.txt").write_text("not a prompt\n", encoding="utf-8")

            hashes = collect_prompt_file_hashes(prompt_dir)

        self.assertEqual(set(hashes), {"draft.md"})
        self.assertEqual(
            hashes["draft.md"]["sha256"],
            hashlib.sha256(draft_text.encode("utf-8")).hexdigest(),
        )
        self.assertEqual(hashes["draft.md"]["bytes"], len(draft_text.encode("utf-8")))

    def test_read_run_config_falls_back_to_legacy_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "runs" / "legacy-run"
            run_root.mkdir(parents=True)
            (run_root / "run_manifest.json").write_text(
                json.dumps(
                    {
                        "run_id": "legacy-run",
                        "run_root": str(run_root),
                        "mode": "normal",
                        "model": "qwen3:8b",
                        "started_at": "2026-06-24T00:00:00",
                        "project": {"project_name": "example"},
                    }
                ),
                encoding="utf-8",
            )

            config = read_run_config(run_root)

        self.assertEqual(config["schema_version"], 0)
        self.assertEqual(config["compatibility"]["source"], "run_manifest.json")
        self.assertTrue(config["compatibility"]["run_config_missing"])
        self.assertEqual(config["model"]["name"], "qwen3:8b")
        self.assertEqual(config["project"]["project_name"], "example")

    def test_read_run_config_tolerates_stale_directory_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "runs" / "stale-run-config"
            run_root.mkdir(parents=True)
            (run_root / "run_config.json").mkdir()

            self.assertEqual(read_run_config(run_root), {})

        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "runs" / "stale-manifest"
            run_root.mkdir(parents=True)
            (run_root / "run_manifest.json").mkdir()

            self.assertEqual(read_run_config(run_root), {})


if __name__ == "__main__":
    unittest.main()
