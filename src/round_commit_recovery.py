"""Provider-free prepare, classification, and recovery for round commits.

The iterative runner uses this engine for new and fully evidenced histories.
Legacy histories without a complete pair retain their pre-transaction compatibility
path because their missing before-generation cannot be reconstructed safely.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import stat
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .resume_safety import validate_project_run_root
from .round_attempts import (
    STAGE_ORDER,
    classify_round_recovery,
    mark_attempt_ready_to_publish,
    publish_attempt,
)
from .round_commit import (
    MAX_ROUND_COMMIT_JOURNAL_BYTES,
    ROUND_COMMIT_ARTIFACT_NAMES,
    RUN_FINALIZE_ARTIFACT_NAMES,
    AfterImage,
    RoundCommitCodecError,
    build_best_output_after_image,
    build_history_after_image,
    decode_round_commit_journal,
    decode_run_finalize_journal,
    encode_round_commit_journal,
    encode_run_finalize_journal,
)
from .storage import (
    artifact_path_exists,
    ensure_artifact_paths_safe,
    ensure_project_runtime_paths_safe,
    read_regular_text_bounded,
    unlink_artifact_file_if_matches,
    write_file_text,
    write_file_text_create_only,
)

ROUND_COMMIT_JOURNAL_NAME = ".round_commit_transaction.json"
RUN_FINALIZE_JOURNAL_NAME = ".run_finalize_transaction.json"
MAX_ROUND_COMMIT_ARTIFACT_BYTES = 64 * 1024 * 1024
MAX_ROUND_COMMIT_METADATA_BYTES = 2 * 1024 * 1024
_EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


class RoundCommitRecoveryError(RuntimeError):
    """A path-redacted, fail-closed round-commit blocker."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class RoundCommitRecoveryIOError(OSError):
    """A path-redacted round-commit filesystem failure."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class RoundCommitReadError(RuntimeError):
    """A fixed, path-redacted blocker for mixed-generation readers."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class RoundCommitRecoveryInspection:
    status: str
    can_recover: bool
    journal_present: bool
    transaction_id: str | None = None
    run_id: str | None = None
    round_index: int | None = None
    attempt_state: str | None = None
    artifact_states: tuple[tuple[str, str], ...] = ()
    blocked_reason: str | None = None


@dataclass(frozen=True)
class _Generation:
    present: bool
    sha256: str | None
    text: str | None


@dataclass(frozen=True)
class _RoundCommitContext:
    project_dir: Path
    run_root: Path
    attempt_dir: Path
    journal_path: Path
    journal_text: str
    payload: dict[str, object]
    attempt_state: str


@dataclass(frozen=True)
class _RunFinalizeContext:
    project_dir: Path
    run_root: Path
    journal_path: Path
    journal_text: str
    payload: dict[str, object]


def _blocked(code: str) -> RoundCommitRecoveryError:
    return RoundCommitRecoveryError(code)


def _sha256_text(text: str) -> str:
    try:
        content = text.encode("utf-8")
    except UnicodeError:
        raise _blocked("artifact_invalid_utf8") from None
    return hashlib.sha256(content).hexdigest()


def _project_context(project_dir: Path) -> tuple[Path, Path]:
    try:
        project_dir = Path(project_dir).expanduser().absolute()
        project_anchor = project_dir.parent
        ensure_project_runtime_paths_safe(project_dir, anchor=project_anchor)
        ensure_artifact_paths_safe(
            [
                project_dir / ROUND_COMMIT_JOURNAL_NAME,
                project_dir / RUN_FINALIZE_JOURNAL_NAME,
            ],
            anchor=project_dir,
        )
    except (OSError, RuntimeError, ValueError):
        raise _blocked("project_runtime_unsafe") from None
    return project_dir, project_anchor


def _journal_exists(path: Path, *, anchor: Path) -> bool:
    try:
        ensure_artifact_paths_safe([path], anchor=anchor)
        return artifact_path_exists(path, anchor=anchor)
    except (OSError, RuntimeError, ValueError):
        raise _blocked("round_commit_journal_unsafe") from None


def _run_root_identity(project_dir: Path, run_root: Path) -> dict[str, object]:
    try:
        configured_runs = project_dir / "runs"
        configured_storage = configured_runs.is_symlink()
        metadata = os.stat(run_root, follow_symlinks=False)
        if not stat.S_ISDIR(metadata.st_mode):
            raise OSError("run root is not a directory")
        device = getattr(metadata, "st_dev", None)
        inode = getattr(metadata, "st_ino", None)
        identity_available = (
            os.name != "nt"
            and type(device) is int
            and device >= 0
            and type(inode) is int
            and inode > 0
        )
    except (OSError, RuntimeError, ValueError):
        raise _blocked("run_root_identity_unavailable") from None
    return {
        "configured_storage": configured_storage,
        "device": device if identity_available else None,
        "inode": inode if identity_available else None,
        "stat_identity_available": identity_available,
    }


def _validated_run_root(
    *,
    project_dir: Path,
    run_root_value: object,
    expected_run_id: str | None = None,
    expected_identity: object | None = None,
) -> Path:
    run_root, blocker = validate_project_run_root(
        project_dir=project_dir,
        run_root_value=run_root_value,
        require_writable=True,
    )
    if blocker is not None or run_root is None:
        raise _blocked("run_root_invalid")
    if str(run_root) != str(run_root_value):
        raise _blocked("run_root_not_canonical")
    if expected_run_id is not None and run_root.name != expected_run_id:
        raise _blocked("run_id_mismatch")
    identity = _run_root_identity(project_dir, run_root)
    if expected_identity is not None and identity != expected_identity:
        raise _blocked("run_root_identity_changed")
    return run_root


def _read_generation(path: Path, *, anchor: Path) -> _Generation:
    try:
        ensure_artifact_paths_safe([path], anchor=anchor)
        present = artifact_path_exists(path, anchor=anchor)
        if not present:
            return _Generation(present=False, sha256=None, text=None)
        text = read_regular_text_bounded(
            path,
            max_bytes=MAX_ROUND_COMMIT_ARTIFACT_BYTES,
            anchor=anchor,
        )
    except (OSError, UnicodeError, RuntimeError, ValueError):
        raise _blocked("artifact_unsafe") from None
    return _Generation(present=True, sha256=_sha256_text(text), text=text)


