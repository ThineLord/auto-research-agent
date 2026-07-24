from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rich.console import Console

import src.round_commit_recovery as recovery_module
from src.cloud_free import CloudFreeDailyQuotaExhausted
from src.diagnostic import run_diagnostic_mode
from src.resume import build_resume_preview
from src.round_commit import (
    RoundCommitCodecError,
    build_checkpoint_after_image,
    build_history_after_image,
    build_run_config_after_image,
    build_run_summary_after_image,
    decode_diagnostic_finalize_journal,
    encode_diagnostic_finalize_journal,
)
from src.round_commit_recovery import (
    DIAGNOSTIC_FINALIZE_JOURNAL_NAME,
    RUN_FINALIZE_JOURNAL_NAME,
    RoundCommitRecoveryError,
    RoundCommitRecoveryIOError,
    classify_diagnostic_finalize_recovery,
    prepare_diagnostic_finalize,
    recover_diagnostic_finalize,
    recover_run_finalize,
)
from src.run_analytics import analyze_run
from tests.test_diagnostic import FakeDiagnosticLLM
from ui.app import build_run_analytics_dashboard, describe_resume_state


class QuotaDiagnosticLLM(FakeDiagnosticLLM):
    def generate(self, **kwargs: object) -> str:
        raise CloudFreeDailyQuotaExhausted("daily quota test stop")


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink()
    }


