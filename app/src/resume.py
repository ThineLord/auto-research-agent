"""Checkpoint resume workflow."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from rich.console import Console

from .agents import ResearchAgents
from .config import DEFAULT_DRAFTING_MODE, MODEL_PROVIDER_GEMINI, MODEL_PROVIDER_OLLAMA
from .mock_run import MOCK_MODEL_NAME, MOCK_MODEL_PROVIDER
from .resume_safety import (
    RESUME_PATH_MESSAGES,
    RUN_ID_MISMATCH,
    UNSAFE_ARTIFACT_PATH,
    UNSAFE_ROUND_PATH,
    resume_artifact_links_are_safe,
    validate_resume_round_dir,
    validate_resume_run_root,
)
from .round_attempts import classify_round_recovery
from .round_commit_recovery import round_commit_read_blocker
from .run_config import INHERIT_GIT_ROOT, GitRootSetting
from .runner import ResumeHistoryError, format_mock_recovery_note, run_iterative_rounds
from .storage import (
    artifact_path_exists,
    artifact_path_is_safe,
    ensure_project_runtime_paths_safe,
    list_artifact_entry_names,
    read_json_file,
    read_regular_text,
)

ROUND_OUTPUT_FILES = ("01_draft.md", "02_review.md", "03_revised.md", "04_judge.md")
NEXT_ROUND_FAIL_SAFE_ACTION = "fail_safe_require_user_action"
OFFLINE_MOCK_BLOCKED_REASON = "offline_mock"
_OFFLINE_MOCK_MODEL_NAMES = frozenset({MOCK_MODEL_NAME, MOCK_MODEL_PROVIDER})


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
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return parsed if math.isfinite(parsed) else default


def _strict_round_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if math.isfinite(value) and value.is_integer() else None
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _checkpoint_best_round(checkpoint: dict[str, Any]) -> int | None:
    best_round = _strict_round_int(checkpoint.get("best_round"))
    if best_round is not None and best_round > 0:
        return best_round
    best_round_path = str(checkpoint.get("best_round_path", "")).strip()
    round_dir_name = Path(best_round_path).name if best_round_path else ""
    if not round_dir_name.startswith("round_"):
        return None
    suffix = round_dir_name.removeprefix("round_")
    parsed = _strict_round_int(suffix) if suffix.isdigit() else None
    return parsed if parsed is not None and parsed > 0 else None


def _display_path(path: Path, root: Path | None) -> str:
    if root is not None:
        try:
            return path.resolve().relative_to(root.resolve()).as_posix()
        except (OSError, RuntimeError, ValueError):
            pass
    return f"<repo>/{path.name}"


def checkpoint_read_problem(project_dir: Path) -> str | None:
    """Distinguish a corrupt or unreadable checkpoint from a missing one.

    Missing and empty files stay on the existing resume preview path. A file
    that cannot be decoded, or that cannot be opened, must not be described as
    absent.
    """

    path = project_dir / "checkpoint.json"
    try:
        content = read_regular_text(path, missing_ok=False, anchor=project_dir)
    except FileNotFoundError:
        return None
    except UnicodeError:
        return "checkpoint.json is corrupt"
    except OSError:
        return "checkpoint.json is unreadable"
    if not content.strip():
        return None
    try:
        data = json.loads(content)
    except (ValueError, RecursionError):
        return "checkpoint.json is corrupt"
    if not isinstance(data, dict):
        return "checkpoint.json is corrupt"
    return None


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
    safe_round_path, path_error = validate_resume_round_dir(
        run_root=next_round_path.parent,
        round_dir=next_round_path,
        require_writable=True,
    )
    if path_error:
        return {
            "path": "",
            "display_path": "N/A",
            "exists": False,
            "status": "unsafe" if path_error == UNSAFE_ROUND_PATH else "invalid",
            "blocks_resume": True,
            "blocked_reason": path_error,
            "message": RESUME_PATH_MESSAGES[path_error],
            "safety_action": NEXT_ROUND_FAIL_SAFE_ACTION,
            "existing_files": [],
            "missing_expected_files": list(ROUND_OUTPUT_FILES),
        }
    assert safe_round_path is not None
    next_round_path = safe_round_path
    try:
        existing_names = list_artifact_entry_names(next_round_path, missing_ok=True)
        directory_exists = artifact_path_exists(next_round_path, allow_directory=True)
        round_index = _strict_round_int(next_round_path.name.removeprefix("round_"))
        if round_index is None or round_index < 1:
            raise ValueError
        classification = classify_round_recovery(next_round_path.parent, round_index)
    except (OSError, ValueError):
        return {
            "path": "",
            "display_path": "N/A",
            "exists": True,
            "status": "unsafe",
            "blocks_resume": True,
            "blocked_reason": UNSAFE_ROUND_PATH,
            "message": "next round directory cannot be inspected safely",
            "safety_action": NEXT_ROUND_FAIL_SAFE_ACTION,
            "existing_files": [],
            "missing_expected_files": list(ROUND_OUTPUT_FILES),
        }

    expected_present = [
        name
        for name in ROUND_OUTPUT_FILES
        if artifact_path_is_safe(next_round_path / name, allow_missing=False)
    ]
    missing_expected = [name for name in ROUND_OUTPUT_FILES if name not in expected_present]
    unexpected_entries = [name for name in existing_names if name not in ROUND_OUTPUT_FILES]
    status = classification.status
    action = classification.safety_action
    if status == "new_round":
        status = "missing"
        action = "proceed_create_round_dir"
    elif status == "legacy_empty_canonical":
        status = "empty"
    elif status == "legacy_partial":
        status = (
            "complete_uncheckpointed"
            if len(expected_present) == len(ROUND_OUTPUT_FILES) and not unexpected_entries
            else "partial"
        )
        action = NEXT_ROUND_FAIL_SAFE_ACTION
    blocked_reason = classification.blocked_reason
    if classification.status == "legacy_partial":
        blocked_reason = "partial_next_round_exists"
    return {
        "path": str(next_round_path),
        "display_path": display_path,
        "exists": directory_exists,
        "status": status,
        "blocks_resume": not classification.can_create_attempt,
        "blocked_reason": blocked_reason,
        "safety_action": action,
        "existing_files": existing_names,
        "missing_expected_files": missing_expected,
        "unexpected_entries": unexpected_entries,
        "preserved_attempt_count": classification.preserved_attempt_count,
        "latest_verified_completed_stage": (classification.latest_verified_completed_stage),
        "retained_attempt_bytes": classification.retained_attempt_bytes,
        "free_bytes": classification.free_bytes,
    }


_REAL_PROVIDERS = frozenset({MODEL_PROVIDER_OLLAMA, MODEL_PROVIDER_GEMINI})
_REAL_RUN_MODES = frozenset({"normal", "continuous", "diagnostic", "session", "resume"})
_RESUME_BLOCK_PREFIXES = (
    "finalization_",
    "diagnostic_finalization_",
    "round_commit_",
    "legacy_migration_",
)


def _value_missing(value: Any) -> bool:
    return value is None or value in ("", {}, [])


def _record_provider(record: Mapping[str, Any]) -> str:
    provider = record.get("provider")
    if isinstance(provider, str) and provider:
        return provider
    model = record.get("model")
    if isinstance(model, dict):
        model_provider = model.get("provider")
        if isinstance(model_provider, str):
            return model_provider
    return ""


def _strong_offline_mock(record: Mapping[str, Any]) -> bool:
    if record.get("mode") == MOCK_MODEL_PROVIDER or record.get("provider") == MOCK_MODEL_PROVIDER:
        return True
    model = record.get("model")
    if isinstance(model, dict) and (
        model.get("provider") == MOCK_MODEL_PROVIDER or model.get("provider_free") is True
    ):
        return True
    project = record.get("project")
    if isinstance(project, dict):
        mock_mode = project.get("mock_mode")
        if isinstance(mock_mode, dict) and (
            mock_mode.get("provider_free") is True or mock_mode.get("deterministic") is True
        ):
            return True
    return False


def _name_only_offline_mock(record: Mapping[str, Any]) -> bool:
    """Historical fallback: the model name alone, with no provider proof."""

    model = record.get("model")
    if isinstance(model, str):
        return model in _OFFLINE_MOCK_MODEL_NAMES
    if isinstance(model, dict):
        return any(model.get(key) in _OFFLINE_MOCK_MODEL_NAMES for key in ("name", "label"))
    return False


def _proven_real_provider(record: Mapping[str, Any]) -> bool:
    return record.get("mode") in _REAL_RUN_MODES and _record_provider(record) in _REAL_PROVIDERS


def _records_are_offline_mock(*records: Any) -> bool:
    present = [record for record in records if isinstance(record, Mapping) and record]
    if any(_strong_offline_mock(record) for record in present):
        return True
    if any(_proven_real_provider(record) for record in present):
        return False
    return any(_name_only_offline_mock(record) for record in present)


def _positive_round_cap(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return None
    return value


def _round_cap_from_record(record: Mapping[str, Any]) -> int | None:
    direct = _positive_round_cap(record.get("max_rounds"))
    if direct is not None:
        return direct
    runtime = record.get("runtime")
    if isinstance(runtime, dict):
        return _positive_round_cap(runtime.get("max_rounds"))
    return None


def _read_linked_json(path: Path, anchor: Path) -> tuple[str, dict[str, Any]]:
    try:
        content = read_regular_text(path, missing_ok=False, anchor=anchor)
    except FileNotFoundError:
        return "missing", {}
    except (OSError, UnicodeError):
        return "invalid", {}
    try:
        data = json.loads(content)
    except (ValueError, RecursionError):
        return "invalid", {}
    if not isinstance(data, dict):
        return "invalid", {}
    return "object", data


def _same_run_record(record: Mapping[str, Any], run_root: Path) -> bool:
    """True when this file does not name a different run or path."""

    run_id = record.get("run_id")
    if run_id not in (None, ""):
        if not isinstance(run_id, str) or run_id != run_root.name:
            return False
    root_value = record.get("run_root")
    if root_value in (None, ""):
        return True
    if not isinstance(root_value, str):
        return False
    try:
        recorded = Path(root_value).expanduser().resolve(strict=False)
        return recorded == run_root.resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        return False


def _combine_same_run_records(
    config: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Fill gaps from the manifest. Values already stored in run_config win."""

    combined = dict(manifest)
    for key, value in config.items():
        if key == "runtime":
            continue
        if not _value_missing(value) or key not in combined:
            combined[key] = value
    runtime: dict[str, Any] = {}
    manifest_runtime = manifest.get("runtime")
    config_runtime = config.get("runtime")
    if isinstance(manifest_runtime, dict):
        runtime.update(manifest_runtime)
    if isinstance(config_runtime, dict):
        for key, value in config_runtime.items():
            if not _value_missing(value) or key not in runtime:
                runtime[key] = value
    if runtime:
        combined["runtime"] = runtime
    return combined


