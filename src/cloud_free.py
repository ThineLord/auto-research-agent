"""Adaptive zero-cost Gemini/Gemma model discovery, profiling, and pacing helpers."""

from __future__ import annotations

import json
import random
import re
import time
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from .judge_output import JUDGE_OUTPUT_SCHEMA
from .storage import parse_score, write_json_file

FREE_RUNNER_AUTO = "auto_long_run"
FREE_RUNNER_QUALITY = "quality_free"
FREE_RUNNER_VOLUME = "volume_free"
FREE_RUNNER_MANUAL = "manual"
FREE_RUNNER_PRESETS = (
    FREE_RUNNER_AUTO,
    FREE_RUNNER_QUALITY,
    FREE_RUNNER_VOLUME,
    FREE_RUNNER_MANUAL,
)

DEFAULT_ALLOWED_MODEL_PATTERNS = (
    r"^gemini-.*flash",
    r"^gemini-.*flash-lite",
    r"^gemma",
    r".*gemma.*",
    r".*(high[-_ ]?tpm|unlimited).*",
)
DEFAULT_BLOCKED_MODEL_PATTERNS = (
    r"pro",
    r"preview",
    r"live",
    r"tts",
    r"image",
    r"batch",
    r"flex",
    r"priority",
    r"grounding",
    r"google[-_ ]?search",
    r"\bsearch\b",
    r"map",
    r"maps",
    r"code[-_ ]?execution",
    r"file[-_ ]?search",
    r"context[-_ ]?cach",
    r"\btool",
)
DEFAULT_SEED_MODELS = (
    "gemini-3.5-flash",
    "gemini-2.5-flash-lite",
)
PROFILE_ARTIFACT_NAME = "cloud_free_profile.json"
DISCOVERY_ARTIFACT_NAME = "cloud_free_models.json"


class CloudFreeDailyQuotaExhausted(RuntimeError):
    """Raised when a free-tier daily quota pause should replace more retries."""


@dataclass(frozen=True)
class CloudFreeConfig:
    cloud_free_mode: bool = True
    free_runner_preset: str = FREE_RUNNER_AUTO
    min_delay_seconds: float | None = None
    max_delay_seconds: float = 3600.0
    max_retries: int = 5
    prompt_budget_chars: int = 24000
    prompt_budget_tokens: int | None = None
    allow_model_fallback: bool = True
    allowed_model_patterns: tuple[str, ...] = DEFAULT_ALLOWED_MODEL_PATTERNS
    blocked_model_patterns: tuple[str, ...] = DEFAULT_BLOCKED_MODEL_PATTERNS


@dataclass(frozen=True)
class CloudModelInfo:
    model_id: str
    display_name: str = ""
    supported_generation_methods: tuple[str, ...] = ()
    input_token_limit: int | None = None
    output_token_limit: int | None = None
    description: str = ""
    appears_gemini: bool = False
    appears_gemma: bool = False
    appears_flash: bool = False
    appears_flash_lite: bool = False
    appears_pro: bool = False
    appears_preview: bool = False
    appears_live: bool = False
    appears_tts: bool = False
    appears_grounding: bool = False
    appears_search: bool = False
    appears_maps: bool = False
    appears_tool: bool = False
    appears_high_tpm: bool = False
    safe_text_generation: bool = False
    blocked_reason: str = ""
    available: bool = True
    source: str = "discovered"


@dataclass(frozen=True)
class CloudModelProfile:
    model_id: str
    reachable: bool = False
    structured_output_works: bool = False
    score_parsing_works: bool = False
    latency_seconds: float | None = None
    estimated_prompt_tokens: int | None = None
    estimated_output_tokens: int | None = None
    rate_limited: bool = False
    daily_quota_exhausted: bool = False
    token_context_error: bool = False
    safety_tool_billing_error: bool = False
    error_type: str = ""
    error_message: str = ""
    diagnostic_score: float | None = None
    attempted_at: str = ""
    safe_text_generation: bool = True


@dataclass(frozen=True)
class CloudModelRecommendation:
    model_id: str
    preset: str
    reason: str
    score: float


