"""Append-only partial-round attempt storage and recovery classification."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .storage import (
    artifact_path_exists,
    list_artifact_entry_names,
    list_artifact_regular_files,
    make_round_attempt_dir,
    read_regular_text,
    write_json_file,
    write_json_file_create_only,
    write_text_create_only,
)

ATTEMPT_SCHEMA_VERSION = 1
ATTEMPT_KIND = "partial_round_attempt"
MAX_ATTEMPTS_PER_ROUND = 32
MIN_FREE_BYTES_FOR_ATTEMPT = 16 * 1024 * 1024
MAX_RETAINED_ATTEMPT_BYTES_PER_ROUND = 256 * 1024 * 1024
ATTEMPT_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]{7,63}\Z")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
STOP_REASON_PATTERN = re.compile(r"[A-Z][A-Z0-9_]{0,63}\Z")
STAGE_OUTPUT_FILES = {
    "draft": "01_draft.md",
    "review": "02_review.md",
    "revise": "03_revised.md",
    "judge": "04_judge.md",
}
STAGE_ORDER = tuple(STAGE_OUTPUT_FILES)
ATTEMPT_STATES = {"active", "stopped", "ready_to_publish", "published", "unverifiable"}


class RoundAttemptBlockedError(RuntimeError):
    """Raised when recovery classification forbids allocating another attempt."""


@dataclass(frozen=True)
class AttemptInspection:
    attempt_id: str
    state: str
    completed_stages: tuple[str, ...]
    verified: bool
    reason: str | None = None
    created_at: str = ""


@dataclass(frozen=True)
class RoundRecoveryClassification:
    status: str
    can_create_attempt: bool
    safety_action: str
    preserved_attempt_count: int
    latest_verified_completed_stage: str | None
    blocked_reason: str | None
    retained_attempt_bytes: int = 0
    free_bytes: int | None = None
    attempts: tuple[AttemptInspection, ...] = ()


def _validate_attempt_id(attempt_id: str) -> str:
    if not isinstance(attempt_id, str) or ATTEMPT_ID_PATTERN.fullmatch(attempt_id) is None:
        raise ValueError("attempt_id must use 8-64 lowercase ASCII identifier characters")
    return attempt_id


def _validate_round_index(round_index: int) -> int:
    if (
        isinstance(round_index, bool)
        or not isinstance(round_index, int)
        or not 1 <= round_index <= 999999
    ):
        raise ValueError("round_index must be an integer between 1 and 999999")
    return round_index


def _aware_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _attempt_run_root(attempt_dir: Path) -> tuple[Path, str]:
    attempt_dir = Path(attempt_dir)
    if (
        not attempt_dir.name.startswith("attempt_")
        or attempt_dir.parent.parent.name != "partial_rounds"
        or re.fullmatch(r"round_\d{2,6}", attempt_dir.parent.name) is None
    ):
        raise ValueError("attempt directory does not use the managed partial-round layout")
    attempt_id = _validate_attempt_id(attempt_dir.name.removeprefix("attempt_"))
    return attempt_dir.parent.parent.parent, attempt_id


def create_round_attempt(
    *,
    run_root: Path,
    round_index: int,
    run_config_sha256: str,
    attempt_id: str | None = None,
    created_at: str | None = None,
    max_attempts: int = MAX_ATTEMPTS_PER_ROUND,
    min_free_bytes: int = MIN_FREE_BYTES_FOR_ATTEMPT,
    max_retained_bytes: int = MAX_RETAINED_ATTEMPT_BYTES_PER_ROUND,
) -> Path:
    """Allocate an attempt and create its initial manifest without overwriting evidence."""
    run_root = Path(run_root).expanduser().absolute()
    round_index = _validate_round_index(round_index)
    if SHA256_PATTERN.fullmatch(run_config_sha256) is None:
        raise ValueError("run_config_sha256 must be a lowercase SHA-256 digest")
    if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or max_attempts < 1:
        raise ValueError("max_attempts must be a positive integer")
    timestamp = created_at or datetime.now().astimezone().isoformat()
    if _aware_timestamp(timestamp) is None:
        raise ValueError("created_at must be a timezone-aware ISO-8601 timestamp")

    classification = classify_round_recovery(
        run_root,
        round_index,
        max_attempts=max_attempts,
        min_free_bytes=min_free_bytes,
        max_retained_bytes=max_retained_bytes,
    )
    if not classification.can_create_attempt:
        reason = classification.blocked_reason or classification.status
        raise RoundAttemptBlockedError(reason)

    selected_id = _validate_attempt_id(attempt_id or uuid.uuid4().hex)
    attempt_dir = make_round_attempt_dir(run_root, round_index, selected_id)
    manifest = {
        "schema_version": ATTEMPT_SCHEMA_VERSION,
        "kind": ATTEMPT_KIND,
        "run_id": Path(run_root).name,
        "round": round_index,
        "attempt_id": selected_id,
        "state": "active",
        "completed_stages": [],
        "last_successful_agent": None,
        "stop_reason": None,
        "created_at": timestamp,
        "updated_at": timestamp,
        "run_config_sha256": run_config_sha256,
        "outputs": {},
    }
    write_json_file_create_only(
        attempt_dir / "attempt.json",
        manifest,
    )
    return attempt_dir


def write_attempt_stage_output(attempt_dir: Path, stage: str, content: str) -> Path:
    """Create one normalized stage output inside an allocated attempt."""
    _attempt_run_root(attempt_dir)
    try:
        output_name = STAGE_OUTPUT_FILES[stage]
    except KeyError as exc:
        raise ValueError(f"unknown attempt stage: {stage}") from exc
    output_path = Path(attempt_dir) / "output" / output_name
    write_text_create_only(output_path, content)
    return output_path


def _transition_timestamp(value: str | None, *, not_before: str) -> str:
    timestamp = value or datetime.now().astimezone().isoformat()
    parsed = _aware_timestamp(timestamp)
    lower_bound = _aware_timestamp(not_before)
    if parsed is None or lower_bound is None:
        raise ValueError("updated_at must be a timezone-aware ISO-8601 timestamp")
    if parsed < lower_bound:
        raise ValueError("updated_at cannot move backwards")
    return timestamp


def _transition_manifest(attempt_dir: Path) -> tuple[Path, int, AttemptInspection, dict[str, Any]]:
    run_root, attempt_id = _attempt_run_root(attempt_dir)
    round_index = int(Path(attempt_dir).parent.name.removeprefix("round_"))
    inspection = _inspect_attempt(
        run_root=run_root,
        round_index=round_index,
        attempt_dir=Path(attempt_dir),
        attempt_id=attempt_id,
    )
    if not inspection.verified:
        raise RoundAttemptBlockedError(inspection.reason or "attempt is unverifiable")
    try:
        manifest = json.loads(read_regular_text(Path(attempt_dir) / "attempt.json"))
    except (OSError, UnicodeError, ValueError, RecursionError):
        raise RoundAttemptBlockedError("attempt manifest is unreadable") from None
    if not isinstance(manifest, dict):
        raise RoundAttemptBlockedError("attempt manifest is invalid")
    return run_root, round_index, inspection, manifest


def _write_transition_manifest(
    attempt_dir: Path,
    *,
    run_root: Path,
    round_index: int,
    manifest: dict[str, Any],
) -> None:
    write_json_file(Path(attempt_dir) / "attempt.json", manifest)
    attempt_id = Path(attempt_dir).name.removeprefix("attempt_")
    inspection = _inspect_attempt(
        run_root=run_root,
        round_index=round_index,
        attempt_dir=Path(attempt_dir),
        attempt_id=attempt_id,
    )
    if not inspection.verified:
        raise RoundAttemptBlockedError(inspection.reason or "attempt transition is unverifiable")


def persist_attempt_stage(
    attempt_dir: Path,
    stage: str,
    content: str,
    *,
    agent_succeeded: bool = True,
    updated_at: str | None = None,
) -> Path:
    """Create the next stage output and atomically record its digest in the manifest."""
    run_root, round_index, inspection, manifest = _transition_manifest(attempt_dir)
    if inspection.state != "active":
        raise RoundAttemptBlockedError(f"attempt state {inspection.state} is immutable")
    if not isinstance(agent_succeeded, bool):
        raise ValueError("agent_succeeded must be a boolean")
    if len(inspection.completed_stages) >= len(STAGE_ORDER):
        raise RoundAttemptBlockedError("all attempt stages are already persisted")
    expected_stage = STAGE_ORDER[len(inspection.completed_stages)]
    if stage != expected_stage:
        raise RoundAttemptBlockedError(f"expected {expected_stage} stage, received {stage}")
    transition_time = _transition_timestamp(
        updated_at,
        not_before=str(manifest["updated_at"]),
    )

    output_path = write_attempt_stage_output(attempt_dir, stage, content)
    output_bytes = read_regular_text(output_path).encode("utf-8")
    output_name = STAGE_OUTPUT_FILES[stage]
    completed_stages = [*inspection.completed_stages, stage]
    outputs = dict(manifest["outputs"])
    outputs[output_name] = {
        "size": len(output_bytes),
        "sha256": hashlib.sha256(output_bytes).hexdigest(),
    }
    manifest.update(
        {
            "completed_stages": completed_stages,
            "last_successful_agent": stage
            if agent_succeeded
            else manifest.get("last_successful_agent"),
            "updated_at": transition_time,
            "outputs": outputs,
        }
    )
    _write_transition_manifest(
        attempt_dir,
        run_root=run_root,
        round_index=round_index,
        manifest=manifest,
    )
    return output_path


def mark_attempt_stopped(
    attempt_dir: Path,
    stop_reason: str,
    *,
    updated_at: str | None = None,
) -> None:
    """Freeze an active attempt as immutable stopped evidence."""
    if not isinstance(stop_reason, str) or STOP_REASON_PATTERN.fullmatch(stop_reason) is None:
        raise ValueError("stop_reason must be a restricted uppercase identifier")
    run_root, round_index, inspection, manifest = _transition_manifest(attempt_dir)
    if inspection.state == "stopped" and manifest.get("stop_reason") == stop_reason:
        return
    if inspection.state != "active":
        raise RoundAttemptBlockedError(f"attempt state {inspection.state} cannot be stopped")
    manifest.update(
        {
            "state": "stopped",
            "stop_reason": stop_reason,
            "updated_at": _transition_timestamp(
                updated_at,
                not_before=str(manifest["updated_at"]),
            ),
        }
    )
    _write_transition_manifest(
        attempt_dir,
        run_root=run_root,
        round_index=round_index,
        manifest=manifest,
    )


def mark_attempt_ready_to_publish(
    attempt_dir: Path,
    *,
    updated_at: str | None = None,
) -> None:
    """Freeze a verified four-stage active attempt for canonical publication."""
    run_root, round_index, inspection, manifest = _transition_manifest(attempt_dir)
    if inspection.state == "ready_to_publish":
        return
    if inspection.state != "active":
        raise RoundAttemptBlockedError(
            f"attempt state {inspection.state} cannot become ready_to_publish"
        )
    if inspection.completed_stages != STAGE_ORDER:
        raise RoundAttemptBlockedError("ready_to_publish requires four completed stages")
    manifest.update(
        {
            "state": "ready_to_publish",
            "stop_reason": None,
            "updated_at": _transition_timestamp(
                updated_at,
                not_before=str(manifest["updated_at"]),
            ),
        }
    )
    _write_transition_manifest(
        attempt_dir,
        run_root=run_root,
        round_index=round_index,
        manifest=manifest,
    )


def _invalid_attempt(attempt_id: str, reason: str) -> AttemptInspection:
    return AttemptInspection(
        attempt_id=attempt_id,
        state="unverifiable",
        completed_stages=(),
        verified=False,
        reason=reason,
    )


def _inspect_attempt(
    *,
    run_root: Path,
    round_index: int,
    attempt_dir: Path,
    attempt_id: str,
) -> AttemptInspection:
    try:
        entry_names = list_artifact_entry_names(attempt_dir)
        if entry_names != ["attempt.json", "output"]:
            return _invalid_attempt(attempt_id, "unexpected_attempt_entries")
        manifest_text = read_regular_text(
            attempt_dir / "attempt.json",
        )
        manifest = json.loads(manifest_text)
        if not isinstance(manifest, dict):
            return _invalid_attempt(attempt_id, "invalid_manifest")
        output_names = list_artifact_entry_names(attempt_dir / "output")
    except (OSError, UnicodeError, ValueError, RecursionError):
        return _invalid_attempt(attempt_id, "unsafe_or_invalid_attempt")

    completed = manifest.get("completed_stages")
    if not isinstance(completed, list) or any(not isinstance(stage, str) for stage in completed):
        return _invalid_attempt(attempt_id, "invalid_completed_stages")
    completed_stages = tuple(completed)
    if completed_stages != STAGE_ORDER[: len(completed_stages)]:
        return _invalid_attempt(attempt_id, "non_prefix_completed_stages")

    state = manifest.get("state")
    created_at = _aware_timestamp(manifest.get("created_at"))
    updated_at = _aware_timestamp(manifest.get("updated_at"))
    if (
        manifest.get("schema_version") != ATTEMPT_SCHEMA_VERSION
        or isinstance(manifest.get("schema_version"), bool)
        or manifest.get("kind") != ATTEMPT_KIND
        or manifest.get("run_id") != run_root.name
        or manifest.get("round") != round_index
        or isinstance(manifest.get("round"), bool)
        or manifest.get("attempt_id") != attempt_id
        or not isinstance(state, str)
        or state not in ATTEMPT_STATES
        or created_at is None
        or updated_at is None
        or updated_at < created_at
        or not isinstance(manifest.get("run_config_sha256"), str)
        or SHA256_PATTERN.fullmatch(manifest["run_config_sha256"]) is None
    ):
        return _invalid_attempt(attempt_id, "manifest_identity_or_schema_mismatch")

    last_successful_agent = manifest.get("last_successful_agent")
    if last_successful_agent is not None and last_successful_agent not in completed_stages:
        return _invalid_attempt(attempt_id, "last_agent_mismatch")
    stop_reason = manifest.get("stop_reason")
    if state == "stopped":
        if not isinstance(stop_reason, str) or STOP_REASON_PATTERN.fullmatch(stop_reason) is None:
            return _invalid_attempt(attempt_id, "invalid_stop_reason")
    elif state == "active" and stop_reason is not None:
        return _invalid_attempt(attempt_id, "active_attempt_has_stop_reason")

    outputs = manifest.get("outputs")
    if not isinstance(outputs, dict):
        return _invalid_attempt(attempt_id, "invalid_outputs")
    expected_output_names = [STAGE_OUTPUT_FILES[stage] for stage in completed_stages]
    if sorted(outputs) != sorted(expected_output_names) or output_names != sorted(
        expected_output_names
    ):
        return _invalid_attempt(attempt_id, "output_manifest_mismatch")

    for output_name in expected_output_names:
        metadata = outputs.get(output_name)
        if not isinstance(metadata, dict):
            return _invalid_attempt(attempt_id, "invalid_output_metadata")
        expected_size = metadata.get("size")
        expected_digest = metadata.get("sha256")
        if (
            isinstance(expected_size, bool)
            or not isinstance(expected_size, int)
            or expected_size < 0
            or not isinstance(expected_digest, str)
            or SHA256_PATTERN.fullmatch(expected_digest) is None
        ):
            return _invalid_attempt(attempt_id, "invalid_output_metadata")
        try:
            content = read_regular_text(
                attempt_dir / "output" / output_name,
            ).encode("utf-8")
        except (OSError, UnicodeError):
            return _invalid_attempt(attempt_id, "unsafe_output")
        if len(content) != expected_size or hashlib.sha256(content).hexdigest() != expected_digest:
            return _invalid_attempt(attempt_id, "output_hash_mismatch")

    return AttemptInspection(
        attempt_id=attempt_id,
        state=state,
        completed_stages=completed_stages,
        verified=True,
        created_at=manifest["created_at"],
    )


def _classification(
    *,
    status: str,
    can_create: bool,
    action: str,
    attempts: tuple[AttemptInspection, ...] = (),
    blocked_reason: str | None = None,
    retained_attempt_bytes: int = 0,
    free_bytes: int | None = None,
) -> RoundRecoveryClassification:
    verified_attempts = [attempt for attempt in attempts if attempt.verified]
    latest = max(
        verified_attempts,
        key=lambda attempt: (_aware_timestamp(attempt.created_at), attempt.attempt_id),
        default=None,
    )
    latest_stage = latest.completed_stages[-1] if latest and latest.completed_stages else None
    return RoundRecoveryClassification(
        status=status,
        can_create_attempt=can_create,
        safety_action=action,
        preserved_attempt_count=len(attempts),
        latest_verified_completed_stage=latest_stage,
        blocked_reason=blocked_reason,
        retained_attempt_bytes=retained_attempt_bytes,
        free_bytes=free_bytes,
        attempts=attempts,
    )


def _retained_attempt_bytes(run_root: Path, round_index: int) -> int:
    attempts_root = run_root / "partial_rounds" / f"round_{round_index:02d}"
    if not artifact_path_exists(attempts_root, allow_directory=True):
        return 0
    total = 0
    for path in list_artifact_regular_files(attempts_root):
        total += len(read_regular_text(path).encode("utf-8"))
    return total


def _eligible_classification(
    *,
    run_root: Path,
    round_index: int,
    status: str,
    action: str,
    attempts: tuple[AttemptInspection, ...],
    min_free_bytes: int,
    max_retained_bytes: int,
) -> RoundRecoveryClassification:
    try:
        retained_bytes = _retained_attempt_bytes(run_root, round_index)
        free_bytes = int(shutil.disk_usage(run_root).free)
    except (OSError, UnicodeError, ValueError):
        return _classification(
            status="disk_space_unavailable",
            can_create=False,
            action="fail_safe_require_user_action",
            attempts=attempts,
            blocked_reason="disk_space_unavailable",
        )
    if retained_bytes > max_retained_bytes:
        return _classification(
            status="retained_attempt_budget_exceeded",
            can_create=False,
            action="archive_attempts_before_retry",
            attempts=attempts,
            blocked_reason="retained_attempt_budget_exceeded",
            retained_attempt_bytes=retained_bytes,
            free_bytes=free_bytes,
        )
    if free_bytes < min_free_bytes:
        return _classification(
            status="insufficient_disk_space",
            can_create=False,
            action="free_disk_space_before_retry",
            attempts=attempts,
            blocked_reason="insufficient_disk_space",
            retained_attempt_bytes=retained_bytes,
            free_bytes=free_bytes,
        )
    return _classification(
        status=status,
        can_create=True,
        action=action,
        attempts=attempts,
        retained_attempt_bytes=retained_bytes,
        free_bytes=free_bytes,
    )


def classify_round_recovery(
    run_root: Path,
    round_index: int,
    *,
    max_attempts: int = MAX_ATTEMPTS_PER_ROUND,
    min_free_bytes: int = MIN_FREE_BYTES_FOR_ATTEMPT,
    max_retained_bytes: int = MAX_RETAINED_ATTEMPT_BYTES_PER_ROUND,
) -> RoundRecoveryClassification:
    """Classify whether a fresh append-only attempt may be allocated for one round."""
    run_root = Path(run_root).expanduser().absolute()
    round_index = _validate_round_index(round_index)
    if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or max_attempts < 1:
        raise ValueError("max_attempts must be a positive integer")
    if (
        isinstance(min_free_bytes, bool)
        or not isinstance(min_free_bytes, int)
        or min_free_bytes < 0
    ):
        raise ValueError("min_free_bytes must be a non-negative integer")
    if (
        isinstance(max_retained_bytes, bool)
        or not isinstance(max_retained_bytes, int)
        or max_retained_bytes < 0
    ):
        raise ValueError("max_retained_bytes must be a non-negative integer")
    canonical = run_root / f"round_{round_index:02d}"
    attempts_root = run_root / "partial_rounds" / f"round_{round_index:02d}"

    try:
        canonical_names = list_artifact_entry_names(canonical, missing_ok=True)
        canonical_exists = artifact_path_exists(
            canonical,
            allow_directory=True,
        )
        attempt_names = list_artifact_entry_names(attempts_root, missing_ok=True)
        attempts_root_exists = artifact_path_exists(
            attempts_root,
            allow_directory=True,
        )
    except OSError:
        return _classification(
            status="unsafe_round_state",
            can_create=False,
            action="fail_safe_require_user_action",
            blocked_reason="unsafe_round_state",
        )

    if canonical_exists and attempts_root_exists and attempt_names:
        return _classification(
            status="canonical_attempt_conflict",
            can_create=False,
            action="preserve_conflicting_evidence",
            blocked_reason="canonical_attempt_conflict",
        )
    if canonical_exists:
        return _classification(
            status="legacy_empty_canonical" if not canonical_names else "legacy_partial",
            can_create=False,
            action=(
                "preserve_existing_empty_canonical"
                if not canonical_names
                else "explicit_migration_required"
            ),
            blocked_reason="canonical_round_exists",
        )
    if len(attempt_names) >= max_attempts:
        return _classification(
            status="attempt_limit_reached",
            can_create=False,
            action="archive_attempts_before_retry",
            blocked_reason="attempt_limit_reached",
        )
    if not attempt_names:
        return _eligible_classification(
            run_root=run_root,
            round_index=round_index,
            status="new_round",
            action="create_new_attempt",
            attempts=(),
            min_free_bytes=min_free_bytes,
            max_retained_bytes=max_retained_bytes,
        )

    parsed_names: list[tuple[str, str]] = []
    for entry_name in attempt_names:
        if not entry_name.startswith("attempt_"):
            return _classification(
                status="attempt_unverifiable",
                can_create=False,
                action="preserve_and_inspect_attempts",
                blocked_reason="unverifiable_attempt",
            )
        attempt_id = entry_name.removeprefix("attempt_")
        try:
            _validate_attempt_id(attempt_id)
        except ValueError:
            return _classification(
                status="attempt_unverifiable",
                can_create=False,
                action="preserve_and_inspect_attempts",
                blocked_reason="unverifiable_attempt",
            )
        parsed_names.append((entry_name, attempt_id))

    attempts = tuple(
        _inspect_attempt(
            run_root=run_root,
            round_index=round_index,
            attempt_dir=attempts_root / entry_name,
            attempt_id=attempt_id,
        )
        for entry_name, attempt_id in parsed_names
    )
    if any(not attempt.verified or attempt.state == "unverifiable" for attempt in attempts):
        return _classification(
            status="attempt_unverifiable",
            can_create=False,
            action="preserve_and_inspect_attempts",
            attempts=attempts,
            blocked_reason="unverifiable_attempt",
        )
    if any(attempt.state == "active" for attempt in attempts):
        return _classification(
            status="attempt_in_progress",
            can_create=False,
            action="verify_run_lock_before_retry",
            attempts=attempts,
            blocked_reason="active_attempt_exists",
        )
    if any(attempt.state in {"ready_to_publish", "published"} for attempt in attempts):
        return _classification(
            status="publication_pending",
            can_create=False,
            action="reconcile_publication_before_retry",
            attempts=attempts,
            blocked_reason="publication_pending",
        )
    return _eligible_classification(
        run_root=run_root,
        round_index=round_index,
        status="staged_partial",
        action="retry_round_preserve_attempt",
        attempts=attempts,
        min_free_bytes=min_free_bytes,
        max_retained_bytes=max_retained_bytes,
    )
