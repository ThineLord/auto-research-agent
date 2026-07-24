from __future__ import annotations

import hashlib
import json
import os
import tempfile
import traceback
import unittest
from pathlib import Path
from unittest.mock import patch

import src.round_commit_recovery as round_commit_recovery_module
from src.round_attempts import (
    create_round_attempt,
    mark_attempt_ready_to_publish,
    persist_attempt_stage,
    publish_attempt,
)
from src.round_commit import (
    MAX_ROUND_COMMIT_JOURNAL_BYTES,
    build_checkpoint_after_image,
    build_project_memory_after_image,
    build_research_state_after_image,
    decode_round_commit_journal,
)
from src.round_commit_recovery import (
    DIAGNOSTIC_FINALIZE_JOURNAL_NAME,
    ROUND_COMMIT_JOURNAL_NAME,
    RUN_FINALIZE_JOURNAL_NAME,
    RoundCommitRecoveryError,
    classify_round_commit_recovery,
    prepare_round_commit,
    recover_round_commit,
)
from src.storage import (
    PROJECT_RUNTIME_FILE_NAMES,
    ensure_project_runtime_paths_safe,
    read_regular_text,
    unlink_artifact_file,
    write_file_text,
    write_file_text_create_only,
    write_json_file,
    write_score_history,
    write_text,
)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _snapshot(*roots: Path) -> dict[str, bytes]:
    snapshot: dict[str, bytes] = {}
    for root_index, root in enumerate(roots):
        for path in root.rglob("*"):
            if path.is_file() and not path.is_symlink():
                relative = path.relative_to(root).as_posix()
                snapshot[f"{root_index}:{relative}"] = path.read_bytes()
    return snapshot


