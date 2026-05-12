"""Local LLM client for Ollama."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import requests


@dataclass
class OllamaClient:
    base_url: str
    model: str
    timeout_seconds: int = 120

    def generate(
        self,
        *,
        system_prompt: Optional[str],
        user_prompt: str,
        temperature: float = 0.4,
        top_p: float = 0.9,
    ) -> str:
        """Generate a response from Ollama chat API."""
        url = f"{self.base_url.rstrip('/')}/api/chat"
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

        response = requests.post(url, json=payload, timeout=self.timeout_seconds)
        response.raise_for_status()
        data = response.json()

        return data.get("message", {}).get("content", "").strip()