def _strict_json(text: str, *, code: str) -> object:
    def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ValueError(value)

    try:
        return json.loads(
            text,
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except (ValueError, RecursionError):
        raise _blocked(code) from None


def _validated_after_image(image: object, *, kind: str) -> AfterImage:
    if not isinstance(image, AfterImage):
        raise _blocked(f"{kind}_after_image_invalid")
    if not isinstance(image.text, str) or not isinstance(image.sha256, str):
        raise _blocked(f"{kind}_after_image_invalid")
    if _sha256_text(image.text) != image.sha256:
        raise _blocked(f"{kind}_after_image_digest_mismatch")
    if kind == "memory":
        if image.value != image.text:
            raise _blocked("memory_after_image_invalid")
        return image
    if not isinstance(image.value, dict):
        raise _blocked(f"{kind}_after_image_invalid")
    try:
        expected_text = json.dumps(image.value, indent=2, allow_nan=False)
    except (TypeError, ValueError, RecursionError):
        raise _blocked(f"{kind}_after_image_invalid") from None
    if image.text != expected_text:
        raise _blocked(f"{kind}_after_image_text_mismatch")
    return image


def _artifact_paths(
    *,
    project_dir: Path,
    run_root: Path,
) -> dict[str, tuple[Path, Path]]:
    return {
        "score_history": (project_dir / "score_history.json", project_dir),
        "round_metrics": (run_root / "round_metrics.json", run_root),
        "best_output": (project_dir / "best_output.md", project_dir),
        "memory": (project_dir / "memory.md", project_dir),
        "research_state": (project_dir / "research_state.json", project_dir),
        "checkpoint": (project_dir / "checkpoint.json", project_dir),
    }


def _attempt_context(
    *,
    run_root: Path,
    round_index: int,
    attempt_id: str,
    run_config_sha256: str,
) -> tuple[Path, str]:
    attempt_dir = run_root / "partial_rounds" / f"round_{round_index:02d}" / f"attempt_{attempt_id}"
    manifest_path = attempt_dir / "attempt.json"
    try:
        manifest_text = read_regular_text_bounded(
            manifest_path,
            max_bytes=MAX_ROUND_COMMIT_METADATA_BYTES,
            anchor=run_root,
        )
    except (OSError, UnicodeError, RuntimeError, ValueError):
        raise _blocked("attempt_manifest_unsafe") from None
    manifest = _strict_json(manifest_text, code="attempt_manifest_invalid")
    if (
        not isinstance(manifest, dict)
        or manifest.get("attempt_id") != attempt_id
        or manifest.get("round") != round_index
        or isinstance(manifest.get("round"), bool)
        or manifest.get("run_id") != run_root.name
        or manifest.get("run_config_sha256") != run_config_sha256
    ):
        raise _blocked("attempt_identity_mismatch")

    classification = classify_round_recovery(run_root, round_index)
    matches = [attempt for attempt in classification.attempts if attempt.attempt_id == attempt_id]
    if len(matches) != 1 or not matches[0].verified:
        raise _blocked("attempt_unverifiable")
    target = matches[0]
    if target.completed_stages != STAGE_ORDER:
        raise _blocked("attempt_incomplete")
    expected_status = {
        "active": "attempt_in_progress",
        "ready_to_publish": "publication_pending",
        "published": "published_uncommitted",
    }.get(target.state)
    if expected_status is None or classification.status != expected_status:
        raise _blocked("attempt_state_conflict")
    return attempt_dir, target.state


def _run_config_digest(run_root: Path) -> str:
    try:
        text = read_regular_text_bounded(
            run_root / "run_config.json",
            max_bytes=MAX_ROUND_COMMIT_METADATA_BYTES,
            anchor=run_root,
        )
    except (OSError, UnicodeError, RuntimeError, ValueError):
        raise _blocked("run_config_unsafe") from None
    return _sha256_text(text)


def _before_record(generation: _Generation) -> dict[str, object]:
    return {
        "before_present": generation.present,
        "before_sha256": generation.sha256,
    }


def _run_finalize_artifact_paths(
    *,
    project_dir: Path,
    run_root: Path,
) -> dict[str, tuple[Path, Path]]:
    return {
        "run_summary": (run_root / "run_summary.json", run_root),
        "run_config": (run_root / "run_config.json", run_root),
        "checkpoint": (project_dir / "checkpoint.json", project_dir),
    }


def _finalization_round(value: Mapping[str, object], field: str) -> int:
    round_value = value.get(field)
    if isinstance(round_value, bool) or not isinstance(round_value, int) or round_value < 0:
        raise _blocked("run_finalize_after_image_mismatch")
    return round_value


def _validate_run_finalize_after_images(
    *,
    project_dir: Path,
    run_root: Path,
    run_summary_after: AfterImage,
    run_config_after: AfterImage,
    checkpoint_after: AfterImage,
) -> tuple[AfterImage, AfterImage, AfterImage]:
    summary = _validated_after_image(run_summary_after, kind="run_summary")
    config = _validated_after_image(run_config_after, kind="run_config")
    checkpoint = _validated_after_image(checkpoint_after, kind="checkpoint")
    values = (summary.value, config.value, checkpoint.value)
    if not all(isinstance(value, dict) for value in values):
        raise _blocked("run_finalize_after_image_mismatch")
    summary_value, config_value, checkpoint_value = values
    assert isinstance(summary_value, dict)
    assert isinstance(config_value, dict)
    assert isinstance(checkpoint_value, dict)

    for value in values:
        if value.get("run_id") != run_root.name:
            raise _blocked("run_finalize_after_image_mismatch")
        candidate_root, blocker = validate_project_run_root(
            project_dir=project_dir,
            run_root_value=value.get("run_root"),
            require_writable=True,
        )
        if blocker is not None or candidate_root != run_root:
            raise _blocked("run_finalize_after_image_mismatch")

    completed_rounds = _finalization_round(summary_value, "completed_rounds")
    if (
        _finalization_round(config_value, "completed_rounds") != completed_rounds
        or _finalization_round(checkpoint_value, "last_completed_round") != completed_rounds
        or config_value.get("status") != "completed"
    ):
        raise _blocked("run_finalize_after_image_mismatch")
    common_fields = ("stop_reason", "can_resume", "best_round", "best_score")
    for field in common_fields:
        expected = summary_value.get(field)
        if config_value.get(field) != expected or checkpoint_value.get(field) != expected:
            raise _blocked("run_finalize_after_image_mismatch")
    if summary_value.get("resume_metadata") != checkpoint_value.get("resume_metadata"):
        raise _blocked("run_finalize_after_image_mismatch")
    config_resume = config_value.get("resume_metadata")
    checkpoint_resume = checkpoint_value.get("resume_metadata")
    if not isinstance(config_resume, dict) or not isinstance(checkpoint_resume, dict):
        raise _blocked("run_finalize_after_image_mismatch")
    for field in ("can_resume", "last_completed_round", "next_round", "stop_reason"):
        if config_resume.get(field) != checkpoint_resume.get(field):
            raise _blocked("run_finalize_after_image_mismatch")
    ended_at = config_value.get("ended_at")
    if (
        not isinstance(ended_at, str)
        or not ended_at
        or config_value.get("updated_at") != ended_at
        or checkpoint_value.get("updated_at") != ended_at
    ):
        raise _blocked("run_finalize_after_image_mismatch")
    return summary, config, checkpoint


def prepare_run_finalize(
    *,
    project_dir: Path,
    run_root: Path,
    run_summary_after: AfterImage,
    run_config_after: AfterImage,
    checkpoint_after: AfterImage,
    transaction_id: str | None = None,
) -> dict[str, object]:
    """Create and reopen the immutable finalization journal before final writes."""
    project_dir, _ = _project_context(project_dir)
    round_journal_path = project_dir / ROUND_COMMIT_JOURNAL_NAME
    journal_path = project_dir / RUN_FINALIZE_JOURNAL_NAME
    if _journal_exists(round_journal_path, anchor=project_dir):
        raise _blocked("round_commit_journal_present")
    if _journal_exists(journal_path, anchor=project_dir):
        raise _blocked("run_finalize_journal_exists")
    run_root = _validated_run_root(
        project_dir=project_dir,
        run_root_value=str(Path(run_root).expanduser().resolve(strict=False)),
    )
    summary, config, checkpoint = _validate_run_finalize_after_images(
        project_dir=project_dir,
        run_root=run_root,
        run_summary_after=run_summary_after,
        run_config_after=run_config_after,
        checkpoint_after=checkpoint_after,
    )
    paths = _run_finalize_artifact_paths(project_dir=project_dir, run_root=run_root)
    generations = {
        name: _read_generation(path, anchor=anchor) for name, (path, anchor) in paths.items()
    }
    images = {
        "run_summary": summary,
        "run_config": config,
        "checkpoint": checkpoint,
    }
    payload: dict[str, object] = {
        "schema_version": 1,
        "kind": "run_finalize",
        "state": "prepared",
        "transaction_id": transaction_id or f"finalize_{uuid.uuid4().hex}",
        "run_id": run_root.name,
        "run_root": str(run_root),
        "run_root_identity": _run_root_identity(project_dir, run_root),
        "artifacts": {
            name: {
                **_before_record(generations[name]),
                "after_sha256": images[name].sha256,
                "after_value": copy.deepcopy(images[name].value),
            }
            for name in RUN_FINALIZE_ARTIFACT_NAMES
        },
    }
    try:
        journal_text = encode_run_finalize_journal(payload)
    except RoundCommitCodecError:
        raise _blocked("run_finalize_journal_invalid") from None
    try:
        write_file_text_create_only(journal_path, journal_text, anchor=project_dir)
    except FileExistsError:
        raise _blocked("run_finalize_journal_exists") from None
    except OSError:
        raise RoundCommitRecoveryIOError("run_finalize_journal_create_failed") from None
    try:
        reopened_text = read_regular_text_bounded(
            journal_path,
            max_bytes=MAX_ROUND_COMMIT_JOURNAL_BYTES,
            anchor=project_dir,
        )
        reopened = decode_run_finalize_journal(reopened_text)
    except (OSError, UnicodeError, ValueError, RoundCommitCodecError):
        raise _blocked("run_finalize_journal_reopen_failed") from None
    if reopened_text != journal_text or reopened != payload:
        raise _blocked("run_finalize_journal_reopen_mismatch")
    return copy.deepcopy(payload)


def _history_after_image(
    generation: _Generation,
    *,
    round_metric: Mapping[str, object],
    round_index: int,
) -> AfterImage:
    if round_index == 1:
        history: list[dict[str, object]] = []
    else:
        if not generation.present or generation.text is None:
            raise _blocked("history_before_missing")
        value = _strict_json(generation.text, code="history_before_invalid")
        if not isinstance(value, list):
            raise _blocked("history_before_invalid")
        history = value
    try:
        return build_history_after_image(
            history,
            round_metric,
            round_index=round_index,
        )
    except RoundCommitCodecError:
        raise _blocked("history_before_invalid") from None


def _validate_checkpoint_before(
    generation: _Generation,
    *,
    project_dir: Path,
    round_index: int,
    run_root: Path,
) -> None:
    if round_index == 1:
        return
    if not generation.present or generation.text is None:
        raise _blocked("checkpoint_before_missing")
    value = _strict_json(generation.text, code="checkpoint_before_invalid")
    checkpoint_run_root = value.get("run_root") if isinstance(value, dict) else None
    canonical_checkpoint_root, checkpoint_root_blocker = validate_project_run_root(
        project_dir=project_dir,
        run_root_value=checkpoint_run_root,
        require_writable=True,
    )
    checkpoint_run_root_matches = (
        checkpoint_root_blocker is None and canonical_checkpoint_root == run_root
    )
    if (
        not isinstance(value, dict)
        or value.get("run_id") != run_root.name
        or not checkpoint_run_root_matches
        or value.get("last_completed_round") != round_index - 1
        or isinstance(value.get("last_completed_round"), bool)
    ):
        raise _blocked("checkpoint_before_mismatch")


def _validate_checkpoint_after(
    image: AfterImage,
    *,
    project_dir: Path,
    round_index: int,
    run_root: Path,
) -> None:
    value = image.value
    checkpoint_run_root = value.get("run_root") if isinstance(value, dict) else None
    canonical_checkpoint_root, checkpoint_root_blocker = validate_project_run_root(
        project_dir=project_dir,
        run_root_value=checkpoint_run_root,
        require_writable=True,
    )
    checkpoint_run_root_matches = (
        checkpoint_root_blocker is None and canonical_checkpoint_root == run_root
    )
    if (
        not isinstance(value, dict)
        or value.get("run_id") != run_root.name
        or not checkpoint_run_root_matches
        or value.get("last_completed_round") != round_index
        or isinstance(value.get("last_completed_round"), bool)
    ):
        raise _blocked("checkpoint_after_mismatch")


def _validate_research_state_after(
    image: AfterImage,
    *,
    round_index: int,
) -> None:
    value = image.value
    if (
        not isinstance(value, dict)
        or value.get("round") != round_index
        or isinstance(value.get("round"), bool)
    ):
        raise _blocked("research_state_after_mismatch")


def prepare_round_commit(
    *,
    project_dir: Path,
    run_root: Path,
    attempt_dir: Path,
    round_metric: Mapping[str, object],
    best_output_write: bool,
    memory_after: AfterImage,
    research_state_after: AfterImage,
    checkpoint_after: AfterImage,
    transaction_id: str | None = None,
) -> dict[str, object]:
    """Create and reopen one immutable prepared journal before publication."""
    project_dir, _ = _project_context(project_dir)
    journal_path = project_dir / ROUND_COMMIT_JOURNAL_NAME
    finalization_path = project_dir / RUN_FINALIZE_JOURNAL_NAME
    if _journal_exists(finalization_path, anchor=project_dir):
        raise _blocked("finalization_journal_present")
    if _journal_exists(journal_path, anchor=project_dir):
        raise _blocked("round_commit_journal_exists")

    run_root = _validated_run_root(
        project_dir=project_dir,
        run_root_value=str(Path(run_root).expanduser().resolve(strict=False)),
    )
    run_config_sha256 = _run_config_digest(run_root)
    if not isinstance(round_metric, dict):
        raise _blocked("round_metric_invalid")
    round_index = round_metric.get("round")
    if isinstance(round_index, bool) or not isinstance(round_index, int):
        raise _blocked("round_metric_invalid")
    attempt_id = Path(attempt_dir).name.removeprefix("attempt_")
    expected_attempt_dir, attempt_state = _attempt_context(
        run_root=run_root,
        round_index=round_index,
        attempt_id=attempt_id,
        run_config_sha256=run_config_sha256,
    )
    try:
        received_attempt_dir = Path(attempt_dir).expanduser().resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        raise _blocked("attempt_path_invalid") from None
    if received_attempt_dir != expected_attempt_dir.resolve(strict=True):
        raise _blocked("attempt_path_mismatch")
    if attempt_state != "active":
        raise _blocked("attempt_not_active")

    memory_after = _validated_after_image(memory_after, kind="memory")
    research_state_after = _validated_after_image(
        research_state_after,
        kind="research_state",
    )
    checkpoint_after = _validated_after_image(
        checkpoint_after,
        kind="checkpoint",
    )
    _validate_research_state_after(
        research_state_after,
        round_index=round_index,
    )
    _validate_checkpoint_after(
        checkpoint_after,
        project_dir=project_dir,
        round_index=round_index,
        run_root=run_root,
    )
    improved = round_metric.get("improved")
    if type(best_output_write) is not bool or type(improved) is not bool:
        raise _blocked("best_output_write_invalid")
    if best_output_write != improved:
        raise _blocked("best_output_write_mismatch")

    paths = _artifact_paths(project_dir=project_dir, run_root=run_root)
    generations = {
        name: _read_generation(path, anchor=anchor) for name, (path, anchor) in paths.items()
    }
    _validate_checkpoint_before(
        generations["checkpoint"],
        project_dir=project_dir,
        round_index=round_index,
        run_root=run_root,
    )
    score_after = _history_after_image(
        generations["score_history"],
        round_metric=round_metric,
        round_index=round_index,
    )
    metrics_after = _history_after_image(
        generations["round_metrics"],
        round_metric=round_metric,
        round_index=round_index,
    )
    if score_after.value != metrics_after.value:
        raise _blocked("history_before_mismatch")

    if best_output_write:
        try:
            revised_output = read_regular_text_bounded(
                expected_attempt_dir / "output" / "03_revised.md",
                max_bytes=MAX_ROUND_COMMIT_ARTIFACT_BYTES,
                anchor=run_root,
            )
        except (OSError, UnicodeError, RuntimeError, ValueError):
            raise _blocked("revised_output_unsafe") from None
        best_after_sha256 = build_best_output_after_image(revised_output).sha256
    else:
        best_before = generations["best_output"]
        best_after_sha256 = best_before.sha256 if best_before.present else _EMPTY_SHA256

    selected_transaction_id = transaction_id or f"txn_{uuid.uuid4().hex}"
    payload: dict[str, object] = {
        "schema_version": 1,
        "kind": "round_commit",
        "state": "prepared",
        "transaction_id": selected_transaction_id,
        "run_id": run_root.name,
        "run_root": str(run_root),
        "run_root_identity": _run_root_identity(project_dir, run_root),
        "round": round_index,
        "attempt_id": attempt_id,
        "run_config_sha256": run_config_sha256,
        "round_metric": copy.deepcopy(round_metric),
        "artifacts": {
            "score_history": {
                **_before_record(generations["score_history"]),
                "after_sha256": score_after.sha256,
            },
            "round_metrics": {
                **_before_record(generations["round_metrics"]),
                "after_sha256": metrics_after.sha256,
            },
            "best_output": {
                "write": best_output_write,
                **_before_record(generations["best_output"]),
                "after_sha256": best_after_sha256,
            },
            "memory": {
                **_before_record(generations["memory"]),
                "after_sha256": memory_after.sha256,
                "after_text": memory_after.text,
            },
            "research_state": {
                **_before_record(generations["research_state"]),
                "after_sha256": research_state_after.sha256,
                "after_value": copy.deepcopy(research_state_after.value),
            },
            "checkpoint": {
                **_before_record(generations["checkpoint"]),
                "after_sha256": checkpoint_after.sha256,
                "after_value": copy.deepcopy(checkpoint_after.value),
            },
        },
    }
    try:
        journal_text = encode_round_commit_journal(payload)
    except RoundCommitCodecError:
        raise _blocked("round_commit_journal_invalid") from None
    try:
        write_file_text_create_only(
            journal_path,
            journal_text,
            anchor=project_dir,
        )
    except FileExistsError:
        raise _blocked("round_commit_journal_exists") from None
    except OSError:
        raise RoundCommitRecoveryIOError("round_commit_journal_create_failed") from None
    try:
        reopened_text = read_regular_text_bounded(
            journal_path,
            max_bytes=MAX_ROUND_COMMIT_JOURNAL_BYTES,
            anchor=project_dir,
        )
        reopened = decode_round_commit_journal(reopened_text)
    except (OSError, UnicodeError, ValueError, RoundCommitCodecError):
        raise _blocked("round_commit_journal_reopen_failed") from None
    if reopened_text != journal_text or reopened != payload:
        raise _blocked("round_commit_journal_reopen_mismatch")
    return copy.deepcopy(payload)


def _load_round_commit_context(project_dir: Path) -> _RoundCommitContext | None:
    project_dir, _ = _project_context(project_dir)
    journal_path = project_dir / ROUND_COMMIT_JOURNAL_NAME
    finalization_path = project_dir / RUN_FINALIZE_JOURNAL_NAME
    if not _journal_exists(journal_path, anchor=project_dir):
        return None
    if _journal_exists(finalization_path, anchor=project_dir):
        raise _blocked("finalization_journal_present")
    try:
        journal_text = read_regular_text_bounded(
            journal_path,
            max_bytes=MAX_ROUND_COMMIT_JOURNAL_BYTES,
            anchor=project_dir,
        )
        payload = decode_round_commit_journal(journal_text)
    except (OSError, UnicodeError, RuntimeError, ValueError, RoundCommitCodecError):
        raise _blocked("round_commit_journal_invalid") from None

    run_id = payload["run_id"]
    run_root = _validated_run_root(
        project_dir=project_dir,
        run_root_value=payload["run_root"],
        expected_run_id=run_id if isinstance(run_id, str) else None,
        expected_identity=payload["run_root_identity"],
    )
    run_config_sha256 = _run_config_digest(run_root)
    if run_config_sha256 != payload["run_config_sha256"]:
        raise _blocked("run_config_digest_changed")
    round_index = payload["round"]
    attempt_id = payload["attempt_id"]
    if not isinstance(round_index, int) or not isinstance(attempt_id, str):
        raise _blocked("round_commit_journal_invalid")
    attempt_dir, attempt_state = _attempt_context(
        run_root=run_root,
        round_index=round_index,
        attempt_id=attempt_id,
        run_config_sha256=run_config_sha256,
    )
    return _RoundCommitContext(
        project_dir=project_dir,
        run_root=run_root,
        attempt_dir=attempt_dir,
        journal_path=journal_path,
        journal_text=journal_text,
        payload=payload,
        attempt_state=attempt_state,
    )


def _classify_artifact(
    artifact_name: str,
    record: Mapping[str, object],
    generation: _Generation,
) -> str:
    before_present = record["before_present"]
    before_sha256 = record["before_sha256"]
    after_sha256 = record["after_sha256"]
    if artifact_name == "best_output" and record.get("write") is False:
        if generation.present != before_present:
            return "conflict"
        if generation.present and generation.sha256 != before_sha256:
            return "conflict"
        return "after"
    if generation.present and generation.sha256 == after_sha256:
        return "after"
    if generation.present == before_present and (
        not generation.present or generation.sha256 == before_sha256
    ):
        return "before"
    return "conflict"


def _artifact_states(
    context: _RoundCommitContext,
) -> tuple[tuple[str, str], ...]:
    paths = _artifact_paths(
        project_dir=context.project_dir,
        run_root=context.run_root,
    )
    artifacts = context.payload.get("artifacts")
    if not isinstance(artifacts, dict):
        raise _blocked("round_commit_journal_invalid")
    states: list[tuple[str, str]] = []
    for artifact_name in ROUND_COMMIT_ARTIFACT_NAMES:
        path, anchor = paths[artifact_name]
        try:
            generation = _read_generation(path, anchor=anchor)
        except RoundCommitRecoveryError:
            raise _blocked(f"artifact_unsafe:{artifact_name}") from None
        record = artifacts.get(artifact_name)
        if not isinstance(record, dict):
            raise _blocked("round_commit_journal_invalid")
        states.append(
            (
                artifact_name,
                _classify_artifact(artifact_name, record, generation),
            )
        )
    return tuple(states)


def _inspection_from_context(
    context: _RoundCommitContext,
) -> RoundCommitRecoveryInspection:
    states = _artifact_states(context)
    conflicts = [name for name, state in states if state == "conflict"]
    if conflicts:
        return RoundCommitRecoveryInspection(
            status="conflict",
            can_recover=False,
            journal_present=True,
            transaction_id=str(context.payload["transaction_id"]),
            run_id=str(context.payload["run_id"]),
            round_index=int(context.payload["round"]),
            attempt_state=context.attempt_state,
            artifact_states=states,
            blocked_reason=f"artifact_conflict:{conflicts[0]}",
        )
    all_after = all(state == "after" for _, state in states)
    status = {
        "active": "prepared",
        "ready_to_publish": "publication_pending",
        "published": "complete" if all_after else "apply_pending",
    }[context.attempt_state]
    return RoundCommitRecoveryInspection(
        status=status,
        can_recover=True,
        journal_present=True,
        transaction_id=str(context.payload["transaction_id"]),
        run_id=str(context.payload["run_id"]),
        round_index=int(context.payload["round"]),
        attempt_state=context.attempt_state,
        artifact_states=states,
    )


def classify_round_commit_recovery(
    project_dir: Path,
) -> RoundCommitRecoveryInspection:
    """Inspect one fixed journal without mutating publication or artifact state."""
    try:
        candidate_project = Path(project_dir).expanduser().absolute()
        if not _journal_exists(
            candidate_project / ROUND_COMMIT_JOURNAL_NAME,
            anchor=candidate_project,
        ):
            return RoundCommitRecoveryInspection(
                status="absent",
                can_recover=False,
                journal_present=False,
            )
        context = _load_round_commit_context(project_dir)
        if context is None:
            return RoundCommitRecoveryInspection(
                status="absent",
                can_recover=False,
                journal_present=False,
            )
        return _inspection_from_context(context)
    except RoundCommitRecoveryError as exc:
        status = (
            "invalid"
            if exc.code
            in {
                "project_runtime_unsafe",
                "round_commit_journal_unsafe",
                "round_commit_journal_invalid",
            }
            else "conflict"
        )
        return RoundCommitRecoveryInspection(
            status=status,
            can_recover=False,
            journal_present=True,
            blocked_reason=exc.code,
        )


def _load_run_finalize_context(project_dir: Path) -> _RunFinalizeContext | None:
    project_dir, _ = _project_context(project_dir)
    round_journal_path = project_dir / ROUND_COMMIT_JOURNAL_NAME
    journal_path = project_dir / RUN_FINALIZE_JOURNAL_NAME
    if not _journal_exists(journal_path, anchor=project_dir):
        return None
    if _journal_exists(round_journal_path, anchor=project_dir):
        raise _blocked("round_commit_journal_present")
    try:
        journal_text = read_regular_text_bounded(
            journal_path,
            max_bytes=MAX_ROUND_COMMIT_JOURNAL_BYTES,
            anchor=project_dir,
        )
        payload = decode_run_finalize_journal(journal_text)
    except (OSError, UnicodeError, RuntimeError, ValueError, RoundCommitCodecError):
        raise _blocked("run_finalize_journal_invalid") from None
    run_id = payload["run_id"]
    run_root = _validated_run_root(
        project_dir=project_dir,
        run_root_value=payload["run_root"],
        expected_run_id=run_id if isinstance(run_id, str) else None,
        expected_identity=payload["run_root_identity"],
    )
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, dict):
        raise _blocked("run_finalize_journal_invalid")
    images: dict[str, AfterImage] = {}
    for name in RUN_FINALIZE_ARTIFACT_NAMES:
        record = artifacts.get(name)
        if not isinstance(record, dict):
            raise _blocked("run_finalize_journal_invalid")
        value = record.get("after_value")
        if not isinstance(value, dict):
            raise _blocked("run_finalize_journal_invalid")
        try:
            text = json.dumps(value, indent=2, allow_nan=False)
        except (TypeError, ValueError, RecursionError):
            raise _blocked("run_finalize_journal_invalid") from None
        images[name] = AfterImage(
            value=copy.deepcopy(value),
            text=text,
            sha256=_sha256_text(text),
        )
    _validate_run_finalize_after_images(
        project_dir=project_dir,
        run_root=run_root,
        run_summary_after=images["run_summary"],
        run_config_after=images["run_config"],
        checkpoint_after=images["checkpoint"],
    )
    return _RunFinalizeContext(
        project_dir=project_dir,
        run_root=run_root,
        journal_path=journal_path,
        journal_text=journal_text,
        payload=payload,
    )


