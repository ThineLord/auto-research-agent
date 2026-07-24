"""Exact-copy execution and roll-forward recovery for one legacy history twin."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
import stat
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Mapping

from .resume_safety import validate_project_run_root
from .round_commit_recovery import (
    DIAGNOSTIC_FINALIZE_JOURNAL_NAME,
    LEGACY_MIGRATION_JOURNAL_NAME,
    ROUND_COMMIT_JOURNAL_NAME,
    RUN_FINALIZE_JOURNAL_NAME,
)
from .runtime import run_lock_handle_is_current
from .storage import (
    artifact_path_exists,
    artifact_path_is_safe,
    create_artifact_directory_only,
    ensure_artifact_paths_safe,
    ensure_project_runtime_paths_safe,
    read_regular_text_bounded,
    unlink_artifact_file_if_matches,
    write_file_text_create_only,
    write_file_text_publish_only,
)

EVIDENCE_SOURCE_NAME = "source_history.json"
EVIDENCE_MANIFEST_NAME = "manifest.json"
EVIDENCE_RECEIPT_NAME = "receipt.json"
MAX_LEGACY_MIGRATION_JOURNAL_BYTES = 2 * 1024 * 1024
MAX_LEGACY_MIGRATION_METADATA_BYTES = 2 * 1024 * 1024
MAX_LEGACY_MIGRATION_HISTORY_BYTES = 64 * 1024 * 1024
MAX_LEGACY_MIGRATION_JSON_DEPTH = 128

_DIGEST_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_MIGRATION_ID_PATTERN = re.compile(r"legacy_[0-9a-f]{32}\Z")
_RUN_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_ARTIFACT_NAMES = {"score_history", "round_metrics"}
_JOURNAL_FIELDS = (
    "schema_version",
    "kind",
    "state",
    "migration_id",
    "run_id",
    "completed_rounds",
    "source_artifact",
    "target_artifact",
    "source_sha256",
    "source_size",
    "checkpoint_sha256",
    "checkpoint_size",
    "run_config_sha256",
    "run_config_size",
    "run_summary_sha256",
    "run_summary_size",
    "run_root_identity",
    "evidence_path",
    "evidence_identity",
    "evidence_manifest_sha256",
    "target_before_present",
)
_IDENTITY_FIELDS = {
    "configured_storage",
    "device",
    "inode",
    "stat_identity_available",
}
_EVIDENCE_IDENTITY_FIELDS = {"device", "inode", "stat_identity_available"}
_MANIFEST_FIELDS = {
    "schema_version",
    "kind",
    "migration_id",
    "tool_version",
    "created_at",
    "classification",
    "run_id",
    "completed_rounds",
    "source_artifact",
    "target_artifact",
    "source_sha256",
    "source_size",
    "checkpoint",
    "run_config",
    "run_summary",
    "inventory",
    "proposed_target_sha256",
    "execution_mode",
}
_RECEIPT_FIELDS = {
    "schema_version",
    "kind",
    "migration_id",
    "run_id",
    "source_artifact",
    "target_artifact",
    "target_sha256",
    "target_size",
    "recovered",
}


class LegacyMigrationCodecError(ValueError):
    """A strict migration journal or evidence schema violation."""


class LegacyMigrationExecutionError(RuntimeError):
    """A fixed, path-redacted execution refusal."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class LegacyMigrationExecutionIOError(OSError):
    """A fixed, path-redacted execution filesystem failure."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class LegacyMigrationRecoveryError(RuntimeError):
    """A fixed, path-redacted recovery conflict."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class LegacyMigrationRecoveryInspection:
    status: str
    can_recover: bool
    journal_present: bool
    migration_id: str | None = None
    run_id: str | None = None
    completed_rounds: int | None = None
    source_artifact: str | None = None
    target_artifact: str | None = None
    target_state: str | None = None
    receipt_state: str | None = None
    blocked_reason: str | None = None


@dataclass(frozen=True)
class LegacyMigrationExecutionResult:
    status: str
    migration_id: str
    run_id: str
    source_artifact: str
    target_artifact: str
    recovered: bool


@dataclass(frozen=True)
class _Generation:
    present: bool
    text: str | None
    sha256: str | None
    size: int | None


@dataclass(frozen=True)
class _Context:
    project_dir: Path
    run_root: Path
    source_path: Path
    source_anchor: Path
    target_path: Path
    target_anchor: Path
    evidence_dir: Path
    journal_path: Path
    journal_text: str
    payload: dict[str, object]


def _tool_version() -> str:
    try:
        value = version("auto-research-agent")
    except PackageNotFoundError:
        return "source-checkout"
    return value if value and len(value) <= 128 else "unknown"


