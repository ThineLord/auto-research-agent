from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import src.cli as cli_module
import src.llm as llm_module
from src.config import (
    AppConfig,
    ConfigValidationError,
    GeminiConfig,
    LiteratureSurveyConfig,
    ModelConfig,
)
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
    @staticmethod
    def _reject_json_constant(value: str) -> None:
        raise ValueError(f"non-standard JSON constant: {value}")

    def test_generation_resource_requirement_matches_cli_mode_contract(self) -> None:
        cases = (
            ("normal", [], True),
            ("mock", ["--mock"], True),
            ("continuous", ["--continuous"], True),
            ("diagnostic", ["--diagnostic"], True),
            ("session", ["--session"], True),
            ("resume", ["--resume"], True),
            ("survey", ["--survey"], False),
            ("cloud-discover", ["--cloud-free-discover"], False),
            ("cloud-profile", ["--cloud-free-profile"], False),
            ("analyze", ["--analyze-run", "projects/selected/runs/run-1"], False),
            (
                "compare",
                [
                    "--compare-runs",
                    "projects/selected/runs/run-1",
                    "projects/selected/runs/run-2",
                ],
                False,
            ),
        )

        for case_name, argv, expected in cases:
            with self.subTest(case=case_name):
                args = cli_module.parse_args(argv)
                self.assertEqual(
                    cli_module._requires_generation_resources(args),
                    expected,
                )

    def test_conflicting_primary_modes_exit_two_before_runtime_setup(self) -> None:
        with (
            patch.object(sys, "argv", ["auto-research-agent", "--mock", "--resume"]),
            patch.object(cli_module, "configure_logging") as configure_logging,
            patch.object(
                cli_module,
                "resolve_runtime_layout",
                side_effect=AssertionError("runtime setup reached"),
            ) as resolve_runtime_layout,
            patch.object(cli_module, "load_app_config") as load_app_config,
            patch.object(cli_module, "load_project_input") as load_project_input,
            patch.object(cli_module, "seed_default_mock_project") as seed_default_mock_project,
        ):
            with self.assertRaises(SystemExit) as raised:
                cli_module.main()

        self.assertEqual(raised.exception.code, 2)
        configure_logging.assert_not_called()
        resolve_runtime_layout.assert_not_called()
        load_app_config.assert_not_called()
        load_project_input.assert_not_called()
        seed_default_mock_project.assert_not_called()

    def test_module_conflicting_primary_modes_exit_two_before_layout(self) -> None:
        script = """
import runpy
import sys

import src.cli as cli

def forbidden_layout(**kwargs):
    print("RUNTIME_LAYOUT_ACCESSED")
    raise AssertionError("runtime layout must not be accessed")

cli.resolve_runtime_layout = forbidden_layout
sys.argv = ["auto-research-agent", "--mock", "--resume"]
runpy.run_module("src.main", run_name="__main__")
"""

        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        combined = result.stdout + result.stderr

        self.assertEqual(result.returncode, 2, combined)
        self.assertIn("not allowed with argument", result.stderr)
        self.assertNotIn("RUNTIME_LAYOUT_ACCESSED", combined)
        self.assertNotIn("Traceback", combined)

    def test_gemini_override_env_must_be_populated_before_runtime_setup(self) -> None:
        transport_env = "AUTO_RESEARCH_AGENT_UI_GEMINI_API_KEY"
        for case_name, environment in (
            ("missing", {}),
            ("empty", {transport_env: ""}),
            ("whitespace", {transport_env: "   "}),
        ):
            with (
                self.subTest(case=case_name),
                patch.dict(cli_module.os.environ, environment, clear=True),
                redirect_stderr(io.StringIO()) as stderr,
            ):
                with self.assertRaises(SystemExit) as raised:
                    cli_module.parse_args(["--gemini-api-key-override-env", transport_env])

            self.assertEqual(raised.exception.code, 2)
            self.assertIn("must name a populated environment variable", stderr.getvalue())

    def test_gemini_ui_session_key_is_actual_child_client_credential(self) -> None:
        transport_env = "AUTO_RESEARCH_AGENT_UI_GEMINI_API_KEY"
        session_secret = "synthetic-ui-session-credential"
        original_create_client = cli_module.create_llm_client

        cases = (
            (
                "config-and-all-environments",
                "synthetic-config-credential",
                "TEAM_GEMINI_KEY",
                {
                    "TEAM_GEMINI_KEY": "synthetic-custom-credential",
                    "GOOGLE_API_KEY": "synthetic-google-credential",
                    "GEMINI_API_KEY": "synthetic-gemini-credential",
                },
                True,
                session_secret,
            ),
            (
                "dual-builtins",
                "",
                "GEMINI_API_KEY",
                {
                    "GOOGLE_API_KEY": "synthetic-google-credential",
                    "GEMINI_API_KEY": "synthetic-gemini-credential",
                },
                True,
                session_secret,
            ),
            ("session-only", "", "TEAM_GEMINI_KEY", {}, True, session_secret),
            (
                "stale-transport-without-activation",
                "synthetic-config-credential",
                "TEAM_GEMINI_KEY",
                {
                    "TEAM_GEMINI_KEY": "synthetic-custom-credential",
                    "GOOGLE_API_KEY": "synthetic-google-credential",
                    "GEMINI_API_KEY": "synthetic-gemini-credential",
                },
                False,
                "synthetic-config-credential",
            ),
        )

        class ProbeStop(RuntimeError):
            pass

        for (
            case_name,
            config_secret,
            configured_env,
            competing_environment,
            activate_override,
            expected_secret,
        ) in cases:
            with self.subTest(case=case_name), tempfile.TemporaryDirectory() as tmp:
                project_dir = Path(tmp) / "projects" / "selected"
                project_dir.mkdir(parents=True)
                environment = dict(competing_environment)
                environment[transport_env] = session_secret
                selected_expected_credential = False

                class FakeClient:
                    def __init__(self, **kwargs: object) -> None:
                        nonlocal selected_expected_credential
                        selected_key = (
                            kwargs.get("api_key")
                            or llm_module.os.environ.get("GOOGLE_API_KEY")
                            or llm_module.os.environ.get("GEMINI_API_KEY")
                        )
                        selected_expected_credential = selected_key == expected_secret

                fake_genai = SimpleNamespace(Client=FakeClient)

                def create_and_probe(**kwargs: object) -> object:
                    client = original_create_client(**kwargs)
                    client._create_client()  # type: ignore[attr-defined]
                    raise ProbeStop("credential selection captured")

                with patch.dict(cli_module.os.environ, environment, clear=True):
                    argv = [
                        "--diagnostic",
                        "--provider",
                        "gemini",
                        "--model",
                        "gemini-test",
                        "--project",
                        "selected",
                        "--gemini-api-key-env",
                        configured_env,
                    ]
                    if activate_override:
                        argv.extend(["--gemini-api-key-override-env", transport_env])
                    args = cli_module.parse_args(argv)
                    with (
                        patch.object(cli_module, "parse_args", return_value=args),
                        patch.object(
                            cli_module,
                            "load_app_config",
                            return_value=AppConfig(
                                model=ModelConfig(
                                    provider="gemini",
                                    name="gemini-test",
                                    gemini=GeminiConfig(
                                        api_key_env=configured_env,
                                        api_key=config_secret,
                                    ),
                                )
                            ),
                        ),
                        patch.object(cli_module, "seed_default_mock_project", return_value=False),
                        patch.object(
                            cli_module,
                            "load_project_input",
                            return_value=_project_input(project_dir),
                        ),
                        patch.object(
                            cli_module,
                            "acquire_run_lock",
                            return_value=(object(), None),
                        ),
                        patch.object(cli_module, "release_run_lock") as release_run_lock,
                        patch.object(
                            cli_module,
                            "create_llm_client",
                            side_effect=create_and_probe,
                        ),
                        patch.object(
                            llm_module,
                            "_load_google_genai",
                            return_value=(fake_genai, SimpleNamespace()),
                        ),
                    ):
                        with self.assertRaises(ProbeStop):
                            cli_module.main()

                self.assertTrue(
                    selected_expected_credential,
                    "child client selected a credential outside the expected precedence",
                )
                release_run_lock.assert_called_once()

    def test_project_preflight_os_errors_exit_two_before_runtime_setup(self) -> None:
        for error in (PermissionError("denied"), FileNotFoundError("missing")):
            with self.subTest(error=error.__class__.__name__), tempfile.TemporaryDirectory() as tmp:
                project_dir = Path(tmp) / "projects" / "selected"
                project_dir.mkdir(parents=True)
                args = cli_module.parse_args(["--mock", "--project", "selected"])

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
                        "ensure_project_runtime_paths_safe",
                        side_effect=error,
                    ),
                    patch.object(cli_module, "acquire_run_lock") as acquire_run_lock,
                    patch.object(cli_module, "build_mock_agents") as build_mock_agents,
                ):
                    with self.assertRaises(SystemExit) as raised:
                        cli_module.main()

                self.assertEqual(raised.exception.code, 2)
                acquire_run_lock.assert_not_called()
                build_mock_agents.assert_not_called()

    @unittest.skipUnless(hasattr(Path, "symlink_to"), "symlinks are unavailable")
    def test_project_preflight_preserves_lock_path_recovery_diagnostics(self) -> None:
        cases = (
            ("active_run.json", "Stale run lock could not be cleared"),
            ("active_run.guard", "Run lock guard could not be acquired"),
        )
        for filename, expected_message in cases:
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                project_dir = root / "projects" / "selected"
                project_dir.mkdir(parents=True)
                external = root / f"external-{filename}"
                external.write_text("PRIVATE_SENTINEL\n", encoding="utf-8")
                (project_dir / filename).symlink_to(external)
                args = cli_module.parse_args(["--mock", "--project", "selected"])

                with (
                    patch.object(cli_module, "Console") as console_class,
                    patch.object(cli_module, "parse_args", return_value=args),
                    patch.object(cli_module, "load_app_config", return_value=AppConfig()),
                    patch.object(
                        cli_module,
                        "load_project_input",
                        return_value=_project_input(project_dir),
                    ),
                    patch.object(cli_module, "acquire_run_lock") as acquire_run_lock,
                    patch.object(cli_module, "build_mock_agents") as build_mock_agents,
                ):
                    with self.assertRaises(SystemExit) as raised:
                        cli_module.main()

                rendered = " ".join(
                    str(call) for call in console_class.return_value.print.call_args_list
                )
                self.assertEqual(raised.exception.code, 2)
                self.assertIn(expected_message, rendered)
                self.assertIn("move aside stale lock paths", rendered)
                self.assertNotIn(str(root), rendered)
                acquire_run_lock.assert_not_called()
                build_mock_agents.assert_not_called()
                self.assertEqual(external.read_text(encoding="utf-8"), "PRIVATE_SENTINEL\n")

    @unittest.skipUnless(hasattr(Path, "symlink_to"), "symlinks are unavailable")
    def test_unsafe_runtime_artifact_exits_two_before_lock_or_provider_setup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir = root / "projects" / "selected"
            project_dir.mkdir(parents=True)
            external_log = root / "external.log"
            external_log.write_text("PRIVATE_LOG_SENTINEL\n", encoding="utf-8")
            (project_dir / "run.log").symlink_to(external_log)
            args = cli_module.parse_args(["--mock", "--project", "selected"])

            with (
                patch.object(cli_module, "parse_args", return_value=args),
                patch.object(cli_module, "load_app_config", return_value=AppConfig()),
                patch.object(
                    cli_module,
                    "load_project_input",
                    return_value=_project_input(project_dir),
                ),
                patch.object(cli_module, "acquire_run_lock") as acquire_run_lock,
                patch.object(cli_module, "build_mock_agents") as build_mock_agents,
            ):
                with self.assertRaises(SystemExit) as raised:
                    cli_module.main()

            self.assertEqual(raised.exception.code, 2)
            acquire_run_lock.assert_not_called()
            build_mock_agents.assert_not_called()
            self.assertEqual(
                external_log.read_text(encoding="utf-8"),
                "PRIVATE_LOG_SENTINEL\n",
            )

    @unittest.skipUnless(hasattr(Path, "symlink_to"), "symlinks are unavailable")
    def test_unsafe_runtime_artifact_blocks_normal_provider_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir = root / "projects" / "selected"
            project_dir.mkdir(parents=True)
            external_log = root / "external.log"
            external_log.write_text("PRIVATE_LOG_SENTINEL\n", encoding="utf-8")
            (project_dir / "run.log").symlink_to(external_log)
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
                    return_value=([], "should-not-reach"),
                ) as list_models,
                patch.object(cli_module, "create_llm_client") as create_client,
                patch.object(cli_module, "acquire_run_lock") as acquire_run_lock,
                patch.object(cli_module.ResearchAgents, "from_prompt_dir") as build_agents,
            ):
                with self.assertRaises(SystemExit) as raised:
                    cli_module.main()

            self.assertEqual(raised.exception.code, 2)
            list_models.assert_not_called()
            create_client.assert_not_called()
            acquire_run_lock.assert_not_called()
            build_agents.assert_not_called()

    @unittest.skipUnless(hasattr(Path, "symlink_to"), "symlinks are unavailable")
    def test_unsafe_nested_cloud_artifact_blocks_discovery_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir = root / "projects" / "selected"
            artifacts_dir = project_dir / "artifacts"
            artifacts_dir.mkdir(parents=True)
            external_profile = root / "external-profile.json"
            external_profile.write_text('{"private": true}\n', encoding="utf-8")
            (artifacts_dir / "cloud_free_profile.json").symlink_to(external_profile)
            args = cli_module.parse_args(["--cloud-free-profile", "--project", "selected"])

            with (
                patch.object(cli_module, "parse_args", return_value=args),
                patch.object(cli_module, "load_app_config", return_value=AppConfig()),
                patch.object(
                    cli_module,
                    "load_project_input",
                    return_value=_project_input(project_dir),
                ),
                patch.object(cli_module, "discover_free_cloud_models") as discover_models,
                patch.object(cli_module, "acquire_run_lock") as acquire_run_lock,
            ):
                with self.assertRaises(SystemExit) as raised:
                    cli_module.main()

            self.assertEqual(raised.exception.code, 2)
            discover_models.assert_not_called()
            acquire_run_lock.assert_not_called()
            self.assertEqual(
                external_profile.read_text(encoding="utf-8"),
                '{"private": true}\n',
            )

    @unittest.skipUnless(hasattr(Path, "symlink_to"), "symlinks are unavailable")
    def test_unsafe_automatic_survey_output_exits_one_and_releases_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir = root / "projects" / "selected"
            outside = root / "outside"
            project_dir.mkdir(parents=True)
            outside.mkdir()
            (project_dir / "linked").symlink_to(outside, target_is_directory=True)
            args = cli_module.parse_args(["--survey", "--project", "selected"])
            lock_handle = project_dir / "test-lock"

            with (
                patch.object(cli_module, "parse_args", return_value=args),
                patch.object(
                    cli_module,
                    "load_app_config",
                    return_value=AppConfig(
                        literature_survey=LiteratureSurveyConfig(
                            output_dir="linked/nested",
                        )
                    ),
                ),
                patch.object(
                    cli_module,
                    "load_project_input",
                    return_value=_project_input(project_dir),
                ),
                patch.object(
                    cli_module,
                    "acquire_run_lock",
                    return_value=(lock_handle, None),
                ),
                patch.object(cli_module, "release_run_lock") as release_run_lock,
            ):
                with self.assertRaises(SystemExit) as raised:
                    cli_module.main()

            self.assertEqual(raised.exception.code, 1)
            release_run_lock.assert_called_once_with(lock_handle)
            self.assertFalse((outside / "nested").exists())

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
                with self.assertRaises(SystemExit) as raised:
                    cli_module.main()

        self.assertEqual(raised.exception.code, 130)
        release_lock.assert_called_once_with(run_lock_path)

    def test_module_entrypoint_survey_interrupt_exits_130_and_releases_lock(self) -> None:
        script = """
import runpy
import sys
import tempfile
from pathlib import Path
import src.cli as cli
from src.config import AppConfig
from src.constants import RUN_LOCK_FILENAME
from src.package_resources import RuntimeLayout

temporary_root = tempfile.TemporaryDirectory()
root = Path(temporary_root.name)
project_dir = root / "projects" / "selected"
project_dir.mkdir(parents=True)
(project_dir / "task.md").write_text("# Survey interrupt test", encoding="utf-8")
cli.resolve_runtime_layout = lambda **kwargs: RuntimeLayout(root, Path.cwd(), root, True)
cli.load_app_config = lambda path: AppConfig()
cli.run_literature_survey_mode = lambda **kwargs: (_ for _ in ()).throw(KeyboardInterrupt)
sys.argv = ["auto-research-agent", "--survey", "--project", "selected"]
try:
    runpy.run_module("src.main", run_name="__main__")
except SystemExit:
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
        self.assertIn("lock_exists=False", result.stdout)
        self.assertNotIn("Traceback", result.stderr)

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
cli.resolve_runtime_layout = lambda **kwargs: RuntimeLayout(root, Path.cwd(), root, True)
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
cli.resolve_runtime_layout = lambda **kwargs: RuntimeLayout(root, Path.cwd(), root, True)
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
cli.resolve_runtime_layout = lambda **kwargs: RuntimeLayout(root, Path.cwd(), root, True)
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
cli.resolve_runtime_layout = lambda **kwargs: RuntimeLayout(root, Path.cwd(), root, True)
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

    def test_provider_free_metric_overflow_outputs_remain_strict_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_a = root / "run-a"
            run_b = root / "run-b"
            run_a.mkdir()
            run_b.mkdir()
            (run_a / "round_metrics.json").write_text(
                json.dumps(
                    [
                        {
                            "round": 1,
                            "agent_timings_seconds": {"draft": 1e308, "review": 1e308},
                            "estimated_total_tokens": float("inf"),
                            "evolution_metrics": {"score_delta_vs_previous": 1e308},
                            "judge_rubric": {"evaluation_design_quality": -1e308},
                        },
                        {
                            "round": 2,
                            "agent_timings_seconds": {"draft": 10**400},
                            "evolution_metrics": {"score_delta_vs_previous": 1e308},
                            "judge_rubric": {"evaluation_design_quality": 1e308},
                        },
                        {"round": 3, "agent_io_metrics": {"draft": []}},
                    ]
                ),
                encoding="utf-8",
            )

            cases = (
                (
                    "analysis",
                    [
                        "--analyze-run",
                        str(run_a),
                        "--analyze-output",
                        str(root / "analysis.json"),
                    ],
                    root / "analysis.json",
                ),
                (
                    "comparison",
                    [
                        "--compare-runs",
                        str(run_a),
                        str(run_b),
                        "--compare-output",
                        str(root / "comparison.json"),
                    ],
                    root / "comparison.json",
                ),
            )
            for mode, mode_args, output_path in cases:
                with self.subTest(mode=mode):
                    result = subprocess.run(
                        [sys.executable, "-m", "src.main", *mode_args],
                        cwd=ROOT,
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    payload = json.loads(
                        output_path.read_text(encoding="utf-8"),
                        parse_constant=self._reject_json_constant,
                    )

                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertNotIn("Traceback", result.stderr)
                    self.assertIsInstance(payload, dict)

    def test_analysis_and_comparison_output_errors_are_privacy_safe(self) -> None:
        for mode in ("analysis", "comparison"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                blocker = root / "private-output-parent"
                blocker.write_text("PRIVATE_OUTPUT_SENTINEL\n", encoding="utf-8")
                if mode == "analysis":
                    run_root = root / "run"
                    run_root.mkdir()
                    mode_args = [
                        "--analyze-run",
                        str(run_root),
                        "--analyze-output",
                        str(blocker / "analysis.json"),
                    ]
                    expected_message = "Run analysis output error"
                else:
                    run_a = root / "run-a"
                    run_b = root / "run-b"
                    run_a.mkdir()
                    run_b.mkdir()
                    mode_args = [
                        "--compare-runs",
                        str(run_a),
                        str(run_b),
                        "--compare-output",
                        str(blocker / "comparison.json"),
                    ]
                    expected_message = "Run comparison output error"

                result = subprocess.run(
                    [sys.executable, "-m", "src.main", *mode_args],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                combined = result.stdout + result.stderr

                self.assertEqual(result.returncode, 1, combined)
                self.assertNotIn("Traceback", result.stderr)
                self.assertNotIn(str(root), combined)
                self.assertNotIn(str(ROOT), combined)
                self.assertIn(expected_message, result.stdout)
                self.assertEqual(
                    blocker.read_text(encoding="utf-8"),
                    "PRIVATE_OUTPUT_SENTINEL\n",
                )

    def test_unresolvable_output_home_is_privacy_safe(self) -> None:
        for mode in ("analysis", "comparison"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                unknown_home = f"~ara033_missing_user_{root.name}"
                if mode == "analysis":
                    run_root = root / "run"
                    run_root.mkdir()
                    mode_args = [
                        "--analyze-run",
                        str(run_root),
                        "--analyze-output",
                        f"{unknown_home}/analysis.json",
                    ]
                    expected_message = "Run analysis output error"
                else:
                    run_a = root / "run-a"
                    run_b = root / "run-b"
                    run_a.mkdir()
                    run_b.mkdir()
                    mode_args = [
                        "--compare-runs",
                        str(run_a),
                        str(run_b),
                        "--compare-output",
                        f"{unknown_home}/comparison.json",
                    ]
                    expected_message = "Run comparison output error"

                result = subprocess.run(
                    [sys.executable, "-m", "src.main", *mode_args],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                combined = result.stdout + result.stderr

                self.assertEqual(result.returncode, 1, combined)
                self.assertNotIn("Traceback", combined)
                self.assertNotIn(str(ROOT), combined)
                self.assertNotIn(unknown_home, combined)
                self.assertIn(expected_message, result.stdout)

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
cli.resolve_runtime_layout = lambda **kwargs: RuntimeLayout(root, Path.cwd(), root, True)
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
cli.resolve_runtime_layout = lambda **kwargs: RuntimeLayout(root, Path.cwd(), root, True)
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

    def test_module_entrypoint_rejects_non_boolean_resume_flag_without_writes(self) -> None:
        script = """
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
import src.cli as cli
from src.config import AppConfig
from src.constants import RUN_LOCK_FILENAME
from src.package_resources import RuntimeLayout