@dataclass(frozen=True)
class GeminiErrorInfo:
    retryable: bool = False
    rate_limited: bool = False
    daily_quota_exhausted: bool = False
    token_context_error: bool = False
    safety_tool_billing_error: bool = False
    retry_after_seconds: float | None = None
    public_message: str = "Gemini request failed."
    error_type: str = "unknown"


def normalize_model_id(model_id: str) -> str:
    model_id = str(model_id or "").strip()
    if model_id.startswith("models/"):
        return model_id.removeprefix("models/")
    return model_id


def _haystack(*values: object) -> str:
    return " ".join(str(value or "") for value in values).lower()


def _matches_any(text: str, patterns: Sequence[str]) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def _first_match(text: str, patterns: Sequence[str]) -> str:
    for pattern in patterns:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return pattern
    return ""


def _as_int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        if value is None or str(value).strip() == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _get_attr_or_item(obj: Any, names: Sequence[str], default: Any = None) -> Any:
    for name in names:
        value = default
        if isinstance(obj, Mapping) and name in obj:
            value = obj.get(name)
        else:
            value = getattr(obj, name, default)
        if value is not default and value is not None:
            return value
    return default


def _tuple_of_strings(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Iterable):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return ()


def classify_model(
    *,
    model_id: str,
    display_name: str = "",
    supported_generation_methods: Sequence[str] = (),
    input_token_limit: int | None = None,
    output_token_limit: int | None = None,
    description: str = "",
    source: str = "discovered",
    available: bool = True,
    allowed_patterns: Sequence[str] = DEFAULT_ALLOWED_MODEL_PATTERNS,
    blocked_patterns: Sequence[str] = DEFAULT_BLOCKED_MODEL_PATTERNS,
) -> CloudModelInfo:
    normalized_id = normalize_model_id(model_id)
    methods = tuple(str(method).strip() for method in supported_generation_methods if method)
    text = _haystack(normalized_id, display_name, description)
    methods_text = _haystack(*methods)
    blocked_pattern = _first_match(text, blocked_patterns)
    supports_generation = not methods or "generatecontent" in methods_text.replace("_", "")
    allowed = _matches_any(text, allowed_patterns)
    blocked_reason = ""
    if blocked_pattern:
        blocked_reason = f"blocked_pattern:{blocked_pattern}"
    elif not supports_generation:
        blocked_reason = "unsupported_generation_method"
    elif not allowed:
        blocked_reason = "not_in_safe_candidate_pool"

    return CloudModelInfo(
        model_id=normalized_id,
        display_name=display_name,
        supported_generation_methods=methods,
        input_token_limit=input_token_limit,
        output_token_limit=output_token_limit,
        description=description,
        appears_gemini="gemini" in text,
        appears_gemma="gemma" in text,
        appears_flash="flash" in text,
        appears_flash_lite="flash-lite" in text or "flash lite" in text,
        appears_pro="pro" in text,
        appears_preview="preview" in text,
        appears_live="live" in text,
        appears_tts="tts" in text,
        appears_grounding="grounding" in text,
        appears_search="search" in text,
        appears_maps="map" in text,
        appears_tool="tool" in text,
        appears_high_tpm=bool(re.search(r"high[-_ ]?tpm|unlimited", text, flags=re.I)),
        safe_text_generation=not blocked_reason,
        blocked_reason=blocked_reason,
        available=available,
        source=source,
    )


