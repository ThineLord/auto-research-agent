"""Runtime coordination helpers for long-running research runs."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

from rich.console import Console

from .constants import RUN_LOCK_FILENAME
from .storage import append_log_line, read_json_file, write_json_file


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
    return True


def acquire_run_lock(project_dir: Path, *, mode: str, model_name: str) -> Tuple[Optional[Path], Optional[str]]:
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
        lock_path.unlink(missing_ok=True)

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
    lock_path.unlink(missing_ok=True)