temporary_root = tempfile.TemporaryDirectory()
root = Path(temporary_root.name)
project_dir = root / "projects" / "selected"
run_root = project_dir / "runs" / "resume-run"
run_root.mkdir(parents=True)
(project_dir / "task.md").write_text("# Resume flag test", encoding="utf-8")
checkpoint_path = project_dir / "checkpoint.json"
checkpoint_bytes = json.dumps(
    {
        "run_id": "resume-run",
        "run_root": str(run_root),
        "last_completed_round": 0,
        "best_score": -1,
        "can_resume": "false",
    }
).encode()
checkpoint_path.write_bytes(checkpoint_bytes)
agent_marker = project_dir / "agent_called"

class UnexpectedAgents:
    def __getattr__(self, name):
        agent_marker.write_text(name, encoding="utf-8")
        raise AssertionError(f"resume agent unexpectedly accessed: {name}")

cli.resolve_runtime_layout = lambda **kwargs: RuntimeLayout(root, Path.cwd(), root, True)
cli.load_app_config = lambda path: AppConfig()
cli.list_installed_ollama_models = lambda: (["qwen3:8b"], None)
cli.create_llm_client = lambda **kwargs: SimpleNamespace(timeout_seconds=1)
cli.ResearchAgents.from_prompt_dir = lambda **kwargs: UnexpectedAgents()
sys.argv = ["auto-research-agent", "--resume", "--project", "selected"]
try:
    cli.main()
