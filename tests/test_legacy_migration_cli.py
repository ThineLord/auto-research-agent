from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import src.cli as cli_module
from src.package_resources import RuntimeLayout


class LegacyMigrationPreviewCliTests(unittest.TestCase):
    @staticmethod
    def _fixture(root: Path) -> Path:
        project_dir = root / "projects" / "selected"
        run_root = project_dir / "runs" / "run-001"
        run_root.mkdir(parents=True)
        history = [
            {
                "round": 1,
                "score": 81.0,
                "improved": True,
                "successful_research_round": True,
            }
        ]
        (project_dir / "checkpoint.json").write_text(
            json.dumps(
                {
                    "run_id": "run-001",
                    "run_root": str(run_root),
                    "last_completed_round": 1,
                    "best_score": 81.0,
                    "best_round": 1,
                    "best_round_path": str(run_root / "round_01"),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        (project_dir / "score_history.json").write_text(
            json.dumps(history, indent=2),
            encoding="utf-8",
        )
        return project_dir

    @staticmethod
    def _snapshot(root: Path) -> dict[str, tuple[str, bytes | None]]:
        snapshot: dict[str, tuple[str, bytes | None]] = {}
        for path in sorted(root.rglob("*")):
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                snapshot[relative] = ("link", os.readlink(path).encode())
            elif path.is_dir():
                snapshot[relative] = ("directory", None)
            else:
                snapshot[relative] = ("file", path.read_bytes())
        return snapshot

    def test_preview_is_an_explicit_provider_free_primary_mode(self) -> None:
        args = cli_module.parse_args(["--legacy-migration-preview", "selected"])

        self.assertEqual(args.legacy_migration_preview, "selected")
        self.assertFalse(cli_module._requires_generation_resources(args))

        stderr = io.StringIO()
        with redirect_stderr(stderr), self.assertRaises(SystemExit) as raised:
            cli_module.parse_args(
                [
                    "--legacy-migration-preview",
                    "selected",
                    "--mock",
                ]
            )
        self.assertEqual(raised.exception.code, 2)
        self.assertNotIn("selected", stderr.getvalue())

    def test_preview_runs_before_config_provider_lock_or_project_input_and_is_read_only(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_dir = self._fixture(root)
            before = self._snapshot(root)
            layout = RuntimeLayout(root, root, root, True)
            stdout = io.StringIO()
            args = cli_module.parse_args(["--legacy-migration-preview", "selected"])
            with (
                redirect_stdout(stdout),
                patch.object(cli_module, "parse_args", return_value=args),
                patch.object(cli_module, "configure_logging"),
                patch.object(cli_module, "resolve_runtime_layout", return_value=layout),
                patch.object(
                    cli_module,
                    "validate_generation_resources",
                    side_effect=AssertionError("generation preflight reached"),
                ) as validate_generation_resources,
                patch.object(
                    cli_module,
                    "load_app_config",
                    side_effect=AssertionError("config load reached"),
                ) as load_app_config,
                patch.object(
                    cli_module,
                    "load_project_input",
                    side_effect=AssertionError("project input reached"),
                ) as load_project_input,
                patch.object(
                    cli_module,
                    "create_llm_client",
                    side_effect=AssertionError("provider construction reached"),
                ) as create_llm_client,
                patch.object(
                    cli_module,
                    "acquire_run_lock",
                    side_effect=AssertionError("lock acquisition reached"),
                ) as acquire_run_lock,
                patch.object(
                    cli_module,
                    "write_json_file",
                    side_effect=AssertionError("artifact write reached"),
                ) as write_json_file,
                patch.object(
                    Path,
                    "rglob",
                    side_effect=AssertionError("recursive project scan reached"),
                ),
                patch(
                    "socket.socket",
                    side_effect=AssertionError("network construction reached"),
                ),
            ):
                cli_module.main()

            output = stdout.getvalue()
            self.assertIn("Legacy migration discovery", output)
            self.assertIn("status: eligible_candidate", output)
            self.assertIn("classification: exact_missing_history_twin", output)
            self.assertIn("execution_authorized: false", output)
            self.assertNotIn(str(root), output)
            self.assertEqual(before, self._snapshot(root))
            self.assertEqual(project_dir, root / "projects" / "selected")
            validate_generation_resources.assert_not_called()
            load_app_config.assert_not_called()
            load_project_input.assert_not_called()
            create_llm_client.assert_not_called()
            acquire_run_lock.assert_not_called()
            write_json_file.assert_not_called()

    def test_invalid_project_name_exits_two_before_config_without_echoing_value(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            private_value = "../private-project"
            stdout = io.StringIO()
            args = cli_module.parse_args(["--legacy-migration-preview", private_value])
            with (
                redirect_stdout(stdout),
                patch.object(cli_module, "parse_args", return_value=args),
                patch.object(cli_module, "configure_logging"),
                patch.object(
                    cli_module,
                    "resolve_runtime_layout",
                    return_value=RuntimeLayout(root, root, root, True),
                ),
                patch.object(
                    cli_module,
                    "load_app_config",
                    side_effect=AssertionError("config load reached"),
                ) as load_app_config,
            ):
                with self.assertRaises(SystemExit) as raised:
                    cli_module.main()

            self.assertEqual(raised.exception.code, 2)
            self.assertIn("Project name must be a simple folder name", stdout.getvalue())
            self.assertNotIn(private_value, stdout.getvalue())
            self.assertFalse((root / "projects").exists())
            load_app_config.assert_not_called()

    def test_unexpected_preview_error_is_generic_and_path_redacted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stdout = io.StringIO()
            args = cli_module.parse_args(["--legacy-migration-preview", "selected"])
            with (
                redirect_stdout(stdout),
                patch.object(cli_module, "parse_args", return_value=args),
                patch.object(cli_module, "configure_logging"),
                patch.object(
                    cli_module,
                    "resolve_runtime_layout",
                    return_value=RuntimeLayout(root, root, root, True),
                ),
                patch.object(
                    cli_module,
                    "classify_legacy_history_migration",
                    side_effect=OSError(f"private path: {root}"),
                ),
            ):
                with self.assertRaises(SystemExit) as raised:
                    cli_module.main()

            self.assertEqual(raised.exception.code, 1)
            self.assertIn("Legacy migration preview failed", stdout.getvalue())
            self.assertNotIn(str(root), stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
