"""Iterative round runner for the local research pipeline."""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from rich.console import Console

from .agents import ResearchAgents
from .cloud_free import CloudFreeDailyQuotaExhausted, next_pacific_reset_heuristic
from .config import (
    DEFAULT_DRAFTING_MODE,
    DRAFTING_MODE_BEST_GUIDED,
    DRAFTING_MODE_CONTINUE_FROM_PREVIOUS,
    DRAFTING_MODE_FRESH_WITH_REVIEW,
)
from .constants import (
    STOP_CLOUD_DAILY_QUOTA,
    STOP_EXCEPTION,
    STOP_INVALID_SCORE,
    STOP_MANUAL_INTERRUPT,
    STOP_MAX_ROUNDS,
    STOP_NO_IMPROVEMENT,
    STOP_OLLAMA_TIMEOUT,
    STOP_PROMPT_TOO_LARGE,
    STOP_PROVIDER_QUOTA_EXHAUSTED,
    STOP_USER_REQUESTED,
)
from .judge_output import parse_judge_rubric
from .metrics import (
    build_agent_io_metrics,
    build_round_evolution_metrics,
    summarize_agent_io_metrics,
    summarize_round_metrics,
)
from .resume_safety import (
    RESUME_PATH_MESSAGES,
    UNSAFE_ARTIFACT_PATH,
    UNSAFE_ROUND_PATH,
    resume_artifact_links_are_safe,
    validate_resume_round_dir,
    validate_resume_run_root,
)
from .run_config import (
    INHERIT_GIT_ROOT,
    GitRootSetting,
    InvalidRunConfigError,
    build_initial_run_config,
    finalize_run_config,
    read_run_config,
)
from .runtime import log_run as _log
from .runtime import stop_requested as _stop_requested
from .storage import (
    append_log_line,
    display_path,
    ensure_project_runtime_paths_safe,
    get_memory_for_prompt,
    list_artifact_entry_names,
    make_round_dir,
    make_run_root,
    parse_score,
    read_json_file,
    read_regular_text,
    read_text,
    save_round_outputs,
    summarize_round_memory,
    unlink_artifact_file,
    update_project_memory,
    update_research_state,
    write_file_text,
    write_interrupted_report,
    write_json_file,
    write_score_history,
    write_text,
)


class ResumeHistoryError(ValueError):
    """Raised before writes when existing resume state is unsafe to append to."""


_MAX_RESUME_JSON_DEPTH = 128
_RESUME_STARTUP_TRANSACTION_NAME = ".resume_startup_transaction.json"
_RESUME_STARTUP_TRANSACTION_KIND = "resume_startup_metadata"
_RESUME_STARTUP_TRANSACTION_SCHEMA_VERSION = 1
_RESUME_STARTUP_ARTIFACT_NAMES = ("run_config.json", "run_manifest.json")


def _resume_json_nesting_is_safe(value: Any) -> bool:
    pending: list[tuple[Any, int]] = [(value, 0)]
    while pending:
        current, depth = pending.pop()
        if depth > _MAX_RESUME_JSON_DEPTH:
            return False
        if isinstance(current, dict):
            pending.extend((nested, depth + 1) for nested in current.values())
        elif isinstance(current, list):
            pending.extend((nested, depth + 1) for nested in current)
    return True


def _validate_pending_resume_round_dir(run_root: Path, round_index: int) -> Path:
    round_dir, path_error = validate_resume_round_dir(
        run_root=run_root,
        round_dir=run_root / f"round_{round_index:02d}",
        require_writable=True,
    )
    if path_error or round_dir is None:
        raise ResumeHistoryError(RESUME_PATH_MESSAGES[path_error or UNSAFE_ROUND_PATH])
    try:
        has_entries = bool(list_artifact_entry_names(round_dir, missing_ok=True))
    except OSError:
        raise ResumeHistoryError("pending round directory cannot be inspected safely") from None
    if has_entries:
        raise ResumeHistoryError(
            f"pending round {round_index} directory already contains files; resume is blocked"
        )
    return round_dir