def _linked_run_record(project_dir: Path, checkpoint: Mapping[str, Any]) -> dict[str, Any]:
    """Read one run's config and manifest after the checkpoint path is verified.

    A readable ``run_config.json`` used to hide ``run_manifest.json``. Missing mode
    or model is filled from that same run's manifest. A conflicting run id or path
    is ignored, and an unreadable config still hides the manifest.
    """

    run_root, error = validate_resume_run_root(
        project_dir=project_dir,
        run_root_value=checkpoint.get("run_root"),
    )
    if error or run_root is None:
        return {}
    config_path = run_root / "run_config.json"
    manifest_path = run_root / "run_manifest.json"
    if not resume_artifact_links_are_safe(
        parent_dir=run_root,
        paths=(config_path, manifest_path),
    ):
        return {}
    config_state, config = _read_linked_json(config_path, run_root)
    if config_state == "invalid":
        return {}
    if config_state == "object" and not _same_run_record(config, run_root):
        config = {}
    manifest_state, manifest = _read_linked_json(manifest_path, run_root)
    if manifest_state != "object" or not _same_run_record(manifest, run_root):
        manifest = {}
    if not config and not manifest:
        return {}
    return _combine_same_run_records(config, manifest)


def offline_mock_resume_block(
    *,
    project_dir: Path,
    checkpoint: Mapping[str, Any] | None = None,
    repo_root: Path | None = None,
    explicit_workspace: Path | None = None,
    source_layout: bool | None = None,
) -> dict[str, str] | None:
    """Refuse ordinary resume of an offline mock before any provider or run write.

    Strong evidence is mock mode, the mock provider, or provider-free mock metadata.
    A historical model name of ``mock`` or ``mock-deterministic`` is only a fallback,
    and it does not override a run that already records a real provider. The returned
    message tells the user to start a new offline mock. ``command`` is empty when the
    round cap cannot be pinned.
    """

    ensure_project_runtime_paths_safe(project_dir)
    if checkpoint is None:
        checkpoint = read_json_file(project_dir / "checkpoint.json", anchor=project_dir)
    if not isinstance(checkpoint, Mapping):
        return None
    run_record = _linked_run_record(project_dir, checkpoint)
    if not _records_are_offline_mock(checkpoint, run_record):
        return None
    max_rounds = _round_cap_from_record(run_record)
    if max_rounds is None:
        max_rounds = _round_cap_from_record(checkpoint)
    message = format_mock_recovery_note(
        project_dir,
        repo_root,
        explicit_workspace=explicit_workspace,
        source_layout=source_layout,
        max_rounds=max_rounds,
    )
    command = ""
    if "`" in message:
        command = message.split("`", 2)[1]
    return {"message": message, "command": command}