def _run_finalize_artifact_states(
    context: _RunFinalizeContext,
) -> tuple[tuple[str, str], ...]:
    paths = _run_finalize_artifact_paths(
        project_dir=context.project_dir,
        run_root=context.run_root,
    )
    artifacts = context.payload.get("artifacts")
    if not isinstance(artifacts, dict):
        raise _blocked("run_finalize_journal_invalid")
    states: list[tuple[str, str]] = []
    for name in RUN_FINALIZE_ARTIFACT_NAMES:
        record = artifacts.get(name)
        if not isinstance(record, dict):
            raise _blocked("run_finalize_journal_invalid")
        path, anchor = paths[name]
        try:
            generation = _read_generation(path, anchor=anchor)
        except RoundCommitRecoveryError:
            raise _blocked(f"artifact_unsafe:{name}") from None
        states.append((name, _classify_artifact(name, record, generation)))
    return tuple(states)


def _run_finalize_inspection(
    context: _RunFinalizeContext,
) -> RoundCommitRecoveryInspection:
    states = _run_finalize_artifact_states(context)
    conflicts = [name for name, state in states if state == "conflict"]
    artifacts = context.payload["artifacts"]
    assert isinstance(artifacts, dict)
    checkpoint = artifacts["checkpoint"]
    assert isinstance(checkpoint, dict)
    checkpoint_value = checkpoint["after_value"]
    assert isinstance(checkpoint_value, dict)
    round_index = checkpoint_value["last_completed_round"]
    assert isinstance(round_index, int)
    if conflicts:
        return RoundCommitRecoveryInspection(
            status="conflict",
            can_recover=False,
            journal_present=True,
            transaction_id=str(context.payload["transaction_id"]),
            run_id=str(context.payload["run_id"]),
            round_index=round_index,
            artifact_states=states,
            blocked_reason=f"artifact_conflict:{conflicts[0]}",
        )
    return RoundCommitRecoveryInspection(
        status="complete" if all(state == "after" for _, state in states) else "apply_pending",
        can_recover=True,
        journal_present=True,
        transaction_id=str(context.payload["transaction_id"]),
        run_id=str(context.payload["run_id"]),
        round_index=round_index,
        artifact_states=states,
    )


