"""Pure builders and a bounded codec for prepared round-commit journals.

This module deliberately performs no filesystem I/O. Runtime journal placement,
recovery, and commit routing are introduced by later ARA-055 packages.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .storage import (
    build_project_memory_text,
    build_research_state,
    build_score_history_text,
)

MAX_ROUND_COMMIT_JOURNAL_BYTES = 2 * 1024 * 1024
MAX_ROUND_COMMIT_JSON_DEPTH = 128
ROUND_COMMIT_ARTIFACT_NAMES = (
    "score_history",
    "round_metrics",
    "best_output",
    "memory",
    "research_state",
    "checkpoint",
)
RUN_FINALIZE_ARTIFACT_NAMES = (
    "run_summary",
    "run_config",
    "checkpoint",
)

_TOP_LEVEL_FIELD_NAMES = (
    "schema_version",
    "kind",
    "state",
    "transaction_id",
    "run_id",
    "run_root",
    "run_root_identity",
    "round",
    "attempt_id",
    "run_config_sha256",
    "round_metric",
    "artifacts",
)
_TOP_LEVEL_FIELDS = set(_TOP_LEVEL_FIELD_NAMES)
_DIGEST_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_TRANSACTION_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]{7,63}\Z")
_RUN_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_ARTIFACT_FIELD_NAMES = {
    "score_history": ("before_present", "before_sha256", "after_sha256"),
    "round_metrics": ("before_present", "before_sha256", "after_sha256"),
    "best_output": ("write", "before_present", "before_sha256", "after_sha256"),
    "memory": (
        "before_present",
        "before_sha256",
        "after_sha256",
        "after_text",
    ),
    "research_state": (
        "before_present",
        "before_sha256",
        "after_sha256",
        "after_value",
    ),
    "checkpoint": (
        "before_present",
        "before_sha256",
        "after_sha256",
        "after_value",
    ),
}
_ARTIFACT_FIELDS = {name: set(field_names) for name, field_names in _ARTIFACT_FIELD_NAMES.items()}


class RoundCommitCodecError(ValueError):
    """Raised when a round-commit builder or journal violates its contract."""


@dataclass(frozen=True)
class AfterImage:
    """An immutable, content-addressed artifact after-image."""

    text: str
    sha256: str
    value: Any


def _sha256_text(text: str) -> str:
    try:
        encoded = text.encode("utf-8")
    except UnicodeError as exc:
        raise RoundCommitCodecError("after-image text must be valid UTF-8") from exc
    return hashlib.sha256(encoded).hexdigest()


def _serialize_artifact_json(value: object) -> str:
    try:
        return json.dumps(value, indent=2, allow_nan=False)
    except (TypeError, ValueError, RecursionError) as exc:
        raise RoundCommitCodecError("after-image is not serializable JSON") from exc


def _validate_json_value(
    value: object,
    *,
    location: str = "value",
    depth: int = 0,
) -> None:
    if depth > MAX_ROUND_COMMIT_JSON_DEPTH:
        raise RoundCommitCodecError(
            f"{location} exceeds maximum JSON depth {MAX_ROUND_COMMIT_JSON_DEPTH}"
        )
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise RoundCommitCodecError(f"{location} contains a non-finite number")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise RoundCommitCodecError(f"{location} contains a non-string object key")
            _validate_json_value(
                item,
                location=f"{location}.{key}",
                depth=depth + 1,
            )
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_value(
                item,
                location=f"{location}[{index}]",
                depth=depth + 1,
            )
        return
    raise RoundCommitCodecError(f"{location} contains unsupported type {type(value).__name__}")


def _json_object_after_image(value: Mapping[str, object]) -> AfterImage:
    if not isinstance(value, dict):
        raise RoundCommitCodecError("after-image value must be a JSON object")
    _validate_json_value(value)
    copied = copy.deepcopy(value)
    text = _serialize_artifact_json(copied)
    return AfterImage(text=text, sha256=_sha256_text(text), value=copied)


def build_history_after_image(
    history: Sequence[Mapping[str, object]],
    round_metric: Mapping[str, object],
    *,
    round_index: int,
) -> AfterImage:
    """Build a deterministic score-history after-image for one appended round."""
    _validate_round(round_index, "round_index")
    if not isinstance(history, list):
        raise RoundCommitCodecError("history must be a JSON array")
    if not isinstance(round_metric, dict):
        raise RoundCommitCodecError("round_metric must be a JSON object")
    _validate_json_value(history, location="history")
    _validate_json_value(round_metric, location="round_metric")

    expected_round = 1
    for index, entry in enumerate(history):
        if not isinstance(entry, dict):
            raise RoundCommitCodecError(f"history[{index}] must be a JSON object")
        entry_round = entry.get("round")
        _validate_round(entry_round, f"history[{index}].round")
        if entry_round != expected_round:
            raise RoundCommitCodecError("history rounds must be consecutive and start at round 1")
        expected_round += 1
    if expected_round != round_index:
        raise RoundCommitCodecError("history must end immediately before the appended round")
    metric_round = round_metric.get("round")
    _validate_round(metric_round, "round_metric.round")
    if metric_round != round_index:
        raise RoundCommitCodecError("round_metric.round must match round_index")

    value = [*copy.deepcopy(history), copy.deepcopy(round_metric)]
    try:
        text = build_score_history_text(value)
    except (TypeError, ValueError, RecursionError) as exc:
        raise RoundCommitCodecError("history after-image is not serializable JSON") from exc
    return AfterImage(text=text, sha256=_sha256_text(text), value=value)


def build_best_output_after_image(revised_output: str) -> AfterImage:
    """Match the runner's existing stripped, newline-terminated best output."""
    if not isinstance(revised_output, str):
        raise RoundCommitCodecError("revised_output must be a string")
    text = revised_output.strip() + "\n"
    return AfterImage(text=text, sha256=_sha256_text(text), value=text)