def _build_resume_preview(
    *,
    project_dir: Path,
    checkpoint: dict[str, Any],
    repo_root: Path | None = None,
) -> dict[str, Any]:
    ensure_project_runtime_paths_safe(project_dir)
    checkpoint_path = project_dir / "checkpoint.json"
    recovery_blocker, recovery = round_commit_read_blocker(project_dir)
    if recovery_blocker is not None:
        is_finalization = recovery_blocker.startswith("finalization_")
        is_diagnostic_finalization = recovery_blocker.startswith("diagnostic_finalization_")
        if is_diagnostic_finalization:
            message = (
                "a pending diagnostic finalization must be recovered under the project lock "
                "before resume"
                if recovery.can_recover
                else "diagnostic finalization recovery is blocked; preserve the artifacts and "
                "inspect them"
            )
        elif is_finalization:
            message = (
                "a pending run finalization must be recovered under the project lock before resume"
                if recovery.can_recover
                else "run finalization recovery is blocked; preserve the artifacts and inspect them"
            )
        else:
            message = (
                "a pending round commit must be recovered under the project lock before resume"
                if recovery.can_recover
                else "round commit recovery is blocked; preserve the artifacts and inspect them"
            )
        return {
            "can_resume": False,
            "blocked_reason": recovery_blocker,
            "message": message,
            "checkpoint_path": str(checkpoint_path),
            "checkpoint_display_path": _display_path(checkpoint_path, repo_root),
            "run_id": recovery.run_id or "",
            "last_completed_round": (
                recovery.round_index
                if (is_finalization or is_diagnostic_finalization)
                and recovery.round_index is not None
                else recovery.round_index - 1
                if recovery.round_index is not None and recovery.round_index > 0
                else 0
            ),
            "next_round": (
                None if is_finalization or is_diagnostic_finalization else recovery.round_index
            ),
            (
                "diagnostic_finalization_status"
                if is_diagnostic_finalization
                else "finalization_status"
                if is_finalization
                else "round_commit_status"
            ): recovery.status,
            (
                "diagnostic_finalization_can_recover"
                if is_diagnostic_finalization
                else "finalization_can_recover"
                if is_finalization
                else "round_commit_can_recover"
            ): recovery.can_recover,
            (
                "diagnostic_finalization_journal_present"
                if is_diagnostic_finalization
                else "finalization_journal_present"
                if is_finalization
                else "round_commit_journal_present"
            ): recovery.journal_present,
        }
    if not checkpoint:
        return {
            "can_resume": False,
            "blocked_reason": "missing_checkpoint",
            "message": "checkpoint.json is missing or empty",
            "checkpoint_path": str(checkpoint_path),
            "checkpoint_display_path": _display_path(checkpoint_path, repo_root),
        }

    last_completed_round = _strict_round_int(checkpoint.get("last_completed_round", 0))
    if last_completed_round is None or last_completed_round < 0:
        return {
            "can_resume": False,
            "blocked_reason": "invalid_last_completed_round",
            "message": "checkpoint last_completed_round must be >= 0",
            "checkpoint_path": str(checkpoint_path),
            "checkpoint_display_path": _display_path(checkpoint_path, repo_root),
        }
    next_round = last_completed_round + 1
    best_round = _checkpoint_best_round(checkpoint)
    checkpoint_can_resume = checkpoint.get("can_resume") is True
    run_root_path, run_root_error = validate_resume_run_root(
        project_dir=project_dir,
        run_root_value=checkpoint.get("run_root"),
    )
    checkpoint_run_id = checkpoint.get("run_id")
    checkpoint_has_run_id = checkpoint_run_id not in (None, "")
    canonical_run_id = run_root_path.name if run_root_path and run_root_error is None else ""
    run_id_mismatch = bool(
        checkpoint_has_run_id
        and canonical_run_id
        and (not isinstance(checkpoint_run_id, str) or checkpoint_run_id != canonical_run_id)
    )
    run_id = canonical_run_id or (checkpoint_run_id if isinstance(checkpoint_run_id, str) else "")
    stop_reason = str(checkpoint.get("stop_reason", "") or "unknown")
    run_config_path = run_root_path / "run_config.json" if run_root_path else None
    run_summary_path = run_root_path / "run_summary.json" if run_root_path else None
    previous_round_path = (
        run_root_path / f"round_{last_completed_round:02d}"
        if run_root_path and last_completed_round
        else None
    )
    previous_round_error: str | None = None
    if run_root_path is not None and run_root_error is None and not run_id_mismatch:
        run_artifact_paths = (
            run_config_path,
            run_summary_path,
            run_root_path / "round_metrics.json",
            run_root_path / "run_manifest.json",
        )
        if not resume_artifact_links_are_safe(
            parent_dir=run_root_path,
            paths=(path for path in run_artifact_paths if path is not None),
        ) or not resume_artifact_links_are_safe(
            parent_dir=project_dir,
            paths=(project_dir / "score_history.json",),
        ):
            previous_round_error = UNSAFE_ARTIFACT_PATH
    if previous_round_path is not None and run_root_error is None and previous_round_error is None:
        safe_previous_round, previous_round_error = validate_resume_round_dir(
            run_root=run_root_path,
            round_dir=previous_round_path,
        )
        if previous_round_error is None and safe_previous_round is not None:
            context_paths = [safe_previous_round / name for name in ROUND_OUTPUT_FILES]
            if not resume_artifact_links_are_safe(
                parent_dir=safe_previous_round,
                paths=context_paths,
            ):
                previous_round_error = UNSAFE_ARTIFACT_PATH
    next_round_path = (
        run_root_path / f"round_{next_round:02d}"
        if run_root_path
        and run_root_error is None
        and not run_id_mismatch
        and previous_round_error is None
        else None
    )
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
        "can_resume": checkpoint_can_resume,
        "best_score": _safe_float(checkpoint.get("best_score"), -1.0),
        "best_round": best_round,
        "best_round_path": (
            str(run_root_path / f"round_{best_round:02d}") if run_root_path and best_round else ""
        ),
        "last_successful_agent": str(checkpoint.get("last_successful_agent", "") or "none"),
        "completed_round_files_preserved": True,
        "next_round_path": str(next_round_path) if next_round_path else "",
        "next_round_display": next_round_info["display_path"],
        "next_round_dir_exists": next_round_info["exists"],
        "next_round_status": next_round_info["status"],
        "next_round_blocks_resume": next_round_info["blocks_resume"],
        "next_round_safety_action": next_round_info["safety_action"],
        "next_round_existing_files": next_round_info["existing_files"],
        "next_round_missing_expected_files": next_round_info["missing_expected_files"],
        "next_round_preserved_attempt_count": next_round_info.get("preserved_attempt_count", 0),
        "next_round_latest_verified_completed_stage": next_round_info.get(
            "latest_verified_completed_stage"
        ),
        "next_round_retained_attempt_bytes": next_round_info.get("retained_attempt_bytes", 0),
        "next_round_free_bytes": next_round_info.get("free_bytes"),
    }

    if not checkpoint_can_resume:
        preview.update(
            {
                "can_resume": False,
                "blocked_reason": "not_resume_eligible",
                "message": "checkpoint exists but can_resume is false",
            }
        )
        return preview
    if run_root_error:
        preview.update(
            {
                "can_resume": False,
                "blocked_reason": run_root_error,
                "message": RESUME_PATH_MESSAGES[run_root_error],
            }
        )
        return preview
    if run_id_mismatch:
        preview.update(
            {
                "can_resume": False,
                "blocked_reason": RUN_ID_MISMATCH,
                "message": RESUME_PATH_MESSAGES[RUN_ID_MISMATCH],
            }
        )
        return preview
    if previous_round_error:
        preview.update(
            {
                "can_resume": False,
                "blocked_reason": previous_round_error,
                "message": RESUME_PATH_MESSAGES[previous_round_error],
            }
        )
        return preview
    if next_round_info["blocks_resume"]:
        blocked_reason = next_round_info.get("blocked_reason")
        preview.update(
            {
                "can_resume": False,
                "blocked_reason": blocked_reason or "partial_next_round_exists",
                "message": next_round_info.get("message")
                or (
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


def _resume_block_outranks_mock(preview: Mapping[str, Any]) -> bool:
    """Transaction, conflict, and path blocks keep their own recovery guidance."""

    reason = preview.get("blocked_reason")
    if not isinstance(reason, str) or reason in {"", OFFLINE_MOCK_BLOCKED_REASON}:
        return False
    if reason in RESUME_PATH_MESSAGES or reason.startswith(_RESUME_BLOCK_PREFIXES):
        return True
    return bool(preview.get("next_round_blocks_resume")) and preview.get("can_resume") is False


def build_resume_preview(
    *,
    project_dir: Path,
    checkpoint: dict[str, Any],
    repo_root: Path | None = None,
    explicit_workspace: Path | None = None,
    source_layout: bool | None = None,
) -> dict[str, Any]:
    """Preview one resume, refusing ordinary continuation of an offline mock."""

    preview = _build_resume_preview(
        project_dir=project_dir,
        checkpoint=checkpoint,
        repo_root=repo_root,
    )
    if _resume_block_outranks_mock(preview):
        return preview
    block = offline_mock_resume_block(
        project_dir=project_dir,
        checkpoint=checkpoint,
        repo_root=repo_root,
        explicit_workspace=explicit_workspace,
        source_layout=source_layout,
    )
    if block is None:
        return preview
    refused = dict(preview)
    refused["can_resume"] = False
    refused["blocked_reason"] = OFFLINE_MOCK_BLOCKED_REASON
    refused["message"] = block["message"]
    refused["mock_restart_command"] = block["command"]
    return refused


def ordinary_resume_refusal(
    *,
    project_dir: Path,
    repo_root: Path | None = None,
    explicit_workspace: Path | None = None,
    source_layout: bool | None = None,
) -> str | None:
    """Stop ordinary resume before a provider operation when a mock is visible.

    A complete offline mock is refused without writing. An existing transaction,
    conflict, or path block keeps that block's guidance instead of suggesting a
    new mock on top of it. When the checkpoint does not yet show a mock, return
    None so in-lock recovery can run; call this again on the recovered checkpoint.
    """

    block = offline_mock_resume_block(
        project_dir=project_dir,
        repo_root=repo_root,
        explicit_workspace=explicit_workspace,
        source_layout=source_layout,
    )
    if block is None:
        return None
    checkpoint = read_json_file(project_dir / "checkpoint.json", anchor=project_dir)
    preview = build_resume_preview(
        project_dir=project_dir,
        checkpoint=checkpoint,
        repo_root=repo_root,
        explicit_workspace=explicit_workspace,
        source_layout=source_layout,
    )
    if _resume_block_outranks_mock(preview):
        message = preview.get("message")
        if isinstance(message, str) and message:
            return message
    return block["message"]


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
    git_root: GitRootSetting = INHERIT_GIT_ROOT,
    drafting_mode: str = DEFAULT_DRAFTING_MODE,
    max_consecutive_provider_quota_failures: int = 2,
    explicit_workspace: Path | None = None,
    source_layout: bool | None = None,
) -> bool:
    # Establish the project trust boundary before the first automatic artifact read.
    # ``build_resume_preview`` repeats this check so it remains safe as a public helper.
    ensure_project_runtime_paths_safe(project_dir)
    checkpoint_problem = checkpoint_read_problem(project_dir)
    if checkpoint_problem:
        console.print(f"[red]Cannot resume: {checkpoint_problem}.[/red]")
        return False
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
        return False
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
    try:
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
            git_root=git_root,
            drafting_mode=drafting_mode,
            max_consecutive_provider_quota_failures=max_consecutive_provider_quota_failures,
            resume_metadata=preview,
            explicit_workspace=explicit_workspace,
            source_layout=source_layout,
        )
        return True
    except ResumeHistoryError as exc:
        console.print(f"[red]Cannot resume safely: {exc}.[/red]")
        raise
    except OSError:
        message = "resume artifact I/O failed; verify project and run directory permissions"
        console.print(f"[red]Cannot resume safely: {message}.[/red]")
        raise ResumeHistoryError(message) from None