def classify_run_finalize_recovery(
    project_dir: Path,
) -> RoundCommitRecoveryInspection:
    """Inspect the finalization journal without changing any final artifact."""
    try:
        candidate_project = Path(project_dir).expanduser().absolute()
        if not _journal_exists(
            candidate_project / RUN_FINALIZE_JOURNAL_NAME,
            anchor=candidate_project,
        ):
            return RoundCommitRecoveryInspection(
                status="absent",
                can_recover=False,
                journal_present=False,
            )
        context = _load_run_finalize_context(project_dir)
        if context is None:
            return RoundCommitRecoveryInspection(
                status="absent",
                can_recover=False,
                journal_present=False,
            )
        return _run_finalize_inspection(context)
    except RoundCommitRecoveryError as exc:
        status = (
            "invalid"
            if exc.code
            in {
                "project_runtime_unsafe",
                "round_commit_journal_unsafe",
                "run_finalize_journal_invalid",
            }
            else "conflict"
        )
        return RoundCommitRecoveryInspection(
            status=status,
            can_recover=False,
            journal_present=True,
            blocked_reason=exc.code,
        )


def _reload_same_run_finalize(expected: _RunFinalizeContext) -> _RunFinalizeContext:
    current = _load_run_finalize_context(expected.project_dir)
    if current is None:
        raise _blocked("run_finalize_journal_missing")
    if current.journal_text != expected.journal_text or current.payload != expected.payload:
        raise _blocked("run_finalize_journal_changed")
    inspection = _run_finalize_inspection(current)
    if not inspection.can_recover:
        raise _blocked(inspection.blocked_reason or "run_finalize_recovery_blocked")
    return current


