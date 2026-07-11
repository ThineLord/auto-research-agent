from __future__ import annotations

import json
import tempfile
import types
import unittest
from importlib.util import find_spec
from pathlib import Path
from unittest.mock import patch

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

import src.cli as cli_module
import src.main as main_module
import src.resume as resume_module
from src.cli import parse_args
from src.cloud_free import CloudFreeDailyQuotaExhausted
from src.config import AppConfig
from src.constants import (
    STOP_CLOUD_DAILY_QUOTA,
    STOP_INVALID_SCORE,
    STOP_MANUAL_INTERRUPT,
    STOP_MAX_ROUNDS,
    STOP_NO_IMPROVEMENT,
    STOP_OLLAMA_TIMEOUT,
    STOP_PROVIDER_QUOTA_EXHAUSTED,
    STOP_USER_REQUESTED,
)
from src.resume import build_resume_preview, run_resume_mode
from src.run_analytics import analyze_run
from src.run_compare import load_run_summary
from src.runner import (
    ResumeHistoryError,
    _history_best_round,
    _load_resume_histories,
    run_iterative_rounds,
)


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
        drafting_mode: str = "best_guided",
        previous_review: str = "",
        previous_draft: str = "",
        previous_revised: str = "",
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
        drafting_mode: str = "best_guided",
        previous_review: str = "",
        previous_draft: str = "",
        previous_revised: str = "",
    ) -> str:
        raise CloudFreeDailyQuotaExhausted(
            "Free-tier daily quota likely exhausted; safe to resume after reset."
        )


class InterruptingAgents(FakeAgents):
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
        raise KeyboardInterrupt


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
        drafting_mode: str = "best_guided",
        previous_review: str = "",
        previous_draft: str = "",
        previous_revised: str = "",
    ) -> str:
        output = super().draft(
            task=task,
            memory=memory,
            round_index=round_index,
            previous_best=previous_best,
            previous_judge=previous_judge,
            drafting_mode=drafting_mode,
            previous_review=previous_review,
            previous_draft=previous_draft,
            previous_revised=previous_revised,
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
        drafting_mode: str = "best_guided",
        previous_review: str = "",
        previous_draft: str = "",
        previous_revised: str = "",
    ) -> str:
        self.draft_rounds.append(round_index)
        return super().draft(
            task=task,
            memory=memory,
            round_index=round_index,
            previous_best=previous_best,
            previous_judge=previous_judge,
            drafting_mode=drafting_mode,
            previous_review=previous_review,
            previous_draft=previous_draft,
            previous_revised=previous_revised,
        )


class DraftContextAgents(FakeAgents):
    def __init__(self) -> None:
        super().__init__([50, 60])
        self.draft_contexts: list[dict[str, str]] = []

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
        self.draft_contexts.append(
            {
                "round": str(round_index),
                "drafting_mode": drafting_mode,
                "previous_best": previous_best,
                "previous_judge": previous_judge,
                "previous_review": previous_review,
                "previous_draft": previous_draft,
                "previous_revised": previous_revised,
            }
        )
        return super().draft(
            task=task,
            memory=memory,
            round_index=round_index,
            previous_best=previous_best,
            previous_judge=previous_judge,
            drafting_mode=drafting_mode,
            previous_review=previous_review,
            previous_draft=previous_draft,
            previous_revised=previous_revised,
        )


class DraftTimeoutAgents(FakeAgents):
    def __init__(self) -> None:
        super().__init__([0, 0, 0])
        self.draft_calls = 0

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
        self.draft_calls += 1
        raise RuntimeError(
            "Ollama request timed out. Increase timeout_seconds or check model/server health."
        )


class ProviderQuotaAgents(FakeAgents):
    def __init__(self) -> None:
        super().__init__([0, 0, 0])
        self.draft_calls = 0

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
        self.draft_calls += 1
        raise RuntimeError("PROVIDER_QUOTA_EXHAUSTED: Gemini provider quota or rate limit reached.")


class GenericProviderFailureAgents(FakeAgents):
    def __init__(self) -> None:
        super().__init__([0])

    def review(self, *, task: str, memory: str, draft_output: str) -> str:
        raise RuntimeError("Gemini request failed.")


class InvalidScoreAgents(FakeAgents):
    def judge(self, *, task: str, memory: str, revised_output: str) -> str:
        return "Judge completed without a numeric score."


