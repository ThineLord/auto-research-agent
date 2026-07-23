from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rich.console import Console

import src.round_commit_recovery as round_commit_recovery_module
import src.runner as runner_module
from src.round_commit_recovery import (
    ROUND_COMMIT_JOURNAL_NAME,
    RoundCommitRecoveryIOError,
    recover_round_commit,
)


class _FakeLLM:
    timeout_seconds = 300


class _FakeAgents:
    def __init__(self, score: int = 70) -> None:
        self.llm = _FakeLLM()
        self.score = score

    def draft(
        self,
        *,
        task: str,
        memory: str,
        round_index: int,
        previous_best: str,
        previous_judge: str,
        drafting_mode: str = "best_guided",
        previous_review: str = "",
        previous_draft: str = "",
        previous_revised: str = "",
    ) -> str:
        return f"Draft round {round_index}: {task}"

    def review(self, *, task: str, memory: str, draft_output: str) -> str:
        return f"Review of {draft_output}"

    def revise(
        self,
        *,
        task: str,
        memory: str,
        draft_output: str,
        review_output: str,
    ) -> str:
        return f"Revised {draft_output}"

    def judge(self, *, task: str, memory: str, revised_output: str) -> str:
        return json.dumps(
            {
                "score": self.score,
                "rubric": {
                    "novelty_and_research_value": 14,
                    "technical_clarity_and_correctness": 14,
                    "feasibility_and_implementation_realism": 14,
                    "evaluation_design_quality": 14,
                    "tomorrow_actionability": 14,
                },
                "reasons": ["The round is complete."],
                "blockers": [],
                "next_step": "CONTINUE",
            }
        )


def _run_one_round(project_dir: Path, *, repo_root: Path) -> dict[str, object]:
    return runner_module.run_iterative_rounds(
        console=Console(),
        agents=_FakeAgents(),
        task_text="Design a bounded memory adapter.",
        project_dir=project_dir,
        memory_path=project_dir / "memory.md",
        mode="test",
        model_name="fake-model",
        max_rounds=1,
        stop_if_no_improvement_rounds=10,
        global_max_runtime_seconds=60,
        per_agent_timeout_seconds=300,
        repo_root=repo_root,
    )


