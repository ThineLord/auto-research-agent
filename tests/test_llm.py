from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import src.llm as llm_module
from src.llm import GeminiClient, OllamaClient


class FakeGenerateContentConfig:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class FakeGeminiQuotaError(RuntimeError):
    status_code = 429


class LlmClientTests(unittest.TestCase):
    def test_generate_omits_response_format_by_default(self) -> None:
        response = SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"message": {"content": "ok"}},
        )

        with patch.object(llm_module.requests, "post", return_value=response) as post:
            output = OllamaClient(base_url="http://localhost:11434", model="test").generate(
                system_prompt=None,
                user_prompt="hello",
            )

        self.assertEqual(output, "ok")
        payload = post.call_args.kwargs["json"]
        self.assertNotIn("format", payload)

    def test_generate_includes_response_format_when_requested(self) -> None:
        response = SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"message": {"content": '{"score": 80}'}},
        )
        response_format = {
            "type": "object",
            "properties": {"score": {"type": "number"}},
            "required": ["score"],
        }

        with patch.object(llm_module.requests, "post", return_value=response) as post:
            OllamaClient(base_url="http://localhost:11434", model="test").generate(
                system_prompt="judge",
                user_prompt="score this",
                response_format=response_format,
            )

        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["format"], response_format)

    def test_ollama_prompt_too_large_fails_before_request(self) -> None:
        with patch.object(llm_module.requests, "post") as post:
            with self.assertRaisesRegex(RuntimeError, "Ollama prompt too large"):
                OllamaClient(
                    base_url="http://localhost:11434",
                    model="test",
                    max_prompt_chars=10,
                ).generate(
                    agent_name="draft",
                    system_prompt="system",
                    user_prompt="this prompt is too long",
                )

        post.assert_not_called()

    def test_ollama_request_start_logs_provider_model_stage_and_prompt_size(self) -> None:
        response = SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"message": {"content": "ok"}},
        )

        with (
            patch.object(llm_module.requests, "post", return_value=response),
            patch.object(llm_module.logger, "info") as log_info,
        ):
            OllamaClient(base_url="http://localhost:11434", model="test").generate(
                agent_name="draft",
                system_prompt="sys",
                user_prompt="hello",
            )

        start_call = next(
            call for call in log_info.call_args_list if call.args[0] == "llm_request_start"
        )
        extra = start_call.kwargs["extra"]
        self.assertEqual(extra["provider"], "ollama")
        self.assertEqual(extra["model"], "test")
        self.assertEqual(extra["stage"], "draft")
        self.assertEqual(extra["prompt_chars"], 8)
        self.assertEqual(extra["timeout_seconds"], 120)

    def test_gemini_generate_calls_google_genai_client(self) -> None:
        generate_content = Mock(return_value=SimpleNamespace(text=" OK "))
        fake_client = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
        fake_genai = SimpleNamespace(Client=Mock(return_value=fake_client))
        fake_types = SimpleNamespace(GenerateContentConfig=FakeGenerateContentConfig)

        with (
            patch.object(llm_module, "_load_google_genai", return_value=(fake_genai, fake_types)),
            patch.dict(llm_module.os.environ, {"GEMINI_API_KEY": "test-key"}, clear=True),
        ):
            output = GeminiClient(model="gemini-3.5-flash").generate(
                agent_name="draft",
                system_prompt="system",
                user_prompt="hello",
                temperature=0.7,
                top_p=0.8,
            )

        self.assertEqual(output, "OK")
        fake_genai.Client.assert_called_once_with()
        generate_content.assert_called_once()
        kwargs = generate_content.call_args.kwargs
        self.assertEqual(kwargs["model"], "gemini-3.5-flash")
        self.assertEqual(kwargs["contents"], "hello")
        self.assertEqual(kwargs["config"].kwargs["system_instruction"], "system")
        self.assertEqual(kwargs["config"].kwargs["temperature"], 0.7)
        self.assertEqual(kwargs["config"].kwargs["top_p"], 0.8)

    def test_gemini_generate_passes_structured_response_config(self) -> None:
        generate_content = Mock(return_value=SimpleNamespace(text='{"score": 80}'))
        fake_client = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
        fake_genai = SimpleNamespace(Client=Mock(return_value=fake_client))
        fake_types = SimpleNamespace(GenerateContentConfig=FakeGenerateContentConfig)
        response_format = {
            "type": "object",
            "properties": {"score": {"type": "number"}},
            "required": ["score"],
        }

        with patch.object(
            llm_module,
            "_load_google_genai",
            return_value=(fake_genai, fake_types),
        ):
            GeminiClient(model="gemini-3.5-flash", api_key="local-key").generate(
                system_prompt="judge",
                user_prompt="score this",
                response_format=response_format,
            )

        config = generate_content.call_args.kwargs["config"]
        self.assertEqual(config.kwargs["response_mime_type"], "application/json")
        self.assertEqual(config.kwargs["response_json_schema"], response_format)
        fake_genai.Client.assert_called_once_with(api_key="local-key")

    def test_gemini_generate_requires_api_key_source(self) -> None:
        with patch.dict(llm_module.os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "Gemini API key is missing"):
                GeminiClient(model="gemini-3.5-flash", api_key_env="MISSING_KEY").generate(
                    system_prompt=None,
                    user_prompt="hello",
                )

    def test_gemini_generate_exception_does_not_leak_api_key(self) -> None:
        secret = "SECRET-KEY"
        generate_content = Mock(side_effect=RuntimeError(f"bad request {secret}"))
        fake_client = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
        fake_genai = SimpleNamespace(Client=Mock(return_value=fake_client))
        fake_types = SimpleNamespace(GenerateContentConfig=FakeGenerateContentConfig)

        with patch.object(
            llm_module,
            "_load_google_genai",
            return_value=(fake_genai, fake_types),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                GeminiClient(model="gemini-3.5-flash", api_key=secret).generate(
                    system_prompt=None,
                    user_prompt="hello",
                )

        self.assertIn("Failed to call Gemini API", str(ctx.exception))
        self.assertNotIn(secret, str(ctx.exception))

    def test_gemini_provider_events_record_quota_error(self) -> None:
        generate_content = Mock(
            side_effect=FakeGeminiQuotaError(
                "RESOURCE_EXHAUSTED quota exceeded for requests per day"
            )
        )
        fake_client = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
        fake_genai = SimpleNamespace(Client=Mock(return_value=fake_client))
        fake_types = SimpleNamespace(GenerateContentConfig=FakeGenerateContentConfig)

        with tempfile.TemporaryDirectory() as tmp:
            event_path = Path(tmp) / "provider_events.jsonl"
            client = GeminiClient(model="gemini-3.5-flash", api_key="local-key")
            client.set_provider_context(
                provider_event_path=event_path,
                run_id="run-1",
                round_index=7,
                stage="draft",
            )

            with patch.object(
                llm_module,
                "_load_google_genai",
                return_value=(fake_genai, fake_types),
            ):
                with self.assertRaisesRegex(RuntimeError, "PROVIDER_QUOTA_EXHAUSTED"):
                    client.generate(
                        agent_name="draft",
                        system_prompt=None,
                        user_prompt="hello",
                    )

            events = [
                json.loads(line) for line in event_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(events[0]["event"], "request_start")
            self.assertEqual(events[0]["round"], 7)
            self.assertEqual(events[0]["stage"], "draft")
            self.assertEqual(events[0]["error_type"], "")
            self.assertEqual(events[1]["event"], "request_error")
            self.assertEqual(events[1]["error_type"], "daily_quota_exhausted")
            self.assertTrue(events[1]["rate_limited"])
            self.assertTrue(events[1]["daily_quota_exhausted"])


if __name__ == "__main__":
    unittest.main()