def _apply_run_finalize_artifact(
    context: _RunFinalizeContext,
    artifact_name: str,
) -> None:
    paths = _run_finalize_artifact_paths(
        project_dir=context.project_dir,
        run_root=context.run_root,
    )
    artifacts = context.payload.get("artifacts")
    if not isinstance(artifacts, dict):
        raise _blocked("run_finalize_journal_invalid")
    record = artifacts.get(artifact_name)
    if not isinstance(record, dict):
        raise _blocked("run_finalize_journal_invalid")
    path, anchor = paths[artifact_name]
    generation = _read_generation(path, anchor=anchor)
    state = _classify_artifact(artifact_name, record, generation)
    if state == "conflict":
        raise _blocked(f"artifact_conflict:{artifact_name}")
    if state == "after":
        return
    value = record.get("after_value")
    try:
        text = json.dumps(value, indent=2, allow_nan=False)
    except (TypeError, ValueError, RecursionError):
        raise _blocked(f"{artifact_name}_after_image_invalid") from None
    if _sha256_text(text) != record.get("after_sha256"):
        raise _blocked(f"{artifact_name}_after_image_digest_mismatch")
    try:
        write_file_text(path, text, anchor=anchor)
    except OSError:
        raise RoundCommitRecoveryIOError(f"artifact_write_failed:{artifact_name}") from None
    verified = _read_generation(path, anchor=anchor)
    if _classify_artifact(artifact_name, record, verified) != "after":
        raise _blocked(f"artifact_verify_failed:{artifact_name}")