except SystemExit:
    print(f"agent_called={agent_marker.exists()}")
    print(f"checkpoint_unchanged={checkpoint_path.read_bytes() == checkpoint_bytes}")
    print(f"run_config_exists={(run_root / 'run_config.json').exists()}")
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

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("agent_called=False", result.stdout)
        self.assertIn("checkpoint_unchanged=True", result.stdout)
        self.assertIn("run_config_exists=False", result.stdout)
        self.assertIn("lock_exists=False", result.stdout)
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

    def test_cloud_artifact_write_failures_exit_one_without_path_disclosure(self) -> None:
        for stage in (
            "discovery",
            "profile_discovery",
            "profile_result",
            "profile_fallback_result",
        ):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                project_dir = root / "projects" / "selected"
                project_dir.mkdir(parents=True)
                mode_arg = (
                    "--cloud-free-discover" if stage == "discovery" else "--cloud-free-profile"
                )
                args = cli_module.parse_args([mode_arg, "--project", "selected"])
                private_error = OSError(f"private artifact path: {root}")
                discovery_write_error = (
                    private_error if stage in {"discovery", "profile_discovery"} else None
                )
                profile_error = (
                    private_error
                    if stage in {"profile_result", "profile_fallback_result"}
                    else None
                )
                discovery_result = (
                    ([], "discovery unavailable")
                    if stage == "profile_fallback_result"
                    else ([], "")
                )
                with (
                    patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=True),
                    patch.object(cli_module, "Console") as console_class,
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
                        return_value=discovery_result,
                    ),
                    patch.object(
                        cli_module,
                        "save_discovery_artifact",
                        side_effect=discovery_write_error,
                        return_value=project_dir / "artifacts" / "cloud_free_models.json",
                    ) as save_discovery,
                    patch.object(
                        cli_module, "profile_free_cloud_models", return_value=[]
                    ) as profile_models,
                    patch.object(
                        cli_module,
                        "save_profile_artifact",
                        side_effect=profile_error,
                    ),
                    patch.object(cli_module, "recommend_free_cloud_model", return_value=None),
                ):
                    with self.assertRaises(SystemExit) as raised:
                        cli_module.main()

                rendered = " ".join(
                    str(call) for call in console_class.return_value.print.call_args_list
                )
                self.assertEqual(raised.exception.code, 1)
                self.assertIn("Cloud artifact error", rendered)
                self.assertNotIn(str(root), rendered)
                self.assertNotIn("private artifact path", rendered)
                if stage == "profile_fallback_result":
                    save_discovery.assert_not_called()
                    profile_models.assert_called_once()

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
