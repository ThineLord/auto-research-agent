from __future__ import annotations

import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from rich.console import Console

from src.cli import _run_analyze_cli
from src.run_analytics import analyze_run, write_run_analysis


class RunAnalyticsTests(unittest.TestCase):
    @staticmethod
    def _reject_json_constant(value: str) -> None:
        raise ValueError(f"non-standard JSON constant: {value}")

    def test_safe_analysis_treats_invalid_utf8_metrics_as_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "run"
            run_root.mkdir()
            (run_root / "round_metrics.json").write_bytes(b"\xff\xfe")

            analysis = analyze_run(run_root, safe_artifacts=True)

            self.assertEqual(analysis["score"]["trend"], "unknown")
            self.assertEqual(analysis["rounds"]["round_count"], 0)

    @unittest.skipUnless(hasattr(Path, "symlink_to"), "symlinks are unavailable")
    def test_explicit_analysis_output_parent_symlink_remains_authorized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_root = root / "run"
            run_root.mkdir()
            (run_root / "run_summary.json").write_text(
                json.dumps({"run_id": "run", "best_score": 80}),
                encoding="utf-8",
            )
            outside_output = root / "outside-output"
            outside_output.mkdir()
            linked_output = root / "linked-output"
            linked_output.symlink_to(outside_output, target_is_directory=True)

            analysis = write_run_analysis(run_root, linked_output / "analysis.json")

            self.assertEqual(
                json.loads((outside_output / "analysis.json").read_text(encoding="utf-8")),
                analysis,
            )

    def test_analyze_run_groups_score_robustness_cost_and_interpretability(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "runs" / "run-a"
            run_root.mkdir(parents=True)
            (run_root / "run_config.json").write_text(
                json.dumps(
                    {
                        "run_id": "run-a",
                        "model": {"provider": "ollama", "name": "qwen3:8b"},
                        "drafting_mode": "best_guided",
                        "runtime": {"max_rounds": 2},
                    }
                ),
                encoding="utf-8",
            )
            (run_root / "round_metrics.json").write_text(
                json.dumps(
                    [
                        {
                            "round": 1,
                            "score": 60.0,
                            "successful_research_round": True,
                            "agent_timings_seconds": {"draft": 1.0},
                            "estimated_input_tokens": 10,
                            "estimated_output_tokens": 5,
                            "estimated_total_tokens": 15,
                            "evolution_metrics": {
                                "draft_to_revised_similarity": 0.7,
                            },
                        },
                        {
                            "round": 2,
                            "score": 75.0,
                            "timeout_this_round": True,
                            "agent_timings_seconds": {"draft": 2.0},
                            "evolution_metrics": {
                                "draft_to_revised_similarity": 0.8,
                                "revised_similarity_to_previous": 0.96,
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
            output_path = Path(tmp) / "analysis.json"

            analysis = write_run_analysis(run_root, output_path)

            self.assertEqual(analysis["run_id"], "run-a")
            self.assertEqual(analysis["model"]["provider"], "ollama")
            self.assertEqual(analysis["score"]["trend"], "improved")
            self.assertEqual(analysis["score"]["score_delta_first_to_latest"], 15.0)
            self.assertEqual(analysis["robustness"]["timeout_count"], 1)
            self.assertEqual(analysis["cost_ready"]["total_estimated_tokens"], 15)
            self.assertEqual(analysis["interpretability"]["low_previous_revised_change_count"], 1)
            self.assertEqual(analysis["rubric"]["rubric_avg_evaluation"], 12.0)
            self.assertEqual(json.loads(output_path.read_text(encoding="utf-8")), analysis)

    def test_analyze_run_handles_missing_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "missing"
            run_root.mkdir()

            analysis = analyze_run(run_root)

        self.assertEqual(analysis["metadata_status"], "missing")
        self.assertEqual(analysis["score"]["trend"], "unknown")
        self.assertIsNone(analysis["score"]["best_score"])

    def test_analyze_run_score_trend_accepts_legacy_numeric_strings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "runs" / "legacy-string-score"
            run_root.mkdir(parents=True)
            (run_root / "round_metrics.json").write_text(
                json.dumps(
                    [
                        {"round": 1, "score": "60.5"},
                        {"round": 2, "score": "72.0"},
                    ]
                ),
                encoding="utf-8",
            )

            analysis = analyze_run(run_root)

        self.assertEqual(analysis["score"]["first_score"], 60.5)
        self.assertEqual(analysis["score"]["latest_score"], 72.0)
        self.assertEqual(analysis["score"]["score_delta_first_to_latest"], 11.5)
        self.assertEqual(analysis["score"]["trend"], "improved")

    def test_non_finite_scores_are_ignored_and_output_is_strict_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "runs" / "non-finite-scores"
            run_root.mkdir(parents=True)
            (run_root / "run_summary.json").write_text(
                json.dumps(
                    {
                        "run_id": "non-finite-scores",
                        "best_score": "nan",
                        "average_score": "Infinity",
                    }
                ),
                encoding="utf-8",
            )
            (run_root / "round_metrics.json").write_text(
                json.dumps(
                    [
                        {"round": 1, "score": float("nan")},
                        {"round": 2, "score": 60},
                        {"round": 3, "score": "Infinity"},
                        {"round": 4, "score": "75.0"},
                        {"round": 5, "score": 10**400},
                        {"round": 6, "score": "-Infinity"},
                    ]
                ),
                encoding="utf-8",
            )
            output_path = Path(tmp) / "analysis.json"

            analysis = write_run_analysis(run_root, output_path)
            strict_payload = json.loads(
                output_path.read_text(encoding="utf-8"),
                parse_constant=self._reject_json_constant,
            )

        self.assertEqual(analysis["score"]["best_score"], 75.0)
        self.assertEqual(analysis["score"]["average_score"], 67.5)
        self.assertEqual(analysis["score"]["first_round"], 2)
        self.assertEqual(analysis["score"]["first_score"], 60.0)
        self.assertEqual(analysis["score"]["latest_round"], 4)
        self.assertEqual(analysis["score"]["latest_score"], 75.0)
        self.assertEqual(analysis["score"]["score_delta_first_to_latest"], 15.0)
        self.assertEqual(analysis["score"]["trend"], "improved")
        self.assertEqual(strict_payload, analysis)

    def test_finite_extreme_score_delta_does_not_escape_strict_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "runs" / "finite-extreme-scores"
            run_root.mkdir(parents=True)
            (run_root / "round_metrics.json").write_text(
                json.dumps(
                    [
                        {"round": 1, "score": -1e308},
                        {"round": 2, "score": 1e308},
                    ]
                ),
                encoding="utf-8",
            )
            output_path = Path(tmp) / "analysis.json"

            analysis = write_run_analysis(run_root, output_path)
            strict_payload = json.loads(
                output_path.read_text(encoding="utf-8"),
                parse_constant=self._reject_json_constant,
            )

        self.assertEqual(analysis["score"]["first_score"], -1e308)
        self.assertEqual(analysis["score"]["latest_score"], 1e308)
        self.assertIsNone(analysis["score"]["score_delta_first_to_latest"])
        self.assertEqual(analysis["score"]["trend"], "improved")
        self.assertEqual(strict_payload, analysis)

    def test_legacy_metric_overflow_does_not_break_strict_analysis_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "runs" / "legacy-metric-overflow"
            run_root.mkdir(parents=True)
            (run_root / "round_metrics.json").write_text(
                json.dumps(
                    [
                        {
                            "round": 1,
                            "agent_timings_seconds": {"draft": 1e308, "review": 1e308},
                            "estimated_total_tokens": float("inf"),
                            "evolution_metrics": {
                                "draft_to_revised_similarity": 1e308,
                            },
                            "judge_rubric": {"evaluation_design_quality": -1e308},
                        },
                        {
                            "round": 2,
                            "agent_timings_seconds": {"draft": 10**400},
                            "evolution_metrics": {
                                "draft_to_revised_similarity": 1e308,
                            },
                            "judge_rubric": {"evaluation_design_quality": 1e308},
                        },
                    ]
                ),
                encoding="utf-8",
            )
            output_path = Path(tmp) / "analysis.json"

            analysis = write_run_analysis(run_root, output_path)
            strict_payload = json.loads(
                output_path.read_text(encoding="utf-8"),
                parse_constant=self._reject_json_constant,
            )

        self.assertIsNone(analysis["cost_ready"]["total_agent_elapsed_seconds"])
        self.assertIsNone(analysis["cost_ready"]["total_estimated_tokens"])
        self.assertEqual(
            analysis["interpretability"]["avg_draft_to_revised_similarity"],
            1e308,
        )
        self.assertEqual(analysis["rubric"]["rubric_avg_evaluation"], 0.0)
        self.assertEqual(strict_payload, analysis)

    def test_legacy_summary_rubric_averages_are_finite_normalized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "runs" / "legacy-summary-rubric"
            run_root.mkdir(parents=True)
            (run_root / "run_summary.json").write_text(
                json.dumps(
                    {
                        "run_id": "legacy-summary-rubric",
                        "rubric_subscore_averages": {
                            "evaluation_design_quality": float("nan"),
                            "tomorrow_actionability": "12.5",
                            "huge_legacy_value": 10**400,
                            "infinite_legacy_value": "Infinity",
                        },
                    }
                ),
                encoding="utf-8",
            )
            output_path = Path(tmp) / "analysis.json"

            analysis = write_run_analysis(run_root, output_path)
            strict_payload = json.loads(
                output_path.read_text(encoding="utf-8"),
                parse_constant=self._reject_json_constant,
            )

        self.assertEqual(
            analysis["rubric"]["rubric_subscore_averages"],
            {"tomorrow_actionability": 12.5},
        )
        self.assertIsNone(analysis["rubric"]["rubric_avg_evaluation"])
        self.assertEqual(analysis["rubric"]["rubric_avg_actionability"], 12.5)
        self.assertEqual(strict_payload, analysis)

    def test_cli_analyze_wrapper_masks_paths_and_writes_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_root = root / "runs" / "run-a"
            run_root.mkdir(parents=True)
            (run_root / "run_summary.json").write_text(
                json.dumps({"run_id": "run-a", "best_score": 80}),
                encoding="utf-8",
            )
            output_path = root / "analysis.json"

            analysis = _run_analyze_cli(
                Namespace(
                    analyze_run="runs/run-a",
                    analyze_output="analysis.json",
                ),
                Console(record=True),
                root,
            )

            self.assertEqual(analysis["run_path"], "runs/run-a")
            self.assertEqual(analysis["artifacts"]["run_config_path"], "runs/run-a/run_config.json")
            self.assertEqual(json.loads(output_path.read_text(encoding="utf-8")), analysis)
            self.assertNotIn(str(Path(tmp)), json.dumps(analysis))


if __name__ == "__main__":
    unittest.main()
