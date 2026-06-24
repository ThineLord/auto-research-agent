from __future__ import annotations

import unittest

from src.metrics import (
    TOKEN_ESTIMATE_METHOD,
    build_agent_io_metrics,
    estimate_tokens_from_chars,
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


if __name__ == "__main__":
    unittest.main()