class DiagnosticFinalizeRecoveryTests(unittest.TestCase):
    def _fixture(
        self,
        root: Path,
        *,
        external_storage: bool = False,
    ) -> dict[str, object]:
        project_dir = root / "project"
        project_dir.mkdir()
        if external_storage:
            runs_root = root / "external-runs"
            runs_root.mkdir()
            (project_dir / "runs").symlink_to(runs_root, target_is_directory=True)
        else:
            runs_root = project_dir / "runs"
        run_root = runs_root / "diagnostic-run"
        run_root.mkdir(parents=True)

        running_config = {
            "schema_version": 1,
            "run_id": run_root.name,
            "run_root": str(run_root.resolve()),
            "mode": "diagnostic",
            "status": "running",
            "stop_reason": "",
            "can_resume": None,
            "completed_rounds": 0,
            "resume_metadata": {
                "lifecycle_action": "start_new_run",
                "can_resume": False,
                "last_completed_round": 0,
                "next_round": None,
                "stop_reason": "",
            },
        }
        prior_summary = {
            "run_id": run_root.name,
            "run_root": str(run_root.resolve()),
            "mode": "diagnostic",
            "completed_rounds": 0,
        }
        prior_checkpoint = {
            "run_id": run_root.name,
            "run_root": str(run_root.resolve()),
            "mode": "diagnostic",
            "last_completed_round": 0,
            "can_resume": False,
        }
        (run_root / "run_config.json").write_text(
            json.dumps(running_config, indent=2),
            encoding="utf-8",
        )
        (run_root / "run_summary.json").write_text(
            json.dumps(prior_summary, indent=2),
            encoding="utf-8",
        )
        (project_dir / "checkpoint.json").write_text(
            json.dumps(prior_checkpoint, indent=2),
            encoding="utf-8",
        )
        (project_dir / "score_history.json").write_text(
            json.dumps([{"round": 9, "score": 9.0}], indent=2),
            encoding="utf-8",
        )

        round_metric = {
            "round": 1,
            "score": 81.0,
            "improved": True,
            "errors": [],
            "model": "fake-model",
            "drafting_mode": "best_guided",
        }
        score_after = build_history_after_image([], round_metric, round_index=1)
        metrics_after = build_history_after_image([], round_metric, round_index=1)
        resume_metadata = {
            "lifecycle_action": "start_new_run",
            "resume_from_checkpoint": False,
            "can_resume": False,
            "last_completed_round": 1,
            "next_round": None,
            "stop_reason": "MAX_ROUNDS",
        }
        ended_at = "2026-07-24T19:00:00+08:00"
        summary_after = build_run_summary_after_image(
            {
                "run_id": run_root.name,
                "run_root": str(run_root.resolve()),
                "mode": "diagnostic",
                "completed_rounds": 1,
                "best_round": 1,
                "best_score": 81.0,
                "stop_reason": "MAX_ROUNDS",
                "can_resume": False,
                "resume_metadata": resume_metadata,
                "round_count": 1,
            }
        )
        config_after = build_run_config_after_image(
            {
                **running_config,
                "status": "completed",
                "ended_at": ended_at,
                "updated_at": ended_at,
                "stop_reason": "MAX_ROUNDS",
                "can_resume": False,
                "completed_rounds": 1,
                "best_round": 1,
                "best_score": 81.0,
                "resume_metadata": resume_metadata,
            }
        )
        checkpoint_after = build_checkpoint_after_image(
            {
                **prior_checkpoint,
                "updated_at": ended_at,
                "last_completed_round": 1,
                "best_score": 81.0,
                "best_round_path": str(run_root.resolve() / "round_01"),
                "stop_reason": "MAX_ROUNDS",
                "can_resume": False,
                "resume_metadata": resume_metadata,
            }
        )
        return {
            "project_dir": project_dir,
            "run_root": run_root.resolve(),
            "score_after": score_after,
            "metrics_after": metrics_after,
            "summary_after": summary_after,
            "config_after": config_after,
            "checkpoint_after": checkpoint_after,
        }

    def _prepare(self, fixture: dict[str, object]) -> dict[str, object]:
        return prepare_diagnostic_finalize(
            project_dir=fixture["project_dir"],  # type: ignore[arg-type]
            run_root=fixture["run_root"],  # type: ignore[arg-type]
            score_history_after=fixture["score_after"],  # type: ignore[arg-type]
            round_metrics_after=fixture["metrics_after"],  # type: ignore[arg-type]
            run_summary_after=fixture["summary_after"],  # type: ignore[arg-type]
            run_config_after=fixture["config_after"],  # type: ignore[arg-type]
            checkpoint_after=fixture["checkpoint_after"],  # type: ignore[arg-type]
            transaction_id="diagnostic_12345678",
        )

    def test_codec_round_trip_is_strict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = self._fixture(Path(tmp))
            payload = self._prepare(fixture)
            journal_path = (
                fixture["project_dir"] / DIAGNOSTIC_FINALIZE_JOURNAL_NAME  # type: ignore[operator]
            )
            encoded = journal_path.read_text(encoding="utf-8")

            self.assertEqual(decode_diagnostic_finalize_journal(encoded), payload)
            self.assertEqual(encode_diagnostic_finalize_journal(payload), encoded)
            unknown = dict(payload)
            unknown["unknown"] = True
            with self.assertRaises(RoundCommitCodecError):
                encode_diagnostic_finalize_journal(unknown)

    def test_recovery_converges_every_write_boundary_across_storage_layouts(self) -> None:
        filenames = (
            "score_history.json",
            "round_metrics.json",
            "run_summary.json",
            "run_config.json",
            "checkpoint.json",
        )
        for external_storage in (False, True):
            for fault_type in (OSError, KeyboardInterrupt):
                for filename in filenames:
                    with (
                        self.subTest(
                            external_storage=external_storage,
                            fault_type=fault_type.__name__,
                            filename=filename,
                        ),
                        tempfile.TemporaryDirectory() as tmp,
                    ):
                        fixture = self._fixture(
                            Path(tmp),
                            external_storage=external_storage,
                        )
                        self._prepare(fixture)
                        real_write = recovery_module.write_file_text
                        failed = False

                        def fail_once(
                            path: Path,
                            content: str,
                            *,
                            anchor: Path | None = None,
                        ) -> None:
                            nonlocal failed
                            if path.name == filename and not failed:
                                failed = True
                                raise fault_type("injected diagnostic finalization write failure")
                            real_write(path, content, anchor=anchor)

                        expected = (
                            RoundCommitRecoveryIOError
                            if fault_type is OSError
                            else KeyboardInterrupt
                        )
                        with patch.object(
                            recovery_module,
                            "write_file_text",
                            side_effect=fail_once,
                        ):
                            with self.assertRaises(expected):
                                recover_diagnostic_finalize(
                                    fixture["project_dir"]  # type: ignore[arg-type]
                                )

                        self.assertTrue(failed)
                        inspection = classify_diagnostic_finalize_recovery(
                            fixture["project_dir"]  # type: ignore[arg-type]
                        )
                        self.assertTrue(inspection.can_recover)
                        self.assertEqual(
                            recover_diagnostic_finalize(
                                fixture["project_dir"]  # type: ignore[arg-type]
                            ).status,
                            "recovered",
                        )
                        self.assertEqual(
                            recover_diagnostic_finalize(
                                fixture["project_dir"]  # type: ignore[arg-type]
                            ).status,
                            "absent",
                        )

    def test_cleanup_failure_preserves_complete_journal_for_retry(self) -> None:
        for external_storage in (False, True):
            for fault_type in (OSError, KeyboardInterrupt):
                with (
                    self.subTest(
                        external_storage=external_storage,
                        fault_type=fault_type.__name__,
                    ),
                    tempfile.TemporaryDirectory() as tmp,
                ):
                    fixture = self._fixture(
                        Path(tmp),
                        external_storage=external_storage,
                    )
                    self._prepare(fixture)
                    expected = (
                        RoundCommitRecoveryIOError if fault_type is OSError else KeyboardInterrupt
                    )
                    with patch.object(
                        recovery_module,
                        "unlink_artifact_file_if_matches",
                        side_effect=fault_type("injected diagnostic cleanup failure"),
                    ):
                        with self.assertRaises(expected):
                            recover_diagnostic_finalize(
                                fixture["project_dir"]  # type: ignore[arg-type]
                            )

                    inspection = classify_diagnostic_finalize_recovery(
                        fixture["project_dir"]  # type: ignore[arg-type]
                    )
                    self.assertEqual(inspection.status, "complete")
                    self.assertTrue(inspection.can_recover)
                    self.assertEqual(
                        recover_diagnostic_finalize(
                            fixture["project_dir"]  # type: ignore[arg-type]
                        ).status,
                        "recovered",
                    )

    def test_conflict_and_readers_are_non_mutating_and_path_redacted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = self._fixture(root)
            self._prepare(fixture)
            (fixture["run_root"] / "round_metrics.json").write_text(  # type: ignore[operator]
                '[{"round": 99}]',
                encoding="utf-8",
            )
            before = _snapshot(root)
            inspection = classify_diagnostic_finalize_recovery(
                fixture["project_dir"]  # type: ignore[arg-type]
            )
            self.assertEqual(inspection.status, "conflict")
            self.assertFalse(inspection.can_recover)
            with self.assertRaises(RoundCommitRecoveryError) as raised:
                recover_diagnostic_finalize(
                    fixture["project_dir"]  # type: ignore[arg-type]
                )
            self.assertNotIn(str(root), str(raised.exception))
            self.assertEqual(_snapshot(root), before)

    def test_preview_ui_and_analytics_refuse_pending_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = self._fixture(root)
            self._prepare(fixture)
            before = _snapshot(root)
            checkpoint = json.loads(
                (fixture["project_dir"] / "checkpoint.json").read_text(  # type: ignore[operator]
                    encoding="utf-8"
                )
            )

            preview = build_resume_preview(
                project_dir=fixture["project_dir"],  # type: ignore[arg-type]
                checkpoint=checkpoint,
                repo_root=root,
            )
            self.assertEqual(preview["blocked_reason"], "diagnostic_finalization_pending")
            self.assertEqual(preview["diagnostic_finalization_status"], "apply_pending")
            resume_state = describe_resume_state(
                project_dir=fixture["project_dir"],  # type: ignore[arg-type]
                checkpoint=checkpoint,
                run_active=False,
                selected_model="",
            )
            self.assertEqual(
                resume_state["message_key"],
                "diagnostic_finalization_pending",
            )
            dashboard = build_run_analytics_dashboard(
                fixture["project_dir"],  # type: ignore[arg-type]
                checkpoint,
            )
            self.assertEqual(
                dashboard["blocked_reason"],
                "diagnostic_finalization_pending",
            )
            with self.assertRaisesRegex(RuntimeError, "diagnostic_finalization_pending"):
                analyze_run(
                    fixture["run_root"],  # type: ignore[arg-type]
                    project_dir=fixture["project_dir"],  # type: ignore[arg-type]
                )
            self.assertEqual(_snapshot(root), before)

    def test_diagnostic_writer_failure_leaves_recoverable_transaction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir = root / "project"
            project_dir.mkdir()
            memory_path = project_dir / "memory.md"
            memory_path.write_text("memory", encoding="utf-8")
            real_write = recovery_module.write_file_text
            failed = False

            def fail_metrics_once(
                path: Path,
                content: str,
                *,
                anchor: Path | None = None,
            ) -> None:
                nonlocal failed
                if path.name == "round_metrics.json" and not failed:
                    failed = True
                    raise OSError("injected diagnostic metrics failure")
                real_write(path, content, anchor=anchor)

            with patch.object(
                recovery_module,
                "write_file_text",
                side_effect=fail_metrics_once,
            ):
                with self.assertRaises(RoundCommitRecoveryIOError):
                    run_diagnostic_mode(
                        console=Console(),
                        llm=FakeDiagnosticLLM(),
                        task_text="diagnostic task",
                        project_dir=project_dir,
                        memory_path=memory_path,
                        model_name="fake-model",
                    )

            self.assertTrue(failed)
            self.assertTrue((project_dir / DIAGNOSTIC_FINALIZE_JOURNAL_NAME).is_file())
            self.assertFalse((project_dir / "checkpoint.json").exists())
            recovered = recover_diagnostic_finalize(project_dir)
            self.assertEqual(recovered.status, "recovered")
            checkpoint = json.loads((project_dir / "checkpoint.json").read_text(encoding="utf-8"))
            run_root = next(path for path in (project_dir / "runs").iterdir() if path.is_dir())
            metrics = json.loads((run_root / "round_metrics.json").read_text(encoding="utf-8"))
            summary = json.loads((run_root / "run_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(checkpoint["last_completed_round"], 1)
            self.assertEqual(metrics[0]["round"], 1)
            self.assertEqual(summary["completed_rounds"], 1)

    def test_quota_finalization_reuses_run_finalize_transaction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "project"
            project_dir.mkdir()
            memory_path = project_dir / "memory.md"
            memory_path.write_text("memory", encoding="utf-8")
            real_write = recovery_module.write_file_text
            failed = False

            def fail_summary_once(
                path: Path,
                content: str,
                *,
                anchor: Path | None = None,
            ) -> None:
                nonlocal failed
                if path.name == "run_summary.json" and not failed:
                    failed = True
                    raise OSError("injected quota summary failure")
                real_write(path, content, anchor=anchor)

            with patch.object(
                recovery_module,
                "write_file_text",
                side_effect=fail_summary_once,
            ):
                with self.assertRaises(RoundCommitRecoveryIOError):
                    run_diagnostic_mode(
                        console=Console(),
                        llm=QuotaDiagnosticLLM(),
                        task_text="diagnostic task",
                        project_dir=project_dir,
                        memory_path=memory_path,
                        model_name="fake-model",
                    )

            self.assertTrue(failed)
            self.assertTrue((project_dir / RUN_FINALIZE_JOURNAL_NAME).is_file())
            self.assertFalse((project_dir / DIAGNOSTIC_FINALIZE_JOURNAL_NAME).exists())
            self.assertEqual(recover_run_finalize(project_dir).status, "recovered")
            checkpoint = json.loads((project_dir / "checkpoint.json").read_text(encoding="utf-8"))
            self.assertEqual(checkpoint["last_completed_round"], 0)
            self.assertTrue(checkpoint["can_resume"])


if __name__ == "__main__":
    unittest.main()