def _reject_constant(value: str) -> None:
    raise LegacyMigrationCodecError(f"invalid JSON numeric constant: {value}")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise LegacyMigrationCodecError("duplicate JSON object key")
        value[key] = item
    return value


def _validate_json_depth(value: object) -> None:
    pending: list[tuple[object, int]] = [(value, 0)]
    while pending:
        current, depth = pending.pop()
        if depth > MAX_LEGACY_MIGRATION_JSON_DEPTH:
            raise LegacyMigrationCodecError("JSON depth exceeds limit")
        if isinstance(current, dict):
            pending.extend((item, depth + 1) for item in current.values())
        elif isinstance(current, list):
            pending.extend((item, depth + 1) for item in current)


def _strict_json(data: str | bytes, *, max_bytes: int) -> object:
    if isinstance(data, str):
        try:
            raw = data.encode("utf-8")
        except UnicodeError:
            raise LegacyMigrationCodecError("input is not valid UTF-8") from None
    elif isinstance(data, bytes):
        raw = data
    else:
        raise LegacyMigrationCodecError("input must be text or bytes")
    if len(raw) > max_bytes:
        raise LegacyMigrationCodecError("input exceeds byte limit")
    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except LegacyMigrationCodecError:
        raise
    except (UnicodeError, ValueError, RecursionError):
        raise LegacyMigrationCodecError("input is not strict JSON") from None
    _validate_json_depth(value)
    return value