def model_info_from_sdk_model(
    model: Any,
    *,
    allowed_patterns: Sequence[str] = DEFAULT_ALLOWED_MODEL_PATTERNS,
    blocked_patterns: Sequence[str] = DEFAULT_BLOCKED_MODEL_PATTERNS,
) -> CloudModelInfo:
    model_id = _get_attr_or_item(model, ("name", "id", "model", "model_id"), "")
    display_name = _get_attr_or_item(model, ("display_name", "displayName", "title"), "")
    description = _get_attr_or_item(model, ("description",), "")
    methods = _tuple_of_strings(
        _get_attr_or_item(
            model,
            ("supported_generation_methods", "supportedGenerationMethods", "methods"),
            (),
        )
    )
    input_limit = _as_int_or_none(
        _get_attr_or_item(
            model,
            ("input_token_limit", "inputTokenLimit", "input_tokens", "context_window"),
            None,
        )
    )
    output_limit = _as_int_or_none(
        _get_attr_or_item(
            model,
            ("output_token_limit", "outputTokenLimit", "output_tokens"),
            None,
        )
    )
    return classify_model(
        model_id=str(model_id),
        display_name=str(display_name or ""),
        supported_generation_methods=methods,
        input_token_limit=input_limit,
        output_token_limit=output_limit,
        description=str(description or ""),
        allowed_patterns=allowed_patterns,
        blocked_patterns=blocked_patterns,
    )


def filter_safe_text_models(
    models: Sequence[CloudModelInfo],
    *,
    include_unavailable: bool = False,
) -> list[CloudModelInfo]:
    return [
        model
        for model in models
        if model.safe_text_generation and (include_unavailable or model.available)
    ]


def build_candidate_pool(
    *,
    discovered_models: Sequence[CloudModelInfo] = (),
    configured_models: Sequence[str] = (),
    config: CloudFreeConfig | None = None,
) -> list[CloudModelInfo]:
    config = config or CloudFreeConfig()
    by_id: dict[str, CloudModelInfo] = {}
    for model in discovered_models:
        by_id[model.model_id] = model

    for model_id in (*DEFAULT_SEED_MODELS, *configured_models):
        normalized = normalize_model_id(model_id)
        if not normalized or normalized in by_id:
            continue
        by_id[normalized] = classify_model(
            model_id=normalized,
            source="configured",
            available=False,
            allowed_patterns=config.allowed_model_patterns,
            blocked_patterns=config.blocked_model_patterns,
        )

    candidates = [
        model
        for model in by_id.values()
        if model.safe_text_generation
        and (
            model.model_id in DEFAULT_SEED_MODELS
            or model.appears_gemma
            or model.appears_high_tpm
            or model.appears_flash
        )
    ]
    return sorted(candidates, key=lambda item: item.model_id.casefold())


def _safe_error_message(exc: BaseException) -> str:
    text = str(exc) or exc.__class__.__name__
    text = re.sub(r"AIza[0-9A-Za-z_\-]{20,}", "[redacted-api-key]", text)
    text = re.sub(r"(?i)(api[_ -]?key|key|token)=['\"]?[^'\"\s,;]+", r"\1=[redacted]", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:240]


def _redact_known_secrets(text: str, secrets: Sequence[str]) -> str:
    redacted = text
    for secret in secrets:
        secret = str(secret or "").strip()
        if len(secret) >= 4:
            redacted = redacted.replace(secret, "[redacted-api-key]")
    return redacted


def _status_code_from_exception(exc: BaseException) -> int | None:
    for attr in ("status_code", "status", "code"):
        value = getattr(exc, attr, None)
        status = _as_int_or_none(value)
        if status is not None:
            return status
    response = getattr(exc, "response", None)
    if response is not None:
        return _as_int_or_none(
            getattr(response, "status_code", None) or getattr(response, "status", None)
        )
    return None


def _retry_after_from_exception(exc: BaseException) -> float | None:
    headers: Any = getattr(exc, "headers", None)
    response = getattr(exc, "response", None)
    if headers is None and response is not None:
        headers = getattr(response, "headers", None)
    if not headers:
        return None
    value = None
    if isinstance(headers, Mapping):
        value = headers.get("Retry-After") or headers.get("retry-after")
    else:
        value = getattr(headers, "get", lambda _: None)("Retry-After")
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return None


