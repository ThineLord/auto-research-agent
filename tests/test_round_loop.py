from __future__ import annotations

import json
import tempfile
import types
import unittest
from importlib.util import find_spec
from pathlib import Path

if find_spec("rich") is None:
    rich_module = types.ModuleType("rich")
    rich_console_module = types.ModuleType("rich.console")

    class Console:  # type: ignore[no-redef]
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def print(self, *args: object, **kwargs: object) -> None:
            pass

        def rule(self, *args: object, **kwargs: object) -> None:
            pass

    rich_console_module.Console = Console
    import sys

    sys.modules["rich"] = rich_module
    sys.modules["rich.console"] = rich_console_module
else:
    from rich.console import Console

if find_spec("requests") is None:
    requests_module = types.ModuleType("requests")

    class RequestException(Exception):
        pass

    class Timeout(RequestException):
        pass

    requests_module.RequestException = RequestException
    requests_module.Timeout = Timeout

    import sys

    sys.modules["requests"] = requests_module

if find_spec("yaml") is None:
    yaml_module = types.ModuleType("yaml")

    def safe_load(_: object) -> dict[str, object]:
        return {}

    yaml_module.safe_load = safe_load

    import sys

    sys.modules["yaml"] = yaml_module

import src.main as main_module
from src.cli import parse_args
from src.cloud_free import CloudFreeDailyQuotaExhausted
from src.constants import STOP_CLOUD_DAILY_QUOTA, STOP_MAX_ROUNDS, STOP_USER_REQUESTED
from src.resume import run_resume_mode
from src.runner import run_iterative_rounds


class FakeLLM:
    timeout_seconds = 300


class FakeAgents:
    def __init__(self, judge_scores: list[int] | None = None) -> None:
        self.llm = FakeLLM()
        self.judge_scores = list(judge_scores or [50, 40])

    def draft(
        self,
        *,
        task: str,
        memory: str,
        round_index: int,
        previous_best: str,
        previous_judge: str,
    ) -> str:
        return f"Draft round {round_index}: {task[:20]} | previous={bool(previous_best)}"

    def review(self, *, task: str, memory: str, draft_output: str) -> str:
        return f"Review notes for {draft_output}"

    def revise(
        self,
        *,
        task: str,
        memory: str,
        draft_output: str,
        review_output: str,
    ) -> str:
        return f"Revised output from {draft_output}"

    def judge(self, *, task: str, memory: str, revised_output: str) -> str:
        score = self.judge_scores.pop(0)
        return json.dumps(
            {
                "score": score,
                "rubric": {
                    "novelty_and_research_value": 10,
                    "technical_clarity_and_correctness": 10,
                    "feasibility_and_implementation_realism": 10,
                    "evaluation_design_quality": 10,
                    "tomorrow_actionability": 10,
                },
                "reasons": [f"Judge feedback for score {score}."],
                "blockers": ["Needs one more validation pass."],
                "next_step": "CONTINUE",
            }
        )


class QuotaPauseAgents(FakeAgents):
    def draft(
        self,
        *,
        task: str,
        memory: str,
        round_index: int,
        previous_best: str,
        previous_judge: str,
    ) -> str:
        raise CloudFreeDailyQuotaExhausted(
            "Free-tier daily quota likely exhausted; safe to resume after reset."
        )


class StopAfterJudgeAgents(FakeAgents):
    def __init__(self, stop_path: Path, stop_after_judge: int) -> None:
        super().__init__([91, 92, 93, 94])
        self.stop_path = stop_path
        self.stop_after_judge = stop_after_judge
        self.judge_calls = 0

    def judge(self, *, task: str, memory: str, revised_output: str) -> str:
        output = super().judge(task=task, memory=memory, revised_output=revised_output)
        self.judge_calls += 1
        if self.judge_calls == self.stop_after_judge:
            self.stop_path.write_text("STOP_REQUESTED\n", encoding="utf-8")
        return output


class StopAfterDraftAgents(FakeAgents):
    def __init__(self, stop_path: Path, stop_after_draft: int) -> None:
        super().__init__([88, 77])
        self.stop_path = stop_path
        self.stop_after_draft = stop_after_draft
        self.draft_calls = 0

    def draft(
        self,
        *,
        task: str,
        memory: str,
        round_index: int,
        previous_best: str,
        previous_judge: str,
    ) -> str:
        output = super().draft(
            task=task,
            memory=memory,
            round_index=round_index,
            previous_best=previous_best,
            previous_judge=previous_judge,
        )
        self.draft_calls += 1
        if self.draft_calls == self.stop_after_draft:
            self.stop_path.write_text("STOP_REQUESTED\n", encoding="utf-8")
        return output