def build_project_memory_after_image(
    existing: str,
    *,
    round_index: int,
    summary: Mapping[str, str],
) -> AfterImage:
    """Build memory.md bytes using the current storage policy."""
    _validate_round(round_index, "round_index")
    if not isinstance(existing, str):
        raise RoundCommitCodecError("existing memory must be a string")
    if not isinstance(summary, dict):
        raise RoundCommitCodecError("summary must be an object")
    expected_fields = {
        "strongest",
        "criticism",
        "unresolved",
        "next_action",
        "best_score",
    }
    if set(summary) != expected_fields or not all(
        isinstance(value, str) for value in summary.values()
    ):
        raise RoundCommitCodecError("summary must contain exactly the five string memory fields")
    text = build_project_memory_text(
        existing,
        round_index=round_index,
        summary=dict(summary),
    )
    return AfterImage(text=text, sha256=_sha256_text(text), value=text)


def build_research_state_after_image(
    *,
    round_index: int,
    best_score: float,
    revised_output: str,
    review_output: str,
    judge_output: str,
    topic_keywords: Sequence[str] | None = None,
) -> AfterImage:
    """Build the current research-state JSON after-image without writing it."""
    _validate_round(round_index, "round_index")
    if isinstance(best_score, bool) or not isinstance(best_score, (int, float)):
        raise RoundCommitCodecError("best_score must be a finite number")
    if not math.isfinite(float(best_score)):
        raise RoundCommitCodecError("best_score must be a finite number")
    for name, value in (
        ("revised_output", revised_output),
        ("review_output", review_output),
        ("judge_output", judge_output),
    ):
        if not isinstance(value, str):
            raise RoundCommitCodecError(f"{name} must be a string")
    if topic_keywords is not None and (
        isinstance(topic_keywords, (str, bytes))
        or not isinstance(topic_keywords, Sequence)
        or not all(isinstance(keyword, str) for keyword in topic_keywords)
    ):
        raise RoundCommitCodecError("topic_keywords must be a sequence of strings")
    value = build_research_state(
        round_index=round_index,
        best_score=best_score,
        revised_output=revised_output,
        review_output=review_output,
        judge_output=judge_output,
        topic_keywords=topic_keywords,
    )
    return _json_object_after_image(value)