def classify_gemini_error(exc: BaseException) -> GeminiErrorInfo:
    status = _status_code_from_exception(exc)
    message = _safe_error_message(exc)
    text = message.lower()
    rate_limited = (
        status == 429
        or "429" in text
        or "resource exhausted" in text
        or "rate limit" in text
        or "rate_limited" in text
        or "quota exceeded" in text
        or "free-tier" in text
    )
    daily_quota = rate_limited and bool(
        re.search(
            r"\b(rpd|daily|per day|day quota|daily quota|requests per day)\b"
            r"|generaterequestsperday",
            text,
            flags=re.I,
        )
    )
    token_context = (
        bool(re.search(r"context|token|too large|maximum|input.*limit|prompt", text, flags=re.I))
        and not rate_limited
    )
    safety_tool_billing = bool(
        re.search(
            r"billing|paid|payment|permission|safety|grounding|search|maps|tool|code execution",
            text,
            flags=re.I,
        )
    )
    retryable = rate_limited or status in {500, 502, 503, 504}
    if daily_quota:
        public = "Free-tier daily quota likely exhausted; safe to resume after reset."
        error_type = "daily_quota_exhausted"
    elif rate_limited:
        public = "Gemini free-tier rate limit reached; backing off before retry."
        error_type = "rate_limited"
    elif token_context:
        public = "Gemini prompt or context limit was reached."
        error_type = "token_context"
    elif safety_tool_billing:
        public = "Gemini request was blocked by safety, permission, billing, or tool constraints."
        error_type = "safety_tool_billing"
    else:
        public = "Gemini request failed."
        error_type = "unknown"
    return GeminiErrorInfo(
        retryable=retryable,
        rate_limited=rate_limited,
        daily_quota_exhausted=daily_quota,
        token_context_error=token_context,
        safety_tool_billing_error=safety_tool_billing,
        retry_after_seconds=_retry_after_from_exception(exc),
        public_message=public,
        error_type=error_type,
    )


def initial_delay_seconds(model_id: str, preset: str, configured_min: float | None = None) -> float:
    if configured_min is not None:
        return max(0.0, float(configured_min))
    text = model_id.lower()
    if "flash-lite" in text or "flash_lite" in text:
        return 10.0 if preset != FREE_RUNNER_QUALITY else 15.0
    if "gemma" in text or "high-tpm" in text or "unlimited" in text:
        return 6.0
    if "flash" in text:
        return 16.0 if preset != FREE_RUNNER_VOLUME else 12.0
    return 12.0


