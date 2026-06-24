"""Single-run analytics export built from existing run artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .run_compare import load_run_summary
from .storage import write_json_file


def _read_json_list(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, list):
        return []
    return [entry for entry in payload if isinstance(entry, dict)]


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _numeric_scores(round_metrics: list[dict[str, Any]]) -> list[tuple[Any, float]]:
    scores: list[tuple[Any, float]] = []
    for entry in round_metrics:
        score = _as_float(entry.get("score"))
        if score is not None:
            scores.append((entry.get("round"), score))
    return scores


def _score_trend(round_metrics: list[dict[str, Any]]) -> dict[str, Any]:
    scores = _numeric_scores(round_metrics)
    if not scores:
        return {
            "first_round": None,
            "first_score": None,
            "latest_round": None,
            "latest_score": None,
            "score_delta_first_to_latest": None,
            "trend": "unknown",
        }
    first_round, first_score = scores[0]
    latest_round, latest_score = scores[-1]
    delta = round(latest_score - first_score, 2)
    if len(scores) == 1:
        trend = "single_round"
    elif delta > 0:
        trend = "improved"
    elif delta < 0:
        trend = "declined"
    else:
        trend = "flat"
    return {
        "first_round": first_round,
        "first_score": first_score,
        "latest_round": latest_round,
        "latest_score": latest_score,
        "score_delta_first_to_latest": delta if len(scores) > 1 else None,
        "trend": trend,
    }


def analyze_run(run_root: Path) -> dict[str, Any]:
    """Summarize one run without provider calls or scoring reinterpretation."""
    run_root = Path(run_root)
    summary = load_run_summary(run_root)
    round_metrics = _read_json_list(run_root / "round_metrics.json")
    score_trend = _score_trend(round_metrics)
    return {
        "analysis_version": 1,
        "run_id": summary.get("run_id"),
        "run_path": summary.get("run_path"),
        "metadata_status": summary.get("metadata_status"),
        "metadata_sources": summary.get("metadata_sources", []),
        "model": {
            "provider": summary.get("provider"),
            "name": summary.get("model"),
            "drafting_mode": summary.get("drafting_mode"),
        },
        "rounds": {
            "max_rounds": summary.get("max_rounds"),
            "completed_rounds": summary.get("completed_rounds"),
            "round_count": summary.get("round_count"),
            "successful_rounds": summary.get("successful_rounds", []),
        },
        "score": {
            "best_score": summary.get("best_score"),
            "average_score": summary.get("average_score"),
            **score_trend,
        },
        "robustness": {
            "stop_reason": summary.get("stop_reason"),
            "timeout_count": summary.get("timeout_count"),
            "error_count": summary.get("error_count"),
            "timeout_rounds": summary.get("timeout_rounds", []),
            "error_rounds": summary.get("error_rounds", []),
        },
        "cost_ready": {
            "total_agent_elapsed_seconds": summary.get("total_agent_elapsed_seconds"),
            "total_estimated_input_tokens": summary.get("total_estimated_input_tokens"),
            "total_estimated_output_tokens": summary.get("total_estimated_output_tokens"),
            "total_estimated_tokens": summary.get("total_estimated_tokens"),
            "token_estimate_method": summary.get("token_estimate_method"),
        },
        "interpretability": {
            "avg_draft_to_revised_similarity": summary.get("avg_draft_to_revised_similarity"),
            "avg_revised_similarity_to_previous": summary.get("avg_revised_similarity_to_previous"),
            "avg_judge_similarity_to_previous": summary.get("avg_judge_similarity_to_previous"),
            "low_revision_change_count": summary.get("low_revision_change_count"),
            "low_previous_revised_change_count": summary.get("low_previous_revised_change_count"),
            "low_revision_change_rounds": summary.get("low_revision_change_rounds", []),
            "low_previous_revised_change_rounds": summary.get(
                "low_previous_revised_change_rounds", []
            ),
        },
        "rubric": {
            "rubric_round_count": summary.get("rubric_round_count"),
            "rubric_subscore_averages": summary.get("rubric_subscore_averages", {}),
            "rubric_avg_evaluation": summary.get("rubric_avg_evaluation"),
            "rubric_avg_actionability": summary.get("rubric_avg_actionability"),
        },
        "artifacts": {
            "run_config_path": summary.get("run_config_path"),
            "run_summary_path": summary.get("run_summary_path"),
        },
    }


def write_run_analysis(run_root: Path, output_path: Path) -> dict[str, Any]:
    analysis = analyze_run(run_root)
    write_json_file(output_path, analysis)
    return analysis