def build_checkpoint_after_image(value: Mapping[str, object]) -> AfterImage:
    return _json_object_after_image(value)


def build_run_summary_after_image(value: Mapping[str, object]) -> AfterImage:
    return _json_object_after_image(value)


def build_run_config_after_image(value: Mapping[str, object]) -> AfterImage:
    return _json_object_after_image(value)


def _validate_round(value: object, location: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RoundCommitCodecError(f"{location} must be an integer")
    if not 1 <= value <= 999_999:
        raise RoundCommitCodecError(f"{location} must be between 1 and 999999")


def _require_exact_fields(
    value: object,
    expected: set[str],
    *,
    location: str,
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise RoundCommitCodecError(f"{location} must be a JSON object")
    if set(value) != expected:
        raise RoundCommitCodecError(f"{location} has missing or unknown fields")
    return value


def _validate_digest(value: object, location: str) -> str:
    if not isinstance(value, str) or _DIGEST_PATTERN.fullmatch(value) is None:
        raise RoundCommitCodecError(f"{location} must be a lowercase SHA-256 digest")
    return value


def _validate_artifact_record(
    artifact_name: str,
    value: object,
) -> dict[str, object]:
    record = _require_exact_fields(
        value,
        _ARTIFACT_FIELDS[artifact_name],
        location=f"artifacts.{artifact_name}",
    )
    before_present = record["before_present"]
    if type(before_present) is not bool:
        raise RoundCommitCodecError(f"artifacts.{artifact_name}.before_present must be boolean")
    before_digest = record["before_sha256"]
    if before_present:
        _validate_digest(
            before_digest,
            f"artifacts.{artifact_name}.before_sha256",
        )
    elif before_digest is not None:
        raise RoundCommitCodecError(
            f"artifacts.{artifact_name}.before_sha256 must be null when absent"
        )
    after_digest = _validate_digest(
        record["after_sha256"],
        f"artifacts.{artifact_name}.after_sha256",
    )

    if artifact_name == "best_output" and type(record["write"]) is not bool:
        raise RoundCommitCodecError("artifacts.best_output.write must be boolean")
    if artifact_name == "memory":
        after_text = record["after_text"]
        if not isinstance(after_text, str):
            raise RoundCommitCodecError("artifacts.memory.after_text must be a string")
        if _sha256_text(after_text) != after_digest:
            raise RoundCommitCodecError("artifacts.memory after-image digest mismatch")
    elif artifact_name in {"research_state", "checkpoint"}:
        after_value = record["after_value"]
        if not isinstance(after_value, dict):
            raise RoundCommitCodecError(
                f"artifacts.{artifact_name}.after_value must be a JSON object"
            )
        _validate_json_value(
            after_value,
            location=f"artifacts.{artifact_name}.after_value",
        )
        after_text = _serialize_artifact_json(after_value)
        if _sha256_text(after_text) != after_digest:
            raise RoundCommitCodecError(f"artifacts.{artifact_name} after-image digest mismatch")
    return record


def _validate_journal(value: object) -> dict[str, object]:
    payload = _require_exact_fields(value, _TOP_LEVEL_FIELDS, location="journal")
    _validate_json_value(payload, location="journal")
    if type(payload["schema_version"]) is not int or payload["schema_version"] != 1:
        raise RoundCommitCodecError("schema_version must be 1")
    if payload["kind"] != "round_commit":
        raise RoundCommitCodecError("kind must be round_commit")
    if payload["state"] != "prepared":
        raise RoundCommitCodecError("state must be prepared")

    for name in ("transaction_id", "attempt_id"):
        item = payload[name]
        if not isinstance(item, str) or _TRANSACTION_ID_PATTERN.fullmatch(item) is None:
            raise RoundCommitCodecError(f"{name} is invalid")

    run_id = payload["run_id"]
    if (
        not isinstance(run_id, str)
        or run_id in {".", ".."}
        or _RUN_ID_PATTERN.fullmatch(run_id) is None
    ):
        raise RoundCommitCodecError("run_id is invalid")
    run_root = payload["run_root"]
    if not isinstance(run_root, str) or not run_root or len(run_root) > 4096 or "\x00" in run_root:
        raise RoundCommitCodecError("run_root is invalid")
    run_root_identity = _require_exact_fields(
        payload["run_root_identity"],
        {
            "configured_storage",
            "device",
            "inode",
            "stat_identity_available",
        },
        location="run_root_identity",
    )
    configured_storage = run_root_identity["configured_storage"]
    identity_available = run_root_identity["stat_identity_available"]
    if type(configured_storage) is not bool:
        raise RoundCommitCodecError("run_root_identity.configured_storage must be boolean")
    if type(identity_available) is not bool:
        raise RoundCommitCodecError("run_root_identity.stat_identity_available must be boolean")
    for name in ("device", "inode"):
        identity_value = run_root_identity[name]
        if identity_available:
            if type(identity_value) is not int or identity_value < 0:
                raise RoundCommitCodecError(
                    f"run_root_identity.{name} must be a non-negative integer "
                    "when identity is available"
                )
        elif identity_value is not None:
            raise RoundCommitCodecError(
                f"run_root_identity.{name} must be null when identity is unavailable"
            )

    round_index = payload["round"]
    _validate_round(round_index, "round")
    _validate_digest(payload["run_config_sha256"], "run_config_sha256")

    round_metric = payload["round_metric"]
    if not isinstance(round_metric, dict):
        raise RoundCommitCodecError("round_metric must be a JSON object")
    metric_round = round_metric.get("round")
    _validate_round(metric_round, "round_metric.round")
    if metric_round != round_index:
        raise RoundCommitCodecError("round_metric.round must match round")

    artifacts = _require_exact_fields(
        payload["artifacts"],
        set(ROUND_COMMIT_ARTIFACT_NAMES),
        location="artifacts",
    )
    for artifact_name in ROUND_COMMIT_ARTIFACT_NAMES:
        _validate_artifact_record(artifact_name, artifacts[artifact_name])
    return payload


def encode_round_commit_journal(payload: Mapping[str, object]) -> str:
    """Validate and deterministically encode a prepared round-commit journal."""
    if not isinstance(payload, dict):
        raise RoundCommitCodecError("journal must be a JSON object")
    _validate_journal(payload)
    ordered_payload = {
        name: copy.deepcopy(payload[name]) for name in _TOP_LEVEL_FIELD_NAMES if name != "artifacts"
    }
    source_artifacts = payload["artifacts"]
    assert isinstance(source_artifacts, dict)
    ordered_payload["artifacts"] = {
        artifact_name: {
            field_name: copy.deepcopy(source_artifacts[artifact_name][field_name])
            for field_name in _ARTIFACT_FIELD_NAMES[artifact_name]
        }
        for artifact_name in ROUND_COMMIT_ARTIFACT_NAMES
    }
    try:
        encoded = json.dumps(
            ordered_payload,
            indent=2,
            allow_nan=False,
        )
    except (TypeError, ValueError, RecursionError) as exc:
        raise RoundCommitCodecError("journal could not be encoded") from exc
    if len(encoded.encode("utf-8")) > MAX_ROUND_COMMIT_JOURNAL_BYTES:
        raise RoundCommitCodecError("journal exceeds maximum encoded size")
    return encoded


def _reject_constant(value: str) -> None:
    raise RoundCommitCodecError(f"invalid JSON numeric constant: {value}")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise RoundCommitCodecError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def decode_round_commit_journal(data: str | bytes) -> dict[str, object]:
    """Decode a strict UTF-8 journal after enforcing its raw byte bound."""
    if isinstance(data, bytes):
        raw = data
    elif isinstance(data, str):
        try:
            raw = data.encode("utf-8")
        except UnicodeError as exc:
            raise RoundCommitCodecError("journal is not valid UTF-8") from exc
    else:
        raise RoundCommitCodecError("journal input must be text or bytes")
    if len(raw) > MAX_ROUND_COMMIT_JOURNAL_BYTES:
        raise RoundCommitCodecError("journal exceeds maximum encoded size")
    try:
        text = raw.decode("utf-8", errors="strict")
        value = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except RoundCommitCodecError:
        raise
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise RoundCommitCodecError("journal is not valid strict JSON") from exc
    payload = _validate_journal(value)
    return copy.deepcopy(payload)


_RUN_FINALIZE_TOP_LEVEL_FIELD_NAMES = (
    "schema_version",
    "kind",
    "state",
    "transaction_id",
    "run_id",
    "run_root",
    "run_root_identity",
    "artifacts",
)
_RUN_FINALIZE_TOP_LEVEL_FIELDS = set(_RUN_FINALIZE_TOP_LEVEL_FIELD_NAMES)
_RUN_FINALIZE_ARTIFACT_FIELD_NAMES = (
    "before_present",
    "before_sha256",
    "after_sha256",
    "after_value",
)
_RUN_FINALIZE_ARTIFACT_FIELDS = set(_RUN_FINALIZE_ARTIFACT_FIELD_NAMES)


def _validate_run_identity_fields(payload: Mapping[str, object]) -> None:
    run_id = payload["run_id"]
    if (
        not isinstance(run_id, str)
        or run_id in {".", ".."}
        or _RUN_ID_PATTERN.fullmatch(run_id) is None
    ):
        raise RoundCommitCodecError("run_id is invalid")
    run_root = payload["run_root"]
    if not isinstance(run_root, str) or not run_root or len(run_root) > 4096 or "\x00" in run_root:
        raise RoundCommitCodecError("run_root is invalid")
    run_root_identity = _require_exact_fields(
        payload["run_root_identity"],
        {
            "configured_storage",
            "device",
            "inode",
            "stat_identity_available",
        },
        location="run_root_identity",
    )
    configured_storage = run_root_identity["configured_storage"]
    identity_available = run_root_identity["stat_identity_available"]
    if type(configured_storage) is not bool:
        raise RoundCommitCodecError("run_root_identity.configured_storage must be boolean")
    if type(identity_available) is not bool:
        raise RoundCommitCodecError("run_root_identity.stat_identity_available must be boolean")
    for name in ("device", "inode"):
        identity_value = run_root_identity[name]
        if identity_available:
            if type(identity_value) is not int or identity_value < 0:
                raise RoundCommitCodecError(
                    f"run_root_identity.{name} must be a non-negative integer "
                    "when identity is available"
                )
        elif identity_value is not None:
            raise RoundCommitCodecError(
                f"run_root_identity.{name} must be null when identity is unavailable"
            )


def _validate_run_finalize_artifact_record(
    artifact_name: str,
    value: object,
) -> dict[str, object]:
    record = _require_exact_fields(
        value,
        _RUN_FINALIZE_ARTIFACT_FIELDS,
        location=f"artifacts.{artifact_name}",
    )
    before_present = record["before_present"]
    if type(before_present) is not bool:
        raise RoundCommitCodecError(f"artifacts.{artifact_name}.before_present must be boolean")
    before_digest = record["before_sha256"]
    if before_present:
        _validate_digest(before_digest, f"artifacts.{artifact_name}.before_sha256")
    elif before_digest is not None:
        raise RoundCommitCodecError(
            f"artifacts.{artifact_name}.before_sha256 must be null when absent"
        )
    after_digest = _validate_digest(
        record["after_sha256"],
        f"artifacts.{artifact_name}.after_sha256",
    )
    after_value = record["after_value"]
    if not isinstance(after_value, dict):
        raise RoundCommitCodecError(f"artifacts.{artifact_name}.after_value must be a JSON object")
    _validate_json_value(
        after_value,
        location=f"artifacts.{artifact_name}.after_value",
    )
    if _sha256_text(_serialize_artifact_json(after_value)) != after_digest:
        raise RoundCommitCodecError(f"artifacts.{artifact_name} after-image digest mismatch")
    return record


def _validate_run_finalize_journal(value: object) -> dict[str, object]:
    payload = _require_exact_fields(
        value,
        _RUN_FINALIZE_TOP_LEVEL_FIELDS,
        location="journal",
    )
    _validate_json_value(payload, location="journal")
    if type(payload["schema_version"]) is not int or payload["schema_version"] != 1:
        raise RoundCommitCodecError("schema_version must be 1")
    if payload["kind"] != "run_finalize":
        raise RoundCommitCodecError("kind must be run_finalize")
    if payload["state"] != "prepared":
        raise RoundCommitCodecError("state must be prepared")
    transaction_id = payload["transaction_id"]
    if (
        not isinstance(transaction_id, str)
        or _TRANSACTION_ID_PATTERN.fullmatch(transaction_id) is None
    ):
        raise RoundCommitCodecError("transaction_id is invalid")
    _validate_run_identity_fields(payload)

    artifacts = _require_exact_fields(
        payload["artifacts"],
        set(RUN_FINALIZE_ARTIFACT_NAMES),
        location="artifacts",
    )
    for artifact_name in RUN_FINALIZE_ARTIFACT_NAMES:
        _validate_run_finalize_artifact_record(
            artifact_name,
            artifacts[artifact_name],
        )
    return payload


def encode_run_finalize_journal(payload: Mapping[str, object]) -> str:
    """Validate and deterministically encode a prepared run-finalization journal."""
    if not isinstance(payload, dict):
        raise RoundCommitCodecError("journal must be a JSON object")
    _validate_run_finalize_journal(payload)
    ordered_payload = {
        name: copy.deepcopy(payload[name])
        for name in _RUN_FINALIZE_TOP_LEVEL_FIELD_NAMES
        if name != "artifacts"
    }
    source_artifacts = payload["artifacts"]
    assert isinstance(source_artifacts, dict)
    ordered_payload["artifacts"] = {
        artifact_name: {
            field_name: copy.deepcopy(source_artifacts[artifact_name][field_name])
            for field_name in _RUN_FINALIZE_ARTIFACT_FIELD_NAMES
        }
        for artifact_name in RUN_FINALIZE_ARTIFACT_NAMES
    }
    try:
        encoded = json.dumps(ordered_payload, indent=2, allow_nan=False)
    except (TypeError, ValueError, RecursionError) as exc:
        raise RoundCommitCodecError("journal could not be encoded") from exc
    if len(encoded.encode("utf-8")) > MAX_ROUND_COMMIT_JOURNAL_BYTES:
        raise RoundCommitCodecError("journal exceeds maximum encoded size")
    return encoded


def decode_run_finalize_journal(data: str | bytes) -> dict[str, object]:
    """Decode a strict bounded run-finalization journal."""
    if isinstance(data, bytes):
        raw = data
    elif isinstance(data, str):
        try:
            raw = data.encode("utf-8")
        except UnicodeError as exc:
            raise RoundCommitCodecError("journal is not valid UTF-8") from exc
    else:
        raise RoundCommitCodecError("journal input must be text or bytes")
    if len(raw) > MAX_ROUND_COMMIT_JOURNAL_BYTES:
        raise RoundCommitCodecError("journal exceeds maximum encoded size")
    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except RoundCommitCodecError:
        raise
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise RoundCommitCodecError("journal is not valid strict JSON") from exc
    return copy.deepcopy(_validate_run_finalize_journal(value))