class CloudFreeScheduler:
    """Serial Gemini pacing and retry policy for free-tier long runs."""

    def __init__(
        self,
        *,
        model_id: str,
        config: CloudFreeConfig,
        sleep_func: Callable[[float], None] = time.sleep,
        monotonic_func: Callable[[], float] = time.monotonic,
        random_uniform: Callable[[float, float], float] = random.uniform,
    ) -> None:
        self.model_id = model_id
        self.config = config
        self.sleep_func = sleep_func
        self.monotonic_func = monotonic_func
        self.random_uniform = random_uniform
        self.lower_bound = initial_delay_seconds(
            model_id,
            config.free_runner_preset,
            config.min_delay_seconds,
        )
        self.current_delay_seconds = self.lower_bound
        self.last_finished_at: float | None = None
        self.calls = 0
        self.successes = 0
        self.failures = 0
        self.recent_outcomes: deque[bool] = deque(maxlen=20)
        self.recent_429_count = 0
        self.last_status = "idle"
        self.last_error_type = ""
        self.last_retry_after_seconds: float | None = None

    def _sleep_for_pacing(self) -> None:
        if self.last_finished_at is None or self.current_delay_seconds <= 0:
            return
        elapsed = self.monotonic_func() - self.last_finished_at
        remaining = self.current_delay_seconds - elapsed
        if remaining > 0:
            self.last_status = "pacing"
            self.sleep_func(remaining)

    def _jitter(self, delay: float) -> float:
        if delay <= 0:
            return 0.0
        return delay + self.random_uniform(0, max(0.5, delay * 0.2))

    def _record_success(self) -> None:
        self.calls += 1
        self.successes += 1
        self.recent_outcomes.append(True)
        self.last_finished_at = self.monotonic_func()
        self.last_status = "running"
        self.last_error_type = ""
        if len(self.recent_outcomes) >= 3 and all(list(self.recent_outcomes)[-3:]):
            self.current_delay_seconds = max(self.lower_bound, self.current_delay_seconds * 0.9)

    def _record_failure(self, info: GeminiErrorInfo) -> None:
        self.calls += 1
        self.failures += 1
        self.recent_outcomes.append(False)
        self.last_finished_at = self.monotonic_func()
        self.last_error_type = info.error_type
        self.last_retry_after_seconds = info.retry_after_seconds
        if info.rate_limited:
            self.recent_429_count += 1
            self.current_delay_seconds = min(
                self.config.max_delay_seconds,
                max(self.lower_bound, self.current_delay_seconds * 1.8),
            )

    def call(self, operation: Callable[[], Any]) -> Any:
        attempt = 0
        while True:
            self._sleep_for_pacing()
            try:
                result = operation()
            except Exception as exc:  # noqa: BLE001 - SDK error classes vary by version.
                info = classify_gemini_error(exc)
                self._record_failure(info)
                if info.daily_quota_exhausted:
                    self.last_status = "paused_until_reset"
                    raise CloudFreeDailyQuotaExhausted(info.public_message) from exc
                if not info.retryable or attempt >= self.config.max_retries:
                    self.last_status = "failed_cleanly"
                    raise RuntimeError(info.public_message) from exc
                attempt += 1
                self.last_status = "backing_off"
                retry_delay = info.retry_after_seconds
                if retry_delay is None:
                    retry_delay = min(
                        self.config.max_delay_seconds,
                        self.current_delay_seconds * (2 ** min(attempt, 6)),
                    )
                    retry_delay = self._jitter(retry_delay)
                else:
                    retry_delay = max(0.0, retry_delay)
                self.current_delay_seconds = min(
                    self.config.max_delay_seconds,
                    max(self.current_delay_seconds, retry_delay),
                )
                self.sleep_func(retry_delay)
                self.last_finished_at = None
                continue
            self._record_success()
            return result

    def status(self) -> dict[str, Any]:
        recent_total = len(self.recent_outcomes)
        recent_successes = sum(1 for item in self.recent_outcomes if item)
        success_rate = (recent_successes / recent_total) if recent_total else None
        delay = max(0.0, self.current_delay_seconds)
        calls_per_hour = 3600.0 / max(delay, 1.0)
        return {
            "status": self.last_status,
            "model": self.model_id,
            "current_delay_seconds": round(delay, 3),
            "recent_success_rate": None if success_rate is None else round(success_rate, 3),
            "recent_429_count": self.recent_429_count,
            "estimated_completed_rounds_per_hour": round(calls_per_hour / 4.0, 2),
            "calls": self.calls,
            "successes": self.successes,
            "failures": self.failures,
            "last_error_type": self.last_error_type,
            "last_retry_after_seconds": self.last_retry_after_seconds,
        }


def apply_cloud_prompt_budget(user_prompt: str, max_chars: int) -> str:
    if max_chars <= 0 or len(user_prompt) <= max_chars:
        return user_prompt
    if max_chars < 1000:
        return user_prompt[-max_chars:]

    section_pattern = re.compile(r"(?m)^# [^\n]+")
    matches = list(section_pattern.finditer(user_prompt))
    if not matches:
        return user_prompt[-max_chars:]

    sections: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(user_prompt)
        header = match.group(0).strip()
        sections.append((header, user_prompt[start:end].strip()))

    critical_names = (
        "topic context",
        "round",
        "research task",
        "previous best",
        "previous judge",
        "draft output",
        "review feedback",
        "revised output",
    )
    critical: list[str] = []
    compressible: list[str] = []
    for header, block in sections:
        normalized = header.lower().lstrip("# ").strip()
        if any(name in normalized for name in critical_names):
            critical.append(block)
        else:
            compressible.append(block)

    marker = "\n\n[...truncated for cloud free prompt budget...]\n\n"
    critical_text = "\n\n".join(critical).strip()
    remaining = max_chars - len(critical_text) - len(marker)
    if remaining > 300 and compressible:
        compressed_source = "\n\n".join(compressible)
        compressed = compressed_source[-remaining:].strip()
        result = f"{critical_text}{marker}{compressed}".strip()
    else:
        result = critical_text[-max_chars:].strip()

    if len(result) <= max_chars:
        return result
    return result[-max_chars:]