def recover_run_finalize(
    project_dir: Path,
) -> RoundCommitRecoveryInspection:
    """Roll final summary/config/checkpoint forward in their fixed safe order."""
    initial = classify_run_finalize_recovery(project_dir)
    if initial.status == "absent":
        return initial
    if not initial.can_recover:
        raise _blocked(initial.blocked_reason or "run_finalize_recovery_blocked")
    context = _load_run_finalize_context(project_dir)
    if context is None:
        return RoundCommitRecoveryInspection(
            status="absent",
            can_recover=False,
            journal_present=False,
        )
    preflight = _run_finalize_inspection(context)
    if not preflight.can_recover:
        raise _blocked(preflight.blocked_reason or "run_finalize_recovery_blocked")
    for artifact_name in RUN_FINALIZE_ARTIFACT_NAMES:
        context = _reload_same_run_finalize(context)
        _apply_run_finalize_artifact(context, artifact_name)
    final_context = _reload_same_run_finalize(context)
    final_inspection = _run_finalize_inspection(final_context)
    if final_inspection.status != "complete":
        raise _blocked("run_finalize_after_state_unverified")
    try:
        unlink_artifact_file_if_matches(
            final_context.journal_path,
            final_context.journal_text,
            anchor=final_context.project_dir,
        )
    except OSError:
        raise RoundCommitRecoveryIOError("run_finalize_journal_cleanup_failed") from None
    return RoundCommitRecoveryInspection(
        status="recovered",
        can_recover=False,
        journal_present=False,
        transaction_id=final_inspection.transaction_id,
        run_id=final_inspection.run_id,
        round_index=final_inspection.round_index,
        artifact_states=final_inspection.artifact_states,
    )