class RoundCommitRecoveryTests(unittest.TestCase):
    def _fixture(
        self,
        tmp: str,
        *,
        external_storage: bool = False,
    ) -> dict[str, object]:
        root = Path(tmp)
        project_dir = root / "project"
        project_dir.mkdir()
        if external_storage:
            runs_root = root / "external-runs"
            runs_root.mkdir()
            (project_dir / "runs").symlink_to(runs_root, target_is_directory=True)
        else:
            runs_root = project_dir / "runs"
            runs_root.mkdir()
        run_root = runs_root / "run-1"
        run_root.mkdir()
        ensure_project_runtime_paths_safe(project_dir, anchor=root)

        run_config_path = run_root / "run_config.json"
        write_json_file(
            run_config_path,
            {"run_id": "run-1", "status": "running", "mode": "mock"},
            anchor=run_root,
        )
        run_config_sha256 = _sha256(read_regular_text(run_config_path, anchor=run_root))
        attempt_dir = create_round_attempt(
            run_root=run_root,
            round_index=2,
            run_config_sha256=run_config_sha256,
            attempt_id="attempt_12345678",
            created_at="2026-07-23T12:00:00+00:00",
        )
        stage_outputs = {
            "draft": "round two draft",
            "review": "the baseline remains incomplete",
            "revise": "round two revised result",
            "judge": "Score: 60\nThe mechanism is bounded.",
        }
        for index, (stage, output) in enumerate(stage_outputs.items(), start=1):
            persist_attempt_stage(
                attempt_dir,
                stage,
                output,
                updated_at=f"2026-07-23T12:0{index}:00+00:00",
            )

        metric = {
            "round": 2,
            "score": 60.0,
            "improved": True,
            "errors": [],
        }
        previous_history = [{"round": 1, "score": 50.0, "improved": True}]
        score_history_path = project_dir / "score_history.json"
        round_metrics_path = run_root / "round_metrics.json"
        write_score_history(score_history_path, previous_history, anchor=project_dir)
        write_score_history(round_metrics_path, previous_history, anchor=run_root)
        write_text(project_dir / "best_output.md", "round one best", anchor=project_dir)
        write_file_text(
            project_dir / "memory.md",
            "Manual notes.\n",
            anchor=project_dir,
        )
        write_json_file(
            project_dir / "research_state.json",
            {"round": 1, "current_best_score": 50.0},
            anchor=project_dir,
        )
        write_json_file(
            project_dir / "checkpoint.json",
            {
                "run_id": "run-1",
                "run_root": str(run_root.resolve()),
                "last_completed_round": 1,
                "best_score": 50.0,
                "can_resume": True,
            },
            anchor=project_dir,
        )

        memory_after = build_project_memory_after_image(
            read_regular_text(project_dir / "memory.md", anchor=project_dir),
            round_index=2,
            summary={
                "strongest": "A bounded mechanism.",
                "criticism": "The baseline is incomplete.",
                "unresolved": "Failure recovery remains open.",
                "next_action": "Run one controlled ablation.",
                "best_score": "60.00",
            },
        )
        research_state_after = build_research_state_after_image(
            round_index=2,
            best_score=60.0,
            revised_output=stage_outputs["revise"],
            review_output=stage_outputs["review"],
            judge_output=stage_outputs["judge"],
        )
        checkpoint_after = build_checkpoint_after_image(
            {
                "run_id": "run-1",
                "run_root": str(run_root.resolve()),
                "run_config": str(run_config_path.resolve()),
                "run_summary": str((run_root / "run_summary.json").resolve()),
                "last_completed_round": 2,
                "last_successful_agent": "judge",
                "best_score": 60.0,
                "best_round": 2,
                "can_resume": True,
                "stop_reason": "",
            }
        )
        return {
            "root": root,
            "project_dir": project_dir,
            "run_root": run_root.resolve(),
            "attempt_dir": attempt_dir.resolve(),
            "metric": metric,
            "memory_after": memory_after,
            "research_state_after": research_state_after,
            "checkpoint_after": checkpoint_after,
            "score_history_path": score_history_path,
            "round_metrics_path": round_metrics_path,
        }

    def _prepare(self, fixture: dict[str, object]) -> dict[str, object]:
        return prepare_round_commit(
            project_dir=fixture["project_dir"],  # type: ignore[arg-type]
            run_root=fixture["run_root"],  # type: ignore[arg-type]
            attempt_dir=fixture["attempt_dir"],  # type: ignore[arg-type]
            round_metric=fixture["metric"],  # type: ignore[arg-type]
            best_output_write=True,
            memory_after=fixture["memory_after"],  # type: ignore[arg-type]
            research_state_after=fixture["research_state_after"],  # type: ignore[arg-type]
            checkpoint_after=fixture["checkpoint_after"],  # type: ignore[arg-type]
            transaction_id="txn_12345678",
        )

    def _first_round_fixture(self, tmp: str) -> dict[str, object]:
        root = Path(tmp)
        project_dir = root / "project"
        project_dir.mkdir()
        run_root = project_dir / "runs" / "new-run"
        run_root.mkdir(parents=True)
        ensure_project_runtime_paths_safe(project_dir, anchor=root)

        run_config_path = run_root / "run_config.json"
        write_json_file(
            run_config_path,
            {"run_id": "new-run", "status": "running", "mode": "mock"},
            anchor=run_root,
        )
        run_config_sha256 = _sha256(read_regular_text(run_config_path, anchor=run_root))
        attempt_dir = create_round_attempt(
            run_root=run_root,
            round_index=1,
            run_config_sha256=run_config_sha256,
            attempt_id="attempt_87654321",
            created_at="2026-07-23T12:00:00+00:00",
        )
        stage_outputs = {
            "draft": "first-round draft",
            "review": "the first round needs another iteration",
            "revise": "first-round revised result",
            "judge": "Score: 40\nContinue.",
        }
        for index, (stage, output) in enumerate(stage_outputs.items(), start=1):
            persist_attempt_stage(
                attempt_dir,
                stage,
                output,
                updated_at=f"2026-07-23T12:0{index}:00+00:00",
            )

        # These project-level artifacts deliberately belong to an older run. A new
        # run's round-one history must replace them rather than append to them.
        write_score_history(
            project_dir / "score_history.json",
            [{"round": 1, "score": 99.0, "improved": True}],
            anchor=project_dir,
        )
        write_file_text(project_dir / "memory.md", "Prior run notes.\n", anchor=project_dir)
        write_json_file(
            project_dir / "research_state.json",
            {"round": 9, "current_best_score": 99.0},
            anchor=project_dir,
        )
        write_json_file(
            project_dir / "checkpoint.json",
            {
                "run_id": "old-run",
                "run_root": str(root / "old-run"),
                "last_completed_round": 9,
                "best_score": 99.0,
                "can_resume": False,
            },
            anchor=project_dir,
        )
        metric = {
            "round": 1,
            "score": 40.0,
            "improved": False,
            "errors": [],
        }
        memory_after = build_project_memory_after_image(
            read_regular_text(project_dir / "memory.md", anchor=project_dir),
            round_index=1,
            summary={
                "strongest": "The first-round mechanism is bounded.",
                "criticism": "The first round needs another iteration.",
                "unresolved": "The evaluation remains incomplete.",
                "next_action": "Run round two.",
                "best_score": "40.00",
            },
        )
        research_state_after = build_research_state_after_image(
            round_index=1,
            best_score=40.0,
            revised_output=stage_outputs["revise"],
            review_output=stage_outputs["review"],
            judge_output=stage_outputs["judge"],
        )
        checkpoint_after = build_checkpoint_after_image(
            {
                "run_id": "new-run",
                "run_root": str(run_root.resolve()),
                "run_config": str(run_config_path.resolve()),
                "run_summary": str((run_root / "run_summary.json").resolve()),
                "last_completed_round": 1,
                "last_successful_agent": "judge",
                "best_score": 40.0,
                "best_round": 1,
                "can_resume": True,
                "stop_reason": "",
            }
        )
        return {
            "project_dir": project_dir,
            "run_root": run_root.resolve(),
            "attempt_dir": attempt_dir.resolve(),
            "metric": metric,
            "memory_after": memory_after,
            "research_state_after": research_state_after,
            "checkpoint_after": checkpoint_after,
        }

    def test_prepare_creates_one_verified_journal_before_publication(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = self._fixture(tmp)
            project_dir = fixture["project_dir"]
            run_root = fixture["run_root"]
            before = _snapshot(project_dir, run_root)  # type: ignore[arg-type]

            payload = self._prepare(fixture)

            journal_path = project_dir / ROUND_COMMIT_JOURNAL_NAME  # type: ignore[operator]
            decoded = decode_round_commit_journal(
                read_regular_text(journal_path, anchor=project_dir)  # type: ignore[arg-type]
            )
            self.assertEqual(decoded, payload)
            self.assertEqual(decoded["state"], "prepared")
            self.assertEqual(decoded["run_id"], "run-1")
            self.assertEqual(decoded["round"], 2)
            self.assertEqual(decoded["attempt_id"], "attempt_12345678")
            self.assertFalse(decoded["run_root_identity"]["configured_storage"])
            self.assertEqual(
                json.loads(
                    read_regular_text(
                        fixture["attempt_dir"] / "attempt.json",  # type: ignore[operator]
                        anchor=run_root,  # type: ignore[arg-type]
                    )
                )["state"],
                "active",
            )
            after = _snapshot(project_dir, run_root)  # type: ignore[arg-type]
            self.assertEqual(
                {key: value for key, value in after.items() if not key.endswith(journal_path.name)},
                before,
            )
            with self.assertRaisesRegex(
                RoundCommitRecoveryError,
                "round_commit_journal_exists",
            ):
                self._prepare(fixture)

    def test_runtime_inventory_includes_all_fixed_journals(self) -> None:
        self.assertIn(ROUND_COMMIT_JOURNAL_NAME, PROJECT_RUNTIME_FILE_NAMES)
        self.assertIn(RUN_FINALIZE_JOURNAL_NAME, PROJECT_RUNTIME_FILE_NAMES)
        self.assertIn(DIAGNOSTIC_FINALIZE_JOURNAL_NAME, PROJECT_RUNTIME_FILE_NAMES)

    def test_prepare_accepts_safe_configured_storage_checkpoint_alias(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = self._fixture(tmp, external_storage=True)
            project_dir = fixture["project_dir"]
            alias_run_root = project_dir / "runs" / "run-1"  # type: ignore[operator]
            write_json_file(
                project_dir / "checkpoint.json",  # type: ignore[operator]
                {
                    "run_id": "run-1",
                    "run_root": str(alias_run_root),
                    "last_completed_round": 1,
                    "best_score": 50.0,
                    "can_resume": True,
                },
                anchor=project_dir,  # type: ignore[arg-type]
            )
            checkpoint_value = dict(fixture["checkpoint_after"].value)  # type: ignore[union-attr]
            checkpoint_value["run_root"] = str(alias_run_root)
            fixture["checkpoint_after"] = build_checkpoint_after_image(checkpoint_value)

            payload = self._prepare(fixture)

            self.assertEqual(payload["run_root"], str(fixture["run_root"]))

    def test_first_round_replaces_prior_run_history_without_creating_best_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = self._first_round_fixture(tmp)
            payload = prepare_round_commit(
                project_dir=fixture["project_dir"],  # type: ignore[arg-type]
                run_root=fixture["run_root"],  # type: ignore[arg-type]
                attempt_dir=fixture["attempt_dir"],  # type: ignore[arg-type]
                round_metric=fixture["metric"],  # type: ignore[arg-type]
                best_output_write=False,
                memory_after=fixture["memory_after"],  # type: ignore[arg-type]
                research_state_after=fixture["research_state_after"],  # type: ignore[arg-type]
                checkpoint_after=fixture["checkpoint_after"],  # type: ignore[arg-type]
                transaction_id="txn_87654321",
            )

            best_record = payload["artifacts"]["best_output"]  # type: ignore[index]
            self.assertFalse(best_record["write"])
            self.assertFalse(best_record["before_present"])
            self.assertEqual(
                recover_round_commit(
                    fixture["project_dir"]  # type: ignore[arg-type]
                ).status,
                "recovered",
            )
            self.assertFalse(
                (
                    fixture["project_dir"] / "best_output.md"  # type: ignore[operator]
                ).exists()
            )
            expected_history = [fixture["metric"]]
            self.assertEqual(
                json.loads(
                    read_regular_text(
                        fixture["project_dir"] / "score_history.json",  # type: ignore[operator]
                        anchor=fixture["project_dir"],  # type: ignore[arg-type]
                    )
                ),
                expected_history,
            )
            self.assertEqual(
                json.loads(
                    read_regular_text(
                        fixture["run_root"] / "round_metrics.json",  # type: ignore[operator]
                        anchor=fixture["run_root"],  # type: ignore[arg-type]
                    )
                ),
                expected_history,
            )

    def test_dry_run_classification_is_read_only_and_path_redacted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = self._fixture(tmp, external_storage=True)
            payload = self._prepare(fixture)
            self.assertTrue(payload["run_root_identity"]["configured_storage"])
            before = _snapshot(
                fixture["project_dir"],  # type: ignore[arg-type]
                fixture["run_root"],  # type: ignore[arg-type]
            )

            inspection = classify_round_commit_recovery(
                fixture["project_dir"]  # type: ignore[arg-type]
            )

            self.assertEqual(inspection.status, "prepared")
            self.assertTrue(inspection.can_recover)
            self.assertEqual(inspection.attempt_state, "active")
            self.assertEqual(
                dict(inspection.artifact_states),
                {
                    "score_history": "before",
                    "round_metrics": "before",
                    "best_output": "before",
                    "memory": "before",
                    "research_state": "before",
                    "checkpoint": "before",
                },
            )
            self.assertNotIn(tmp, inspection.blocked_reason or "")
            self.assertEqual(
                _snapshot(
                    fixture["project_dir"],  # type: ignore[arg-type]
                    fixture["run_root"],  # type: ignore[arg-type]
                ),
                before,
            )

    def test_recovery_publishes_and_applies_each_artifact_exactly_once(self) -> None:
        for external_storage in (False, True):
            with self.subTest(external_storage=external_storage):
                with tempfile.TemporaryDirectory() as tmp:
                    fixture = self._fixture(
                        tmp,
                        external_storage=external_storage,
                    )
                    payload = self._prepare(fixture)

                    result = recover_round_commit(
                        fixture["project_dir"]  # type: ignore[arg-type]
                    )

                    self.assertEqual(result.status, "recovered")
                    self.assertFalse(
                        (
                            fixture["project_dir"] / ROUND_COMMIT_JOURNAL_NAME  # type: ignore[operator]
                        ).exists()
                    )
                    run_root = fixture["run_root"]
                    canonical = run_root / "round_02"  # type: ignore[operator]
                    self.assertEqual(
                        sorted(path.name for path in canonical.iterdir()),
                        [
                            "01_draft.md",
                            "02_review.md",
                            "03_revised.md",
                            "04_judge.md",
                        ],
                    )
                    self.assertEqual(
                        json.loads(
                            read_regular_text(
                                fixture["attempt_dir"] / "attempt.json",  # type: ignore[operator]
                                anchor=run_root,  # type: ignore[arg-type]
                            )
                        )["state"],
                        "published",
                    )
                    for history_path in (
                        fixture["score_history_path"],
                        fixture["round_metrics_path"],
                    ):
                        history = json.loads(
                            read_regular_text(history_path)  # type: ignore[arg-type]
                        )
                        self.assertEqual([item["round"] for item in history], [1, 2])
                        self.assertEqual(history[1], fixture["metric"])
                    self.assertEqual(
                        _sha256(
                            read_regular_text(
                                fixture["project_dir"] / "memory.md",  # type: ignore[operator]
                                anchor=fixture["project_dir"],  # type: ignore[arg-type]
                            )
                        ),
                        payload["artifacts"]["memory"]["after_sha256"],  # type: ignore[index]
                    )
                    self.assertEqual(
                        json.loads(
                            read_regular_text(
                                fixture["project_dir"] / "checkpoint.json",  # type: ignore[operator]
                                anchor=fixture["project_dir"],  # type: ignore[arg-type]
                            )
                        )["last_completed_round"],
                        2,
                    )
                    second = recover_round_commit(
                        fixture["project_dir"]  # type: ignore[arg-type]
                    )
                    self.assertEqual(second.status, "absent")

    def test_recovery_resumes_ready_and_published_attempts(self) -> None:
        transitions = ("ready_to_publish", "published")
        for target_state in transitions:
            with self.subTest(target_state=target_state):
                with tempfile.TemporaryDirectory() as tmp:
                    fixture = self._fixture(tmp)
                    self._prepare(fixture)
                    mark_attempt_ready_to_publish(
                        fixture["attempt_dir"]  # type: ignore[arg-type]
                    )
                    if target_state == "published":
                        publish_attempt(fixture["attempt_dir"])  # type: ignore[arg-type]

                    inspection = classify_round_commit_recovery(
                        fixture["project_dir"]  # type: ignore[arg-type]
                    )
                    self.assertEqual(inspection.attempt_state, target_state)

                    self.assertEqual(
                        recover_round_commit(
                            fixture["project_dir"]  # type: ignore[arg-type]
                        ).status,
                        "recovered",
                    )

    def test_prepare_create_faults_preserve_a_recoverable_boundary(self) -> None:
        for external_storage in (False, True):
            for phase in ("before", "after"):
                for error_type in (OSError, KeyboardInterrupt):
                    with self.subTest(
                        external_storage=external_storage,
                        phase=phase,
                        error_type=error_type.__name__,
                    ):
                        with tempfile.TemporaryDirectory() as tmp:
                            fixture = self._fixture(
                                tmp,
                                external_storage=external_storage,
                            )

                            def fail_create(
                                path: Path,
                                content: str,
                                **kwargs: object,
                            ) -> None:
                                if phase == "after":
                                    write_file_text_create_only(path, content, **kwargs)
                                raise error_type("injected journal create failure")

                            with (
                                patch(
                                    "src.round_commit_recovery.write_file_text_create_only",
                                    side_effect=fail_create,
                                ),
                                self.assertRaises(error_type),
                            ):
                                self._prepare(fixture)

                            journal_path = (
                                fixture["project_dir"] / ROUND_COMMIT_JOURNAL_NAME  # type: ignore[operator]
                            )
                            self.assertEqual(journal_path.exists(), phase == "after")
                            if phase == "before":
                                self._prepare(fixture)
                            self.assertEqual(
                                recover_round_commit(
                                    fixture["project_dir"]  # type: ignore[arg-type]
                                ).status,
                                "recovered",
                            )

    def test_publication_faults_resume_before_and_after_each_boundary(self) -> None:
        operations = {
            "mark": mark_attempt_ready_to_publish,
            "publish": publish_attempt,
        }
        for external_storage in (False, True):
            for operation_name, original_operation in operations.items():
                for phase in ("before", "after"):
                    for error_type in (OSError, RuntimeError, KeyboardInterrupt):
                        with self.subTest(
                            external_storage=external_storage,
                            operation=operation_name,
                            phase=phase,
                            error_type=error_type.__name__,
                        ):
                            with tempfile.TemporaryDirectory() as tmp:
                                fixture = self._fixture(
                                    tmp,
                                    external_storage=external_storage,
                                )
                                self._prepare(fixture)

                                def fail_operation(attempt_dir: Path) -> None:
                                    if phase == "after":
                                        original_operation(attempt_dir)
                                    raise error_type(f"injected {tmp} publication failure")

                                with (
                                    patch(
                                        f"src.round_commit_recovery.{operation_name}_attempt_"
                                        + (
                                            "ready_to_publish"
                                            if operation_name == "mark"
                                            else "publish"
                                        ),
                                        side_effect=fail_operation,
                                    )
                                    if operation_name == "mark"
                                    else patch(
                                        "src.round_commit_recovery.publish_attempt",
                                        side_effect=fail_operation,
                                    ),
                                    self.assertRaises(error_type) as raised,
                                ):
                                    recover_round_commit(
                                        fixture["project_dir"]  # type: ignore[arg-type]
                                    )

                                if error_type is not KeyboardInterrupt:
                                    self.assertNotIn(tmp, str(raised.exception))
                                    rendered = "".join(
                                        traceback.format_exception(
                                            type(raised.exception),
                                            raised.exception,
                                            raised.exception.__traceback__,
                                        )
                                    )
                                    self.assertNotIn(tmp, rendered)
                                inspection = classify_round_commit_recovery(
                                    fixture["project_dir"]  # type: ignore[arg-type]
                                )
                                self.assertTrue(inspection.can_recover)
                                self.assertEqual(
                                    dict(inspection.artifact_states)["checkpoint"],
                                    "before",
                                )
                                self.assertEqual(
                                    recover_round_commit(
                                        fixture["project_dir"]  # type: ignore[arg-type]
                                    ).status,
                                    "recovered",
                                )

    def test_same_process_journal_change_blocks_the_next_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = self._fixture(tmp)
            self._prepare(fixture)
            project_dir = fixture["project_dir"]
            journal_path = project_dir / ROUND_COMMIT_JOURNAL_NAME  # type: ignore[operator]
            original_journal = read_regular_text(
                journal_path,
                anchor=project_dir,  # type: ignore[arg-type]
            )
            original_apply = round_commit_recovery_module._apply_artifact
            changed = False

            def change_after_first_apply(
                context: object,
                artifact_name: str,
            ) -> None:
                nonlocal changed
                original_apply(context, artifact_name)  # type: ignore[arg-type]
                if not changed:
                    changed = True
                    journal_path.write_text(
                        original_journal.replace(
                            "txn_12345678",
                            "txn_87654321",
                        ),
                        encoding="utf-8",
                    )

            with (
                patch.object(
                    round_commit_recovery_module,
                    "_apply_artifact",
                    side_effect=change_after_first_apply,
                ),
                self.assertRaisesRegex(
                    RoundCommitRecoveryError,
                    "round_commit_journal_changed",
                ),
            ):
                recover_round_commit(project_dir)  # type: ignore[arg-type]

            self.assertTrue(changed)
            self.assertEqual(
                dict(
                    classify_round_commit_recovery(
                        project_dir  # type: ignore[arg-type]
                    ).artifact_states
                )["score_history"],
                "before",
            )
            journal_path.write_text(original_journal, encoding="utf-8")
            self.assertEqual(
                recover_round_commit(project_dir).status,  # type: ignore[arg-type]
                "recovered",
            )

    def test_artifact_faults_leave_journal_and_retry_rolls_forward(self) -> None:
        artifact_files = {
            "best_output": "best_output.md",
            "score_history": "score_history.json",
            "round_metrics": "round_metrics.json",
            "memory": "memory.md",
            "research_state": "research_state.json",
            "checkpoint": "checkpoint.json",
        }
        for external_storage in (False, True):
            for artifact_name, file_name in artifact_files.items():
                for phase in ("before", "after"):
                    for error_type in (OSError, KeyboardInterrupt):
                        with self.subTest(
                            external_storage=external_storage,
                            artifact=artifact_name,
                            phase=phase,
                            error_type=error_type.__name__,
                        ):
                            with tempfile.TemporaryDirectory() as tmp:
                                fixture = self._fixture(
                                    tmp,
                                    external_storage=external_storage,
                                )
                                self._prepare(fixture)
                                original_write = write_file_text

                                def fail_artifact(
                                    path: Path,
                                    content: str,
                                    **kwargs: object,
                                ) -> None:
                                    if path.name != file_name:
                                        original_write(path, content, **kwargs)
                                        return
                                    if phase == "after":
                                        original_write(path, content, **kwargs)
                                    raise error_type(f"injected {tmp} artifact failure")

                                with (
                                    patch(
                                        "src.round_commit_recovery.write_file_text",
                                        side_effect=fail_artifact,
                                    ),
                                    self.assertRaises(error_type) as raised,
                                ):
                                    recover_round_commit(
                                        fixture["project_dir"]  # type: ignore[arg-type]
                                    )

                                if error_type is not KeyboardInterrupt:
                                    self.assertNotIn(tmp, str(raised.exception))
                                self.assertTrue(
                                    (
                                        fixture["project_dir"] / ROUND_COMMIT_JOURNAL_NAME  # type: ignore[operator]
                                    ).is_file()
                                )
                                inspection = classify_round_commit_recovery(
                                    fixture["project_dir"]  # type: ignore[arg-type]
                                )
                                states = dict(inspection.artifact_states)
                                self.assertEqual(
                                    states[artifact_name],
                                    "after" if phase == "after" else "before",
                                )
                                self.assertEqual(
                                    states["checkpoint"],
                                    (
                                        "after"
                                        if artifact_name == "checkpoint" and phase == "after"
                                        else "before"
                                    ),
                                )

                                self.assertEqual(
                                    recover_round_commit(
                                        fixture["project_dir"]  # type: ignore[arg-type]
                                    ).status,
                                    "recovered",
                                )
                                for history_path in (
                                    fixture["score_history_path"],
                                    fixture["round_metrics_path"],
                                ):
                                    history = json.loads(
                                        read_regular_text(
                                            history_path  # type: ignore[arg-type]
                                        )
                                    )
                                    self.assertEqual(
                                        [item["round"] for item in history],
                                        [1, 2],
                                    )

    def test_conflict_blocks_all_writes_and_does_not_disclose_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = self._fixture(tmp)
            self._prepare(fixture)
            memory_path = fixture["project_dir"] / "memory.md"  # type: ignore[operator]
            write_file_text(
                memory_path,
                "manual third generation\n",
                anchor=fixture["project_dir"],  # type: ignore[arg-type]
            )
            before = _snapshot(
                fixture["project_dir"],  # type: ignore[arg-type]
                fixture["run_root"],  # type: ignore[arg-type]
            )

            inspection = classify_round_commit_recovery(
                fixture["project_dir"]  # type: ignore[arg-type]
            )

            self.assertEqual(inspection.status, "conflict")
            self.assertFalse(inspection.can_recover)
            self.assertEqual(inspection.blocked_reason, "artifact_conflict:memory")
            with self.assertRaises(RoundCommitRecoveryError) as raised:
                recover_round_commit(
                    fixture["project_dir"]  # type: ignore[arg-type]
                )
            self.assertNotIn(tmp, str(raised.exception))
            self.assertEqual(
                _snapshot(
                    fixture["project_dir"],  # type: ignore[arg-type]
                    fixture["run_root"],  # type: ignore[arg-type]
                ),
                before,
            )

    def test_missing_before_generation_is_a_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = self._fixture(tmp)
            self._prepare(fixture)
            unlink_artifact_file(
                fixture["project_dir"] / "research_state.json",  # type: ignore[operator]
                missing_ok=False,
                anchor=fixture["project_dir"],  # type: ignore[arg-type]
            )

            inspection = classify_round_commit_recovery(
                fixture["project_dir"]  # type: ignore[arg-type]
            )

            self.assertEqual(inspection.status, "conflict")
            self.assertEqual(
                inspection.blocked_reason,
                "artifact_conflict:research_state",
            )

    def test_invalid_oversized_and_unsafe_journals_fail_closed(self) -> None:
        cases = ("invalid", "oversized", "symlink", "hardlink", "valid_hardlink")
        for case in cases:
            with self.subTest(case=case):
                with tempfile.TemporaryDirectory() as tmp:
                    fixture = self._fixture(tmp)
                    project_dir = fixture["project_dir"]
                    journal_path = project_dir / ROUND_COMMIT_JOURNAL_NAME  # type: ignore[operator]
                    if case == "invalid":
                        write_file_text_create_only(
                            journal_path,
                            '{"schema_version": 1}',
                            anchor=project_dir,  # type: ignore[arg-type]
                        )
                    elif case == "oversized":
                        journal_path.write_bytes(b" " * (MAX_ROUND_COMMIT_JOURNAL_BYTES + 1))
                    elif case == "symlink":
                        target = Path(tmp) / "private-journal"
                        target.write_text("{}", encoding="utf-8")
                        journal_path.symlink_to(target)
                    elif case == "hardlink":
                        target = Path(tmp) / "private-journal"
                        target.write_text("{}", encoding="utf-8")
                        os.link(target, journal_path)
                    else:
                        payload = self._prepare(fixture)
                        journal_text = json.dumps(payload, indent=2)
                        journal_path.unlink()
                        target = Path(tmp) / "private-journal"
                        target.write_text(journal_text, encoding="utf-8")
                        os.link(target, journal_path)
                    before = _snapshot(
                        project_dir,  # type: ignore[arg-type]
                        fixture["run_root"],  # type: ignore[arg-type]
                    )

                    inspection = classify_round_commit_recovery(
                        project_dir  # type: ignore[arg-type]
                    )

                    self.assertIn(inspection.status, {"invalid", "conflict"})
                    self.assertFalse(inspection.can_recover)
                    self.assertNotIn(tmp, inspection.blocked_reason or "")
                    self.assertEqual(
                        _snapshot(
                            project_dir,  # type: ignore[arg-type]
                            fixture["run_root"],  # type: ignore[arg-type]
                        ),
                        before,
                    )

    def test_changed_config_and_moved_external_storage_fail_closed(self) -> None:
        for case in ("config", "storage"):
            with self.subTest(case=case):
                with tempfile.TemporaryDirectory() as tmp:
                    fixture = self._fixture(tmp, external_storage=True)
                    self._prepare(fixture)
                    if case == "config":
                        write_json_file(
                            fixture["run_root"] / "run_config.json",  # type: ignore[operator]
                            {"run_id": "run-1", "status": "changed"},
                            anchor=fixture["run_root"],  # type: ignore[arg-type]
                        )
                    else:
                        project_dir = fixture["project_dir"]
                        (project_dir / "runs").unlink()  # type: ignore[operator]
                        replacement = Path(tmp) / "replacement-runs"
                        replacement.mkdir()
                        (project_dir / "runs").symlink_to(  # type: ignore[operator]
                            replacement,
                            target_is_directory=True,
                        )

                    inspection = classify_round_commit_recovery(
                        fixture["project_dir"]  # type: ignore[arg-type]
                    )

                    self.assertEqual(inspection.status, "conflict")
                    self.assertFalse(inspection.can_recover)
                    self.assertNotIn(tmp, inspection.blocked_reason or "")

    def test_cleanup_faults_do_not_reapply_a_fully_committed_round(self) -> None:
        original_unlink = round_commit_recovery_module.unlink_artifact_file_if_matches
        for external_storage in (False, True):
            for phase in ("before", "after"):
                for error_type in (OSError, KeyboardInterrupt):
                    with self.subTest(
                        external_storage=external_storage,
                        phase=phase,
                        error_type=error_type.__name__,
                    ):
                        with tempfile.TemporaryDirectory() as tmp:
                            fixture = self._fixture(
                                tmp,
                                external_storage=external_storage,
                            )
                            self._prepare(fixture)

                            def fail_cleanup(
                                path: Path,
                                expected_content: str,
                                **kwargs: object,
                            ) -> None:
                                if phase == "after":
                                    original_unlink(path, expected_content, **kwargs)
                                raise error_type(f"injected {tmp} cleanup failure")

                            with (
                                patch.object(
                                    round_commit_recovery_module,
                                    "unlink_artifact_file_if_matches",
                                    side_effect=fail_cleanup,
                                ),
                                self.assertRaises(error_type) as raised,
                            ):
                                recover_round_commit(
                                    fixture["project_dir"]  # type: ignore[arg-type]
                                )

                            if error_type is not KeyboardInterrupt:
                                self.assertNotIn(tmp, str(raised.exception))
                            inspection = classify_round_commit_recovery(
                                fixture["project_dir"]  # type: ignore[arg-type]
                            )
                            self.assertEqual(
                                inspection.status,
                                "absent" if phase == "after" else "complete",
                            )
                            before = _snapshot(
                                fixture["project_dir"],  # type: ignore[arg-type]
                                fixture["run_root"],  # type: ignore[arg-type]
                            )

                            retry = recover_round_commit(
                                fixture["project_dir"]  # type: ignore[arg-type]
                            )
                            self.assertEqual(
                                retry.status,
                                "absent" if phase == "after" else "recovered",
                            )
                            after = _snapshot(
                                fixture["project_dir"],  # type: ignore[arg-type]
                                fixture["run_root"],  # type: ignore[arg-type]
                            )
                            journal_suffix = f":{ROUND_COMMIT_JOURNAL_NAME}"
                            self.assertEqual(
                                {
                                    key: value
                                    for key, value in before.items()
                                    if not key.endswith(journal_suffix)
                                },
                                after,
                            )


if __name__ == "__main__":
    unittest.main()