def _exact_object(value: object, fields: set[str], *, location: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != fields:
        raise LegacyMigrationCodecError(f"{location} has missing or unknown fields")
    return value


def _digest(value: object, *, location: str) -> str:
    if not isinstance(value, str) or _DIGEST_PATTERN.fullmatch(value) is None:
        raise LegacyMigrationCodecError(f"{location} is not a SHA-256 digest")
    return value


def _positive_size(value: object, *, location: str, maximum: int) -> int:
    if type(value) is not int or value <= 0 or value > maximum:
        raise LegacyMigrationCodecError(f"{location} is outside its byte bound")
    return value


def _optional_generation(
    digest: object,
    size: object,
    *,
    location: str,
) -> None:
    if digest is None and size is None:
        return
    _digest(digest, location=f"{location}_sha256")
    _positive_size(
        size,
        location=f"{location}_size",
        maximum=MAX_LEGACY_MIGRATION_METADATA_BYTES,
    )


def _validate_identity(
    value: object,
    *,
    evidence: bool = False,
) -> dict[str, object]:
    fields = _EVIDENCE_IDENTITY_FIELDS if evidence else _IDENTITY_FIELDS
    identity = _exact_object(value, fields, location="identity")
    if not evidence and type(identity["configured_storage"]) is not bool:
        raise LegacyMigrationCodecError("configured_storage must be boolean")
    available = identity["stat_identity_available"]
    if type(available) is not bool:
        raise LegacyMigrationCodecError("stat_identity_available must be boolean")
    for name in ("device", "inode"):
        item = identity[name]
        if available:
            if type(item) is not int or item < 0:
                raise LegacyMigrationCodecError(f"identity.{name} is invalid")
        elif item is not None:
            raise LegacyMigrationCodecError(f"identity.{name} must be null")
    return identity


def _validate_journal(value: object) -> dict[str, object]:
    payload = _exact_object(value, set(_JOURNAL_FIELDS), location="journal")
    if payload["schema_version"] != 1 or type(payload["schema_version"]) is not int:
        raise LegacyMigrationCodecError("schema_version must be 1")
    if payload["kind"] != "legacy_history_migration" or payload["state"] != "prepared":
        raise LegacyMigrationCodecError("journal kind or state is invalid")
    migration_id = payload["migration_id"]
    run_id = payload["run_id"]
    if not isinstance(migration_id, str) or _MIGRATION_ID_PATTERN.fullmatch(migration_id) is None:
        raise LegacyMigrationCodecError("migration_id is invalid")
    if not isinstance(run_id, str) or _RUN_ID_PATTERN.fullmatch(run_id) is None:
        raise LegacyMigrationCodecError("run_id is invalid")
    completed_rounds = payload["completed_rounds"]
    if type(completed_rounds) is not int or not 1 <= completed_rounds <= 999999:
        raise LegacyMigrationCodecError("completed_rounds is invalid")
    source = payload["source_artifact"]
    target = payload["target_artifact"]
    if source not in _ARTIFACT_NAMES or target not in _ARTIFACT_NAMES or source == target:
        raise LegacyMigrationCodecError("source or target artifact is invalid")
    _digest(payload["source_sha256"], location="source_sha256")
    _positive_size(
        payload["source_size"],
        location="source_size",
        maximum=MAX_LEGACY_MIGRATION_HISTORY_BYTES,
    )
    _digest(payload["checkpoint_sha256"], location="checkpoint_sha256")
    _positive_size(
        payload["checkpoint_size"],
        location="checkpoint_size",
        maximum=MAX_LEGACY_MIGRATION_METADATA_BYTES,
    )
    _optional_generation(
        payload["run_config_sha256"],
        payload["run_config_size"],
        location="run_config",
    )
    _optional_generation(
        payload["run_summary_sha256"],
        payload["run_summary_size"],
        location="run_summary",
    )
    _validate_identity(payload["run_root_identity"])
    evidence_path = payload["evidence_path"]
    if (
        not isinstance(evidence_path, str)
        or not evidence_path
        or len(evidence_path) > 4096
        or "\x00" in evidence_path
        or not Path(evidence_path).is_absolute()
    ):
        raise LegacyMigrationCodecError("evidence_path is invalid")
    _validate_identity(payload["evidence_identity"], evidence=True)
    _digest(payload["evidence_manifest_sha256"], location="evidence_manifest_sha256")
    if payload["target_before_present"] is not False:
        raise LegacyMigrationCodecError("target_before_present must be false")
    return payload


def encode_legacy_migration_journal(payload: Mapping[str, object]) -> str:
    if not isinstance(payload, dict):
        raise LegacyMigrationCodecError("journal must be an object")
    validated = _validate_journal(payload)
    ordered = {name: copy.deepcopy(validated[name]) for name in _JOURNAL_FIELDS}
    try:
        encoded = json.dumps(ordered, indent=2, allow_nan=False)
    except (TypeError, ValueError, RecursionError):
        raise LegacyMigrationCodecError("journal is not serializable") from None
    if len(encoded.encode("utf-8")) > MAX_LEGACY_MIGRATION_JOURNAL_BYTES:
        raise LegacyMigrationCodecError("journal exceeds byte limit")
    return encoded


def decode_legacy_migration_journal(data: str | bytes) -> dict[str, object]:
    value = _strict_json(data, max_bytes=MAX_LEGACY_MIGRATION_JOURNAL_BYTES)
    return copy.deepcopy(_validate_journal(value))


def _read_generation(path: Path, *, anchor: Path, max_bytes: int) -> _Generation:
    try:
        ensure_artifact_paths_safe([path], anchor=anchor)
        if not artifact_path_exists(path, anchor=anchor):
            return _Generation(False, None, None, None)
        text = read_regular_text_bounded(path, max_bytes=max_bytes, anchor=anchor)
    except (OSError, RuntimeError, UnicodeError, ValueError):
        raise LegacyMigrationRecoveryError("legacy_migration_artifact_unsafe") from None
    content = text.encode("utf-8")
    return _Generation(True, text, hashlib.sha256(content).hexdigest(), len(content))


def _run_root_identity(project_dir: Path, run_root: Path) -> dict[str, object]:
    try:
        metadata = os.stat(run_root, follow_symlinks=False)
        if not stat.S_ISDIR(metadata.st_mode):
            raise OSError
        device = getattr(metadata, "st_dev", None)
        inode = getattr(metadata, "st_ino", None)
        available = (
            os.name != "nt"
            and type(device) is int
            and device >= 0
            and type(inode) is int
            and inode > 0
        )
        return {
            "configured_storage": (project_dir / "runs").is_symlink(),
            "device": device if available else None,
            "inode": inode if available else None,
            "stat_identity_available": available,
        }
    except (OSError, RuntimeError, ValueError):
        raise LegacyMigrationRecoveryError("legacy_migration_run_identity_unsafe") from None


def _evidence_identity(evidence_dir: Path) -> dict[str, object]:
    try:
        metadata = evidence_dir.lstat()
        if evidence_dir.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
            raise OSError
        device = getattr(metadata, "st_dev", None)
        inode = getattr(metadata, "st_ino", None)
        available = (
            os.name != "nt"
            and type(device) is int
            and device >= 0
            and type(inode) is int
            and inode > 0
        )
        return {
            "device": device if available else None,
            "inode": inode if available else None,
            "stat_identity_available": available,
        }
    except (OSError, RuntimeError, ValueError):
        raise LegacyMigrationRecoveryError("legacy_migration_evidence_unsafe") from None


def _load_project_generations(
    project_dir: Path,
) -> tuple[Path, dict[str, object], dict[str, _Generation]]:
    try:
        project_dir = Path(project_dir).expanduser().absolute()
        ensure_project_runtime_paths_safe(project_dir, anchor=project_dir.parent)
    except (OSError, RuntimeError, ValueError):
        raise LegacyMigrationRecoveryError("legacy_migration_project_unsafe") from None
    checkpoint = _read_generation(
        project_dir / "checkpoint.json",
        anchor=project_dir,
        max_bytes=MAX_LEGACY_MIGRATION_METADATA_BYTES,
    )
    if not checkpoint.present or checkpoint.text is None:
        raise LegacyMigrationRecoveryError("legacy_migration_checkpoint_missing")
    try:
        checkpoint_value = _strict_json(
            checkpoint.text,
            max_bytes=MAX_LEGACY_MIGRATION_METADATA_BYTES,
        )
    except LegacyMigrationCodecError:
        raise LegacyMigrationRecoveryError("legacy_migration_checkpoint_invalid") from None
    if not isinstance(checkpoint_value, dict):
        raise LegacyMigrationRecoveryError("legacy_migration_checkpoint_invalid")
    run_id = checkpoint_value.get("run_id")
    run_root, blocker = validate_project_run_root(
        project_dir=project_dir,
        run_root_value=checkpoint_value.get("run_root"),
        require_writable=True,
    )
    if (
        blocker is not None
        or run_root is None
        or not isinstance(run_id, str)
        or run_root.name != run_id
    ):
        raise LegacyMigrationRecoveryError("legacy_migration_run_identity_unsafe")
    generations = {
        "checkpoint": checkpoint,
        "run_config": _read_generation(
            run_root / "run_config.json",
            anchor=run_root,
            max_bytes=MAX_LEGACY_MIGRATION_METADATA_BYTES,
        ),
        "run_summary": _read_generation(
            run_root / "run_summary.json",
            anchor=run_root,
            max_bytes=MAX_LEGACY_MIGRATION_METADATA_BYTES,
        ),
        "score_history": _read_generation(
            project_dir / "score_history.json",
            anchor=project_dir,
            max_bytes=MAX_LEGACY_MIGRATION_HISTORY_BYTES,
        ),
        "round_metrics": _read_generation(
            run_root / "round_metrics.json",
            anchor=run_root,
            max_bytes=MAX_LEGACY_MIGRATION_HISTORY_BYTES,
        ),
    }
    return run_root, checkpoint_value, generations


def _artifact_paths(
    project_dir: Path,
    run_root: Path,
    source_artifact: str,
    target_artifact: str,
) -> tuple[Path, Path, Path, Path]:
    locations = {
        "score_history": (project_dir / "score_history.json", project_dir),
        "round_metrics": (run_root / "round_metrics.json", run_root),
    }
    source_path, source_anchor = locations[source_artifact]
    target_path, target_anchor = locations[target_artifact]
    return source_path, source_anchor, target_path, target_anchor


def _metadata_evidence(generation: _Generation) -> dict[str, object]:
    return {
        "present": generation.present,
        "sha256": generation.sha256,
        "size": generation.size,
    }


def _bounded_checkpoint_fields(value: dict[str, object]) -> dict[str, object]:
    best_score = value.get("best_score")
    if isinstance(best_score, bool) or not isinstance(best_score, (int, float)):
        best_score = None
    elif not math.isfinite(float(best_score)):
        best_score = None
    best_round = value.get("best_round")
    if type(best_round) is not int or not 1 <= best_round <= 999999:
        best_round = None
    return {
        "run_id": value.get("run_id"),
        "last_completed_round": value.get("last_completed_round"),
        "best_score": best_score,
        "best_round": best_round,
    }


def _write_evidence_manifest(evidence_dir: Path, text: str) -> None:
    write_file_text_create_only(
        evidence_dir / EVIDENCE_MANIFEST_NAME,
        text,
        anchor=evidence_dir,
    )


def _write_target_create_only(path: Path, text: str, *, anchor: Path) -> None:
    write_file_text_publish_only(path, text, anchor=anchor)


def _manifest_text(value: Mapping[str, object]) -> str:
    if not isinstance(value, dict) or set(value) != _MANIFEST_FIELDS:
        raise LegacyMigrationCodecError("evidence manifest fields are invalid")
    try:
        text = json.dumps(value, indent=2, allow_nan=False)
    except (TypeError, ValueError, RecursionError):
        raise LegacyMigrationCodecError("evidence manifest is not serializable") from None
    decoded = _strict_json(text, max_bytes=MAX_LEGACY_MIGRATION_METADATA_BYTES)
    _exact_object(decoded, _MANIFEST_FIELDS, location="evidence manifest")
    return text


def _receipt_text(payload: Mapping[str, object], *, recovered: bool) -> str:
    value = {
        "schema_version": 1,
        "kind": "legacy_history_migration_receipt",
        "migration_id": payload["migration_id"],
        "run_id": payload["run_id"],
        "source_artifact": payload["source_artifact"],
        "target_artifact": payload["target_artifact"],
        "target_sha256": payload["source_sha256"],
        "target_size": payload["source_size"],
        "recovered": recovered,
    }
    return json.dumps(value, indent=2, allow_nan=False)


def _receipt_state(context: _Context) -> str:
    receipt = _read_generation(
        context.evidence_dir / EVIDENCE_RECEIPT_NAME,
        anchor=context.evidence_dir,
        max_bytes=MAX_LEGACY_MIGRATION_METADATA_BYTES,
    )
    if not receipt.present:
        return "absent"
    if receipt.text is None:
        return "conflict"
    try:
        value = _strict_json(receipt.text, max_bytes=MAX_LEGACY_MIGRATION_METADATA_BYTES)
    except LegacyMigrationCodecError:
        return "conflict"
    if not isinstance(value, dict) or set(value) != _RECEIPT_FIELDS:
        return "conflict"
    expected = context.payload
    if (
        value.get("schema_version") != 1
        or value.get("kind") != "legacy_history_migration_receipt"
        or value.get("migration_id") != expected["migration_id"]
        or value.get("run_id") != expected["run_id"]
        or value.get("source_artifact") != expected["source_artifact"]
        or value.get("target_artifact") != expected["target_artifact"]
        or value.get("target_sha256") != expected["source_sha256"]
        or value.get("target_size") != expected["source_size"]
        or type(value.get("recovered")) is not bool
    ):
        return "conflict"
    return "exact"


def _load_context(project_dir: Path) -> _Context | None:
    project_dir = Path(project_dir).expanduser().absolute()
    journal_path = project_dir / LEGACY_MIGRATION_JOURNAL_NAME
    try:
        ensure_artifact_paths_safe([journal_path], anchor=project_dir)
        if not artifact_path_exists(journal_path, anchor=project_dir):
            return None
        journal_text = read_regular_text_bounded(
            journal_path,
            max_bytes=MAX_LEGACY_MIGRATION_JOURNAL_BYTES,
            anchor=project_dir,
        )
        payload = decode_legacy_migration_journal(journal_text)
    except (
        OSError,
        RuntimeError,
        UnicodeError,
        ValueError,
        LegacyMigrationCodecError,
    ):
        raise LegacyMigrationRecoveryError("legacy_migration_journal_invalid") from None
    for other_name in (
        ROUND_COMMIT_JOURNAL_NAME,
        RUN_FINALIZE_JOURNAL_NAME,
        DIAGNOSTIC_FINALIZE_JOURNAL_NAME,
    ):
        try:
            if artifact_path_exists(project_dir / other_name, anchor=project_dir):
                raise LegacyMigrationRecoveryError("legacy_migration_other_transaction_present")
        except LegacyMigrationRecoveryError:
            raise
        except (OSError, RuntimeError, ValueError):
            raise LegacyMigrationRecoveryError(
                "legacy_migration_other_transaction_unsafe"
            ) from None
    run_root, checkpoint_value, generations = _load_project_generations(project_dir)
    if (
        checkpoint_value.get("run_id") != payload["run_id"]
        or checkpoint_value.get("last_completed_round") != payload["completed_rounds"]
        or _run_root_identity(project_dir, run_root) != payload["run_root_identity"]
    ):
        raise LegacyMigrationRecoveryError("legacy_migration_run_generation_changed")
    for name in ("checkpoint", "run_config", "run_summary"):
        generation = generations[name]
        expected_digest = payload[f"{name}_sha256"]
        expected_size = payload[f"{name}_size"]
        if generation.sha256 != expected_digest or generation.size != expected_size:
            raise LegacyMigrationRecoveryError(f"legacy_migration_{name}_changed")
    source_artifact = str(payload["source_artifact"])
    target_artifact = str(payload["target_artifact"])
    source = generations[source_artifact]
    if (
        not source.present
        or source.sha256 != payload["source_sha256"]
        or source.size != payload["source_size"]
    ):
        raise LegacyMigrationRecoveryError("legacy_migration_source_changed")
    evidence_dir = Path(str(payload["evidence_path"]))
    if _evidence_identity(evidence_dir) != payload["evidence_identity"]:
        raise LegacyMigrationRecoveryError("legacy_migration_evidence_changed")
    manifest = _read_generation(
        evidence_dir / EVIDENCE_MANIFEST_NAME,
        anchor=evidence_dir,
        max_bytes=MAX_LEGACY_MIGRATION_METADATA_BYTES,
    )
    evidence_source = _read_generation(
        evidence_dir / EVIDENCE_SOURCE_NAME,
        anchor=evidence_dir,
        max_bytes=MAX_LEGACY_MIGRATION_HISTORY_BYTES,
    )
    if (
        not manifest.present
        or manifest.sha256 != payload["evidence_manifest_sha256"]
        or not evidence_source.present
        or evidence_source.sha256 != payload["source_sha256"]
        or evidence_source.size != payload["source_size"]
    ):
        raise LegacyMigrationRecoveryError("legacy_migration_evidence_changed")
    source_path, source_anchor, target_path, target_anchor = _artifact_paths(
        project_dir,
        run_root,
        source_artifact,
        target_artifact,
    )
    return _Context(
        project_dir=project_dir,
        run_root=run_root,
        source_path=source_path,
        source_anchor=source_anchor,
        target_path=target_path,
        target_anchor=target_anchor,
        evidence_dir=evidence_dir,
        journal_path=journal_path,
        journal_text=journal_text,
        payload=payload,
    )


def classify_legacy_migration_recovery(
    project_dir: Path,
) -> LegacyMigrationRecoveryInspection:
    project_dir = Path(project_dir).expanduser().absolute()
    journal_path = project_dir / LEGACY_MIGRATION_JOURNAL_NAME
    try:
        if not artifact_path_is_safe(journal_path, allow_missing=True, anchor=project_dir):
            raise LegacyMigrationRecoveryError("legacy_migration_journal_unsafe")
        if not artifact_path_exists(journal_path, anchor=project_dir):
            return LegacyMigrationRecoveryInspection("absent", False, False)
        context = _load_context(project_dir)
        if context is None:
            return LegacyMigrationRecoveryInspection("absent", False, False)
        target = _read_generation(
            context.target_path,
            anchor=context.target_anchor,
            max_bytes=MAX_LEGACY_MIGRATION_HISTORY_BYTES,
        )
        if not target.present:
            target_state = "absent"
        elif (
            target.sha256 == context.payload["source_sha256"]
            and target.size == context.payload["source_size"]
        ):
            target_state = "exact"
        else:
            target_state = "conflict"
        receipt_state = _receipt_state(context)
        blocked_reason = None
        if target_state == "conflict":
            blocked_reason = "legacy_migration_target_conflict"
        elif receipt_state == "conflict":
            blocked_reason = "legacy_migration_receipt_conflict"
        status = (
            "conflict"
            if blocked_reason is not None
            else "complete"
            if target_state == "exact" and receipt_state == "exact"
            else "apply_pending"
        )
        return LegacyMigrationRecoveryInspection(
            status=status,
            can_recover=blocked_reason is None,
            journal_present=True,
            migration_id=str(context.payload["migration_id"]),
            run_id=str(context.payload["run_id"]),
            completed_rounds=int(context.payload["completed_rounds"]),
            source_artifact=str(context.payload["source_artifact"]),
            target_artifact=str(context.payload["target_artifact"]),
            target_state=target_state,
            receipt_state=receipt_state,
            blocked_reason=blocked_reason,
        )
    except LegacyMigrationRecoveryError as exc:
        return LegacyMigrationRecoveryInspection(
            status="invalid",
            can_recover=False,
            journal_present=True,
            blocked_reason=exc.code,
        )
    except (OSError, RuntimeError, ValueError):
        return LegacyMigrationRecoveryInspection(
            status="invalid",
            can_recover=False,
            journal_present=True,
            blocked_reason="legacy_migration_journal_unsafe",
        )


def _require_owned_lock(project_dir: Path, lock_handle: object) -> None:
    if not run_lock_handle_is_current(project_dir, lock_handle):
        raise LegacyMigrationExecutionError("legacy_migration_lock_required")


def _prepare_evidence_and_journal(
    project_dir: Path,
    evidence_dir: Path,
    *,
    inspection: object,
) -> None:
    run_root, checkpoint_value, generations = _load_project_generations(project_dir)
    source_artifact = str(getattr(inspection, "source_artifact"))
    target_artifact = str(getattr(inspection, "target_artifact"))
    source = generations[source_artifact]
    target = generations[target_artifact]
    if (
        not source.present
        or source.text is None
        or source.sha256 != getattr(inspection, "source_sha256")
        or source.size != getattr(inspection, "source_size")
        or target.present
    ):
        raise LegacyMigrationExecutionError("legacy_migration_generation_changed")
    evidence_dir = Path(evidence_dir).expanduser().absolute()
    try:
        create_artifact_directory_only(
            evidence_dir,
            anchor=evidence_dir.parent,
            mode=0o700,
        )
        write_file_text_create_only(
            evidence_dir / EVIDENCE_SOURCE_NAME,
            source.text,
            anchor=evidence_dir,
        )
    except FileExistsError:
        raise LegacyMigrationExecutionError("legacy_migration_evidence_exists") from None
    except OSError:
        raise LegacyMigrationExecutionIOError("legacy_migration_evidence_write_failed") from None
    migration_id = f"legacy_{uuid.uuid4().hex}"
    checkpoint = generations["checkpoint"]
    manifest_value = {
        "schema_version": 1,
        "kind": "legacy_history_migration_evidence",
        "migration_id": migration_id,
        "tool_version": _tool_version(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "classification": "exact_missing_history_twin",
        "run_id": checkpoint_value["run_id"],
        "completed_rounds": checkpoint_value["last_completed_round"],
        "source_artifact": source_artifact,
        "target_artifact": target_artifact,
        "source_sha256": source.sha256,
        "source_size": source.size,
        "checkpoint": {
            **_metadata_evidence(checkpoint),
            **_bounded_checkpoint_fields(checkpoint_value),
        },
        "run_config": _metadata_evidence(generations["run_config"]),
        "run_summary": _metadata_evidence(generations["run_summary"]),
        "inventory": {
            "target_absent": True,
            "round_commit_absent": True,
            "run_finalize_absent": True,
            "diagnostic_finalize_absent": True,
            "legacy_migration_absent": True,
        },
        "proposed_target_sha256": source.sha256,
        "execution_mode": "explicit_exact_copy",
    }
    try:
        manifest_text = _manifest_text(manifest_value)
        _write_evidence_manifest(evidence_dir, manifest_text)
    except (OSError, LegacyMigrationCodecError):
        raise LegacyMigrationExecutionIOError("legacy_migration_evidence_write_failed") from None
    manifest = _read_generation(
        evidence_dir / EVIDENCE_MANIFEST_NAME,
        anchor=evidence_dir,
        max_bytes=MAX_LEGACY_MIGRATION_METADATA_BYTES,
    )
    if not manifest.present or manifest.text != manifest_text or manifest.sha256 is None:
        raise LegacyMigrationExecutionError("legacy_migration_evidence_verify_failed")
    payload = {
        "schema_version": 1,
        "kind": "legacy_history_migration",
        "state": "prepared",
        "migration_id": migration_id,
        "run_id": checkpoint_value["run_id"],
        "completed_rounds": checkpoint_value["last_completed_round"],
        "source_artifact": source_artifact,
        "target_artifact": target_artifact,
        "source_sha256": source.sha256,
        "source_size": source.size,
        "checkpoint_sha256": checkpoint.sha256,
        "checkpoint_size": checkpoint.size,
        "run_config_sha256": generations["run_config"].sha256,
        "run_config_size": generations["run_config"].size,
        "run_summary_sha256": generations["run_summary"].sha256,
        "run_summary_size": generations["run_summary"].size,
        "run_root_identity": _run_root_identity(project_dir, run_root),
        "evidence_path": str(evidence_dir),
        "evidence_identity": _evidence_identity(evidence_dir),
        "evidence_manifest_sha256": manifest.sha256,
        "target_before_present": False,
    }
    journal_text = encode_legacy_migration_journal(payload)
    try:
        write_file_text_create_only(
            project_dir / LEGACY_MIGRATION_JOURNAL_NAME,
            journal_text,
            anchor=project_dir,
        )
    except FileExistsError:
        raise LegacyMigrationExecutionError("legacy_migration_journal_exists") from None
    except OSError:
        raise LegacyMigrationExecutionIOError("legacy_migration_journal_create_failed") from None
    try:
        reopened = read_regular_text_bounded(
            project_dir / LEGACY_MIGRATION_JOURNAL_NAME,
            max_bytes=MAX_LEGACY_MIGRATION_JOURNAL_BYTES,
            anchor=project_dir,
        )
        decoded = decode_legacy_migration_journal(reopened)
    except (OSError, RuntimeError, ValueError, LegacyMigrationCodecError):
        raise LegacyMigrationExecutionError("legacy_migration_journal_reopen_failed") from None
    if reopened != journal_text or decoded != payload:
        raise LegacyMigrationExecutionError("legacy_migration_journal_reopen_mismatch")


def execute_legacy_history_migration(
    project_dir: Path,
    evidence_dir: Path,
    *,
    lock_handle: object,
) -> LegacyMigrationExecutionResult:
    """Execute only the strict exact-copy candidate under an owned project lock."""
    project_dir = Path(project_dir).expanduser().absolute()
    _require_owned_lock(project_dir, lock_handle)
    from .legacy_migration import classify_legacy_history_migration

    inspection = classify_legacy_history_migration(
        project_dir,
        _owned_lock=lock_handle,
    )
    if (
        inspection.status != "eligible_candidate"
        or inspection.classification != "exact_missing_history_twin"
    ):
        raise LegacyMigrationExecutionError("legacy_migration_not_eligible")
    _prepare_evidence_and_journal(
        project_dir,
        evidence_dir,
        inspection=inspection,
    )
    return recover_legacy_history_migration(
        project_dir,
        lock_handle=lock_handle,
        recovered=False,
    )


def recover_legacy_history_migration(
    project_dir: Path,
    *,
    lock_handle: object,
    recovered: bool = True,
    expected_evidence_dir: Path | None = None,
) -> LegacyMigrationExecutionResult:
    """Roll one valid prepared migration forward without replacing any generation."""
    project_dir = Path(project_dir).expanduser().absolute()
    _require_owned_lock(project_dir, lock_handle)
    inspection = classify_legacy_migration_recovery(project_dir)
    if inspection.status == "absent":
        raise LegacyMigrationRecoveryError("legacy_migration_journal_missing")
    if not inspection.can_recover:
        raise LegacyMigrationRecoveryError(
            inspection.blocked_reason or "legacy_migration_recovery_blocked"
        )
    context = _load_context(project_dir)
    if context is None:
        raise LegacyMigrationRecoveryError("legacy_migration_journal_missing")
    if (
        expected_evidence_dir is not None
        and Path(expected_evidence_dir).expanduser().absolute() != context.evidence_dir
    ):
        raise LegacyMigrationRecoveryError("legacy_migration_evidence_mismatch")
    target = _read_generation(
        context.target_path,
        anchor=context.target_anchor,
        max_bytes=MAX_LEGACY_MIGRATION_HISTORY_BYTES,
    )
    if not target.present:
        source = _read_generation(
            context.source_path,
            anchor=context.source_anchor,
            max_bytes=MAX_LEGACY_MIGRATION_HISTORY_BYTES,
        )
        if source.text is None:
            raise LegacyMigrationRecoveryError("legacy_migration_source_changed")
        try:
            _write_target_create_only(
                context.target_path,
                source.text,
                anchor=context.target_anchor,
            )
        except FileExistsError:
            raise LegacyMigrationRecoveryError("legacy_migration_target_conflict") from None
        except OSError:
            raise LegacyMigrationExecutionIOError("legacy_migration_target_write_failed") from None
    target = _read_generation(
        context.target_path,
        anchor=context.target_anchor,
        max_bytes=MAX_LEGACY_MIGRATION_HISTORY_BYTES,
    )
    if (
        target.sha256 != context.payload["source_sha256"]
        or target.size != context.payload["source_size"]
    ):
        raise LegacyMigrationRecoveryError("legacy_migration_target_conflict")
    receipt_state = _receipt_state(context)
    if receipt_state == "conflict":
        raise LegacyMigrationRecoveryError("legacy_migration_receipt_conflict")
    if receipt_state == "absent":
        try:
            write_file_text_create_only(
                context.evidence_dir / EVIDENCE_RECEIPT_NAME,
                _receipt_text(context.payload, recovered=recovered),
                anchor=context.evidence_dir,
            )
        except FileExistsError:
            raise LegacyMigrationRecoveryError("legacy_migration_receipt_conflict") from None
        except OSError:
            raise LegacyMigrationExecutionIOError("legacy_migration_receipt_write_failed") from None
    final = classify_legacy_migration_recovery(project_dir)
    if final.status != "complete" or not final.can_recover:
        raise LegacyMigrationRecoveryError(
            final.blocked_reason or "legacy_migration_after_state_unverified"
        )
    try:
        unlink_artifact_file_if_matches(
            context.journal_path,
            context.journal_text,
            anchor=project_dir,
        )
    except OSError:
        raise LegacyMigrationExecutionIOError("legacy_migration_journal_cleanup_failed") from None
    return LegacyMigrationExecutionResult(
        status="recovered" if recovered else "completed",
        migration_id=str(context.payload["migration_id"]),
        run_id=str(context.payload["run_id"]),
        source_artifact=str(context.payload["source_artifact"]),
        target_artifact=str(context.payload["target_artifact"]),
        recovered=recovered,
    )
