"""Runtime coordination helpers for long-running research runs."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple

from rich.console import Console

from .constants import RUN_LOCK_FILENAME
from .storage import append_log_line, read_json_file, write_json_file

RUN_PROCESS_META_FILENAME = "ui_run_process.json"
MODEL_JOB_PROCESS_META_FILENAME = "ui_model_job_process.json"


@dataclass(frozen=True)
class BackgroundProcessResult:
    pid: Optional[int]
    error: Optional[str] = None


def shorten_text_by_words(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words])


def log_run(console: Console, log_path: Path, mode: str, message: str) -> None:
    line = f"mode={mode} | {message}"
    console.print(line)
    append_log_line(log_path, line)


def stop_requested(stop_signal_path: Path) -> bool:
    return stop_signal_path.exists()


def is_pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    try:
        result = subprocess.run(
            ["ps", "-o", "stat=", "-p", str(pid)],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return True
    if result.returncode == 0 and result.stdout.strip().startswith("Z"):
        return False
    return True


def run_meta_path(project_dir: Path) -> Path:
    return project_dir / RUN_PROCESS_META_FILENAME


def model_job_meta_path(project_dir: Path) -> Path:
    return project_dir / MODEL_JOB_PROCESS_META_FILENAME


def get_active_process_meta(meta_path: Path) -> Dict[str, Any]:
    meta = read_json_file(meta_path)
    try:
        pid = int(meta.get("pid", 0)) if meta else 0
    except (TypeError, ValueError):
        pid = 0
    if pid and is_pid_running(pid):
        return meta
    try:
        meta_path.unlink(missing_ok=True)
    except OSError:
        pass
    return {}


def start_background_process(
    *,
    command: Sequence[str],
    cwd: Path,
    log_path: Path,
    meta_path: Path,
    kind: str,
    extra: Optional[Dict[str, Any]] = None,
    env_overrides: Optional[Dict[str, str]] = None,
) -> BackgroundProcessResult:
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_file = log_path.open("a", encoding="utf-8")
        try:
            env = os.environ.copy()
            if env_overrides:
                env.update(env_overrides)
            process = subprocess.Popen(
                list(command),
                cwd=str(cwd),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
                env=env,
            )
        finally:
            log_file.close()
        meta: Dict[str, Any] = {
            "pid": process.pid,
            "command": " ".join(command),
            "kind": kind,
            "started_at": datetime.now().isoformat(),
        }
        if extra:
            meta.update(extra)
        write_json_file(meta_path, meta)
        return BackgroundProcessResult(pid=process.pid)
    except Exception as exc:  # noqa: BLE001
        return BackgroundProcessResult(pid=None, error=f"Failed to start {kind} process: {exc}")


def _timeout_output_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def run_project_tests(
    root: Path,
    *,
    timeout_seconds: int = 120,
    python_executable: str = sys.executable,
) -> Dict[str, Any]:
    started = time.monotonic()
    command = [
        python_executable,
        "-m",
        "pytest",
        "-q",
    ]
    try:
        result = subprocess.run(
            command,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        elapsed = time.monotonic() - started
        output = "\n".join(
            part
            for part in [
                _timeout_output_text(exc.stdout),
                _timeout_output_text(exc.stderr),
            ]
            if part
        )
        return {
            "ok": False,
            "returncode": None,
            "elapsed": elapsed,
            "command": " ".join(command),
            "output": output or f"Test run timed out after {timeout_seconds} seconds.",
        }

    elapsed = time.monotonic() - started
    output = "\n".join(part for part in [result.stdout, result.stderr] if part.strip())
    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "elapsed": elapsed,
        "command": " ".join(command),
        "output": output.strip() or "(no test output)",
    }


def acquire_run_lock(
    project_dir: Path, *, mode: str, model_name: str
) -> Tuple[Optional[Path], Optional[str]]:
    lock_path = project_dir / RUN_LOCK_FILENAME
    if lock_path.exists():
        lock_data = read_json_file(lock_path)
        lock_pid = int(lock_data.get("pid", 0)) if lock_data else 0
        if is_pid_running(lock_pid):
            lock_mode = str(lock_data.get("mode", "unknown"))
            lock_model = str(lock_data.get("model", "unknown"))
            lock_started = str(lock_data.get("started_at", "unknown"))
            return (
                None,
                "Another run is already active. "
                f"pid={lock_pid} mode={lock_mode} model={lock_model} started_at={lock_started}.",
            )
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:
            return (
                None,
                f"Stale run lock could not be cleared: {RUN_LOCK_FILENAME} is not removable. "
                "Move it aside manually and retry.",
            )

    write_json_file(
        lock_path,
        {
            "pid": os.getpid(),
            "mode": mode,
            "model": model_name,
            "started_at": datetime.now().isoformat(),
        },
    )
    return lock_path, None


def release_run_lock(lock_path: Optional[Path]) -> None:
    if lock_path is None:
        return
    try:
        lock_path.unlink(missing_ok=True)
    except OSError:
        pass
