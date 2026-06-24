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
from src.constants import (
    STOP_CLOUD_DAILY_QUOTA,
    STOP_MAX_ROUNDS,
    STOP_OLLAMA_TIMEOUT,
    STOP_PROVIDER_QUOTA_EXHAUSTED,
    STOP_USER_REQUESTED,
)
from src.resume import build_resume_preview, run_resume_mode
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


class RoundLoopTests(unittest.TestCase):
    def test_main_reexports_backward_compatible_api(self) -> None:
        self.assertIs(main_module.run_iterative_rounds, run_iterative_rounds)
        self.assertEqual(main_module.STOP_MAX_ROUNDS, STOP_MAX_ROUNDS)
        self.assertTrue(callable(main_module.parse_args))
        self.assertTrue(callable(main_module.run_diagnostic_mode))
        self.assertTrue(callable(main_module.run_session_mode))

    def test_parse_args_accepts_mode_and_model_flags(self) -> None:
        args = parse_args(
            [
                "--diagnostic",
                "--survey",
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

            run_resume_mode(
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

            run_resume_mode(
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
        self.assertFalse(stale_preview["can_resume"])
        self.assertEqual(stale_preview["blocked_reason"], "stale_run_root")
        self.assertEqual(stale_preview["next_round"], 3)
        self.assertEqual(stale_preview["run_root_display"], "project/runs/missing-run")
        self.assertFalse(partial_preview["can_resume"])
        self.assertEqual(partial_preview["blocked_reason"], "partial_next_round_exists")
        self.assertEqual(partial_preview["next_round_status"], "partial")


if __name__ == "__main__":
    unittest.main()