def _model_score_capacity_bonus(model: CloudModelInfo | None) -> float:
    if model is None:
        return 0.0
    bonus = 0.0
    if model.appears_high_tpm:
        bonus += 20.0
    if model.appears_gemma:
        bonus += 10.0
    if model.input_token_limit:
        bonus += min(15.0, model.input_token_limit / 10000.0)
    return bonus


def recommend_free_cloud_model(
    *,
    candidates: Sequence[CloudModelInfo],
    profiles: Sequence[CloudModelProfile] = (),
    preset: str = FREE_RUNNER_AUTO,
) -> CloudModelRecommendation | None:
    safe_candidates = [item for item in candidates if item.safe_text_generation]
    if not safe_candidates:
        return None
    by_id = {candidate.model_id: candidate for candidate in safe_candidates}
    profile_by_id = {profile.model_id: profile for profile in profiles}

    if preset == FREE_RUNNER_MANUAL:
        return None
    if preset == FREE_RUNNER_QUALITY and "gemini-3.5-flash" in by_id:
        profile = profile_by_id.get("gemini-3.5-flash")
        if profile is None or (profile.reachable and profile.structured_output_works):
            return CloudModelRecommendation(
                model_id="gemini-3.5-flash",
                preset=preset,
                reason="Quality preset prefers validated Gemini 3.5 Flash.",
                score=100.0,
            )

    scored: list[CloudModelRecommendation] = []
    for candidate in safe_candidates:
        profile = profile_by_id.get(candidate.model_id)
        if profile and (
            not profile.reachable
            or profile.safety_tool_billing_error
            or profile.daily_quota_exhausted
            or profile.token_context_error
        ):
            continue
        score = 0.0
        reasons = []
        if profile:
            if profile.reachable:
                score += 35.0
                reasons.append("health passed")
            if profile.structured_output_works:
                score += 25.0
                reasons.append("structured output passed")
            if profile.score_parsing_works:
                score += 15.0
                reasons.append("score parsing passed")
            if not profile.rate_limited:
                score += 10.0
                reasons.append("no 429 during profile")
            if profile.latency_seconds is not None:
                score += max(0.0, 10.0 - min(10.0, profile.latency_seconds))
            if profile.diagnostic_score is not None:
                score += min(15.0, max(0.0, profile.diagnostic_score / 10.0))
        else:
            score += 5.0
            reasons.append("safe candidate")
        score += _model_score_capacity_bonus(candidate)
        if preset == FREE_RUNNER_VOLUME:
            if candidate.appears_high_tpm or candidate.appears_gemma:
                score += 35.0
                reasons.append("volume-friendly candidate")
            elif "flash-lite" in candidate.model_id:
                score += 20.0
                reasons.append("Flash-Lite fallback")
        elif preset == FREE_RUNNER_AUTO and candidate.appears_high_tpm:
            score += 25.0
            reasons.append("high TPM/unlimited signal")
        scored.append(
            CloudModelRecommendation(
                model_id=candidate.model_id,
                preset=preset,
                reason=", ".join(reasons) or "safe text-only candidate",
                score=round(score, 3),
            )
        )

    if not scored:
        fallback_id = (
            "gemini-2.5-flash-lite"
            if "gemini-2.5-flash-lite" in by_id
            else safe_candidates[0].model_id
        )
        return CloudModelRecommendation(
            model_id=fallback_id,
            preset=preset,
            reason="No profiled winner; using safe fallback candidate.",
            score=1.0,
        )
    return max(scored, key=lambda item: (item.score, item.model_id))


