"""Checkpoint resume workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from rich.console import Console

from .agents import ResearchAgents
from .config import DEFAULT_DRAFTING_MODE
from .runner import run_iterative_rounds
from .storage import read_json_file

ROUND_OUTPUT_FILES = ("01_draft.md", "02_review.md", "03_revised.md", "04_judge.md")
NEXT_ROUND_FAIL_SAFE_ACTION = "fail_safe_require_user_action"


def _safe_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = -1.0) -> float:
    if isinstance(value, bool):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _display_path(path: Path, root: Path | None) -> str:
    if root is not None:
        try:
            return path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            pass
    return f"<repo>/{path.name}"


def inspect_next_round_directory(
    next_round_path: Path | None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    if next_round_path is None:
        return {
            "path": "",
            "display_path": "N/A",
            "exists": False,
            "status": "unknown",
            "blocks_resume": False,
            "safety_action": "none",
            "existing_files": [],
            "missing_expected_files": list(ROUND_OUTPUT_FILES),
        }

    display_path = _display_path(next_round_path, repo_root)
    if not next_round_path.exists():
        return {
            "path": str(next_round_path),
            "display_path": display_path,
            "exists": False,
            "status": "missing",
            "blocks_resume": False,
            "safety_action": "proceed_create_round_dir",
            "existing_files": [],
            "missing_expected_files": list(ROUND_OUTPUT_FILES),
        }

    entries = sorted(next_round_path.iterdir(), key=lambda path: path.name)
    if not entries:
        return {
            "path": str(next_round_path),
            "display_path": display_path,
            "exists": True,
            "status": "empty",
            "blocks_resume": False,
            "safety_action": "proceed_reuse_empty_round_dir",
            "existing_files": [],
            "missing_expected_files": list(ROUND_OUTPUT_FILES),
        }

    existing_names = [path.name for path in entries]
    expected_present = [name for name in ROUND_OUTPUT_FILES if (next_round_path / name).exists()]
    missing_expected = [name for name in ROUND_OUTPUT_FILES if name not in expected_present]
    unexpected_entries = [name for name in existing_names if name not in ROUND_OUTPUT_FILES]
    status = (
        "complete_uncheckpointed"
        if len(expected_present) == len(ROUND_OUTPUT_FILES) and not unexpected_entries
        else "partial"
    )
    return {
        "path": str(next_round_path),
        "display_path": display_path,
        "exists": True,
        "status": status,
        "blocks_resume": True,
        "safety_action": NEXT_ROUND_FAIL_SAFE_ACTION,
        "existing_files": existing_names,
        "missing_expected_files": missing_expected,
        "unexpected_entries": unexpected_entries,
    }


def build_resume_preview(
    *,
    project_dir: Path,
    checkpoint: dict[str, Any],
    repo_root: Path | None = None,
) -> dict[str, Any]:
    checkpoint_path = project_dir / "checkpoint.json"
    if not checkpoint:
        return {
            "can_resume": False,
            "blocked_reason": "missing_checkpoint",
            "message": "checkpoint.json is missing or empty",
            "checkpoint_path": str(checkpoint_path),
            "checkpoint_display_path": _display_path(checkpoint_path, repo_root),
        }

    run_root_text = str(checkpoint.get("run_root", "")).strip()
    run_root_path = Path(run_root_text) if run_root_text else None
    last_completed_round = _safe_int(checkpoint.get("last_completed_round"), 0)
    next_round = last_completed_round + 1
    run_id = str(checkpoint.get("run_id") or (run_root_path.name if run_root_path else "")).strip()
    stop_reason = str(checkpoint.get("stop_reason", "") or "unknown")
    run_config_path = (
        Path(str(checkpoint.get("run_config")))
        if checkpoint.get("run_config")
        else (run_root_path / "run_config.json" if run_root_path else None)
    )
    run_summary_path = (
        Path(str(checkpoint.get("run_summary")))
        if checkpoint.get("run_summary")
        else (run_root_path / "run_summary.json" if run_root_path else None)
    )
    next_round_path = run_root_path / f"round_{next_round:02d}" if run_root_path else None
    next_round_info = inspect_next_round_directory(next_round_path, repo_root)

    preview = {
        "lifecycle_action": "resume_existing_run",
        "resume_from_checkpoint": True,
        "checkpoint_path": str(checkpoint_path),
        "checkpoint_display_path": _display_path(checkpoint_path, repo_root),
        "run_id": run_id,
        "run_root": str(run_root_path) if run_root_path else "",
        "run_root_display": _display_path(run_root_path, repo_root) if run_root_path else "N/A",
        "run_config": str(run_config_path) if run_config_path else "",
        "run_config_display": _display_path(run_config_path, repo_root)
        if run_config_path
        else "N/A",
        "run_summary": str(run_summary_path) if run_summary_path else "",
        "run_summary_display": _display_path(run_summary_path, repo_root)
        if run_summary_path
        else "N/A",
        "last_completed_round": last_completed_round,
        "next_round": next_round,
        "resume_from_round": next_round,
        "stop_reason": stop_reason,
        "can_resume": bool(checkpoint.get("can_resume")),
        "best_score": _safe_float(checkpoint.get("best_score"), -1.0),
        "completed_round_files_preserved": True,
        "next_round_path": str(next_round_path) if next_round_path else "",
        "next_round_display": next_round_info["display_path"],
        "next_round_dir_exists": next_round_info["exists"],
        "next_round_status": next_round_info["status"],
        "next_round_blocks_resume": next_round_info["blocks_resume"],
        "next_round_safety_action": next_round_info["safety_action"],
        "next_round_existing_files": next_round_info["existing_files"],
        "next_round_missing_expected_files": next_round_info["missing_expected_files"],
    }

    if not checkpoint.get("can_resume"):
        preview.update(
            {
                "can_resume": False,
                "blocked_reason": "not_resume_eligible",
                "message": "checkpoint exists but can_resume is false",
            }
        )
        return preview
    if run_root_path is None:
        preview.update(
            {
                "can_resume": False,
                "blocked_reason": "missing_run_root",
                "message": "checkpoint run_root is missing",
            }
        )
        return preview
    if not run_root_path.exists():
        preview.update(
            {
                "can_resume": False,
                "blocked_reason": "stale_run_root",
                "message": "checkpoint run_root does not exist",
            }
        )
        return preview
    if next_round_info["blocks_resume"]:
        preview.update(
            {
                "can_resume": False,
                "blocked_reason": "partial_next_round_exists",
                "message": (
                    "next round directory already contains files; resume is blocked to avoid "
                    "overwriting partial or uncheckpointed outputs"
                ),
            }
        )
        return preview

    preview["message"] = (
        "resume existing run from checkpoint; completed round files will be preserved"
    )
    return preview


def _print_resume_preview(console: Console, preview: dict[str, Any]) -> None:
    if not preview.get("run_root") and not preview.get("run_id"):
        return
    console.print(
        "[cyan]Resume preview:[/cyan] "
        f"run_id={preview.get('run_id') or 'N/A'} "
        f"run_root={preview.get('run_root_display')} "
        f"last_completed_round={preview.get('last_completed_round')} "
        f"next_round={preview.get('next_round')} "
        f"stop_reason={preview.get('stop_reason')} "
        f"can_resume={preview.get('can_resume')}"
    )
    console.print(
        "[cyan]Next round directory:[/cyan] "
        f"path={preview.get('next_round_display')} "
        f"status={preview.get('next_round_status')} "
        f"action={preview.get('next_round_safety_action')}"
    )


def run_resume_mode(
    *,
    console: Console,
    agents: ResearchAgents,
    task_text: str,
    project_dir: Path,
    memory_path: Path,
    model_name: str,
    max_rounds: int,
    stop_if_no_improvement_rounds: int,
    global_max_runtime_seconds: int,
    per_agent_timeout_seconds: int,
    topic_keywords: Sequence[str] = (),
    project_metadata: dict[str, object] | None = None,
    model_provider: str = "",
    model_parameters: dict[str, Any] | None = None,
    topic_snapshot: dict[str, Any] | None = None,
    prompt_dir: Path | None = None,
    repo_root: Path | None = None,
    drafting_mode: str = DEFAULT_DRAFTING_MODE,
    max_consecutive_provider_quota_failures: int = 2,
) -> None:
    checkpoint_path = project_dir / "checkpoint.json"
    checkpoint = read_json_file(checkpoint_path)
    preview = build_resume_preview(
        project_dir=project_dir,
        checkpoint=checkpoint,
        repo_root=repo_root,
    )
    _print_resume_preview(console, preview)
    if not preview.get("can_resume"):
        console.print(f"[red]Cannot resume: {preview.get('message', 'unknown reason')}.[/red]")
        return
    run_root_path = Path(str(preview["run_root"]))
    start_round = _safe_int(preview.get("next_round"), 1)
    initial_best_score = _safe_float(preview.get("best_score"), -1.0)
    console.print(
        "[cyan]Lifecycle:[/cyan] Resuming the existing run from checkpoint; "
        "completed round files are preserved. This is not a new run from previous best output."
    )
    if preview.get("next_round_status") == "empty":
        console.print(
            "[yellow]Resume note:[/yellow] "
            f"{preview.get('next_round_display')} already exists but is empty; resume can use it."
        )
    run_iterative_rounds(
        console=console,
        agents=agents,
        task_text=task_text,
        project_dir=project_dir,
        memory_path=memory_path,
        mode="resume",
        model_name=model_name,
        max_rounds=max(max_rounds, start_round),
        stop_if_no_improvement_rounds=stop_if_no_improvement_rounds,
        global_max_runtime_seconds=global_max_runtime_seconds,
        per_agent_timeout_seconds=per_agent_timeout_seconds,
        start_round=start_round,
        run_root_override=run_root_path,
        initial_best_score=initial_best_score,
        topic_keywords=topic_keywords,
        project_metadata=project_metadata,
        model_provider=model_provider,
        model_parameters=model_parameters,
        topic_snapshot=topic_snapshot,
        prompt_dir=prompt_dir,
        repo_root=repo_root,
        drafting_mode=drafting_mode,
        max_consecutive_provider_quota_failures=max_consecutive_provider_quota_failures,
        resume_metadata=preview,
    )
