from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import yaml

import src.config as config_module
import src.runtime as runtime_module
from src.config import (
    list_installed_ollama_models,
    load_default_model_name,
    query_ollama_models,
    save_default_model_name,
)
from src.runtime import (
    get_active_process_meta,
    run_project_tests,
    start_background_process,
)
from src.storage import (
    read_file_text,
    read_json_file,
    tail_file_lines,
    write_file_text,
    write_json_file,
)


class SharedUiBackendHelperTests(unittest.TestCase):
    def test_text_json_and_tail_helpers_handle_missing_and_invalid_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            text_path = root / "nested" / "note.txt"
            json_path = root / "state.json"
            invalid_json_path = root / "invalid.json"
            log_path = root / "run.log"

            self.assertEqual(read_file_text(text_path), "")
            write_file_text(text_path, "hello\n")
            self.assertEqual(read_file_text(text_path), "hello\n")

            self.assertEqual(read_json_file(json_path), {})
            write_json_file(json_path, {"round": 3})
            self.assertEqual(read_json_file(json_path), {"round": 3})

            invalid_json_path.write_text("{not json", encoding="utf-8")
            self.assertEqual(read_json_file(invalid_json_path), {})

            log_path.write_text("one\ntwo\nthree\n", encoding="utf-8")
            self.assertEqual(tail_file_lines(log_path, max_lines=2), "two\nthree")
            self.assertEqual(tail_file_lines(root / "missing.log"), "")

    def test_get_active_process_meta_returns_live_process_and_removes_stale_meta(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            meta_path = Path(tmp) / "ui_run_process.json"
            write_json_file(meta_path, {"pid": 123, "command": "run"})

            with patch.object(runtime_module, "is_pid_running", return_value=True):
                self.assertEqual(get_active_process_meta(meta_path)["pid"], 123)

            write_json_file(meta_path, {"pid": 123, "command": "run"})
            with patch.object(runtime_module, "is_pid_running", return_value=False):
                self.assertEqual(get_active_process_meta(meta_path), {})

            self.assertFalse(meta_path.exists())

    def test_start_background_process_writes_meta_and_reports_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log_path = root / "run.log"
            meta_path = root / "ui_run_process.json"

            with patch.object(
                runtime_module.subprocess,
                "Popen",
                return_value=SimpleNamespace(pid=456),
            ):
                result = start_background_process(
                    command=["python", "-m", "src.main"],
                    cwd=root,
                    log_path=log_path,
                    meta_path=meta_path,
                    kind="run",
                    extra={"model": "qwen3:8b"},
                )

            self.assertEqual(result.pid, 456)
            self.assertIsNone(result.error)
            self.assertEqual(read_json_file(meta_path)["pid"], 456)
            self.assertEqual(read_json_file(meta_path)["model"], "qwen3:8b")

            with patch.object(
                runtime_module.subprocess,
                "Popen",
                side_effect=OSError("boom"),
            ):
                result = start_background_process(
                    command=["bad"],
                    cwd=root,
                    log_path=log_path,
                    meta_path=meta_path,
                    kind="run",
                )

            self.assertIsNone(result.pid)
            self.assertIn("Failed to start run process", result.error or "")

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

        with patch.object(config_module.subprocess, "run", return_value=result):
            models, error = query_ollama_models()

        self.assertIsNone(error)
        self.assertEqual([model["name"] for model in models], ["qwen3:8b", "llama3.1:8b"])
        self.assertEqual(models[0]["id"], "abc123")
        self.assertEqual(models[1]["modified"], "yesterday")

        with patch.object(config_module.subprocess, "run", return_value=result):
            names, error = list_installed_ollama_models()

        self.assertIsNone(error)
        self.assertEqual(names, ["qwen3:8b", "llama3.1:8b"])

        with patch.object(config_module.subprocess, "run", side_effect=FileNotFoundError):
            models, error = query_ollama_models()

        self.assertEqual(models, [])
        self.assertIn("Ollama is not installed", error or "")

    def test_default_model_helpers_read_and_update_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.yaml"

            self.assertEqual(load_default_model_name(config_path), "qwen3:8b")
            self.assertIn(
                "config file not found",
                save_default_model_name(config_path, "qwen3:8b") or "",
            )

            config_path.write_text("model:\n  name: llama3.1:8b\n", encoding="utf-8")
            self.assertEqual(load_default_model_name(config_path), "llama3.1:8b")

            self.assertIsNone(save_default_model_name(config_path, "qwen3:14b"))
            saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["model"]["name"], "qwen3:14b")
            self.assertEqual(saved["model"]["provider"], "ollama")
            self.assertEqual(saved["model"]["timeout_seconds"], 300)

    def test_run_project_tests_reports_success_failure_and_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            success = SimpleNamespace(returncode=0, stdout="1 passed\n", stderr="")
            failure = SimpleNamespace(returncode=1, stdout="", stderr="failed\n")

            with patch.object(runtime_module.subprocess, "run", return_value=success) as run:
                result = run_project_tests(root)

            self.assertTrue(result["ok"])
            self.assertEqual(result["returncode"], 0)
            self.assertEqual(result["output"], "1 passed")
            self.assertEqual(run.call_args.kwargs["cwd"], root)

            with patch.object(runtime_module.subprocess, "run", return_value=failure):
                result = run_project_tests(root)

            self.assertFalse(result["ok"])
            self.assertEqual(result["returncode"], 1)
            self.assertEqual(result["output"], "failed")

            timeout = subprocess.TimeoutExpired(
                cmd=["pytest"],
                timeout=120,
                output="partial out",
                stderr="partial err",
            )
            with patch.object(runtime_module.subprocess, "run", side_effect=timeout):
                result = run_project_tests(root)

            self.assertFalse(result["ok"])
            self.assertIsNone(result["returncode"])
            self.assertIn("partial out", result["output"])
            self.assertIn("partial err", result["output"])

    def test_streamlit_app_imports_shared_helpers(self) -> None:
        import ui.app as ui_app

        self.assertIs(ui_app.read_file_text, read_file_text)
        self.assertIs(ui_app.read_json_file, read_json_file)
        self.assertIs(ui_app.run_project_tests, run_project_tests)


if __name__ == "__main__":
    unittest.main()