def infer_round_commit_project_dir(run_root: Path) -> Path | None:
    """Infer the project only from the supported lexical ``project/runs/run`` form."""
    run_root = Path(run_root).expanduser()
    if run_root.parent.name != "runs":
        return None
    return run_root.parent.parent


def round_commit_read_blocker(
    project_dir: Path,
) -> tuple[str | None, RoundCommitRecoveryInspection]:
    """Return a fixed blocker without changing journal or artifact state."""
    inspection = classify_round_commit_recovery(project_dir)
    if inspection.status != "absent":
        blocker = (
            "round_commit_recovery_required"
            if inspection.can_recover
            else "round_commit_recovery_conflict"
        )
        return blocker, inspection
    finalization = classify_run_finalize_recovery(project_dir)
    if finalization.status == "absent":
        return None, finalization
    blocker = "finalization_pending" if finalization.can_recover else "finalization_conflict"
    return blocker, finalization


def ensure_round_commit_readable(
    project_dir: Path,
) -> RoundCommitRecoveryInspection:
    """Fail before a reader can combine artifacts from different generations."""
    blocker, inspection = round_commit_read_blocker(project_dir)
    if blocker is not None:
        raise RoundCommitReadError(blocker)
    return inspection


def _history_after_text(
    context: _RoundCommitContext,
    artifact_name: str,
) -> str:
    paths = _artifact_paths(
        project_dir=context.project_dir,
        run_root=context.run_root,
    )
    path, anchor = paths[artifact_name]
    generation = _read_generation(path, anchor=anchor)
    round_index = int(context.payload["round"])
    metric = context.payload.get("round_metric")
    if not isinstance(metric, dict):
        raise _blocked("round_commit_journal_invalid")
    return _history_after_image(
        generation,
        round_metric=metric,
        round_index=round_index,
    ).text


