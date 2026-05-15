from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from src.constants import RUN_LOCK_FILENAME
from src.runtime import acquire_run_lock, release_run_lock
from src.storage import write_json_file


class RuntimeLockTests(unittest.TestCase):
    def test_active_lock_blocks_new_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            lock_path = project_dir / RUN_LOCK_FILENAME
            write_json_file(
                lock_path,
                {
                    "pid": os.getpid(),
                    "mode": "normal",
                    "model": "fake-model",
                    "started_at": "2026-05-15T12:00:00",
                },
            )

            acquired_path, error = acquire_run_lock(
                project_dir, mode="resume", model_name="other-model"
            )

            self.assertIsNone(acquired_path)
            self.assertIsNotNone(error)
            self.assertIn("Another run is already active", error or "")
            self.assertEqual(json.loads(lock_path.read_text(encoding="utf-8"))["pid"], os.getpid())

    def test_stale_lock_is_replaced_and_released(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            lock_path = project_dir / RUN_LOCK_FILENAME
            write_json_file(
                lock_path,
                {
                    "pid": 0,
                    "mode": "continuous",
                    "model": "stale-model",
                    "started_at": "2026-05-15T12:00:00",
                },
            )

            acquired_path, error = acquire_run_lock(
                project_dir, mode="normal", model_name="fresh-model"
            )

            self.assertEqual(acquired_path, lock_path)
            self.assertIsNone(error)
            data = json.loads(lock_path.read_text(encoding="utf-8"))
            self.assertEqual(data["pid"], os.getpid())
            self.assertEqual(data["mode"], "normal")
            self.assertEqual(data["model"], "fresh-model")

            release_run_lock(acquired_path)
            self.assertFalse(lock_path.exists())
            release_run_lock(None)


if __name__ == "__main__":
    unittest.main()
