from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.benchmark_report import analyze_benchmark_run, write_benchmark_report


def _write_round(
    run_root: Path,
    round_index: int,
    *,
    draft: str,
    review: str,
    revised: str,
    judge: str,
) -> None:
    round_dir = run_root / f"round_{round_index:02d}"
    round_dir.mkdir(parents=True)
    (round_dir / "01_draft.md").write_text(draft, encoding="utf-8")
    (round_dir / "02_review.md").write_text(review, encoding="utf-8")
    (round_dir / "03_revised.md").write_text(revised, encoding="utf-8")
    (round_dir / "04_judge.md").write_text(judge, encoding="utf-8")


class BenchmarkReportTests(unittest.TestCase):
    def test_placeholder_rounds_do_not_drive_convergence_or_mode_collapse(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "runs" / "run-1"
            run_root.mkdir(parents=True)
            _write_round(
                run_root,
                1,
                draft="Draft A",
                review="Review A",
                revised="A concrete privacy benchmark with attack taxonomy and metrics.",
                judge='{"score": 80, "reasons": ["useful"], "blockers": []}',
            )
            _write_round(
                run_root,
                2,
                draft="Draft B",
                review="Review B",
                revised="A refined memory privacy evaluation plan with utility tradeoffs.",
                judge='{"score": 85, "reasons": ["better"], "blockers": []}',
            )
            for round_index in (3, 4):
                _write_round(
                    run_root,
                    round_index,
                    draft=(
                        "[DRAFT ERROR] PROVIDER_QUOTA_EXHAUSTED: "
                        "Gemini provider quota or rate limit reached."
                    ),
                    review="[REVIEW SKIPPED] draft agent failed.",
                    revised="[REVISE SKIPPED] draft/review agent failed.",
                    judge="SCORE: 0\n- Judge skipped because revise step failed.",
                )

            analysis = analyze_benchmark_run(run_root)

            self.assertEqual(analysis.successful_research_rounds, [1, 2])
            self.assertEqual(analysis.failed_provider_rounds, [3, 4])
            self.assertEqual(analysis.skipped_placeholder_rounds, [3, 4])
            self.assertIsNone(analysis.convergence_start_round)
            self.assertFalse(analysis.mode_collapse_detected)
            self.assertEqual(analysis.high_similarity_success_rounds, [])

    def test_generic_gemini_request_failure_counts_as_provider_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "runs" / "run-1"
            run_root.mkdir(parents=True)
            _write_round(
                run_root,
                1,
                draft="Draft A",
                review="[REVIEW ERROR] Gemini request failed.",
                revised="[REVISE SKIPPED] draft/review agent failed.",
                judge="SCORE: 0\n- Judge skipped because revise step failed.",
            )

            analysis = analyze_benchmark_run(run_root)

            self.assertEqual(analysis.successful_research_rounds, [])
            self.assertEqual(analysis.failed_provider_rounds, [1])
            self.assertEqual(analysis.skipped_placeholder_rounds, [1])

    def test_written_report_masks_run_root_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            project_dir = repo_root / "projects" / "demo"
            run_root = project_dir / "runs" / "run-1"
            run_root.mkdir(parents=True)
            (project_dir / "checkpoint.json").write_text(
                '{"stop_reason": "MAX_ROUNDS"}',
                encoding="utf-8",
            )
            _write_round(
                run_root,
                1,
                draft="Draft A",
                review="Review A",
                revised="A concrete privacy benchmark.",
                judge='{"score": 80, "reasons": ["useful"], "blockers": []}',
            )
            output_path = project_dir / "benchmark_report.md"

            write_benchmark_report(run_root=run_root, output_path=output_path)

            content = output_path.read_text(encoding="utf-8")
            self.assertIn("- Run root: `projects/demo/runs/run-1`", content)
            self.assertNotIn(str(repo_root), content)


if __name__ == "__main__":
    unittest.main()