def _best_output_after_text(context: _RoundCommitContext) -> str:
    round_index = int(context.payload["round"])
    try:
        revised_output = read_regular_text_bounded(
            context.run_root / f"round_{round_index:02d}" / "03_revised.md",
            max_bytes=MAX_ROUND_COMMIT_ARTIFACT_BYTES,
            anchor=context.run_root,
        )
    except (OSError, UnicodeError, RuntimeError, ValueError):
        raise _blocked("canonical_revised_output_unsafe") from None
    return build_best_output_after_image(revised_output).text


def _artifact_after_text(
    context: _RoundCommitContext,
    artifact_name: str,
) -> str:
    artifacts = context.payload.get("artifacts")
    if not isinstance(artifacts, dict):
        raise _blocked("round_commit_journal_invalid")
    record = artifacts.get(artifact_name)
    if not isinstance(record, dict):
        raise _blocked("round_commit_journal_invalid")
    if artifact_name in {"score_history", "round_metrics"}:
        text = _history_after_text(context, artifact_name)
    elif artifact_name == "best_output":
        text = _best_output_after_text(context)
    elif artifact_name == "memory":
        text = record.get("after_text")
        if not isinstance(text, str):
            raise _blocked("memory_after_image_invalid")
    else:
        value = record["after_value"]
        try:
            text = json.dumps(value, indent=2, allow_nan=False)
        except (TypeError, ValueError, RecursionError):
            raise _blocked(f"{artifact_name}_after_image_invalid") from None
    if _sha256_text(text) != record["after_sha256"]:
        raise _blocked(f"{artifact_name}_after_image_digest_mismatch")
    return text


def _apply_artifact(
    context: _RoundCommitContext,
    artifact_name: str,
) -> None:
    paths = _artifact_paths(
        project_dir=context.project_dir,
        run_root=context.run_root,
    )
    artifacts = context.payload.get("artifacts")
    if not isinstance(artifacts, dict):
        raise _blocked("round_commit_journal_invalid")
    record = artifacts.get(artifact_name)
    if not isinstance(record, dict):
        raise _blocked("round_commit_journal_invalid")
    path, anchor = paths[artifact_name]
    generation = _read_generation(path, anchor=anchor)
    state = _classify_artifact(artifact_name, record, generation)
    if state == "conflict":
        raise _blocked(f"artifact_conflict:{artifact_name}")
    if state == "after":
        return
    text = _artifact_after_text(context, artifact_name)
    try:
        write_file_text(path, text, anchor=anchor)
    except OSError:
        raise RoundCommitRecoveryIOError(f"artifact_write_failed:{artifact_name}") from None
    verified = _read_generation(path, anchor=anchor)
    if _classify_artifact(artifact_name, record, verified) != "after":
        raise _blocked(f"artifact_verify_failed:{artifact_name}")


def _reload_same_transaction(
    expected: _RoundCommitContext,
    *,
    required_attempt_state: str | None = None,
) -> _RoundCommitContext:
    current = _load_round_commit_context(expected.project_dir)
    if current is None:
        raise _blocked("round_commit_journal_missing")
    if current.journal_text != expected.journal_text or current.payload != expected.payload:
        raise _blocked("round_commit_journal_changed")
    if required_attempt_state is not None and current.attempt_state != required_attempt_state:
        raise _blocked("round_commit_attempt_state_changed")
    inspection = _inspection_from_context(current)
    if not inspection.can_recover:
        raise _blocked(inspection.blocked_reason or "round_commit_recovery_blocked")
    return current


def _mark_ready(attempt_dir: Path) -> None:
    try:
        mark_attempt_ready_to_publish(attempt_dir)
    except OSError:
        raise RoundCommitRecoveryIOError("round_commit_publication_io_failed") from None
    except (ValueError, RuntimeError):
        raise _blocked("round_commit_publication_failed") from None


def _publish(attempt_dir: Path) -> None:
    try:
        publish_attempt(attempt_dir)
    except OSError:
        raise RoundCommitRecoveryIOError("round_commit_publication_io_failed") from None
    except (ValueError, RuntimeError):
        raise _blocked("round_commit_publication_failed") from None


def recover_round_commit(
    project_dir: Path,
) -> RoundCommitRecoveryInspection:
    """Perform one bounded idempotent publication and roll-forward pass."""
    initial = classify_round_commit_recovery(project_dir)
    if initial.status == "absent":
        return initial
    if not initial.can_recover:
        raise _blocked(initial.blocked_reason or "round_commit_recovery_blocked")

    context = _load_round_commit_context(project_dir)
    if context is None:
        return RoundCommitRecoveryInspection(
            status="absent",
            can_recover=False,
            journal_present=False,
        )
    # Recheck all generations before publication or any mutable artifact write.
    preflight = _inspection_from_context(context)
    if not preflight.can_recover:
        raise _blocked(preflight.blocked_reason or "round_commit_recovery_blocked")

    if context.attempt_state == "active":
        _mark_ready(context.attempt_dir)
        context = _reload_same_transaction(
            context,
            required_attempt_state="ready_to_publish",
        )
    if context.attempt_state == "ready_to_publish":
        _publish(context.attempt_dir)

    context = _reload_same_transaction(
        context,
        required_attempt_state="published",
    )

    for artifact_name in (
        "best_output",
        "score_history",
        "round_metrics",
        "memory",
        "research_state",
        "checkpoint",
    ):
        context = _reload_same_transaction(
            context,
            required_attempt_state="published",
        )
        _apply_artifact(context, artifact_name)

    final_context = _reload_same_transaction(
        context,
        required_attempt_state="published",
    )
    final_inspection = _inspection_from_context(final_context)
    if final_inspection.status != "complete":
        raise _blocked("round_commit_after_state_unverified")
    try:
        unlink_artifact_file_if_matches(
            final_context.journal_path,
            final_context.journal_text,
            anchor=final_context.project_dir,
        )
    except OSError:
        raise RoundCommitRecoveryIOError("round_commit_journal_cleanup_failed") from None
    return RoundCommitRecoveryInspection(
        status="recovered",
        can_recover=False,
        journal_present=False,
        transaction_id=final_inspection.transaction_id,
        run_id=final_inspection.run_id,
        round_index=final_inspection.round_index,
        attempt_state="published",
        artifact_states=final_inspection.artifact_states,
    )
