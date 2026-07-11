from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import src.cli as cli_module
from src.config import AppConfig, ConfigValidationError
from src.project_input import ProjectInputError

ROOT = Path(__file__).resolve().parent.parent


def _project_input(project_dir: Path) -> SimpleNamespace:
    return SimpleNamespace(
        project_name=project_dir.name,
        project_dir=project_dir,
        task_path=project_dir / "task.md",
        task_text="# CLI exit status test",
        project_title="CLI exit status test",
        source_kind="user_provided",
        as_metadata=lambda: {"project_name": project_dir.name},
    )


class _InterruptOnTruth:
    def __bool__(self) -> bool:
        raise KeyboardInterrupt


class CliExitCodeTests(unittest.TestCase):
    def test_direct_mock_interrupt_exits_130_and_releases_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "projects" / "selected"
            project_dir.mkdir(parents=True)
            run_lock_path = project_dir / cli_module.RUN_LOCK_FILENAME
            args = cli_module.parse_args(["--mock", "--project", "selected"])

            def acquire_then_interrupt(*args: object, **kwargs: object) -> tuple[object, object]:
                handle, error = original_acquire(*args, **kwargs)
                self.assertIsNone(error)
                return handle, _InterruptOnTruth()

            original_acquire = cli_module.acquire_run_lock
            with (
                patch.object(cli_module, "parse_args", return_value=args),
                patch.object(cli_module, "load_app_config", return_value=AppConfig()),
                patch.object(
                    cli_module,
                    "load_project_input",
                    return_value=_project_input(project_dir),
                ),
                patch.object(
                    cli_module,
                    "acquire_run_lock",
                    side_effect=acquire_then_interrupt,
                ),
            ):
                with self.assertRaises(SystemExit) as raised:
                    cli_module.main()

            self.assertEqual(raised.exception.code, 130)
            self.assertFalse(run_lock_path.exists())

    def test_direct_provider_interrupt_exits_130_and_releases_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "projects" / "selected"
            project_dir.mkdir(parents=True)
            run_lock_path = project_dir / ".run.lock"
            args = cli_module.parse_args(["--project", "selected"])
            with (
                patch.object(cli_module, "parse_args", return_value=args),
                patch.object(cli_module, "load_app_config", return_value=AppConfig()),
                patch.object(
                    cli_module,
                    "load_project_input",
                    return_value=_project_input(project_dir),
                ),
                patch.object(
                    cli_module,
                    "list_installed_ollama_models",
                    return_value=(["qwen3:8b"], None),
                ),
                patch.object(
                    cli_module,
                    "acquire_run_lock",
                    return_value=(run_lock_path, _InterruptOnTruth()),
                ),
                patch.object(cli_module, "release_run_lock") as release_lock,
            ):
                with self.assertRaises(SystemExit) as raised:
                    cli_module.main()

        self.assertEqual(raised.exception.code, 130)
        release_lock.assert_called_once_with(run_lock_path)

    def test_survey_interrupt_during_lock_result_releases_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "projects" / "selected"
            project_dir.mkdir(parents=True)
            run_lock_path = project_dir / ".run.lock"
            args = cli_module.parse_args(["--survey", "--project", "selected"])
            with (
                patch.object(cli_module, "parse_args", return_value=args),
                patch.object(cli_module, "load_app_config", return_value=AppConfig()),
                patch.object(
                    cli_module,
                    "load_project_input",
                    return_value=_project_input(project_dir),
                ),
                patch.object(
                    cli_module,
                    "acquire_run_lock",
                    return_value=(run_lock_path, _InterruptOnTruth()),
                ),
                patch.object(cli_module, "release_run_lock") as release_lock,
            ):
                with self.assertRaises(KeyboardInterrupt):
                    cli_module.main()

        release_lock.assert_called_once_with(run_lock_path)

    def test_module_entrypoint_direct_interrupt_exits_130_after_releasing_lock(self) -> None:
        script = """
import runpy
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import src.cli as cli
from src.config import AppConfig
from src.constants import RUN_LOCK_FILENAME
from src.package_resources import RuntimeLayout

temporary_root = tempfile.TemporaryDirectory()
root = Path(temporary_root.name)
project_dir = root / "projects" / "selected"
project_dir.mkdir(parents=True)
(project_dir / "task.md").write_text("# interrupt subprocess test\\n", encoding="utf-8")
cli.resolve_runtime_layout = lambda **kwargs: RuntimeLayout(root, root, root, True)
cli.load_app_config = lambda path: AppConfig()
sys.argv = ["auto-research-agent", "--mock", "--project", "selected"]
interrupting_agents = cli.build_mock_agents(topic_context="")
interrupting_agents.draft = lambda **kwargs: (_ for _ in ()).throw(KeyboardInterrupt)
with patch.object(cli, "build_mock_agents", return_value=interrupting_agents):
    try:
        runpy.run_module("src.main", run_name="__main__")
    except SystemExit:
        checkpoint = json.loads((project_dir / "checkpoint.json").read_text(encoding="utf-8"))
        run_root = Path(checkpoint["run_root"])
        run_summary = json.loads((run_root / "run_summary.json").read_text(encoding="utf-8"))
        run_config = json.loads((run_root / "run_config.json").read_text(encoding="utf-8"))
        print(f"artifact_reasons={checkpoint['stop_reason']},{run_summary['stop_reason']},{run_config['stop_reason']}")
        print(f"can_resume={checkpoint['can_resume']},{run_summary['can_resume']},{run_config['can_resume']}")
        print(f"interrupted_report_exists={(project_dir / 'interrupted_report.md').is_file()}")
        print(f"lock_exists={(project_dir / RUN_LOCK_FILENAME).exists()}")
        raise
"""

        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 130, result.stdout + result.stderr)
        self.assertIn("Stop reason: MANUAL_INTERRUPT", result.stdout)
        self.assertIn(
            "artifact_reasons=MANUAL_INTERRUPT,MANUAL_INTERRUPT,MANUAL_INTERRUPT",
            result.stdout,
        )
        self.assertIn("can_resume=True,True,True", result.stdout)
        self.assertIn("interrupted_report_exists=True", result.stdout)
        self.assertIn("lock_exists=False", result.stdout)
        self.assertNotIn("Traceback", result.stderr)

    def test_user_requested_mock_stop_remains_successful_in_subprocess(self) -> None:
        script = """
import json
import sys
import tempfile
from pathlib import Path

import src.cli as cli
from src.config import AppConfig
from src.package_resources import RuntimeLayout

temporary_root = tempfile.TemporaryDirectory()
root = Path(temporary_root.name)
project_dir = root / "projects" / "selected"
project_dir.mkdir(parents=True)
(project_dir / "task.md").write_text("# safe stop subprocess test\\n", encoding="utf-8")
(project_dir / "STOP_REQUESTED").write_text("STOP_REQUESTED\\n", encoding="utf-8")
cli.resolve_runtime_layout = lambda **kwargs: RuntimeLayout(root, root, root, True)
cli.load_app_config = lambda path: AppConfig()
sys.argv = ["auto-research-agent", "--mock", "--project", "selected"]
cli.main()
checkpoint = json.loads((project_dir / "checkpoint.json").read_text(encoding="utf-8"))
print(f"stop_reason={checkpoint['stop_reason']}")
print(f"can_resume={checkpoint['can_resume']}")
print(f"stop_signal_exists={(project_dir / 'STOP_REQUESTED').exists()}")
"""

        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("stop_reason=USER_STOP_REQUESTED", result.stdout)
        self.assertIn("can_resume=True", result.stdout)
        self.assertIn("stop_signal_exists=False", result.stdout)

    def test_module_entrypoint_missing_config_exits_two(self) -> None:
        script = """
import sys
import tempfile
from pathlib import Path
import src.cli as cli
from src.package_resources import RuntimeLayout

temporary_root = tempfile.TemporaryDirectory()
root = Path(temporary_root.name)
cli.resolve_runtime_layout = lambda **kwargs: RuntimeLayout(root, root, root, True)
sys.argv = ["auto-research-agent"]
cli.main()
"""

        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("Config error", result.stdout)

    def test_module_entrypoint_invalid_utf8_config_exits_two_without_traceback(self) -> None:
        script = """
import sys
import tempfile
from pathlib import Path
import src.cli as cli
from src.package_resources import RuntimeLayout

temporary_root = tempfile.TemporaryDirectory()
root = Path(temporary_root.name)
(root / "config.yaml").write_bytes(b"\\xff\\xfe")
cli.resolve_runtime_layout = lambda **kwargs: RuntimeLayout(root, root, root, True)
sys.argv = ["auto-research-agent"]
cli.main()
"""

        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("config file must be valid UTF-8", result.stdout)
        self.assertNotIn("Traceback", result.stderr)

    def test_help_and_provider_free_analysis_remain_successful(self) -> None:
        help_result = subprocess.run(
            [sys.executable, "-m", "src.main", "--help"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(help_result.returncode, 0, help_result.stdout + help_result.stderr)

        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "run"
            run_root.mkdir()
            analysis_result = subprocess.run(
                [sys.executable, "-m", "src.main", "--analyze-run", str(run_root)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(
            analysis_result.returncode,
            0,
            analysis_result.stdout + analysis_result.stderr,
        )

    def test_module_entrypoint_invalid_project_exits_two(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "src.main", "--mock", "--project", "../outside"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("Project name must be a simple folder name", result.stdout)

    def test_module_entrypoint_invalid_utf8_task_exits_two_without_traceback(self) -> None:
        script = """
import sys
import tempfile
from pathlib import Path
import src.cli as cli
from src.config import AppConfig
from src.package_resources import RuntimeLayout

temporary_root = tempfile.TemporaryDirectory()
root = Path(temporary_root.name)
project_dir = root / "projects" / "bad-input"
project_dir.mkdir(parents=True)
(project_dir / "task.md").write_bytes(b"\\xff\\xfe")
cli.resolve_runtime_layout = lambda **kwargs: RuntimeLayout(root, root, root, True)
cli.load_app_config = lambda path: AppConfig()
sys.argv = ["auto-research-agent", "--mock", "--project", "bad-input"]
cli.main()
"""

        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("Task file must be valid UTF-8 text", result.stdout)
        self.assertNotIn("Traceback", result.stderr)

    def test_module_entrypoint_invalid_utf8_checkpoint_exits_two_without_traceback(self) -> None:
        script = """
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
import src.cli as cli
from src.config import AppConfig
from src.package_resources import RuntimeLayout

temporary_root = tempfile.TemporaryDirectory()
root = Path(temporary_root.name)
project_dir = root / "projects" / "selected"
project_dir.mkdir(parents=True)
(project_dir / "task.md").write_text("# Resume test", encoding="utf-8")
(project_dir / "checkpoint.json").write_bytes(b"\\xff\\xfe")
cli.resolve_runtime_layout = lambda **kwargs: RuntimeLayout(root, root, root, True)
cli.load_app_config = lambda path: AppConfig()
cli.list_installed_ollama_models = lambda: (["qwen3:8b"], None)
cli.create_llm_client = lambda **kwargs: SimpleNamespace(timeout_seconds=1)
cli.ResearchAgents.from_prompt_dir = lambda **kwargs: SimpleNamespace()
sys.argv = ["auto-research-agent", "--resume", "--project", "selected"]
cli.main()
"""

        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_config_and_project_startup_errors_exit_two(self) -> None:
        cases = (
            (
                "missing config",
                cli_module.parse_args([]),
                FileNotFoundError("config.yaml is missing"),
                None,
            ),
            (
                "invalid config",
                cli_module.parse_args([]),
                ConfigValidationError("config.model.timeout_seconds is invalid"),
                None,
            ),
            (
                "invalid project override",
                cli_module.parse_args(["--project", "../outside"]),
                AppConfig(),
                None,
            ),
            (
                "missing project input",
                cli_module.parse_args(["--project", "missing"]),
                AppConfig(),
                ProjectInputError("task.md is missing"),
            ),
        )
        for name, args, config_result, project_error in cases:
            with self.subTest(name=name):
                config_side_effect = config_result if isinstance(config_result, Exception) else None
                with (
                    patch.object(cli_module, "parse_args", return_value=args),
                    patch.object(
                        cli_module,
                        "load_app_config",
                        side_effect=config_side_effect,
                        return_value=None if config_side_effect else config_result,
                    ),
                    patch.object(
                        cli_module,
                        "load_project_input",
                        side_effect=project_error,
                    ) as load_project,
                ):
                    with self.assertRaises(SystemExit) as raised:
                        cli_module.main()

                self.assertEqual(raised.exception.code, 2)
                if name == "invalid project override":
                    load_project.assert_not_called()

    def test_mock_fallback_config_error_exits_two(self) -> None:
        args = cli_module.parse_args(["--mock"])
        with (
            patch.object(cli_module, "parse_args", return_value=args),
            patch.object(
                cli_module,
                "load_app_config",
                side_effect=(
                    FileNotFoundError("config.yaml is missing"),
                    FileNotFoundError("config.example.yaml is missing"),
                ),
            ),
        ):
            with self.assertRaises(SystemExit) as raised:
                cli_module.main()

        self.assertEqual(raised.exception.code, 2)

    def test_provider_preflight_errors_exit_two(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "projects" / "selected"
            project_dir.mkdir(parents=True)
            project_input = _project_input(project_dir)
            cases = (
                (
                    "ollama unavailable",
                    cli_module.parse_args(["--project", "selected"]),
                    ([], "Ollama is unavailable"),
                    {},
                ),
                (
                    "ollama model missing",
                    cli_module.parse_args(["--project", "selected"]),
                    ([], None),
                    {},
                ),
                (
                    "gemini key missing",
                    cli_module.parse_args(
                        ["--provider", "gemini", "--model", "gemini-test", "--project", "selected"]
                    ),
                    ([], None),
                    {},
                ),
            )
            for name, args, ollama_result, environment in cases:
                with (
                    self.subTest(name=name),
                    patch.dict(os.environ, environment, clear=True),
                    patch.object(cli_module, "parse_args", return_value=args),
                    patch.object(cli_module, "load_app_config", return_value=AppConfig()),
                    patch.object(cli_module, "load_project_input", return_value=project_input),
                    patch.object(
                        cli_module,
                        "list_installed_ollama_models",
                        return_value=ollama_result,
                    ),
                ):
                    with self.assertRaises(SystemExit) as raised:
                        cli_module.main()
                    self.assertEqual(raised.exception.code, 2)

    def test_explicit_cloud_discovery_failure_exits_one(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "projects" / "selected"
            project_dir.mkdir(parents=True)
            args = cli_module.parse_args(["--cloud-free-discover", "--project", "selected"])
            with (
                patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=True),
                patch.object(cli_module, "parse_args", return_value=args),
                patch.object(cli_module, "load_app_config", return_value=AppConfig()),
                patch.object(
                    cli_module,
                    "load_project_input",
                    return_value=_project_input(project_dir),
                ),
                patch.object(
                    cli_module,
                    "discover_free_cloud_models",
                    return_value=([], "discovery unavailable"),
                ),
            ):
                with self.assertRaises(SystemExit) as raised:
                    cli_module.main()

        self.assertEqual(raised.exception.code, 1)

    def test_cloud_profile_discovery_failure_remains_a_successful_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "projects" / "selected"
            project_dir.mkdir(parents=True)
            args = cli_module.parse_args(["--cloud-free-profile", "--project", "selected"])
            with (
                patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=True),
                patch.object(cli_module, "parse_args", return_value=args),
                patch.object(cli_module, "load_app_config", return_value=AppConfig()),
                patch.object(
                    cli_module,
                    "load_project_input",
                    return_value=_project_input(project_dir),
                ),
                patch.object(
                    cli_module,
                    "discover_free_cloud_models",
                    return_value=([], "discovery unavailable"),
                ),
                patch.object(cli_module, "profile_free_cloud_models", return_value=[]),
                patch.object(
                    cli_module,
                    "save_profile_artifact",
                    return_value=project_dir / "cloud_free_profile.json",
                ),
                patch.object(cli_module, "recommend_free_cloud_model", return_value=None),
            ):
                result = cli_module.main()

        self.assertIsNone(result)

    def test_lock_contention_exits_two_for_each_locking_entrypoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "projects" / "selected"
            project_dir.mkdir(parents=True)
            project_input = _project_input(project_dir)
            for mode_args in (
                ["--survey", "--project", "selected"],
                ["--mock", "--project", "selected"],
                ["--project", "selected"],
            ):
                with self.subTest(args=mode_args):
                    args = cli_module.parse_args(mode_args)
                    with (
                        patch.object(cli_module, "parse_args", return_value=args),
                        patch.object(cli_module, "load_app_config", return_value=AppConfig()),
                        patch.object(
                            cli_module,
                            "load_project_input",
                            return_value=project_input,
                        ),
                        patch.object(
                            cli_module,
                            "list_installed_ollama_models",
                            return_value=(["qwen3:8b"], None),
                        ),
                        patch.object(
                            cli_module,
                            "acquire_run_lock",
                            return_value=(None, "Another run is already active"),
                        ),
                    ):
                        with self.assertRaises(SystemExit) as raised:
                            cli_module.main()

                    self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