def choose_fallback_model(
    *,
    current_model: str,
    candidates: Sequence[CloudModelInfo],
    profiles: Sequence[CloudModelProfile] = (),
    config: CloudFreeConfig | None = None,
) -> str | None:
    config = config or CloudFreeConfig()
    if not config.allow_model_fallback:
        return None
    blocked = [
        candidate
        for candidate in candidates
        if not candidate.safe_text_generation or candidate.blocked_reason
    ]
    blocked_ids = {candidate.model_id for candidate in blocked}
    available = [
        candidate
        for candidate in candidates
        if candidate.safe_text_generation and candidate.model_id != current_model
    ]
    recommendation = recommend_free_cloud_model(
        candidates=available,
        profiles=profiles,
        preset=FREE_RUNNER_VOLUME,
    )
    if recommendation and recommendation.model_id not in blocked_ids:
        return recommendation.model_id
    for fallback in ("gemini-2.5-flash-lite", "gemini-3.5-flash"):
        if fallback != current_model and fallback in {
            candidate.model_id for candidate in available
        }:
            return fallback
    return available[0].model_id if available else None


def _serialize_models(models: Sequence[CloudModelInfo]) -> list[dict[str, Any]]:
    return [asdict(model) for model in models]


def _serialize_profiles(profiles: Sequence[CloudModelProfile]) -> list[dict[str, Any]]:
    return [asdict(profile) for profile in profiles]


def save_discovery_artifact(project_dir: Path, models: Sequence[CloudModelInfo]) -> Path:
    path = project_dir / "artifacts" / DISCOVERY_ARTIFACT_NAME
    write_json_file(
        path,
        {
            "generated_at": datetime.now().isoformat(),
            "models": _serialize_models(models),
        },
    )
    return path


def save_profile_artifact(project_dir: Path, profiles: Sequence[CloudModelProfile]) -> Path:
    path = project_dir / "artifacts" / PROFILE_ARTIFACT_NAME
    write_json_file(
        path,
        {
            "generated_at": datetime.now().isoformat(),
            "profiles": _serialize_profiles(profiles),
        },
    )
    return path


def load_profile_artifact(project_dir: Path) -> list[CloudModelProfile]:
    path = project_dir / "artifacts" / PROFILE_ARTIFACT_NAME
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    profiles = payload.get("profiles", []) if isinstance(payload, Mapping) else []
    result: list[CloudModelProfile] = []
    for item in profiles:
        if isinstance(item, Mapping):
            fields = {field.name for field in CloudModelProfile.__dataclass_fields__.values()}
            result.append(CloudModelProfile(**{key: item.get(key) for key in fields}))
    return result


def load_discovery_artifact(project_dir: Path) -> list[CloudModelInfo]:
    path = project_dir / "artifacts" / DISCOVERY_ARTIFACT_NAME
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    models = payload.get("models", []) if isinstance(payload, Mapping) else []
    result: list[CloudModelInfo] = []
    for item in models:
        if isinstance(item, Mapping):
            fields = {field.name for field in CloudModelInfo.__dataclass_fields__.values()}
            result.append(CloudModelInfo(**{key: item.get(key) for key in fields}))
    return result


def _create_genai_client(*, api_key_env: str, api_key: str) -> Any:
    from .llm import GeminiClient

    return GeminiClient(model="gemini-3.5-flash", api_key_env=api_key_env, api_key=api_key)


def discover_free_cloud_models(
    *,
    api_key_env: str,
    api_key: str = "",
    config: CloudFreeConfig | None = None,
) -> tuple[list[CloudModelInfo], str]:
    config = config or CloudFreeConfig()
    try:
        client_wrapper = _create_genai_client(api_key_env=api_key_env, api_key=api_key)
        client_wrapper._ensure_api_key_available()  # noqa: SLF001 - shared internal key resolver.
        client = client_wrapper._create_client()  # noqa: SLF001 - keeps API key handling centralized.
        raw_models = client.models.list()
    except Exception as exc:  # noqa: BLE001
        return [], _redact_known_secrets(_safe_error_message(exc), (api_key,))

    discovered: list[CloudModelInfo] = []
    try:
        iterator = list(raw_models)
    except TypeError:
        iterator = list(getattr(raw_models, "models", []) or [])
    for raw_model in iterator:
        discovered.append(
            model_info_from_sdk_model(
                raw_model,
                allowed_patterns=config.allowed_model_patterns,
                blocked_patterns=config.blocked_model_patterns,
            )
        )
    return discovered, ""