class RoundLoopTests(unittest.TestCase):
    def test_main_reexports_backward_compatible_api(self) -> None:
        self.assertIs(main_module.run_iterative_rounds, run_iterative_rounds)
        self.assertEqual(main_module.STOP_MAX_ROUNDS, STOP_MAX_ROUNDS)
        self.assertTrue(callable(main_module.parse_args))
        self.assertTrue(callable(main_module.run_diagnostic_mode))
        self.assertTrue(callable(main_module.run_session_mode))

    def test_round_loop_rejects_non_positive_max_rounds_before_writing_artifacts(self) -> None:
        for max_rounds in (0, -1):
            with self.subTest(max_rounds=max_rounds), tempfile.TemporaryDirectory() as tmp:
                project_dir = Path(tmp) / "project"
                project_dir.mkdir()
                memory_path = project_dir / "memory.md"
                memory_path.write_text("Manual memory.\n", encoding="utf-8")
                agents = RecordingAgents()

                with self.assertRaisesRegex(ValueError, "max_rounds must be >= 1"):
                    run_iterative_rounds(
                        console=Console(),
                        agents=agents,
                        task_text="Design a privacy-aware memory adapter.",
                        project_dir=project_dir,
                        memory_path=memory_path,
                        mode="normal",
                        model_name="fake-model",
                        max_rounds=max_rounds,
                        stop_if_no_improvement_rounds=10,
                        global_max_runtime_seconds=60,
                        per_agent_timeout_seconds=300,
                    )

                self.assertEqual(agents.draft_rounds, [])
                self.assertFalse((project_dir / "runs").exists())
                self.assertFalse((project_dir / "checkpoint.json").exists())

    def test_round_loop_rejects_non_positive_start_round_before_writing_artifacts(self) -> None:
        for start_round in (0, -1, -0.5, 1.5, True):
            with self.subTest(start_round=start_round), tempfile.TemporaryDirectory() as tmp:
                project_dir = Path(tmp) / "project"
                project_dir.mkdir()
                memory_path = project_dir / "memory.md"
                memory_path.write_text("Manual memory.\n", encoding="utf-8")
                agents = RecordingAgents()

                with self.assertRaisesRegex(ValueError, "start_round must be >= 1"):
                    run_iterative_rounds(
                        console=Console(),
                        agents=agents,
                        task_text="Design a privacy-aware memory adapter.",
                        project_dir=project_dir,
                        memory_path=memory_path,
                        mode="resume",
                        model_name="fake-model",
                        max_rounds=1,
                        start_round=start_round,  # type: ignore[arg-type]
                        stop_if_no_improvement_rounds=10,
                        global_max_runtime_seconds=60,
                        per_agent_timeout_seconds=300,
                    )

                self.assertEqual(agents.draft_rounds, [])
                self.assertFalse((project_dir / "runs").exists())
                self.assertFalse((project_dir / "checkpoint.json").exists())

    def test_parse_args_accepts_mode_and_model_flags(self) -> None:
        args = parse_args(
            [
                "--diagnostic",
                "--survey",
                "--mock",
                "--survey-output",
                "custom_survey.md",
                "--compare-runs",
                "projects/example/runs/a",
                "projects/example/runs/b",
                "--compare-output",
                "projects/example/run_comparison.json",
                "--analyze-run",
                "projects/example/runs/a",
                "--analyze-output",
                "projects/example/run_analysis.json",
                "--model",
                "llama3.1:8b",
                "--benchmark-preset",
                "free_eval",
                "--max-provider-quota-failures",
                "2",
                "--drafting-mode",
                "continue_from_previous_draft",
            ]
        )

        self.assertTrue(args.diagnostic)
        self.assertTrue(args.survey)
        self.assertTrue(args.mock)
        self.assertEqual(args.survey_output, "custom_survey.md")
        self.assertEqual(args.compare_runs, ["projects/example/runs/a", "projects/example/runs/b"])
        self.assertEqual(args.compare_output, "projects/example/run_comparison.json")
        self.assertEqual(args.analyze_run, "projects/example/runs/a")
        self.assertEqual(args.analyze_output, "projects/example/run_analysis.json")
        self.assertEqual(args.model, "llama3.1:8b")
        self.assertEqual(args.benchmark_preset, "free_eval")
        self.assertEqual(args.max_provider_quota_failures, 2)
        self.assertEqual(args.drafting_mode, "continue_from_previous_draft")

    def test_round_loop_writes_outputs_and_keeps_best_score(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "project"
            project_dir.mkdir()
            memory_path = project_dir / "memory.md"
            memory_path.write_text("Manual memory.\n", encoding="utf-8")
            prompt_dir = Path(tmp) / "prompts"
            prompt_dir.mkdir()
            (prompt_dir / "draft.md").write_text("Draft prompt\n", encoding="utf-8")
            (prompt_dir / "judge.md").write_text("Judge prompt\n", encoding="utf-8")

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
                model_provider="test-provider",
                model_parameters={
                    "temperature": 0.2,
                    "top_p": 0.8,
                    "timeout_seconds": 300,
                    "max_prompt_chars": 12000,
                },
                topic_snapshot={
                    "title": "Memory Adapter",
                    "description": "Test topic.",
                    "keywords": ["memory", "adapter"],
                },
                prompt_dir=prompt_dir,
                repo_root=Path(tmp),
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

            run_config = json.loads((run_root / "run_config.json").read_text(encoding="utf-8"))
            run_summary = json.loads((run_root / "run_summary.json").read_text(encoding="utf-8"))
            round_metrics = json.loads(
                (run_root / "round_metrics.json").read_text(encoding="utf-8")
            )
            checkpoint = json.loads((project_dir / "checkpoint.json").read_text(encoding="utf-8"))
            self.assertEqual(run_config["schema_version"], 1)
            self.assertEqual(run_config["status"], "completed")
            self.assertEqual(run_config["stop_reason"], STOP_MAX_ROUNDS)
            self.assertFalse(run_config["can_resume"])
            self.assertEqual(run_config["model"]["provider"], "test-provider")
            self.assertEqual(run_config["model"]["name"], "fake-model")
            self.assertEqual(run_config["runtime"]["max_rounds"], 2)
            self.assertEqual(run_config["topic"]["title"], "Memory Adapter")
            self.assertIn("draft.md", run_config["prompt_files"])
            self.assertEqual(len(run_config["prompt_files"]["draft.md"]["sha256"]), 64)
            self.assertIsNotNone(run_config["started_at"])
            self.assertIsNotNone(run_config["ended_at"])
            self.assertEqual(checkpoint["run_config"], str(run_root / "run_config.json"))
            self.assertEqual(checkpoint["run_summary"], str(run_root / "run_summary.json"))
            self.assertEqual(run_summary["best_score"], 50)
            self.assertEqual(run_summary["completed_rounds"], 2)
            self.assertEqual(run_summary["successful_rounds"], [1, 2])
            self.assertEqual(
                run_summary["total_elapsed_seconds"], run_summary["total_runtime_seconds"]
            )
            self.assertGreaterEqual(run_summary["total_agent_elapsed_seconds"], 0)
            self.assertGreater(run_summary["total_estimated_input_tokens"], 0)
            self.assertGreater(run_summary["total_estimated_output_tokens"], 0)
            self.assertEqual(
                run_summary["total_estimated_tokens"],
                run_summary["total_estimated_input_tokens"]
                + run_summary["total_estimated_output_tokens"],
            )
            self.assertEqual(run_summary["timeout_count"], 0)
            self.assertEqual(run_summary["error_count"], 0)
            self.assertIn("draft", run_summary["agent_metric_totals"])
            self.assertIn("evolution_metric_totals", run_summary)
            self.assertEqual(
                run_summary["evolution_metric_totals"]["rounds_with_evolution_metrics"],
                2,
            )
            self.assertIsNotNone(run_summary["avg_draft_to_revised_similarity"])
            self.assertEqual(run_summary["rubric_round_count"], 2)
            self.assertEqual(
                run_summary["rubric_subscore_averages"]["evaluation_design_quality"],
                10.0,
            )
            self.assertEqual(
                run_summary["rubric_subscore_latest"]["tomorrow_actionability"],
                10.0,
            )
            self.assertEqual(run_summary["resume_metadata"]["lifecycle_action"], "start_new_run")
            self.assertFalse(run_summary["resume_metadata"]["resume_from_checkpoint"])
            self.assertFalse(run_summary["resume_metadata"]["new_run_from_previous_best"])
            self.assertEqual(len(round_metrics), 2)
            self.assertIn("agent_timings_seconds", round_metrics[0])
            self.assertIn("agent_io_metrics", round_metrics[0])
            self.assertIn("evolution_metrics", round_metrics[0])
            self.assertFalse(round_metrics[0]["evolution_metrics"]["has_previous_round"])
            self.assertTrue(round_metrics[1]["evolution_metrics"]["has_previous_round"])
            self.assertEqual(
                round_metrics[1]["evolution_metrics"]["score_delta_vs_previous"],
                -10.0,
            )
            self.assertGreater(round_metrics[0]["estimated_total_tokens"], 0)
            self.assertEqual(
                round_metrics[0]["agent_io_metrics"]["draft"]["token_estimate_method"],
                run_summary["token_estimate_method"],
            )
            self.assertIn("judge_rubric", round_metrics[0])
            self.assertEqual(round_metrics[0]["judge_rubric"]["novelty_and_research_value"], 10.0)

    def test_drafting_modes_pass_expected_previous_context_to_draft_agent(self) -> None:
        expectations = {
            "best_guided": {
                "previous_best": "Revised output from Draft round 1",
                "previous_review": "",
                "previous_draft": "",
                "previous_revised": "",
            },
            "fresh_from_task_with_review": {
                "previous_best": "",
                "previous_review": "Review notes for Draft round 1",
                "previous_draft": "",
                "previous_revised": "",
            },
            "continue_from_previous_draft": {
                "previous_best": "",
                "previous_review": "Review notes for Draft round 1",
                "previous_draft": "Draft round 1",
                "previous_revised": "Revised output from Draft round 1",
            },
        }
        for drafting_mode, expected in expectations.items():
            with self.subTest(drafting_mode=drafting_mode):
                with tempfile.TemporaryDirectory() as tmp:
                    project_dir = Path(tmp) / "project"
                    project_dir.mkdir()
                    memory_path = project_dir / "memory.md"
                    memory_path.write_text("Manual memory.\n", encoding="utf-8")
                    agents = DraftContextAgents()

                    result = run_iterative_rounds(
                        console=Console(),
                        agents=agents,
                        task_text="Design a privacy-aware memory adapter.",
                        project_dir=project_dir,
                        memory_path=memory_path,
                        mode="test",
                        model_name="fake-model",
                        max_rounds=2,
                        stop_if_no_improvement_rounds=10,
                        global_max_runtime_seconds=60,
                        per_agent_timeout_seconds=300,
                        drafting_mode=drafting_mode,
                    )

                    run_root = Path(result["run_root"])
                    checkpoint = json.loads(
                        (project_dir / "checkpoint.json").read_text(encoding="utf-8")
                    )
                    score_history = json.loads(
                        (project_dir / "score_history.json").read_text(encoding="utf-8")
                    )
                    run_config = json.loads(
                        (run_root / "run_config.json").read_text(encoding="utf-8")
                    )
                    round_two = agents.draft_contexts[1]

                    self.assertEqual(round_two["drafting_mode"], drafting_mode)
                    self.assertIn("score", round_two["previous_judge"])
                    for field, expected_text in expected.items():
                        if expected_text:
                            self.assertIn(expected_text, round_two[field])
                        else:
                            self.assertEqual(round_two[field], "")
                    self.assertEqual(checkpoint["drafting_mode"], drafting_mode)
                    self.assertEqual(run_config["drafting_mode"], drafting_mode)
                    self.assertEqual(
                        [entry["drafting_mode"] for entry in score_history],
                        [drafting_mode, drafting_mode],
                    )

    def test_round_loop_records_project_source_in_manifest_checkpoint_and_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "project"
            project_dir.mkdir()
            memory_path = project_dir / "memory.md"
            memory_path.write_text("Manual memory.\n", encoding="utf-8")
            metadata = {
                "project_name": "nebula_unique_task",
                "project_dir": str(project_dir),
                "task_path": str(project_dir / "task.md"),
                "project_title": "Nebula Constraint Solver",
                "source_kind": "user_provided",
                "explicit_project": True,
                "is_example_project": False,
            }

            result = run_iterative_rounds(
                console=Console(),
                agents=FakeAgents([50]),
                task_text="Design a privacy-aware memory adapter.",
                project_dir=project_dir,
                memory_path=memory_path,
                mode="test",
                model_name="fake-model",
                max_rounds=1,
                stop_if_no_improvement_rounds=10,
                global_max_runtime_seconds=60,
                per_agent_timeout_seconds=300,
                project_metadata=metadata,
            )

            run_root = Path(result["run_root"])
            manifest = json.loads((run_root / "run_manifest.json").read_text(encoding="utf-8"))
            checkpoint = json.loads((project_dir / "checkpoint.json").read_text(encoding="utf-8"))
            run_log = (project_dir / "run.log").read_text(encoding="utf-8")

            self.assertEqual(manifest["project"]["source_kind"], "user_provided")
            self.assertEqual(manifest["project"]["project_title"], "Nebula Constraint Solver")
            self.assertEqual(checkpoint["project"]["task_path"], str(project_dir / "task.md"))
            self.assertIn("project_source kind=user_provided", run_log)

    def test_round_loop_masks_paths_in_console_and_run_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            project_dir = repo_root / "projects" / "demo"
            project_dir.mkdir(parents=True)
            memory_path = project_dir / "memory.md"
            memory_path.write_text("Manual memory.\n", encoding="utf-8")
            metadata = {
                "project_name": "demo",
                "project_dir": str(project_dir),
                "task_path": str(project_dir / "task.md"),
                "project_title": "Demo",
                "source_kind": "user_provided",
            }
            console = Console(record=True, width=200)

            run_iterative_rounds(
                console=console,
                agents=FakeAgents([50]),
                task_text="Design a privacy-aware memory adapter.",
                project_dir=project_dir,
                memory_path=memory_path,
                mode="test",
                model_name="fake-model",
                max_rounds=1,
                stop_if_no_improvement_rounds=10,
                global_max_runtime_seconds=60,
                per_agent_timeout_seconds=300,
                project_metadata=metadata,
                repo_root=repo_root,
            )

            output = console.export_text(styles=False)
            run_log = (project_dir / "run.log").read_text(encoding="utf-8")
            self.assertIn("run_root=projects/demo/runs/", output)
            self.assertIn("project_dir=projects/demo", run_log)
            self.assertIn("task_path=projects/demo/task.md", run_log)
            self.assertIn("Best output path: projects/demo/best_output.md", output)
            self.assertIn("Score history path: projects/demo/score_history.json", output)
            self.assertNotIn(str(project_dir), output)
            self.assertNotIn(str(project_dir), run_log)

    def test_continuous_mode_stops_after_first_draft_timeout_even_when_timeout_stop_disabled(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "project"
            project_dir.mkdir()
            memory_path = project_dir / "memory.md"
            memory_path.write_text("Manual memory.\n", encoding="utf-8")
            agents = DraftTimeoutAgents()

            result = run_iterative_rounds(
                console=Console(),
                agents=agents,
                task_text="Design a privacy-aware memory adapter.",
                project_dir=project_dir,
                memory_path=memory_path,
                mode="continuous",
                model_name="fake-model",
                max_rounds=3,
                stop_if_no_improvement_rounds=10,
                global_max_runtime_seconds=60,
                per_agent_timeout_seconds=300,
                disable_no_improvement_stop=True,
                disable_timeout_stop=True,
            )

            self.assertEqual(agents.draft_calls, 1)
            self.assertEqual(result["completed_rounds"], 1)
            self.assertEqual(result["stop_reason"], STOP_OLLAMA_TIMEOUT)

    def test_round_loop_stops_after_consecutive_provider_quota_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "project"
            project_dir.mkdir()
            memory_path = project_dir / "memory.md"
            memory_path.write_text("Manual memory.\n", encoding="utf-8")
            agents = ProviderQuotaAgents()

            result = run_iterative_rounds(
                console=Console(),
                agents=agents,
                task_text="Design a privacy-aware memory adapter.",
                project_dir=project_dir,
                memory_path=memory_path,
                mode="continuous",
                model_name="gemini:gemini-3.5-flash",
                max_rounds=5,
                stop_if_no_improvement_rounds=10,
                global_max_runtime_seconds=60,
                per_agent_timeout_seconds=300,
                disable_no_improvement_stop=True,
                disable_timeout_stop=True,
                max_consecutive_provider_quota_failures=2,
            )

            run_root = Path(result["run_root"])
            checkpoint = json.loads((project_dir / "checkpoint.json").read_text(encoding="utf-8"))
            score_history = json.loads(
                (project_dir / "score_history.json").read_text(encoding="utf-8")
            )

            self.assertEqual(agents.draft_calls, 2)
            self.assertEqual(result["completed_rounds"], 2)
            self.assertEqual(result["stop_reason"], STOP_PROVIDER_QUOTA_EXHAUSTED)
            self.assertEqual(checkpoint["stop_reason"], STOP_PROVIDER_QUOTA_EXHAUSTED)
            self.assertTrue(checkpoint["can_resume"])
            self.assertTrue(checkpoint["provider_quota_exhausted"])
            self.assertEqual([entry["round"] for entry in score_history], [1, 2])
            self.assertTrue(all(entry["provider_quota_this_round"] for entry in score_history))
            self.assertFalse((run_root / "round_03").exists())

    def test_round_loop_marks_generic_provider_failure_round(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "project"
            project_dir.mkdir()
            memory_path = project_dir / "memory.md"
            memory_path.write_text("Manual memory.\n", encoding="utf-8")
            best_output_path = project_dir / "best_output.md"
            best_output_path.write_text("Trusted prior best.\n", encoding="utf-8")

            result = run_iterative_rounds(
                console=Console(),
                agents=GenericProviderFailureAgents(),
                task_text="Design a privacy-aware memory adapter.",
                project_dir=project_dir,
                memory_path=memory_path,
                mode="continuous",
                model_name="gemini:gemini-3.5-flash",
                max_rounds=1,
                stop_if_no_improvement_rounds=10,
                global_max_runtime_seconds=60,
                per_agent_timeout_seconds=300,
                disable_no_improvement_stop=True,
                disable_timeout_stop=True,
            )

            score_history = json.loads(
                (project_dir / "score_history.json").read_text(encoding="utf-8")
            )

            self.assertEqual(result["completed_rounds"], 1)
            self.assertEqual(result["stop_reason"], STOP_MAX_ROUNDS)
            self.assertEqual(score_history[0]["errors"][0], "Gemini request failed.")
            self.assertTrue(score_history[0]["provider_failure_this_round"])
            self.assertFalse(score_history[0]["provider_quota_this_round"])
            self.assertTrue(score_history[0]["skipped_placeholder_this_round"])
            self.assertFalse(score_history[0]["successful_research_round"])
            self.assertFalse(score_history[0]["improved"])
            self.assertEqual(result["best_output"], "Trusted prior best.")
            self.assertEqual(best_output_path.read_text(encoding="utf-8"), "Trusted prior best.\n")

    def test_invalid_judge_score_does_not_replace_trusted_best_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "project"
            project_dir.mkdir()
            memory_path = project_dir / "memory.md"
            memory_path.write_text("Manual memory.\n", encoding="utf-8")
            best_output_path = project_dir / "best_output.md"
            best_output_path.write_text("Trusted prior best.\n", encoding="utf-8")

            result = run_iterative_rounds(
                console=Console(),
                agents=InvalidScoreAgents(),
                task_text="Design a privacy-aware memory adapter.",
                project_dir=project_dir,
                memory_path=memory_path,
                mode="normal",
                model_name="fake-model",
                max_rounds=1,
                stop_if_no_improvement_rounds=10,
                global_max_runtime_seconds=60,
                per_agent_timeout_seconds=300,
            )

            score_history = json.loads(
                (project_dir / "score_history.json").read_text(encoding="utf-8")
            )

            self.assertEqual(result["stop_reason"], STOP_INVALID_SCORE)
            self.assertTrue(score_history[0]["invalid_score_this_round"])
            self.assertFalse(score_history[0]["successful_research_round"])
            self.assertFalse(score_history[0]["improved"])
            self.assertEqual(result["best_output"], "Trusted prior best.")
            self.assertEqual(best_output_path.read_text(encoding="utf-8"), "Trusted prior best.\n")

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

    def test_manual_interrupt_finalizes_resumable_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "project"
            project_dir.mkdir()
            memory_path = project_dir / "memory.md"
            memory_path.write_text("Manual memory.\n", encoding="utf-8")

            with self.assertRaises(KeyboardInterrupt):
                run_iterative_rounds(
                    console=Console(),
                    agents=InterruptingAgents(),
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

            checkpoint = json.loads((project_dir / "checkpoint.json").read_text(encoding="utf-8"))
            run_root = Path(checkpoint["run_root"])
            run_summary = json.loads((run_root / "run_summary.json").read_text(encoding="utf-8"))
            run_config = json.loads((run_root / "run_config.json").read_text(encoding="utf-8"))

            for artifact in (checkpoint, run_summary, run_config):
                self.assertEqual(artifact["stop_reason"], STOP_MANUAL_INTERRUPT)
                self.assertTrue(artifact["can_resume"])
            self.assertEqual(checkpoint["last_completed_round"], 0)
            self.assertEqual(run_summary["completed_rounds"], 0)
            self.assertEqual(run_config["completed_rounds"], 0)
            self.assertTrue((project_dir / "interrupted_report.md").is_file())

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

    def test_stale_stop_signal_directory_does_not_crash_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "project"
            project_dir.mkdir()
            memory_path = project_dir / "memory.md"
            memory_path.write_text("Manual memory.\n", encoding="utf-8")
            stop_path = project_dir / "STOP_REQUESTED"
            stop_path.mkdir()

            result = run_iterative_rounds(
                console=Console(),
                agents=FakeAgents(),
                task_text="Design a privacy-aware memory adapter.",
                project_dir=project_dir,
                memory_path=memory_path,
                mode="test",
                model_name="fake-model",
                max_rounds=1,
                stop_if_no_improvement_rounds=10,
                global_max_runtime_seconds=60,
                per_agent_timeout_seconds=300,
            )

            self.assertEqual(result["completed_rounds"], 0)
            self.assertEqual(result["stop_reason"], STOP_USER_REQUESTED)
            self.assertTrue(stop_path.is_dir())

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
            completed_round_dir = run_root / "round_03"
            completed_round_dir.mkdir()
            completed_judge_path = completed_round_dir / "04_judge.md"
            completed_judge_path.write_text("completed round 3 judge\n", encoding="utf-8")
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
            console = Console(record=True)

            resume_started = run_resume_mode(
                console=console,
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
            run_config = json.loads((run_root / "run_config.json").read_text(encoding="utf-8"))
            run_summary = json.loads((run_root / "run_summary.json").read_text(encoding="utf-8"))
            self.assertTrue(resume_started)
            self.assertEqual(agents.draft_rounds, [4])
            self.assertEqual(checkpoint["last_completed_round"], 4)
            self.assertEqual(
                completed_judge_path.read_text(encoding="utf-8"),
                "completed round 3 judge\n",
            )
            if hasattr(console, "export_text"):
                output = " ".join(console.export_text().split())
                self.assertIn("Resume preview", output)
                self.assertIn("completed round files are preserved", output)
            for artifact in (checkpoint, run_config, run_summary):
                resume_metadata = artifact["resume_metadata"]
                self.assertEqual(resume_metadata["lifecycle_action"], "resume_existing_run")
                self.assertTrue(resume_metadata["resume_from_checkpoint"])
                self.assertEqual(resume_metadata["resume_from_round"], 4)
                self.assertTrue(resume_metadata["completed_round_files_preserved"])
                self.assertEqual(resume_metadata["next_round_status"], "missing")
                self.assertEqual(
                    resume_metadata["next_round_safety_action"], "proceed_create_round_dir"
                )
            self.assertEqual(run_config["resume_sessions"][0]["start_round"], 4)

    @unittest.skipUnless(hasattr(Path, "symlink_to"), "symlinks are unavailable")
    def test_resume_mode_rejects_linked_project_ancestor_before_checkpoint_read(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outside_project = root / "outside-projects" / "selected"
            outside_project.mkdir(parents=True)
            external_checkpoint = outside_project / "checkpoint.json"
            external_checkpoint.write_text(
                '{"run_id": "private", "can_resume": true}\n',
                encoding="utf-8",
            )
            (root / "projects").symlink_to(
                root / "outside-projects",
                target_is_directory=True,
            )
            project_dir = root / "projects" / "selected"

            with patch.object(
                resume_module,
                "read_json_file",
                side_effect=AssertionError("external checkpoint must not be read"),
            ) as read_checkpoint:
                with self.assertRaises(OSError):
                    run_resume_mode(
                        console=Console(),
                        agents=RecordingAgents(),
                        task_text="must not run",
                        project_dir=project_dir,
                        memory_path=project_dir / "memory.md",
                        model_name="fake-model",
                        max_rounds=1,
                        stop_if_no_improvement_rounds=1,
                        global_max_runtime_seconds=1,
                        per_agent_timeout_seconds=1,
                    )

            read_checkpoint.assert_not_called()
            self.assertEqual(
                external_checkpoint.read_text(encoding="utf-8"),
                '{"run_id": "private", "can_resume": true}\n',
            )

    def test_resume_preserves_legacy_manifest_provenance_and_unknown_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "project"
            project_dir.mkdir()
            run_root = project_dir / "runs" / "legacy-run"
            previous_round = run_root / "round_01"
            previous_round.mkdir(parents=True)
            (previous_round / "04_judge.md").write_text("legacy judge\n", encoding="utf-8")
            memory_path = project_dir / "memory.md"
            memory_path.write_text("Manual memory.\n", encoding="utf-8")
            (project_dir / "best_output.md").write_text("Legacy best.\n", encoding="utf-8")
            history = [
                {
                    "round": 1,
                    "score": 80.0,
                    "improved": True,
                    "successful_research_round": True,
                }
            ]
            (run_root / "round_metrics.json").write_text(json.dumps(history), encoding="utf-8")
            (project_dir / "score_history.json").write_text(json.dumps(history), encoding="utf-8")
            original_manifest = {
                "run_id": "legacy-run",
                "run_root": str(run_root),
                "mode": "session",
                "model": "original-model",
                "drafting_mode": "fresh_with_review",
                "started_at": "2026-06-20T01:02:03+00:00",
                "project": {"project_name": "original-project", "legacy_project": True},
                "resume_metadata": {"legacy_resume_marker": {"preserve": True}},
                "legacy_extension": {"nested": [1, {"preserve": "exactly"}]},
                "run_config": "legacy-run-config-pointer",
            }
            manifest_path = run_root / "run_manifest.json"
            manifest_path.write_text(json.dumps(original_manifest), encoding="utf-8")
            (project_dir / "checkpoint.json").write_text(
                json.dumps(
                    {
                        "run_id": "legacy-run",
                        "run_root": str(run_root),
                        "last_completed_round": 1,
                        "best_score": 80.0,
                        "best_round_path": str(previous_round),
                        "can_resume": True,
                    }
                ),
                encoding="utf-8",
            )

            resumed = run_resume_mode(
                console=Console(),
                agents=RecordingAgents(),
                task_text="Design a privacy-aware memory adapter.",
                project_dir=project_dir,
                memory_path=memory_path,
                model_name="current-model",
                max_rounds=2,
                stop_if_no_improvement_rounds=10,
                global_max_runtime_seconds=60,
                per_agent_timeout_seconds=300,
                project_metadata={"project_name": "current-project"},
            )

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertTrue(resumed)
            for key in (
                "run_id",
                "mode",
                "model",
                "drafting_mode",
                "started_at",
                "project",
                "legacy_extension",
            ):
                self.assertEqual(manifest[key], original_manifest[key])
            self.assertEqual(manifest["run_root"], str(run_root.resolve()))
            self.assertEqual(manifest["run_config"], str(run_root.resolve() / "run_config.json"))
            self.assertEqual(
                manifest["resume_metadata"]["legacy_resume_marker"],
                {"preserve": True},
            )
            self.assertEqual(
                manifest["resume_metadata"]["lifecycle_action"],
                "resume_existing_run",
            )
            self.assertEqual(manifest["resume_metadata"]["resume_from_round"], 2)

    def test_resume_preview_requires_checkpoint_id_to_match_canonical_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "project"
            run_root = project_dir / "runs" / "canonical-run"
            run_root.mkdir(parents=True)
            alias_root = run_root.parent / "legacy-alias"
            alias_root.symlink_to(run_root, target_is_directory=True)

            for name, checkpoint_root, checkpoint_id in (
                ("direct mismatch", run_root, "different-run"),
                ("symlink alias", alias_root, "legacy-alias"),
                ("non-string id", run_root, 7),
            ):
                with self.subTest(name=name):
                    preview = build_resume_preview(
                        project_dir=project_dir,
                        checkpoint={
                            "run_id": checkpoint_id,
                            "run_root": str(checkpoint_root),
                            "last_completed_round": 0,
                            "can_resume": True,
                        },
                    )

                    self.assertFalse(preview["can_resume"])
                    self.assertEqual(preview["blocked_reason"], "run_id_mismatch")
                    self.assertNotIn(str(Path(tmp)), preview["message"])

            derived_preview = build_resume_preview(
                project_dir=project_dir,
                checkpoint={
                    "run_root": str(alias_root),
                    "last_completed_round": 0,
                    "can_resume": True,
                },
            )
            self.assertTrue(derived_preview["can_resume"])
            self.assertEqual(derived_preview["run_id"], "canonical-run")
            self.assertEqual(Path(derived_preview["run_root"]), run_root.resolve())

    def test_resume_preview_requires_literal_true_and_finite_best_score(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "project"
            run_root = project_dir / "runs" / "resume-run"
            run_root.mkdir(parents=True)
            base_checkpoint = {
                "run_id": "resume-run",
                "run_root": str(run_root),
                "last_completed_round": 0,
            }

            for invalid_flag in ("false", "true", 1, 0, [], {}):
                with self.subTest(can_resume=invalid_flag):
                    preview = build_resume_preview(
                        project_dir=project_dir,
                        checkpoint={**base_checkpoint, "can_resume": invalid_flag},
                    )

                    self.assertFalse(preview["can_resume"])
                    self.assertEqual(preview["blocked_reason"], "not_resume_eligible")

            valid_preview = build_resume_preview(
                project_dir=project_dir,
                checkpoint={
                    **base_checkpoint,
                    "can_resume": True,
                    "best_score": "80.5",
                },
            )
            self.assertTrue(valid_preview["can_resume"])
            self.assertEqual(valid_preview["best_score"], 80.5)

            for invalid_score in (10**400, "Infinity", float("inf"), float("nan"), True):
                with self.subTest(best_score=invalid_score):
                    preview = build_resume_preview(
                        project_dir=project_dir,
                        checkpoint={
                            **base_checkpoint,
                            "can_resume": True,
                            "best_score": invalid_score,
                        },
                    )

                    self.assertTrue(preview["can_resume"])
                    self.assertEqual(preview["best_score"], -1.0)

    def test_non_boolean_resume_eligibility_blocks_before_agents_or_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "project"
            run_root = project_dir / "runs" / "resume-run"
            run_root.mkdir(parents=True)
            memory_path = project_dir / "memory.md"
            memory_path.write_text("Manual memory.\n", encoding="utf-8")
            checkpoint_path = project_dir / "checkpoint.json"
            checkpoint_path.write_text(
                json.dumps(
                    {
                        "run_id": "resume-run",
                        "run_root": str(run_root),
                        "last_completed_round": 0,
                        "best_score": -1,
                        "can_resume": "false",
                    }
                ),
                encoding="utf-8",
            )
            before = {
                path.relative_to(project_dir): path.read_bytes()
                for path in project_dir.rglob("*")
                if path.is_file()
            }
            agents = RecordingAgents()

            resume_started = run_resume_mode(
                console=Console(),
                agents=agents,
                task_text="Design a privacy-aware memory adapter.",
                project_dir=project_dir,
                memory_path=memory_path,
                model_name="fake-model",
                max_rounds=1,
                stop_if_no_improvement_rounds=10,
                global_max_runtime_seconds=60,
                per_agent_timeout_seconds=300,
            )
            after = {
                path.relative_to(project_dir): path.read_bytes()
                for path in project_dir.rglob("*")
                if path.is_file()
            }

            self.assertFalse(resume_started)
            self.assertEqual(agents.draft_rounds, [])
            self.assertEqual(after, before)

    def test_resume_rejects_unpreservable_legacy_manifest_before_writes(self) -> None:
        deeply_nested_manifest = b'{"nested":' * 150 + b"0" + b"}" * 150
        cases = {
            "invalid_json": b'{"run_id":',
            "invalid_utf8": b"\xff\xfe",
            "non_object": b"[]",
            "deep_json": deeply_nested_manifest,
            "mismatched_run_id": b'{"run_id": "different-run"}',
            "invalid_run_id_type": b'{"run_id": 7}',
            "invalid_resume_metadata": (
                b'{"run_id": "resume-run", "resume_metadata": "legacy-text"}'
            ),
        }
        for name, manifest_bytes in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                project_dir = Path(tmp) / "project"
                run_root = project_dir / "runs" / "resume-run"
                run_root.mkdir(parents=True)
                memory_path = project_dir / "memory.md"
                memory_path.write_text("Manual memory.\n", encoding="utf-8")
                manifest_path = run_root / "run_manifest.json"
                manifest_path.write_bytes(manifest_bytes)
                checkpoint_path = project_dir / "checkpoint.json"
                checkpoint_bytes = json.dumps(
                    {
                        "run_id": "resume-run",
                        "run_root": str(run_root),
                        "last_completed_round": 0,
                        "best_score": -1,
                        "can_resume": True,
                    }
                ).encode()
                checkpoint_path.write_bytes(checkpoint_bytes)
                agents = RecordingAgents()

                with self.assertRaises(ResumeHistoryError) as caught:
                    run_resume_mode(
                        console=Console(),
                        agents=agents,
                        task_text="Design a privacy-aware memory adapter.",
                        project_dir=project_dir,
                        memory_path=memory_path,
                        model_name="fake-model",
                        max_rounds=1,
                        stop_if_no_improvement_rounds=10,
                        global_max_runtime_seconds=60,
                        per_agent_timeout_seconds=300,
                    )

                self.assertEqual(agents.draft_rounds, [])
                self.assertEqual(manifest_path.read_bytes(), manifest_bytes)
                self.assertEqual(checkpoint_path.read_bytes(), checkpoint_bytes)
                self.assertFalse((run_root / "run_config.json").exists())
                self.assertFalse((run_root / "run_summary.json").exists())
                self.assertFalse((run_root / "round_01").exists())
                self.assertIn("run_manifest.json", str(caught.exception))
                self.assertNotIn(str(Path(tmp)), str(caught.exception))

    def test_resume_rejects_invalid_existing_run_config_before_writes(self) -> None:
        deeply_nested_config = b'{"nested":' * 150 + b"0" + b"}" * 150
        cases = {
            "invalid_json": b'{"schema_version": 1, "started_at": ',
            "invalid_utf8": b"\xff\xfe",
            "non_object": b"[]",
            "null": b"null",
            "deep_json": deeply_nested_config,
        }
        for name, config_bytes in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                project_dir = Path(tmp) / "project"
                run_root = project_dir / "runs" / "resume-run"
                run_root.mkdir(parents=True)
                memory_path = project_dir / "memory.md"
                memory_path.write_text("Manual memory.\n", encoding="utf-8")
                config_path = run_root / "run_config.json"
                config_path.write_bytes(config_bytes)
                manifest_path = run_root / "run_manifest.json"
                manifest_path.write_text(
                    json.dumps(
                        {
                            "run_id": "resume-run",
                            "started_at": "2026-01-01T00:00:00+00:00",
                            "legacy_extension": {"preserve": True},
                        }
                    ),
                    encoding="utf-8",
                )
                checkpoint_path = project_dir / "checkpoint.json"
                checkpoint_path.write_text(
                    json.dumps(
                        {
                            "run_id": "resume-run",
                            "run_root": str(run_root),
                            "last_completed_round": 0,
                            "best_score": -1,
                            "can_resume": True,
                        }
                    ),
                    encoding="utf-8",
                )
                stop_path = project_dir / "STOP_REQUESTED"
                stop_path.write_text("STOP_REQUESTED\n", encoding="utf-8")
                original_bytes = {
                    path: path.read_bytes()
                    for path in (config_path, manifest_path, checkpoint_path, stop_path)
                }
                agents = RecordingAgents()

                with self.assertRaises(ResumeHistoryError) as caught:
                    run_resume_mode(
                        console=Console(),
                        agents=agents,
                        task_text="Design a privacy-aware memory adapter.",
                        project_dir=project_dir,
                        memory_path=memory_path,
                        model_name="fake-model",
                        max_rounds=1,
                        stop_if_no_improvement_rounds=10,
                        global_max_runtime_seconds=60,
                        per_agent_timeout_seconds=300,
                    )

                self.assertEqual(agents.draft_rounds, [])
                for path, expected_bytes in original_bytes.items():
                    self.assertEqual(path.read_bytes(), expected_bytes)
                for unexpected_path in (
                    project_dir / "run.log",
                    project_dir / "score_history.json",
                    project_dir / "research_state.json",
                    run_root / "run_summary.json",
                    run_root / "round_metrics.json",
                    run_root / "round_01",
                ):
                    self.assertFalse(unexpected_path.exists())
                self.assertIn("run_config.json", str(caught.exception))
                self.assertNotIn(str(Path(tmp)), str(caught.exception))

    def test_repeated_resume_does_not_invent_sparse_manifest_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "project"
            run_root = project_dir / "runs" / "sparse-run"
            run_root.mkdir(parents=True)
            memory_path = project_dir / "memory.md"
            memory_path.write_text("Manual memory.\n", encoding="utf-8")
            manifest_path = run_root / "run_manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "run_id": "sparse-run",
                        "legacy_extension": {"preserve": True},
                        "resume_metadata": {"legacy_resume_marker": "keep"},
                    }
                ),
                encoding="utf-8",
            )
            checkpoint_path = project_dir / "checkpoint.json"
            checkpoint_path.write_text(
                json.dumps(
                    {
                        "run_id": "sparse-run",
                        "run_root": str(run_root),
                        "last_completed_round": 0,
                        "best_score": -1,
                        "can_resume": True,
                    }
                ),
                encoding="utf-8",
            )

            for session_index in (1, 2):
                (project_dir / "STOP_REQUESTED").write_text("STOP_REQUESTED\n", encoding="utf-8")
                resumed = run_resume_mode(
                    console=Console(),
                    agents=RecordingAgents(),
                    task_text="Design a privacy-aware memory adapter.",
                    project_dir=project_dir,
                    memory_path=memory_path,
                    model_name=f"current-model-{session_index}",
                    max_rounds=1,
                    stop_if_no_improvement_rounds=10,
                    global_max_runtime_seconds=60,
                    per_agent_timeout_seconds=300,
                    project_metadata={"project_name": f"current-project-{session_index}"},
                    drafting_mode="continue_from_previous_draft",
                )

                self.assertTrue(resumed)
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                for creation_field in (
                    "mode",
                    "model",
                    "drafting_mode",
                    "started_at",
                    "project",
                ):
                    self.assertNotIn(creation_field, manifest)
                self.assertEqual(manifest["legacy_extension"], {"preserve": True})
                self.assertEqual(manifest["resume_metadata"]["legacy_resume_marker"], "keep")
                self.assertEqual(
                    manifest["resume_metadata"]["lifecycle_action"],
                    "resume_existing_run",
                )
                self.assertEqual(manifest["run_id"], "sparse-run")
                self.assertEqual(manifest["run_root"], str(run_root.resolve()))
                self.assertFalse((project_dir / "STOP_REQUESTED").exists())
                run_config = json.loads((run_root / "run_config.json").read_text(encoding="utf-8"))
                self.assertEqual(len(run_config["resume_sessions"]), session_index)
                self.assertEqual(run_config["resume_sessions"][-1]["start_round"], 1)

    def test_resume_rejects_run_roots_outside_the_selected_project(self) -> None:
        unsafe_kinds = (
            "absolute",
            "traversal",
            "symlink",
            "runs_directory",
            "relative",
            "nested",
            "sibling_prefix",
            "missing_outside",
            "nul_character",
        )
        for unsafe_kind in unsafe_kinds:
            with self.subTest(unsafe_kind=unsafe_kind), tempfile.TemporaryDirectory() as tmp:
                repo_root = Path(tmp)
                project_dir = repo_root / "projects" / "selected"
                runs_dir = project_dir / "runs"
                runs_dir.mkdir(parents=True)
                outside_run = repo_root / "projects" / "other" / "runs" / unsafe_kind
                if unsafe_kind != "missing_outside":
                    outside_run.mkdir(parents=True)

                if unsafe_kind == "absolute":
                    checkpoint_run_root = outside_run
                elif unsafe_kind == "traversal":
                    escaped_run = project_dir / "escaped-run"
                    escaped_run.mkdir()
                    checkpoint_run_root = runs_dir / ".." / escaped_run.name
                elif unsafe_kind == "symlink":
                    checkpoint_run_root = runs_dir / "linked-run"
                    checkpoint_run_root.symlink_to(outside_run, target_is_directory=True)
                elif unsafe_kind == "relative":
                    relative_target = runs_dir / "relative-run"
                    relative_target.mkdir()
                    checkpoint_run_root = Path("projects/selected/runs/relative-run")
                elif unsafe_kind == "nested":
                    checkpoint_run_root = runs_dir / "nested" / "run"
                    checkpoint_run_root.mkdir(parents=True)
                elif unsafe_kind == "sibling_prefix":
                    checkpoint_run_root = project_dir / "runs-evil" / "run"
                    checkpoint_run_root.mkdir(parents=True)
                elif unsafe_kind == "nul_character":
                    checkpoint_run_root = str(runs_dir / "bad") + "\x00tail"
                else:
                    checkpoint_run_root = (
                        runs_dir if unsafe_kind == "runs_directory" else outside_run
                    )

                checkpoint = {
                    "run_id": "unsafe-run",
                    "run_root": str(checkpoint_run_root),
                    "last_completed_round": 0,
                    "can_resume": True,
                }
                preview = build_resume_preview(
                    project_dir=project_dir,
                    checkpoint=checkpoint,
                    repo_root=repo_root,
                )

                self.assertFalse(preview["can_resume"])
                self.assertEqual(preview["blocked_reason"], "unsafe_run_root")
                self.assertIn("selected project's runs directory", preview["message"])
                self.assertNotIn(str(repo_root), preview["message"])

    def test_runner_rejects_unsafe_run_root_override_before_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            project_dir = repo_root / "projects" / "selected"
            project_dir.mkdir(parents=True)
            outside_run = repo_root / "outside-run"
            outside_run.mkdir()
            memory_path = project_dir / "memory.md"
            memory_path.write_text("Manual memory.\n", encoding="utf-8")
            agents = RecordingAgents()

            with self.assertRaisesRegex(ResumeHistoryError, "selected project's runs directory"):
                run_iterative_rounds(
                    console=Console(),
                    agents=agents,
                    task_text="Design a privacy-aware memory adapter.",
                    project_dir=project_dir,
                    memory_path=memory_path,
                    mode="resume",
                    model_name="fake-model",
                    max_rounds=1,
                    stop_if_no_improvement_rounds=10,
                    global_max_runtime_seconds=60,
                    per_agent_timeout_seconds=300,
                    run_root_override=outside_run,
                    repo_root=repo_root,
                )

            self.assertEqual(agents.draft_rounds, [])
            self.assertEqual(list(outside_run.iterdir()), [])
            self.assertFalse((project_dir / "checkpoint.json").exists())
            self.assertFalse((project_dir / "run.log").exists())

    def test_runner_rechecks_resume_child_paths_before_writes(self) -> None:
        for unsafe_kind in (
            "next_round",
            "future_round",
            "previous_output",
            "state_artifact",
        ):
            with self.subTest(unsafe_kind=unsafe_kind), tempfile.TemporaryDirectory() as tmp:
                repo_root = Path(tmp)
                project_dir = repo_root / "projects" / "selected"
                run_root = project_dir / "runs" / "resume-run"
                run_root.mkdir(parents=True)
                outside_path = repo_root / "outside" / unsafe_kind
                outside_path.parent.mkdir(parents=True)
                start_round = 1
                max_rounds = 1
                if unsafe_kind == "next_round":
                    outside_path.mkdir()
                    (run_root / "round_01").symlink_to(
                        outside_path,
                        target_is_directory=True,
                    )
                elif unsafe_kind == "future_round":
                    outside_path.mkdir()
                    (run_root / "round_02").symlink_to(
                        outside_path,
                        target_is_directory=True,
                    )
                    max_rounds = 2
                elif unsafe_kind == "previous_output":
                    outside_path.write_text("private context\n", encoding="utf-8")
                    previous_round = run_root / "round_01"
                    previous_round.mkdir()
                    (previous_round / "04_judge.md").symlink_to(outside_path)
                    start_round = 2
                else:
                    outside_path.write_text('{"private": true}\n', encoding="utf-8")
                    (run_root / "run_config.json").symlink_to(outside_path)
                outside_bytes = outside_path.read_bytes() if outside_path.is_file() else None
                memory_path = project_dir / "memory.md"
                memory_path.write_text("Manual memory.\n", encoding="utf-8")
                agents = RecordingAgents()

                with self.assertRaises(ResumeHistoryError):
                    run_iterative_rounds(
                        console=Console(),
                        agents=agents,
                        task_text="Design a privacy-aware memory adapter.",
                        project_dir=project_dir,
                        memory_path=memory_path,
                        mode="resume",
                        model_name="fake-model",
                        max_rounds=max_rounds,
                        start_round=start_round,
                        stop_if_no_improvement_rounds=10,
                        global_max_runtime_seconds=60,
                        per_agent_timeout_seconds=300,
                        run_root_override=run_root,
                        repo_root=repo_root,
                    )

                self.assertEqual(agents.draft_rounds, [])
                self.assertFalse((project_dir / "checkpoint.json").exists())
                self.assertFalse((project_dir / "run.log").exists())
                if outside_bytes is not None:
                    self.assertEqual(outside_path.read_bytes(), outside_bytes)
                else:
                    self.assertEqual(list(outside_path.iterdir()), [])

    def test_cli_unsafe_resume_exits_two_and_releases_run_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            temp_root = Path(tmp)
            project_dir = temp_root / "projects" / "selected"
            project_dir.mkdir(parents=True)
            outside_run = temp_root / "outside-run"
            outside_run.mkdir()
            (project_dir / "checkpoint.json").write_text(
                json.dumps(
                    {
                        "run_id": "outside-run",
                        "run_root": str(outside_run),
                        "last_completed_round": 0,
                        "can_resume": True,
                    }
                ),
                encoding="utf-8",
            )
            args = parse_args(
                [
                    "--resume",
                    "--provider",
                    "ollama",
                    "--model",
                    "qwen3:8b",
                    "--project",
                    "selected",
                ]
            )
            project_input = types.SimpleNamespace(
                project_name="selected",
                project_dir=project_dir,
                task_path=project_dir / "task.md",
                task_text="# Resume safety test",
                project_title="Resume safety test",
                source_kind="user_provided",
                as_metadata=lambda: {"project_name": "selected"},
            )

            with (
                patch.object(cli_module, "parse_args", return_value=args),
                patch.object(cli_module, "load_app_config", return_value=AppConfig()),
                patch.object(cli_module, "load_project_input", return_value=project_input),
                patch.object(
                    cli_module,
                    "list_installed_ollama_models",
                    return_value=(["qwen3:8b"], None),
                ),
                patch.object(
                    cli_module,
                    "create_llm_client",
                    return_value=types.SimpleNamespace(timeout_seconds=1),
                ),
            ):
                with self.assertRaisesRegex(SystemExit, "2"):
                    cli_module.main()

            self.assertFalse((project_dir / "active_run.json").exists())
            self.assertFalse((project_dir / "run.log").exists())
            self.assertEqual(list(outside_run.iterdir()), [])

    def test_cli_model_constructor_failures_release_run_lock(self) -> None:
        for failure_stage in ("client", "agents"):
            with self.subTest(stage=failure_stage), tempfile.TemporaryDirectory() as tmp:
                temp_root = Path(tmp)
                project_dir = temp_root / "projects" / "selected"
                project_dir.mkdir(parents=True)
                args = parse_args(
                    [
                        "--diagnostic",
                        "--provider",
                        "ollama",
                        "--model",
                        "qwen3:8b",
                        "--project",
                        "selected",
                    ]
                )
                project_input = types.SimpleNamespace(
                    project_name="selected",
                    project_dir=project_dir,
                    task_path=project_dir / "task.md",
                    task_text="# Constructor failure test",
                    project_title="Constructor failure test",
                    source_kind="user_provided",
                    as_metadata=lambda: {"project_name": "selected"},
                )
                client_result = (
                    RuntimeError("injected client failure")
                    if failure_stage == "client"
                    else types.SimpleNamespace(timeout_seconds=1)
                )

                with (
                    patch.object(cli_module, "parse_args", return_value=args),
                    patch.object(cli_module, "load_app_config", return_value=AppConfig()),
                    patch.object(cli_module, "load_project_input", return_value=project_input),
                    patch.object(
                        cli_module,
                        "list_installed_ollama_models",
                        return_value=(["qwen3:8b"], None),
                    ),
                    patch.object(
                        cli_module,
                        "create_llm_client",
                        side_effect=client_result if isinstance(client_result, Exception) else None,
                        return_value=None
                        if isinstance(client_result, Exception)
                        else client_result,
                    ),
                    patch.object(
                        cli_module.ResearchAgents,
                        "from_prompt_dir",
                        side_effect=RuntimeError("injected agents failure")
                        if failure_stage == "agents"
                        else None,
                    ),
                ):
                    with self.assertRaisesRegex(RuntimeError, f"injected {failure_stage} failure"):
                        cli_module.main()

                self.assertFalse((project_dir / "active_run.json").exists())
                retry_handle, retry_error = cli_module.acquire_run_lock(
                    project_dir,
                    mode="diagnostic",
                    model_name="qwen3:8b",
                )
                self.assertIsNotNone(retry_handle)
                self.assertIsNone(retry_error)
                cli_module.release_run_lock(retry_handle)

    def test_resume_rejects_non_directory_run_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            project_dir = repo_root / "projects" / "selected"
            runs_dir = project_dir / "runs"
            runs_dir.mkdir(parents=True)
            run_root_file = runs_dir / "not-a-directory"
            run_root_file.write_text("sentinel\n", encoding="utf-8")

            preview = build_resume_preview(
                project_dir=project_dir,
                checkpoint={
                    "run_root": str(run_root_file),
                    "last_completed_round": 0,
                    "can_resume": True,
                },
                repo_root=repo_root,
            )

            self.assertFalse(preview["can_resume"])
            self.assertEqual(preview["blocked_reason"], "invalid_run_root")
            self.assertEqual(run_root_file.read_text(encoding="utf-8"), "sentinel\n")
            self.assertNotIn(str(repo_root), preview["message"])

    def test_resume_accepts_run_under_configured_runs_storage_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            project_dir = repo_root / "projects" / "selected"
            project_dir.mkdir(parents=True)
            external_runs = repo_root / "configured-run-storage"
            external_runs.mkdir()
            (project_dir / "runs").symlink_to(external_runs, target_is_directory=True)
            run_root = external_runs / "legacy-run"
            run_root.mkdir()

            preview = build_resume_preview(
                project_dir=project_dir,
                checkpoint={
                    "run_id": "legacy-run",
                    "run_root": str(run_root),
                    "last_completed_round": 0,
                    "can_resume": True,
                },
                repo_root=repo_root,
            )

            self.assertTrue(preview["can_resume"])
            self.assertEqual(Path(preview["run_root"]), run_root.resolve())
            self.assertEqual(preview["next_round_status"], "missing")

    @unittest.skipUnless(hasattr(Path, "symlink_to"), "symlinks are unavailable")
    def test_runner_creates_and_resumes_under_configured_runs_storage_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            project_dir = repo_root / "projects" / "selected"
            project_dir.mkdir(parents=True)
            memory_path = project_dir / "memory.md"
            memory_path.write_text("Manual memory.\n", encoding="utf-8")
            external_runs = repo_root / "configured-run-storage"
            external_runs.mkdir()
            (project_dir / "runs").symlink_to(external_runs, target_is_directory=True)

            first = run_iterative_rounds(
                console=Console(),
                agents=FakeAgents([60]),
                task_text="Design a privacy-aware memory adapter.",
                project_dir=project_dir,
                memory_path=memory_path,
                mode="test",
                model_name="fake-model",
                max_rounds=1,
                stop_if_no_improvement_rounds=10,
                global_max_runtime_seconds=60,
                per_agent_timeout_seconds=300,
                repo_root=repo_root,
            )
            run_root = Path(first["run_root"])
            second = run_iterative_rounds(
                console=Console(),
                agents=FakeAgents([70]),
                task_text="Design a privacy-aware memory adapter.",
                project_dir=project_dir,
                memory_path=memory_path,
                mode="resume",
                model_name="fake-model",
                max_rounds=2,
                stop_if_no_improvement_rounds=10,
                global_max_runtime_seconds=60,
                per_agent_timeout_seconds=300,
                start_round=2,
                run_root_override=run_root,
                initial_best_score=float(first["best_score"]),
                repo_root=repo_root,
            )

            self.assertEqual(run_root.parent, external_runs.resolve())
            for round_index in (1, 2):
                round_dir = run_root / f"round_{round_index:02d}"
                self.assertTrue(round_dir.is_dir())
                for filename in ("01_draft.md", "02_review.md", "03_revised.md", "04_judge.md"):
                    self.assertTrue((round_dir / filename).is_file())
            self.assertEqual(second["completed_rounds"], 2)
            self.assertTrue((project_dir / "checkpoint.json").is_file())

    def test_resume_preview_blocks_unreadable_next_round_without_leaking_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            project_dir = repo_root / "projects" / "selected"
            run_root = project_dir / "runs" / "resume-run"
            next_round = run_root / "round_01"
            next_round.mkdir(parents=True)
            checkpoint = {
                "run_id": "resume-run",
                "run_root": str(run_root),
                "last_completed_round": 0,
                "can_resume": True,
            }

            with patch(
                "src.storage.os.listdir",
                side_effect=PermissionError(str(next_round)),
            ):
                preview = build_resume_preview(
                    project_dir=project_dir,
                    checkpoint=checkpoint,
                    repo_root=repo_root,
                )

            self.assertFalse(preview["can_resume"])
            self.assertEqual(preview["blocked_reason"], "unsafe_round_path")
            self.assertEqual(preview["next_round_status"], "unsafe")
            self.assertNotIn(str(repo_root), preview["message"])

    def test_resume_preview_blocks_inaccessible_root_and_state_file(self) -> None:
        for inaccessible_kind in ("run_root", "run_config"):
            with (
                self.subTest(inaccessible_kind=inaccessible_kind),
                tempfile.TemporaryDirectory() as tmp,
            ):
                repo_root = Path(tmp)
                project_dir = repo_root / "projects" / "selected"
                run_root = project_dir / "runs" / "resume-run"
                run_root.mkdir(parents=True)
                run_config_path = run_root / "run_config.json"
                run_config_path.write_text('{"legacy": true}\n', encoding="utf-8")
                inaccessible_path = (
                    run_root if inaccessible_kind == "run_root" else run_config_path
                ).resolve()

                def fake_access(path: object, mode: int) -> bool:
                    del mode
                    return Path(path).resolve() != inaccessible_path

                with patch("src.resume_safety.os.access", side_effect=fake_access):
                    preview = build_resume_preview(
                        project_dir=project_dir,
                        checkpoint={
                            "run_id": "resume-run",
                            "run_root": str(run_root),
                            "last_completed_round": 0,
                            "can_resume": True,
                        },
                        repo_root=repo_root,
                    )

                self.assertFalse(preview["can_resume"])
                self.assertEqual(
                    preview["blocked_reason"],
                    "inaccessible_run_root"
                    if inaccessible_kind == "run_root"
                    else "unsafe_artifact_path",
                )
                self.assertNotIn(str(repo_root), preview["message"])

    def test_resume_wraps_racing_io_error_without_leaking_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            project_dir = repo_root / "projects" / "selected"
            run_root = project_dir / "runs" / "resume-run"
            run_root.mkdir(parents=True)
            memory_path = project_dir / "memory.md"
            memory_path.write_text("Manual memory.\n", encoding="utf-8")
            (project_dir / "checkpoint.json").write_text(
                json.dumps(
                    {
                        "run_id": "resume-run",
                        "run_root": str(run_root),
                        "last_completed_round": 0,
                        "can_resume": True,
                    }
                ),
                encoding="utf-8",
            )
            console = Console(record=True)
            private_temp_path = repo_root / "outside" / ".run_config.secret.tmp"

            with patch(
                "src.resume.run_iterative_rounds",
                side_effect=PermissionError(str(private_temp_path)),
            ):
                with self.assertRaisesRegex(ResumeHistoryError, "artifact I/O failed") as caught:
                    run_resume_mode(
                        console=console,
                        agents=RecordingAgents(),
                        task_text="Design a privacy-aware memory adapter.",
                        project_dir=project_dir,
                        memory_path=memory_path,
                        model_name="fake-model",
                        max_rounds=1,
                        stop_if_no_improvement_rounds=10,
                        global_max_runtime_seconds=60,
                        per_agent_timeout_seconds=300,
                        repo_root=repo_root,
                    )

            self.assertNotIn(str(repo_root), str(caught.exception))
            self.assertNotIn(str(repo_root), console.export_text(styles=False))

    def test_resume_rejects_escaping_round_symlinks_without_external_reads_or_writes(
        self,
    ) -> None:
        for round_kind, last_completed_round in (("previous", 1), ("next", 0)):
            with self.subTest(round_kind=round_kind), tempfile.TemporaryDirectory() as tmp:
                repo_root = Path(tmp)
                project_dir = repo_root / "projects" / "selected"
                run_root = project_dir / "runs" / "resume-run"
                run_root.mkdir(parents=True)
                outside_round = repo_root / "outside" / round_kind
                outside_round.mkdir(parents=True)
                sentinel_path = outside_round / "04_judge.md"
                sentinel_path.write_text("external private context\n", encoding="utf-8")
                linked_round = run_root / f"round_{1:02d}"
                linked_round.symlink_to(outside_round, target_is_directory=True)
                checkpoint = {
                    "run_id": "resume-run",
                    "run_root": str(run_root),
                    "last_completed_round": last_completed_round,
                    "can_resume": True,
                }
                checkpoint_path = project_dir / "checkpoint.json"
                checkpoint_path.write_text(json.dumps(checkpoint), encoding="utf-8")
                checkpoint_bytes = checkpoint_path.read_bytes()
                memory_path = project_dir / "memory.md"
                memory_path.write_text("Manual memory.\n", encoding="utf-8")
                agents = DraftContextAgents()
                console = Console(record=True)

                preview = build_resume_preview(
                    project_dir=project_dir,
                    checkpoint=checkpoint,
                    repo_root=repo_root,
                )
                resume_started = run_resume_mode(
                    console=console,
                    agents=agents,
                    task_text="Design a privacy-aware memory adapter.",
                    project_dir=project_dir,
                    memory_path=memory_path,
                    model_name="fake-model",
                    max_rounds=1,
                    stop_if_no_improvement_rounds=10,
                    global_max_runtime_seconds=60,
                    per_agent_timeout_seconds=300,
                    repo_root=repo_root,
                )

                self.assertFalse(preview["can_resume"])
                self.assertEqual(preview["blocked_reason"], "unsafe_round_path")
                self.assertFalse(resume_started)
                self.assertEqual(agents.draft_contexts, [])
                self.assertEqual(
                    sentinel_path.read_text(encoding="utf-8"),
                    "external private context\n",
                )
                self.assertEqual(checkpoint_path.read_bytes(), checkpoint_bytes)
                self.assertFalse((run_root / "run_config.json").exists())
                self.assertNotIn(str(repo_root), console.export_text(styles=False))

    def test_resume_rejects_unsafe_state_artifacts_without_reading_them(self) -> None:
        unsafe_artifacts = (
            ("run_config_symlink", "run_config.json", True),
            ("run_manifest_symlink", "run_manifest.json", True),
            ("run_config_directory", "run_config.json", False),
        )
        for case, artifact_name, use_symlink in unsafe_artifacts:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                repo_root = Path(tmp)
                project_dir = repo_root / "projects" / "selected"
                run_root = project_dir / "runs" / "resume-run"
                run_root.mkdir(parents=True)
                external_config = repo_root / "outside" / "private.json"
                external_config.parent.mkdir()
                external_config.write_text('{"private": "sentinel"}\n', encoding="utf-8")
                artifact_path = run_root / artifact_name
                if use_symlink:
                    artifact_path.symlink_to(external_config)
                else:
                    artifact_path.mkdir()
                checkpoint = {
                    "run_id": "resume-run",
                    "run_root": str(run_root),
                    "last_completed_round": 0,
                    "can_resume": True,
                }
                checkpoint_path = project_dir / "checkpoint.json"
                checkpoint_path.write_text(json.dumps(checkpoint), encoding="utf-8")
                memory_path = project_dir / "memory.md"
                memory_path.write_text("Manual memory.\n", encoding="utf-8")
                agents = RecordingAgents()

                preview = build_resume_preview(
                    project_dir=project_dir,
                    checkpoint=checkpoint,
                    repo_root=repo_root,
                )
                resume_started = run_resume_mode(
                    console=Console(),
                    agents=agents,
                    task_text="Design a privacy-aware memory adapter.",
                    project_dir=project_dir,
                    memory_path=memory_path,
                    model_name="fake-model",
                    max_rounds=1,
                    stop_if_no_improvement_rounds=10,
                    global_max_runtime_seconds=60,
                    per_agent_timeout_seconds=300,
                    repo_root=repo_root,
                )

                self.assertFalse(preview["can_resume"])
                self.assertEqual(preview["blocked_reason"], "unsafe_artifact_path")
                self.assertFalse(resume_started)
                self.assertEqual(agents.draft_rounds, [])
                self.assertEqual(
                    external_config.read_text(encoding="utf-8"),
                    '{"private": "sentinel"}\n',
                )
                self.assertEqual(artifact_path.is_symlink(), use_symlink)

    def test_resume_preserves_history_best_round_and_previous_round_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "project"
            project_dir.mkdir()
            run_root = project_dir / "runs" / "resume-run"
            run_root.mkdir(parents=True)
            memory_path = project_dir / "memory.md"
            memory_path.write_text("Manual memory.\n", encoding="utf-8")
            best_output_path = project_dir / "best_output.md"
            best_output_path.write_text("Trusted round 2 best.\n", encoding="utf-8")

            round_outputs = {
                1: ("draft one", "review one", "revised one", "judge one"),
                2: ("draft two", "review two", "revised two", "judge two"),
                3: ("draft three", "review three", "revised three", "judge three"),
            }
            for round_index, outputs in round_outputs.items():
                round_dir = run_root / f"round_{round_index:02d}"
                round_dir.mkdir()
                for filename, content in zip(
                    ("01_draft.md", "02_review.md", "03_revised.md", "04_judge.md"),
                    outputs,
                    strict=True,
                ):
                    (round_dir / filename).write_text(f"{content}\n", encoding="utf-8")

            historical_metrics = [
                {
                    "round": 1,
                    "score": 80.0,
                    "improved": True,
                    "non_improve_streak": 0,
                    "successful_research_round": True,
                    "timeout_this_round": False,
                    "provider_failure_this_round": False,
                    "invalid_score_this_round": False,
                    "errors": [],
                    "agent_timings_seconds": {"draft": 1.0},
                    "estimated_input_tokens": 40,
                    "estimated_output_tokens": 60,
                    "estimated_total_tokens": 100,
                },
                {
                    "round": 2,
                    "score": 93.0,
                    "improved": True,
                    "non_improve_streak": 0,
                    "successful_research_round": True,
                    "timeout_this_round": False,
                    "provider_failure_this_round": False,
                    "invalid_score_this_round": False,
                    "errors": [],
                    "agent_timings_seconds": {"draft": 2.0},
                    "estimated_input_tokens": 80,
                    "estimated_output_tokens": 120,
                    "estimated_total_tokens": 200,
                },
                {
                    "round": 3,
                    "score": 85.0,
                    "improved": False,
                    "non_improve_streak": 1,
                    "successful_research_round": True,
                    "timeout_this_round": False,
                    "provider_failure_this_round": False,
                    "invalid_score_this_round": False,
                    "errors": [],
                    "agent_timings_seconds": {"draft": 3.0},
                    "estimated_input_tokens": 120,
                    "estimated_output_tokens": 180,
                    "estimated_total_tokens": 300,
                },
            ]
            (run_root / "round_metrics.json").write_text(
                json.dumps(historical_metrics), encoding="utf-8"
            )
            (project_dir / "score_history.json").write_text(
                json.dumps(historical_metrics), encoding="utf-8"
            )
            (run_root / "run_config.json").write_text(
                json.dumps(
                    {
                        "run_id": "resume-run",
                        "started_at": "2026-07-10T00:00:00+00:00",
                        "completed_rounds": 3,
                        "best_score": 93.0,
                        "best_round": 2,
                        "total_runtime_seconds": 12.5,
                        "resume_sessions": [],
                    }
                ),
                encoding="utf-8",
            )
            (run_root / "run_summary.json").write_text(
                json.dumps(
                    {
                        "run_id": "resume-run",
                        "completed_rounds": 3,
                        "round_count": 3,
                        "best_score": 100.0,
                        "best_round": 3,
                        "total_runtime_seconds": 12.5,
                    }
                ),
                encoding="utf-8",
            )
            (project_dir / "checkpoint.json").write_text(
                json.dumps(
                    {
                        "run_id": "resume-run",
                        "run_root": str(run_root),
                        "last_completed_round": 3,
                        "best_score": 80.0,
                        "best_round": 4,
                        "best_round_path": str(run_root / "round_04"),
                        "last_successful_agent": "judge",
                        "can_resume": True,
                    }
                ),
                encoding="utf-8",
            )
            agents = DraftContextAgents()

            run_resume_mode(
                console=Console(),
                agents=agents,
                task_text="Design a privacy-aware memory adapter.",
                project_dir=project_dir,
                memory_path=memory_path,
                model_name="fake-model",
                max_rounds=4,
                stop_if_no_improvement_rounds=2,
                global_max_runtime_seconds=60,
                per_agent_timeout_seconds=300,
                drafting_mode="continue_from_previous_draft",
            )

            round_metrics = json.loads(
                (run_root / "round_metrics.json").read_text(encoding="utf-8")
            )
            score_history = json.loads(
                (project_dir / "score_history.json").read_text(encoding="utf-8")
            )
            checkpoint = json.loads((project_dir / "checkpoint.json").read_text(encoding="utf-8"))
            run_config = json.loads((run_root / "run_config.json").read_text(encoding="utf-8"))
            run_summary = json.loads((run_root / "run_summary.json").read_text(encoding="utf-8"))

            self.assertEqual(round_metrics[:3], historical_metrics)
            self.assertEqual(score_history[:3], historical_metrics)
            self.assertEqual([entry["round"] for entry in round_metrics], [1, 2, 3, 4])
            self.assertEqual([entry["round"] for entry in score_history], [1, 2, 3, 4])
            self.assertEqual(round_metrics, score_history)
            self.assertEqual(round_metrics[-1]["non_improve_streak"], 2)
            self.assertTrue(round_metrics[-1]["evolution_metrics"]["has_previous_round"])
            self.assertEqual(
                round_metrics[-1]["evolution_metrics"]["score_delta_vs_previous"], -35.0
            )

            self.assertEqual(len(agents.draft_contexts), 1)
            self.assertEqual(agents.draft_contexts[0]["previous_judge"], "judge three")
            self.assertEqual(agents.draft_contexts[0]["previous_review"], "review three")
            self.assertEqual(agents.draft_contexts[0]["previous_draft"], "draft three")
            self.assertEqual(agents.draft_contexts[0]["previous_revised"], "revised three")

            self.assertEqual(checkpoint["last_completed_round"], 4)
            self.assertEqual(checkpoint["best_score"], 93.0)
            self.assertEqual(checkpoint["best_round"], 2)
            self.assertEqual(checkpoint["best_round_path"], str((run_root / "round_02").resolve()))
            self.assertEqual(checkpoint["last_successful_agent"], "judge")
            self.assertEqual(checkpoint["stop_reason"], STOP_NO_IMPROVEMENT)
            self.assertEqual(run_config["completed_rounds"], 4)
            self.assertEqual(run_config["best_round"], 2)
            self.assertTrue(run_config["resume_metadata"]["best_score_reconciled"])
            self.assertGreaterEqual(run_config["total_runtime_seconds"], 12.5)
            self.assertEqual(run_summary["completed_rounds"], 4)
            self.assertEqual(run_summary["round_count"], 4)
            self.assertEqual(run_summary["best_round"], 2)
            self.assertEqual(run_summary["stop_reason"], STOP_NO_IMPROVEMENT)
            self.assertEqual(run_summary["successful_rounds"], [1, 2, 3, 4])
            self.assertGreaterEqual(run_summary["total_runtime_seconds"], 12.5)
            self.assertGreater(run_summary["total_estimated_tokens"], 600)
            comparison_summary = load_run_summary(run_root)
            analysis = analyze_run(run_root)
            self.assertEqual(comparison_summary["completed_rounds"], 4)
            self.assertEqual(comparison_summary["round_count"], 4)
            self.assertEqual(comparison_summary["average_score"], 77.0)
            self.assertEqual(analysis["score"]["first_round"], 1)
            self.assertEqual(analysis["score"]["latest_round"], 4)
            self.assertEqual(analysis["score"]["score_delta_first_to_latest"], -30.0)
            self.assertEqual(
                best_output_path.read_text(encoding="utf-8"), "Trusted round 2 best.\n"
            )
            self.assertEqual(
                (run_root / "round_03" / "03_revised.md").read_text(encoding="utf-8"),
                "revised three\n",
            )

    def test_resume_uses_project_score_history_for_legacy_run_without_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "project"
            project_dir.mkdir()
            run_root = project_dir / "runs" / "legacy-resume-run"
            previous_round_dir = run_root / "round_01"
            previous_round_dir.mkdir(parents=True)
            (previous_round_dir / "04_judge.md").write_text("legacy judge\n", encoding="utf-8")
            memory_path = project_dir / "memory.md"
            memory_path.write_text("Manual memory.\n", encoding="utf-8")
            (project_dir / "best_output.md").write_text("Legacy best.\n", encoding="utf-8")
            legacy_entry = {
                "round": "1",
                "score": "80",
                "improved": True,
                "non_improve_streak": 0,
                "successful_research_round": True,
                "legacy_marker": {"preserve": True},
            }
            (project_dir / "score_history.json").write_text(
                json.dumps([legacy_entry]), encoding="utf-8"
            )
            (project_dir / "checkpoint.json").write_text(
                json.dumps(
                    {
                        "run_id": "legacy-resume-run",
                        "run_root": str(run_root),
                        "last_completed_round": 1,
                        "best_score": 80.0,
                        "best_round_path": str(previous_round_dir),
                        "can_resume": True,
                    }
                ),
                encoding="utf-8",
            )

            run_resume_mode(
                console=Console(),
                agents=RecordingAgents(),
                task_text="Design a privacy-aware memory adapter.",
                project_dir=project_dir,
                memory_path=memory_path,
                model_name="fake-model",
                max_rounds=2,
                stop_if_no_improvement_rounds=10,
                global_max_runtime_seconds=60,
                per_agent_timeout_seconds=300,
            )

            round_metrics = json.loads(
                (run_root / "round_metrics.json").read_text(encoding="utf-8")
            )
            score_history = json.loads(
                (project_dir / "score_history.json").read_text(encoding="utf-8")
            )
            run_config = json.loads((run_root / "run_config.json").read_text(encoding="utf-8"))
            run_summary = json.loads((run_root / "run_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(round_metrics[0], legacy_entry)
            self.assertEqual(score_history[0], legacy_entry)
            self.assertEqual([entry["round"] for entry in round_metrics], ["1", 2])
            self.assertEqual([entry["round"] for entry in score_history], ["1", 2])
            self.assertEqual(
                round_metrics[-1]["evolution_metrics"]["score_delta_vs_previous"], -16.0
            )
            self.assertEqual(run_summary["round_count"], 2)
            self.assertEqual(run_summary["best_round"], 1)
            self.assertEqual(run_config["resume_metadata"]["history_status"], "complete")
            self.assertEqual(
                run_config["resume_metadata"]["round_metrics_source"],
                "score_history_fallback",
            )

    def test_resume_stop_before_new_round_does_not_rewind_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "project"
            project_dir.mkdir()
            run_root = project_dir / "runs" / "resume-run"
            run_root.mkdir(parents=True)
            memory_path = project_dir / "memory.md"
            memory_path.write_text("Manual memory.\n", encoding="utf-8")
            (project_dir / "best_output.md").write_text("Trusted best.\n", encoding="utf-8")
            historical_metrics = [
                {
                    "round": round_index,
                    "score": score,
                    "improved": round_index == 2,
                    "non_improve_streak": 1 if round_index == 3 else 0,
                    "successful_research_round": True,
                    "errors": [],
                }
                for round_index, score in ((1, 80.0), (2, 93.0), (3, 85.0))
            ]
            history_bytes = json.dumps(historical_metrics).encode()
            (run_root / "round_metrics.json").write_bytes(history_bytes)
            (project_dir / "score_history.json").write_bytes(history_bytes)
            (run_root / "run_config.json").write_text(
                json.dumps(
                    {
                        "run_id": "resume-run",
                        "started_at": "2026-07-10T00:00:00+00:00",
                        "completed_rounds": 3,
                        "best_score": 93.0,
                        "best_round": 2,
                        "total_runtime_seconds": 7.5,
                        "resume_sessions": [],
                    }
                ),
                encoding="utf-8",
            )
            (run_root / "run_summary.json").write_text(
                json.dumps(
                    {
                        "run_id": "resume-run",
                        "completed_rounds": 3,
                        "round_count": 3,
                        "best_score": 93.0,
                        "best_round": 2,
                        "total_runtime_seconds": 7.5,
                    }
                ),
                encoding="utf-8",
            )
            (project_dir / "checkpoint.json").write_text(
                json.dumps(
                    {
                        "run_id": "resume-run",
                        "run_root": str(run_root),
                        "last_completed_round": 3,
                        "best_score": 93.0,
                        "best_round_path": str(run_root / "round_02"),
                        "last_successful_agent": "judge",
                        "can_resume": True,
                    }
                ),
                encoding="utf-8",
            )
            (project_dir / "STOP_REQUESTED").write_text("STOP_REQUESTED\n", encoding="utf-8")
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
            run_config = json.loads((run_root / "run_config.json").read_text(encoding="utf-8"))
            run_summary = json.loads((run_root / "run_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(agents.draft_rounds, [])
            self.assertFalse((run_root / "round_04").exists())
            self.assertEqual((run_root / "round_metrics.json").read_bytes(), history_bytes)
            self.assertEqual((project_dir / "score_history.json").read_bytes(), history_bytes)
            self.assertEqual(checkpoint["last_completed_round"], 3)
            self.assertEqual(checkpoint["best_round"], 2)
            self.assertEqual(checkpoint["best_round_path"], str((run_root / "round_02").resolve()))
            self.assertEqual(checkpoint["stop_reason"], STOP_USER_REQUESTED)
            self.assertEqual(checkpoint["last_successful_agent"], "judge")
            self.assertEqual(run_config["completed_rounds"], 3)
            self.assertEqual(run_config["best_round"], 2)
            self.assertEqual(run_summary["completed_rounds"], 3)
            self.assertEqual(run_summary["round_count"], 3)
            self.assertEqual(run_summary["best_round"], 2)

    def test_history_best_round_prefers_the_strict_improvement_on_tied_scores(self) -> None:
        history = [
            {"round": 1, "score": 80.0, "improved": True},
            {"round": 2, "score": 93.0, "improved": True},
            {"round": 3, "score": 93.0, "improved": False},
        ]
        self.assertEqual(_history_best_round(history, 93.0), 2)
        self.assertEqual(
            _history_best_round(
                [
                    {"round": 1, "score": 93.0},
                    {"round": 2, "score": 93.0},
                ],
                93.0,
            ),
            1,
        )

    def test_unsafe_resume_histories_fail_before_writing_any_artifact(self) -> None:
        valid_round_one = b'[{"round": 1, "score": 80}]'
        deeply_nested_value = b'{"nested":' * 150 + b"0" + b"}" * 150
        unsafe_histories = {
            "invalid_json": (b'{"not": "complete"', valid_round_one, 80.0),
            "invalid_utf8": (b"\xff\xfe", valid_round_one, 80.0),
            "huge_integer": (
                b'[{"round": ' + b"9" * 5000 + b"}]",
                valid_round_one,
                80.0,
            ),
            "deep_json": (b"[" * 2000 + b"0" + b"]" * 2000, valid_round_one, 80.0),
            "deep_history_value": (
                b'[{"round": 1, "details": ' + deeply_nested_value + b"}]",
                valid_round_one,
                80.0,
            ),
            "wrong_type": (b'{"round": 1}', valid_round_one, 80.0),
            "duplicate_round": (
                b'[{"round": 1}, {"round": 1}]',
                valid_round_one,
                80.0,
            ),
            "future_round": (
                b'[{"round": 1}, {"round": 2}]',
                valid_round_one,
                80.0,
            ),
            "different_round_sequences": (valid_round_one, b"[]", 80.0),
            "same_round_conflicting_fields": (
                b'[{"round": 1, "score": 80, "successful_research_round": false}]',
                b'[{"round": 1, "score": 80, "successful_research_round": true}]',
                80.0,
            ),
            "same_round_bool_int_conflict": (
                b'[{"round": 1, "score": 80, "successful_research_round": true}]',
                b'[{"round": 1, "score": 80, "successful_research_round": 1}]',
                80.0,
            ),
            "nested_bool_int_conflict": (
                b'[{"round": 1, "score": 80, "agent_io_metrics": {"draft": {"called": true}}}]',
                b'[{"round": 1, "score": 80, "agent_io_metrics": {"draft": {"called": 1}}}]',
                80.0,
            ),
            "list_bool_int_conflict": (
                b'[{"round": 1, "score": 80, "errors": [true]}]',
                b'[{"round": 1, "score": 80, "errors": [1]}]',
                80.0,
            ),
            "unsupported_checkpoint_best": (valid_round_one, valid_round_one, 90.0),
        }
        for case, (
            round_metrics_content,
            score_history_content,
            checkpoint_best_score,
        ) in unsafe_histories.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                project_dir = Path(tmp) / "project"
                project_dir.mkdir()
                run_root = project_dir / "runs" / "resume-run"
                run_root.mkdir(parents=True)
                memory_path = project_dir / "memory.md"
                memory_path.write_text("Manual memory.\n", encoding="utf-8")
                artifact_contents = {
                    run_root / "round_metrics.json": round_metrics_content,
                    project_dir / "score_history.json": score_history_content,
                    run_root / "run_config.json": b'{"run_id": "resume-run"}',
                    run_root / "run_summary.json": b'{"completed_rounds": 1}',
                    run_root / "run_manifest.json": b'{"legacy_field": "preserve"}',
                    project_dir / "checkpoint.json": json.dumps(
                        {
                            "run_id": "resume-run",
                            "run_root": str(run_root),
                            "last_completed_round": 1,
                            "best_score": checkpoint_best_score,
                            "best_round_path": str(run_root / "round_01"),
                            "can_resume": True,
                        }
                    ).encode(),
                }
                for path, content in artifact_contents.items():
                    path.write_bytes(content)
                agents = RecordingAgents()
                console = Console(record=True)

                with self.assertRaises(ResumeHistoryError) as caught:
                    run_resume_mode(
                        console=console,
                        agents=agents,
                        task_text="Design a privacy-aware memory adapter.",
                        project_dir=project_dir,
                        memory_path=memory_path,
                        model_name="fake-model",
                        max_rounds=2,
                        stop_if_no_improvement_rounds=10,
                        global_max_runtime_seconds=60,
                        per_agent_timeout_seconds=300,
                    )

                self.assertEqual(agents.draft_rounds, [])
                self.assertFalse((run_root / "round_02").exists())
                for path, content in artifact_contents.items():
                    self.assertEqual(path.read_bytes(), content)
                if hasattr(console, "export_text"):
                    output = " ".join(console.export_text().split())
                    self.assertIn("Cannot resume safely", output)
                    if case == "unsupported_checkpoint_best":
                        self.assertIn("checkpoint best_score", output)
                    else:
                        self.assertIn("round_metrics.json", output)
                    self.assertNotIn(str(Path(tmp)), output)
                self.assertNotIn(str(Path(tmp)), str(caught.exception))

    def test_legacy_score_history_fallback_must_not_exceed_checkpoint_best(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            score_history_path = root / "score_history.json"
            round_metrics_path = root / "run" / "round_metrics.json"
            score_history_path.write_text(
                '[{"round": 1, "score": 90, "successful_research_round": true}]',
                encoding="utf-8",
            )

            for checkpoint_best_score in (80.0, 100.0, None):
                with self.subTest(checkpoint_best_score=checkpoint_best_score):
                    with self.assertRaisesRegex(ResumeHistoryError, "checkpoint best_score"):
                        _load_resume_histories(
                            score_history_path=score_history_path,
                            round_metrics_path=round_metrics_path,
                            start_round=2,
                            checkpoint_best_score=checkpoint_best_score,
                        )

            self.assertFalse(round_metrics_path.exists())

    def test_partial_history_without_best_metadata_preserves_existing_best(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "project"
            project_dir.mkdir()
            run_root = project_dir / "runs" / "resume-run"
            run_root.mkdir(parents=True)
            memory_path = project_dir / "memory.md"
            memory_path.write_text("Manual memory.\n", encoding="utf-8")
            artifact_contents = {
                run_root / "round_metrics.json": b'[{"round": 1, "score": 50}]',
                project_dir / "score_history.json": b'[{"round": 1, "score": 50}]',
                project_dir / "best_output.md": b"Trusted missing-round best.\n",
                run_root / "run_config.json": b'{"run_id": "resume-run"}',
                run_root / "run_summary.json": b'{"completed_rounds": 2}',
                project_dir / "checkpoint.json": json.dumps(
                    {
                        "run_id": "resume-run",
                        "run_root": str(run_root),
                        "last_completed_round": 2,
                        "can_resume": True,
                    }
                ).encode(),
            }
            for path, content in artifact_contents.items():
                path.write_bytes(content)

            with self.assertRaisesRegex(ResumeHistoryError, "partial history"):
                run_resume_mode(
                    console=Console(),
                    agents=RecordingAgents(),
                    task_text="Design a privacy-aware memory adapter.",
                    project_dir=project_dir,
                    memory_path=memory_path,
                    model_name="fake-model",
                    max_rounds=3,
                    stop_if_no_improvement_rounds=10,
                    global_max_runtime_seconds=60,
                    per_agent_timeout_seconds=300,
                )

            self.assertFalse((run_root / "round_03").exists())
            for path, content in artifact_contents.items():
                self.assertEqual(path.read_bytes(), content)

    def test_resume_blocks_partial_next_round_without_overwriting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "project"
            project_dir.mkdir()
            run_root = project_dir / "runs" / "resume-run"
            run_root.mkdir(parents=True)
            partial_round_dir = run_root / "round_04"
            partial_round_dir.mkdir()
            partial_draft_path = partial_round_dir / "01_draft.md"
            partial_draft_path.write_text("partial draft should stay\n", encoding="utf-8")
            memory_path = project_dir / "memory.md"
            memory_path.write_text("Manual memory.\n", encoding="utf-8")
            checkpoint = {
                "run_id": "resume-run",
                "run_root": str(run_root),
                "last_completed_round": 3,
                "best_score": 93.0,
                "can_resume": True,
            }
            (project_dir / "checkpoint.json").write_text(
                json.dumps(checkpoint),
                encoding="utf-8",
            )
            preview = build_resume_preview(
                project_dir=project_dir,
                checkpoint=checkpoint,
                repo_root=Path(tmp),
            )
            agents = RecordingAgents()
            console = Console(record=True)

            resume_started = run_resume_mode(
                console=console,
                agents=agents,
                task_text="Design a privacy-aware memory adapter.",
                project_dir=project_dir,
                memory_path=memory_path,
                model_name="fake-model",
                max_rounds=4,
                stop_if_no_improvement_rounds=10,
                global_max_runtime_seconds=60,
                per_agent_timeout_seconds=300,
                repo_root=Path(tmp),
            )

            self.assertFalse(preview["can_resume"])
            self.assertFalse(resume_started)
            self.assertEqual(preview["blocked_reason"], "partial_next_round_exists")
            self.assertEqual(preview["next_round_status"], "partial")
            self.assertEqual(preview["next_round_safety_action"], "fail_safe_require_user_action")
            self.assertEqual(agents.draft_rounds, [])
            self.assertEqual(
                partial_draft_path.read_text(encoding="utf-8"),
                "partial draft should stay\n",
            )
            self.assertFalse((run_root / "run_config.json").exists())
            checkpoint_after = json.loads(
                (project_dir / "checkpoint.json").read_text(encoding="utf-8")
            )
            self.assertEqual(checkpoint_after["last_completed_round"], 3)
            if hasattr(console, "export_text"):
                output = " ".join(console.export_text().split())
                self.assertIn("Cannot resume", output)
                self.assertIn("already contains files", output)

    def test_resume_preview_reports_missing_and_stale_checkpoints(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            project_dir = repo_root / "project"
            project_dir.mkdir()
            missing_preview = build_resume_preview(
                project_dir=project_dir,
                checkpoint={},
                repo_root=repo_root,
            )
            invalid_round_previews = [
                build_resume_preview(
                    project_dir=project_dir,
                    checkpoint={
                        "can_resume": True,
                        "run_root": str(project_dir / "runs" / "invalid-run"),
                        "last_completed_round": invalid_round,
                    },
                    repo_root=repo_root,
                )
                for invalid_round in (-1, -0.5, 1.5, True)
            ]
            stale_preview = build_resume_preview(
                project_dir=project_dir,
                checkpoint={
                    "can_resume": True,
                    "run_root": str(project_dir / "runs" / "missing-run"),
                    "last_completed_round": "2",
                    "stop_reason": "USER_REQUESTED",
                },
                repo_root=repo_root,
            )
            run_root = project_dir / "runs" / "partial-run"
            run_root.mkdir(parents=True)
            partial_dir = run_root / "round_03"
            partial_dir.mkdir()
            (partial_dir / "01_draft.md").write_text("partial", encoding="utf-8")
            partial_preview = build_resume_preview(
                project_dir=project_dir,
                checkpoint={
                    "can_resume": True,
                    "run_root": str(run_root),
                    "last_completed_round": 2,
                    "stop_reason": "USER_REQUESTED",
                },
                repo_root=repo_root,
            )

        self.assertFalse(missing_preview["can_resume"])
        self.assertEqual(missing_preview["blocked_reason"], "missing_checkpoint")
        for invalid_round_preview in invalid_round_previews:
            self.assertFalse(invalid_round_preview["can_resume"])
            self.assertEqual(
                invalid_round_preview["blocked_reason"], "invalid_last_completed_round"
            )
        self.assertFalse(stale_preview["can_resume"])
        self.assertEqual(stale_preview["blocked_reason"], "stale_run_root")
        self.assertEqual(stale_preview["next_round"], 3)
        self.assertEqual(stale_preview["run_root_display"], "project/runs/missing-run")
        self.assertFalse(partial_preview["can_resume"])
        self.assertEqual(partial_preview["blocked_reason"], "partial_next_round_exists")
        self.assertEqual(partial_preview["next_round_status"], "partial")


if __name__ == "__main__":
    unittest.main()
