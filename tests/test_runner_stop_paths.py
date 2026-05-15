from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.constants import STOP_INVALID_SCORE, STOP_OLLAMA_TIMEOUT, STOP_USER_REQUESTED
from src.runner import run_iterative_rounds
from tests.helpers import ConfigurableFakeAgents, NullConsole, make_project_fixture


class RunnerStopPathTests(unittest.TestCase):
    def test_stop_signal_during_round_writes_resumable_checkpoint_and_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = make_project_fixture(Path(tmp))
            stop_signal_path = fixture.project_dir / "STOP_REQUESTED"

            agents = ConfigurableFakeAgents(
                draft_side_effect=lambda: stop_signal_path.write_text(
                    "STOP_REQUESTED\n", encoding="utf-8"
                )
            )

            result = run_iterative_rounds(
                console=NullConsole(),
                agents=agents,
                task_text="Stop safely after the current draft.",
                project_dir=fixture.project_dir,
                memory_path=fixture.memory_path,
                mode="test",
                model_name="fake-model",
                max_rounds=3,
                stop_if_no_improvement_rounds=10,
                global_max_runtime_seconds=60,
                per_agent_timeout_seconds=300,
            )

            checkpoint = json.loads(
                (fixture.project_dir / "checkpoint.json").read_text(encoding="utf-8")
            )
            report = (fixture.project_dir / "interrupted_report.md").read_text(encoding="utf-8")

            self.assertEqual(result["stop_reason"], STOP_USER_REQUESTED)
            self.assertEqual(result["completed_rounds"], 1)
            self.assertTrue(checkpoint["can_resume"])
            self.assertEqual(checkpoint["stop_reason"], STOP_USER_REQUESTED)
            self.assertFalse(stop_signal_path.exists())
            self.assertIn("safe resume command", report)

    def test_agent_timeout_stops_run_and_records_timeout_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = make_project_fixture(Path(tmp))
            agents = ConfigurableFakeAgents(
                errors={
                    "draft": (
                        "Ollama request timed out. Increase timeout_seconds or check "
                        "model/server health."
                    )
                }
            )

            result = run_iterative_rounds(
                console=NullConsole(),
                agents=agents,
                task_text="Exercise timeout handling.",
                project_dir=fixture.project_dir,
                memory_path=fixture.memory_path,
                mode="test",
                model_name="fake-model",
                max_rounds=3,
                stop_if_no_improvement_rounds=10,
                global_max_runtime_seconds=60,
                per_agent_timeout_seconds=300,
            )

            score_history = json.loads(
                (fixture.project_dir / "score_history.json").read_text(encoding="utf-8")
            )
            checkpoint = json.loads(
                (fixture.project_dir / "checkpoint.json").read_text(encoding="utf-8")
            )

            self.assertEqual(result["stop_reason"], STOP_OLLAMA_TIMEOUT)
            self.assertTrue(result["timeout_seen"])
            self.assertEqual(result["completed_rounds"], 1)
            self.assertFalse(checkpoint["can_resume"])
            self.assertTrue(score_history[0]["timeout_this_round"])
            self.assertIn("timed out", score_history[0]["errors"][0])

    def test_invalid_judge_score_marks_invalid_score_stop_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = make_project_fixture(Path(tmp))
            agents = ConfigurableFakeAgents(judge_outputs=["No numeric score in this review."])

            result = run_iterative_rounds(
                console=NullConsole(),
                agents=agents,
                task_text="Exercise invalid score handling.",
                project_dir=fixture.project_dir,
                memory_path=fixture.memory_path,
                mode="test",
                model_name="fake-model",
                max_rounds=1,
                stop_if_no_improvement_rounds=10,
                global_max_runtime_seconds=60,
                per_agent_timeout_seconds=300,
            )

            score_history = json.loads(
                (fixture.project_dir / "score_history.json").read_text(encoding="utf-8")
            )
            checkpoint = json.loads(
                (fixture.project_dir / "checkpoint.json").read_text(encoding="utf-8")
            )

            self.assertEqual(result["stop_reason"], STOP_INVALID_SCORE)
            self.assertTrue(result["invalid_score_seen"])
            self.assertEqual(score_history[0]["score"], 0.0)
            self.assertTrue(score_history[0]["invalid_score_this_round"])
            self.assertEqual(checkpoint["stop_reason"], STOP_INVALID_SCORE)


if __name__ == "__main__":
    unittest.main()
