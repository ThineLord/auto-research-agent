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


def load_run_summary(run_root: Path) -> dict[str, Any]:
    summary = _read_json(run_root / "run_summary.json")
    if isinstance(summary, dict) and summary:
        return summary

    run_config = read_run_config(run_root)
    model_config = run_config.get("model")
    model_label = model_config.get("label", "") if isinstance(model_config, dict) else ""
    round_metrics = _read_json_list(run_root / "round_metrics.json")
    scores = [
        float(entry["score"])
        for entry in round_metrics
        if isinstance(entry.get("score"), (int, float))
    ]
    best_score = max(scores) if scores else float(run_config.get("best_score", -1.0) or -1.0)
    return {
        "run_id": run_config.get("run_id", run_root.name),
        "run_root": str(run_root),
        "mode": run_config.get("mode", ""),
        "model": model_label,
        "drafting_mode": run_config.get("drafting_mode", ""),
        "completed_rounds": run_config.get("completed_rounds", len(round_metrics)),
        "best_score": round(best_score, 2),
        "stop_reason": run_config.get("stop_reason", ""),
        "round_count": len(round_metrics),
        "successful_rounds": [
            entry.get("round") for entry in round_metrics if entry.get("successful_research_round")
        ],
        "timeout_rounds": [
            entry.get("round") for entry in round_metrics if entry.get("timeout_this_round")
        ],
        "error_rounds": [entry.get("round") for entry in round_metrics if entry.get("errors")],
    }


def compare_runs(run_roots: Sequence[Path]) -> dict[str, Any]:
    runs = [load_run_summary(Path(run_root)) for run_root in run_roots]
    ranked = sorted(
        runs,
        key=lambda item: (
            float(item.get("best_score", -1.0) or -1.0),
            int(item.get("completed_rounds", 0) or 0),
        ),
        reverse=True,
    )
    best_run = ranked[0] if ranked else {}
    baseline_score = float(runs[0].get("best_score", -1.0) or -1.0) if runs else -1.0
    return {
        "run_count": len(runs),
        "best_run_id": best_run.get("run_id", ""),
        "best_score": best_run.get("best_score"),
        "baseline_run_id": runs[0].get("run_id", "") if runs else "",
        "best_vs_baseline_delta": round(
            float(best_run.get("best_score", -1.0) or -1.0) - baseline_score,
            2,
        )
        if runs
        else None,
        "runs": runs,
    }


def write_run_comparison(run_roots: Sequence[Path], output_path: Path) -> dict[str, Any]:
    comparison = compare_runs(run_roots)
    write_json_file(output_path, comparison)
    return comparison
