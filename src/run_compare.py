"""Helpers for comparing completed Auto Research Agent runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

from .metrics import JUDGE_RUBRIC_KEYS, summarize_round_metrics
from .run_config import read_run_config
from .storage import write_json_file


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _read_json_list(path: Path) -> list[dict[str, Any]]:
    data = _read_json(path)
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def _as_float(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _score_values(round_metrics: Sequence[dict[str, Any]]) -> list[float]:
    scores: list[float] = []
    for entry in round_metrics:
        score = _as_float(entry.get("score"))
        if score is not None:
            scores.append(score)
    return scores


def _rubric_short_name(key: str) -> str:
    return {
        "novelty_and_research_value": "novelty",
        "technical_clarity_and_correctness": "clarity",
        "feasibility_and_implementation_realism": "feasibility",
        "evaluation_design_quality": "evaluation",
        "tomorrow_actionability": "actionability",
    }.get(key, key)


def _rubric_average_fields(rubric_averages: dict[str, Any]) -> dict[str, float | None]:
    fields: dict[str, float | None] = {}
    for key in JUDGE_RUBRIC_KEYS:
        value = _as_float(rubric_averages.get(key))
        fields[f"rubric_avg_{_rubric_short_name(key)}"] = (
            round(value, 3) if value is not None else None
        )
    return fields


def _rounds_from_summary_or_metrics(
    summary: dict[str, Any],
    round_metrics: Sequence[dict[str, Any]],
    key: str,
    metric_flag: str,
) -> list[Any]:
    summary_value = summary.get(key)
    if isinstance(summary_value, list):
        return summary_value
    return [entry.get("round") for entry in round_metrics if entry.get(metric_flag)]


def _error_rounds(summary: dict[str, Any], round_metrics: Sequence[dict[str, Any]]) -> list[Any]:
    summary_value = summary.get("error_rounds")
    if isinstance(summary_value, list):
        return summary_value
    return [entry.get("round") for entry in round_metrics if entry.get("errors")]


def load_run_summary(run_root: Path) -> dict[str, Any]:
    run_root = Path(run_root)
    run_summary_path = run_root / "run_summary.json"
    run_config_path = run_root / "run_config.json"
    round_metrics_path = run_root / "round_metrics.json"
    summary = _read_json(run_summary_path)
    summary = summary if isinstance(summary, dict) else {}
    run_config = read_run_config(run_root)
    model_config = run_config.get("model")
    model_config = model_config if isinstance(model_config, dict) else {}
    runtime_config = run_config.get("runtime")
    runtime_config = runtime_config if isinstance(runtime_config, dict) else {}
    round_metrics = _read_json_list(round_metrics_path)
    scores = _score_values(round_metrics)
    summary_best_score = _as_float(summary.get("best_score"))
    config_best_score = _as_float(run_config.get("best_score"))
    best_score = summary_best_score
    if best_score is None:
        best_score = max(scores) if scores else config_best_score
    average_score = (
        round(sum(scores) / len(scores), 2) if scores else _as_float(summary.get("average_score"))
    )
    completed_rounds = _as_int(summary.get("completed_rounds"))
    if completed_rounds is None:
        completed_rounds = _as_int(run_config.get("completed_rounds"))
    if completed_rounds is None:
        completed_rounds = len(round_metrics)
    timeout_rounds = _rounds_from_summary_or_metrics(
        summary, round_metrics, "timeout_rounds", "timeout_this_round"
    )
    error_rounds = _error_rounds(summary, round_metrics)
    successful_rounds = _rounds_from_summary_or_metrics(
        summary, round_metrics, "successful_rounds", "successful_research_round"
    )
    metrics_totals = summarize_round_metrics(round_metrics)
    evolution_totals = metrics_totals.get("evolution_metric_totals")
    evolution_totals = evolution_totals if isinstance(evolution_totals, dict) else {}
    rubric_totals = summary.get("rubric_metric_totals")
    rubric_totals = rubric_totals if isinstance(rubric_totals, dict) else {}
    if not rubric_totals:
        rubric_totals = metrics_totals.get("rubric_metric_totals")
        rubric_totals = rubric_totals if isinstance(rubric_totals, dict) else {}
    total_elapsed_seconds = _as_float(summary.get("total_elapsed_seconds"))
    if total_elapsed_seconds is None:
        total_elapsed_seconds = _as_float(summary.get("total_runtime_seconds"))
    total_agent_elapsed_seconds = _as_float(summary.get("total_agent_elapsed_seconds"))
    if total_agent_elapsed_seconds is None and metrics_totals["rounds_with_agent_timings"]:
        total_agent_elapsed_seconds = metrics_totals["total_agent_elapsed_seconds"]
    total_estimated_input_tokens = _as_int(summary.get("total_estimated_input_tokens"))
    total_estimated_output_tokens = _as_int(summary.get("total_estimated_output_tokens"))
    total_estimated_tokens = _as_int(summary.get("total_estimated_tokens"))
    if total_estimated_tokens is None and metrics_totals["rounds_with_token_estimates"]:
        total_estimated_input_tokens = metrics_totals["total_estimated_input_tokens"]
        total_estimated_output_tokens = metrics_totals["total_estimated_output_tokens"]
        total_estimated_tokens = metrics_totals["total_estimated_tokens"]
    token_estimate_method = summary.get("token_estimate_method") or (
        metrics_totals["token_estimate_method"]
        if metrics_totals["rounds_with_token_estimates"]
        else ""
    )
    avg_draft_to_revised_similarity = _as_float(summary.get("avg_draft_to_revised_similarity"))
    if avg_draft_to_revised_similarity is None:
        avg_draft_to_revised_similarity = _as_float(
            evolution_totals.get("avg_draft_to_revised_similarity")
        )
    avg_revised_similarity_to_previous = _as_float(
        summary.get("avg_revised_similarity_to_previous")
    )
    if avg_revised_similarity_to_previous is None:
        avg_revised_similarity_to_previous = _as_float(
            evolution_totals.get("avg_revised_similarity_to_previous")
        )
    avg_judge_similarity_to_previous = _as_float(summary.get("avg_judge_similarity_to_previous"))
    if avg_judge_similarity_to_previous is None:
        avg_judge_similarity_to_previous = _as_float(
            evolution_totals.get("avg_judge_similarity_to_previous")
        )
    low_revision_change_rounds = summary.get("low_revision_change_rounds")
    if not isinstance(low_revision_change_rounds, list):
        low_revision_change_rounds = evolution_totals.get("low_revision_change_rounds", [])
    if not isinstance(low_revision_change_rounds, list):
        low_revision_change_rounds = []
    low_previous_revised_change_rounds = summary.get("low_previous_revised_change_rounds")
    if not isinstance(low_previous_revised_change_rounds, list):
        low_previous_revised_change_rounds = evolution_totals.get(
            "low_previous_revised_change_rounds", []
        )
    if not isinstance(low_previous_revised_change_rounds, list):
        low_previous_revised_change_rounds = []
    rubric_averages = summary.get("rubric_subscore_averages")
    if not isinstance(rubric_averages, dict):
        rubric_averages = rubric_totals.get("rubric_averages", {})
    if not isinstance(rubric_averages, dict):
        rubric_averages = {}
    rubric_round_count = _as_int(summary.get("rubric_round_count"))
    if rubric_round_count is None:
        rubric_round_count = _as_int(rubric_totals.get("rounds_with_rubric"))
    rubric_average_fields = _rubric_average_fields(rubric_averages)
    metadata_sources = []
    if summary:
        metadata_sources.append("run_summary")
    compatibility = run_config.get("compatibility")
    compatibility = compatibility if isinstance(compatibility, dict) else {}
    if run_config:
        metadata_sources.append(
            "legacy_run_manifest" if compatibility.get("run_config_missing") else "run_config"
        )
    if round_metrics:
        metadata_sources.append("round_metrics")
    model_label = (
        model_config.get("label") or model_config.get("name") or summary.get("model") or ""
    )
    return {
        "run_id": summary.get("run_id") or run_config.get("run_id", run_root.name),
        "run_path": str(run_root),
        "run_root": str(run_root),
        "mode": summary.get("mode") or run_config.get("mode", ""),
        "provider": model_config.get("provider") or summary.get("provider", ""),
        "model": model_label,
        "drafting_mode": summary.get("drafting_mode") or run_config.get("drafting_mode", ""),
        "max_rounds": runtime_config.get("max_rounds") or summary.get("max_rounds"),
        "completed_rounds": completed_rounds,
        "best_score": round(best_score, 2) if best_score is not None else None,
        "average_score": average_score,
        "stop_reason": summary.get("stop_reason") or run_config.get("stop_reason", ""),
        "timeout_count": len(timeout_rounds),
        "error_count": len(error_rounds),
        "total_elapsed_seconds": (
            round(total_elapsed_seconds, 3) if total_elapsed_seconds is not None else None
        ),
        "total_agent_elapsed_seconds": (
            round(total_agent_elapsed_seconds, 3)
            if total_agent_elapsed_seconds is not None
            else None
        ),
        "total_estimated_input_tokens": total_estimated_input_tokens,
        "total_estimated_output_tokens": total_estimated_output_tokens,
        "total_estimated_tokens": total_estimated_tokens,
        "token_estimate_method": token_estimate_method,
        "avg_draft_to_revised_similarity": avg_draft_to_revised_similarity,
        "avg_revised_similarity_to_previous": avg_revised_similarity_to_previous,
        "avg_judge_similarity_to_previous": avg_judge_similarity_to_previous,
        "low_revision_change_count": len(low_revision_change_rounds),
        "low_previous_revised_change_count": len(low_previous_revised_change_rounds),
        "low_revision_change_rounds": low_revision_change_rounds,
        "low_previous_revised_change_rounds": low_previous_revised_change_rounds,
        "rubric_round_count": rubric_round_count,
        "rubric_subscore_averages": rubric_averages,
        **rubric_average_fields,
        "round_count": summary.get("round_count", len(round_metrics)),
        "successful_rounds": successful_rounds,
        "timeout_rounds": timeout_rounds,
        "error_rounds": error_rounds,
        "run_config_path": str(run_config_path),
        "run_summary_path": str(run_summary_path),
        "metadata_sources": metadata_sources,
        "metadata_status": "ok" if metadata_sources else "missing",
    }


def compare_runs(run_roots: Sequence[Path]) -> dict[str, Any]:
    runs = [load_run_summary(Path(run_root)) for run_root in run_roots]
    ranked = sorted(
        runs,
        key=lambda item: (
            _as_float(item.get("best_score"))
            if _as_float(item.get("best_score")) is not None
            else -1.0,
            _as_int(item.get("completed_rounds")) or 0,
        ),
        reverse=True,
    )
    best_run = ranked[0] if ranked else {}
    baseline_score = _as_float(runs[0].get("best_score")) if runs else None
    best_score = _as_float(best_run.get("best_score"))
    return {
        "run_count": len(runs),
        "best_run_id": best_run.get("run_id", ""),
        "best_score": best_run.get("best_score"),
        "baseline_run_id": runs[0].get("run_id", "") if runs else "",
        "best_vs_baseline_delta": round(
            best_score - baseline_score,
            2,
        )
        if best_score is not None and baseline_score is not None
        else None,
        "runs": runs,
    }


def write_run_comparison(run_roots: Sequence[Path], output_path: Path) -> dict[str, Any]:
    comparison = compare_runs(run_roots)
    write_json_file(output_path, comparison)
    return comparison
