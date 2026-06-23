from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.run_compare import compare_runs, load_run_summary, write_run_comparison


class RunCompareTests(unittest.TestCase):
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
                        "best_score": 72.0,
                        "completed_rounds": 2,
                        "drafting_mode": "best_guided",
                    }
                ),
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
                        {"round": 1, "score": 70.0, "successful_research_round": True},
                        {"round": 2, "score": 75.0, "timeout_this_round": True},
                    ]
                ),
                encoding="utf-8",
            )

            summary = load_run_summary(run_root)
            comparison = compare_runs([run_root])

        self.assertEqual(summary["best_score"], 75.0)
        self.assertEqual(summary["successful_rounds"], [1])
        self.assertEqual(summary["timeout_rounds"], [2])
        self.assertEqual(comparison["best_run_id"], "legacy-run")


if __name__ == "__main__":
    unittest.main()
