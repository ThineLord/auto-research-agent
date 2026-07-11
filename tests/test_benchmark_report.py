from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from src import constants as stop_constants
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

    def test_analysis_tolerates_stale_round_text_artifact_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "runs" / "run-1"
            round_dir = run_root / "round_01"
            round_dir.mkdir(parents=True)
            (round_dir / "01_draft.md").mkdir()
            (round_dir / "02_review.md").write_text("Review A", encoding="utf-8")
            (round_dir / "03_revised.md").write_text(
                "A concrete privacy benchmark.",
                encoding="utf-8",
            )
            (round_dir / "04_judge.md").write_text(
                '{"score": 80, "reasons": ["useful"], "blockers": []}',
                encoding="utf-8",
            )

            analysis = analyze_benchmark_run(run_root)

            self.assertEqual(analysis.successful_research_rounds, [1])
            self.assertEqual(analysis.failed_provider_rounds, [])

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

    def test_written_report_uses_target_run_stop_reason_not_latest_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "projects" / "demo"
            run_root = project_dir / "runs" / "run-old"
            run_root.mkdir(parents=True)
            (run_root / "run_summary.json").write_text(
                '{"run_id": "run-old", "stop_reason": "USER_STOP_REQUESTED"}',
                encoding="utf-8",
            )
            (run_root / "run_config.json").write_text(
                '{"run_id": "run-old", "stop_reason": "NO_IMPROVEMENT"}',
                encoding="utf-8",
            )
            (run_root / "run_manifest.json").write_text(
                '{"run_id": "run-old", "stop_reason": "OLLAMA_TIMEOUT"}',
                encoding="utf-8",
            )
            (project_dir / "checkpoint.json").write_text(
                '{"run_id": "run-new", "stop_reason": "MAX_ROUNDS"}',
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
            output_path = project_dir / "historical-benchmark-report.md"

            write_benchmark_report(run_root=run_root, output_path=output_path)

            content = output_path.read_text(encoding="utf-8")
            self.assertIn("- Stop reason: `USER_STOP_REQUESTED`", content)
            self.assertNotIn("- Stop reason: `MAX_ROUNDS`", content)

    def test_written_report_falls_back_to_run_config_then_legacy_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "projects" / "demo"
            config_run = project_dir / "runs" / "config-run"
            config_run.mkdir(parents=True)
            (config_run / "run_summary.json").write_text("[]", encoding="utf-8")
            (config_run / "run_config.json").write_text(
                '{"stop_reason": "NO_IMPROVEMENT"}',
                encoding="utf-8",
            )

            config_report = project_dir / "config-report.md"
            write_benchmark_report(run_root=config_run, output_path=config_report)

            self.assertIn(
                "- Stop reason: `NO_IMPROVEMENT`",
                config_report.read_text(encoding="utf-8"),
            )

            manifest_run = project_dir / "runs" / "manifest-run"
            manifest_run.mkdir(parents=True)
            (manifest_run / "run_summary.json").write_text(
                '{"stop_reason": 42}',
                encoding="utf-8",
            )
            (manifest_run / "run_config.json").write_text(
                '{"stop_reason": "   "}',
                encoding="utf-8",
            )
            (manifest_run / "run_manifest.json").write_text(
                '{"stop_reason": "OLLAMA_TIMEOUT"}',
                encoding="utf-8",
            )

            manifest_report = project_dir / "manifest-report.md"
            write_benchmark_report(run_root=manifest_run, output_path=manifest_report)

            self.assertIn(
                "- Stop reason: `OLLAMA_TIMEOUT`",
                manifest_report.read_text(encoding="utf-8"),
            )

    def test_checkpoint_fallback_requires_matching_target_identity(self) -> None:
        cases = (
            (
                "matching-absolute-root",
                lambda run_root: {"run_id": run_root.name, "run_root": str(run_root)},
                "MAX_ROUNDS",
            ),
            (
                "matching-relative-root",
                lambda run_root: {"run_root": f"runs/{run_root.name}"},
                "MAX_ROUNDS",
            ),
            (
                "matching-repo-relative-root",
                lambda run_root: {"run_root": f"projects/demo/runs/{run_root.name}"},
                "MAX_ROUNDS",
            ),
            (
                "legacy-run-id-only",
                lambda run_root: {"run_id": run_root.name},
                "MAX_ROUNDS",
            ),
            (
                "mismatched-root",
                lambda run_root: {
                    "run_id": run_root.name,
                    "run_root": str(run_root.parent / "another-run"),
                },
                "unknown",
            ),
            (
                "mismatched-id",
                lambda run_root: {"run_id": "another-run", "run_root": str(run_root)},
                "unknown",
            ),
            (
                "invalid-root-type",
                lambda run_root: {"run_id": run_root.name, "run_root": [str(run_root)]},
                "unknown",
            ),
            (
                "invalid-id-type",
                lambda run_root: {"run_id": 42, "run_root": str(run_root)},
                "unknown",
            ),
            (
                "invalid-root-value",
                lambda run_root: {"run_id": run_root.name, "run_root": "bad\0path"},
                "unknown",
            ),
            ("missing-identity", lambda run_root: {}, "unknown"),
        )
        for label, checkpoint_factory, expected in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                project_dir = Path(tmp) / "projects" / "demo"
                run_root = project_dir / "runs" / "target-run"
                run_root.mkdir(parents=True)
                checkpoint = checkpoint_factory(run_root)
                checkpoint["stop_reason"] = "MAX_ROUNDS"
                (project_dir / "checkpoint.json").write_text(
                    json.dumps(checkpoint),
                    encoding="utf-8",
                )
                output_path = project_dir / "benchmark-report.md"

                write_benchmark_report(run_root=run_root, output_path=output_path)

                self.assertIn(
                    f"- Stop reason: `{expected}`",
                    output_path.read_text(encoding="utf-8"),
                )

        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "projects" / "demo"
            run_root = project_dir / "runs" / "target-run"
            run_root.mkdir(parents=True)
            (project_dir / "checkpoint.json").write_text("[]", encoding="utf-8")
            output_path = project_dir / "nonobject-checkpoint-report.md"

            write_benchmark_report(run_root=run_root, output_path=output_path)

            self.assertIn(
                "- Stop reason: `unknown`",
                output_path.read_text(encoding="utf-8"),
            )

    def test_metadata_symlinks_are_not_read(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside_tmp:
            project_dir = Path(tmp) / "projects" / "demo"
            run_root = project_dir / "runs" / "symlink-run"
            run_root.mkdir(parents=True)
            outside_summary = Path(outside_tmp) / "run_summary.json"
            outside_summary.write_text(
                '{"stop_reason": "MAX_ROUNDS"}',
                encoding="utf-8",
            )
            try:
                (run_root / "run_summary.json").symlink_to(outside_summary)
            except OSError as exc:
                self.skipTest(f"symlinks unavailable: {type(exc).__name__}")
            (run_root / "run_config.json").write_text(
                '{"stop_reason": "NO_IMPROVEMENT"}',
                encoding="utf-8",
            )
            output_path = project_dir / "symlink-report.md"

            write_benchmark_report(run_root=run_root, output_path=output_path)

            content = output_path.read_text(encoding="utf-8")
            self.assertIn("- Stop reason: `NO_IMPROVEMENT`", content)
            self.assertNotIn("- Stop reason: `MAX_ROUNDS`", content)

            checkpoint_run = project_dir / "runs" / "checkpoint-run"
            checkpoint_run.mkdir(parents=True)
            outside_checkpoint = Path(outside_tmp) / "checkpoint.json"
            outside_checkpoint.write_text(
                json.dumps(
                    {
                        "run_id": checkpoint_run.name,
                        "run_root": str(checkpoint_run),
                        "stop_reason": "MAX_ROUNDS",
                    }
                ),
                encoding="utf-8",
            )
            (project_dir / "checkpoint.json").symlink_to(outside_checkpoint)
            checkpoint_report = project_dir / "checkpoint-report.md"

            write_benchmark_report(run_root=checkpoint_run, output_path=checkpoint_report)

            self.assertIn(
                "- Stop reason: `unknown`",
                checkpoint_report.read_text(encoding="utf-8"),
            )
            self.assertNotIn(
                "- Stop reason: `MAX_ROUNDS`",
                checkpoint_report.read_text(encoding="utf-8"),
            )

    def test_nonregular_metadata_leaves_are_skipped_without_blocking(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "projects" / "demo"
            directory_run = project_dir / "runs" / "directory-run"
            directory_run.mkdir(parents=True)
            (directory_run / "run_summary.json").mkdir()
            (directory_run / "run_config.json").write_text(
                '{"stop_reason": "PROMPT_TOO_LARGE"}',
                encoding="utf-8",
            )
            directory_report = project_dir / "directory-report.md"

            write_benchmark_report(run_root=directory_run, output_path=directory_report)

            self.assertIn(
                "- Stop reason: `PROMPT_TOO_LARGE`",
                directory_report.read_text(encoding="utf-8"),
            )

            if hasattr(os, "mkfifo"):
                fifo_run = project_dir / "runs" / "fifo-run"
                fifo_run.mkdir(parents=True)
                os.mkfifo(fifo_run / "run_summary.json")
                (fifo_run / "run_config.json").write_text(
                    '{"stop_reason": "OLLAMA_TIMEOUT"}',
                    encoding="utf-8",
                )
                fifo_report = project_dir / "fifo-report.md"

                write_benchmark_report(run_root=fifo_run, output_path=fifo_report)

                self.assertIn(
                    "- Stop reason: `OLLAMA_TIMEOUT`",
                    fifo_report.read_text(encoding="utf-8"),
                )

    def test_unsafe_stop_reason_is_not_rendered_as_markdown_or_private_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "projects" / "demo"
            run_root = project_dir / "runs" / "unsafe-reason-run"
            run_root.mkdir(parents=True)
            private_path = "/" + "Users" + "/private-name"
            unsafe_reason = f"MAX_ROUNDS`\n\n## Injected\n{private_path}"
            (run_root / "run_summary.json").write_text(
                json.dumps({"stop_reason": unsafe_reason}),
                encoding="utf-8",
            )
            output_path = project_dir / "unsafe-reason-report.md"

            write_benchmark_report(run_root=run_root, output_path=output_path)

            content = output_path.read_text(encoding="utf-8")
            self.assertIn("- Stop reason: `unknown`", content)
            self.assertNotIn("## Injected", content)
            self.assertNotIn(private_path, content)

            credential_shaped_reason = "AK" + "IA" + "A" * 16
            (run_root / "run_summary.json").write_text(
                json.dumps({"stop_reason": credential_shaped_reason}),
                encoding="utf-8",
            )
            credential_report = project_dir / "credential-reason-report.md"

            write_benchmark_report(run_root=run_root, output_path=credential_report)

            credential_content = credential_report.read_text(encoding="utf-8")
            self.assertIn("- Stop reason: `unknown`", credential_content)
            self.assertNotIn(credential_shaped_reason, credential_content)

    def test_all_current_stop_reason_constants_remain_reportable(self) -> None:
        stop_reasons = {
            value
            for name, value in vars(stop_constants).items()
            if name.startswith("STOP_") and isinstance(value, str)
        }
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "projects" / "demo"
            for index, stop_reason in enumerate(sorted(stop_reasons), start=1):
                with self.subTest(stop_reason=stop_reason):
                    run_root = project_dir / "runs" / f"constant-run-{index}"
                    run_root.mkdir(parents=True)
                    (run_root / "run_summary.json").write_text(
                        json.dumps({"stop_reason": stop_reason}),
                        encoding="utf-8",
                    )
                    output_path = project_dir / f"constant-report-{index}.md"

                    write_benchmark_report(run_root=run_root, output_path=output_path)

                    self.assertIn(
                        f"- Stop reason: `{stop_reason}`",
                        output_path.read_text(encoding="utf-8"),
                    )


if __name__ == "__main__":
    unittest.main()
