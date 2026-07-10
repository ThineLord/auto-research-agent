"""Runtime coordination helpers for long-running research runs."""

from __future__ import annotations

import errno
import os
import stat
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, BinaryIO, Dict, Optional, Sequence, Tuple

from rich.console import Console

from .constants import RUN_LOCK_FILENAME
from .storage import append_log_line, read_json_file, write_json_file

RUN_PROCESS_META_FILENAME = "ui_run_process.json"
MODEL_JOB_PROCESS_META_FILENAME = "ui_model_job_process.json"
RUN_LOCK_GUARD_FILENAME = "active_run.guard"
RUN_LOCK_SCHEMA_VERSION = 1
MAX_PROCESS_ID = (1 << 32) - 1


@dataclass(frozen=True)
class BackgroundProcessResult:
    pid: Optional[int]
    error: Optional[str] = None


@dataclass
class RunLockHandle:
    """Owner capability that must be passed intact to ``release_run_lock``."""

    path: Path
    owner_token: str = field(repr=False)
    pid: int
    guard_device: int
    guard_inode: int
    _guard_file: BinaryIO = field(repr=False, compare=False)

    def __fspath__(self) -> str:
        return os.fspath(self.path)

    def __str__(self) -> str:
        return os.fspath(self.path)

    def exists(self) -> bool:
        return self.path.exists()


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
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0 or pid > MAX_PROCESS_ID:
        return False
    if os.name == "nt":
        return _is_windows_pid_running(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except (OverflowError, ValueError):
        return False
    except OSError as exc:
        if exc.errno == errno.ESRCH:
            return False
        return True
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


def _is_windows_pid_running(pid: int) -> bool:
    import ctypes
    from ctypes import wintypes

    process_query_limited_information = 0x1000
    still_active = 259
    invalid_parameter = 87
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    process_handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
    if not process_handle:
        return ctypes.get_last_error() != invalid_parameter
    try:
        exit_code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(process_handle, ctypes.byref(exit_code)):
            return True
        return exit_code.value == still_active
    finally:
        kernel32.CloseHandle(process_handle)


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


def _safe_start_error(exc: Exception) -> str:
    if isinstance(exc, OSError) and exc.strerror:
        detail = exc.strerror
    else:
        detail = exc.__class__.__name__
    return f"{exc.__class__.__name__}: {detail}"


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
        return BackgroundProcessResult(
            pid=None,
            error=f"Failed to start {kind} process: {_safe_start_error(exc)}",
        )


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


def _parse_lock_pid(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value if 0 < value <= MAX_PROCESS_ID else 0
    if isinstance(value, str):
        text = value.strip()
        if not text.isascii() or not text.isdigit():
            return 0
        try:
            parsed = int(text)
        except ValueError:
            return 0
        return parsed if 0 < parsed <= MAX_PROCESS_ID else 0
    return 0


def _lock_metadata(lock_path: Path) -> tuple[Dict[str, Any], bool]:
    try:
        lock_stat = lock_path.lstat()
    except FileNotFoundError:
        return {}, True
    except OSError:
        return {}, False
    if not stat.S_ISREG(lock_stat.st_mode):
        return {}, False
    try:
        return read_json_file(lock_path), True
    except Exception:  # noqa: BLE001 - lock metadata is diagnostic and must be total
        return {}, True


def _active_lock_error(lock_data: Dict[str, Any]) -> str:
    lock_pid = _parse_lock_pid(lock_data.get("pid"))
    lock_mode = str(lock_data.get("mode", "unknown"))
    lock_model = str(lock_data.get("model", "unknown"))
    lock_started = str(lock_data.get("started_at", "unknown"))
    return (
        "Another run is already active. "
        f"pid={lock_pid or 'unknown'} mode={lock_mode} model={lock_model} "
        f"started_at={lock_started}."
    )


def _try_lock_guard(guard_file: BinaryIO) -> bool:
    if os.name == "nt":
        import msvcrt

        guard_file.seek(0)
        try:
            msvcrt.locking(guard_file.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            if exc.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                return False
            raise
        return True

    import fcntl

    try:
        fcntl.flock(guard_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return False
    return True


def _open_guard_file(guard_path: Path) -> BinaryIO:
    try:
        existing_stat = guard_path.lstat()
    except FileNotFoundError:
        existing_stat = None
    if existing_stat is not None and not stat.S_ISREG(existing_stat.st_mode):
        raise OSError("run lock guard must be a regular file")

    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(guard_path, flags, 0o600)
    try:
        opened_stat = os.fstat(descriptor)
        if not stat.S_ISREG(opened_stat.st_mode):
            raise OSError("run lock guard must be a regular file")
        return os.fdopen(descriptor, "r+b")
    except BaseException:
        os.close(descriptor)
        raise


def _guard_identity(guard_file: BinaryIO) -> tuple[int, int]:
    guard_stat = os.fstat(guard_file.fileno())
    return guard_stat.st_dev, guard_stat.st_ino


def _metadata_guard_matches(lock_data: Dict[str, Any], device: int, inode: int) -> bool:
    stored_device = lock_data.get("guard_device")
    stored_inode = lock_data.get("guard_inode")
    return (
        isinstance(stored_device, int)
        and not isinstance(stored_device, bool)
        and isinstance(stored_inode, int)
        and not isinstance(stored_inode, bool)
        and stored_device == device
        and stored_inode == inode
    )


def _unlock_guard(guard_file: BinaryIO) -> None:
    if os.name == "nt":
        import msvcrt

        guard_file.seek(0)
        msvcrt.locking(guard_file.fileno(), msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(guard_file.fileno(), fcntl.LOCK_UN)


def _close_guard(guard_file: BinaryIO) -> None:
    try:
        _unlock_guard(guard_file)
    except (OSError, ValueError):
        pass
    try:
        guard_file.close()
    except (OSError, ValueError):
        pass


def acquire_run_lock(
    project_dir: Path, *, mode: str, model_name: str
) -> Tuple[Optional[RunLockHandle], Optional[str]]:
    lock_path = project_dir / RUN_LOCK_FILENAME
    guard_path = project_dir / RUN_LOCK_GUARD_FILENAME
    guard_file: BinaryIO | None = None
    try:
        project_dir.mkdir(parents=True, exist_ok=True)
        guard_file = _open_guard_file(guard_path)
        guard_acquired = _try_lock_guard(guard_file)
    except OSError as exc:
        if guard_file is not None:
            try:
                guard_file.close()
            except OSError:
                pass
        return None, f"Run lock guard could not be acquired: {exc.__class__.__name__}."

    if not guard_acquired:
        guard_file.close()
        lock_data, _ = _lock_metadata(lock_path)
        return None, _active_lock_error(lock_data)

    guard_device, guard_inode = _guard_identity(guard_file)
    lock_data, regular_or_missing = _lock_metadata(lock_path)
    if not regular_or_missing:
        _close_guard(guard_file)
        return (
            None,
            f"Stale run lock could not be cleared: {RUN_LOCK_FILENAME} is not removable. "
            "Move it aside manually and retry.",
        )

    existing_pid = _parse_lock_pid(lock_data.get("pid")) if lock_data else 0
    same_guard = _metadata_guard_matches(lock_data, guard_device, guard_inode)
    if lock_data and existing_pid and not same_guard and is_pid_running(existing_pid):
        error = _active_lock_error(lock_data)
        _close_guard(guard_file)
        return None, error

    owner_token = uuid.uuid4().hex
    pid = os.getpid()
    try:
        write_json_file(
            lock_path,
            {
                "schema_version": RUN_LOCK_SCHEMA_VERSION,
                "owner_token": owner_token,
                "pid": pid,
                "guard_device": guard_device,
                "guard_inode": guard_inode,
                "mode": mode,
                "model": model_name,
                "started_at": datetime.now().isoformat(),
            },
        )
    except Exception as exc:  # noqa: BLE001
        _close_guard(guard_file)
        return None, f"Run lock metadata could not be written: {exc.__class__.__name__}."

    return (
        RunLockHandle(
            path=lock_path,
            owner_token=owner_token,
            pid=pid,
            guard_device=guard_device,
            guard_inode=guard_inode,
            _guard_file=guard_file,
        ),
        None,
    )


def release_run_lock(lock_handle: Optional[RunLockHandle | Path]) -> None:
    """Release only a live capability owned by the current process; bare paths fail closed."""
    if not isinstance(lock_handle, RunLockHandle):
        return
    guard_file = lock_handle._guard_file
    if guard_file.closed:
        return
    if os.getpid() != lock_handle.pid:
        try:
            guard_file.close()
        except (OSError, ValueError):
            pass
        return
    try:
        lock_data, regular_or_missing = _lock_metadata(lock_handle.path)
        if (
            regular_or_missing
            and lock_data.get("owner_token") == lock_handle.owner_token
            and _parse_lock_pid(lock_data.get("pid")) == lock_handle.pid
            and _metadata_guard_matches(
                lock_data,
                lock_handle.guard_device,
                lock_handle.guard_inode,
            )
        ):
            lock_handle.path.unlink(missing_ok=True)
    except OSError:
        pass
    finally:
        _close_guard(guard_file)
