"""Helpers for comparing completed Auto Research Agent runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

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
