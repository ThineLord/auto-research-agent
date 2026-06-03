"""Provider-neutral LLM clients for Ollama and Gemini."""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol

import requests

from .config import (
    DEFAULT_GEMINI_API_KEY_ENV,
    MODEL_PROVIDER_GEMINI,
    MODEL_PROVIDER_OLLAMA,
    GeminiConfig,
)

MAX_PROMPT_CHARS = 32000
logger = logging.getLogger(__name__)


class LLMClientProtocol(Protocol):
    timeout_seconds: int

    def generate(
        self,
        *,
        agent_name: str = "unknown",
        system_prompt: Optional[str],
        user_prompt: str,
        temperature: float = 0.4,
        top_p: float = 0.9,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> str: ...


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
        response_format: Optional[Dict[str, Any]] = None,
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
        if response_format is not None:
            payload["format"] = response_format

        started = time.monotonic()
        logger.info(
            "llm_request_start",
            extra={
                "event": "llm_request_start",
                "agent_name": agent_name,
                "system_chars": len(system_prompt or ""),
                "user_chars": len(user_prompt),
                "timeout_seconds": self.timeout_seconds,
                "structured_response": response_format is not None,
            },
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
        logger.info(
            "llm_request_end",
            extra={
                "event": "llm_request_end",
                "agent_name": agent_name,
                "response_chars": len(content),
                "elapsed_seconds": round(elapsed, 3),
            },
        )
        return content


def _load_google_genai() -> tuple[Any, Any]:
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise RuntimeError(
            "google-genai is required for Gemini provider. Install project dependencies first."
        ) from exc
    return genai, types


def _read_response_text(response: Any) -> str:
    try:
        text = getattr(response, "text", None)
    except Exception:  # noqa: BLE001 - SDK response properties can raise on malformed payloads.
        text = None
    if isinstance(text, str) and text.strip():
        return text.strip()

    candidates = getattr(response, "candidates", None)
    if candidates is None and isinstance(response, dict):
        candidates = response.get("candidates")
    if not candidates:
        return ""

    parts_text: list[str] = []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        if content is None and isinstance(candidate, dict):
            content = candidate.get("content")
        parts = getattr(content, "parts", None)
        if parts is None and isinstance(content, dict):
            parts = content.get("parts")
        if not parts:
            continue
        for part in parts:
            part_text = getattr(part, "text", None)
            if part_text is None and isinstance(part, dict):
                part_text = part.get("text")
            if isinstance(part_text, str) and part_text:
                parts_text.append(part_text)
    return "\n".join(parts_text).strip()


@dataclass
class GeminiClient:
    model: str
    api_key_env: str = DEFAULT_GEMINI_API_KEY_ENV
    api_key: str = ""
    timeout_seconds: int = 120

    def _available_api_key(self) -> str:
        configured_key = self.api_key.strip()
        if configured_key:
            return configured_key

        for env_name in (
            self.api_key_env.strip(),
            DEFAULT_GEMINI_API_KEY_ENV,
            "GOOGLE_API_KEY",
        ):
            if not env_name:
                continue
            env_value = os.environ.get(env_name, "").strip()
            if env_value:
                return env_value
        return ""

    def _ensure_api_key_available(self) -> None:
        if self._available_api_key():
            return
        raise RuntimeError(
            "Gemini API key is missing. Set the configured environment variable, "
            "GEMINI_API_KEY, or GOOGLE_API_KEY before using provider 'gemini'."
        )

    def _create_client(self) -> Any:
        genai, _ = _load_google_genai()
        configured_key = self.api_key.strip()
        if configured_key:
            return genai.Client(api_key=configured_key)

        # Gemini 3 models commonly perform best with temperature around 1.0, but
        # project-level temperature remains the source of truth for compatibility.
        env_key = os.environ.get(self.api_key_env.strip(), "").strip()
        if env_key and self.api_key_env.strip() not in {
            DEFAULT_GEMINI_API_KEY_ENV,
            "GOOGLE_API_KEY",
        }:
            return genai.Client(api_key=env_key)
        return genai.Client()

    def _generation_config(
        self,
        *,
        system_prompt: Optional[str],
        temperature: float,
        top_p: float,
        response_format: Optional[Dict[str, Any]],
    ) -> Any:
        _, genai_types = _load_google_genai()
        config_kwargs: Dict[str, Any] = {
            "system_instruction": system_prompt,
            "temperature": temperature,
            "top_p": top_p,
        }
        if response_format is not None:
            config_kwargs["response_mime_type"] = "application/json"
            config_kwargs["response_json_schema"] = response_format
        try:
            return genai_types.GenerateContentConfig(**config_kwargs)
        except TypeError:
            return config_kwargs

    def generate(
        self,
        *,
        agent_name: str = "unknown",
        system_prompt: Optional[str],
        user_prompt: str,
        temperature: float = 0.4,
        top_p: float = 0.9,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> str:
        if len(user_prompt) > MAX_PROMPT_CHARS:
            user_prompt = user_prompt[-MAX_PROMPT_CHARS:]

        self._ensure_api_key_available()
        client = self._create_client()
        config = self._generation_config(
            system_prompt=system_prompt,
            temperature=temperature,
            top_p=top_p,
            response_format=response_format,
        )

        started = time.monotonic()
        logger.info(
            "llm_request_start",
            extra={
                "event": "llm_request_start",
                "provider": MODEL_PROVIDER_GEMINI,
                "agent_name": agent_name,
                "system_chars": len(system_prompt or ""),
                "user_chars": len(user_prompt),
                "timeout_seconds": self.timeout_seconds,
                "structured_response": response_format is not None,
            },
        )
        try:
            response = client.models.generate_content(
                model=self.model,
                contents=user_prompt,
                config=config,
            )
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                "Failed to call Gemini API. Check API key, model name, and network access."
            ) from exc

        content = _read_response_text(response)
        elapsed = time.monotonic() - started
        logger.info(
            "llm_request_end",
            extra={
                "event": "llm_request_end",
                "provider": MODEL_PROVIDER_GEMINI,
                "agent_name": agent_name,
                "response_chars": len(content),
                "elapsed_seconds": round(elapsed, 3),
            },
        )
        return content


def create_llm_client(
    *,
    provider: str,
    model_name: str,
    ollama_base_url: str,
    timeout_seconds: int,
    gemini_config: GeminiConfig,
    explicit_gemini_api_key: str = "",
) -> LLMClientProtocol:
    provider = provider.strip().lower()
    if provider == MODEL_PROVIDER_OLLAMA:
        return OllamaClient(
            base_url=ollama_base_url,
            model=model_name,
            timeout_seconds=timeout_seconds,
        )
    if provider == MODEL_PROVIDER_GEMINI:
        return GeminiClient(
            model=model_name,
            api_key_env=gemini_config.api_key_env,
            api_key=explicit_gemini_api_key or gemini_config.api_key,
            timeout_seconds=timeout_seconds,
        )
    raise ValueError(f"Unsupported model provider: {provider}")
