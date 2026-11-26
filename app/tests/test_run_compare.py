from __future__ import annotations

import json
import sys
import tempfile
import unittest
from argparse import Namespace
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

from rich.console import Console

from src.cli import _run_compare_cli, parse_args
from src.run_analytics import analyze_run
from src.run_compare import compare_runs, load_run_summary, write_run_comparison
from src.runner import run_iterative_rounds


class RunCompareTests(unittest.TestCase):
    @staticmethod
    def _reject_json_constant(value: str) -> None:
        raise ValueError(f"non-standard JSON constant: {value}")

    def test_safe_run_loading_treats_invalid_utf8_as_missing_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "run"
            run_root.mkdir()
            (run_root / "run_summary.json").write_bytes(b"\xff\xfe")

            summary = load_run_summary(run_root, safe_artifacts=True)

            self.assertEqual(summary["metadata_status"], "missing")
            self.assertIsNone(summary["best_score"])

    @unittest.skipUnless(hasattr(Path, "symlink_to"), "symlinks are unavailable")
    def test_explicit_run_alias_and_output_parent_symlink_remain_authorized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            physical_run = root / "physical-run"
            physical_run.mkdir()
            (physical_run / "run_config.json").write_text(
                json.dumps(
                    {
                        "run_id": "canonical-run",
                        "model": {"provider": "mock", "name": "expected-model"},
                        "runtime": {"max_rounds": 3},
                    }
                ),
                encoding="utf-8",
            )
            (physical_run / "run_summary.json").write_text(
                json.dumps({"run_id": "canonical-run", "best_score": 77}),
                encoding="utf-8",
            )
            run_alias = root / "run-alias"
            run_alias.symlink_to(physical_run, target_is_directory=True)
            outside_output = root / "outside-output"
            outside_output.mkdir()
            linked_output = root / "linked-output"
            linked_output.symlink_to(outside_output, target_is_directory=True)

            summary = load_run_summary(run_alias)
            comparison = write_run_comparison(
                [run_alias],
                linked_output / "comparison.json",
            )

            self.assertEqual(summary["run_id"], "canonical-run")
            self.assertEqual(summary["provider"], "mock")
            self.assertEqual(summary["model"], "expected-model")
            self.assertEqual(summary["max_rounds"], 3)
            self.assertEqual(
                json.loads((outside_output / "comparison.json").read_text(encoding="utf-8")),
                comparison,
            )

    def test_cli_rejects_a_single_compare_run(self) -> None:
        stderr = StringIO()

        with redirect_stderr(stderr), self.assertRaises(SystemExit) as raised:
            parse_args(["--compare-runs", "runs/only"])

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("--compare-runs requires at least two RUN_DIR arguments", stderr.getvalue())

    def test_cli_accepts_two_or_more_compare_runs(self) -> None:
        args = parse_args(["--compare-runs", "runs/a", "runs/b", "runs/c"])

        self.assertEqual(args.compare_runs, ["runs/a", "runs/b", "runs/c"])

    def test_compare_runs_ranks_by_best_score_and_writes_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_a = root / "run-a"
            run_b = root / "run-b"
            run_a.mkdir()
            run_b.mkdir()
            (run_a / "run_summary.json").write_text(
                json.dumps(
                    {
                        "run_id": "run-a",
                        "model": "qwen3:8b",
                        "best_score": 72.0,
                        "completed_rounds": 2,
                        "drafting_mode": "best_guided",
                        "timeout_rounds": [2],
                        "total_agent_elapsed_seconds": 5.25,
                        "total_estimated_tokens": 123,
                        "avg_revised_similarity_to_previous": 0.82,
                        "low_previous_revised_change_rounds": [2],
                        "rubric_round_count": 2,
                        "rubric_subscore_averages": {
                            "evaluation_design_quality": 11,
                            "tomorrow_actionability": 14,
                        },
                    }
                ),
                encoding="utf-8",
            )
            (run_a / "run_config.json").write_text(
                json.dumps(
                    {
                        "model": {"provider": "ollama", "name": "qwen3:8b"},
                        "runtime": {"max_rounds": 3},
                    }
                ),
                encoding="utf-8",
            )
            (run_a / "round_metrics.json").write_text(
                json.dumps([{"round": 1, "score": 70.0}, {"round": 2, "score": 72.0}]),
                encoding="utf-8",
            )
            (run_b / "run_summary.json").write_text(
                json.dumps(
                    {
                        "run_id": "run-b",
                        "best_score": 84.0,
                        "completed_rounds": 2,
                        "drafting_mode": "fresh_from_task_with_review",
                    }
                ),
                encoding="utf-8",
            )
            output_path = root / "comparison.json"

            comparison = write_run_comparison([run_a, run_b], output_path)

            self.assertEqual(comparison["best_run_id"], "run-b")
            self.assertEqual(comparison["best_vs_baseline_delta"], 12.0)
            self.assertEqual(comparison["runs"][0]["provider"], "ollama")
            self.assertEqual(comparison["runs"][0]["max_rounds"], 3)
            self.assertEqual(comparison["runs"][0]["average_score"], 71.0)
            self.assertEqual(comparison["runs"][0]["timeout_count"], 1)
            self.assertEqual(comparison["runs"][0]["total_agent_elapsed_seconds"], 5.25)
            self.assertEqual(comparison["runs"][0]["total_estimated_tokens"], 123)
            self.assertEqual(comparison["runs"][0]["avg_revised_similarity_to_previous"], 0.82)
            self.assertEqual(comparison["runs"][0]["low_previous_revised_change_count"], 1)
            self.assertEqual(comparison["runs"][0]["rubric_round_count"], 2)
            self.assertEqual(comparison["runs"][0]["rubric_avg_evaluation"], 11.0)
            self.assertEqual(comparison["runs"][0]["rubric_avg_actionability"], 14.0)
            self.assertEqual(comparison["runs"][0]["metadata_status"], "ok")
            self.assertEqual(json.loads(output_path.read_text(encoding="utf-8")), comparison)

    def test_load_run_summary_falls_back_to_run_config_and_round_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "legacy-run"
            run_root.mkdir()
            (run_root / "run_config.json").write_text(
                json.dumps(
                    {
                        "run_id": "legacy-run",
                        "mode": "normal",
                        "drafting_mode": "best_guided",
                        "model": {"label": "fake-model"},
                    }
                ),
                encoding="utf-8",
            )
            (run_root / "round_metrics.json").write_text(
                json.dumps(
                    [
                        {
                            "round": 1,
                            "score": 70.0,
                            "successful_research_round": True,
                            "agent_timings_seconds": {"draft": 1.0, "review": 0.5},
                            "estimated_input_tokens": 10,
                            "estimated_output_tokens": 4,
                            "estimated_total_tokens": 14,
                        },
                        {
                            "round": 2,
                            "score": 75.0,
                            "timeout_this_round": True,
                            "agent_timings_seconds": {"draft": 2.0},
                            "evolution_metrics": {
                                "draft_to_revised_similarity": 0.8,
                                "revised_similarity_to_previous": 0.96,
                                "judge_similarity_to_previous": 0.5,
                            },
                            "judge_rubric": {
                                "evaluation_design_quality": 12,
                                "tomorrow_actionability": 15,
                            },
                        },
                    ]
                ),
                encoding="utf-8",
            )

            summary = load_run_summary(run_root)
            comparison = compare_runs([run_root])

        self.assertEqual(summary["best_score"], 75.0)
        self.assertEqual(summary["successful_rounds"], [1])
        self.assertEqual(summary["timeout_rounds"], [2])
        self.assertEqual(summary["average_score"], 72.5)
        self.assertEqual(summary["total_agent_elapsed_seconds"], 3.5)
        self.assertEqual(summary["total_estimated_tokens"], 14)
        self.assertEqual(summary["avg_revised_similarity_to_previous"], 0.96)
        self.assertEqual(summary["low_previous_revised_change_count"], 1)
        self.assertEqual(summary["rubric_round_count"], 1)
        self.assertEqual(summary["rubric_avg_evaluation"], 12.0)
        self.assertEqual(comparison["best_run_id"], "legacy-run")

    def test_average_score_preserves_existing_rounding_for_finite_totals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "rounding-compatible-run"
            run_root.mkdir()
            scores = [78.89, 65.6, 10.19, 31.22]
            (run_root / "round_metrics.json").write_text(
                json.dumps(
                    [
                        {"round": round_number, "score": score}
                        for round_number, score in enumerate(scores, start=1)
                    ]
                ),
                encoding="utf-8",
            )

            summary = load_run_summary(run_root)

        self.assertEqual(summary["average_score"], 46.48)

    def test_missing_metadata_is_reported_without_failing_comparison(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing_run = Path(tmp) / "missing-run"
            missing_run.mkdir()

            summary = load_run_summary(missing_run)
            comparison = compare_runs([missing_run])

        self.assertEqual(summary["run_id"], "missing-run")
        self.assertEqual(summary["metadata_status"], "missing")
        self.assertIsNone(summary["best_score"])
        self.assertEqual(comparison["run_count"], 1)
        self.assertIsNone(comparison["best_vs_baseline_delta"])

    def test_boolean_scores_are_not_treated_as_numeric_scores(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "bool-score-run"
            run_root.mkdir()
            (run_root / "round_metrics.json").write_text(
                json.dumps([{"round": 1, "score": True}]),
                encoding="utf-8",
            )

            summary = load_run_summary(run_root)
            comparison = compare_runs([run_root])

        self.assertIsNone(summary["best_score"])
        self.assertIsNone(summary["average_score"])
        self.assertIsNone(comparison["best_score"])

    def test_non_finite_scores_do_not_win_ranking_or_escape_strict_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            malformed_run = root / "malformed-run"
            valid_run = root / "valid-run"
            malformed_run.mkdir()
            valid_run.mkdir()
            (malformed_run / "run_summary.json").write_text(
                json.dumps(
                    {
                        "run_id": "malformed-run",
                        "best_score": "nan",
                        "average_score": "Infinity",
                    }
                ),
                encoding="utf-8",
            )
            (malformed_run / "round_metrics.json").write_text(
                json.dumps(
                    [
                        {"round": 1, "score": float("nan")},
                        {"round": 2, "score": "Infinity"},
                        {"round": 3, "score": 10**400},
                        {"round": 4, "score": "-Infinity"},
                    ]
                ),
                encoding="utf-8",
            )
            (valid_run / "run_summary.json").write_text(
                json.dumps({"run_id": "valid-run", "best_score": 75}),
                encoding="utf-8",
            )
            output_path = root / "comparison.json"

            comparison = write_run_comparison(
                [malformed_run, valid_run],
                output_path,
            )
            strict_payload = json.loads(
                output_path.read_text(encoding="utf-8"),
                parse_constant=self._reject_json_constant,
            )

        self.assertEqual(comparison["best_run_id"], "valid-run")
        self.assertEqual(comparison["best_score"], 75.0)
        self.assertIsNone(comparison["best_vs_baseline_delta"])
        self.assertIsNone(comparison["runs"][0]["best_score"])
        self.assertIsNone(comparison["runs"][0]["average_score"])
        self.assertEqual(strict_payload, comparison)

    def test_missing_score_does_not_outrank_a_finite_negative_score(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            negative_run = root / "negative-run"
            missing_run = root / "missing-run"
            negative_run.mkdir()
            missing_run.mkdir()
            (negative_run / "run_summary.json").write_text(
                json.dumps(
                    {
                        "run_id": "negative-run",
                        "best_score": "-5.0",
                        "completed_rounds": 1,
                    }
                ),
                encoding="utf-8",
            )
            (missing_run / "run_summary.json").write_text(
                json.dumps({"run_id": "missing-run", "completed_rounds": 99}),
                encoding="utf-8",
            )

            comparison = compare_runs([negative_run, missing_run])

        self.assertEqual(comparison["best_run_id"], "negative-run")
        self.assertEqual(comparison["best_score"], -5.0)

    def test_finite_extreme_derived_scores_do_not_escape_strict_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            max_score = sys.float_info.max
            baseline_run = root / "baseline-run"
            best_run = root / "best-run"
            baseline_run.mkdir()
            best_run.mkdir()
            (baseline_run / "run_summary.json").write_text(
                json.dumps({"run_id": "baseline-run", "best_score": -1e308}),
                encoding="utf-8",
            )
            (best_run / "round_metrics.json").write_text(
                json.dumps(
                    [
                        {"round": 1, "score": max_score},
                        {"round": 2, "score": max_score},
                        {"round": 3, "score": max_score},
                    ]
                ),
                encoding="utf-8",
            )
            output_path = root / "comparison.json"

            comparison = write_run_comparison(
                [baseline_run, best_run],
                output_path,
            )
            strict_payload = json.loads(
                output_path.read_text(encoding="utf-8"),
                parse_constant=self._reject_json_constant,
            )

        self.assertEqual(comparison["best_run_id"], "best-run")
        self.assertEqual(comparison["best_score"], max_score)
        self.assertEqual(comparison["runs"][1]["average_score"], max_score)
        self.assertIsNone(comparison["best_vs_baseline_delta"])
        self.assertEqual(strict_payload, comparison)

    def test_cli_compare_wrapper_resolves_repo_relative_paths_and_writes_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_a = root / "runs" / "a"
            run_b = root / "runs" / "b"
            run_a.mkdir(parents=True)
            run_b.mkdir(parents=True)
            (run_a / "run_summary.json").write_text(
                json.dumps({"run_id": "a", "best_score": 60}),
                encoding="utf-8",
            )
            (run_b / "run_summary.json").write_text(
                json.dumps({"run_id": "b", "best_score": 80}),
                encoding="utf-8",
            )
            output_path = root / "comparison.json"

            comparison = _run_compare_cli(
                Namespace(
                    compare_runs=["runs/a", "runs/b"],
                    compare_output="comparison.json",
                ),
                Console(record=True),
                root,
            )

            self.assertEqual(comparison["best_run_id"], "b")
            self.assertEqual(comparison["runs"][0]["run_path"], "runs/a")
            self.assertEqual(comparison["runs"][0]["run_config_path"], "runs/a/run_config.json")
            self.assertEqual(json.loads(output_path.read_text(encoding="utf-8")), comparison)

    def test_invalid_judge_runs_do_not_select_a_winner_or_a_zero_trend(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            one_round = self._run_invalid_judge(root / "one-round", max_rounds=1)
            two_rounds = self._run_invalid_judge(root / "two-rounds", max_rounds=2)

            for run_root, completed in ((one_round, 1), (two_rounds, 2)):
                raw_summary = json.loads(
                    (run_root / "run_summary.json").read_text(encoding="utf-8")
                )
                raw_metrics = json.loads(
                    (run_root / "round_metrics.json").read_text(encoding="utf-8")
                )
                self.assertEqual(raw_summary["best_score"], -1)
                self.assertEqual(raw_summary["successful_rounds"], [])
                self.assertEqual(len(raw_metrics), completed)
                self.assertTrue(
                    all(entry["successful_research_round"] is False for entry in raw_metrics)
                )
                self.assertTrue(
                    all(entry["invalid_score_this_round"] is True for entry in raw_metrics)
                )
                self.assertTrue(all(entry["score"] == 0 for entry in raw_metrics))

            comparison = compare_runs([one_round, two_rounds])
            one_analysis = analyze_run(one_round)
            two_analysis = analyze_run(two_rounds)

        self.assertEqual(comparison["run_count"], 2)
        self.assertEqual(comparison["best_run_id"], "")
        self.assertIsNone(comparison["best_score"])
        self.assertIsNone(comparison["best_vs_baseline_delta"])
        self.assertEqual(comparison["baseline_run_id"], one_round.name)
        self.assertTrue(
            all(
                run["best_score"] is None and run["average_score"] is None
                for run in comparison["runs"]
            )
        )
        self.assertEqual([run["error_count"] for run in comparison["runs"]], [0, 0])
        self.assertEqual([run["successful_rounds"] for run in comparison["runs"]], [[], []])
        for analysis, completed in ((one_analysis, 1), (two_analysis, 2)):
            self.assertIsNone(analysis["score"]["best_score"])
            self.assertIsNone(analysis["score"]["average_score"])
            self.assertIsNone(analysis["score"]["first_score"])
            self.assertIsNone(analysis["score"]["latest_score"])
            self.assertIsNone(analysis["score"]["score_delta_first_to_latest"])
            self.assertEqual(analysis["score"]["trend"], "unknown")
            self.assertEqual(analysis["rounds"]["completed_rounds"], completed)
            self.assertEqual(analysis["rounds"]["successful_rounds"], [])
            self.assertEqual(analysis["robustness"]["error_count"], 0)
            self.assertEqual(analysis["robustness"]["error_rounds"], [])
            self.assertEqual(analysis["robustness"]["timeout_count"], 0)

    def test_null_best_scores_do_not_announce_a_winner(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            older = root / "older"
            newer = root / "newer"
            older.mkdir()
            newer.mkdir()
            (older / "run_summary.json").write_text(
                json.dumps({"run_id": "older", "best_score": None, "completed_rounds": 1}),
                encoding="utf-8",
            )
            (newer / "run_summary.json").write_text(
                json.dumps({"run_id": "newer", "best_score": None, "completed_rounds": 6}),
                encoding="utf-8",
            )

            comparison = compare_runs([older, newer])

        self.assertEqual(comparison["best_run_id"], "")
        self.assertIsNone(comparison["best_score"])
        self.assertIsNone(comparison["best_vs_baseline_delta"])
        self.assertEqual(comparison["baseline_run_id"], "older")
        self.assertEqual(comparison["runs"][1]["completed_rounds"], 6)

    def test_valid_zero_ranks_above_invalid_fallbacks_and_null_summaries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_run(
                root / "null-history",
                {"run_id": "null-history", "best_score": None, "completed_rounds": 9},
            )
            self._write_run(
                root / "sentinel",
                {
                    "run_id": "sentinel",
                    "best_score": -1,
                    "completed_rounds": 8,
                    "error_rounds": [1],
                },
                [
                    {
                        "round": 1,
                        "score": 0,
                        "successful_research_round": False,
                        "invalid_score_this_round": True,
                        "errors": ["judge returned no score"],
                    }
                ],
            )
            self._write_run(
                root / "real-zero",
                {"run_id": "real-zero", "best_score": 0, "completed_rounds": 1},
                [
                    {
                        "round": 1,
                        "score": 0,
                        "successful_research_round": True,
                        "invalid_score_this_round": False,
                    }
                ],
            )
            self._write_run(
                root / "real-six",
                {"run_id": "real-six", "best_score": 6, "completed_rounds": 2},
            )
            self._write_run(
                root / "legacy-negative",
                {"run_id": "legacy-negative", "best_score": -5, "completed_rounds": 1},
            )

            mixed = compare_runs(
                [
                    root / "null-history",
                    root / "sentinel",
                    root / "real-zero",
                    root / "real-six",
                ]
            )
            zero_versus_invalid = compare_runs([root / "real-zero", root / "sentinel"])
            negative_versus_sentinel = compare_runs([root / "legacy-negative", root / "sentinel"])
            sentinel_summary = load_run_summary(root / "sentinel")
            zero_summary = load_run_summary(root / "real-zero")

        self.assertEqual(mixed["best_run_id"], "real-six")
        self.assertEqual(mixed["best_score"], 6)
        self.assertIsNone(mixed["best_vs_baseline_delta"])
        self.assertEqual(zero_versus_invalid["best_run_id"], "real-zero")
        self.assertEqual(zero_versus_invalid["best_score"], 0)
        self.assertEqual(zero_versus_invalid["best_vs_baseline_delta"], 0)
        self.assertEqual(negative_versus_sentinel["best_run_id"], "legacy-negative")
        self.assertEqual(negative_versus_sentinel["best_score"], -5)
        self.assertIsNone(sentinel_summary["best_score"])
        self.assertIsNone(sentinel_summary["average_score"])
        self.assertEqual(sentinel_summary["error_count"], 1)
        self.assertEqual(sentinel_summary["error_rounds"], [1])
        self.assertEqual(zero_summary["best_score"], 0)
        self.assertEqual(zero_summary["average_score"], 0)

    def test_real_zero_trend_ignores_an_invalid_fallback_and_keeps_failure_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "mixed"
            self._write_run(
                run_root,
                {"run_id": "mixed", "best_score": 0, "completed_rounds": 3},
                [
                    {
                        "round": 1,
                        "score": 0,
                        "successful_research_round": False,
                        "invalid_score_this_round": True,
                        "errors": ["judge returned no score"],
                        "timeout_this_round": True,
                    },
                    {
                        "round": 2,
                        "score": 0,
                        "successful_research_round": True,
                        "invalid_score_this_round": False,
                    },
                    {
                        "round": 3,
                        "score": 0,
                        "successful_research_round": True,
                        "invalid_score_this_round": False,
                    },
                ],
            )

            summary = load_run_summary(run_root)
            analysis = analyze_run(run_root)

        self.assertEqual(summary["best_score"], 0)
        self.assertEqual(summary["average_score"], 0)
        self.assertEqual(summary["error_count"], 1)
        self.assertEqual(summary["timeout_count"], 1)
        self.assertEqual(analysis["score"]["first_score"], 0)
        self.assertEqual(analysis["score"]["latest_score"], 0)
        self.assertEqual(analysis["score"]["score_delta_first_to_latest"], 0)
        self.assertEqual(analysis["score"]["trend"], "flat")
        self.assertEqual(analysis["score"]["first_round"], 2)
        self.assertEqual(analysis["robustness"]["error_count"], 1)
        self.assertEqual(analysis["robustness"]["timeout_rounds"], [1])

    @staticmethod
    def _write_run(
        run_root: Path,
        summary: dict[str, object],
        metrics: list[dict[str, object]] | None = None,
    ) -> None:
        run_root.mkdir(parents=True, exist_ok=True)
        (run_root / "run_summary.json").write_text(json.dumps(summary), encoding="utf-8")
        if metrics is not None:
            (run_root / "round_metrics.json").write_text(json.dumps(metrics), encoding="utf-8")

    @staticmethod
    def _run_invalid_judge(project_dir: Path, *, max_rounds: int) -> Path:
        project_dir.mkdir()
        memory_path = project_dir / "memory.md"
        memory_path.write_text("Manual memory.\n", encoding="utf-8")
        result = run_iterative_rounds(
            console=Console(),
            agents=_InvalidJudgeAgents(),
            task_text="Design a privacy-aware memory adapter.",
            project_dir=project_dir,
            memory_path=memory_path,
            mode="normal",
            model_name="fake-model",
            max_rounds=max_rounds,
            stop_if_no_improvement_rounds=10,
            global_max_runtime_seconds=60,
            per_agent_timeout_seconds=300,
            disable_no_improvement_stop=True,
            disable_timeout_stop=True,
        )
        return Path(result["run_root"])


class _InvalidJudgeAgents:
    def __init__(self) -> None:
        self.llm = SimpleNamespace(timeout_seconds=300)

    def draft(self, **_kwargs: object) -> str:
        return "Draft from the invalid-judge fixture."

    def review(self, **_kwargs: object) -> str:
        return "Review from the invalid-judge fixture."

    def revise(self, **_kwargs: object) -> str:
        return "Revised from the invalid-judge fixture."

    def judge(self, **_kwargs: object) -> str:
        return "Judge completed without a numeric score."


if __name__ == "__main__":
    unittest.main()
