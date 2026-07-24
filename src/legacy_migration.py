"""Read-only discovery for narrowly eligible legacy history migration.

This module deliberately performs no migration, cleanup, lock recovery, or
artifact creation.  It classifies one explicitly selected project directory and
builds a fixed, path-redacted report for later packages to consume.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .resume_safety import (
    INACCESSIBLE_RUN_ROOT,
    INVALID_RUN_ROOT,
    MISSING_RUN_ROOT,
    STALE_RUN_ROOT,
    UNSAFE_RUN_ROOT,
    validate_project_run_root,
)
from .round_attempts import classify_round_recovery
from .round_commit_recovery import (
    DIAGNOSTIC_FINALIZE_JOURNAL_NAME,
    ROUND_COMMIT_JOURNAL_NAME,
    RUN_FINALIZE_JOURNAL_NAME,
    RoundCommitRecoveryInspection,
    classify_diagnostic_finalize_recovery,
    classify_round_commit_recovery,
    classify_run_finalize_recovery,
)
from .run_config import RUN_CONFIG_SCHEMA_VERSION
from .runtime import is_pid_running
from .storage import (
    artifact_path_exists,
    artifact_path_is_safe,
    ensure_project_runtime_paths_safe,
    read_regular_text_bounded,
)

LEGACY_MIGRATION_REPORT_SCHEMA_VERSION = 1
LEGACY_MIGRATION_STATUSES = (
    "already_supported",
    "eligible_candidate",
    "not_migratable",
    "busy",
    "unsafe",
)
LEGACY_MIGRATION_REPORT_KEYS = (
    "schema_version",
    "operation",
    "status",
    "classification",
    "run_id",
    "completed_rounds",
    "source_artifact",
    "target_artifact",
    "source_sha256",
    "source_size",
    "reason_codes",
    "execution_authorized",
)
LEGACY_MIGRATION_CLASSIFICATIONS = (
    "current_transaction_pending",
    "already_transaction_eligible",
    "exact_missing_history_twin",
    "incomplete_history_evidence",
    "history_sequence_conflict",
    "history_value_conflict",
    "history_ahead_of_checkpoint",
    "history_checkpoint_conflict",
    "partial_history_uncorrelated",
    "journal_less_published_round",
    "canonical_without_provenance",
    "supported_empty_canonical",
    "attempt_state_owned",
    "attempt_evidence_conflict",
    "journal_less_finalize_split",
    "journal_less_diagnostic_split",
    "legacy_manifest_compatible",
    "unsafe_storage_identity",
    "unsafe_serialization",
    "unknown_schema",
    "run_identity_unavailable",
)
LEGACY_MIGRATION_REASON_CODES = frozenset(
    {
        "active_attempt_present",
        "attempt_limit_reached",
        "attempt_unverifiable",
        "canonical_attempt_conflict",
        "checkpoint_identity_invalid",
        "checkpoint_missing",
        "checkpoint_not_object",
        "checkpoint_run_identity_mismatch",
        "checkpoint_run_root_inaccessible",
        "checkpoint_run_root_invalid",
        "checkpoint_run_root_missing",
        "checkpoint_run_root_stale",
        "checkpoint_run_root_unsafe",
        "checkpoint_best_matches",
        "current_transaction_changed",
        "current_transaction_present",
        "diagnostic_artifacts_not_atomic",
        "exact_history_sequence",
        "finalization_metadata_conflict",
        "history_best_selection_differs",
        "history_overlapping_values_differ",
        "history_pair_already_present",
        "history_round_exceeds_checkpoint",
        "history_round_sequences_differ",
        "insufficient_disk_space",
        "invalid_current_transaction",
        "legacy_empty_canonical_present",
        "legacy_history_absent",
        "legacy_manifest_read_only_fallback",
        "legacy_partial_round_present",
        "live_run_lock",
        "next_round_state_unverifiable",
        "partial_history_exceeds_checkpoint_best",
        "publication_pending",
        "published_round_not_committed",
        "retained_attempt_budget_exceeded",
        "run_lock_invalid",
        "run_metadata_not_object",
        "single_history_not_exact",
        "staged_attempt_present",
        "target_history_missing",
        "unknown_artifact_schema",
        "unknown_transaction_schema",
        "unsafe_legacy_artifact_serialization",
        "unsafe_project_metadata",
        "unsafe_project_runtime",
        "unsafe_round_state",
        "unsafe_run_artifact_layout",
    }
)

MAX_LEGACY_METADATA_BYTES = 2 * 1024 * 1024
MAX_LEGACY_HISTORY_BYTES = 64 * 1024 * 1024
MAX_LEGACY_JSON_DEPTH = 128
_RUN_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class LegacyMigrationInspection:
    """Path-redacted result for one explicitly selected project."""

    status: str
    classification: str | None
    run_id: str | None = None
    completed_rounds: int | None = None
    source_artifact: str | None = None
    target_artifact: str | None = None
    source_sha256: str | None = None
    source_size: int | None = None
    reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class _JsonArtifact:
    present: bool
    value: object | None = None
    content: bytes | None = None


@dataclass(frozen=True)
class _History:
    artifact_name: str
    entries: tuple[dict[str, object], ...]
    content: bytes
    rounds: tuple[int | None, ...]

    @property
    def is_exact(self) -> bool:
        return bool(self.rounds) and self.rounds == tuple(range(1, len(self.rounds) + 1))

    @property
    def max_round(self) -> int | None:
        numeric = [value for value in self.rounds if value is not None]
        return max(numeric, default=None)


class _UnsafeSerialization(ValueError):
    pass


class _UnsafeLayout(OSError):
    pass


def build_legacy_migration_report(
    inspection: LegacyMigrationInspection,
) -> dict[str, object]:
    """Build the fixed JSON-compatible report without authorizing execution."""
    if inspection.status not in LEGACY_MIGRATION_STATUSES:
        raise ValueError("unknown legacy migration status")
    if (inspection.status == "busy") != (inspection.classification is None):
        raise ValueError("legacy migration status and classification disagree")
    if inspection.classification is not None and (
        inspection.classification not in LEGACY_MIGRATION_CLASSIFICATIONS
    ):
        raise ValueError("unknown legacy migration classification")
    supported = {
        "current_transaction_pending",
        "already_transaction_eligible",
        "supported_empty_canonical",
        "attempt_state_owned",
        "legacy_manifest_compatible",
    }
    expected_status = (
        "busy"
        if inspection.classification is None
        else "eligible_candidate"
        if inspection.classification == "exact_missing_history_twin"
        else "already_supported"
        if inspection.classification in supported
        else "unsafe"
        if inspection.classification in {"unsafe_storage_identity", "unsafe_serialization"}
        else "not_migratable"
    )
    if inspection.status != expected_status:
        raise ValueError("legacy migration status and classification disagree")
    if inspection.run_id is not None and (_RUN_ID_PATTERN.fullmatch(inspection.run_id) is None):
        raise ValueError("invalid legacy migration run id")
    if inspection.completed_rounds is not None and (
        type(inspection.completed_rounds) is not int
        or inspection.completed_rounds < 0
        or inspection.completed_rounds > 999999
    ):
        raise ValueError("invalid legacy migration completed round count")
    if inspection.source_artifact not in {None, "score_history", "round_metrics"}:
        raise ValueError("unknown legacy migration source artifact")
    if inspection.target_artifact not in {None, "score_history", "round_metrics"}:
        raise ValueError("unknown legacy migration target artifact")
    if inspection.source_sha256 is not None and (
        _SHA256_PATTERN.fullmatch(inspection.source_sha256) is None
    ):
        raise ValueError("invalid legacy migration source digest")
    if inspection.source_size is not None and (
        type(inspection.source_size) is not int
        or inspection.source_size < 0
        or inspection.source_size > MAX_LEGACY_HISTORY_BYTES
    ):
        raise ValueError("invalid legacy migration source size")
    if (inspection.source_sha256 is None) != (inspection.source_size is None):
        raise ValueError("legacy migration source evidence is incomplete")
    if (inspection.source_artifact is None) != (inspection.source_sha256 is None):
        raise ValueError("legacy migration source label and evidence disagree")
    if inspection.classification == "exact_missing_history_twin":
        if (
            inspection.status != "eligible_candidate"
            or inspection.source_artifact is None
            or inspection.target_artifact is None
            or inspection.source_artifact == inspection.target_artifact
        ):
            raise ValueError("eligible legacy migration candidate is incomplete")
    elif inspection.status == "eligible_candidate":
        raise ValueError("only exact missing history twins are eligible")
    if (
        not isinstance(inspection.reason_codes, tuple)
        or any(code not in LEGACY_MIGRATION_REASON_CODES for code in inspection.reason_codes)
        or len(inspection.reason_codes) > 8
    ):
        raise ValueError("invalid legacy migration reason codes")
    return {
        "schema_version": LEGACY_MIGRATION_REPORT_SCHEMA_VERSION,
        "operation": "legacy_history_migration_discovery",
        "status": inspection.status,
        "classification": inspection.classification,
        "run_id": inspection.run_id,
        "completed_rounds": inspection.completed_rounds,
        "source_artifact": inspection.source_artifact,
        "target_artifact": inspection.target_artifact,
        "source_sha256": inspection.source_sha256,
        "source_size": inspection.source_size,
        "reason_codes": list(inspection.reason_codes),
        "execution_authorized": False,
    }


def format_legacy_migration_report(inspection: LegacyMigrationInspection) -> str:
    """Render a bounded human report using only logical labels and public IDs."""
    report = build_legacy_migration_report(inspection)
    reason_codes = report["reason_codes"]
    assert isinstance(reason_codes, list)
    values = (
        ("status", report["status"]),
        ("classification", report["classification"] or "none"),
        ("run_id", report["run_id"] or "unavailable"),
        ("completed_rounds", report["completed_rounds"]),
        ("source_artifact", report["source_artifact"] or "none"),
        ("target_artifact", report["target_artifact"] or "none"),
        ("source_sha256", report["source_sha256"] or "none"),
        ("source_size", report["source_size"]),
        ("reason_codes", ",".join(reason_codes) if reason_codes else "none"),
        ("execution_authorized", "false"),
    )
    return "Legacy migration discovery\n" + "\n".join(
        f"{key}: {value if value is not None else 'none'}" for key, value in values
    )


def _result(
    status: str,
    classification: str | None,
    *,
    run_id: str | None = None,
    completed_rounds: int | None = None,
    source: _History | None = None,
    target_artifact: str | None = None,
    reasons: tuple[str, ...],
) -> LegacyMigrationInspection:
    return LegacyMigrationInspection(
        status=status,
        classification=classification,
        run_id=run_id,
        completed_rounds=completed_rounds,
        source_artifact=source.artifact_name if source is not None else None,
        target_artifact=target_artifact,
        source_sha256=(hashlib.sha256(source.content).hexdigest() if source is not None else None),
        source_size=len(source.content) if source is not None else None,
        reason_codes=reasons,
    )


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise _UnsafeSerialization("duplicate_object_key")
        value[key] = item
    return value


def _reject_nonfinite(_value: str) -> object:
    raise _UnsafeSerialization("nonfinite_number")


def _validate_json_depth(value: object) -> None:
    pending: list[tuple[object, int]] = [(value, 0)]
    while pending:
        current, depth = pending.pop()
        if depth > MAX_LEGACY_JSON_DEPTH:
            raise _UnsafeSerialization("json_depth_exceeded")
        if isinstance(current, dict):
            pending.extend((item, depth + 1) for item in current.values())
        elif isinstance(current, list):
            pending.extend((item, depth + 1) for item in current)


def _decode_json(content: bytes) -> object:
    try:
        text = content.decode("utf-8")
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite,
        )
        _validate_json_depth(value)
        return value
    except _UnsafeSerialization:
        raise
    except (UnicodeError, ValueError, RecursionError):
        raise _UnsafeSerialization("invalid_json") from None


def _read_optional_json(
    path: Path,
    *,
    anchor: Path,
    max_bytes: int,
) -> _JsonArtifact:
    if not artifact_path_is_safe(path, allow_missing=True, anchor=anchor):
        raise _UnsafeLayout("unsafe_artifact_path")
    if not artifact_path_exists(path, anchor=anchor):
        return _JsonArtifact(present=False)
    try:
        text = read_regular_text_bounded(path, max_bytes=max_bytes, anchor=anchor)
        content = text.encode("utf-8")
    except (UnicodeError, ValueError, RecursionError):
        raise _UnsafeSerialization("unsafe_artifact_content") from None
    except OSError:
        raise _UnsafeLayout("unsafe_artifact_read") from None
    return _JsonArtifact(
        present=True,
        value=_decode_json(content),
        content=content,
    )


def _read_history(path: Path, *, anchor: Path, artifact_name: str) -> _History | None:
    artifact = _read_optional_json(
        path,
        anchor=anchor,
        max_bytes=MAX_LEGACY_HISTORY_BYTES,
    )
    if not artifact.present:
        return None
    if not isinstance(artifact.value, list) or artifact.content is None:
        raise _UnsafeSerialization("history_root_not_list")
    entries: list[dict[str, object]] = []
    rounds: list[int | None] = []
    for raw_entry in artifact.value:
        if not isinstance(raw_entry, dict):
            raise _UnsafeSerialization("history_entry_not_object")
        entry = dict(raw_entry)
        entries.append(entry)
        round_value = entry.get("round")
        rounds.append(round_value if type(round_value) is int and round_value > 0 else None)
    return _History(
        artifact_name=artifact_name,
        entries=tuple(entries),
        content=artifact.content,
        rounds=tuple(rounds),
    )


def _journal_classification(project_dir: Path) -> LegacyMigrationInspection | None:
    journal_classifiers: tuple[
        tuple[str, str, Callable[[Path], RoundCommitRecoveryInspection]], ...
    ] = (
        (
            ROUND_COMMIT_JOURNAL_NAME,
            "round_commit",
            classify_round_commit_recovery,
        ),
        (
            RUN_FINALIZE_JOURNAL_NAME,
            "run_finalize",
            classify_run_finalize_recovery,
        ),
        (
            DIAGNOSTIC_FINALIZE_JOURNAL_NAME,
            "diagnostic_finalize",
            classify_diagnostic_finalize_recovery,
        ),
    )
    for journal_name, expected_kind, classifier in journal_classifiers:
        journal = _read_optional_json(
            project_dir / journal_name,
            anchor=project_dir,
            max_bytes=MAX_LEGACY_METADATA_BYTES,
        )
        if not journal.present:
            continue
        if (
            not isinstance(journal.value, dict)
            or type(journal.value.get("schema_version")) is not int
            or journal.value.get("schema_version") != 1
            or journal.value.get("kind") != expected_kind
        ):
            return _result(
                "not_migratable",
                "unknown_schema",
                reasons=("unknown_transaction_schema",),
            )
        inspection = classifier(project_dir)
        if inspection.status == "absent" or not inspection.journal_present:
            return _result(
                "unsafe",
                "unsafe_storage_identity",
                reasons=("current_transaction_changed",),
            )
        if inspection.status == "invalid":
            return _result(
                "unsafe",
                "unsafe_serialization",
                reasons=("invalid_current_transaction",),
            )
        return _result(
            "already_supported",
            "current_transaction_pending",
            run_id=(
                inspection.run_id
                if isinstance(inspection.run_id, str)
                and _RUN_ID_PATTERN.fullmatch(inspection.run_id)
                else None
            ),
            completed_rounds=inspection.round_index,
            reasons=("current_transaction_present",),
        )
    return None


def _strict_positive_int(value: object) -> int | None:
    if type(value) is int and value > 0:
        return value
    return None


def _strict_nonnegative_int(value: object) -> int | None:
    if type(value) is int and value >= 0:
        return value
    return None


def _finite_float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    candidate = float(value)
    return candidate if math.isfinite(candidate) else None


def _scores_match(left: object, right: object) -> bool:
    left_score = _finite_float(left)
    right_score = _finite_float(right)
    return (
        left_score is not None
        and right_score is not None
        and math.isclose(left_score, right_score, rel_tol=0.0, abs_tol=0.005)
    )


def _json_values_equal(left: object, right: object) -> bool:
    if isinstance(left, bool) ^ isinstance(right, bool):
        return False
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(
            _json_values_equal(left[key], right[key]) for key in left
        )
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            _json_values_equal(left_item, right_item)
            for left_item, right_item in zip(left, right, strict=True)
        )
    return left == right


def _histories_values_match(left: _History, right: _History) -> bool:
    for left_entry, right_entry in zip(left.entries, right.entries, strict=True):
        for key in left_entry.keys() & right_entry.keys():
            if key == "round":
                continue
            if key == "score":
                if not _scores_match(left_entry[key], right_entry[key]):
                    return False
            elif not _json_values_equal(left_entry[key], right_entry[key]):
                return False
    return True


def _successful_scores(history: _History) -> list[float]:
    scores: list[float] = []
    for entry in history.entries:
        if entry.get("successful_research_round") is False:
            continue
        score = _finite_float(entry.get("score"))
        if score is not None:
            scores.append(score)
    return scores


def _history_best_round(history: _History, best_score: float) -> int | None:
    matching: list[int] = []
    matching_improved: list[int] = []
    last_improved: int | None = None
    for entry, round_index in zip(history.entries, history.rounds, strict=True):
        if round_index is None or entry.get("successful_research_round") is False:
            continue
        score = _finite_float(entry.get("score"))
        if score is not None and math.isclose(
            score,
            best_score,
            rel_tol=0.0,
            abs_tol=0.005,
        ):
            matching.append(round_index)
            if entry.get("improved") is True:
                matching_improved.append(round_index)
        if entry.get("improved") is True:
            last_improved = round_index
    if matching_improved:
        return matching_improved[-1]
    if matching:
        return matching[0]
    return last_improved if best_score < 0 else None


def _best_round_from_path(value: object) -> int | None:
    if not isinstance(value, str) or not value:
        return None
    match = re.search(r"(?:^|[/\\])round_(\d{2,6})\Z", value)
    return int(match.group(1)) if match is not None else None


def _checkpoint_best_round(checkpoint: dict[str, object]) -> int | None:
    explicit = _strict_positive_int(checkpoint.get("best_round"))
    path_round = _best_round_from_path(checkpoint.get("best_round_path"))
    return explicit if explicit is not None else path_round


def _checkpoint_best_round_conflicts(checkpoint: dict[str, object]) -> bool:
    explicit = _strict_positive_int(checkpoint.get("best_round"))
    path_value = checkpoint.get("best_round_path")
    path_round = _best_round_from_path(path_value)
    return explicit is not None and path_round is not None and explicit != path_round


def _metadata_conflicts(
    metadata: tuple[dict[str, object], ...],
    *,
    run_id: str,
    completed_rounds: int,
    checkpoint_best_score: float | None,
    checkpoint_best_round: int | None,
) -> bool:
    for value in metadata:
        metadata_run_id = value.get("run_id")
        if metadata_run_id not in (None, "") and metadata_run_id != run_id:
            return True
        round_candidates = (
            value.get("completed_rounds"),
            value.get("last_completed_round"),
            value.get("round_count"),
        )
        for candidate in round_candidates:
            if candidate is not None and (_strict_nonnegative_int(candidate) != completed_rounds):
                return True
        metadata_best = value.get("best_score")
        if (
            metadata_best is not None
            and checkpoint_best_score is not None
            and not _scores_match(metadata_best, checkpoint_best_score)
        ):
            return True
        metadata_best_round = value.get("best_round")
        if metadata_best_round is not None and (
            checkpoint_best_round is None
            or _strict_positive_int(metadata_best_round) != checkpoint_best_round
        ):
            return True
    return False


def _lock_state(project_dir: Path) -> str:
    try:
        lock = _read_optional_json(
            project_dir / "active_run.json",
            anchor=project_dir,
            max_bytes=MAX_LEGACY_METADATA_BYTES,
        )
    except (_UnsafeLayout, _UnsafeSerialization):
        return "invalid"
    if not lock.present:
        return "absent"
    if not isinstance(lock.value, dict):
        return "invalid"
    pid_value = lock.value.get("pid")
    pid = _strict_positive_int(pid_value)
    if pid is None and isinstance(pid_value, str):
        normalized = pid_value.strip()
        if normalized.isascii() and normalized.isdigit():
            pid = _strict_positive_int(int(normalized))
    if pid is None:
        return "invalid"
    return "live" if is_pid_running(pid) else "stale"


def _map_next_round_state(
    run_root: Path,
    *,
    completed_rounds: int,
    run_id: str,
) -> LegacyMigrationInspection | None:
    try:
        recovery = classify_round_recovery(run_root, completed_rounds + 1)
    except (OSError, RuntimeError, ValueError):
        return _result(
            "not_migratable",
            "attempt_evidence_conflict",
            run_id=run_id,
            completed_rounds=completed_rounds,
            reasons=("next_round_state_unverifiable",),
        )
    mapping = {
        "published_uncommitted": (
            "journal_less_published_round",
            "published_round_not_committed",
        ),
        "legacy_partial": (
            "canonical_without_provenance",
            "legacy_partial_round_present",
        ),
        "legacy_empty_canonical": (
            "supported_empty_canonical",
            "legacy_empty_canonical_present",
        ),
        "attempt_in_progress": ("attempt_state_owned", "active_attempt_present"),
        "publication_pending": ("attempt_state_owned", "publication_pending"),
        "staged_partial": ("attempt_state_owned", "staged_attempt_present"),
        "canonical_attempt_conflict": (
            "attempt_evidence_conflict",
            "canonical_attempt_conflict",
        ),
        "attempt_unverifiable": (
            "attempt_evidence_conflict",
            "attempt_unverifiable",
        ),
        "attempt_limit_reached": (
            "attempt_evidence_conflict",
            "attempt_limit_reached",
        ),
        "unsafe_round_state": (
            "attempt_evidence_conflict",
            "unsafe_round_state",
        ),
        "retained_attempt_budget_exceeded": (
            "attempt_evidence_conflict",
            "retained_attempt_budget_exceeded",
        ),
        "insufficient_disk_space": (
            "attempt_evidence_conflict",
            "insufficient_disk_space",
        ),
    }
    selected = mapping.get(recovery.status)
    if selected is None:
        return None
    classification, reason = selected
    status = (
        "already_supported"
        if classification in {"supported_empty_canonical", "attempt_state_owned"}
        else "not_migratable"
    )
    return _result(
        status,
        classification,
        run_id=run_id,
        completed_rounds=completed_rounds,
        reasons=(reason,),
    )


def _unsafe_result(
    classification: str,
    *,
    reason: str,
) -> LegacyMigrationInspection:
    return _result(
        "unsafe" if classification != "run_identity_unavailable" else "not_migratable",
        classification,
        reasons=(reason,),
    )


def classify_legacy_history_migration(
    project_dir: Path,
) -> LegacyMigrationInspection:
    """Classify one selected project without mutating any local state."""
    try:
        project_dir = Path(project_dir).expanduser().absolute()
        ensure_project_runtime_paths_safe(project_dir, anchor=project_dir.parent)
        journal_result = _journal_classification(project_dir)
        if journal_result is not None:
            return journal_result
        checkpoint_artifact = _read_optional_json(
            project_dir / "checkpoint.json",
            anchor=project_dir,
            max_bytes=MAX_LEGACY_METADATA_BYTES,
        )
    except _UnsafeSerialization:
        return _unsafe_result("unsafe_serialization", reason="unsafe_project_metadata")
    except (OSError, RuntimeError, ValueError, _UnsafeLayout):
        return _unsafe_result("unsafe_storage_identity", reason="unsafe_project_runtime")

    if not checkpoint_artifact.present:
        return _unsafe_result(
            "run_identity_unavailable",
            reason="checkpoint_missing",
        )
    if not isinstance(checkpoint_artifact.value, dict):
        return _unsafe_result(
            "unsafe_serialization",
            reason="checkpoint_not_object",
        )
    checkpoint = checkpoint_artifact.value
    run_id_value = checkpoint.get("run_id")
    run_id = (
        run_id_value
        if isinstance(run_id_value, str) and _RUN_ID_PATTERN.fullmatch(run_id_value) is not None
        else None
    )
    completed_rounds = _strict_nonnegative_int(checkpoint.get("last_completed_round"))
    if run_id is None or completed_rounds is None or completed_rounds > 999999:
        return _unsafe_result(
            "run_identity_unavailable",
            reason="checkpoint_identity_invalid",
        )
    run_root, blocker = validate_project_run_root(
        project_dir=project_dir,
        run_root_value=checkpoint.get("run_root"),
        require_writable=False,
    )
    if blocker is not None or run_root is None or run_root.name != run_id:
        classification = (
            "unsafe_storage_identity"
            if blocker in {UNSAFE_RUN_ROOT, INVALID_RUN_ROOT, INACCESSIBLE_RUN_ROOT}
            else "run_identity_unavailable"
        )
        reason = {
            MISSING_RUN_ROOT: "checkpoint_run_root_missing",
            STALE_RUN_ROOT: "checkpoint_run_root_stale",
            UNSAFE_RUN_ROOT: "checkpoint_run_root_unsafe",
            INVALID_RUN_ROOT: "checkpoint_run_root_invalid",
            INACCESSIBLE_RUN_ROOT: "checkpoint_run_root_inaccessible",
        }.get(blocker, "checkpoint_run_identity_mismatch")
        return _unsafe_result(classification, reason=reason)

    lock_state = _lock_state(project_dir)
    if lock_state == "live":
        return _result(
            "busy",
            None,
            run_id=run_id,
            completed_rounds=completed_rounds,
            reasons=("live_run_lock",),
        )
    if lock_state == "invalid":
        return _result(
            "unsafe",
            "unsafe_serialization",
            run_id=run_id,
            completed_rounds=completed_rounds,
            reasons=("run_lock_invalid",),
        )

    try:
        run_summary_artifact = _read_optional_json(
            run_root / "run_summary.json",
            anchor=run_root,
            max_bytes=MAX_LEGACY_METADATA_BYTES,
        )
        run_config_artifact = _read_optional_json(
            run_root / "run_config.json",
            anchor=run_root,
            max_bytes=MAX_LEGACY_METADATA_BYTES,
        )
        run_manifest_artifact = _read_optional_json(
            run_root / "run_manifest.json",
            anchor=run_root,
            max_bytes=MAX_LEGACY_METADATA_BYTES,
        )
        score_history = _read_history(
            project_dir / "score_history.json",
            anchor=project_dir,
            artifact_name="score_history",
        )
        round_metrics = _read_history(
            run_root / "round_metrics.json",
            anchor=run_root,
            artifact_name="round_metrics",
        )
    except _UnsafeSerialization:
        return _result(
            "unsafe",
            "unsafe_serialization",
            run_id=run_id,
            completed_rounds=completed_rounds,
            reasons=("unsafe_legacy_artifact_serialization",),
        )
    except (_UnsafeLayout, OSError, RuntimeError, ValueError):
        return _result(
            "unsafe",
            "unsafe_storage_identity",
            run_id=run_id,
            completed_rounds=completed_rounds,
            reasons=("unsafe_run_artifact_layout",),
        )

    metadata_artifacts = (
        run_summary_artifact,
        run_config_artifact,
        run_manifest_artifact,
    )
    if any(
        artifact.present and not isinstance(artifact.value, dict) for artifact in metadata_artifacts
    ):
        return _result(
            "unsafe",
            "unsafe_serialization",
            run_id=run_id,
            completed_rounds=completed_rounds,
            reasons=("run_metadata_not_object",),
        )
    if (
        run_config_artifact.present
        and isinstance(run_config_artifact.value, dict)
        and (
            type(run_config_artifact.value.get("schema_version")) is not int
            or run_config_artifact.value.get("schema_version") != RUN_CONFIG_SCHEMA_VERSION
        )
    ):
        return _result(
            "not_migratable",
            "unknown_schema",
            run_id=run_id,
            completed_rounds=completed_rounds,
            reasons=("unknown_artifact_schema",),
        )
    metadata = tuple(
        artifact.value
        for artifact in metadata_artifacts
        if artifact.present and isinstance(artifact.value, dict)
    )
    checkpoint_best_score = _finite_float(checkpoint.get("best_score"))
    checkpoint_best_round = _checkpoint_best_round(checkpoint)
    metadata_conflict = _metadata_conflicts(
        metadata,
        run_id=run_id,
        completed_rounds=completed_rounds,
        checkpoint_best_score=checkpoint_best_score,
        checkpoint_best_round=checkpoint_best_round,
    )
    diagnostic_mode = any(value.get("mode") == "diagnostic" for value in metadata)

    histories = tuple(history for history in (score_history, round_metrics) if history is not None)
    if any(
        history.max_round is not None and history.max_round > completed_rounds
        for history in histories
    ):
        return _result(
            "not_migratable",
            "history_ahead_of_checkpoint",
            run_id=run_id,
            completed_rounds=completed_rounds,
            reasons=("history_round_exceeds_checkpoint",),
        )
    if diagnostic_mode and (
        metadata_conflict
        or len(histories) != 2
        or score_history is None
        or round_metrics is None
        or score_history.rounds != round_metrics.rounds
        or not _histories_values_match(score_history, round_metrics)
    ):
        return _result(
            "not_migratable",
            "journal_less_diagnostic_split",
            run_id=run_id,
            completed_rounds=completed_rounds,
            reasons=("diagnostic_artifacts_not_atomic",),
        )
    if metadata_conflict:
        return _result(
            "not_migratable",
            "journal_less_finalize_split",
            run_id=run_id,
            completed_rounds=completed_rounds,
            reasons=("finalization_metadata_conflict",),
        )

    if score_history is not None and round_metrics is not None:
        if score_history.rounds != round_metrics.rounds:
            return _result(
                "not_migratable",
                "history_sequence_conflict",
                run_id=run_id,
                completed_rounds=completed_rounds,
                reasons=("history_round_sequences_differ",),
            )
        if not _histories_values_match(score_history, round_metrics):
            return _result(
                "not_migratable",
                "history_value_conflict",
                run_id=run_id,
                completed_rounds=completed_rounds,
                reasons=("history_overlapping_values_differ",),
            )

    source = score_history or round_metrics
    if source is not None:
        successful_scores = _successful_scores(source)
        if source.is_exact and len(source.entries) == completed_rounds:
            source_best_score = max(successful_scores, default=None)
            source_best_round = (
                _history_best_round(source, source_best_score)
                if source_best_score is not None
                else None
            )
            if (
                _checkpoint_best_round_conflicts(checkpoint)
                or source_best_score is None
                or checkpoint_best_score is None
                or not math.isclose(
                    source_best_score,
                    checkpoint_best_score,
                    rel_tol=0.0,
                    abs_tol=0.005,
                )
                or (
                    checkpoint_best_round is not None and checkpoint_best_round != source_best_round
                )
            ):
                return _result(
                    "not_migratable",
                    "history_checkpoint_conflict",
                    run_id=run_id,
                    completed_rounds=completed_rounds,
                    reasons=("history_best_selection_differs",),
                )
        elif (
            successful_scores
            and checkpoint_best_score is not None
            and max(successful_scores) > checkpoint_best_score + 0.005
        ):
            return _result(
                "not_migratable",
                "partial_history_uncorrelated",
                run_id=run_id,
                completed_rounds=completed_rounds,
                reasons=("partial_history_exceeds_checkpoint_best",),
            )

    next_round_result = _map_next_round_state(
        run_root,
        completed_rounds=completed_rounds,
        run_id=run_id,
    )
    if next_round_result is not None:
        return next_round_result

    if not run_config_artifact.present and run_manifest_artifact.present and source is None:
        return _result(
            "already_supported",
            "legacy_manifest_compatible",
            run_id=run_id,
            completed_rounds=completed_rounds,
            reasons=("legacy_manifest_read_only_fallback",),
        )

    if score_history is not None and round_metrics is not None:
        if source.is_exact and len(source.entries) == completed_rounds:
            return _result(
                "already_supported",
                "already_transaction_eligible",
                run_id=run_id,
                completed_rounds=completed_rounds,
                reasons=("history_pair_already_present",),
            )
        return _result(
            "not_migratable",
            "partial_history_uncorrelated",
            run_id=run_id,
            completed_rounds=completed_rounds,
            reasons=("single_history_not_exact",),
        )
    if source is None:
        return _result(
            "not_migratable",
            "partial_history_uncorrelated",
            run_id=run_id,
            completed_rounds=completed_rounds,
            reasons=("legacy_history_absent",),
        )
    if not source.is_exact or len(source.entries) != completed_rounds:
        classification = (
            "partial_history_uncorrelated"
            if checkpoint_best_score is None
            else "incomplete_history_evidence"
        )
        return _result(
            "not_migratable",
            classification,
            run_id=run_id,
            completed_rounds=completed_rounds,
            source=source,
            reasons=("single_history_not_exact",),
        )

    target_artifact = (
        "round_metrics" if source.artifact_name == "score_history" else "score_history"
    )
    return _result(
        "eligible_candidate",
        "exact_missing_history_twin",
        run_id=run_id,
        completed_rounds=completed_rounds,
        source=source,
        target_artifact=target_artifact,
        reasons=(
            "exact_history_sequence",
            "checkpoint_best_matches",
            "target_history_missing",
        ),
    )