class RoundCommitRunnerTests(unittest.TestCase):
    def _project(
        self,
        root: Path,
        *,
        external_storage: bool,
    ) -> tuple[Path, Path]:
        project_dir = root / "project"
        project_dir.mkdir()
        (project_dir / "memory.md").write_text("Manual memory.\n", encoding="utf-8")
        if external_storage:
            runs_root = root / "external-runs"
            runs_root.mkdir()
            (project_dir / "runs").symlink_to(runs_root, target_is_directory=True)
        else:
            runs_root = project_dir / "runs"
        return project_dir, runs_root

    def test_successful_round_prepares_before_engine_publication(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir, _ = self._project(root, external_storage=False)
            events: list[str] = []
            real_prepare = round_commit_recovery_module.prepare_round_commit
            real_recover = round_commit_recovery_module.recover_round_commit
            real_mark_ready = round_commit_recovery_module.mark_attempt_ready_to_publish
            real_publish = round_commit_recovery_module.publish_attempt

            def prepare(**kwargs: object) -> dict[str, object]:
                events.append("prepare")
                prepared = real_prepare(**kwargs)  # type: ignore[arg-type]
                self.assertTrue((project_dir / ROUND_COMMIT_JOURNAL_NAME).is_file())
                return prepared

            def recover(selected_project_dir: Path) -> object:
                events.append("recover")
                return real_recover(selected_project_dir)

            def mark_ready(attempt_dir: Path) -> None:
                events.append("ready")
                self.assertTrue((project_dir / ROUND_COMMIT_JOURNAL_NAME).is_file())
                real_mark_ready(attempt_dir)

            def publish(attempt_dir: Path) -> Path:
                events.append("publish")
                self.assertTrue((project_dir / ROUND_COMMIT_JOURNAL_NAME).is_file())
                return real_publish(attempt_dir)

            legacy_write = AssertionError("runner used a legacy round-commit writer")
            with (
                patch.object(runner_module, "prepare_round_commit", side_effect=prepare),
                patch.object(runner_module, "recover_round_commit", side_effect=recover),
                patch.object(
                    round_commit_recovery_module,
                    "mark_attempt_ready_to_publish",
                    side_effect=mark_ready,
                ),
                patch.object(
                    round_commit_recovery_module,
                    "publish_attempt",
                    side_effect=publish,
                ),
                patch.object(
                    runner_module,
                    "mark_attempt_ready_to_publish",
                    side_effect=legacy_write,
                ),
                patch.object(runner_module, "publish_attempt", side_effect=legacy_write),
                patch.object(runner_module, "write_text", side_effect=legacy_write),
                patch.object(runner_module, "write_score_history", side_effect=legacy_write),
                patch.object(runner_module, "update_project_memory", side_effect=legacy_write),
                patch.object(runner_module, "update_research_state", side_effect=legacy_write),
            ):
                result = _run_one_round(project_dir, repo_root=root)

            self.assertEqual(events, ["prepare", "recover", "ready", "publish"])
            self.assertFalse((project_dir / ROUND_COMMIT_JOURNAL_NAME).exists())
            self.assertEqual(result["completed_rounds"], 1)
            self.assertEqual(
                json.loads((project_dir / "score_history.json").read_text(encoding="utf-8"))[0][
                    "round"
                ],
                1,
            )

    def test_interrupted_second_history_write_recovers_without_duplicates(self) -> None:
        for external_storage, fault_type, expected_type in (
            (external, fault, RoundCommitRecoveryIOError if fault is OSError else KeyboardInterrupt)
            for external in (False, True)
            for fault in (OSError, KeyboardInterrupt)
        ):
            with (
                self.subTest(
                    external_storage=external_storage,
                    fault_type=fault_type.__name__,
                ),
                tempfile.TemporaryDirectory() as tmp,
            ):
                root = Path(tmp)
                project_dir, runs_root = self._project(
                    root,
                    external_storage=external_storage,
                )
                real_write = round_commit_recovery_module.write_file_text
                failed = False

                def fail_round_metrics_once(
                    path: Path,
                    content: str,
                    *,
                    anchor: Path | None = None,
                ) -> None:
                    nonlocal failed
                    if path.name == "round_metrics.json" and not failed:
                        failed = True
                        raise fault_type("injected second-history failure")
                    real_write(path, content, anchor=anchor)

                with patch.object(
                    round_commit_recovery_module,
                    "write_file_text",
                    side_effect=fail_round_metrics_once,
                ):
                    with self.assertRaises(expected_type):
                        _run_one_round(project_dir, repo_root=root)

                self.assertTrue(failed)
                self.assertTrue((project_dir / ROUND_COMMIT_JOURNAL_NAME).is_file())
                run_root = next(path for path in runs_root.iterdir() if path.is_dir())
                self.assertTrue((run_root / "round_01").is_dir())
                self.assertFalse((run_root / "run_summary.json").exists())

                recovered = recover_round_commit(project_dir)
                self.assertEqual(recovered.status, "recovered")
                self.assertEqual(recover_round_commit(project_dir).status, "absent")
                self.assertFalse((project_dir / ROUND_COMMIT_JOURNAL_NAME).exists())

                project_history = json.loads(
                    (project_dir / "score_history.json").read_text(encoding="utf-8")
                )
                run_history = json.loads(
                    (run_root / "round_metrics.json").read_text(encoding="utf-8")
                )
                self.assertEqual([entry["round"] for entry in project_history], [1])
                self.assertEqual(project_history, run_history)
                checkpoint = json.loads(
                    (project_dir / "checkpoint.json").read_text(encoding="utf-8")
                )
                self.assertEqual(checkpoint["last_completed_round"], 1)
                self.assertTrue((project_dir / "best_output.md").is_file())
                self.assertTrue((project_dir / "research_state.json").is_file())

    def test_complete_legacy_fallback_transitions_next_round_to_transaction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir, runs_root = self._project(root, external_storage=False)
            run_root = runs_root / "legacy-run"
            previous_round = run_root / "round_01"
            previous_round.mkdir(parents=True)
            (previous_round / "04_judge.md").write_text("legacy judge\n", encoding="utf-8")
            (project_dir / "best_output.md").write_text("legacy best\n", encoding="utf-8")
            legacy_entry = {
                "round": 1,
                "score": 70.0,
                "improved": True,
                "successful_research_round": True,
            }
            (project_dir / "score_history.json").write_text(
                json.dumps([legacy_entry]),
                encoding="utf-8",
            )
            prepared_rounds: list[int] = []
            real_prepare = round_commit_recovery_module.prepare_round_commit

            def prepare(**kwargs: object) -> dict[str, object]:
                metric = kwargs["round_metric"]
                self.assertIsInstance(metric, dict)
                prepared_rounds.append(metric["round"])  # type: ignore[index]
                return real_prepare(**kwargs)  # type: ignore[arg-type]

            with patch.object(runner_module, "prepare_round_commit", side_effect=prepare):
                result = runner_module.run_iterative_rounds(
                    console=Console(),
                    agents=_FakeAgents(),
                    task_text="Design a bounded memory adapter.",
                    project_dir=project_dir,
                    memory_path=project_dir / "memory.md",
                    mode="resume",
                    model_name="fake-model",
                    max_rounds=3,
                    start_round=2,
                    run_root_override=run_root,
                    initial_best_score=70.0,
                    stop_if_no_improvement_rounds=10,
                    global_max_runtime_seconds=60,
                    per_agent_timeout_seconds=300,
                    repo_root=root,
                )

            self.assertEqual(prepared_rounds, [3])
            self.assertEqual(result["completed_rounds"], 3)
            project_history = json.loads(
                (project_dir / "score_history.json").read_text(encoding="utf-8")
            )
            run_history = json.loads((run_root / "round_metrics.json").read_text(encoding="utf-8"))
            self.assertEqual([entry["round"] for entry in project_history], [1, 2, 3])
            self.assertEqual(project_history, run_history)
