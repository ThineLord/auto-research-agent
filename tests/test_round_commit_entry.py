from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from rich.console import Console

import src.cli as cli_module
import src.round_commit_recovery as recovery_module
from src.benchmark_report import write_benchmark_report
from src.config import AppConfig
from src.mock_run import build_mock_agents
from src.resume import build_resume_preview
from src.run_analytics import analyze_run
from src.run_compare import compare_runs
from tests.test_round_commit_runner import _run_one_round
from ui.app import (
    build_output_catalog,
    build_run_analytics_dashboard,
    build_run_comparison_rows,
)


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink()
    }


class RoundCommitEntryTests(unittest.TestCase):
    def _pending_commit(self, root: Path) -> tuple[Path, Path]:
        project_dir = root / "project"
        project_dir.mkdir()
        (project_dir / "memory.md").write_text("Manual memory.\n", encoding="utf-8")
        real_write = recovery_module.write_file_text
        failed = False

        def fail_second_history_once(
            path: Path,
            content: str,
            *,
            anchor: Path | None = None,
        ) -> None:
            nonlocal failed
            if path.name == "round_metrics.json" and not failed:
                failed = True
                raise OSError("injected mixed-generation boundary")
            real_write(path, content, anchor=anchor)

        with patch.object(
            recovery_module,
            "write_file_text",
            side_effect=fail_second_history_once,
        ):
            with self.assertRaises(recovery_module.RoundCommitRecoveryIOError):
                _run_one_round(project_dir, repo_root=root)
        self.assertTrue(failed)
        run_root = next(path for path in (project_dir / "runs").iterdir() if path.is_dir())
        return project_dir, run_root

    def test_preview_reports_recovery_required_without_mutating(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir, _ = self._pending_commit(root)
            before = _snapshot(root)

            preview = build_resume_preview(
                project_dir=project_dir,
                checkpoint={},
                repo_root=root,
            )

            self.assertFalse(preview["can_resume"])
            self.assertEqual(
                preview["blocked_reason"],
                "round_commit_recovery_required",
            )
            self.assertEqual(preview["round_commit_status"], "apply_pending")
            self.assertEqual(_snapshot(root), before)

    def test_preview_and_ui_expose_conflict_without_mutating(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir, _ = self._pending_commit(root)
            (project_dir / "score_history.json").write_text(
                '[{"round": 99, "score": 999}]',
                encoding="utf-8",
            )
            before = _snapshot(root)

            preview = build_resume_preview(
                project_dir=project_dir,
                checkpoint={},
                repo_root=root,
            )
            dashboard = build_run_analytics_dashboard(project_dir, {})

            self.assertEqual(
                preview["blocked_reason"],
                "round_commit_recovery_conflict",
            )
            self.assertEqual(preview["round_commit_status"], "conflict")
            self.assertEqual(
                dashboard["blocked_reason"],
                "round_commit_recovery_conflict",
            )
            self.assertEqual(dashboard["round_commit_status"], "conflict")
            self.assertEqual(_snapshot(root), before)

    def test_entry_recovery_is_provider_free_and_regenerates_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir, _ = self._pending_commit(root)
            console = Console(record=True)

            recovered = cli_module._recover_pending_round_commit(
                console=console,
                project_dir=project_dir,
            )

            self.assertEqual(recovered.status, "recovered")
            self.assertFalse((project_dir / recovery_module.ROUND_COMMIT_JOURNAL_NAME).exists())
            checkpoint = json.loads((project_dir / "checkpoint.json").read_text(encoding="utf-8"))
            self.assertEqual(checkpoint["last_completed_round"], 1)
            self.assertIn("Recovered pending round commit", console.export_text())

    def test_mock_entry_recovers_after_lock_and_before_agent_construction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "projects" / "example"
            project_dir.mkdir(parents=True)
            (project_dir / "task.md").write_text("# Mock task\n", encoding="utf-8")
            args = cli_module.parse_args(["--mock", "--project", "example"])
            events: list[str] = []

            def recover(**_: object) -> recovery_module.RoundCommitRecoveryInspection:
                events.append("recover")
                return recovery_module.RoundCommitRecoveryInspection(
                    status="absent",
                    can_recover=False,
                    journal_present=False,
                )

            def construct_agents(*, topic_context: str):
                events.append("agents")
                return build_mock_agents(topic_context=topic_context)

            with (
                patch.object(cli_module, "parse_args", return_value=args),
                patch.object(cli_module, "load_app_config", return_value=AppConfig()),
                patch.object(
                    cli_module,
                    "load_project_input",
                    return_value=SimpleNamespace(
                        project_name="example",
                        project_dir=project_dir,
                        task_path=project_dir / "task.md",
                        task_text="# Mock task",
                        project_title="Mock task",
                        source_kind="example_default",
                        as_metadata=lambda: {"project_name": "example"},
                    ),
                ),
                patch.object(
                    cli_module,
                    "acquire_run_lock",
                    side_effect=lambda *args, **kwargs: (
                        events.append("lock") or project_dir / "run.lock",
                        None,
                    ),
                ),
                patch.object(cli_module, "release_run_lock"),
                patch.object(
                    cli_module,
                    "_recover_pending_round_commit",
                    side_effect=recover,
                ),
                patch.object(
                    cli_module,
                    "build_mock_agents",
                    side_effect=construct_agents,
                ),
                patch.object(cli_module, "run_iterative_rounds"),
            ):
                cli_module.main()

            self.assertEqual(events, ["lock", "recover", "agents"])

    def test_normal_entry_recovers_before_provider_preflight_and_client(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "projects" / "example"
            project_dir.mkdir(parents=True)
            (project_dir / "task.md").write_text("# Normal task\n", encoding="utf-8")
            args = cli_module.parse_args(["--project", "example"])
            events: list[str] = []

            with (
                patch.object(cli_module, "parse_args", return_value=args),
                patch.object(cli_module, "load_app_config", return_value=AppConfig()),
                patch.object(
                    cli_module,
                    "load_project_input",
                    return_value=SimpleNamespace(
                        project_name="example",
                        project_dir=project_dir,
                        task_path=project_dir / "task.md",
                        task_text="# Normal task",
                        project_title="Normal task",
                        source_kind="example_default",
                        as_metadata=lambda: {"project_name": "example"},
                    ),
                ),
                patch.object(
                    cli_module,
                    "acquire_run_lock",
                    side_effect=lambda *args, **kwargs: (
                        events.append("lock") or project_dir / "run.lock",
                        None,
                    ),
                ),
                patch.object(cli_module, "release_run_lock"),
                patch.object(
                    cli_module,
                    "_recover_pending_round_commit",
                    side_effect=lambda **kwargs: (
                        events.append("recover")
                        or recovery_module.RoundCommitRecoveryInspection(
                            status="absent",
                            can_recover=False,
                            journal_present=False,
                        )
                    ),
                ),
                patch.object(
                    cli_module,
                    "list_installed_ollama_models",
                    side_effect=lambda: (
                        events.append("provider") or ["qwen3:8b"],
                        None,
                    ),
                ),
                patch.object(
                    cli_module,
                    "create_llm_client",
                    side_effect=lambda **kwargs: events.append("client") or object(),
                ),
                patch.object(
                    cli_module.ResearchAgents,
                    "from_prompt_dir",
                    side_effect=lambda **kwargs: events.append("agents") or object(),
                ),
                patch.object(cli_module, "run_iterative_rounds"),
            ):
                cli_module.main()

            self.assertEqual(
                events,
                ["lock", "recover", "provider", "client", "agents"],
            )

    def test_diagnostic_entry_recovers_before_provider_preflight_and_client(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "projects" / "example"
            project_dir.mkdir(parents=True)
            (project_dir / "task.md").write_text("# Diagnostic task\n", encoding="utf-8")
            args = cli_module.parse_args(["--diagnostic", "--project", "example"])
            events: list[str] = []

            with (
                patch.object(cli_module, "parse_args", return_value=args),
                patch.object(cli_module, "load_app_config", return_value=AppConfig()),
                patch.object(
                    cli_module,
                    "load_project_input",
                    return_value=SimpleNamespace(
                        project_name="example",
                        project_dir=project_dir,
                        task_path=project_dir / "task.md",
                        task_text="# Diagnostic task",
                        project_title="Diagnostic task",
                        source_kind="example_default",
                        as_metadata=lambda: {"project_name": "example"},
                    ),
                ),
                patch.object(
                    cli_module,
                    "acquire_run_lock",
                    side_effect=lambda *args, **kwargs: (
                        events.append("lock") or project_dir / "run.lock",
                        None,
                    ),
                ),
                patch.object(cli_module, "release_run_lock"),
                patch.object(
                    cli_module,
                    "_recover_pending_round_commit",
                    side_effect=lambda **kwargs: (
                        events.append("recover")
                        or recovery_module.RoundCommitRecoveryInspection(
                            status="absent",
                            can_recover=False,
                            journal_present=False,
                        )
                    ),
                ),
                patch.object(
                    cli_module,
                    "list_installed_ollama_models",
                    side_effect=lambda: (
                        events.append("provider") or ["qwen3:8b"],
                        None,
                    ),
                ),
                patch.object(
                    cli_module,
                    "create_llm_client",
                    side_effect=lambda **kwargs: events.append("client") or object(),
                ),
                patch.object(
                    cli_module.ResearchAgents,
                    "from_prompt_dir",
                    side_effect=lambda **kwargs: events.append("agents") or object(),
                ),
                patch.object(
                    cli_module,
                    "run_diagnostic_mode",
                    side_effect=lambda **kwargs: events.append("diagnostic"),
                ),
            ):
                cli_module.main()

            self.assertEqual(
                events,
                ["lock", "recover", "provider", "client", "agents", "diagnostic"],
            )

    def test_entry_conflict_blocks_without_mutation_or_path_disclosure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir, _ = self._pending_commit(root)
            (project_dir / "score_history.json").write_text(
                '[{"round": 99, "score": 999}]',
                encoding="utf-8",
            )
            before = _snapshot(root)
            console = Console(record=True)

            with self.assertRaisesRegex(SystemExit, "2"):
                cli_module._recover_pending_round_commit(
                    console=console,
                    project_dir=project_dir,
                )

            output = console.export_text()
            self.assertIn("round commit recovery is blocked", output.lower())
            self.assertNotIn(str(root), output)
            self.assertEqual(_snapshot(root), before)

    def test_analytics_and_report_refuse_mixed_generation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir, run_root = self._pending_commit(root)
            report_path = project_dir / "benchmark.md"

            with self.assertRaisesRegex(RuntimeError, "round_commit_recovery_required"):
                analyze_run(run_root, project_dir=project_dir)
            with self.assertRaisesRegex(RuntimeError, "round_commit_recovery_required"):
                compare_runs([run_root])
            self.assertEqual(
                build_run_comparison_rows(
                    [run_root],
                    project_dir=project_dir,
                ),
                [],
            )
            with self.assertRaisesRegex(RuntimeError, "round_commit_recovery_required"):
                write_benchmark_report(
                    run_root=run_root,
                    output_path=report_path,
                    project_dir=project_dir,
                )

            self.assertFalse(report_path.exists())

    def test_ui_blocks_mixed_generation_analytics_and_transaction_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir, _ = self._pending_commit(root)

            dashboard = build_run_analytics_dashboard(project_dir, {})
            catalog = build_output_catalog(project_dir, {})

            self.assertFalse(dashboard["available"])
            self.assertEqual(
                dashboard["blocked_reason"],
                "round_commit_recovery_required",
            )
            sensitive = {
                item["label"]: item
                for item in catalog
                if item["label"]
                in {
                    "Best output",
                    "Checkpoint",
                    "Round metrics",
                    "Score history",
                }
            }
            self.assertEqual(len(sensitive), 4)
            for item in sensitive.values():
                self.assertFalse(item["exists"])
                self.assertEqual(
                    item["missing_key"],
                    "round_commit_recovery_required",
                )

    def test_invalid_finalization_only_state_blocks_readers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "project"
            project_dir.mkdir()
            (project_dir / recovery_module.RUN_FINALIZE_JOURNAL_NAME).write_text(
                "{}",
                encoding="utf-8",
            )

            inspection = recovery_module.classify_round_commit_recovery(project_dir)
            finalization = recovery_module.classify_run_finalize_recovery(project_dir)
            preview = build_resume_preview(
                project_dir=project_dir,
                checkpoint={},
            )

            self.assertEqual(inspection.status, "absent")
            self.assertEqual(finalization.status, "invalid")
            self.assertFalse(finalization.can_recover)
            self.assertEqual(preview["blocked_reason"], "finalization_conflict")
            self.assertEqual(preview["finalization_status"], "invalid")


if __name__ == "__main__":
    unittest.main()
