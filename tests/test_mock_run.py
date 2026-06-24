from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from rich.console import Console

import src.cli as cli_module
from src.config import AppConfig
from src.mock_run import (
    MOCK_DEFAULT_ROUNDS,
    MOCK_MODEL_NAME,
    MOCK_MODEL_PROVIDER,
    MockResearchAgents,
    build_mock_agents,
    mock_model_parameters,
)
from src.runner import run_iterative_rounds


class MockRunTests(unittest.TestCase):
    def test_parse_args_accepts_mock_mode(self) -> None:
        args = cli_module.parse_args(["--mock", "--max-rounds", "3"])

        self.assertTrue(args.mock)
        self.assertEqual(args.max_rounds, 3)

    def test_mock_agents_write_normal_run_artifacts_without_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir = root / "projects" / "demo"
            project_dir.mkdir(parents=True)
            memory_path = project_dir / "memory.md"
            memory_path.write_text("Existing demo memory.\n", encoding="utf-8")
            prompt_dir = root / "prompts"
            prompt_dir.mkdir()
            for name in ("draft.md", "review.md", "revise.md", "judge.md"):
                (prompt_dir / name).write_text(f"{name} prompt\n", encoding="utf-8")

            result = run_iterative_rounds(
                console=Console(),
                agents=build_mock_agents(topic_context="Topic: mock demo"),
                task_text="Demonstrate provider-free artifact generation.",
                project_dir=project_dir,
                memory_path=memory_path,
                mode="mock",
                model_name=MOCK_MODEL_NAME,
                max_rounds=2,
                stop_if_no_improvement_rounds=10,
                global_max_runtime_seconds=60,
                per_agent_timeout_seconds=1,
                model_provider=MOCK_MODEL_PROVIDER,
                model_parameters=mock_model_parameters(),
                topic_snapshot={"title": "Mock Demo", "description": "", "keywords": ["mock"]},
                project_metadata={"mock_mode": {"provider_free": True, "deterministic": True}},
                prompt_dir=prompt_dir,
                repo_root=root,
            )

            run_root = Path(result["run_root"])
            self.assertEqual(result["completed_rounds"], 2)
            self.assertTrue((run_root / "run_config.json").exists())
            self.assertTrue((run_root / "run_summary.json").exists())
            self.assertTrue((run_root / "round_metrics.json").exists())
            self.assertTrue((project_dir / "checkpoint.json").exists())
            self.assertTrue((project_dir / "score_history.json").exists())
            self.assertTrue((project_dir / "best_output.md").exists())

            run_config = json.loads((run_root / "run_config.json").read_text(encoding="utf-8"))
            run_summary = json.loads((run_root / "run_summary.json").read_text(encoding="utf-8"))
            round_metrics = json.loads(
                (run_root / "round_metrics.json").read_text(encoding="utf-8")
            )
            score_history = json.loads(
                (project_dir / "score_history.json").read_text(encoding="utf-8")
            )

            self.assertEqual(run_config["mode"], "mock")
            self.assertEqual(run_config["model"]["provider"], MOCK_MODEL_PROVIDER)
            self.assertEqual(run_config["model"]["name"], MOCK_MODEL_NAME)
            self.assertTrue(run_config["model"]["provider_free"])
            self.assertTrue(run_config["model"]["deterministic"])
            self.assertEqual(run_summary["mode"], "mock")
            self.assertEqual(run_summary["completed_rounds"], 2)
            self.assertEqual(run_summary["best_score"], 76)
            self.assertEqual(run_summary["rubric_round_count"], 2)
            self.assertGreater(run_summary["total_estimated_tokens"], 0)
            self.assertEqual(round_metrics[0]["score"], 73.0)
            self.assertEqual(round_metrics[1]["score"], 76.0)
            self.assertEqual(score_history[-1]["model"], MOCK_MODEL_NAME)
            self.assertEqual(score_history[-1]["drafting_mode"], "best_guided")
            self.assertIn(
                "Mock Revised Output Round 2", (project_dir / "best_output.md").read_text()
            )

    def test_cli_mock_mode_skips_provider_discovery_and_client_creation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "projects" / "example"
            project_dir.mkdir(parents=True)
            (project_dir / "task.md").write_text("# Mock task\n", encoding="utf-8")
            args = SimpleNamespace(
                session=False,
                diagnostic=False,
                continuous=False,
                resume=False,
                survey=False,
                survey_output=None,
                mock=True,
                compare_runs=None,
                compare_output=None,
                analyze_run=None,
                analyze_output=None,
                model=None,
                provider=None,
                gemini_api_key_env=None,
                project=None,
                cloud_free_discover=False,
                cloud_free_profile=False,
                free_runner_preset=None,
                disable_cloud_free_mode=False,
                min_delay_seconds=None,
                max_delay_seconds=None,
                max_retries=None,
                prompt_budget_chars=None,
                max_prompt_chars=None,
                max_rounds=None,
                drafting_mode=None,
                benchmark_preset=None,
                max_provider_quota_failures=2,
            )

            with (
                patch.object(cli_module, "parse_args", return_value=args),
                patch.object(cli_module, "load_app_config", return_value=AppConfig()),
                patch.object(
                    cli_module,
                    "load_project_input",
                    return_value=SimpleNamespace(
                        project_name="example",
                        project_dir=project_dir,
                        task_path=project_dir / "task.md",
                        task_text="# Mock task",
                        project_title="Mock task",
                        source_kind="example_default",
                        as_metadata=lambda: {"project_name": "example"},
                    ),
                ),
                patch.object(
                    cli_module,
                    "acquire_run_lock",
                    return_value=(project_dir / "run.lock", None),
                ),
                patch.object(cli_module, "release_run_lock"),
                patch.object(cli_module, "run_iterative_rounds") as run_rounds,
                patch.object(cli_module, "list_installed_ollama_models") as list_models,
                patch.object(cli_module, "create_llm_client") as create_client,
            ):
                cli_module.main()

            list_models.assert_not_called()
            create_client.assert_not_called()
            run_rounds.assert_called_once()
            kwargs = run_rounds.call_args.kwargs
            self.assertIsInstance(kwargs["agents"], MockResearchAgents)
            self.assertEqual(kwargs["mode"], "mock")
            self.assertEqual(kwargs["model_provider"], MOCK_MODEL_PROVIDER)
            self.assertEqual(kwargs["model_name"], MOCK_MODEL_NAME)
            self.assertEqual(kwargs["max_rounds"], MOCK_DEFAULT_ROUNDS)
            self.assertEqual(kwargs["per_agent_timeout_seconds"], 1)


if __name__ == "__main__":
    unittest.main()
