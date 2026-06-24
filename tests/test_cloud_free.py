from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from rich.console import Console

import src.cli as cli_module
from src.cloud_free import (
    FREE_RUNNER_QUALITY,
    FREE_RUNNER_VOLUME,
    CloudFreeConfig,
    CloudFreeDailyQuotaExhausted,
    CloudFreeScheduler,
    CloudModelProfile,
    apply_cloud_prompt_budget,
    build_candidate_pool,
    choose_fallback_model,
    classify_gemini_error,
    classify_model,
    filter_safe_text_models,
    load_discovery_artifact,
    load_profile_artifact,
    model_info_from_sdk_model,
    profile_free_cloud_models,
    recommend_free_cloud_model,
    save_profile_artifact,
)
from src.config import (
    MODEL_PROVIDER_GEMINI,
    MODEL_PROVIDER_OLLAMA,
    AppConfig,
    GeminiConfig,
    ModelConfig,
)
from src.llm import OllamaClient, create_llm_client


class CloudFreePolicyTests(unittest.TestCase):
    def _cloud_free_cli_args(self, **overrides: object) -> SimpleNamespace:
        values: dict[str, object] = {
            "session": False,
            "diagnostic": False,
            "continuous": False,
            "resume": False,
            "survey": False,
            "survey_output": None,
            "mock": False,
            "compare_runs": None,
            "compare_output": None,
            "analyze_run": None,
            "analyze_output": None,
            "model": None,
            "provider": MODEL_PROVIDER_GEMINI,
            "gemini_api_key_env": None,
            "project": "demo",
            "cloud_free_discover": False,
            "cloud_free_profile": False,
            "free_runner_preset": None,
            "disable_cloud_free_mode": False,
            "min_delay_seconds": None,
            "max_delay_seconds": None,
            "max_retries": None,
            "prompt_budget_chars": None,
            "max_prompt_chars": None,
            "max_rounds": None,
            "drafting_mode": None,
            "benchmark_preset": None,
            "max_provider_quota_failures": 2,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def test_model_filtering_excludes_paid_preview_live_tool_variants(self) -> None:
        raw = [
            classify_model(model_id="gemini-3.5-flash"),
            classify_model(model_id="gemini-2.5-pro"),
            classify_model(model_id="gemini-2.5-flash-preview"),
            classify_model(model_id="gemini-live-001"),
            classify_model(model_id="gemini-tts"),
            classify_model(model_id="gemini-flash-grounding-search"),
            classify_model(model_id="gemini-flash-maps"),
            classify_model(model_id="gemini-flash-code-execution-tool"),
            classify_model(model_id="gemma-3-1b-it"),
        ]

        safe = filter_safe_text_models(raw)

        self.assertEqual(
            [model.model_id for model in safe],
            ["gemini-3.5-flash", "gemma-3-1b-it"],
        )

    def test_model_discovery_metadata_handles_missing_fields(self) -> None:
        info = model_info_from_sdk_model(SimpleNamespace(name="models/gemma-3-1b-it"))

        self.assertEqual(info.model_id, "gemma-3-1b-it")
        self.assertEqual(info.supported_generation_methods, ())
        self.assertIsNone(info.input_token_limit)
        self.assertTrue(info.safe_text_generation)

    def test_candidate_pool_marks_configured_unavailable_cleanly(self) -> None:
        candidates = build_candidate_pool(
            discovered_models=[],
            configured_models=["gemini-3.5-flash", "gemma-3-1b-it"],
        )

        by_id = {candidate.model_id: candidate for candidate in candidates}
        self.assertIn("gemini-3.5-flash", by_id)
        self.assertFalse(by_id["gemini-3.5-flash"].available)
        self.assertIn("gemma-3-1b-it", by_id)

    def test_profiler_handles_unavailable_models_without_key_leak(self) -> None:
        secret = "SECRET-KEY"
        candidate = classify_model(model_id="gemini-3.5-flash")

        with patch(
            "src.llm.GeminiClient.generate",
            side_effect=RuntimeError(f"model unavailable api_key={secret}"),
        ):
            profiles = profile_free_cloud_models(
                candidates=[candidate],
                api_key_env="GEMINI_API_KEY",
                api_key=secret,
            )

        self.assertEqual(len(profiles), 1)
        self.assertFalse(profiles[0].reachable)
        self.assertNotIn(secret, profiles[0].error_message)

    def test_scheduler_uses_retry_after_when_present(self) -> None:
        class RetryAfterError(Exception):
            status_code = 429
            headers = {"Retry-After": "7"}

        sleeps: list[float] = []
        calls = {"count": 0}
        scheduler = CloudFreeScheduler(
            model_id="gemini-3.5-flash",
            config=CloudFreeConfig(min_delay_seconds=1, max_retries=2),
            sleep_func=sleeps.append,
            monotonic_func=lambda: 0.0,
        )

        def operation() -> str:
            calls["count"] += 1
            if calls["count"] == 1:
                raise RetryAfterError("429 resource exhausted")
            return "ok"

        self.assertEqual(scheduler.call(operation), "ok")
        self.assertEqual(sleeps, [7.0])
        self.assertEqual(scheduler.status()["recent_429_count"], 1)

    def test_scheduler_exponential_backoff_with_jitter_uses_mocked_sleep(self) -> None:
        class RateLimitError(Exception):
            status_code = 429

        sleeps: list[float] = []
        calls = {"count": 0}
        scheduler = CloudFreeScheduler(
            model_id="gemini-2.5-flash-lite",
            config=CloudFreeConfig(min_delay_seconds=1, max_delay_seconds=100, max_retries=1),
            sleep_func=sleeps.append,
            monotonic_func=lambda: 0.0,
            random_uniform=lambda _a, _b: 0.5,
        )

        def operation() -> str:
            calls["count"] += 1
            if calls["count"] == 1:
                raise RateLimitError("429 resource exhausted")
            return "ok"

        self.assertEqual(scheduler.call(operation), "ok")
        self.assertEqual(sleeps, [4.1])

    def test_daily_quota_detection_pauses_instead_of_spinning(self) -> None:
        class DailyQuotaError(Exception):
            status_code = 429

        error = DailyQuotaError("Resource exhausted: RPD daily quota exceeded")
        info = classify_gemini_error(error)

        self.assertTrue(info.daily_quota_exhausted)

        scheduler = CloudFreeScheduler(
            model_id="gemini-3.5-flash",
            config=CloudFreeConfig(min_delay_seconds=0, max_retries=5),
            sleep_func=lambda _seconds: None,
        )
        with self.assertRaises(CloudFreeDailyQuotaExhausted):
            scheduler.call(lambda: (_ for _ in ()).throw(error))
        self.assertEqual(scheduler.status()["status"], "paused_until_reset")

    def test_wrapped_rate_limit_text_is_still_classified(self) -> None:
        info = classify_gemini_error(RuntimeError("Gemini free-tier rate limit reached"))

        self.assertTrue(info.rate_limited)
        self.assertTrue(info.retryable)
        self.assertEqual(info.error_type, "rate_limited")

    def test_prompt_budget_guard_preserves_critical_state(self) -> None:
        prompt = (
            "# Topic Context\nKeep this topic.\n\n"
            "# Research Task\nImportant task instruction.\n\n"
            "# Project Memory\n"
            + ("old memory " * 1000)
            + "\n\n# Previous Best (optional)\nLatest strong draft.\n\n"
            "# Previous Judge Feedback (optional)\nLatest judge feedback.\n"
        )

        compacted = apply_cloud_prompt_budget(prompt, 1200)

        self.assertLessEqual(len(compacted), 1200)
        self.assertIn("Important task instruction.", compacted)
        self.assertIn("Latest strong draft.", compacted)
        self.assertIn("Latest judge feedback.", compacted)
        self.assertIn("truncated for cloud free prompt budget", compacted)

    def test_fallback_never_selects_blocked_models(self) -> None:
        candidates = [
            classify_model(model_id="gemini-2.5-pro"),
            classify_model(model_id="gemini-2.5-flash-lite"),
        ]

        self.assertEqual(
            choose_fallback_model(current_model="gemini-3.5-flash", candidates=candidates),
            "gemini-2.5-flash-lite",
        )

    def test_quality_and_volume_recommendations_use_expected_preferences(self) -> None:
        candidates = [
            classify_model(model_id="gemini-3.5-flash"),
            classify_model(model_id="gemini-2.5-flash-lite"),
            classify_model(model_id="gemma-3-high-tpm"),
        ]
        profiles = [
            CloudModelProfile(
                model_id=candidate.model_id,
                reachable=True,
                structured_output_works=True,
                score_parsing_works=True,
                diagnostic_score=87,
            )
            for candidate in candidates
        ]

        quality = recommend_free_cloud_model(
            candidates=candidates,
            profiles=profiles,
            preset=FREE_RUNNER_QUALITY,
        )
        volume = recommend_free_cloud_model(
            candidates=candidates,
            profiles=profiles,
            preset=FREE_RUNNER_VOLUME,
        )

        self.assertIsNotNone(quality)
        self.assertEqual(quality.model_id, "gemini-3.5-flash")
        self.assertIsNotNone(volume)
        self.assertEqual(volume.model_id, "gemma-3-high-tpm")

    def test_profile_artifact_does_not_store_api_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            secret = "SECRET-KEY"
            path = save_profile_artifact(
                project_dir,
                [CloudModelProfile(model_id="gemini-3.5-flash", error_message="safe")],
            )

            self.assertNotIn(secret, path.read_text(encoding="utf-8"))
            self.assertNotIn("api_key", path.read_text(encoding="utf-8").lower())

    def test_stale_cloud_free_artifact_paths_return_empty_lists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            artifacts = project_dir / "artifacts"
            artifacts.mkdir()
            (artifacts / "cloud_free_profile.json").mkdir()
            (artifacts / "cloud_free_models.json").mkdir()

            self.assertEqual(load_profile_artifact(project_dir), [])
            self.assertEqual(load_discovery_artifact(project_dir), [])

    def test_cloud_free_discovery_cli_masks_project_and_artifact_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            temp_root = Path(tmp)
            project_dir = temp_root / "projects" / "demo"
            project_dir.mkdir(parents=True)
            artifact = project_dir / "artifacts" / "cloud_free_models.json"
            console = Console(record=True, width=120)
            args = self._cloud_free_cli_args(cloud_free_discover=True)
            config = AppConfig(
                model=ModelConfig(
                    provider=MODEL_PROVIDER_GEMINI,
                    gemini=GeminiConfig(api_key="local-key"),
                )
            )
            project_input = SimpleNamespace(
                project_name="demo",
                project_dir=project_dir,
                task_path=project_dir / "task.md",
                task_text="# Demo",
                project_title="Demo",
                source_kind="explicit",
                as_metadata=lambda: {"project_name": "demo"},
            )

            with (
                patch.object(cli_module, "parse_args", return_value=args),
                patch.object(cli_module, "Console", return_value=console),
                patch.object(cli_module, "load_app_config", return_value=config),
                patch.object(cli_module, "load_project_input", return_value=project_input),
                patch.object(
                    cli_module,
                    "discover_free_cloud_models",
                    return_value=([classify_model(model_id="gemini-3.5-flash")], ""),
                ),
                patch.object(cli_module, "save_discovery_artifact", return_value=artifact),
            ):
                cli_module.main()

            output = console.export_text(styles=False)
            self.assertIn("Saved discovery artifact:", output)
            self.assertIn("<repo>/cloud_free_models.json", output)
            self.assertIn("task=<repo>/task.md", output)
            self.assertNotIn(str(project_dir), output)
            self.assertNotIn(str(artifact), output)

    def test_cloud_free_profile_cli_masks_project_and_artifact_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            temp_root = Path(tmp)
            project_dir = temp_root / "projects" / "demo"
            project_dir.mkdir(parents=True)
            artifact = project_dir / "artifacts" / "cloud_free_profile.json"
            console = Console(record=True, width=120)
            args = self._cloud_free_cli_args(cloud_free_profile=True)
            config = AppConfig(
                model=ModelConfig(
                    provider=MODEL_PROVIDER_GEMINI,
                    gemini=GeminiConfig(api_key="local-key"),
                )
            )
            project_input = SimpleNamespace(
                project_name="demo",
                project_dir=project_dir,
                task_path=project_dir / "task.md",
                task_text="# Demo",
                project_title="Demo",
                source_kind="explicit",
                as_metadata=lambda: {"project_name": "demo"},
            )

            with (
                patch.object(cli_module, "parse_args", return_value=args),
                patch.object(cli_module, "Console", return_value=console),
                patch.object(cli_module, "load_app_config", return_value=config),
                patch.object(cli_module, "load_project_input", return_value=project_input),
                patch.object(
                    cli_module,
                    "discover_free_cloud_models",
                    return_value=([classify_model(model_id="gemini-3.5-flash")], ""),
                ),
                patch.object(cli_module, "save_discovery_artifact"),
                patch.object(
                    cli_module,
                    "profile_free_cloud_models",
                    return_value=[
                        CloudModelProfile(
                            model_id="gemini-3.5-flash",
                            reachable=True,
                            structured_output_works=True,
                            score_parsing_works=True,
                            diagnostic_score=87,
                        )
                    ],
                ),
                patch.object(cli_module, "save_profile_artifact", return_value=artifact),
            ):
                cli_module.main()

            output = console.export_text(styles=False)
            self.assertIn("Saved profile artifact:", output)
            self.assertIn("<repo>/cloud_free_profile.json", output)
            self.assertIn("task=<repo>/task.md", output)
            self.assertNotIn(str(project_dir), output)
            self.assertNotIn(str(artifact), output)

    def test_ollama_path_ignores_cloud_free_config(self) -> None:
        client = create_llm_client(
            provider=MODEL_PROVIDER_OLLAMA,
            model_name="qwen3:8b",
            ollama_base_url="http://localhost:11434",
            timeout_seconds=120,
            gemini_config=GeminiConfig(),
            cloud_free_config=CloudFreeConfig(),
        )

        self.assertIsInstance(client, OllamaClient)


if __name__ == "__main__":
    unittest.main()
