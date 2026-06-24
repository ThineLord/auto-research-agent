from __future__ import annotations

import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from rich.console import Console

from src.cli import _run_compare_cli
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
                        "model": "qwen3:8b",
                        "best_score": 72.0,
                        "completed_rounds": 2,
                        "drafting_mode": "best_guided",
                        "timeout_rounds": [2],
                        "total_agent_elapsed_seconds": 5.25,
                        "total_estimated_tokens": 123,
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
        self.assertEqual(comparison["best_run_id"], "legacy-run")

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
