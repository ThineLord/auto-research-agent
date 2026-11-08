"""Benchmark-safe iteration presets and request budget estimates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .config import MODEL_PROVIDER_GEMINI

BENCHMARK_PRESETS: Mapping[str, int] = {
    "free_smoke": 4,
    "free_eval": 5,
    "paid_benchmark": 25,
    "stress_test": 50,
}
DEFAULT_ROUND_LLM_CALLS = 4
CONSERVATIVE_GEMINI_FREE_TIER_CALLS = 20


@dataclass(frozen=True)
class RequestBudgetEstimate:
    provider: str
    mode: str
    planned_rounds: int
    calls_per_round: int
    estimated_total_calls: int
    conservative_low_quota_calls: int | None = None
    exceeds_conservative_low_quota: bool = False
    warning: str = ""


def benchmark_preset_rounds(preset: str | None) -> int | None:
    if preset is None:
        return None
    return BENCHMARK_PRESETS[preset]


def estimate_request_budget(
    *,
    provider: str,
    mode: str,
    planned_rounds: int,
    calls_per_round: int = DEFAULT_ROUND_LLM_CALLS,
) -> RequestBudgetEstimate:
    estimated_total = max(0, planned_rounds) * max(0, calls_per_round)
    provider = provider.strip().lower()
    warning = ""
    conservative_limit = None
    exceeds_limit = False
    if provider == MODEL_PROVIDER_GEMINI:
        conservative_limit = CONSERVATIVE_GEMINI_FREE_TIER_CALLS
        exceeds_limit = estimated_total > conservative_limit
        if exceeds_limit:
            warning = (
                "Estimated Gemini calls exceed a conservative low free-tier quota. "
                "Use free_smoke/free_eval for free-tier checks, or paid_benchmark only "
                "with paid or higher-quota access."
            )
    return RequestBudgetEstimate(
        provider=provider,
        mode=mode,
        planned_rounds=planned_rounds,
        calls_per_round=calls_per_round,
        estimated_total_calls=estimated_total,
        conservative_low_quota_calls=conservative_limit,
        exceeds_conservative_low_quota=exceeds_limit,
        warning=warning,
    )


def format_request_budget_estimate(estimate: RequestBudgetEstimate) -> list[str]:
    lines = [
        "request_budget "
        f"mode={estimate.mode} rounds={estimate.planned_rounds} "
        f"calls_per_round={estimate.calls_per_round} "
        f"estimated_total_calls={estimate.estimated_total_calls}",
    ]
    if estimate.conservative_low_quota_calls is not None:
        lines.append(
            "request_budget_quota_check "
            f"conservative_low_quota_calls={estimate.conservative_low_quota_calls} "
            f"exceeds={estimate.exceeds_conservative_low_quota}"
        )
    if estimate.warning:
        lines.append(f"request_budget_warning {estimate.warning}")
    return lines
