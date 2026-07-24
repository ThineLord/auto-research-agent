from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rich.console import Console

import src.cli as cli_module
import src.round_commit_recovery as recovery_module
from src.resume import build_resume_preview
from src.round_commit import (
    RoundCommitCodecError,
    build_checkpoint_after_image,
    build_run_config_after_image,
    build_run_summary_after_image,
    decode_run_finalize_journal,
    encode_run_finalize_journal,
)
from src.round_commit_recovery import (
    RUN_FINALIZE_JOURNAL_NAME,
    RoundCommitRecoveryError,
    RoundCommitRecoveryIOError,
    classify_run_finalize_recovery,
    prepare_run_finalize,
    recover_run_finalize,
)
from src.run_analytics import analyze_run
from tests.test_round_commit_runner import _run_one_round
from ui.app import build_run_analytics_dashboard, describe_resume_state


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink()
    }


class RunFinalizeRecoveryTests(unittest.TestCase):
    def _fixture(
        self,
        root: Path,
        *,
        external_storage: bool = False,
        can_resume: bool = False,
    ) -> dict[str, object]:
        project_dir = root / "project"
        project_dir.mkdir()
        if external_storage:
            runs_root = root / "external-runs"
            runs_root.mkdir()
            (project_dir / "runs").symlink_to(runs_root, target_is_directory=True)
        else:
            runs_root = project_dir / "runs"
        run_root = runs_root / "run-1"
        run_root.mkdir(parents=True)

        running_config = {
            "schema_version": 1,
            "run_id": "run-1",
            "run_root": str(run_root.resolve()),
            "status": "running",
            "stop_reason": "",
            "can_resume": None,
            "completed_rounds": 1,
        }
        old_summary = {
            "run_id": "run-1",
            "run_root": str(run_root.resolve()),
            "completed_rounds": 0,
            "stop_reason": "",
            "can_resume": True,
        }
        per_round_checkpoint = {
            "run_id": "run-1",
            "run_root": str(run_root.resolve()),
            "last_completed_round": 1,
            "stop_reason": "",
            "can_resume": True,
        }
        (run_root / "run_config.json").write_text(
            json.dumps(running_config, indent=2),
            encoding="utf-8",
        )
        (run_root / "run_summary.json").write_text(
            json.dumps(old_summary, indent=2),
            encoding="utf-8",
        )
        (project_dir / "checkpoint.json").write_text(
            json.dumps(per_round_checkpoint, indent=2),
            encoding="utf-8",
        )

        resume_metadata = {
            "can_resume": can_resume,
            "last_completed_round": 1,
            "next_round": 2 if can_resume else None,
            "stop_reason": "USER_REQUESTED" if can_resume else "MAX_ROUNDS",
        }
        stop_reason = resume_metadata["stop_reason"]
        ended_at = "2026-07-24T17:00:00+08:00"
        summary_after = build_run_summary_after_image(
            {
                "run_id": "run-1",
                "run_root": str(run_root.resolve()),
                "completed_rounds": 1,
                "best_round": 1,
                "best_score": 70.0,
                "stop_reason": stop_reason,
                "can_resume": can_resume,
                "resume_metadata": resume_metadata,
            }
        )
        config_after = build_run_config_after_image(
            {
                **running_config,
                "status": "completed",
                "ended_at": ended_at,
                "updated_at": ended_at,
                "stop_reason": stop_reason,
                "can_resume": can_resume,
                "completed_rounds": 1,
                "best_round": 1,
                "best_score": 70.0,
                "resume_metadata": resume_metadata,
            }
        )
        checkpoint_after = build_checkpoint_after_image(
            {
                **per_round_checkpoint,
                "updated_at": ended_at,
                "stop_reason": stop_reason,
                "can_resume": can_resume,
                "best_round": 1,
                "best_score": 70.0,
                "resume_metadata": resume_metadata,
            }
        )
        return {
            "project_dir": project_dir,
            "run_root": run_root.resolve(),
            "summary_after": summary_after,
            "config_after": config_after,
            "checkpoint_after": checkpoint_after,
        }

    def _prepare(self, fixture: dict[str, object]) -> dict[str, object]:
        return prepare_run_finalize(
            project_dir=fixture["project_dir"],  # type: ignore[arg-type]
            run_root=fixture["run_root"],  # type: ignore[arg-type]
            run_summary_after=fixture["summary_after"],  # type: ignore[arg-type]
            run_config_after=fixture["config_after"],  # type: ignore[arg-type]
            checkpoint_after=fixture["checkpoint_after"],  # type: ignore[arg-type]
            transaction_id="finalize_12345678",
        )

    def test_codec_round_trip_is_strict_and_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = self._fixture(Path(tmp))
            payload = self._prepare(fixture)
            journal_path = fixture["project_dir"] / RUN_FINALIZE_JOURNAL_NAME  # type: ignore[operator]
            encoded = journal_path.read_text(encoding="utf-8")

            self.assertEqual(decode_run_finalize_journal(encoded), payload)
            self.assertEqual(encode_run_finalize_journal(payload), encoded)

            unknown = dict(payload)
            unknown["unknown"] = True
            with self.assertRaises(RoundCommitCodecError):
                encode_run_finalize_journal(unknown)
            with self.assertRaises(RoundCommitCodecError):
                decode_run_finalize_journal(
                    encoded.replace('"schema_version": 1', '"schema_version": NaN')
                )

    def test_recovery_converges_each_write_boundary_across_storage_layouts(self) -> None:
        for external_storage in (False, True):
            for fault_type in (OSError, KeyboardInterrupt):
                for artifact_name in ("run_summary.json", "run_config.json", "checkpoint.json"):
                    with (
                        self.subTest(
                            external_storage=external_storage,
                            fault_type=fault_type.__name__,
                            artifact_name=artifact_name,
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
                            if path.name == artifact_name and not failed:
                                failed = True
                                raise fault_type("injected finalization write failure")
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
                                recover_run_finalize(fixture["project_dir"])  # type: ignore[arg-type]

                        self.assertTrue(failed)
                        inspection = classify_run_finalize_recovery(
                            fixture["project_dir"]  # type: ignore[arg-type]
                        )
                        self.assertTrue(inspection.can_recover)
                        recovered = recover_run_finalize(
                            fixture["project_dir"]  # type: ignore[arg-type]
                        )
                        self.assertEqual(recovered.status, "recovered")
                        self.assertEqual(
                            recover_run_finalize(
                                fixture["project_dir"]  # type: ignore[arg-type]
                            ).status,
                            "absent",
                        )
                        for key, filename in (
                            ("summary_after", "run_summary.json"),
                            ("config_after", "run_config.json"),
                        ):
                            after = fixture[key]
                            self.assertEqual(
                                (fixture["run_root"] / filename).read_text(  # type: ignore[operator]
                                    encoding="utf-8"
                                ),
                                after.text,  # type: ignore[union-attr]
                            )
                        self.assertEqual(
                            (
                                fixture["project_dir"] / "checkpoint.json"  # type: ignore[operator]
                            ).read_text(encoding="utf-8"),
                            fixture["checkpoint_after"].text,  # type: ignore[union-attr]
                        )

    def test_conflict_is_read_only_and_path_redacted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = self._fixture(root)
            self._prepare(fixture)
            (fixture["run_root"] / "run_summary.json").write_text(  # type: ignore[operator]
                '{"manual": true}',
                encoding="utf-8",
            )
            before = _snapshot(root)

            inspection = classify_run_finalize_recovery(
                fixture["project_dir"]  # type: ignore[arg-type]
            )
            self.assertEqual(inspection.status, "conflict")
            self.assertFalse(inspection.can_recover)
            self.assertEqual(_snapshot(root), before)
            with self.assertRaises(RoundCommitRecoveryError) as raised:
                recover_run_finalize(fixture["project_dir"])  # type: ignore[arg-type]
            self.assertNotIn(str(root), str(raised.exception))
            self.assertEqual(_snapshot(root), before)

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
                        side_effect=fault_type("injected finalization cleanup failure"),
                    ):
                        with self.assertRaises(expected):
                            recover_run_finalize(fixture["project_dir"])  # type: ignore[arg-type]

                    inspection = classify_run_finalize_recovery(
                        fixture["project_dir"]  # type: ignore[arg-type]
                    )
                    self.assertEqual(inspection.status, "complete")
                    self.assertTrue(inspection.can_recover)
                    self.assertEqual(
                        recover_run_finalize(
                            fixture["project_dir"]  # type: ignore[arg-type]
                        ).status,
                        "recovered",
                    )

    def test_preview_and_analytics_refuse_pending_finalization_without_mutation(self) -> None:
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
            self.assertFalse(preview["can_resume"])
            self.assertEqual(preview["blocked_reason"], "finalization_pending")
            self.assertEqual(preview["finalization_status"], "apply_pending")
            resume_state = describe_resume_state(
                project_dir=fixture["project_dir"],  # type: ignore[arg-type]
                checkpoint=checkpoint,
                run_active=False,
                selected_model="",
            )
            self.assertEqual(resume_state["message_key"], "finalization_pending")
            self.assertEqual(
                resume_state["details"]["finalization_status"],
                "apply_pending",
            )
            dashboard = build_run_analytics_dashboard(
                fixture["project_dir"],  # type: ignore[arg-type]
                checkpoint,
            )
            self.assertFalse(dashboard["available"])
            self.assertEqual(dashboard["blocked_reason"], "finalization_pending")
            self.assertEqual(dashboard["finalization_status"], "apply_pending")
            with self.assertRaisesRegex(RuntimeError, "finalization_pending"):
                analyze_run(
                    fixture["run_root"],  # type: ignore[arg-type]
                    project_dir=fixture["project_dir"],  # type: ignore[arg-type]
                )
            self.assertEqual(_snapshot(root), before)

    def test_entry_recovers_pending_finalization_under_existing_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = self._fixture(Path(tmp), can_resume=True)
            self._prepare(fixture)
            console = Console(record=True)

            result = cli_module._recover_pending_round_commit(
                console=console,
                project_dir=fixture["project_dir"],  # type: ignore[arg-type]
            )

            self.assertEqual(result.status, "recovered")
            self.assertIn("finalization", console.export_text().lower())
            self.assertFalse(
                (
                    fixture["project_dir"] / RUN_FINALIZE_JOURNAL_NAME  # type: ignore[operator]
                ).exists()
            )

    def test_runner_failure_leaves_recoverable_finalization_not_final_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir = root / "project"
            project_dir.mkdir()
            (project_dir / "memory.md").write_text("Manual memory.\n", encoding="utf-8")
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
                    raise OSError("injected runner finalization failure")
                real_write(path, content, anchor=anchor)

            with patch.object(
                recovery_module,
                "write_file_text",
                side_effect=fail_summary_once,
            ):
                with self.assertRaises(RoundCommitRecoveryIOError):
                    _run_one_round(project_dir, repo_root=root)

            self.assertTrue(failed)
            self.assertTrue((project_dir / RUN_FINALIZE_JOURNAL_NAME).is_file())
            checkpoint_before = json.loads(
                (project_dir / "checkpoint.json").read_text(encoding="utf-8")
            )
            self.assertNotEqual(checkpoint_before.get("stop_reason"), "MAX_ROUNDS")

            recovered = recover_run_finalize(project_dir)
            self.assertEqual(recovered.status, "recovered")
            checkpoint_after = json.loads(
                (project_dir / "checkpoint.json").read_text(encoding="utf-8")
            )
            run_root = next(path for path in (project_dir / "runs").iterdir() if path.is_dir())
            summary = json.loads((run_root / "run_summary.json").read_text(encoding="utf-8"))
            config = json.loads((run_root / "run_config.json").read_text(encoding="utf-8"))
            self.assertEqual(checkpoint_after["stop_reason"], "MAX_ROUNDS")
            self.assertEqual(summary["stop_reason"], "MAX_ROUNDS")
            self.assertEqual(config["stop_reason"], "MAX_ROUNDS")


if __name__ == "__main__":
    unittest.main()
