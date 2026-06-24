"""Run-level reproducibility metadata helpers."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

RUN_CONFIG_SCHEMA_VERSION = 1


def utc_now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect_prompt_file_hashes(prompt_dir: Path | None) -> dict[str, dict[str, Any]]:
    if prompt_dir is None or not prompt_dir.exists():
        return {}

    prompt_hashes: dict[str, dict[str, Any]] = {}
    for path in sorted(prompt_dir.glob("*.md")):
        if not path.is_file():
            continue
        prompt_hashes[path.name] = {
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        }
    return prompt_hashes


def git_commit_hash(repo_root: Path | None) -> str | None:
    if repo_root is None:
        return None
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    commit = result.stdout.strip()
    return commit or None


def _json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def build_initial_run_config(
    *,
    run_id: str,
    run_root: Path,
    mode: str,
    model_name: str,
    model_provider: str = "",
    model_parameters: Mapping[str, Any] | None = None,
    runtime_config: Mapping[str, Any] | None = None,
    topic_snapshot: Mapping[str, Any] | None = None,
    project_metadata: Mapping[str, Any] | None = None,
    prompt_dir: Path | None = None,
    repo_root: Path | None = None,
    started_at: str | None = None,
    existing_run_config: Mapping[str, Any] | None = None,
    resume_metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    existing = dict(existing_run_config or {})
    start_time = str(existing.get("started_at") or started_at or utc_now_iso())
    current_session_started_at = started_at or utc_now_iso()
    resume_sessions = list(existing.get("resume_sessions", []))
    start_round = int((runtime_config or {}).get("start_round", 1))
    drafting_mode = str((runtime_config or {}).get("drafting_mode", ""))
    if start_round > 1:
        resume_sessions.append(
            {
                "started_at": current_session_started_at,
                "start_round": start_round,
            }
        )

    existing_model = existing.get("model", {})
    existing_provider = (
        str(existing_model.get("provider", "")) if isinstance(existing_model, Mapping) else ""
    )
    model = {
        "provider": model_provider or existing_provider,
        "name": model_name,
        "label": model_name,
    }
    if model_parameters:
        model.update(_json_safe(model_parameters))

    return {
        "schema_version": RUN_CONFIG_SCHEMA_VERSION,
        "run_id": run_id,
        "run_root": str(run_root),
        "mode": mode,
        "drafting_mode": drafting_mode,
        "status": "running",
        "started_at": start_time,
        "current_session_started_at": current_session_started_at,
        "ended_at": None,
        "stop_reason": "",
        "can_resume": None,
        "resume_eligibility": {
            "can_resume": None,
            "resume_from_round": None,
        },
        "model": _json_safe(model),
        "runtime": _json_safe(runtime_config or {}),
        "topic": _json_safe(topic_snapshot or {}),
        "prompt_files": collect_prompt_file_hashes(prompt_dir),
        "git": {
            "commit": git_commit_hash(repo_root),
        },
        "project": _json_safe(project_metadata or {}),
        "resume_metadata": _json_safe(resume_metadata or {}),
        "resume_sessions": resume_sessions,
        "compatibility": {
            "legacy_run_manifest_supported": True,
        },
        "updated_at": current_session_started_at,
    }


def finalize_run_config(
    run_config: Mapping[str, Any],
    *,
    stop_reason: str,
    can_resume: bool,
    completed_rounds: int,
    best_score: float,
    best_round: int | None,
    total_runtime_seconds: float,
    ended_at: str | None = None,
) -> dict[str, Any]:
    finalized = dict(run_config)
    end_time = ended_at or utc_now_iso()
    resume_metadata = finalized.get("resume_metadata")
    resume_metadata = dict(resume_metadata) if isinstance(resume_metadata, Mapping) else {}
    resume_metadata.update(
        {
            "can_resume": can_resume,
            "last_completed_round": completed_rounds,
            "next_round": completed_rounds + 1 if can_resume else None,
            "stop_reason": stop_reason,
        }
    )
    finalized.update(
        {
            "status": "completed",
            "ended_at": end_time,
            "stop_reason": stop_reason,
            "can_resume": can_resume,
            "resume_eligibility": {
                "can_resume": can_resume,
                "resume_from_round": completed_rounds + 1 if can_resume else None,
            },
            "completed_rounds": completed_rounds,
            "best_score": round(best_score, 2),
            "best_round": best_round,
            "total_runtime_seconds": round(total_runtime_seconds, 3),
            "resume_metadata": _json_safe(resume_metadata),
            "updated_at": end_time,
        }
    )
    return finalized


def read_run_config(run_root: Path) -> dict[str, Any]:
    run_config_path = run_root / "run_config.json"
    if run_config_path.exists():
        try:
            data = json.loads(run_config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    manifest_path = run_root / "run_manifest.json"
    if not manifest_path.exists():
        return {}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(manifest, dict):
        return {}
    return {
        "schema_version": 0,
        "run_id": manifest.get("run_id", run_root.name),
        "run_root": manifest.get("run_root", str(run_root)),
        "mode": manifest.get("mode", ""),
        "drafting_mode": manifest.get("drafting_mode", ""),
        "status": "legacy",
        "started_at": manifest.get("started_at", ""),
        "ended_at": None,
        "stop_reason": "",
        "can_resume": None,
        "model": {
            "name": manifest.get("model", ""),
            "label": manifest.get("model", ""),
            "provider": "",
        },
        "runtime": {},
        "topic": {},
        "prompt_files": {},
        "git": {
            "commit": None,
        },
        "project": manifest.get("project", {}),
        "compatibility": {
            "run_config_missing": True,
            "source": "run_manifest.json",
        },
    }
