from __future__ import annotations

import unittest

from src.benchmarking import benchmark_preset_rounds, estimate_request_budget


class BenchmarkingTests(unittest.TestCase):
    def test_benchmark_presets_are_safe_named_round_counts(self) -> None:
        self.assertEqual(benchmark_preset_rounds("free_smoke"), 4)
        self.assertEqual(benchmark_preset_rounds("free_eval"), 5)
        self.assertEqual(benchmark_preset_rounds("paid_benchmark"), 25)
        self.assertEqual(benchmark_preset_rounds("stress_test"), 50)

    def test_gemini_budget_warns_when_low_quota_may_be_exceeded(self) -> None:
        free_eval = estimate_request_budget(
            provider="gemini",
            mode="continuous",
            planned_rounds=5,
        )
        paid_benchmark = estimate_request_budget(
            provider="gemini",
            mode="continuous",
            planned_rounds=25,
        )

        self.assertEqual(free_eval.calls_per_round, 4)
        self.assertEqual(free_eval.estimated_total_calls, 20)
        self.assertFalse(free_eval.exceeds_conservative_low_quota)
        self.assertEqual(paid_benchmark.estimated_total_calls, 100)
        self.assertTrue(paid_benchmark.exceeds_conservative_low_quota)
        self.assertIn("free_smoke/free_eval", paid_benchmark.warning)


if __name__ == "__main__":
    unittest.main()