def _history_round_number(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if math.isfinite(value) and value.is_integer() else None
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _history_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        result = float(value)
        return result if math.isfinite(result) else None
    try:
        result = float(str(value))
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _read_resume_history(path: Path, *, start_round: int) -> List[Dict[str, Any]] | None:
    try:
        payload = json.loads(read_regular_text(path))
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        raise ResumeHistoryError(f"{path.name} is unreadable or invalid JSON") from exc
    if not isinstance(payload, list):
        raise ResumeHistoryError(f"{path.name} must contain a JSON array")
    if not _resume_json_nesting_is_safe(payload):
        raise ResumeHistoryError(f"{path.name} exceeds the supported JSON nesting depth")

    history: List[Dict[str, Any]] = []
    previous_round = 0
    for entry in payload:
        if not isinstance(entry, dict):
            raise ResumeHistoryError(f"{path.name} contains a non-object entry")
        round_number = _history_round_number(entry.get("round"))
        if round_number is None or round_number < 1:
            raise ResumeHistoryError(f"{path.name} contains an invalid round number")
        if round_number <= previous_round:
            raise ResumeHistoryError(f"{path.name} rounds must be strictly increasing")
        if round_number >= start_round:
            raise ResumeHistoryError(
                f"{path.name} already contains round {round_number}, which is not before "
                f"resume round {start_round}"
            )
        history.append(dict(entry))
        previous_round = round_number
    return history


def _read_resume_round_text(path: Path) -> str:
    try:
        return read_regular_text(path, missing_ok=True).strip()
    except FileNotFoundError:
        return ""
    except (OSError, UnicodeError):
        raise ResumeHistoryError(f"{path.name} is unreadable or invalid UTF-8") from None


def _read_resume_manifest(path: Path, *, canonical_run_id: str) -> Optional[Dict[str, Any]]:
    try:
        payload = json.loads(read_regular_text(path))
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        raise ResumeHistoryError(f"{path.name} is unreadable or invalid JSON") from exc
    if not isinstance(payload, dict):
        raise ResumeHistoryError(f"{path.name} must contain a JSON object")
    if not _resume_json_nesting_is_safe(payload):
        raise ResumeHistoryError(f"{path.name} exceeds the supported JSON nesting depth")

    manifest_run_id = payload.get("run_id")
    if manifest_run_id not in (None, "") and (
        not isinstance(manifest_run_id, str) or manifest_run_id != canonical_run_id
    ):
        raise ResumeHistoryError(f"{path.name} run_id does not match the canonical run directory")
    manifest_resume_metadata = payload.get("resume_metadata")
    if manifest_resume_metadata is not None and not isinstance(manifest_resume_metadata, dict):
        raise ResumeHistoryError(f"{path.name} resume_metadata must contain a JSON object")
    return dict(payload)


def _startup_text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read_startup_artifact_text(path: Path) -> tuple[bool, str]:
    try:
        return True, read_regular_text(path)
    except FileNotFoundError:
        return False, ""
    except (OSError, UnicodeError):
        raise ResumeHistoryError(
            "resume startup metadata is unreadable; manual recovery is required"
        ) from None


def _read_resume_startup_transaction(
    *,
    run_root: Path,
    run_id: str,
) -> Dict[str, Any] | None:
    transaction_path = run_root / _RESUME_STARTUP_TRANSACTION_NAME
    try:
        text = read_regular_text(transaction_path)
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError):
        raise ResumeHistoryError(
            "resume startup transaction is unreadable; manual recovery is required"
        ) from None
    try:
        payload = json.loads(text)
    except (ValueError, RecursionError):
        raise ResumeHistoryError(
            "resume startup transaction is invalid; manual recovery is required"
        ) from None
    if not isinstance(payload, dict) or not _resume_json_nesting_is_safe(payload):
        raise ResumeHistoryError(
            "resume startup transaction is invalid; manual recovery is required"
        )
    if (
        set(payload) != {"schema_version", "kind", "state", "run_id", "artifacts"}
        or type(payload.get("schema_version")) is not int
        or payload.get("schema_version") != _RESUME_STARTUP_TRANSACTION_SCHEMA_VERSION
        or payload.get("kind") != _RESUME_STARTUP_TRANSACTION_KIND
        or payload.get("state") != "prepared"
        or payload.get("run_id") != run_id
    ):
        raise ResumeHistoryError(
            "resume startup transaction is invalid; manual recovery is required"
        )
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != set(_RESUME_STARTUP_ARTIFACT_NAMES):
        raise ResumeHistoryError(
            "resume startup transaction is invalid; manual recovery is required"
        )
    for artifact_name in _RESUME_STARTUP_ARTIFACT_NAMES:
        record = artifacts.get(artifact_name)
        if not isinstance(record, dict) or set(record) != {
            "before_present",
            "before_text",
            "before_sha256",
            "after_sha256",
        }:
            raise ResumeHistoryError(
                "resume startup transaction is invalid; manual recovery is required"
            )
        before_present = record.get("before_present")
        before_text = record.get("before_text")
        before_sha256 = record.get("before_sha256")
        after_sha256 = record.get("after_sha256")
        if type(before_present) is not bool or not isinstance(before_text, str):
            raise ResumeHistoryError(
                "resume startup transaction is invalid; manual recovery is required"
            )
        expected_before_sha256 = _startup_text_sha256(before_text) if before_present else None
        if (
            (not before_present and before_text)
            or before_sha256 != expected_before_sha256
            or not isinstance(after_sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", after_sha256) is None
        ):
            raise ResumeHistoryError(
                "resume startup transaction is invalid; manual recovery is required"
            )
    return payload


def _restore_resume_startup_transaction(
    *,
    run_root: Path,
    payload: Dict[str, Any],
    transaction_missing_ok: bool,
) -> None:
    artifacts = payload["artifacts"]
    current_states: Dict[str, tuple[bool, str]] = {}
    for artifact_name in _RESUME_STARTUP_ARTIFACT_NAMES:
        artifact_path = run_root / artifact_name
        present, text = _read_startup_artifact_text(artifact_path)
        current_sha256 = _startup_text_sha256(text) if present else None
        record = artifacts[artifact_name]
        if current_sha256 not in {record["before_sha256"], record["after_sha256"]}:
            raise ResumeHistoryError(
                "resume startup metadata changed outside its transaction; "
                "manual recovery is required"
            )
        current_states[artifact_name] = (present, text)

    try:
        for artifact_name in _RESUME_STARTUP_ARTIFACT_NAMES:
            artifact_path = run_root / artifact_name
            record = artifacts[artifact_name]
            if record["before_present"]:
                if current_states[artifact_name] != (True, record["before_text"]):
                    write_file_text(artifact_path, record["before_text"])
            elif current_states[artifact_name][0]:
                unlink_artifact_file(artifact_path, missing_ok=True)
        unlink_artifact_file(
            run_root / _RESUME_STARTUP_TRANSACTION_NAME,
            missing_ok=transaction_missing_ok,
        )
    except (OSError, UnicodeError):
        raise ResumeHistoryError(
            "resume startup metadata recovery is incomplete; retry resume to recover"
        ) from None


def _recover_resume_startup_transaction(*, run_root: Path, run_id: str) -> bool:
    payload = _read_resume_startup_transaction(run_root=run_root, run_id=run_id)
    if payload is None:
        return False
    _restore_resume_startup_transaction(
        run_root=run_root,
        payload=payload,
        transaction_missing_ok=False,
    )
    return True


def _write_resume_startup_metadata(
    *,
    run_root: Path,
    run_id: str,
    run_config: Dict[str, Any],
    run_manifest: Dict[str, Any],
) -> None:
    if _read_resume_startup_transaction(run_root=run_root, run_id=run_id) is not None:
        raise ResumeHistoryError(
            "resume startup transaction is still pending; retry resume to recover"
        )
    payloads = {
        "run_config.json": run_config,
        "run_manifest.json": run_manifest,
    }
    artifacts: Dict[str, Any] = {}
    for artifact_name in _RESUME_STARTUP_ARTIFACT_NAMES:
        before_present, before_text = _read_startup_artifact_text(run_root / artifact_name)
        after_text = json.dumps(payloads[artifact_name], indent=2)
        artifacts[artifact_name] = {
            "before_present": before_present,
            "before_text": before_text,
            "before_sha256": _startup_text_sha256(before_text) if before_present else None,
            "after_sha256": _startup_text_sha256(after_text),
        }
    transaction_path = run_root / _RESUME_STARTUP_TRANSACTION_NAME
    transaction = {
        "schema_version": _RESUME_STARTUP_TRANSACTION_SCHEMA_VERSION,
        "kind": _RESUME_STARTUP_TRANSACTION_KIND,
        "state": "prepared",
        "run_id": run_id,
        "artifacts": artifacts,
    }
    try:
        write_json_file(transaction_path, transaction)
        for artifact_name in _RESUME_STARTUP_ARTIFACT_NAMES:
            write_json_file(run_root / artifact_name, payloads[artifact_name])
        unlink_artifact_file(transaction_path, missing_ok=False)
    except BaseException:
        try:
            pending_transaction = _read_resume_startup_transaction(
                run_root=run_root,
                run_id=run_id,
            )
            if pending_transaction is not None and pending_transaction != transaction:
                raise ResumeHistoryError(
                    "resume startup transaction changed while it was active; "
                    "manual recovery is required"
                )
            _restore_resume_startup_transaction(
                run_root=run_root,
                payload=transaction,
                transaction_missing_ok=pending_transaction is None,
            )
        except ResumeHistoryError:
            raise
        raise


def _build_run_manifest(
    *,
    existing_manifest: Optional[Dict[str, Any]],
    existing_run_config: Dict[str, Any],
    resumes_existing_run: bool,
    run_id: str,
    run_root: Path,
    mode: str,
    model_name: str,
    drafting_mode: str,
    started_at: str,
    project_metadata: Optional[Dict[str, Any]],
    run_config_path: Path,
    resume_metadata: Dict[str, Any],
) -> Dict[str, Any]:
    manifest = dict(existing_manifest or {})
    defaults: Dict[str, Any] = {}
    if not resumes_existing_run:
        defaults = {
            "mode": mode,
            "model": model_name,
            "drafting_mode": drafting_mode,
            "started_at": started_at,
            "project": project_metadata or {},
        }
    elif existing_manifest is None and existing_run_config:
        for key in ("mode", "drafting_mode", "started_at", "project"):
            if key in existing_run_config:
                defaults[key] = existing_run_config[key]
        existing_model = existing_run_config.get("model")
        if isinstance(existing_model, dict):
            original_model_name = existing_model.get("name") or existing_model.get("label")
            if original_model_name not in (None, ""):
                defaults["model"] = str(original_model_name)
    for key, value in defaults.items():
        manifest.setdefault(key, value)

    merged_resume_metadata = dict(manifest.get("resume_metadata") or {})
    merged_resume_metadata.update(resume_metadata)
    manifest.update(
        {
            "run_id": run_id,
            "run_root": str(run_root),
            "run_config": str(run_config_path),
            "resume_metadata": merged_resume_metadata,
        }
    )
    return manifest


def _resume_json_values_equal(left: Any, right: Any) -> bool:
    if isinstance(left, bool) ^ isinstance(right, bool):
        return False
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(
            _resume_json_values_equal(left[key], right[key]) for key in left
        )
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            _resume_json_values_equal(left_item, right_item)
            for left_item, right_item in zip(left, right, strict=True)
        )
    return left == right


