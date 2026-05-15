from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import src.llm as llm_module
from src.llm import OllamaClient


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


if __name__ == "__main__":
    unittest.main()
