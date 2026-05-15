from __future__ import annotations

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
from src.constants import STOP_MAX_ROUNDS
from src.runner import run_iterative_rounds


class FakeLLM:
    timeout_seconds = 300


class FakeAgents:
    def __init__(self) -> None:
        self.llm = FakeLLM()
        self.judge_scores = [50, 40]

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
        return f"SCORE: {score}\n- Judge feedback for score {score}."


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


if __name__ == "__main__":
    unittest.main()
