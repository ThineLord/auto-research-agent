from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import yaml

import src.config as config_module
import src.runtime as runtime_module
from src.config import (
    list_installed_ollama_models,
    load_default_model_name,
    parse_ollama_list_output,
    parse_ollama_tags_payload,
    query_ollama_models,
    save_default_model_name,
)
from src.runtime import (
    get_active_process_meta,
    run_project_tests,
    start_background_process,
)
from src.storage import (
    read_file_text,
    read_json_file,
    tail_file_lines,
    write_file_text,
    write_json_file,
)


class SharedUiBackendHelperTests(unittest.TestCase):
    def test_text_json_and_tail_helpers_handle_missing_and_invalid_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            text_path = root / "nested" / "note.txt"
            json_path = root / "state.json"
            invalid_json_path = root / "invalid.json"
            log_path = root / "run.log"

            self.assertEqual(read_file_text(text_path), "")
            write_file_text(text_path, "hello\n")
            self.assertEqual(read_file_text(text_path), "hello\n")

            self.assertEqual(read_json_file(json_path), {})
            write_json_file(json_path, {"round": 3})
            self.assertEqual(read_json_file(json_path), {"round": 3})

            invalid_json_path.write_text("{not json", encoding="utf-8")
            self.assertEqual(read_json_file(invalid_json_path), {})

            log_path.write_text("one\ntwo\nthree\n", encoding="utf-8")
            self.assertEqual(tail_file_lines(log_path, max_lines=2), "two\nthree")
            self.assertEqual(tail_file_lines(root / "missing.log"), "")

    def test_get_active_process_meta_returns_live_process_and_removes_stale_meta(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            meta_path = Path(tmp) / "ui_run_process.json"
            write_json_file(meta_path, {"pid": 123, "command": "run"})

            with patch.object(runtime_module, "is_pid_running", return_value=True):
                self.assertEqual(get_active_process_meta(meta_path)["pid"], 123)

            write_json_file(meta_path, {"pid": 123, "command": "run"})
            with patch.object(runtime_module, "is_pid_running", return_value=False):
                self.assertEqual(get_active_process_meta(meta_path), {})

            self.assertFalse(meta_path.exists())

    def test_is_pid_running_treats_zombie_process_as_stale(self) -> None:
        with (
            patch.object(runtime_module.os, "kill"),
            patch.object(
                runtime_module.subprocess,
                "run",
                return_value=SimpleNamespace(returncode=0, stdout="Z+\n"),
            ),
        ):
            self.assertFalse(runtime_module.is_pid_running(123))

        with (
            patch.object(runtime_module.os, "kill"),
            patch.object(
                runtime_module.subprocess,
                "run",
                return_value=SimpleNamespace(returncode=0, stdout="S+\n"),
            ),
        ):
            self.assertTrue(runtime_module.is_pid_running(123))

    def test_start_background_process_writes_meta_and_reports_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log_path = root / "run.log"
            meta_path = root / "ui_run_process.json"

            with patch.object(
                runtime_module.subprocess,
                "Popen",
                return_value=SimpleNamespace(pid=456),
            ) as popen:
                result = start_background_process(
                    command=["python", "-m", "src.main"],
                    cwd=root,
                    log_path=log_path,
                    meta_path=meta_path,
                    kind="run",
                    extra={"model": "qwen3:8b"},
                    env_overrides={"GEMINI_API_KEY": "secret-key"},
                )

            self.assertEqual(result.pid, 456)
            self.assertIsNone(result.error)
            self.assertEqual(popen.call_args.kwargs["env"]["GEMINI_API_KEY"], "secret-key")
            self.assertEqual(read_json_file(meta_path)["pid"], 456)
            self.assertEqual(read_json_file(meta_path)["model"], "qwen3:8b")
            meta_text = meta_path.read_text(encoding="utf-8")
            self.assertNotIn("secret-key", meta_text)
            self.assertNotIn("env_overrides", meta_text)

            with patch.object(
                runtime_module.subprocess,
                "Popen",
                side_effect=OSError("boom"),
            ):
                result = start_background_process(
                    command=["bad"],
                    cwd=root,
                    log_path=log_path,
                    meta_path=meta_path,
                    kind="run",
                )

            self.assertIsNone(result.pid)
            self.assertIn("Failed to start run process", result.error or "")

    def test_parse_ollama_list_output_sorts_dedupes_and_handles_empty_list(self) -> None:
        output = (
            "NAME           ID              SIZE      MODIFIED\n"
            "qwen3:8b       abc123          4.7 GB    2 days ago\n"
            "llama3.1:8b    def456          4.9 GB    yesterday\n"
            "qwen3:8b       duplicate       4.7 GB    today\n"
        )

        models = parse_ollama_list_output(output)

        self.assertEqual([model["name"] for model in models], ["llama3.1:8b", "qwen3:8b"])
        self.assertEqual(models[1]["id"], "abc123")
        self.assertEqual(parse_ollama_list_output("NAME ID SIZE MODIFIED\n"), [])

    def test_parse_ollama_tags_payload_reads_api_models(self) -> None:
        models = parse_ollama_tags_payload(
            {
                "models": [
                    {"name": "qwen3:8b", "digest": "abc", "size": 123, "modified_at": "today"},
                    {"name": "phi3:mini", "digest": "def", "size": 456},
                ]
            }
        )

        self.assertEqual([model["name"] for model in models], ["phi3:mini", "qwen3:8b"])
        self.assertEqual(models[0]["id"], "def")
        self.assertEqual(models[1]["modified"], "today")

    def test_query_ollama_models_parses_success_and_reports_missing_binary(self) -> None:
        result = SimpleNamespace(
            returncode=0,
            stdout=(
                "NAME           ID              SIZE      MODIFIED\n"
                "qwen3:8b       abc123          4.7 GB    2 days ago\n"
                "llama3.1:8b    def456          4.9 GB    yesterday\n"
            ),
            stderr="",
        )

        with patch.object(config_module.subprocess, "run", return_value=result):
            models, error = query_ollama_models()

        self.assertIsNone(error)
        self.assertEqual([model["name"] for model in models], ["llama3.1:8b", "qwen3:8b"])
        self.assertEqual(models[1]["id"], "abc123")
        self.assertEqual(models[0]["modified"], "yesterday")

        with patch.object(config_module.subprocess, "run", return_value=result):
            names, error = list_installed_ollama_models()

        self.assertIsNone(error)
        self.assertEqual(names, ["llama3.1:8b", "qwen3:8b"])

        with (
            patch.object(config_module.subprocess, "run", side_effect=FileNotFoundError),
            patch.object(
                config_module,
                "query_ollama_api_models",
                return_value=([], "api down"),
            ),
        ):
            models, error = query_ollama_models()

        self.assertEqual(models, [])
        self.assertIn("Ollama is not installed", error or "")

    def test_query_ollama_models_falls_back_to_api_when_command_fails(self) -> None:
        result = SimpleNamespace(returncode=1, stdout="", stderr="service down")

        with (
            patch.object(config_module.subprocess, "run", return_value=result),
            patch.object(
                config_module,
                "query_ollama_api_models",
                return_value=(
                    [{"name": "phi3:mini", "id": "", "size": "", "modified": ""}],
                    None,
                ),
            ),
        ):
            models, error = query_ollama_models()

        self.assertIsNone(error)
        self.assertEqual([model["name"] for model in models], ["phi3:mini"])

    def test_default_model_helpers_read_and_update_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.yaml"

            self.assertEqual(load_default_model_name(config_path), "qwen3:8b")
            self.assertIn(
                "config file not found",
                save_default_model_name(config_path, "qwen3:8b") or "",
            )

            config_path.write_text("model:\n  name: llama3.1:8b\n", encoding="utf-8")
            self.assertEqual(load_default_model_name(config_path), "llama3.1:8b")

            self.assertIsNone(save_default_model_name(config_path, "qwen3:14b"))
            saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["model"]["name"], "qwen3:14b")
            self.assertEqual(saved["model"]["provider"], "ollama")
            self.assertEqual(saved["model"]["timeout_seconds"], 300)

    def test_run_project_tests_reports_success_failure_and_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            success = SimpleNamespace(returncode=0, stdout="1 passed\n", stderr="")
            failure = SimpleNamespace(returncode=1, stdout="", stderr="failed\n")

            with patch.object(runtime_module.subprocess, "run", return_value=success) as run:
                result = run_project_tests(root)

            self.assertTrue(result["ok"])
            self.assertEqual(result["returncode"], 0)
            self.assertEqual(result["output"], "1 passed")
            self.assertEqual(run.call_args.kwargs["cwd"], root)

            with patch.object(runtime_module.subprocess, "run", return_value=failure):
                result = run_project_tests(root)

            self.assertFalse(result["ok"])
            self.assertEqual(result["returncode"], 1)
            self.assertEqual(result["output"], "failed")

            timeout = subprocess.TimeoutExpired(
                cmd=["pytest"],
                timeout=120,
                output="partial out",
                stderr="partial err",
            )
            with patch.object(runtime_module.subprocess, "run", side_effect=timeout):
                result = run_project_tests(root)

            self.assertFalse(result["ok"])
            self.assertIsNone(result["returncode"])
            self.assertIn("partial out", result["output"])
            self.assertIn("partial err", result["output"])

    def test_streamlit_app_imports_shared_helpers(self) -> None:
        import ui.app as ui_app

        self.assertIs(ui_app.read_file_text, read_file_text)
        self.assertIs(ui_app.read_json_file, read_json_file)
        self.assertIs(ui_app.run_project_tests, run_project_tests)

    def test_ui_model_picker_prefers_manual_then_session_config_and_default(self) -> None:
        import ui.app as ui_app

        self.assertEqual(
            ui_app.resolve_effective_model(
                selected_model="qwen3:8b",
                manual_model=" phi3:mini ",
                config_model="llama3.2:3b",
            ),
            "phi3:mini",
        )
        self.assertEqual(
            ui_app.resolve_effective_model(
                selected_model="qwen3:8b",
                manual_model=" ",
                config_model="llama3.2:3b",
            ),
            "qwen3:8b",
        )

        self.assertEqual(
            ui_app.default_project_index(["example", "nebula_unique_task"], "nebula_unique_task"),
            1,
        )
        self.assertEqual(
            ui_app.default_project_index(["example", "other"], "missing_project"),
            0,
        )

    def test_ui_cloud_provider_helpers_build_safe_command_and_env(self) -> None:
        import ui.app as ui_app

        self.assertEqual(
            ui_app.resolve_effective_cloud_model(
                selected_model="gemini-2.5-flash",
                manual_model=" gemini-custom ",
                default_model="gemini-3.5-flash",
            ),
            "gemini-custom",
        )
        self.assertEqual(
            ui_app.resolve_effective_cloud_model(
                selected_model="gemini-2.5-flash",
                manual_model="",
                default_model="gemini-3.5-flash",
            ),
            "gemini-2.5-flash",
        )
        self.assertEqual(
            ui_app.provider_model_label("gemini", "gemini-3.5-flash"),
            "gemini:gemini-3.5-flash",
        )

        command = ui_app.build_run_command(
            provider="gemini",
            mode="diagnostic",
            model="gemini-3.5-flash",
            gemini_api_key_env="TEAM_GEMINI_KEY",
            project="example",
            free_runner_preset="volume_free",
            benchmark_preset="free_smoke",
            max_provider_quota_failures=2,
            drafting_mode="continue_from_previous_draft",
        )

        self.assertIn("--provider", command)
        self.assertIn("gemini", command)
        self.assertIn("--model", command)
        self.assertIn("gemini-3.5-flash", command)
        self.assertIn("--gemini-api-key-env", command)
        self.assertIn("TEAM_GEMINI_KEY", command)
        self.assertIn("--project", command)
        self.assertIn("example", command)
        self.assertIn("--free-runner-preset", command)
        self.assertIn("volume_free", command)
        self.assertIn("--benchmark-preset", command)
        self.assertIn("free_smoke", command)
        self.assertIn("--max-provider-quota-failures", command)
        self.assertIn("2", command)
        self.assertIn("--drafting-mode", command)
        self.assertIn("continue_from_previous_draft", command)
        self.assertNotIn("secret-key", command)
        self.assertEqual(
            ui_app.build_provider_env_overrides(
                provider="gemini",
                api_key_env="TEAM_GEMINI_KEY",
                api_key_value=" secret-key ",
            ),
            {"TEAM_GEMINI_KEY": "secret-key"},
        )
        self.assertEqual(
            ui_app.build_provider_env_overrides(
                provider="ollama",
                api_key_env="TEAM_GEMINI_KEY",
                api_key_value="secret-key",
            ),
            {},
        )

    def test_cloud_provider_does_not_treat_ollama_model_error_as_blocking(self) -> None:
        import ui.app as ui_app

        local_blocked = bool("Ollama is not available") or not "qwen3:8b"
        cloud_blocked = (not "gemini-3.5-flash") or (
            not ui_app.has_gemini_api_key_source(
                api_key_env="GEMINI_API_KEY",
                api_key_value="secret-key",
            )
        )

        self.assertTrue(local_blocked)
        self.assertFalse(cloud_blocked)
        self.assertEqual(
            ui_app.resolve_effective_model(
                selected_model="",
                manual_model="",
                config_model="llama3.2:3b",
            ),
            "llama3.2:3b",
        )

        installed_models = ["gemma2:2b", "qwen3:8b", "phi3:mini"]
        self.assertEqual(
            ui_app.choose_model_picker_default(
                installed_model_names=installed_models,
                session_model="phi3:mini",
                config_model="gemma2:2b",
            ),
            "phi3:mini",
        )
        self.assertEqual(
            ui_app.choose_model_picker_default(
                installed_model_names=installed_models,
                session_model="missing:latest",
                config_model="gemma2:2b",
            ),
            "gemma2:2b",
        )
        self.assertEqual(
            ui_app.choose_model_picker_default(
                installed_model_names=["gemma2:2b", "qwen3:8b"],
                session_model="missing:latest",
                config_model="missing:also",
            ),
            "qwen3:8b",
        )

    def test_ui_progress_resume_and_output_helpers(self) -> None:
        import ui.app as ui_app

        log_text = (
            "2026-05-15 12:00:00 | mode=normal | round_enter round=2\n"
            "2026-05-15 12:00:01 | mode=normal | round=2 | agent=review | status=start\n"
        )
        progress = ui_app.infer_running_stage(
            log_text=log_text,
            checkpoint={
                "last_completed_round": 1,
                "mode": "normal",
                "model": "qwen3:8b",
                "best_score": 71,
            },
            run_meta={"pid": 123, "mode": "normal", "model": "qwen3:8b"},
        )

        self.assertTrue(progress["run_active"])
        self.assertEqual(progress["stage"], "review")
        self.assertEqual(progress["round"], 2)
        self.assertEqual(ui_app.live_refresh_interval(True), "2s")
        self.assertIsNone(ui_app.live_refresh_interval(False))

        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "project" / "runs" / "run1"
            run_root.mkdir(parents=True)
            resume = ui_app.describe_resume_state(
                checkpoint={
                    "run_id": "run1",
                    "run_root": str(run_root),
                    "can_resume": True,
                    "last_completed_round": 2,
                    "stop_reason": "USER_REQUESTED",
                    "model": "qwen3:8b",
                },
                run_active=False,
                selected_model="llama3.1:8b",
            )

        self.assertTrue(resume["can_resume"])
        self.assertIn("round 3", resume["message"])
        self.assertIn("Checkpoint model", resume["message"])
        self.assertEqual(resume["details"]["run_id"], "run1")
        self.assertEqual(resume["details"]["last_completed_round"], 2)
        self.assertEqual(resume["details"]["next_round"], 3)
        self.assertEqual(resume["details"]["stop_reason"], "USER_REQUESTED")
        self.assertTrue(resume["details"]["completed_round_files_preserved"])
        self.assertEqual(resume["details"]["next_round_status"], "missing")
        self.assertEqual(resume["details"]["next_round_safety_action"], "proceed_create_round_dir")

        stale_resume = ui_app.describe_resume_state(
            checkpoint={
                "run_id": "stale",
                "run_root": str(Path("/tmp") / "definitely-missing-auto-research-run"),
                "can_resume": True,
                "last_completed_round": 4,
            },
            run_active=False,
            selected_model="qwen3:8b",
        )
        missing_root_resume = ui_app.describe_resume_state(
            checkpoint={"can_resume": True, "last_completed_round": 1},
            run_active=False,
            selected_model="qwen3:8b",
        )

        self.assertFalse(stale_resume["can_resume"])
        self.assertEqual(stale_resume["message_key"], "resume_stale_checkpoint")
        self.assertFalse(stale_resume["details"]["can_resume"])
        self.assertFalse(missing_root_resume["can_resume"])
        self.assertEqual(missing_root_resume["message_key"], "resume_missing_run_root")
        self.assertFalse(missing_root_resume["details"]["can_resume"])

        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "project" / "runs" / "partial"
            partial_round = run_root / "round_03"
            partial_round.mkdir(parents=True)
            (partial_round / "01_draft.md").write_text("partial", encoding="utf-8")
            partial_resume = ui_app.describe_resume_state(
                checkpoint={
                    "run_id": "partial",
                    "run_root": str(run_root),
                    "can_resume": True,
                    "last_completed_round": 2,
                    "stop_reason": "USER_REQUESTED",
                },
                run_active=False,
                selected_model="qwen3:8b",
            )

        self.assertFalse(partial_resume["can_resume"])
        self.assertEqual(partial_resume["message_key"], "resume_partial_next_round")
        self.assertEqual(partial_resume["details"]["next_round_status"], "partial")
        self.assertTrue(partial_resume["details"]["next_round_blocks_resume"])
        self.assertEqual(
            partial_resume["details"]["next_round_safety_action"],
            "fail_safe_require_user_action",
        )

        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            run_root = project_dir / "runs" / "run1"
            round_dir = run_root / "round_02"
            round_dir.mkdir(parents=True)
            (project_dir / "checkpoint.json").write_text("{}", encoding="utf-8")
            (round_dir / "04_judge.md").write_text("judge", encoding="utf-8")

            catalog = ui_app.build_output_catalog(
                project_dir,
                {"run_root": str(run_root), "last_completed_round": 2},
            )

        labels = [item["label"] for item in catalog]
        self.assertIn("Checkpoint", labels)
        self.assertIn("Round metrics", labels)
        self.assertIn("Latest round judge", labels)
        judge_item = next(item for item in catalog if item["label"] == "Latest round judge")
        self.assertTrue(judge_item["exists"])
        self.assertEqual(judge_item["kind"], "markdown")
        metrics_item = next(item for item in catalog if item["label"] == "Round metrics")
        self.assertEqual(metrics_item["missing_key"], "missing_round_metrics")

    def test_ui_score_history_rows_flatten_metrics_for_display(self) -> None:
        import ui.app as ui_app

        with tempfile.TemporaryDirectory() as tmp:
            score_history_path = Path(tmp) / "score_history.json"
            score_history_path.write_text(
                """
[
  {
    "round": 1,
    "score": 82,
    "improved": true,
    "drafting_mode": "best_guided",
    "errors": [],
    "agent_timings_seconds": {"draft": 1.2, "review": 0.8, "revise": 0.7, "judge": 0.5},
    "round_runtime_seconds": 3.2,
    "estimated_input_tokens": 120,
    "estimated_output_tokens": 35,
    "estimated_total_tokens": 155,
    "evolution_metrics": {
      "score_delta_vs_previous": 4.5,
      "draft_to_revised_similarity": 0.72,
      "revised_similarity_to_previous": 0.81
    },
    "judge_rubric": {
      "evaluation_design_quality": 11,
      "tomorrow_actionability": 14
    }
  }
]
""",
                encoding="utf-8",
            )

            rows = ui_app.load_score_history_rows(score_history_path)

        self.assertEqual(rows[0]["round"], 1)
        self.assertEqual(rows[0]["score"], 82)
        self.assertEqual(rows[0]["draft_s"], 1.2)
        self.assertEqual(rows[0]["errors"], 0)
        self.assertEqual(rows[0]["estimated_input_tokens"], 120)
        self.assertEqual(rows[0]["estimated_output_tokens"], 35)
        self.assertEqual(rows[0]["estimated_total_tokens"], 155)
        self.assertEqual(rows[0]["score_delta_vs_previous"], 4.5)
        self.assertEqual(rows[0]["draft_to_revised_similarity"], 0.72)
        self.assertEqual(rows[0]["revised_similarity_to_previous"], 0.81)
        self.assertEqual(rows[0]["rubric_evaluation_design_quality"], 11)
        self.assertEqual(rows[0]["rubric_tomorrow_actionability"], 14)

    def test_ui_run_analytics_dashboard_summarizes_existing_artifacts(self) -> None:
        import ui.app as ui_app

        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "project"
            run_root = project_dir / "runs" / "run1"
            run_root.mkdir(parents=True)
            round_metrics = [
                {
                    "round": 1,
                    "score": 80.0,
                    "errors": [],
                    "agent_timings_seconds": {
                        "draft": 1.0,
                        "review": 0.5,
                        "revise": 0.4,
                        "judge": 0.3,
                    },
                    "round_runtime_seconds": 2.2,
                    "estimated_input_tokens": 100,
                    "estimated_output_tokens": 30,
                    "estimated_total_tokens": 130,
                    "evolution_metrics": {
                        "draft_to_revised_similarity": 0.72,
                    },
                    "judge_rubric": {
                        "evaluation_design_quality": 11,
                        "tomorrow_actionability": 13,
                    },
                },
                {
                    "round": 2,
                    "score": 91.0,
                    "timeout_this_round": True,
                    "errors": ["timeout"],
                    "agent_timings_seconds": {
                        "draft": 1.5,
                        "review": 0.7,
                        "revise": 0.6,
                        "judge": 0.4,
                    },
                    "round_runtime_seconds": 3.2,
                    "estimated_input_tokens": 120,
                    "estimated_output_tokens": 40,
                    "estimated_total_tokens": 160,
                    "evolution_metrics": {
                        "score_delta_vs_previous": 11,
                        "draft_to_revised_similarity": 0.75,
                        "revised_similarity_to_previous": 0.82,
                    },
                    "judge_rubric": {
                        "evaluation_design_quality": 14,
                        "tomorrow_actionability": 15,
                    },
                },
            ]
            write_json_file(
                run_root / "run_config.json",
                {
                    "run_id": "run1",
                    "model": {"provider": "ollama", "name": "qwen3:8b"},
                    "runtime": {"max_rounds": 2},
                },
            )
            write_json_file(
                run_root / "run_summary.json",
                {
                    "run_id": "run1",
                    "completed_rounds": 2,
                    "best_score": 91,
                    "timeout_count": 1,
                    "error_count": 1,
                    "total_agent_elapsed_seconds": 5.4,
                    "total_estimated_tokens": 290,
                    "round_metrics_path": str(run_root / "round_metrics.json"),
                },
            )
            (run_root / "round_metrics.json").write_text(
                json.dumps(round_metrics),
                encoding="utf-8",
            )
            (project_dir / "score_history.json").write_text(
                json.dumps(round_metrics),
                encoding="utf-8",
            )
            checkpoint = {
                "run_root": str(run_root),
                "run_summary": str(run_root / "run_summary.json"),
            }

            dashboard = ui_app.build_run_analytics_dashboard(project_dir, checkpoint)

        self.assertTrue(dashboard["available"])
        cards = {card["label_key"]: card["value"] for card in dashboard["cards"]}
        self.assertEqual(cards["analytics_best_score"], 91.0)
        self.assertEqual(cards["analytics_completed_rounds"], 2)
        self.assertEqual(cards["analytics_timeout_errors"], "1 / 1")
        self.assertEqual(cards["analytics_agent_elapsed"], "5.40s")
        self.assertEqual(cards["analytics_estimated_tokens"], 290)
        self.assertEqual(dashboard["score_rows"][-1]["score_delta"], 11)
        self.assertEqual(dashboard["rubric_rows"][-1]["evaluation"], 14.0)
        self.assertEqual(dashboard["similarity_rows"][-1]["revised_to_previous"], 0.82)
        self.assertEqual(dashboard["agent_timing_rows"][-1]["judge_s"], 0.4)
        self.assertEqual(dashboard["token_rows"][-1]["total_tokens"], 160)
        self.assertNotIn(
            str(Path(tmp)),
            "\n".join(str(value) for value in dashboard["sources"]),
        )

    def test_ui_run_analytics_dashboard_tolerates_missing_legacy_metrics(self) -> None:
        import ui.app as ui_app

        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "project"
            project_dir.mkdir(parents=True)
            (project_dir / "score_history.json").write_text(
                """
[
  {"round": 1, "score": 70, "errors": [], "round_runtime_seconds": 1.5},
  {"round": 2, "score": 72, "errors": ["legacy warning"], "round_runtime_seconds": 1.7}
]
""",
                encoding="utf-8",
            )

            dashboard = ui_app.build_run_analytics_dashboard(project_dir, {})

        self.assertTrue(dashboard["available"])
        self.assertEqual(dashboard["score_rows"][-1]["score"], 72.0)
        self.assertEqual(dashboard["cards"][0]["value"], 72.0)
        self.assertEqual(dashboard["cards"][1]["value"], 2)
        self.assertEqual(dashboard["cards"][2]["value"], "0 / 1")
        self.assertEqual(dashboard["rubric_rows"], [])
        self.assertEqual(dashboard["similarity_rows"], [])

    def test_ui_run_metadata_rows_summarize_latest_run_without_absolute_paths(self) -> None:
        import ui.app as ui_app

        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "project"
            run_root = project_dir / "runs" / "run1"
            run_root.mkdir(parents=True)
            run_config_path = run_root / "run_config.json"
            run_summary_path = run_root / "run_summary.json"
            round_metrics_path = run_root / "round_metrics.json"
            write_json_file(
                run_config_path,
                {
                    "run_id": "run1",
                    "mode": "normal",
                    "drafting_mode": "continue_from_previous_draft",
                    "started_at": "2026-06-23T01:00:00+00:00",
                    "ended_at": "2026-06-23T01:02:00+00:00",
                    "stop_reason": "max_rounds",
                    "can_resume": False,
                    "completed_rounds": 2,
                    "best_score": 88.5,
                    "model": {"provider": "ollama", "name": "qwen3:8b"},
                    "runtime": {"max_rounds": 2},
                    "git": {"commit": "abcdef1234567890"},
                },
            )
            write_json_file(
                run_summary_path,
                {
                    "run_id": "run1",
                    "round_metrics_path": str(round_metrics_path),
                    "avg_revised_similarity_to_previous": 0.84,
                    "low_previous_revised_change_rounds": [2],
                    "rubric_round_count": 2,
                    "rubric_subscore_averages": {
                        "evaluation_design_quality": 12,
                    },
                },
            )
            checkpoint = {
                "run_root": str(run_root),
                "run_config": str(run_config_path),
                "run_summary": str(run_summary_path),
            }

            rows = ui_app.build_run_metadata_rows(project_dir, checkpoint)
            catalog = ui_app.build_output_catalog(project_dir, checkpoint)

        by_key = {row["field_key"]: row["value"] for row in rows}
        self.assertEqual(by_key["run_meta_provider"], "ollama")
        self.assertEqual(by_key["run_meta_model"], "qwen3:8b")
        self.assertEqual(by_key["run_meta_drafting_mode"], "continue_from_previous_draft")
        self.assertEqual(by_key["run_meta_git_commit"], "abcdef123456")
        self.assertEqual(by_key["run_meta_avg_revised_similarity"], "0.84")
        self.assertEqual(by_key["run_meta_low_change_rounds"], "1")
        self.assertEqual(by_key["run_meta_rubric_rounds"], "2")
        self.assertEqual(by_key["run_meta_rubric_avg_evaluation"], "12")
        self.assertEqual(by_key["run_meta_round_metrics_path"], "<repo>/round_metrics.json")
        self.assertNotIn(str(Path(tmp)), "\n".join(by_key.values()))

        metrics_item = next(item for item in catalog if item["label"] == "Round metrics")
        self.assertEqual(metrics_item["path"], round_metrics_path)

    def test_stop_signal_display_path_is_masked(self) -> None:
        import ui.app as ui_app

        with tempfile.TemporaryDirectory() as tmp:
            stop_signal_path = Path(tmp) / "project" / "STOP_REQUESTED"

            display_path = ui_app.output_display_path(stop_signal_path)

        self.assertEqual(display_path, "<repo>/STOP_REQUESTED")
        self.assertNotIn(str(Path(tmp)), display_path)

    def test_ui_run_comparison_helpers_mask_paths_and_flatten_fields(self) -> None:
        import ui.app as ui_app

        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "project"
            run_a = project_dir / "runs" / "run-a"
            run_b = project_dir / "runs" / "run-b"
            run_a.mkdir(parents=True)
            run_b.mkdir(parents=True)
            write_json_file(
                run_a / "run_config.json",
                {
                    "run_id": "run-a",
                    "drafting_mode": "best_guided",
                    "model": {"provider": "ollama", "name": "qwen3:8b"},
                    "runtime": {"max_rounds": 2},
                },
            )
            write_json_file(
                run_a / "round_metrics.json",
                [
                    {
                        "round": 1,
                        "score": 60.0,
                        "timeout_this_round": True,
                        "agent_timings_seconds": {"draft": 1.0},
                        "estimated_input_tokens": 10,
                        "estimated_output_tokens": 5,
                        "estimated_total_tokens": 15,
                    },
                    {
                        "round": 2,
                        "score": 70.0,
                        "errors": ["boom"],
                        "agent_timings_seconds": {"draft": 2.0},
                        "estimated_input_tokens": 20,
                        "estimated_output_tokens": 5,
                        "estimated_total_tokens": 25,
                        "evolution_metrics": {
                            "draft_to_revised_similarity": 0.6,
                            "revised_similarity_to_previous": 0.97,
                        },
                        "judge_rubric": {
                            "evaluation_design_quality": 13,
                            "tomorrow_actionability": 16,
                        },
                    },
                ],
            )
            write_json_file(
                run_b / "run_summary.json",
                {
                    "run_id": "run-b",
                    "model": "gemini-3.5-flash",
                    "drafting_mode": "fresh_from_task_with_review",
                    "best_score": 88.0,
                    "completed_rounds": 1,
                },
            )

            discovered = ui_app.discover_project_run_roots(project_dir)
            rows = ui_app.build_run_comparison_rows([run_a, run_b])

        self.assertEqual({path.name for path in discovered}, {"run-a", "run-b"})
        by_id = {row["run_id"]: row for row in rows}
        self.assertEqual(by_id["run-a"]["provider"], "ollama")
        self.assertEqual(by_id["run-a"]["model"], "qwen3:8b")
        self.assertEqual(by_id["run-a"]["max_rounds"], "2")
        self.assertEqual(by_id["run-a"]["average_score"], 65.0)
        self.assertEqual(by_id["run-a"]["timeout_count"], "1")
        self.assertEqual(by_id["run-a"]["error_count"], "1")
        self.assertEqual(by_id["run-a"]["agent_elapsed_s"], "3.0")
        self.assertEqual(by_id["run-a"]["estimated_tokens"], "40")
        self.assertEqual(by_id["run-a"]["avg_revised_similarity"], "0.97")
        self.assertEqual(by_id["run-a"]["low_change_rounds"], "1")
        self.assertEqual(by_id["run-a"]["rubric_rounds"], "1")
        self.assertEqual(by_id["run-a"]["rubric_avg_evaluation"], "13.0")
        self.assertEqual(by_id["run-a"]["rubric_avg_actionability"], "16.0")
        self.assertEqual(by_id["run-a"]["run_path"], "<repo>/run-a")
        self.assertNotIn(
            str(Path(tmp)), "\n".join(str(value) for row in rows for value in row.values())
        )

    def test_fast_model_health_check_uses_api_and_selected_model_presence(self) -> None:
        import ui.app as ui_app

        response = SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"models": [{"name": "qwen3:8b"}]},
        )

        with patch.object(ui_app.requests, "get", return_value=response) as get:
            health = ui_app.check_model_health(
                base_url="http://localhost:11434",
                selected_model="qwen3:8b",
                installed_model_names=[],
            )

        self.assertTrue(health["ok"])
        self.assertTrue(health["api_ok"])
        self.assertTrue(health["model_ok"])
        self.assertEqual(get.call_args.args[0], "http://localhost:11434/api/tags")

        with patch.object(ui_app.requests, "get", return_value=response):
            health = ui_app.check_model_health(
                base_url="http://localhost:11434",
                selected_model="missing:latest",
                installed_model_names=[],
            )

        self.assertFalse(health["ok"])
        self.assertTrue(health["api_ok"])
        self.assertFalse(health["model_ok"])
        self.assertIn("not installed", health["message"])

    def test_gemini_health_check_uses_mocked_client_and_missing_key_short_circuits(self) -> None:
        import ui.app as ui_app

        with patch.object(ui_app, "has_gemini_api_key_source", return_value=False):
            health = ui_app.check_gemini_model_health(
                selected_model="gemini-3.5-flash",
                api_key_env="GEMINI_API_KEY",
            )

        self.assertFalse(health["ok"])
        self.assertEqual(health["message_key"], "gemini_health_missing_key")

        with (
            patch.object(ui_app, "has_gemini_api_key_source", return_value=True),
            patch.object(
                ui_app.GeminiClient,
                "generate",
                return_value="OK",
            ) as generate,
        ):
            health = ui_app.check_gemini_model_health(
                selected_model="gemini-3.5-flash",
                api_key_env="GEMINI_API_KEY",
                api_key_value="secret-key",
            )

        self.assertTrue(health["ok"])
        self.assertEqual(health["message_key"], "gemini_health_ok")
        generate.assert_called_once()


if __name__ == "__main__":
    unittest.main()
