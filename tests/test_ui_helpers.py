from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import yaml

import ui.app as ui_app


class UiHelperTests(unittest.TestCase):
    def test_text_json_and_tail_helpers_handle_missing_and_invalid_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            text_path = root / "nested" / "note.txt"
            json_path = root / "state.json"
            invalid_json_path = root / "invalid.json"
            log_path = root / "run.log"

            self.assertEqual(ui_app.read_text(text_path), "")
            ui_app.write_text(text_path, "hello\n")
            self.assertEqual(ui_app.read_text(text_path), "hello\n")

            self.assertEqual(ui_app.read_json(json_path), {})
            ui_app.write_json(json_path, {"round": 3})
            self.assertEqual(ui_app.read_json(json_path), {"round": 3})

            invalid_json_path.write_text("{not json", encoding="utf-8")
            self.assertEqual(ui_app.read_json(invalid_json_path), {})

            log_path.write_text("one\ntwo\nthree\n", encoding="utf-8")
            self.assertEqual(ui_app.tail_lines(log_path, max_lines=2), "two\nthree")
            self.assertEqual(ui_app.tail_lines(root / "missing.log"), "")

    def test_get_active_meta_returns_live_process_and_removes_stale_meta(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            meta_path = Path(tmp) / "ui_run_process.json"
            ui_app.write_json(meta_path, {"pid": 123, "command": "run"})

            with patch.object(ui_app, "is_pid_running", return_value=True):
                self.assertEqual(ui_app.get_active_meta(meta_path)["pid"], 123)

            ui_app.write_json(meta_path, {"pid": 123, "command": "run"})
            with patch.object(ui_app, "is_pid_running", return_value=False):
                self.assertEqual(ui_app.get_active_meta(meta_path), {})

            self.assertFalse(meta_path.exists())

    def test_query_ollama_models_parses_success_and_reports_missing_binary(self) -> None:
        result = SimpleNamespace(
            returncode=0,
            stdout=(
                "NAME           ID              SIZE      MODIFIED\n"
                "qwen3:8b       abc123          4.7 GB    2 days ago\n"
                "llama3.1:8b    def456          4.9 GB    yesterday\n"
            ),
            stderr="",
        )

        with patch.object(ui_app.subprocess, "run", return_value=result):
            models, error = ui_app.query_ollama_models()

        self.assertIsNone(error)
        self.assertEqual([model["name"] for model in models], ["qwen3:8b", "llama3.1:8b"])
        self.assertEqual(models[0]["id"], "abc123")
        self.assertEqual(models[1]["modified"], "yesterday")

        with patch.object(ui_app.subprocess, "run", side_effect=FileNotFoundError):
            models, error = ui_app.query_ollama_models()

        self.assertEqual(models, [])
        self.assertIn("Ollama is not installed", error or "")

    def test_default_model_helpers_read_and_update_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.yaml"

            with patch.object(ui_app, "CONFIG_PATH", config_path):
                self.assertEqual(ui_app.load_default_model_name(), "qwen3:8b")
                self.assertIn("config file not found", ui_app.save_default_model_name("qwen3:8b"))

                config_path.write_text("model:\n  name: llama3.1:8b\n", encoding="utf-8")
                self.assertEqual(ui_app.load_default_model_name(), "llama3.1:8b")

                self.assertIsNone(ui_app.save_default_model_name("qwen3:14b"))
                saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
                self.assertEqual(saved["model"]["name"], "qwen3:14b")
                self.assertEqual(saved["model"]["provider"], "ollama")
                self.assertEqual(saved["model"]["timeout_seconds"], 300)

    def test_run_project_tests_reports_success_failure_and_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            success = SimpleNamespace(returncode=0, stdout="1 passed\n", stderr="")
            failure = SimpleNamespace(returncode=1, stdout="", stderr="failed\n")

            with (
                patch.object(ui_app, "ROOT", root),
                patch.object(ui_app.subprocess, "run", return_value=success) as run,
            ):
                result = ui_app.run_project_tests()

            self.assertTrue(result["ok"])
            self.assertEqual(result["returncode"], 0)
            self.assertEqual(result["output"], "1 passed")
            self.assertEqual(run.call_args.kwargs["cwd"], root)

            with patch.object(ui_app.subprocess, "run", return_value=failure):
                result = ui_app.run_project_tests()

            self.assertFalse(result["ok"])
            self.assertEqual(result["returncode"], 1)
            self.assertEqual(result["output"], "failed")

            timeout = subprocess.TimeoutExpired(
                cmd=["pytest"],
                timeout=120,
                output="partial out",
                stderr="partial err",
            )
            with patch.object(ui_app.subprocess, "run", side_effect=timeout):
                result = ui_app.run_project_tests()

            self.assertFalse(result["ok"])
            self.assertIsNone(result["returncode"])
            self.assertIn("partial out", result["output"])
            self.assertIn("partial err", result["output"])


if __name__ == "__main__":
    unittest.main()
