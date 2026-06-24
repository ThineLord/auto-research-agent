"""Structured run metrics and conservative token estimates."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from difflib import SequenceMatcher
from typing import Any

AGENT_STAGES: tuple[str, ...] = ("draft", "review", "revise", "judge")
TOKEN_ESTIMATE_METHOD = "visible_context_chars_div_4_ceil"
TOKEN_ESTIMATE_CHARS_PER_TOKEN = 4
LOW_SIMILARITY_CHANGE_THRESHOLD = 0.95


def estimate_tokens_from_chars(char_count: int) -> int:
    """Return a conservative integer token estimate from character count."""
    safe_count = max(0, int(char_count))
    if safe_count == 0:
        return 0
    return (safe_count + TOKEN_ESTIMATE_CHARS_PER_TOKEN - 1) // TOKEN_ESTIMATE_CHARS_PER_TOKEN


def _text_char_count(parts: Sequence[Any] | str | None) -> int:
    if parts is None:
        return 0
    if isinstance(parts, str):
        return len(parts)
    return sum(len(str(part)) for part in parts if part is not None)


def _as_float(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return 0.0


def _as_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return 0


def _average(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 3)


def _normalize_similarity_text(text: str) -> str:
    return " ".join(str(text or "").lower().split())


def _similarity_ratio(left: str, right: str) -> float | None:
    left_norm = _normalize_similarity_text(left)
    right_norm = _normalize_similarity_text(right)
    if not left_norm or not right_norm:
        return None
    return round(SequenceMatcher(None, left_norm, right_norm).ratio(), 3)


def _changed_line_count(before: str, after: str) -> int | None:
    if not before.strip() and not after.strip():
        return None
    before_lines = before.splitlines()
    after_lines = after.splitlines()
    matcher = SequenceMatcher(None, before_lines, after_lines)
    changed = 0
    for tag, before_start, before_end, after_start, after_end in matcher.get_opcodes():
        if tag == "equal":
            continue
        changed += (before_end - before_start) + (after_end - after_start)
    return changed


def build_round_evolution_metrics(
    *,
    current_draft: str,
    current_revised: str,
    current_judge: str,
    previous_draft: str = "",
    previous_revised: str = "",
    previous_judge: str = "",
    current_score: float | None = None,
    previous_score: float | None = None,
) -> dict[str, Any]:
    """Measure text evolution without changing prompts, scoring, or control flow."""
    draft_chars = len(current_draft)
    revised_chars = len(current_revised)
    judge_chars = len(current_judge)
    previous_revised_chars = len(previous_revised)
    score_delta = None
    if current_score is not None and previous_score is not None:
        score_delta = round(current_score - previous_score, 2)
    revised_delta_chars = None
    if previous_revised.strip():
        revised_delta_chars = revised_chars - previous_revised_chars

    draft_to_revised_similarity = _similarity_ratio(current_draft, current_revised)
    revised_similarity_to_previous = _similarity_ratio(previous_revised, current_revised)
    draft_similarity_to_previous = _similarity_ratio(previous_draft, current_draft)
    judge_similarity_to_previous = _similarity_ratio(previous_judge, current_judge)

    return {
        "metric_version": 1,
        "has_previous_round": bool(
            previous_draft.strip() or previous_revised.strip() or previous_judge.strip()
        ),
        "draft_chars": draft_chars,
        "revised_chars": revised_chars,
        "judge_chars": judge_chars,
        "previous_revised_chars": previous_revised_chars if previous_revised.strip() else None,
        "revised_delta_chars": revised_delta_chars,
        "draft_to_revised_similarity": draft_to_revised_similarity,
        "draft_similarity_to_previous": draft_similarity_to_previous,
        "revised_similarity_to_previous": revised_similarity_to_previous,
        "judge_similarity_to_previous": judge_similarity_to_previous,
        "draft_to_revised_changed_lines": _changed_line_count(current_draft, current_revised),
        "revised_changed_lines_vs_previous": _changed_line_count(previous_revised, current_revised)
        if previous_revised.strip()
        else None,
        "score_delta_vs_previous": score_delta,
    }


def build_agent_io_metrics(
    *,
    agent_inputs: Mapping[str, Sequence[Any] | str],
    agent_outputs: Mapping[str, str],
    agent_timings_seconds: Mapping[str, float],
    agent_errors: Mapping[str, str | None],
) -> dict[str, dict[str, Any]]:
    """Build provider-usage estimates for each stage without changing agent execution."""
    metrics: dict[str, dict[str, Any]] = {}
    for agent in AGENT_STAGES:
        elapsed_seconds = _as_float(agent_timings_seconds.get(agent, 0.0))
        called = elapsed_seconds > 0.0
        had_error = bool(agent_errors.get(agent))
        input_chars = _text_char_count(agent_inputs.get(agent)) if called else 0
        output_chars = len(agent_outputs.get(agent, "")) if called and not had_error else 0
        estimated_input_tokens = estimate_tokens_from_chars(input_chars)
        estimated_output_tokens = estimate_tokens_from_chars(output_chars)
        metrics[agent] = {
            "called": called,
            "had_error": had_error,
            "elapsed_seconds": round(elapsed_seconds, 3),
            "estimated_input_chars": input_chars,
            "output_chars": output_chars,
            "estimated_input_tokens": estimated_input_tokens,
            "estimated_output_tokens": estimated_output_tokens,
            "estimated_total_tokens": estimated_input_tokens + estimated_output_tokens,
            "token_estimate_method": TOKEN_ESTIMATE_METHOD,
        }
    return metrics


def summarize_agent_io_metrics(agent_io_metrics: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    totals = {
        "total_agent_elapsed_seconds": 0.0,
        "total_estimated_input_chars": 0,
        "total_output_chars": 0,
        "total_estimated_input_tokens": 0,
        "total_estimated_output_tokens": 0,
        "total_estimated_tokens": 0,
        "agent_metric_totals": {},
        "token_estimate_method": TOKEN_ESTIMATE_METHOD,
    }
    agent_metric_totals: dict[str, dict[str, Any]] = {}
    for agent in AGENT_STAGES:
        metric = agent_io_metrics.get(agent, {})
        agent_total = {
            "called_count": 1 if metric.get("called") else 0,
            "error_count": 1 if metric.get("had_error") else 0,
            "elapsed_seconds": round(_as_float(metric.get("elapsed_seconds")), 3),
            "estimated_input_chars": _as_int(metric.get("estimated_input_chars")),
            "output_chars": _as_int(metric.get("output_chars")),
            "estimated_input_tokens": _as_int(metric.get("estimated_input_tokens")),
            "estimated_output_tokens": _as_int(metric.get("estimated_output_tokens")),
            "estimated_total_tokens": _as_int(metric.get("estimated_total_tokens")),
        }
        agent_metric_totals[agent] = agent_total
        totals["total_agent_elapsed_seconds"] += agent_total["elapsed_seconds"]
        totals["total_estimated_input_chars"] += agent_total["estimated_input_chars"]
        totals["total_output_chars"] += agent_total["output_chars"]
        totals["total_estimated_input_tokens"] += agent_total["estimated_input_tokens"]
        totals["total_estimated_output_tokens"] += agent_total["estimated_output_tokens"]
        totals["total_estimated_tokens"] += agent_total["estimated_total_tokens"]
    totals["total_agent_elapsed_seconds"] = round(totals["total_agent_elapsed_seconds"], 3)
    totals["agent_metric_totals"] = agent_metric_totals
    return totals


def summarize_round_metrics(round_metrics: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate additive metrics across rounds, tolerating legacy artifacts."""
    aggregate = {
        "total_agent_elapsed_seconds": 0.0,
        "total_estimated_input_chars": 0,
        "total_output_chars": 0,
        "total_estimated_input_tokens": 0,
        "total_estimated_output_tokens": 0,
        "total_estimated_tokens": 0,
        "timeout_count": 0,
        "error_count": 0,
        "rounds_with_token_estimates": 0,
        "rounds_with_agent_timings": 0,
        "agent_metric_totals": {
            agent: {
                "called_count": 0,
                "error_count": 0,
                "elapsed_seconds": 0.0,
                "estimated_input_chars": 0,
                "output_chars": 0,
                "estimated_input_tokens": 0,
                "estimated_output_tokens": 0,
                "estimated_total_tokens": 0,
            }
            for agent in AGENT_STAGES
        },
        "token_estimate_method": TOKEN_ESTIMATE_METHOD,
        "evolution_metric_totals": {
            "rounds_with_evolution_metrics": 0,
            "rounds_with_previous_round_similarity": 0,
            "avg_draft_to_revised_similarity": None,
            "avg_revised_similarity_to_previous": None,
            "avg_judge_similarity_to_previous": None,
            "avg_score_delta_vs_previous": None,
            "low_revision_change_rounds": [],
            "low_previous_revised_change_rounds": [],
        },
    }
    draft_to_revised_similarities: list[float] = []
    revised_previous_similarities: list[float] = []
    judge_previous_similarities: list[float] = []
    score_deltas: list[float] = []
    low_revision_change_rounds: list[Any] = []
    low_previous_revised_change_rounds: list[Any] = []
    for entry in round_metrics:
        if entry.get("timeout_this_round"):
            aggregate["timeout_count"] += 1
        if entry.get("errors"):
            aggregate["error_count"] += 1

        agent_io_metrics = entry.get("agent_io_metrics")
        if isinstance(agent_io_metrics, Mapping):
            round_totals = summarize_agent_io_metrics(agent_io_metrics)
            aggregate["rounds_with_token_estimates"] += 1
            aggregate["rounds_with_agent_timings"] += 1
        else:
            timings = entry.get("agent_timings_seconds")
            timings = timings if isinstance(timings, Mapping) else {}
            if timings:
                aggregate["rounds_with_agent_timings"] += 1
            round_totals = {
                "total_agent_elapsed_seconds": sum(_as_float(value) for value in timings.values()),
                "total_estimated_input_chars": _as_int(entry.get("estimated_input_chars")),
                "total_output_chars": _as_int(entry.get("output_chars")),
                "total_estimated_input_tokens": _as_int(entry.get("estimated_input_tokens")),
                "total_estimated_output_tokens": _as_int(entry.get("estimated_output_tokens")),
                "total_estimated_tokens": _as_int(entry.get("estimated_total_tokens")),
                "agent_metric_totals": {},
            }
            if round_totals["total_estimated_tokens"] > 0:
                aggregate["rounds_with_token_estimates"] += 1

        aggregate["total_agent_elapsed_seconds"] += _as_float(
            round_totals.get("total_agent_elapsed_seconds")
        )
        aggregate["total_estimated_input_chars"] += _as_int(
            round_totals.get("total_estimated_input_chars")
        )
        aggregate["total_output_chars"] += _as_int(round_totals.get("total_output_chars"))
        aggregate["total_estimated_input_tokens"] += _as_int(
            round_totals.get("total_estimated_input_tokens")
        )
        aggregate["total_estimated_output_tokens"] += _as_int(
            round_totals.get("total_estimated_output_tokens")
        )
        aggregate["total_estimated_tokens"] += _as_int(round_totals.get("total_estimated_tokens"))

        agent_metric_totals = round_totals.get("agent_metric_totals")
        agent_metric_totals = (
            agent_metric_totals if isinstance(agent_metric_totals, Mapping) else {}
        )
        for agent in AGENT_STAGES:
            source = agent_metric_totals.get(agent, {})
            source = source if isinstance(source, Mapping) else {}
            target = aggregate["agent_metric_totals"][agent]
            target["called_count"] += _as_int(source.get("called_count"))
            target["error_count"] += _as_int(source.get("error_count"))
            target["elapsed_seconds"] += _as_float(source.get("elapsed_seconds"))
            target["estimated_input_chars"] += _as_int(source.get("estimated_input_chars"))
            target["output_chars"] += _as_int(source.get("output_chars"))
            target["estimated_input_tokens"] += _as_int(source.get("estimated_input_tokens"))
            target["estimated_output_tokens"] += _as_int(source.get("estimated_output_tokens"))
            target["estimated_total_tokens"] += _as_int(source.get("estimated_total_tokens"))

        evolution_metrics = entry.get("evolution_metrics")
        if isinstance(evolution_metrics, Mapping):
            aggregate["evolution_metric_totals"]["rounds_with_evolution_metrics"] += 1
            round_number = entry.get("round")
            draft_to_revised = evolution_metrics.get("draft_to_revised_similarity")
            revised_previous = evolution_metrics.get("revised_similarity_to_previous")
            judge_previous = evolution_metrics.get("judge_similarity_to_previous")
            score_delta = evolution_metrics.get("score_delta_vs_previous")
            if isinstance(draft_to_revised, (int, float)):
                draft_to_revised_similarities.append(float(draft_to_revised))
                if draft_to_revised >= LOW_SIMILARITY_CHANGE_THRESHOLD:
                    low_revision_change_rounds.append(round_number)
            if isinstance(revised_previous, (int, float)):
                revised_previous_similarities.append(float(revised_previous))
                aggregate["evolution_metric_totals"]["rounds_with_previous_round_similarity"] += 1
                if revised_previous >= LOW_SIMILARITY_CHANGE_THRESHOLD:
                    low_previous_revised_change_rounds.append(round_number)
            if isinstance(judge_previous, (int, float)):
                judge_previous_similarities.append(float(judge_previous))
            if isinstance(score_delta, (int, float)):
                score_deltas.append(float(score_delta))

    aggregate["total_agent_elapsed_seconds"] = round(aggregate["total_agent_elapsed_seconds"], 3)
    for agent_totals in aggregate["agent_metric_totals"].values():
        agent_totals["elapsed_seconds"] = round(agent_totals["elapsed_seconds"], 3)
    evolution_totals = aggregate["evolution_metric_totals"]
    evolution_totals["avg_draft_to_revised_similarity"] = _average(draft_to_revised_similarities)
    evolution_totals["avg_revised_similarity_to_previous"] = _average(revised_previous_similarities)
    evolution_totals["avg_judge_similarity_to_previous"] = _average(judge_previous_similarities)
    evolution_totals["avg_score_delta_vs_previous"] = _average(score_deltas)
    evolution_totals["low_revision_change_rounds"] = low_revision_change_rounds
    evolution_totals["low_previous_revised_change_rounds"] = low_previous_revised_change_rounds
    return aggregate
