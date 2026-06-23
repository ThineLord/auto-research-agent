from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from src.config import (
    DEFAULT_GEMINI_MAX_PROMPT_CHARS,
    DEFAULT_GEMINI_MODEL,
    DEFAULT_GEMINI_MODELS,
    DEFAULT_MODEL_NAME,
    DEFAULT_OLLAMA_MAX_PROMPT_CHARS,
    MODEL_PROVIDER_GEMINI,
    MODEL_PROVIDER_OLLAMA,
    ConfigValidationError,
    LiteratureSurveyConfig,
    format_model_label,
    format_topic_context,
    load_app_config,
    load_config,
    load_default_model_name,
    resolve_model_provider_settings,
    resolve_model_settings,
    resolve_runtime_limits,
    save_default_model_name,
    save_default_model_selection,
)

ROOT = Path(__file__).resolve().parents[1]


class ConfigValidationTests(unittest.TestCase):
    def write_config(self, text: str) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        config_path = Path(tmp.name) / "config.yaml"
        config_path.write_text(text, encoding="utf-8")
        return config_path

    def test_sample_config_file_loads_as_typed_and_normalized_config(self) -> None:
        config_path = ROOT / "config.example.yaml"
        config = load_app_config(config_path)

        self.assertEqual(config.model.provider, "ollama")
        self.assertEqual(config.model.name, "qwen3:8b")
        self.assertEqual(config.model.max_prompt_chars, DEFAULT_OLLAMA_MAX_PROMPT_CHARS)
        self.assertEqual(config.model.gemini.api_key_env, "GEMINI_API_KEY")
        self.assertEqual(config.model.gemini.api_key, "")
        self.assertEqual(config.model.gemini.models, DEFAULT_GEMINI_MODELS)
        self.assertTrue(config.cloud_free.cloud_free_mode)
        self.assertEqual(config.cloud_free.free_runner_preset, "auto_long_run")
        self.assertEqual(config.cloud_free.max_retries, 5)
        self.assertEqual(config.literature_survey, LiteratureSurveyConfig())
        self.assertEqual(config.project_name, "example")
        self.assertIn("Example Research Planning Task", config.topic.title)
        self.assertIn("research", config.topic.keywords)
        self.assertGreaterEqual(config.runtime.normal_max_runtime_seconds, 60)

        normalized = load_config(config_path)
        self.assertEqual(normalized["model"]["name"], config.model.name)
        self.assertEqual(normalized["topic"]["title"], config.topic.title)
        self.assertEqual(normalized["topic"]["keywords"], list(config.topic.keywords))
        self.assertEqual(normalized["literature_survey"]["output_dir"], "survey")
        self.assertNotIn("temperature", normalized)
        self.assertEqual(
            resolve_model_settings(config),
            (config.model.name, config.model.temperature, config.model.timeout_seconds),
        )
        self.assertEqual(
            resolve_runtime_limits(normalized),
            (
                config.runtime.normal_max_runtime_seconds,
                config.runtime.continuous_max_runtime_seconds,
            ),
        )

    def test_legacy_model_string_and_top_level_model_settings_still_work(self) -> None:
        config_path = self.write_config(
            """
model: llama3.1:8b
temperature: 0.7
timeout_seconds: 120
runtime:
  normal_max_runtime_seconds: 120
  continuous_max_runtime_seconds: 240
"""
        )

        config = load_app_config(config_path)

        self.assertEqual(config.model.name, "llama3.1:8b")
        self.assertEqual(config.model.provider, MODEL_PROVIDER_OLLAMA)
        self.assertEqual(config.model.temperature, 0.7)
        self.assertEqual(config.model.timeout_seconds, 120)
        self.assertEqual(config.model.max_prompt_chars, DEFAULT_OLLAMA_MAX_PROMPT_CHARS)
        self.assertEqual(resolve_model_settings(config.as_dict()), ("llama3.1:8b", 0.7, 120))
        self.assertEqual(
            resolve_model_provider_settings(config.as_dict()),
            (
                MODEL_PROVIDER_OLLAMA,
                "llama3.1:8b",
                0.7,
                120,
                config.model.gemini,
            ),
        )
        self.assertEqual(resolve_runtime_limits(config), (120, 240))

    def test_topic_defaults_are_generic_when_not_configured(self) -> None:
        config_path = self.write_config("model:\n  name: qwen3:8b\n")

        config = load_app_config(config_path)

        self.assertEqual(config.project_name, "example")
        self.assertEqual(config.topic.title, "Configured Research Topic")
        self.assertIn("evaluation", config.topic.keywords)
        self.assertIn("Configured Research Topic", format_topic_context(config.topic))

    def test_topic_config_validates_and_deduplicates_keywords(self) -> None:
        config_path = self.write_config(
            """
topic:
  title: Graph Retrieval Evaluation
  description: Planning repeatable graph retrieval experiments.
  keywords:
    - graph
    - retrieval
    - Graph
"""
        )

        config = load_app_config(config_path)

        self.assertEqual(config.topic.title, "Graph Retrieval Evaluation")
        self.assertEqual(config.topic.keywords, ("graph", "retrieval"))

    def test_nested_model_settings_take_precedence_over_legacy_top_level_values(self) -> None:
        config_path = self.write_config(
            """
model:
  name: qwen3:14b
  temperature: 0.2
  timeout_seconds: 200
  max_prompt_chars: 16000
temperature: 0.9
timeout_seconds: 20
"""
        )

        config = load_app_config(config_path)

        self.assertEqual(resolve_model_settings(config), ("qwen3:14b", 0.2, 200))
        self.assertEqual(config.model.max_prompt_chars, 16000)

    def test_gemini_model_config_loads_and_formats_cloud_label(self) -> None:
        config_path = self.write_config(
            """
model:
  provider: gemini
  name: gemini-2.5-pro
  temperature: 0.3
  timeout_seconds: 300
  gemini:
    api_key_env: GEMINI_API_KEY
    api_key: ""
    models:
      - gemini-3.5-flash
      - gemini-2.5-pro
      - gemini-2.5-pro
"""
        )

        config = load_app_config(config_path)

        self.assertEqual(config.model.provider, MODEL_PROVIDER_GEMINI)
        self.assertEqual(config.model.name, "gemini-2.5-pro")
        self.assertEqual(config.model.max_prompt_chars, DEFAULT_GEMINI_MAX_PROMPT_CHARS)
        self.assertEqual(config.model.gemini.models, ("gemini-3.5-flash", "gemini-2.5-pro"))
        self.assertEqual(
            resolve_model_provider_settings(config),
            (
                MODEL_PROVIDER_GEMINI,
                "gemini-2.5-pro",
                0.3,
                300,
                config.model.gemini,
            ),
        )
        self.assertEqual(
            format_model_label(MODEL_PROVIDER_GEMINI, "gemini-2.5-pro"),
            "gemini:gemini-2.5-pro",
        )
        self.assertEqual(format_model_label(MODEL_PROVIDER_OLLAMA, "qwen3:8b"), "qwen3:8b")

    def test_gemini_provider_uses_default_model_when_name_is_missing(self) -> None:
        config_path = self.write_config("model:\n  provider: gemini\n")

        config = load_app_config(config_path)

        self.assertEqual(config.model.provider, MODEL_PROVIDER_GEMINI)
        self.assertEqual(config.model.name, DEFAULT_GEMINI_MODEL)

    def test_rejects_malformed_yaml_and_non_mapping_yaml(self) -> None:
        malformed_path = self.write_config("model: [\n")
        list_path = self.write_config("- model\n")

        with self.assertRaisesRegex(ConfigValidationError, "failed to parse YAML"):
            load_app_config(malformed_path)
        with self.assertRaisesRegex(ConfigValidationError, "top-level YAML must be a mapping"):
            load_app_config(list_path)

    def test_rejects_unknown_keys_at_each_config_level(self) -> None:
        cases = [
            ("unexpected: true\n", "config: unknown key"),
            ("model:\n  name: qwen3:8b\n  extra: true\n", "config.model: unknown key"),
            (
                "model:\n  gemini:\n    extra: true\n",
                "config.model.gemini: unknown key",
            ),
            ("topic:\n  title: Demo\n  extra: true\n", "config.topic: unknown key"),
            (
                "runtime:\n  normal_max_runtime_seconds: 120\n  extra: true\n",
                "config.runtime: unknown key",
            ),
            (
                "cloud_free:\n  extra: true\n",
                "config.cloud_free: unknown key",
            ),
            (
                "literature_survey:\n  extra: true\n",
                "config.literature_survey: unknown key",
            ),
        ]

        for text, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ConfigValidationError, message):
                    load_app_config(self.write_config(text))

    def test_rejects_wrong_numeric_types_and_invalid_ranges(self) -> None:
        cases = [
            ("model:\n  temperature: true\n", "config.model.temperature: must be a number"),
            ("model:\n  timeout_seconds: '300'\n", "config.model.timeout_seconds"),
            ("model:\n  max_prompt_chars: 999\n", "config.model.max_prompt_chars"),
            ("max_rounds: 0\n", "config.max_rounds"),
            ("stop_if_no_improvement_rounds: -1\n", "config.stop_if_no_improvement_rounds"),
            ("top_p: 0\n", "config.top_p"),
            ("model:\n  timeout_seconds: 301\n", "config.model.timeout_seconds"),
        ]

        for text, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ConfigValidationError, message):
                    load_app_config(self.write_config(text))

    def test_rejects_invalid_strings_and_runtime_ordering(self) -> None:
        cases = [
            ("model:\n  provider: openai\n", "config.model.provider"),
            ("model:\n  name: '   '\n", "config.model.name"),
            ("model:\n  gemini:\n    api_key_env: ' '\n", "config.model.gemini.api_key_env"),
            ("model:\n  gemini:\n    api_key: 123\n", "config.model.gemini.api_key"),
            ("model:\n  gemini:\n    models: []\n", "config.model.gemini.models"),
            (
                "model:\n  gemini:\n    models:\n      - gemini-3.5-flash\n      - 123\n",
                "config.model.gemini.models",
            ),
            ("project_name: ../private\n", "config.project_name"),
            ("topic: demo\n", "config.topic"),
            ("topic:\n  title: ' '\n", "config.topic.title"),
            ("topic:\n  keywords: []\n", "config.topic.keywords"),
            ("topic:\n  keywords: graph\n", "config.topic.keywords"),
            ("ollama_base_url: localhost:11434\n", "config.ollama_base_url"),
            ("runtime:\n  normal_max_runtime_seconds: 59\n", "normal_max_runtime_seconds"),
            (
                "runtime:\n  normal_max_runtime_seconds: 120\n  continuous_max_runtime_seconds: 60\n",
                "continuous_max_runtime_seconds",
            ),
            ("cloud_free:\n  free_runner_preset: paid_fast\n", "free_runner_preset"),
            ("cloud_free:\n  max_retries: -1\n", "max_retries"),
            ("cloud_free:\n  prompt_budget_chars: 999\n", "prompt_budget_chars"),
            ("literature_survey:\n  include_task: 'yes'\n", "include_task"),
            ("literature_survey:\n  max_source_files: 0\n", "max_source_files"),
            ("literature_survey:\n  max_papers: 0\n", "max_papers"),
            ("literature_survey:\n  output_dir: ../reports\n", "output_dir"),
        ]

        for text, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ConfigValidationError, message):
                    load_app_config(self.write_config(text))

    def test_default_model_helpers_use_validation_when_reading_and_saving(self) -> None:
        config_path = self.write_config(
            """
model: llama3.1:8b
temperature: 0.6
timeout_seconds: 180
"""
        )

        self.assertEqual(load_default_model_name(config_path), "llama3.1:8b")
        self.assertIsNone(save_default_model_name(config_path, "qwen3:14b"))

        saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["model"]["name"], "qwen3:14b")
        self.assertEqual(saved["model"]["provider"], "ollama")
        self.assertEqual(saved["model"]["temperature"], 0.6)
        self.assertEqual(saved["model"]["timeout_seconds"], 180)

        bad_config_path = self.write_config("unknown: true\n")
        before = bad_config_path.read_text(encoding="utf-8")
        err = save_default_model_name(bad_config_path, "qwen3:8b")

        self.assertIn("invalid config.yaml", err or "")
        self.assertEqual(bad_config_path.read_text(encoding="utf-8"), before)
        with self.assertRaises(ConfigValidationError):
            load_default_model_name(bad_config_path)

    def test_default_model_selection_saves_provider_model_and_non_sensitive_gemini_settings(
        self,
    ) -> None:
        config_path = self.write_config(
            """
model:
  provider: gemini
  temperature: 0.5
  timeout_seconds: 200
  gemini:
    api_key_env: OLD_GEMINI_KEY
    api_key: super-secret
    models:
      - gemini-3.5-flash
      - gemini-2.5-pro
"""
        )

        self.assertIsNone(
            save_default_model_selection(
                config_path,
                provider=MODEL_PROVIDER_GEMINI,
                model_name="gemini-2.5-pro",
                gemini_api_key_env="TEAM_GEMINI_KEY",
            )
        )

        saved_text = config_path.read_text(encoding="utf-8")
        saved = yaml.safe_load(saved_text)
        self.assertEqual(saved["model"]["provider"], MODEL_PROVIDER_GEMINI)
        self.assertEqual(saved["model"]["name"], "gemini-2.5-pro")
        self.assertEqual(saved["model"]["gemini"]["api_key_env"], "TEAM_GEMINI_KEY")
        self.assertEqual(saved["model"]["gemini"]["api_key"], "")
        self.assertNotIn("super-secret", saved_text)

        self.assertIsNone(
            save_default_model_selection(
                config_path,
                provider=MODEL_PROVIDER_OLLAMA,
                model_name="",
            )
        )
        saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["model"]["provider"], MODEL_PROVIDER_OLLAMA)
        self.assertEqual(saved["model"]["name"], DEFAULT_MODEL_NAME)


if __name__ == "__main__":
    unittest.main()