def _usage_tokens_from_response_text(text: str) -> tuple[int | None, int | None]:
    if not text:
        return None, None
    estimated_output = max(1, len(text) // 4)
    return None, estimated_output


def profile_free_cloud_models(
    *,
    candidates: Sequence[CloudModelInfo],
    api_key_env: str,
    api_key: str = "",
    timeout_seconds: int = 30,
    include_diagnostic: bool = False,
) -> list[CloudModelProfile]:
    from .llm import GeminiClient

    profiles: list[CloudModelProfile] = []
    for candidate in candidates:
        started = time.monotonic()
        attempted_at = datetime.now().isoformat()
        if not candidate.safe_text_generation:
            profiles.append(
                CloudModelProfile(
                    model_id=candidate.model_id,
                    error_type="blocked_model",
                    error_message=candidate.blocked_reason,
                    attempted_at=attempted_at,
                    safe_text_generation=False,
                )
            )
            continue
        client = GeminiClient(
            model=candidate.model_id,
            api_key_env=api_key_env,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
        )
        try:
            health = client.generate(
                agent_name="free_cloud_health",
                system_prompt="Reply only with OK.",
                user_prompt="Reply with OK.",
                temperature=0.0,
                top_p=0.9,
            )
            structured = client.generate(
                agent_name="free_cloud_structured_smoke",
                system_prompt=(
                    "Return JSON only with keys: score, rubric, reasons, blockers, next_step."
                ),
                user_prompt="Score this candidate as 87. Use score 87.",
                temperature=0.0,
                top_p=0.9,
                response_format=JUDGE_OUTPUT_SCHEMA,
            )
            parsed = parse_score(structured)
            diagnostic_score = parsed
            if include_diagnostic:
                mini = client.generate(
                    agent_name="free_cloud_mini_diagnostic",
                    system_prompt="Return a one-line diagnostic judgment with SCORE: 87.",
                    user_prompt="Return SCORE: 87 and one short reason.",
                    temperature=0.0,
                    top_p=0.9,
                )
                diagnostic_score = parse_score(mini) or parsed
            latency = time.monotonic() - started
            _, output_tokens = _usage_tokens_from_response_text(health + structured)
            profiles.append(
                CloudModelProfile(
                    model_id=candidate.model_id,
                    reachable=bool(health.strip()),
                    structured_output_works=bool(structured.strip()),
                    score_parsing_works=parsed is not None,
                    latency_seconds=round(latency, 3),
                    estimated_prompt_tokens=None,
                    estimated_output_tokens=output_tokens,
                    diagnostic_score=diagnostic_score,
                    attempted_at=attempted_at,
                    safe_text_generation=True,
                )
            )
        except RuntimeError as exc:
            info = classify_gemini_error(exc)
            profiles.append(
                CloudModelProfile(
                    model_id=candidate.model_id,
                    latency_seconds=round(time.monotonic() - started, 3),
                    rate_limited=info.rate_limited,
                    daily_quota_exhausted=info.daily_quota_exhausted,
                    token_context_error=info.token_context_error,
                    safety_tool_billing_error=info.safety_tool_billing_error,
                    error_type=info.error_type,
                    error_message=info.public_message,
                    attempted_at=attempted_at,
                    safe_text_generation=True,
                )
            )
    return profiles


def next_pacific_reset_heuristic(now: datetime | None = None) -> str:
    """Return a documented display-only Pacific midnight reset heuristic."""

    now = now or datetime.now(timezone.utc)
    pacific = timezone(timedelta(hours=-8))
    pacific_now = now.astimezone(pacific)
    tomorrow = pacific_now.date() + timedelta(days=1)
    reset = datetime.combine(tomorrow, datetime.min.time(), tzinfo=pacific)
    return reset.isoformat()
