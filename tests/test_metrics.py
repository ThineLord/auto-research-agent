from __future__ import annotations

import json
import unittest

from src.metrics import (
    AGENT_STAGES,
    TOKEN_ESTIMATE_METHOD,
    build_agent_io_metrics,
    build_round_evolution_metrics,
    estimate_tokens_from_chars,
    summarize_judge_rubric_metrics,
    summarize_round_metrics,
)


class MetricsTests(unittest.TestCase):
    def test_estimate_tokens_from_chars_uses_ceil_division(self) -> None:
        self.assertEqual(estimate_tokens_from_chars(0), 0)
        self.assertEqual(estimate_tokens_from_chars(1), 1)
        self.assertEqual(estimate_tokens_from_chars(4), 1)
        self.assertEqual(estimate_tokens_from_chars(5), 2)

    def test_build_agent_io_metrics_zeros_skipped_stage_provider_usage(self) -> None:
        metrics = build_agent_io_metrics(
            agent_inputs={
                "draft": ["system", "task text"],
                "review": ["would not be sent"],
            },
            agent_outputs={
                "draft": "draft output",
                "review": "[REVIEW SKIPPED] draft failed.",
            },
            agent_timings_seconds={
                "draft": 1.25,
                "review": 0.0,
            },
            agent_errors={
                "draft": None,
                "review": "skipped due to draft failure",
            },
        )

        self.assertTrue(metrics["draft"]["called"])
        self.assertEqual(metrics["draft"]["output_chars"], len("draft output"))
        self.assertEqual(metrics["draft"]["token_estimate_method"], TOKEN_ESTIMATE_METHOD)
        self.assertFalse(metrics["review"]["called"])
        self.assertEqual(metrics["review"]["estimated_input_tokens"], 0)
        self.assertEqual(metrics["review"]["estimated_output_tokens"], 0)

    def test_summarize_round_metrics_tolerates_legacy_and_new_entries(self) -> None:
        new_metrics = build_agent_io_metrics(
            agent_inputs={"draft": ["abcd"]},
            agent_outputs={"draft": "abcdefgh"},
            agent_timings_seconds={"draft": 1.0},
            agent_errors={"draft": None},
        )
        summary = summarize_round_metrics(
            [
                {
                    "round": 1,
                    "agent_io_metrics": new_metrics,
                    "timeout_this_round": True,
                    "errors": [],
                },
                {
                    "round": 2,
                    "agent_timings_seconds": {"draft": 2.0},
                    "errors": ["boom"],
                },
            ]
        )

        self.assertEqual(summary["timeout_count"], 1)
        self.assertEqual(summary["error_count"], 1)
        self.assertEqual(summary["rounds_with_token_estimates"], 1)
        self.assertEqual(summary["total_agent_elapsed_seconds"], 3.0)
        self.assertEqual(summary["total_estimated_tokens"], 3)

    def test_round_evolution_metrics_capture_similarity_and_aggregate(self) -> None:
        first = build_round_evolution_metrics(
            current_draft="Plan A\nRun baseline",
            current_revised="Plan A\nRun baseline with ablation",
            current_judge="Score: 70\nGood start",
            current_score=70,
        )
        second = build_round_evolution_metrics(
            current_draft="Plan A\nRun baseline with ablation",
            current_revised="Plan A\nRun baseline with ablation and error analysis",
            current_judge="Score: 75\nBetter validation",
            previous_draft="Plan A\nRun baseline",
            previous_revised="Plan A\nRun baseline with ablation",
            previous_judge="Score: 70\nGood start",
            current_score=75,
            previous_score=70,
        )
        summary = summarize_round_metrics(
            [
                {"round": 1, "evolution_metrics": first},
                {"round": 2, "evolution_metrics": second},
            ]
        )

        self.assertFalse(first["has_previous_round"])
        self.assertIsNone(first["revised_similarity_to_previous"])
        self.assertTrue(second["has_previous_round"])
        self.assertGreater(second["draft_to_revised_similarity"], 0.5)
        self.assertEqual(second["score_delta_vs_previous"], 5)
        self.assertEqual(summary["evolution_metric_totals"]["rounds_with_evolution_metrics"], 2)
        self.assertEqual(
            summary["evolution_metric_totals"]["rounds_with_previous_round_similarity"],
            1,
        )
        self.assertIsNotNone(summary["evolution_metric_totals"]["avg_draft_to_revised_similarity"])

    def test_rubric_metrics_preserve_subscore_trends_without_required_schema(self) -> None:
        summary = summarize_judge_rubric_metrics(
            [
                {
                    "round": 1,
                    "judge_rubric": {
                        "evaluation_design_quality": 8,
                        "tomorrow_actionability": 9,
                    },
                },
                {
                    "round": 2,
                    "judge_rubric": {
                        "evaluation_design_quality": 12,
                        "tomorrow_actionability": 15,
                        "legacy_extra": "6",
                    },
                },
                {"round": 3, "judge_rubric": {}},
            ]
        )
        aggregate = summarize_round_metrics(
            [
                {
                    "round": 1,
                    "judge_rubric": {
                        "evaluation_design_quality": 8,
                        "tomorrow_actionability": 9,
                    },
                },
                {
                    "round": 2,
                    "judge_rubric": {
                        "evaluation_design_quality": 12,
                        "tomorrow_actionability": 15,
                    },
                },
            ]
        )

        self.assertEqual(summary["rounds_with_rubric"], 2)
        self.assertEqual(summary["rubric_averages"]["evaluation_design_quality"], 10)
        self.assertEqual(summary["rubric_latest"]["tomorrow_actionability"], 15.0)
        self.assertEqual(
            summary["rubric_delta_first_to_latest"]["evaluation_design_quality"],
            4,
        )
        self.assertEqual(aggregate["rubric_metric_totals"]["rounds_with_rubric"], 2)

    def test_malformed_legacy_metrics_remain_finite_and_strict_json(self) -> None:
        summary = summarize_round_metrics(
            [
                {
                    "round": 1,
                    "agent_timings_seconds": {"draft": 1e308, "review": 1e308},
                    "estimated_input_tokens": float("nan"),
                    "estimated_total_tokens": float("inf"),
                    "evolution_metrics": {"score_delta_vs_previous": 1e308},
                    "judge_rubric": {"evaluation_design_quality": -1e308},
                },
                {
                    "round": 2,
                    "agent_timings_seconds": {"draft": 10**400},
                    "evolution_metrics": {"score_delta_vs_previous": 1e308},
                    "judge_rubric": {"evaluation_design_quality": 1e308},
                },
                {
                    "round": 3,
                    "agent_io_metrics": {"draft": []},
                    "evolution_metrics": {
                        "draft_to_revised_similarity": float("inf"),
                        "score_delta_vs_previous": 10**400,
                    },
                    "judge_rubric": {
                        "evaluation_design_quality": 10**400,
                        "legacy_non_finite": "Infinity",
                    },
                },
                {
                    "round": 4,
                    "agent_timings_seconds": {"draft": "Infinity"},
                },
            ]
        )

        json.dumps(summary, allow_nan=False)
        self.assertIsNone(summary["total_agent_elapsed_seconds"])
        self.assertEqual(summary["total_estimated_tokens"], 0)
        self.assertEqual(
            summary["evolution_metric_totals"]["avg_score_delta_vs_previous"],
            1e308,
        )
        self.assertEqual(
            summary["evolution_metric_totals"]["low_revision_change_rounds"],
            [],
        )
        self.assertEqual(
            summary["rubric_metric_totals"]["rubric_averages"]["evaluation_design_quality"],
            0.0,
        )
        self.assertIsNone(
            summary["rubric_metric_totals"]["rubric_delta_first_to_latest"][
                "evaluation_design_quality"
            ]
        )
        self.assertNotIn(
            "legacy_non_finite",
            summary["rubric_metric_totals"]["rubric_averages"],
        )
        self.assertEqual(summary["agent_metric_totals"]["draft"]["called_count"], 0)

    def test_agent_metric_elapsed_overflow_uses_unavailable_total(self) -> None:
        agent_io_metrics = {
            agent: {
                "called": True,
                "had_error": False,
                "elapsed_seconds": 1e308,
                "estimated_input_chars": 0,
                "output_chars": 0,
                "estimated_input_tokens": 0,
                "estimated_output_tokens": 0,
                "estimated_total_tokens": 0,
            }
            for agent in AGENT_STAGES
        }

        summary = summarize_round_metrics([{"round": 1, "agent_io_metrics": agent_io_metrics}])

        json.dumps(summary, allow_nan=False)
        self.assertIsNone(summary["total_agent_elapsed_seconds"])
        for agent in AGENT_STAGES:
            self.assertEqual(
                summary["agent_metric_totals"][agent]["elapsed_seconds"],
                1e308,
            )

        repeated_summary = summarize_round_metrics(
            [
                {"round": 1, "agent_io_metrics": agent_io_metrics},
                {"round": 2, "agent_io_metrics": agent_io_metrics},
            ]
        )
        json.dumps(repeated_summary, allow_nan=False)
        self.assertIsNone(repeated_summary["total_agent_elapsed_seconds"])
        for agent in AGENT_STAGES:
            self.assertIsNone(repeated_summary["agent_metric_totals"][agent]["elapsed_seconds"])

    def test_evolution_score_delta_overflow_is_unavailable(self) -> None:
        metrics = build_round_evolution_metrics(
            current_draft="draft",
            current_revised="revised",
            current_judge="judge",
            current_score=1e308,
            previous_score=-1e308,
        )

        json.dumps(metrics, allow_nan=False)
        self.assertIsNone(metrics["score_delta_vs_previous"])

    def test_legacy_metric_numeric_compatibility_is_preserved(self) -> None:
        huge_exact_token_count = 10**400
        summary = summarize_round_metrics(
            [
                {
                    "round": 1,
                    "agent_timings_seconds": {"draft": "1.25"},
                    "estimated_total_tokens": 1.9,
                    "evolution_metrics": {"score_delta_vs_previous": "5.0"},
                    "judge_rubric": {"legacy_extra": "6"},
                },
                {
                    "round": 2,
                    "estimated_total_tokens": huge_exact_token_count,
                },
            ]
        )

        json.dumps(summary, allow_nan=False)
        self.assertEqual(summary["total_agent_elapsed_seconds"], 1.25)
        self.assertEqual(summary["total_estimated_tokens"], huge_exact_token_count + 1)
        self.assertIsNone(summary["evolution_metric_totals"]["avg_score_delta_vs_previous"])
        self.assertEqual(
            summary["rubric_metric_totals"]["rubric_averages"]["legacy_extra"],
            6.0,
        )


if __name__ == "__main__":
    unittest.main()
