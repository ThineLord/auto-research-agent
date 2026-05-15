"""Local LLM client for Ollama."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

import requests

MAX_PROMPT_CHARS = 32000


@dataclass
class OllamaClient:
    base_url: str
    model: str
    timeout_seconds: int = 120

    def generate(
        self,
        *,
        agent_name: str = "unknown",
        system_prompt: Optional[str],
        user_prompt: str,
        temperature: float = 0.4,
        top_p: float = 0.9,
    ) -> str:
        """Generate a response from Ollama chat API."""
        url = f"{self.base_url.rstrip('/')}/api/chat"
        if len(user_prompt) > MAX_PROMPT_CHARS:
            user_prompt = user_prompt[-MAX_PROMPT_CHARS:]

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "top_p": top_p,
            },
        }

        started = time.monotonic()
        print(
            f"[LLM] {agent_name} request start | system_chars={len(system_prompt or '')} "
            f"user_chars={len(user_prompt)} timeout={self.timeout_seconds}s"
        )
        try:
            response = requests.post(
                url,
                json=payload,
                timeout=(10, self.timeout_seconds),
            )
            response.raise_for_status()
            data = response.json()
        except requests.Timeout as exc:
            raise RuntimeError(
                "Ollama request timed out. "
                f"Increase timeout_seconds or check model/server health at {self.base_url}."
            ) from exc
        except requests.RequestException as exc:
            raise RuntimeError(
                "Failed to call Ollama API. Ensure Ollama is running at "
                f"{self.base_url} and model '{self.model}' is available."
            ) from exc

        elapsed = time.monotonic() - started
        content = data.get("message", {}).get("content", "").strip()
        print(
            f"[LLM] {agent_name} request end | response_chars={len(content)} elapsed={elapsed:.2f}s"
        )
        return content