def _load_resume_histories(
    *,
    score_history_path: Path,
    round_metrics_path: Path,
    start_round: int,
    checkpoint_best_score: float | None = None,
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    existing_round_metrics = _read_resume_history(round_metrics_path, start_round=start_round)
    existing_score_history = _read_resume_history(score_history_path, start_round=start_round)

    if existing_round_metrics is not None and existing_score_history is not None:
        metric_rounds = [
            _history_round_number(entry.get("round")) for entry in existing_round_metrics
        ]
        score_rounds = [
            _history_round_number(entry.get("round")) for entry in existing_score_history
        ]
        if metric_rounds != score_rounds:
            raise ResumeHistoryError(
                "round_metrics.json and score_history.json contain different round sequences"
            )
        for metric_entry, score_entry, round_number in zip(
            existing_round_metrics,
            existing_score_history,
            metric_rounds,
            strict=True,
        ):
            for key in sorted(metric_entry.keys() & score_entry.keys()):
                if key == "round":
                    continue
                metric_value = metric_entry[key]
                score_history_value = score_entry[key]
                values_match = _resume_json_values_equal(metric_value, score_history_value)
                if key == "score":
                    metric_score = _history_float(metric_value)
                    score_history_score = _history_float(score_history_value)
                    values_match = (
                        metric_score is not None
                        and score_history_score is not None
                        and math.isclose(
                            metric_score,
                            score_history_score,
                            rel_tol=0.0,
                            abs_tol=0.005,
                        )
                    )
                if not values_match:
                    raise ResumeHistoryError(
                        "round_metrics.json and score_history.json disagree on "
                        f"{key} for round {round_number}"
                    )

    if existing_round_metrics is None and existing_score_history is not None and start_round > 1:
        fallback_rounds = [
            _history_round_number(entry.get("round")) for entry in existing_score_history
        ]
        fallback_last_round = fallback_rounds[-1] if fallback_rounds else None
        if fallback_last_round != start_round - 1:
            raise ResumeHistoryError(
                "score_history.json cannot be correlated with the checkpoint's last round"
            )
        fallback_scores = [
            score
            for entry in existing_score_history
            if entry.get("successful_research_round") is not False
            and (score := _history_float(entry.get("score"))) is not None
        ]
        if existing_score_history and not fallback_scores:
            raise ResumeHistoryError(
                "score_history.json has no numeric scores for checkpoint correlation"
            )
        if fallback_scores and checkpoint_best_score is None:
            raise ResumeHistoryError(
                "score_history.json cannot be correlated without a checkpoint best_score"
            )
        fallback_is_complete = len(fallback_rounds) == start_round - 1 and all(
            round_number == index for index, round_number in enumerate(fallback_rounds, start=1)
        )
        fallback_best_score = max(fallback_scores, default=None)
        if (
            fallback_is_complete
            and fallback_best_score is not None
            and checkpoint_best_score is not None
            and not math.isclose(
                fallback_best_score,
                checkpoint_best_score,
                rel_tol=0.0,
                abs_tol=0.005,
            )
        ):
            raise ResumeHistoryError(
                "complete score_history.json does not match the checkpoint best_score"
            )
        if (
            not fallback_is_complete
            and fallback_best_score is not None
            and checkpoint_best_score is not None
            and fallback_best_score > checkpoint_best_score + 0.005
        ):
            raise ResumeHistoryError(
                "partial score_history.json exceeds the checkpoint best_score and cannot "
                "be safely attributed to this run"
            )

    if existing_round_metrics is None:
        round_metrics = [dict(entry) for entry in (existing_score_history or [])]
        round_metrics_source = (
            "score_history_fallback" if existing_score_history is not None else "none"
        )
    else:
        round_metrics = existing_round_metrics
        round_metrics_source = "round_metrics"

    if existing_score_history is None:
        score_history = [dict(entry) for entry in round_metrics]
        score_history_source = (
            "round_metrics_fallback" if existing_round_metrics is not None else "none"
        )
    else:
        score_history = existing_score_history
        score_history_source = "score_history"

    retained_rounds = [
        round_number
        for entry in round_metrics
        if (round_number := _history_round_number(entry.get("round"))) is not None
    ]
    history_is_complete = len(retained_rounds) == max(0, start_round - 1) and all(
        round_number == index for index, round_number in enumerate(retained_rounds, start=1)
    )
    history_status = "complete" if history_is_complete else "partial"
    metadata = {
        "history_status": history_status,
        "retained_round_count": len(round_metrics),
        "retained_rounds": retained_rounds,
        "round_metrics_source": round_metrics_source,
        "score_history_source": score_history_source,
    }
    return score_history, round_metrics, metadata


def _history_entry_for_round(
    history: Sequence[Dict[str, Any]], round_number: int
) -> Dict[str, Any] | None:
    for entry in reversed(history):
        if _history_round_number(entry.get("round")) == round_number:
            return entry
    return None


def _history_best_round(history: Sequence[Dict[str, Any]], best_score: float) -> int | None:
    last_improved_round: int | None = None
    matching_rounds: List[int] = []
    matching_improved_rounds: List[int] = []
    for entry in history:
        if entry.get("successful_research_round") is False:
            continue
        round_number = _history_round_number(entry.get("round"))
        score = _history_float(entry.get("score"))
        if round_number is None or score is None:
            continue
        if best_score >= 0 and math.isclose(score, best_score, rel_tol=0.0, abs_tol=0.005):
            matching_rounds.append(round_number)
            if entry.get("improved") is True:
                matching_improved_rounds.append(round_number)
        if entry.get("improved") is True:
            last_improved_round = round_number
    if matching_improved_rounds:
        return matching_improved_rounds[-1]
    if matching_rounds:
        return matching_rounds[0]
    return last_improved_round if best_score < 0 else None


def _best_round_from_sources(
    *,
    history: Sequence[Dict[str, Any]],
    best_score: float,
    before_round: int,
    metadata_candidates: Sequence[tuple[Any, Any]],
) -> int | None:
    history_best_round = _history_best_round(history, best_score)
    if history_best_round is not None and history_best_round < before_round:
        return history_best_round

    for round_value, score_value in metadata_candidates:
        round_number = _history_round_number(round_value)
        source_score = _history_float(score_value)
        if (
            round_number is None
            or round_number < 1
            or round_number >= before_round
            or source_score is None
            or not math.isclose(source_score, best_score, rel_tol=0.0, abs_tol=0.005)
        ):
            continue
        historical_entry = _history_entry_for_round(history, round_number)
        historical_score = _history_float((historical_entry or {}).get("score"))
        if historical_score is not None and not math.isclose(
            historical_score,
            best_score,
            rel_tol=0.0,
            abs_tol=0.005,
        ):
            continue
        return round_number
    return None


def _prior_runtime_seconds(*values: Any) -> float:
    candidates = [value for item in values if (value := _history_float(item)) is not None]
    return max((value for value in candidates if value >= 0.0), default=0.0)


def _display_metadata_path(value: object, repo_root: Path | None) -> str:
    text = str(value or "").strip()
    return display_path(text, repo_root, default="") if text else ""


def _normalize_judge_text(text: str) -> str:
    lines = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.lower().startswith("score:"):
            continue
        lines.append(line.lower())
    merged = " ".join(lines)
    return re.sub(r"\s+", " ", merged).strip()


def _is_repetitive_judge(current: str, history: List[str]) -> bool:
    if not history:
        return False
    current_norm = _normalize_judge_text(current)
    if not current_norm:
        return False
    previous_norm = _normalize_judge_text(history[-1])
    if current_norm == previous_norm:
        return True
    similarity = SequenceMatcher(None, current_norm, previous_norm).ratio()
    return similarity >= 0.95


def _run_agent_step(
    *,
    console: Console,
    round_index: int,
    agent_name: str,
    call: Callable[[], str],
    log_path: Optional[Path] = None,
    mode: str = "normal",
) -> Tuple[str, Optional[str], float]:
    depth = int(getattr(_run_agent_step, "_depth", 0))
    if depth > 0:
        raise RuntimeError("Recursive agent step detected; aborting for safety.")
    _run_agent_step._depth = depth + 1  # type: ignore[attr-defined]
    console.print(f"[Round {round_index}] Running {agent_name} agent...")
    if log_path is not None:
        append_log_line(
            log_path, f"mode={mode} | round={round_index} | agent={agent_name} | status=start"
        )
    started = time.monotonic()
    try:
        output = call()
        elapsed = time.monotonic() - started
        console.print(f"[Round {round_index}] {agent_name.capitalize()} finished.")
        if log_path is not None:
            append_log_line(
                log_path,
                f"mode={mode} | round={round_index} | agent={agent_name} | "
                f"status=end | elapsed={elapsed:.3f}s",
            )
        return output, None, elapsed
    except CloudFreeDailyQuotaExhausted:
        raise
    except RuntimeError as exc:
        elapsed = time.monotonic() - started
        console.print(f"[red][Round {round_index}] {agent_name} failed: {exc}[/red]")
        if log_path is not None:
            append_log_line(
                log_path,
                f"mode={mode} | round={round_index} | agent={agent_name} | "
                f"status=error | elapsed={elapsed:.3f}s | error={exc}",
            )
        return f"[{agent_name.upper()} ERROR] {exc}", str(exc), elapsed
    finally:
        _run_agent_step._depth = depth  # type: ignore[attr-defined]


def _cloud_free_status(agents: ResearchAgents) -> Dict[str, Any]:
    status_fn = getattr(agents.llm, "cloud_free_status", None)
    if not callable(status_fn):
        return {}
    status = status_fn()
    return status if isinstance(status, dict) else {}


def _is_user_stop_error(error: Optional[str]) -> bool:
    return "user stop requested" in (error or "").lower()


def _is_provider_quota_error(error: Optional[str]) -> bool:
    text = (error or "").lower()
    return any(
        marker in text
        for marker in (
            "provider_quota_exhausted",
            "resource_exhausted",
            "rate limit",
            "rate-limit",
            "rate_limited",
            "quota",
            "free-tier",
            "free tier",
            "retry after",
            "429",
        )
    )


def _is_skipped_placeholder_error(error: Optional[str]) -> bool:
    text = (error or "").lower()
    return text.startswith("skipped due") or " skipped" in text


def _is_provider_failure_error(error: Optional[str]) -> bool:
    text = (error or "").lower()
    if not text:
        return False
    return (
        _is_provider_quota_error(error)
        or "failed to call" in text
        or "provider" in text
        or "gemini request failed" in text
        or "ollama request timed out" in text
        or "ollama prompt too large" in text
        or "gemini prompt too large" in text
    )


def _set_provider_context(
    *,
    agents: ResearchAgents,
    project_dir: Path,
    run_id: str,
    round_index: int,
    agent_name: str,
) -> None:
    setter = getattr(agents.llm, "set_provider_context", None)
    if callable(setter):
        setter(
            provider_event_path=project_dir / "provider_events.jsonl",
            run_id=run_id,
            round_index=round_index,
            stage=agent_name,
        )


def _base_resume_metadata(
    *,
    mode: str,
    run_id: str,
    start_round: int,
    run_root_override: Optional[Path],
    best_output_path: Path,
    initial_best_output: str,
    checkpoint_preview: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    resumes_existing_run = mode == "resume" or start_round > 1 or run_root_override is not None
    previous_best_available = bool(initial_best_output.strip())
    metadata: Dict[str, Any] = {
        "lifecycle_action": "resume_existing_run" if resumes_existing_run else "start_new_run",
        "resume_from_checkpoint": resumes_existing_run,
        "resume_source": "checkpoint"
        if resumes_existing_run
        else "previous_best_context"
        if previous_best_available
        else "none",
        "resumed_run_id": run_id if resumes_existing_run else None,
        "resume_from_round": start_round if resumes_existing_run else None,
        "new_run_from_previous_best": (not resumes_existing_run) and previous_best_available,
        "previous_best_output_path": str(best_output_path) if previous_best_available else "",
        "completed_round_files_preserved": resumes_existing_run,
        "next_round": start_round,
    }
    if checkpoint_preview:
        metadata["checkpoint_preview"] = checkpoint_preview
        for key in (
            "next_round_status",
            "next_round_blocks_resume",
            "next_round_safety_action",
            "next_round_existing_files",
            "next_round_missing_expected_files",
        ):
            if key in checkpoint_preview:
                metadata[key] = checkpoint_preview[key]
    return metadata


def _resume_metadata_for_checkpoint(
    *,
    base_metadata: Dict[str, Any],
    completed_rounds: int,
    can_resume: bool,
    stop_reason: str,
) -> Dict[str, Any]:
    metadata = dict(base_metadata)
    metadata.update(
        {
            "can_resume": can_resume,
            "last_completed_round": completed_rounds,
            "next_round": completed_rounds + 1 if can_resume else None,
            "stop_reason": stop_reason,
            "completed_round_files_preserved": can_resume
            or base_metadata.get("lifecycle_action") == "resume_existing_run",
        }
    )
    return metadata


def run_iterative_rounds(
    *,
    console: Console,
    agents: ResearchAgents,
    task_text: str,
    project_dir: Path,
    memory_path: Path,
    mode: str,
    model_name: str,
    max_rounds: int,
    stop_if_no_improvement_rounds: int,
    global_max_runtime_seconds: int,
    per_agent_timeout_seconds: int,
    disable_no_improvement_stop: bool = False,
    disable_timeout_stop: bool = False,
    start_round: int = 1,
    run_root_override: Optional[Path] = None,
    initial_best_score: float = -1.0,
    topic_keywords: Optional[Sequence[str]] = None,
    project_metadata: Optional[Dict[str, Any]] = None,
    model_provider: str = "",
    model_parameters: Optional[Dict[str, Any]] = None,
    topic_snapshot: Optional[Dict[str, Any]] = None,
    prompt_dir: Optional[Path] = None,
    repo_root: Optional[Path] = None,
    git_root: GitRootSetting = INHERIT_GIT_ROOT,
    drafting_mode: str = DEFAULT_DRAFTING_MODE,
    max_consecutive_draft_timeouts: int = 1,
    max_consecutive_provider_quota_failures: int = 2,
    resume_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if max_rounds < 1:
        raise ValueError("max_rounds must be >= 1")
    if isinstance(start_round, bool) or not isinstance(start_round, int) or start_round < 1:
        raise ValueError("start_round must be >= 1")
    ensure_project_runtime_paths_safe(project_dir)

    # Termination guarantee:
    # 1) The only round loop is a bounded for-loop over [1..max_rounds].
    # 2) There is no recursive agent call path.
    # 3) No retry loop exists for failed LLM requests.
    # 4) Additional early-stop conditions (timeout/no-improvement/errors) can only reduce runtime.
    started_at = time.monotonic()
    if run_root_override is not None:
        run_root, run_root_error = validate_resume_run_root(
            project_dir=project_dir,
            run_root_value=run_root_override,
        )
        if run_root_error or run_root is None:
            raise ResumeHistoryError(RESUME_PATH_MESSAGES[run_root_error or "unsafe_run_root"])
    else:
        run_root = make_run_root(project_dir)
    log_path = project_dir / "run.log"
    checkpoint_path = project_dir / "checkpoint.json"
    stop_signal_path = project_dir / "STOP_REQUESTED"
    best_output_path = project_dir / "best_output.md"
    interrupted_report_path = project_dir / "interrupted_report.md"
    run_id = run_root.name
    run_config_path = run_root / "run_config.json"
    score_history_path = project_dir / "score_history.json"
    round_metrics_path = run_root / "round_metrics.json"
    research_state_path = project_dir / "research_state.json"
    started_at_iso = datetime.now().astimezone().isoformat()
    resumes_existing_run = mode == "resume" or start_round > 1 or run_root_override is not None
    last_draft_output = ""
    last_review_output = ""
    last_revised_output = ""
    last_judge_output = ""
    if resumes_existing_run:
        resume_artifact_paths = (
            run_config_path,
            run_root / "run_summary.json",
            round_metrics_path,
            run_root / "run_manifest.json",
            run_root / _RESUME_STARTUP_TRANSACTION_NAME,
        )
        if not resume_artifact_links_are_safe(
            parent_dir=run_root,
            paths=resume_artifact_paths,
        ) or not resume_artifact_links_are_safe(
            parent_dir=project_dir,
            paths=(score_history_path,),
        ):
            raise ResumeHistoryError(RESUME_PATH_MESSAGES[UNSAFE_ARTIFACT_PATH])

        previous_round = start_round - 1
        if previous_round:
            previous_round_dir, previous_round_error = validate_resume_round_dir(
                run_root=run_root,
                round_dir=run_root / f"round_{previous_round:02d}",
            )
            if previous_round_error or previous_round_dir is None:
                raise ResumeHistoryError(
                    RESUME_PATH_MESSAGES[previous_round_error or UNSAFE_ROUND_PATH]
                )
            previous_outputs = tuple(
                previous_round_dir / filename
                for filename in (
                    "01_draft.md",
                    "02_review.md",
                    "03_revised.md",
                    "04_judge.md",
                )
            )
            if not resume_artifact_links_are_safe(
                parent_dir=previous_round_dir,
                paths=previous_outputs,
            ):
                raise ResumeHistoryError(RESUME_PATH_MESSAGES[UNSAFE_ARTIFACT_PATH])
            (
                last_draft_output,
                last_review_output,
                last_revised_output,
                last_judge_output,
            ) = tuple(_read_resume_round_text(path) for path in previous_outputs)

        for pending_round in range(start_round, max_rounds + 1):
            _validate_pending_resume_round_dir(run_root, pending_round)

        _recover_resume_startup_transaction(run_root=run_root, run_id=run_id)

    initial_best_output = read_text(best_output_path)
    base_resume_metadata = _base_resume_metadata(
        mode=mode,
        run_id=run_id,
        start_round=start_round,
        run_root_override=run_root_override,
        best_output_path=best_output_path,
        initial_best_output=initial_best_output,
        checkpoint_preview=resume_metadata,
    )
    existing_run_manifest = (
        _read_resume_manifest(
            run_root / "run_manifest.json",
            canonical_run_id=run_id,
        )
        if resumes_existing_run
        else None
    )
    try:
        existing_run_config = read_run_config(
            run_root,
            safe_artifacts=True,
            strict_existing=resumes_existing_run,
        )
    except InvalidRunConfigError as exc:
        raise ResumeHistoryError(str(exc)) from None
    if resumes_existing_run and not _resume_json_nesting_is_safe(existing_run_config):
        raise ResumeHistoryError("run_config.json exceeds the supported JSON nesting depth")
    existing_run_summary = read_json_file(run_root / "run_summary.json")
    resumes_existing_run = base_resume_metadata["lifecycle_action"] == "resume_existing_run"
    score_history: List[Dict[str, Any]] = []
    round_metrics: List[Dict[str, Any]] = []
    if resumes_existing_run:
        checkpoint_best_score = _history_float(initial_best_score)
        checkpoint_best_score = (
            checkpoint_best_score
            if checkpoint_best_score is not None and checkpoint_best_score >= 0
            else None
        )
        score_history, round_metrics, history_metadata = _load_resume_histories(
            score_history_path=score_history_path,
            round_metrics_path=round_metrics_path,
            start_round=start_round,
            checkpoint_best_score=checkpoint_best_score,
        )
        base_resume_metadata.update(history_metadata)
    prior_total_runtime = (
        _prior_runtime_seconds(
            existing_run_config.get("total_runtime_seconds"),
            existing_run_summary.get("total_runtime_seconds"),
            existing_run_summary.get("total_elapsed_seconds"),
        )
        if resumes_existing_run
        else 0.0
    )
    best_score = initial_best_score
    historical_scores = [
        score
        for entry in round_metrics
        if entry.get("successful_research_round") is not False
        and (score := _history_float(entry.get("score"))) is not None
    ]
    if resumes_existing_run:
        best_score_sources = {
            "checkpoint": _history_float(initial_best_score),
            "run_summary": _history_float(existing_run_summary.get("best_score")),
            "run_config": _history_float(existing_run_config.get("best_score")),
            "round_metrics": max(historical_scores) if historical_scores else None,
        }
        valid_best_scores = {
            source: score
            for source, score in best_score_sources.items()
            if score is not None and score >= 0
        }
        checkpoint_best_score = valid_best_scores.get("checkpoint")
        historical_best_score = valid_best_scores.get("round_metrics")
        history_is_complete = (
            base_resume_metadata.get("history_status") == "complete"
            and historical_best_score is not None
        )
        if (
            history_is_complete
            and checkpoint_best_score is not None
            and checkpoint_best_score > historical_best_score + 0.005
        ):
            raise ResumeHistoryError("checkpoint best_score exceeds the complete round history")
        supported_scores = [historical_best_score] if historical_best_score is not None else []
        if history_is_complete:
            pass
        else:
            metadata_scores = [
                score for source, score in valid_best_scores.items() if source != "round_metrics"
            ]
            distinct_metadata_scores = {round(score, 6) for score in metadata_scores}
            if len(distinct_metadata_scores) > 1:
                raise ResumeHistoryError(
                    "partial round history has conflicting best_score metadata"
                )
            if metadata_scores:
                supported_scores.append(metadata_scores[0])
            elif initial_best_output:
                raise ResumeHistoryError(
                    "best_output.md exists but partial history has no best_score metadata"
                )
        best_score = max(supported_scores, default=-1.0)
        all_source_scores = list(valid_best_scores.values())
        rounded_source_scores = {round(score, 6) for score in all_source_scores}
        base_resume_metadata["best_score_reconciled"] = len(rounded_source_scores) > 1 or any(
            not math.isclose(score, best_score, rel_tol=0.0, abs_tol=0.005)
            for score in all_source_scores
        )
        base_resume_metadata["best_score_source_count"] = len(all_source_scores)
    runtime_snapshot = {
        "max_rounds": max_rounds,
        "start_round": start_round,
        "stop_if_no_improvement_rounds": stop_if_no_improvement_rounds,
        "global_max_runtime_seconds": global_max_runtime_seconds,
        "per_agent_timeout_seconds": per_agent_timeout_seconds,
        "disable_no_improvement_stop": disable_no_improvement_stop,
        "disable_timeout_stop": disable_timeout_stop,
        "max_consecutive_draft_timeouts": max_consecutive_draft_timeouts,
        "max_consecutive_provider_quota_failures": max_consecutive_provider_quota_failures,
        "drafting_mode": drafting_mode,
    }
    run_config = build_initial_run_config(
        run_id=run_id,
        run_root=run_root,
        mode=mode,
        model_name=model_name,
        model_provider=model_provider,
        model_parameters=model_parameters,
        runtime_config=runtime_snapshot,
        topic_snapshot=topic_snapshot,
        project_metadata=project_metadata,
        prompt_dir=prompt_dir,
        repo_root=repo_root,
        git_root=git_root,
        started_at=started_at_iso,
        existing_run_config=existing_run_config,
        resume_metadata=base_resume_metadata,
    )
    run_manifest = _build_run_manifest(
        existing_manifest=existing_run_manifest,
        existing_run_config=existing_run_config,
        resumes_existing_run=resumes_existing_run,
        run_id=run_id,
        run_root=run_root,
        mode=mode,
        model_name=model_name,
        drafting_mode=drafting_mode,
        started_at=started_at_iso,
        project_metadata=project_metadata,
        run_config_path=run_config_path,
        resume_metadata=base_resume_metadata,
    )
    if resumes_existing_run:
        _write_resume_startup_metadata(
            run_root=run_root,
            run_id=run_id,
            run_config=run_config,
            run_manifest=run_manifest,
        )
        _log(
            console,
            log_path,
            mode,
            f"run_start run_id={run_id} run_root={display_path(run_root, repo_root)} "
            f"model={model_name}",
        )
    else:
        write_json_file(run_config_path, run_config)
        _log(
            console,
            log_path,
            mode,
            f"run_start run_id={run_id} run_root={display_path(run_root, repo_root)} "
            f"model={model_name}",
        )
        write_json_file(run_root / "run_manifest.json", run_manifest)
    if project_metadata:
        _log(
            console,
            log_path,
            mode,
            "project_source "
            f"kind={project_metadata.get('source_kind', 'unknown')} "
            f"name={project_metadata.get('project_name', '')} "
            f"title={project_metadata.get('project_title', '')} "
            f"project_dir={_display_metadata_path(project_metadata.get('project_dir'), repo_root)} "
            f"task_path={_display_metadata_path(project_metadata.get('task_path'), repo_root)}",
        )
    _log(
        console,
        log_path,
        mode,
        "safety "
        f"max_rounds={max_rounds} no_improve_limit={stop_if_no_improvement_rounds} "
        f"global_runtime_limit={global_max_runtime_seconds}s",
    )

    best_output = initial_best_output
    best_round = _best_round_from_sources(
        history=round_metrics,
        best_score=best_score,
        before_round=start_round,
        metadata_candidates=(
            ((resume_metadata or {}).get("best_round"), initial_best_score),
            (
                existing_run_summary.get("best_round"),
                existing_run_summary.get("best_score"),
            ),
            (
                existing_run_config.get("best_round"),
                existing_run_config.get("best_score"),
            ),
        ),
    )
    previous_round = start_round - 1 if resumes_existing_run else 0
    previous_judge = last_judge_output
    judge_history: List[str] = [last_judge_output] if last_judge_output else []
    previous_round_metric = _history_entry_for_round(round_metrics, previous_round)
    non_improve_streak = max(
        0,
        _history_round_number((previous_round_metric or {}).get("non_improve_streak")) or 0,
    )
    stop_reason = STOP_MAX_ROUNDS
    completed_rounds = previous_round
    last_successful_agent = str((resume_metadata or {}).get("last_successful_agent", "") or "none")
    invalid_score_seen = any(entry.get("invalid_score_this_round") for entry in round_metrics)
    timeout_seen = any(entry.get("timeout_this_round") for entry in round_metrics)
    paused_until_reset_message = ""
    consecutive_draft_timeouts = 0
    consecutive_provider_quota_failures = max(
        0,
        _history_round_number((previous_round_metric or {}).get("provider_quota_streak")) or 0,
    )
    provider_quota_failure_seen = any(
        entry.get("provider_failure_this_round") for entry in round_metrics
    )

    def _remaining_runtime_seconds() -> int:
        remaining = global_max_runtime_seconds - (time.monotonic() - started_at)
        return max(0, int(remaining))

    def _apply_dynamic_timeout() -> None:
        remaining = _remaining_runtime_seconds()
        agents.llm.timeout_seconds = max(1, min(per_agent_timeout_seconds, remaining))
        console.print(
            f"[debug] Applied per-agent timeout={agents.llm.timeout_seconds}s "
            f"(remaining_global_runtime={remaining}s)"
        )

    # round_index is strictly increasing and cannot be reset.
    for round_index in range(start_round, max_rounds + 1):
        elapsed_before_round = time.monotonic() - started_at
        if elapsed_before_round >= global_max_runtime_seconds:
            stop_reason = STOP_EXCEPTION
            _log(
                console,
                log_path,
                mode,
                "global_runtime_limit_reached_before_round",
            )
            break

        if _stop_requested(stop_signal_path):
            stop_reason = STOP_USER_REQUESTED
            _log(console, log_path, mode, f"user_stop_requested_before_round round={round_index}")
            break

        if resumes_existing_run:
            round_dir = _validate_pending_resume_round_dir(run_root, round_index)
            round_dir = make_round_dir(run_root, round_index, allow_existing=round_dir.exists())
        else:
            round_dir = make_round_dir(run_root, round_index)
        _log(console, log_path, mode, f"round_enter round={round_index}")
        console.rule(f"Round {round_index}")
        draft_output = ""
        review_output = ""
        revised_output = ""
        judge_output = ""
        agent_timings_seconds = {
            "draft": 0.0,
            "review": 0.0,
            "revise": 0.0,
            "judge": 0.0,
        }
        draft_previous_review_output = last_review_output
        draft_previous_draft_output = last_draft_output
        draft_previous_revised_output = last_revised_output
        draft_previous_best_output = best_output

        def _persist_round_outputs(stage: str) -> None:
            save_round_outputs(
                round_dir,
                draft=draft_output,
                review=review_output,
                revised=revised_output,
                judge=judge_output,
            )
            _log(console, log_path, mode, f"round_partial_saved round={round_index} stage={stage}")

        memory_text = get_memory_for_prompt(memory_path)
        memory_words = len(memory_text.split())
        _log(
            console,
            log_path,
            mode,
            f"memory_loaded round={round_index} words={memory_words} limit=1500",
        )
        if memory_words > 1500:
            memory_text = " ".join(memory_text.split()[-1500:])
            _log(console, log_path, mode, f"memory_truncated round={round_index}")

        if _stop_requested(stop_signal_path):
            stop_reason = STOP_USER_REQUESTED
            _log(console, log_path, mode, f"user_stop_requested_before_round round={round_index}")
            break

        try:
            if time.monotonic() - started_at >= global_max_runtime_seconds:
                draft_output = "[DRAFT SKIPPED] global runtime limit reached."
                draft_error = "global runtime limit reached"
                review_output = "[REVIEW SKIPPED] global runtime limit reached."
                review_error = "global runtime limit reached"
                revised_output = "[REVISE SKIPPED] global runtime limit reached."
                revise_error = "global runtime limit reached"
                judge_output = "SCORE: 0\n- Global runtime limit reached before agent call."
                judge_error = "global runtime limit reached"
                _log(console, log_path, mode, f"global_runtime_skip_all_agents round={round_index}")
            else:
                if _stop_requested(stop_signal_path):
                    draft_output = "[DRAFT SKIPPED] user stop requested."
                    draft_error = "user stop requested"
                    _log(
                        console,
                        log_path,
                        mode,
                        f"user_stop_requested_before_draft round={round_index}",
                    )
                else:
                    _apply_dynamic_timeout()
                    _set_provider_context(
                        agents=agents,
                        project_dir=project_dir,
                        run_id=run_id,
                        round_index=round_index,
                        agent_name="draft",
                    )
                    draft_output, draft_error, agent_timings_seconds["draft"] = _run_agent_step(
                        console=console,
                        round_index=round_index,
                        agent_name="draft",
                        log_path=log_path,
                        mode=mode,
                        call=lambda: agents.draft(
                            task=task_text,
                            memory=memory_text,
                            round_index=round_index,
                            previous_best=best_output
                            if drafting_mode == DRAFTING_MODE_BEST_GUIDED
                            else "",
                            previous_judge=previous_judge,
                            drafting_mode=drafting_mode,
                            previous_review=last_review_output
                            if drafting_mode
                            in {
                                DRAFTING_MODE_FRESH_WITH_REVIEW,
                                DRAFTING_MODE_CONTINUE_FROM_PREVIOUS,
                            }
                            else "",
                            previous_draft=last_draft_output
                            if drafting_mode == DRAFTING_MODE_CONTINUE_FROM_PREVIOUS
                            else "",
                            previous_revised=last_revised_output
                            if drafting_mode == DRAFTING_MODE_CONTINUE_FROM_PREVIOUS
                            else "",
                        ),
                    )
            if not draft_error and _stop_requested(stop_signal_path):
                draft_error = "user stop requested after draft"
                _log(
                    console, log_path, mode, f"user_stop_requested_after_draft round={round_index}"
                )
            _persist_round_outputs("draft")
            if not draft_error:
                last_successful_agent = "draft"
            if draft_error:
                review_output = "[REVIEW SKIPPED] draft agent failed."
                review_error = "skipped due to draft failure"
                console.print(
                    f"[yellow][Round {round_index}] Skipping review agent due to draft failure.[/yellow]"
                )
            else:
                if _stop_requested(stop_signal_path):
                    review_output = "[REVIEW SKIPPED] user stop requested."
                    review_error = "user stop requested"
                    _log(
                        console,
                        log_path,
                        mode,
                        f"user_stop_requested_before_review round={round_index}",
                    )
                elif time.monotonic() - started_at >= global_max_runtime_seconds:
                    review_output = "[REVIEW SKIPPED] global runtime limit reached."
                    review_error = "global runtime limit reached"
                    console.print(
                        f"[yellow][Round {round_index}] Skipping review agent due to global runtime limit.[/yellow]"
                    )
                else:
                    _apply_dynamic_timeout()
                    _set_provider_context(
                        agents=agents,
                        project_dir=project_dir,
                        run_id=run_id,
                        round_index=round_index,
                        agent_name="review",
                    )
                    review_output, review_error, agent_timings_seconds["review"] = _run_agent_step(
                        console=console,
                        round_index=round_index,
                        agent_name="review",
                        log_path=log_path,
                        mode=mode,
                        call=lambda: agents.review(
                            task=task_text,
                            memory=memory_text,
                            draft_output=draft_output,
                        ),
                    )
                if not review_error and _stop_requested(stop_signal_path):
                    review_error = "user stop requested after review"
                    _log(
                        console,
                        log_path,
                        mode,
                        f"user_stop_requested_after_review round={round_index}",
                    )
                _persist_round_outputs("review")
                if not review_error:
                    last_successful_agent = "review"

            if draft_error or review_error:
                revised_output = "[REVISE SKIPPED] draft/review agent failed."
                revise_error = "skipped due to upstream failure"
                console.print(
                    f"[yellow][Round {round_index}] Skipping revise agent due to upstream failure.[/yellow]"
                )
            else:
                if _stop_requested(stop_signal_path):
                    revised_output = "[REVISE SKIPPED] user stop requested."
                    revise_error = "user stop requested"
                    _log(
                        console,
                        log_path,
                        mode,
                        f"user_stop_requested_before_revise round={round_index}",
                    )
                elif time.monotonic() - started_at >= global_max_runtime_seconds:
                    revised_output = "[REVISE SKIPPED] global runtime limit reached."
                    revise_error = "global runtime limit reached"
                    console.print(
                        f"[yellow][Round {round_index}] Skipping revise agent due to global runtime limit.[/yellow]"
                    )
                else:
                    _apply_dynamic_timeout()
                    _set_provider_context(
                        agents=agents,
                        project_dir=project_dir,
                        run_id=run_id,
                        round_index=round_index,
                        agent_name="revise",
                    )
                    revised_output, revise_error, agent_timings_seconds["revise"] = _run_agent_step(
                        console=console,
                        round_index=round_index,
                        agent_name="revise",
                        log_path=log_path,
                        mode=mode,
                        call=lambda: agents.revise(
                            task=task_text,
                            memory=memory_text,
                            draft_output=draft_output,
                            review_output=review_output,
                        ),
                    )
                if not revise_error and _stop_requested(stop_signal_path):
                    revise_error = "user stop requested after revise"
                    _log(
                        console,
                        log_path,
                        mode,
                        f"user_stop_requested_after_revise round={round_index}",
                    )
                _persist_round_outputs("revise")
                if not revise_error:
                    last_successful_agent = "revise"

            if revise_error:
                judge_output = "SCORE: 0\n- Judge skipped because revise step failed."
                judge_error = "skipped due to revise failure"
                console.print(
                    f"[yellow][Round {round_index}] Skipping judge agent due to revise failure (score=0).[/yellow]"
                )
            else:
                if _stop_requested(stop_signal_path):
                    judge_output = "SCORE: 0\n- Judge skipped because user stop was requested."
                    judge_error = "user stop requested"
                    _log(
                        console,
                        log_path,
                        mode,
                        f"user_stop_requested_before_judge round={round_index}",
                    )
                elif time.monotonic() - started_at >= global_max_runtime_seconds:
                    judge_output = "SCORE: 0\n- Global runtime limit reached before judge call."
                    judge_error = "global runtime limit reached"
                    console.print(
                        f"[yellow][Round {round_index}] Skipping judge agent due to global runtime limit (score=0).[/yellow]"
                    )
                else:
                    _apply_dynamic_timeout()
                    _set_provider_context(
                        agents=agents,
                        project_dir=project_dir,
                        run_id=run_id,
                        round_index=round_index,
                        agent_name="judge",
                    )
                    judge_output, judge_error, agent_timings_seconds["judge"] = _run_agent_step(
                        console=console,
                        round_index=round_index,
                        agent_name="judge",
                        log_path=log_path,
                        mode=mode,
                        call=lambda: agents.judge(
                            task=task_text,
                            memory=memory_text,
                            revised_output=revised_output,
                        ),
                    )
                if not judge_error:
                    last_successful_agent = "judge"
            _persist_round_outputs("judge")
        except CloudFreeDailyQuotaExhausted as exc:
            stop_reason = STOP_CLOUD_DAILY_QUOTA
            paused_until_reset_message = str(exc)
            _log(
                console,
                log_path,
                mode,
                "cloud_free_paused_until_reset "
                f"round={round_index} message={paused_until_reset_message}",
            )
            console.print(f"[yellow]{paused_until_reset_message}[/yellow]")
            break
        except KeyboardInterrupt:
            stop_reason = STOP_MANUAL_INTERRUPT
            _log(console, log_path, mode, "manual_interrupt_caught")
            break
        except Exception as exc:  # noqa: BLE001
            stop_reason = STOP_EXCEPTION
            _log(console, log_path, mode, f"exception round={round_index} error={exc}")
            break

        round_errors = [
            err for err in [draft_error, review_error, revise_error, judge_error] if err
        ]
        if round_errors:
            console.print(
                f"[yellow][Round {round_index}] Agent errors detected: {len(round_errors)}[/yellow]"
            )
        timeout_this_round = any("timed out" in (err or "").lower() for err in round_errors)
        if timeout_this_round:
            timeout_seen = True
        draft_timeout_this_round = "timed out" in (draft_error or "").lower()
        prompt_too_large_this_round = any(
            "prompt too large" in (err or "").lower() for err in round_errors
        )
        provider_quota_this_round = any(_is_provider_quota_error(err) for err in round_errors)
        provider_failure_this_round = any(
            _is_provider_failure_error(err)
            for err in round_errors
            if not _is_skipped_placeholder_error(err)
        )
        skipped_placeholder_this_round = any(
            _is_skipped_placeholder_error(err) for err in round_errors
        )
        if draft_timeout_this_round:
            consecutive_draft_timeouts += 1
        else:
            consecutive_draft_timeouts = 0
        if provider_quota_this_round:
            provider_quota_failure_seen = True
            consecutive_provider_quota_failures += 1
        else:
            consecutive_provider_quota_failures = 0

        save_round_outputs(
            round_dir,
            draft=draft_output,
            review=review_output,
            revised=revised_output,
            judge=judge_output,
        )
        _log(
            console,
            log_path,
            mode,
            f"round_saved round={round_index} path={display_path(round_dir, repo_root)}",
        )

        if any(_is_user_stop_error(err) for err in round_errors):
            stop_reason = STOP_USER_REQUESTED
            _log(
                console,
                log_path,
                mode,
                f"round_incomplete_not_scored round={round_index} reason={STOP_USER_REQUESTED}",
            )
            break

        last_review_output = review_output
        last_draft_output = draft_output
        last_revised_output = revised_output
        last_judge_output = judge_output

        parsed_score = parse_score(judge_output)
        if parsed_score is None:
            score = 0.0
            invalid_score_seen = True
            _log(console, log_path, mode, f"score_parse_failed round={round_index} fallback=0")
        else:
            score = parsed_score
        _log(
            console,
            log_path,
            mode,
            f"score_extracted round={round_index} parsed={parsed_score is not None} value={score:.2f}",
        )
        judge_rubric = parse_judge_rubric(judge_output)
        completed_rounds = round_index

        successful_research_round = not round_errors and parsed_score is not None
        improved = successful_research_round and score > best_score
        if improved:
            best_score = score
            best_round = round_index
            best_output = revised_output
            write_text(best_output_path, best_output)
            non_improve_streak = 0
            console.print(
                f"[bold green]New best score:[/bold green] {best_score:.2f} -> updated best_output.md"
            )
        else:
            non_improve_streak += 1

        repetitive_judge = _is_repetitive_judge(judge_output, judge_history)
        judge_history.append(judge_output)

        previous_score = _history_float(round_metrics[-1].get("score")) if round_metrics else None
        continuation_source = draft_previous_revised_output or draft_previous_draft_output
        agent_topic_context = getattr(agents, "topic_context", "")
        draft_input_context = [
            getattr(agents, "draft_prompt", ""),
            agent_topic_context,
            round_index,
            task_text,
            memory_text,
            draft_previous_best_output if drafting_mode == DRAFTING_MODE_BEST_GUIDED else "",
            previous_judge,
            (
                draft_previous_review_output
                if drafting_mode
                in {
                    DRAFTING_MODE_FRESH_WITH_REVIEW,
                    DRAFTING_MODE_CONTINUE_FROM_PREVIOUS,
                }
                else ""
            ),
            continuation_source if drafting_mode == DRAFTING_MODE_CONTINUE_FROM_PREVIOUS else "",
        ]
        agent_io_metrics = build_agent_io_metrics(
            agent_inputs={
                "draft": draft_input_context,
                "review": [
                    getattr(agents, "review_prompt", ""),
                    agent_topic_context,
                    task_text,
                    memory_text,
                    draft_output,
                ],
                "revise": [
                    getattr(agents, "revise_prompt", ""),
                    agent_topic_context,
                    task_text,
                    memory_text,
                    draft_output,
                    review_output,
                ],
                "judge": [
                    getattr(agents, "judge_prompt", ""),
                    agent_topic_context,
                    task_text,
                    memory_text,
                    revised_output,
                ],
            },
            agent_outputs={
                "draft": draft_output,
                "review": review_output,
                "revise": revised_output,
                "judge": judge_output,
            },
            agent_timings_seconds=agent_timings_seconds,
            agent_errors={
                "draft": draft_error,
                "review": review_error,
                "revise": revise_error,
                "judge": judge_error,
            },
        )
        round_metric_totals = summarize_agent_io_metrics(agent_io_metrics)
        evolution_metrics = build_round_evolution_metrics(
            current_draft=draft_output,
            current_revised=revised_output,
            current_judge=judge_output,
            previous_draft=draft_previous_draft_output,
            previous_revised=draft_previous_revised_output,
            previous_judge=previous_judge,
            current_score=score,
            previous_score=previous_score,
        )
        round_metric = {
            "round": round_index,
            "score": score,
            "improved": improved,
            "non_improve_streak": non_improve_streak,
            "repetitive_judge": repetitive_judge,
            "errors": round_errors,
            "agent_errors": {
                "draft": draft_error,
                "review": review_error,
                "revise": revise_error,
                "judge": judge_error,
            },
            "agent_timings_seconds": {
                agent: round(elapsed, 3) for agent, elapsed in agent_timings_seconds.items()
            },
            "round_runtime_seconds": round(sum(agent_timings_seconds.values()), 3),
            "agent_io_metrics": agent_io_metrics,
            "evolution_metrics": evolution_metrics,
            "estimated_input_chars": round_metric_totals["total_estimated_input_chars"],
            "output_chars": round_metric_totals["total_output_chars"],
            "estimated_input_tokens": round_metric_totals["total_estimated_input_tokens"],
            "estimated_output_tokens": round_metric_totals["total_estimated_output_tokens"],
            "estimated_total_tokens": round_metric_totals["total_estimated_tokens"],
            "token_estimate_method": round_metric_totals["token_estimate_method"],
            "timeout_this_round": timeout_this_round,
            "provider_failure_this_round": provider_failure_this_round,
            "provider_quota_this_round": provider_quota_this_round,
            "provider_quota_streak": consecutive_provider_quota_failures,
            "skipped_placeholder_this_round": skipped_placeholder_this_round,
            "successful_research_round": successful_research_round,
            "invalid_score_this_round": parsed_score is None,
            "judge_rubric": judge_rubric,
            "model": model_name,
            "drafting_mode": drafting_mode,
        }
        score_history.append(round_metric)
        round_metrics.append(round_metric)
        write_score_history(score_history_path, score_history)
        write_score_history(round_metrics_path, round_metrics)

        memory_summary = summarize_round_memory(
            revised_output=revised_output,
            review_output=review_output,
            judge_output=judge_output,
            current_best_score=best_score,
            topic_keywords=topic_keywords,
        )
        update_project_memory(
            memory_path=memory_path,
            round_index=round_index,
            summary=memory_summary,
        )
        update_research_state(
            state_path=research_state_path,
            round_index=round_index,
            best_score=best_score,
            revised_output=revised_output,
            review_output=review_output,
            judge_output=judge_output,
            topic_keywords=topic_keywords,
        )
        _log(console, log_path, mode, f"memory_updated round={round_index}")
        _log(console, log_path, mode, f"research_state_updated round={round_index}")

        checkpoint_data = {
            "run_id": run_id,
            "run_root": str(run_root),
            "run_config": str(run_config_path),
            "run_summary": str(run_root / "run_summary.json"),
            "last_completed_round": round_index,
            "last_successful_agent": last_successful_agent,
            "best_score": round(best_score, 2),
            "best_round": best_round,
            "best_round_path": str(run_root / f"round_{best_round:02d}") if best_round else "",
            "stop_reason": "",
            "can_resume": True,
            "updated_at": datetime.now().isoformat(),
            "mode": mode,
            "model": model_name,
            "drafting_mode": drafting_mode,
            "project": project_metadata or {},
            "cloud_free": _cloud_free_status(agents),
            "resume_metadata": _resume_metadata_for_checkpoint(
                base_metadata=base_resume_metadata,
                completed_rounds=round_index,
                can_resume=True,
                stop_reason="",
            ),
        }
        write_json_file(checkpoint_path, checkpoint_data)

        elapsed_after_round = time.monotonic() - started_at
        _log(
            console,
            log_path,
            mode,
            f"stop_check round={round_index} timeout={timeout_this_round} "
            f"draft_timeout_streak={consecutive_draft_timeouts} "
            f"provider_quota={provider_quota_this_round} "
            f"provider_quota_streak={consecutive_provider_quota_failures} "
            f"repetitive={repetitive_judge} non_improve_streak={non_improve_streak} "
            f"invalid_score={parsed_score is None} elapsed={elapsed_after_round:.2f}s",
        )

        # Stop conditions:
        # - OLLAMA_TIMEOUT: any agent timeout in current round.
        # - NO_IMPROVEMENT: score does not improve for configured rounds.
        # - EXCEPTION: global runtime reached or unhandled exception.
        # - MAX_ROUNDS: for-loop exhausts naturally.
        if timeout_this_round and not disable_timeout_stop:
            stop_reason = STOP_OLLAMA_TIMEOUT
            _log(console, log_path, mode, f"stop_reason={STOP_OLLAMA_TIMEOUT} round={round_index}")
            break

        if (
            max_consecutive_draft_timeouts > 0
            and consecutive_draft_timeouts >= max_consecutive_draft_timeouts
        ):
            stop_reason = STOP_OLLAMA_TIMEOUT
            _log(
                console,
                log_path,
                mode,
                f"stop_reason={STOP_OLLAMA_TIMEOUT} round={round_index} "
                f"draft_timeout_streak={consecutive_draft_timeouts}",
            )
            break

        if prompt_too_large_this_round:
            stop_reason = STOP_PROMPT_TOO_LARGE
            _log(
                console,
                log_path,
                mode,
                f"stop_reason={STOP_PROMPT_TOO_LARGE} round={round_index}",
            )
            break

        if (
            max_consecutive_provider_quota_failures > 0
            and consecutive_provider_quota_failures >= max_consecutive_provider_quota_failures
        ):
            stop_reason = STOP_PROVIDER_QUOTA_EXHAUSTED
            _log(
                console,
                log_path,
                mode,
                f"stop_reason={STOP_PROVIDER_QUOTA_EXHAUSTED} round={round_index} "
                f"provider_quota_streak={consecutive_provider_quota_failures}",
            )
            break

        if not disable_no_improvement_stop and non_improve_streak >= stop_if_no_improvement_rounds:
            stop_reason = STOP_NO_IMPROVEMENT
            _log(console, log_path, mode, f"stop_reason={STOP_NO_IMPROVEMENT} round={round_index}")
            break

        if elapsed_after_round >= global_max_runtime_seconds:
            stop_reason = STOP_EXCEPTION
            _log(console, log_path, mode, f"stop_reason={STOP_EXCEPTION} round={round_index}")
            break

        if _stop_requested(stop_signal_path):
            stop_reason = STOP_USER_REQUESTED
            _log(console, log_path, mode, f"stop_reason={STOP_USER_REQUESTED} round={round_index}")
            break

        previous_judge = judge_output
        _log(console, log_path, mode, f"round_exit round={round_index}")
    else:
        stop_reason = STOP_MAX_ROUNDS

    if stop_reason == STOP_MAX_ROUNDS and invalid_score_seen and completed_rounds == 1:
        stop_reason = STOP_INVALID_SCORE

    best_round_text = "N/A" if best_round is None else str(best_round)
    best_score_text = "N/A" if best_score < 0 else f"{best_score:.2f}"
    best_output_path_text = (
        display_path(best_output_path, repo_root) if best_output_path.exists() else "N/A"
    )
    score_history_path_text = display_path(score_history_path, repo_root)
    session_runtime = time.monotonic() - started_at
    total_runtime = prior_total_runtime + session_runtime

    console.rule("Run Summary")
    console.print(f"[bold]Completed rounds:[/bold] {completed_rounds}")
    console.print(f"[bold]Best round:[/bold] {best_round_text}")
    console.print(f"[bold]Best score:[/bold] {best_score_text}")
    console.print(f"[bold]Stop reason:[/bold] {stop_reason}")
    console.print(f"[bold]Total runtime:[/bold] {total_runtime:.2f}s")
    console.print(f"[bold]Last successful agent:[/bold] {last_successful_agent}")
    console.print(f"[bold]Best output path:[/bold] {best_output_path_text}")
    console.print(f"[bold]Score history path:[/bold] {score_history_path_text}")
    _log(
        console,
        log_path,
        mode,
        f"run_summary completed_rounds={completed_rounds} stop_reason={stop_reason} "
        f"best_score={best_score_text} last_successful_agent={last_successful_agent}",
    )

    can_resume = stop_reason in {
        STOP_USER_REQUESTED,
        STOP_MANUAL_INTERRUPT,
        STOP_CLOUD_DAILY_QUOTA,
        STOP_PROVIDER_QUOTA_EXHAUSTED,
    }
    checkpoint_final = {
        "run_id": run_id,
        "run_root": str(run_root),
        "run_config": str(run_config_path),
        "run_summary": str(run_root / "run_summary.json"),
        "last_completed_round": completed_rounds,
        "last_successful_agent": last_successful_agent,
        "best_score": round(best_score, 2),
        "best_round": best_round,
        "best_round_path": str(run_root / f"round_{best_round:02d}") if best_round else "",
        "stop_reason": stop_reason,
        "updated_at": datetime.now().isoformat(),
        "mode": mode,
        "model": model_name,
        "drafting_mode": drafting_mode,
        "project": project_metadata or {},
        "cloud_free": _cloud_free_status(agents),
        "provider_quota_failure_seen": provider_quota_failure_seen,
        "resume_metadata": _resume_metadata_for_checkpoint(
            base_metadata=base_resume_metadata,
            completed_rounds=completed_rounds,
            can_resume=can_resume,
            stop_reason=stop_reason,
        ),
    }
    if stop_reason == STOP_CLOUD_DAILY_QUOTA:
        checkpoint_final.update(
            {
                "status": "paused_until_reset",
                "paused_until_reset": True,
                "pause_message": paused_until_reset_message
                or "Free-tier daily quota likely exhausted; safe to resume after reset.",
                "reset_heuristic": next_pacific_reset_heuristic(),
            }
        )
    if stop_reason == STOP_PROVIDER_QUOTA_EXHAUSTED:
        checkpoint_final.update(
            {
                "status": "provider_quota_exhausted",
                "provider_quota_exhausted": True,
                "pause_message": (
                    "Provider quota or rate limit failed consecutive rounds; "
                    "resume after quota reset or reduce benchmark preset."
                ),
                "reset_heuristic": next_pacific_reset_heuristic(),
            }
        )
    checkpoint_final["can_resume"] = can_resume
    write_json_file(checkpoint_path, checkpoint_final)
    successful_rounds = [
        entry["round"] for entry in round_metrics if entry.get("successful_research_round")
    ]
    timeout_rounds = [entry["round"] for entry in round_metrics if entry.get("timeout_this_round")]
    error_rounds = [entry["round"] for entry in round_metrics if entry.get("errors")]
    provider_failure_rounds = [
        entry["round"] for entry in round_metrics if entry.get("provider_failure_this_round")
    ]
    invalid_score_rounds = [
        entry["round"] for entry in round_metrics if entry.get("invalid_score_this_round")
    ]
    metrics_totals = summarize_round_metrics(round_metrics)
    run_summary_path = run_root / "run_summary.json"
    write_json_file(
        run_summary_path,
        {
            "run_id": run_id,
            "run_root": str(run_root),
            "mode": mode,
            "model": model_name,
            "drafting_mode": drafting_mode,
            "completed_rounds": completed_rounds,
            "best_round": best_round,
            "best_score": round(best_score, 2),
            "stop_reason": stop_reason,
            "can_resume": can_resume,
            "total_runtime_seconds": round(total_runtime, 3),
            "total_elapsed_seconds": round(total_runtime, 3),
            "total_agent_elapsed_seconds": metrics_totals["total_agent_elapsed_seconds"],
            "total_estimated_input_tokens": metrics_totals["total_estimated_input_tokens"],
            "total_estimated_output_tokens": metrics_totals["total_estimated_output_tokens"],
            "total_estimated_tokens": metrics_totals["total_estimated_tokens"],
            "total_estimated_input_chars": metrics_totals["total_estimated_input_chars"],
            "total_output_chars": metrics_totals["total_output_chars"],
            "token_estimate_method": metrics_totals["token_estimate_method"],
            "agent_metric_totals": metrics_totals["agent_metric_totals"],
            "evolution_metric_totals": metrics_totals["evolution_metric_totals"],
            "rubric_metric_totals": metrics_totals["rubric_metric_totals"],
            "rubric_round_count": metrics_totals["rubric_metric_totals"]["rounds_with_rubric"],
            "rubric_subscore_averages": metrics_totals["rubric_metric_totals"]["rubric_averages"],
            "rubric_subscore_latest": metrics_totals["rubric_metric_totals"]["rubric_latest"],
            "rubric_subscore_delta_first_to_latest": metrics_totals["rubric_metric_totals"][
                "rubric_delta_first_to_latest"
            ],
            "avg_draft_to_revised_similarity": metrics_totals["evolution_metric_totals"][
                "avg_draft_to_revised_similarity"
            ],
            "avg_revised_similarity_to_previous": metrics_totals["evolution_metric_totals"][
                "avg_revised_similarity_to_previous"
            ],
            "avg_judge_similarity_to_previous": metrics_totals["evolution_metric_totals"][
                "avg_judge_similarity_to_previous"
            ],
            "low_revision_change_rounds": metrics_totals["evolution_metric_totals"][
                "low_revision_change_rounds"
            ],
            "low_previous_revised_change_rounds": metrics_totals["evolution_metric_totals"][
                "low_previous_revised_change_rounds"
            ],
            "timeout_count": metrics_totals["timeout_count"],
            "error_count": metrics_totals["error_count"],
            "resume_metadata": checkpoint_final["resume_metadata"],
            "score_history_path": str(score_history_path),
            "round_metrics_path": str(round_metrics_path),
            "run_config_path": str(run_config_path),
            "successful_rounds": successful_rounds,
            "timeout_rounds": timeout_rounds,
            "error_rounds": error_rounds,
            "provider_failure_rounds": provider_failure_rounds,
            "invalid_score_rounds": invalid_score_rounds,
            "round_count": len(round_metrics),
        },
    )
    run_config = finalize_run_config(
        run_config,
        stop_reason=stop_reason,
        can_resume=can_resume,
        completed_rounds=completed_rounds,
        best_score=best_score,
        best_round=best_round,
        total_runtime_seconds=total_runtime,
        ended_at=checkpoint_final["updated_at"],
    )
    write_json_file(run_config_path, run_config)

    if stop_reason in {STOP_USER_REQUESTED, STOP_MANUAL_INTERRUPT}:
        write_interrupted_report(
            report_path=interrupted_report_path,
            last_completed_round=completed_rounds,
            last_successful_agent=last_successful_agent,
            best_score=max(0.0, best_score),
            best_output_path=best_output_path,
            resume_command=".venv/bin/python -m src.main --resume",
            stop_time=datetime.now().isoformat(),
            repo_root=repo_root,
        )
        try:
            unlink_artifact_file(stop_signal_path)
        except OSError:
            pass

    if best_output:
        console.print(f"[bold cyan]Best score:[/bold cyan] {best_score:.2f}")
    else:
        console.print(
            "[red]No valid score found from judge output. best_output.md was not updated.[/red]"
        )

    if stop_reason == STOP_MANUAL_INTERRUPT:
        raise KeyboardInterrupt

    return {
        "run_root": run_root,
        "best_round": best_round,
        "best_score": best_score,
        "best_output": best_output,
        "stop_reason": stop_reason,
        "completed_rounds": completed_rounds,
        "score_history_path": score_history_path,
        "best_output_path": best_output_path,
        "last_review_output": last_review_output,
        "last_revised_output": last_revised_output,
        "last_judge_output": last_judge_output,
        "total_runtime_seconds": total_runtime,
        "last_successful_agent": last_successful_agent,
        "timeout_seen": timeout_seen,
        "provider_quota_failure_seen": provider_quota_failure_seen,
        "invalid_score_seen": invalid_score_seen,
    }