class RecordingAgents(FakeAgents):
    def __init__(self) -> None:
        super().__init__([64])
        self.draft_rounds: list[int] = []

    def draft(
        self,
        *,
        task: str,
        memory: str,
        round_index: int,
        previous_best: str,
        previous_judge: str,
    ) -> str:
        self.draft_rounds.append(round_index)
        return super().draft(
            task=task,
            memory=memory,
            round_index=round_index,
            previous_best=previous_best,
            previous_judge=previous_judge,
        )


class RoundLoopTests(unittest.TestCase):
    def test_main_reexports_backward_compatible_api(self) -> None:
        self.assertIs(main_module.run_iterative_rounds, run_iterative_rounds)
        self.assertEqual(main_module.STOP_MAX_ROUNDS, STOP_MAX_ROUNDS)
        self.assertTrue(callable(main_module.parse_args))
        self.assertTrue(callable(main_module.run_diagnostic_mode))
        self.assertTrue(callable(main_module.run_session_mode))

    def test_parse_args_accepts_mode_and_model_flags(self) -> None:
        args = parse_args(["--diagnostic", "--model", "llama3.1:8b"])

        self.assertTrue(args.diagnostic)
        self.assertEqual(args.model, "llama3.1:8b")

    def test_round_loop_writes_outputs_and_keeps_best_score(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "project"
            project_dir.mkdir()
            memory_path = project_dir / "memory.md"
            memory_path.write_text("Manual memory.\n", encoding="utf-8")

            result = run_iterative_rounds(
                console=Console(),
                agents=FakeAgents(),
                task_text="Design a privacy-aware memory adapter.",
                project_dir=project_dir,
                memory_path=memory_path,
                mode="test",
                model_name="fake-model",
                max_rounds=2,
                stop_if_no_improvement_rounds=10,
                global_max_runtime_seconds=60,
                per_agent_timeout_seconds=300,
            )

            run_root = Path(result["run_root"])
            self.assertEqual(result["completed_rounds"], 2)
            self.assertEqual(result["best_round"], 1)
            self.assertEqual(result["best_score"], 50)
            self.assertEqual(result["stop_reason"], STOP_MAX_ROUNDS)

            for round_index in (1, 2):
                round_dir = run_root / f"round_{round_index:02d}"
                self.assertTrue((round_dir / "01_draft.md").exists())
                self.assertTrue((round_dir / "02_review.md").exists())
                self.assertTrue((round_dir / "03_revised.md").exists())
                self.assertTrue((round_dir / "04_judge.md").exists())

            best_output = (project_dir / "best_output.md").read_text(encoding="utf-8")
            self.assertIn("Draft round 1", best_output)
            self.assertNotIn("Draft round 2", best_output)

            score_history = (project_dir / "score_history.json").read_text(encoding="utf-8")
            self.assertIn('"score": 50.0', score_history)
            self.assertIn('"score": 40.0', score_history)

    def test_round_loop_checkpoints_resumable_cloud_quota_pause(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "project"
            project_dir.mkdir()
            memory_path = project_dir / "memory.md"
            memory_path.write_text("Manual memory.\n", encoding="utf-8")

            result = run_iterative_rounds(
                console=Console(),
                agents=QuotaPauseAgents(),
                task_text="Design a privacy-aware memory adapter.",
                project_dir=project_dir,
                memory_path=memory_path,
                mode="continuous",
                model_name="gemini:gemini-3.5-flash",
                max_rounds=2,
                stop_if_no_improvement_rounds=10,
                global_max_runtime_seconds=60,
                per_agent_timeout_seconds=300,
            )

            checkpoint = json.loads((project_dir / "checkpoint.json").read_text(encoding="utf-8"))
            self.assertEqual(result["stop_reason"], STOP_CLOUD_DAILY_QUOTA)
            self.assertEqual(checkpoint["stop_reason"], STOP_CLOUD_DAILY_QUOTA)
            self.assertTrue(checkpoint["can_resume"])
            self.assertTrue(checkpoint["paused_until_reset"])
            self.assertEqual(checkpoint["last_completed_round"], 0)

    def test_stop_after_requested_rounds_keeps_exact_completed_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "project"
            project_dir.mkdir()
            memory_path = project_dir / "memory.md"
            memory_path.write_text("Manual memory.\n", encoding="utf-8")
            stop_path = project_dir / "STOP_REQUESTED"

            result = run_iterative_rounds(
                console=Console(),
                agents=StopAfterJudgeAgents(stop_path, stop_after_judge=3),
                task_text="Design a privacy-aware memory adapter.",
                project_dir=project_dir,
                memory_path=memory_path,
                mode="test",
                model_name="fake-model",
                max_rounds=5,
                stop_if_no_improvement_rounds=10,
                global_max_runtime_seconds=60,
                per_agent_timeout_seconds=300,
            )

            run_root = Path(result["run_root"])
            checkpoint = json.loads((project_dir / "checkpoint.json").read_text(encoding="utf-8"))
            score_history = json.loads(
                (project_dir / "score_history.json").read_text(encoding="utf-8")
            )

            self.assertEqual(result["completed_rounds"], 3)
            self.assertEqual(result["stop_reason"], STOP_USER_REQUESTED)
            self.assertEqual(checkpoint["last_completed_round"], 3)
            self.assertEqual([entry["round"] for entry in score_history], [1, 2, 3])
            self.assertEqual([entry["score"] for entry in score_history], [91.0, 92.0, 93.0])
            self.assertFalse((run_root / "round_04").exists())

    def test_stopped_partial_round_does_not_append_zero_score_or_advance_checkpoint(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "project"
            project_dir.mkdir()
            memory_path = project_dir / "memory.md"
            memory_path.write_text("Manual memory.\n", encoding="utf-8")
            stop_path = project_dir / "STOP_REQUESTED"

            result = run_iterative_rounds(
                console=Console(),
                agents=StopAfterDraftAgents(stop_path, stop_after_draft=2),
                task_text="Design a privacy-aware memory adapter.",
                project_dir=project_dir,
                memory_path=memory_path,
                mode="test",
                model_name="fake-model",
                max_rounds=5,
                stop_if_no_improvement_rounds=10,
                global_max_runtime_seconds=60,
                per_agent_timeout_seconds=300,
            )

            run_root = Path(result["run_root"])
            checkpoint = json.loads((project_dir / "checkpoint.json").read_text(encoding="utf-8"))
            score_history = json.loads(
                (project_dir / "score_history.json").read_text(encoding="utf-8")
            )

            self.assertEqual(result["completed_rounds"], 1)
            self.assertEqual(result["stop_reason"], STOP_USER_REQUESTED)
            self.assertEqual(checkpoint["last_completed_round"], 1)
            self.assertEqual([entry["round"] for entry in score_history], [1])
            self.assertEqual([entry["score"] for entry in score_history], [88.0])
            self.assertNotIn(0.0, [entry["score"] for entry in score_history])
            self.assertTrue((run_root / "round_02").exists())
            self.assertIn(
                "Judge skipped",
                (run_root / "round_02" / "04_judge.md").read_text(encoding="utf-8"),
            )

    def test_resume_starts_after_last_real_completed_round(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "project"
            project_dir.mkdir()
            run_root = project_dir / "runs" / "resume-run"
            run_root.mkdir(parents=True)
            memory_path = project_dir / "memory.md"
            memory_path.write_text("Manual memory.\n", encoding="utf-8")
            (project_dir / "checkpoint.json").write_text(
                json.dumps(
                    {
                        "run_id": "resume-run",
                        "run_root": str(run_root),
                        "last_completed_round": 3,
                        "best_score": 93.0,
                        "can_resume": True,
                    }
                ),
                encoding="utf-8",
            )
            agents = RecordingAgents()

            run_resume_mode(
                console=Console(),
                agents=agents,
                task_text="Design a privacy-aware memory adapter.",
                project_dir=project_dir,
                memory_path=memory_path,
                model_name="fake-model",
                max_rounds=4,
                stop_if_no_improvement_rounds=10,
                global_max_runtime_seconds=60,
                per_agent_timeout_seconds=300,
            )

            checkpoint = json.loads((project_dir / "checkpoint.json").read_text(encoding="utf-8"))
            self.assertEqual(agents.draft_rounds, [4])
            self.assertEqual(checkpoint["last_completed_round"], 4)


if __name__ == "__main__":
    unittest.main()
