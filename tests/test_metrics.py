from __future__ import annotations

import unittest

from src.metrics import (
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


if __name__ == "__main__":
    unittest.main()
