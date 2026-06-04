"""Provider-neutral LLM clients for Ollama and Gemini."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Protocol

import requests

from .cloud_free import (
    CloudFreeConfig,
    CloudFreeDailyQuotaExhausted,
    CloudFreeScheduler,
    apply_cloud_prompt_budget,
    classify_gemini_error,
)
from .config import (
    DEFAULT_GEMINI_API_KEY_ENV,
    DEFAULT_GEMINI_MAX_PROMPT_CHARS,
    DEFAULT_OLLAMA_MAX_PROMPT_CHARS,
    MODEL_PROVIDER_GEMINI,
    MODEL_PROVIDER_OLLAMA,
    GeminiConfig,
)

logger = logging.getLogger(__name__)


def _redact_provider_message(text: str) -> str:
    redacted = str(text or "")
    redacted = re.sub(r"AIza[0-9A-Za-z_\-]{20,}", "[redacted-api-key]", redacted)
    redacted = re.sub(
        r"(?i)(api[_ -]?key|key|token)=['\"]?[^'\"\s,;]+",
        r"\1=[redacted]",
        redacted,
    )
    redacted = re.sub(r"\s+", " ", redacted).strip()
    return redacted[:1000]


def _write_provider_event(path: Path | None, payload: Dict[str, Any]) -> None:
    if path is None:
        return
    event = {"time": datetime.now().isoformat(), **payload}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")


class LLMClientProtocol(Protocol):
    timeout_seconds: int
    max_prompt_chars: int

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
    max_prompt_chars: int = DEFAULT_OLLAMA_MAX_PROMPT_CHARS
    provider_event_path: Path | None = None
    run_id: str = ""
    current_round: int | None = None
    current_stage: str = ""

    def set_provider_context(
        self,
        *,
        provider_event_path: Path,
        run_id: str,
        round_index: int,
        stage: str,
    ) -> None:
        self.provider_event_path = provider_event_path
        self.run_id = run_id
        self.current_round = round_index
        self.current_stage = stage

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
        system_chars = len(system_prompt or "")
        original_user_chars = len(user_prompt)
        prompt_chars = system_chars + original_user_chars
        if self.max_prompt_chars > 0 and prompt_chars > self.max_prompt_chars:
            logger.warning(
                "llm_prompt_too_large",
                extra={
                    "event": "llm_prompt_too_large",
                    "provider": MODEL_PROVIDER_OLLAMA,
                    "model": self.model,
                    "stage": agent_name,
                    "agent_name": agent_name,
                    "prompt_chars": prompt_chars,
                    "system_chars": system_chars,
                    "user_chars": original_user_chars,
                    "max_prompt_chars": self.max_prompt_chars,
                    "timeout_seconds": self.timeout_seconds,
                },
            )
            raise RuntimeError(
                f"Ollama prompt too large for stage '{agent_name}': "
                f"prompt_chars={prompt_chars}, max_prompt_chars={self.max_prompt_chars}. "
                "Shorten task.md/memory.md or raise model.max_prompt_chars only if the "
                "selected local model and server can handle the context."
            )

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
        _write_provider_event(
            self.provider_event_path,
            {
                "event": "request_start",
                "provider": MODEL_PROVIDER_OLLAMA,
                "model": self.model,
                "stage": agent_name,
                "round": self.current_round,
                "run_id": self.run_id,
                "error_type": "",
                "prompt_chars": prompt_chars,
                "structured_response": response_format is not None,
            },
        )
        logger.info(
            "llm_request_start",
            extra={
                "event": "llm_request_start",
                "provider": MODEL_PROVIDER_OLLAMA,
                "model": self.model,
                "stage": agent_name,
                "agent_name": agent_name,
                "prompt_chars": prompt_chars,
                "system_chars": system_chars,
                "user_chars": len(user_prompt),
                "original_user_chars": original_user_chars,
                "max_prompt_chars": self.max_prompt_chars,
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
            _write_provider_event(
                self.provider_event_path,
                {
                    "event": "request_error",
                    "provider": MODEL_PROVIDER_OLLAMA,
                    "model": self.model,
                    "stage": agent_name,
                    "round": self.current_round,
                    "run_id": self.run_id,
                    "error_type": "timeout",
                    "message": _redact_provider_message(str(exc)),
                },
            )
            raise RuntimeError(
                "Ollama request timed out. "
                f"Increase timeout_seconds or check model/server health at {self.base_url}."
            ) from exc
        except requests.RequestException as exc:
            _write_provider_event(
                self.provider_event_path,
                {
                    "event": "request_error",
                    "provider": MODEL_PROVIDER_OLLAMA,
                    "model": self.model,
                    "stage": agent_name,
                    "round": self.current_round,
                    "run_id": self.run_id,
                    "error_type": "request_error",
                    "message": _redact_provider_message(str(exc)),
                },
            )
            raise RuntimeError(
                "Failed to call Ollama API. Ensure Ollama is running at "
                f"{self.base_url} and model '{self.model}' is available."
            ) from exc

        elapsed = time.monotonic() - started
        content = data.get("message", {}).get("content", "").strip()
        _write_provider_event(
            self.provider_event_path,
            {
                "event": "request_end",
                "provider": MODEL_PROVIDER_OLLAMA,
                "model": self.model,
                "stage": agent_name,
                "round": self.current_round,
                "run_id": self.run_id,
                "error_type": "",
                "response_chars": len(content),
                "elapsed_seconds": round(elapsed, 3),
            },
        )
        logger.info(
            "llm_request_end",
            extra={
                "event": "llm_request_end",
                "provider": MODEL_PROVIDER_OLLAMA,
                "model": self.model,
                "stage": agent_name,
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
    max_prompt_chars: int = DEFAULT_GEMINI_MAX_PROMPT_CHARS
    cloud_free_config: CloudFreeConfig | None = None
    provider_event_path: Path | None = None
    run_id: str = ""
    current_round: int | None = None
    current_stage: str = ""
    _scheduler: CloudFreeScheduler | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        if self.cloud_free_config and self.cloud_free_config.cloud_free_mode:
            self._scheduler = CloudFreeScheduler(
                model_id=self.model,
                config=self.cloud_free_config,
            )

    def set_provider_context(
        self,
        *,
        provider_event_path: Path,
        run_id: str,
        round_index: int,
        stage: str,
    ) -> None:
        self.provider_event_path = provider_event_path
        self.run_id = run_id
        self.current_round = round_index
        self.current_stage = stage

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
        system_chars = len(system_prompt or "")
        original_user_chars = len(user_prompt)
        prompt_chars = system_chars + original_user_chars
        if self.cloud_free_config and self.cloud_free_config.cloud_free_mode:
            user_prompt = apply_cloud_prompt_budget(
                user_prompt,
                self.cloud_free_config.prompt_budget_chars,
            )
        elif self.max_prompt_chars > 0 and prompt_chars > self.max_prompt_chars:
            logger.warning(
                "llm_prompt_too_large",
                extra={
                    "event": "llm_prompt_too_large",
                    "provider": MODEL_PROVIDER_GEMINI,
                    "model": self.model,
                    "stage": agent_name,
                    "agent_name": agent_name,
                    "prompt_chars": prompt_chars,
                    "system_chars": system_chars,
                    "user_chars": original_user_chars,
                    "max_prompt_chars": self.max_prompt_chars,
                    "timeout_seconds": self.timeout_seconds,
                },
            )
            raise RuntimeError(
                f"Gemini prompt too large for stage '{agent_name}': "
                f"prompt_chars={prompt_chars}, max_prompt_chars={self.max_prompt_chars}. "
                "Shorten task.md/memory.md or raise model.max_prompt_chars if the selected "
                "cloud model supports the context."
            )
        final_prompt_chars = system_chars + len(user_prompt)

        self._ensure_api_key_available()
        client = self._create_client()
        config = self._generation_config(
            system_prompt=system_prompt,
            temperature=temperature,
            top_p=top_p,
            response_format=response_format,
        )

        started = time.monotonic()
        _write_provider_event(
            self.provider_event_path,
            {
                "event": "request_start",
                "provider": MODEL_PROVIDER_GEMINI,
                "model": self.model,
                "stage": agent_name,
                "round": self.current_round,
                "run_id": self.run_id,
                "error_type": "",
                "prompt_chars": final_prompt_chars,
                "original_prompt_chars": prompt_chars,
                "structured_response": response_format is not None,
            },
        )
        logger.info(
            "llm_request_start",
            extra={
                "event": "llm_request_start",
                "provider": MODEL_PROVIDER_GEMINI,
                "model": self.model,
                "stage": agent_name,
                "agent_name": agent_name,
                "prompt_chars": final_prompt_chars,
                "original_prompt_chars": prompt_chars,
                "system_chars": system_chars,
                "user_chars": len(user_prompt),
                "original_user_chars": original_user_chars,
                "max_prompt_chars": self.max_prompt_chars,
                "timeout_seconds": self.timeout_seconds,
                "structured_response": response_format is not None,
            },
        )
        try:

            def operation() -> Any:
                return client.models.generate_content(
                    model=self.model,
                    contents=user_prompt,
                    config=config,
                )

            response = self._scheduler.call(operation) if self._scheduler else operation()
        except CloudFreeDailyQuotaExhausted as exc:
            _write_provider_event(
                self.provider_event_path,
                {
                    "event": "request_error",
                    "provider": MODEL_PROVIDER_GEMINI,
                    "model": self.model,
                    "stage": agent_name,
                    "round": self.current_round,
                    "run_id": self.run_id,
                    "error_type": "daily_quota_exhausted",
                    "message": _redact_provider_message(str(exc)),
                },
            )
            raise
        except RuntimeError as exc:
            info = classify_gemini_error(exc)
            error_type = info.error_type
            _write_provider_event(
                self.provider_event_path,
                {
                    "event": "request_error",
                    "provider": MODEL_PROVIDER_GEMINI,
                    "model": self.model,
                    "stage": agent_name,
                    "round": self.current_round,
                    "run_id": self.run_id,
                    "error_type": error_type,
                    "retryable": info.retryable,
                    "rate_limited": info.rate_limited,
                    "daily_quota_exhausted": info.daily_quota_exhausted,
                    "retry_after_seconds": info.retry_after_seconds,
                    "message": _redact_provider_message(str(exc)),
                },
            )
            if info.rate_limited or info.daily_quota_exhausted:
                raise RuntimeError(
                    "PROVIDER_QUOTA_EXHAUSTED: Gemini provider quota or rate limit reached. "
                    f"{info.public_message}"
                ) from exc
            if self._scheduler is not None:
                raise
            raise RuntimeError(
                "Failed to call Gemini API. Check API key, model name, and network access."
            ) from exc
        except Exception as exc:  # noqa: BLE001
            info = classify_gemini_error(exc)
            _write_provider_event(
                self.provider_event_path,
                {
                    "event": "request_error",
                    "provider": MODEL_PROVIDER_GEMINI,
                    "model": self.model,
                    "stage": agent_name,
                    "round": self.current_round,
                    "run_id": self.run_id,
                    "error_type": info.error_type,
                    "retryable": info.retryable,
                    "rate_limited": info.rate_limited,
                    "daily_quota_exhausted": info.daily_quota_exhausted,
                    "retry_after_seconds": info.retry_after_seconds,
                    "message": _redact_provider_message(str(exc)),
                },
            )
            if info.rate_limited or info.daily_quota_exhausted:
                raise RuntimeError(
                    "PROVIDER_QUOTA_EXHAUSTED: Gemini provider quota or rate limit reached. "
                    f"{info.public_message}"
                ) from exc
            raise RuntimeError(
                "Failed to call Gemini API. Check API key, model name, and network access."
            ) from exc

        content = _read_response_text(response)
        elapsed = time.monotonic() - started
        _write_provider_event(
            self.provider_event_path,
            {
                "event": "request_end",
                "provider": MODEL_PROVIDER_GEMINI,
                "model": self.model,
                "stage": agent_name,
                "round": self.current_round,
                "run_id": self.run_id,
                "error_type": "",
                "response_chars": len(content),
                "elapsed_seconds": round(elapsed, 3),
            },
        )
        logger.info(
            "llm_request_end",
            extra={
                "event": "llm_request_end",
                "provider": MODEL_PROVIDER_GEMINI,
                "model": self.model,
                "stage": agent_name,
                "agent_name": agent_name,
                "response_chars": len(content),
                "elapsed_seconds": round(elapsed, 3),
            },
        )
        return content

    def cloud_free_status(self) -> dict[str, Any]:
        if self._scheduler is None:
            return {}
        return self._scheduler.status()


def create_llm_client(
    *,
    provider: str,
    model_name: str,
    ollama_base_url: str,
    timeout_seconds: int,
    gemini_config: GeminiConfig,
    max_prompt_chars: int | None = None,
    explicit_gemini_api_key: str = "",
    cloud_free_config: CloudFreeConfig | None = None,
) -> LLMClientProtocol:
    provider = provider.strip().lower()
    if provider == MODEL_PROVIDER_OLLAMA:
        return OllamaClient(
            base_url=ollama_base_url,
            model=model_name,
            timeout_seconds=timeout_seconds,
            max_prompt_chars=max_prompt_chars or DEFAULT_OLLAMA_MAX_PROMPT_CHARS,
        )
    if provider == MODEL_PROVIDER_GEMINI:
        return GeminiClient(
            model=model_name,
            api_key_env=gemini_config.api_key_env,
            api_key=explicit_gemini_api_key or gemini_config.api_key,
            timeout_seconds=timeout_seconds,
            max_prompt_chars=max_prompt_chars or DEFAULT_GEMINI_MAX_PROMPT_CHARS,
            cloud_free_config=cloud_free_config,
        )
    raise ValueError(f"Unsupported model provider: {provider}")
