from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import src.run_compare as run_compare
from src.round_commit_recovery import ROUND_COMMIT_JOURNAL_NAME, RoundCommitReadError
from src.run_analytics import analyze_run


class AnalyticsSnapshotTests(unittest.TestCase):
    def test_metrics_are_read_and_decoded_once_per_analysis(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "run"
            run_root.mkdir()
            metrics_path = run_root / "round_metrics.json"
            content = json.dumps([{"round": 1, "score": 40}, {"round": 2, "score": 70}])
            metrics_path.write_text(content, encoding="utf-8")
            real_read_text = Path.read_text
            for safe_artifacts in (False, True):
                with (
                    self.subTest(safe_artifacts=safe_artifacts),
                    patch.object(
                        Path, "read_text", autospec=True, side_effect=real_read_text
                    ) as ordinary_read,
                    patch.object(
                        run_compare, "read_regular_text", wraps=run_compare.read_regular_text
                    ) as safe_read,
                    patch.object(json, "loads", wraps=json.loads) as decode,
                ):
                    analysis = analyze_run(run_root, safe_artifacts=safe_artifacts)

                    reads = [
                        call
                        for reader in (ordinary_read, safe_read)
                        for call in reader.call_args_list
                        if call.args[0] == metrics_path
                    ]
                    decodes = [call for call in decode.call_args_list if call.args[0] == content]
                    self.assertEqual(len(reads), 1)
                    self.assertEqual(len(decodes), 1)
                    self.assertEqual(analysis["score"]["average_score"], 55.0)
                    self.assertEqual(analysis["score"]["latest_score"], 70.0)

    def test_summary_and_trend_share_snapshot_but_next_request_reads_fresh_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "run"
            run_root.mkdir()
            metrics_path = run_root / "round_metrics.json"
            initial = [{"round": 1, "score": 40}]
            updated = initial + [{"round": 2, "score": 90}]
            real_read_metrics = run_compare._read_json_list

            def update_after_read(path: Path, **kwargs: bool) -> list[dict]:
                metrics = real_read_metrics(path, **kwargs)
                metrics_path.write_text(json.dumps(updated), encoding="utf-8")
                return metrics

            for safe_artifacts in (False, True):
                with self.subTest(safe_artifacts=safe_artifacts):
                    metrics_path.write_text(json.dumps(initial), encoding="utf-8")
                    with patch.object(
                        run_compare, "_read_json_list", side_effect=update_after_read
                    ):
                        first = analyze_run(run_root, safe_artifacts=safe_artifacts)
                    second = analyze_run(run_root, safe_artifacts=safe_artifacts)

                    self.assertEqual(first["rounds"]["round_count"], 1)
                    self.assertEqual(first["score"]["best_score"], 40.0)
                    self.assertEqual(first["score"]["latest_score"], 40.0)
                    self.assertEqual(first["score"]["trend"], "single_round")
                    self.assertEqual(second["rounds"]["round_count"], 2)
                    self.assertEqual(second["score"]["best_score"], 90.0)
                    self.assertEqual(second["score"]["latest_score"], 90.0)
                    self.assertEqual(second["score"]["trend"], "improved")

    def test_complete_analysis_schema_and_summary_precedence_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "run"
            run_root.mkdir()
            (run_root / "run_config.json").write_text(
                json.dumps(
                    {
                        "run_id": "fixture",
                        "model": {"provider": "mock", "name": "test-model"},
                        "runtime": {"max_rounds": 5},
                        "drafting_mode": "best_guided",
                    }
                ),
                encoding="utf-8",
            )
            (run_root / "run_summary.json").write_text(
                json.dumps(
                    {
                        "best_score": 90,
                        "completed_rounds": 5,
                        "stop_reason": "fixture",
                        "timeout_rounds": [4],
                    }
                ),
                encoding="utf-8",
            )
            (run_root / "round_metrics.json").write_text(
                json.dumps(
                    [
                        None,
                        {"round": 1, "score": "40", "successful_research_round": True},
                        {"round": 2, "score": 70, "errors": ["error"]},
                    ]
                ),
                encoding="utf-8",
            )
            expected = {
                "analysis_version": 1,
                "run_id": "fixture",
                "run_path": str(run_root),
                "metadata_status": "ok",
                "metadata_sources": ["run_summary", "run_config", "round_metrics"],
                "model": {
                    "provider": "mock",
                    "name": "test-model",
                    "drafting_mode": "best_guided",
                },
                "rounds": {
                    "max_rounds": 5,
                    "completed_rounds": 5,
                    "round_count": 2,
                    "successful_rounds": [1],
                },
                "score": {
                    "best_score": 90.0,
                    "average_score": 55.0,
                    "first_round": 1,
                    "first_score": 40.0,
                    "latest_round": 2,
                    "latest_score": 70.0,
                    "score_delta_first_to_latest": 30.0,
                    "trend": "improved",
                },
                "robustness": {
                    "stop_reason": "fixture",
                    "timeout_count": 1,
                    "error_count": 1,
                    "timeout_rounds": [4],
                    "error_rounds": [2],
                },
                "cost_ready": {
                    "total_agent_elapsed_seconds": None,
                    "total_estimated_input_tokens": None,
                    "total_estimated_output_tokens": None,
                    "total_estimated_tokens": None,
                    "token_estimate_method": "",
                },
                "interpretability": {
                    "avg_draft_to_revised_similarity": None,
                    "avg_revised_similarity_to_previous": None,
                    "avg_judge_similarity_to_previous": None,
                    "low_revision_change_count": 0,
                    "low_previous_revised_change_count": 0,
                    "low_revision_change_rounds": [],
                    "low_previous_revised_change_rounds": [],
                },
                "rubric": {
                    "rubric_round_count": 0,
                    "rubric_subscore_averages": {},
                    "rubric_avg_evaluation": None,
                    "rubric_avg_actionability": None,
                },
                "artifacts": {
                    "run_config_path": str(run_root / "run_config.json"),
                    "run_summary_path": str(run_root / "run_summary.json"),
                },
            }

            for safe_artifacts in (False, True):
                with self.subTest(safe_artifacts=safe_artifacts):
                    self.assertEqual(analyze_run(run_root, safe_artifacts=safe_artifacts), expected)
                    summary = run_compare.load_run_summary(run_root, safe_artifacts=safe_artifacts)
                    self.assertEqual(summary["best_score"], expected["score"]["best_score"])
                    self.assertEqual(summary["round_count"], expected["rounds"]["round_count"])
                    self.assertNotIn("round_metrics", summary)

    def test_journal_conflict_blocks_before_any_analysis_artifact_read(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "project"
            run_root = project_dir / "runs" / "run"
            run_root.mkdir(parents=True)
            journal = project_dir / ROUND_COMMIT_JOURNAL_NAME
            journal.write_text("{invalid journal", encoding="utf-8")
            for reader in (analyze_run, run_compare.load_run_summary):
                for safe_artifacts in (False, True):
                    for explicit_project in (None, project_dir):
                        with (
                            self.subTest(
                                reader=reader.__name__,
                                safe_artifacts=safe_artifacts,
                                explicit_project=explicit_project,
                            ),
                            patch.object(run_compare, "_read_json") as read_json,
                            patch.object(run_compare, "read_run_config") as read_config,
                            self.assertRaisesRegex(
                                RoundCommitReadError, "round_commit_recovery_conflict"
                            ),
                        ):
                            reader(
                                run_root,
                                safe_artifacts=safe_artifacts,
                                project_dir=explicit_project,
                            )
                        read_json.assert_not_called()
                        read_config.assert_not_called()
            self.assertEqual(journal.read_text(encoding="utf-8"), "{invalid journal")


if __name__ == "__main__":
    unittest.main()
