from __future__ import annotations

import json
import sys
import tempfile
import unittest
from argparse import Namespace
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path

from rich.console import Console

from src.cli import _run_compare_cli, parse_args
from src.run_compare import compare_runs, load_run_summary, write_run_comparison


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


if __name__ == "__main__":
    unittest.main()
