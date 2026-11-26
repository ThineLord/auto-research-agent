"""Runtime coordination helpers for long-running research runs."""

from __future__ import annotations

import errno
import hashlib
import os
import stat
import struct
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, BinaryIO, Dict, Optional, Sequence, Tuple

from rich.console import Console

from .constants import RUN_LOCK_FILENAME
from .storage import (
    append_log_line,
    artifact_boundary_is_registered,
    artifact_path_exists,
    artifact_path_is_safe,
    ensure_artifact_directory,
    ensure_artifact_paths_safe,
    ensure_project_runtime_paths_safe,
    open_append_text_file,
    open_binary_update_file,
    read_json_file,
    read_regular_text_bounded,
    unlink_artifact_file,
    write_file_text,
    write_file_text_publish_only,
    write_json_file,
)

RUN_PROCESS_META_FILENAME = "ui_run_process.json"
MODEL_JOB_PROCESS_META_FILENAME = "ui_model_job_process.json"
RUN_LOCK_GUARD_FILENAME = "active_run.guard"
STOP_GUARD_FILENAME = "active_stop.guard"
_DASHBOARD_STOP = "ARA_DASHBOARD_STOP_V1 "
RUN_LOCK_SCHEMA_VERSION = 1
MAX_PROCESS_ID = (1 << 32) - 1
# Research modes that hold the run guard. Diagnostic is live but does not read
# STOP_REQUESTED, so it is not stoppable. Edit and maintenance locks use the
# same guard and are not a run.
LIVE_RESEARCH_MODES = frozenset(
    {
        "mock",
        "normal",
        "continuous",
        "diagnostic",
        "session",
        "resume",
    }
)
STOPPABLE_RUN_MODES = frozenset(
    {
        "mock",
        "normal",
        "continuous",
        "session",
        "resume",
    }
)


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
    mode: str
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


@contextmanager
def _stop_guard(project_dir: Path):
    """Serialize dashboard stop publication, run handoff, and the last stop check."""
    with open_binary_update_file(
        project_dir / STOP_GUARD_FILENAME, anchor=project_dir.parent
    ) as guard:
        if os.name == "nt":
            import msvcrt

            guard.seek(0)
            msvcrt.locking(guard.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(guard.fileno(), fcntl.LOCK_EX)
        yield  # Closing the descriptor releases the lock, including on exceptions.


def _dashboard_marker(path: Path) -> str | None:
    """None means absent; the empty string represents any pre-existing manual marker."""
    try:
        text = read_regular_text_bounded(path, max_bytes=256, anchor=path.parent.parent)
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        return "" if artifact_path_exists(path, allow_directory=True) else None
    return text.rstrip("\n") if text.startswith(_DASHBOARD_STOP) else ""


def _ui_marker(meta: dict) -> str:
    return _DASHBOARD_STOP + ui_run_generation(meta)


def ui_run_generation(meta: dict) -> str:
    return f"ui {meta.get('pid')} {meta.get('started_at', '')}"


def _owner_marker(token: str) -> str:
    return _DASHBOARD_STOP + token


def stop_requested(stop_signal_path: Path) -> bool:
    if not artifact_boundary_is_registered(stop_signal_path):
        try:
            ensure_project_runtime_paths_safe(
                stop_signal_path.parent,
                anchor=stop_signal_path.parent.parent,
            )
        except OSError:
            return False
    if not artifact_path_exists(stop_signal_path, allow_directory=True):
        return False
    marker = _dashboard_marker(stop_signal_path)
    if not marker:
        return marker == ""
    project = stop_signal_path.parent
    lock = read_json_file(project / RUN_LOCK_FILENAME)
    if isinstance(lock.get("owner_token"), str) and marker == _owner_marker(lock["owner_token"]):
        return True
    ui = get_active_process_meta(run_meta_path(project), cleanup=False)
    return bool(ui and marker == _ui_marker(ui) and (not lock or lock.get("pid") == ui["pid"]))


def request_dashboard_stop(project: Path, expected: dict) -> None:
    """Revalidate the selected generation while its stop window cannot close."""
    with _stop_guard(project):
        cli = read_live_cli_run(project)
        ui = get_active_process_meta(run_meta_path(project), cleanup=False)
        current = cli if expected.get("kind") == "cli_run" else ui
        if current is ui and ui:
            current = {**ui, "generation": ui_run_generation(ui)}
        if not current or any(
            current.get(key) != expected.get(key) for key in ("pid", "started_at", "generation")
        ):
            raise ValueError("No active run")
        lock = read_json_file(project / RUN_LOCK_FILENAME)
        if not run_accepts_cooperative_stop(current) or (
            lock
            and (
                lock.get("pid") != current.get("pid")
                or lock.get("mode") not in STOPPABLE_RUN_MODES
                or lock.get("stoppable") is False
            )
        ):
            raise ValueError("This run cannot be stopped safely")
        token = lock.get("owner_token")
        marker = _owner_marker(token) if isinstance(token, str) and token else _ui_marker(current)
        path = project / "STOP_REQUESTED"
        existing = _dashboard_marker(path)
        if existing is None:
            try:
                write_file_text_publish_only(path, marker + "\n", anchor=project.parent)
            except FileExistsError:
                pass  # A manual marker published concurrently already requests a stop.
        elif existing and existing != marker:
            write_file_text(path, marker + "\n", anchor=project.parent)


def close_run_stop_window(handle: RunLockHandle | None) -> bool:
    """Close the window before finalizing, and observe any already accepted stop."""
    if not isinstance(handle, RunLockHandle):
        return False
    project = handle.path.parent
    with _stop_guard(project):
        if not run_lock_handle_is_current(project, handle):
            return False
        meta = read_json_file(handle.path)
        meta["stoppable"] = False
        write_json_file(handle.path, meta)
        return stop_requested(project / "STOP_REQUESTED")


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


def _recorded_pid(meta: Dict[str, Any]) -> int:
    try:
        pid = int(meta.get("pid", 0)) if meta else 0
    except (TypeError, ValueError):
        return 0
    if pid <= 0 or pid > MAX_PROCESS_ID:
        return 0
    return pid


def _process_meta_snapshot(
    meta_path: Path,
) -> tuple[Dict[str, Any], Optional[tuple[int, int, int, int]]]:
    """Return metadata and the file identity observed with it.

    A missing file has no identity, so the caller must not unlink. A file that
    changes between the stat and the read also has no identity: that is a new
    record and must be left in place.
    """
    try:
        ensure_project_runtime_paths_safe(
            meta_path.parent,
            anchor=meta_path.parent.parent,
        )
    except OSError:
        return {}, None
    if not artifact_path_is_safe(meta_path, allow_missing=True):
        return {}, None
    try:
        before = meta_path.lstat()
    except FileNotFoundError:
        return {}, None
    except OSError:
        return {}, None
    if not stat.S_ISREG(before.st_mode):
        return {}, None
    meta = read_json_file(meta_path)
    try:
        after = meta_path.lstat()
    except OSError:
        return {}, None
    identity = (after.st_dev, after.st_ino, after.st_size, getattr(after, "st_mtime_ns", 0))
    observed = (before.st_dev, before.st_ino, before.st_size, getattr(before, "st_mtime_ns", 0))
    if identity != observed:
        return {}, None
    return meta if isinstance(meta, dict) else {}, identity


def _unlink_process_meta(meta_path: Path, identity: tuple[int, int, int, int]) -> None:
    try:
        current = meta_path.lstat()
    except OSError:
        return
    if (
        current.st_dev,
        current.st_ino,
        current.st_size,
        getattr(current, "st_mtime_ns", 0),
    ) != identity:
        return
    try:
        unlink_artifact_file(meta_path)
    except OSError:
        pass


def get_active_process_meta(meta_path: Path, *, cleanup: bool = True) -> Dict[str, Any]:
    """Return live process metadata.

    ``cleanup`` removes a stale record this call actually observed. Read-only
    callers pass False so they cannot delete a record published after the read
    decided the file was missing or expired.
    """
    meta, identity = _process_meta_snapshot(meta_path)
    pid = _recorded_pid(meta)
    if pid and is_pid_running(pid):
        return meta
    if not cleanup or identity is None:
        return {}
    current, current_identity = _process_meta_snapshot(meta_path)
    if current_identity != identity:
        current_pid = _recorded_pid(current)
        if current_pid and is_pid_running(current_pid):
            return current
        return {}
    current_pid = _recorded_pid(current)
    if current_pid and is_pid_running(current_pid):
        return current
    _unlink_process_meta(meta_path, identity)
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
    process: subprocess.Popen[str] | None = None
    try:
        log_parent = Path(os.path.abspath(log_path.parent))
        meta_parent = Path(os.path.abspath(meta_path.parent))
        if log_parent != meta_parent:
            raise OSError("background log and metadata must share one project directory")
        ensure_project_runtime_paths_safe(log_parent, anchor=log_parent.parent)
        ensure_artifact_paths_safe((log_path, meta_path))
        log_file = open_append_text_file(log_path)
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
        if process is not None:
            try:
                process.terminate()
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    process.kill()
                    process.wait(timeout=5)
                except (OSError, subprocess.SubprocessError):
                    pass
            except (OSError, subprocess.SubprocessError):
                pass
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
    return open_binary_update_file(guard_path)


def _guard_identity(guard_file: BinaryIO) -> tuple[int, int]:
    guard_stat = os.fstat(guard_file.fileno())
    return guard_stat.st_dev, guard_stat.st_ino


def _lock_int(value: object) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


_PROC_LOCKS_PATH = Path("/proc/locks")
# Darwin struct flock: off_t, off_t, pid_t, short, short. Native alignment is 24 bytes.
_DARWIN_FLOCK = struct.Struct("@qqihh")
_DARWIN_VNODE = 1
_DARWIN_LIST_FDS = 1
_DARWIN_FD_VNODE = 1


def run_accepts_cooperative_stop(meta: Dict[str, Any]) -> bool:
    """True when this live record belongs to a mode that consumes STOP_REQUESTED."""
    if not isinstance(meta, dict) or not meta:
        return False
    marker = meta.get("stoppable")
    if isinstance(marker, bool):
        return marker
    mode = meta.get("mode")
    if isinstance(mode, str) and mode in LIVE_RESEARCH_MODES:
        return mode in STOPPABLE_RUN_MODES
    return True


def _proc_locks_text() -> Optional[str]:
    try:
        return _PROC_LOCKS_PATH.read_text(encoding="utf-8")
    except OSError:
        return None


def _proc_locks_show_write_flock(text: str, device: int, inode: int, pid: int) -> bool:
    identity = f"{os.major(device):02x}:{os.minor(device):02x}:{inode}"
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 6:
            continue
        if (
            parts[1] == "FLOCK"
            and parts[3] == "WRITE"
            and parts[4] == str(pid)
            and parts[5] == identity
        ):
            return True
    return False


def _devices_match(left: int, right: int) -> bool:
    return left == right or (left & 0xFFFFFFFF) == (right & 0xFFFFFFFF)


def _open_inode_matches(device: int, inode: int, records: Sequence[tuple[int, int]]) -> bool:
    return any(
        seen_inode == inode and _devices_match(seen_device, device)
        for seen_device, seen_inode in records
    )


def _darwin_lock_is_held(
    lock_type: int,
    lock_pid: int,
    pid: int,
    write_type: int,
    inode_open: bool,
) -> bool:
    """Attribute a Darwin F_GETLK result to this project's flock holder.

    flock(2) is visible to F_GETLK, but its owner pid is -1. A write lock with
    an unknown owner counts only when the recorded PID still has that inode
    open. A different pid, or a live PID alone, does not.
    """
    if lock_type != write_type:
        return False
    if lock_pid == pid:
        return True
    if lock_pid == -1:
        return inode_open
    return False


def _darwin_proc_library() -> Any:
    import ctypes
    import ctypes.util

    # `import ctypes` does not load ctypes.util. A clean interpreter raises
    # AttributeError here, and the caller then treats the guard as unlocked.
    library = ctypes.util.find_library("proc") or "/usr/lib/libSystem.B.dylib"
    loaded = ctypes.CDLL(library, use_errno=True)
    for name in ("proc_pidinfo", "proc_pidfdinfo"):
        function = getattr(loaded, name)
        function.restype = ctypes.c_int
    loaded.proc_pidinfo.argtypes = [
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint64,
        ctypes.c_void_p,
        ctypes.c_int,
    ]
    loaded.proc_pidfdinfo.argtypes = [
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_int,
    ]
    return loaded


def _darwin_open_inodes(pid: int) -> Optional[list[tuple[int, int]]]:
    import ctypes

    try:
        library = _darwin_proc_library()
    except (AttributeError, OSError):
        return None
    fd_size = 8
    capacity = 256
    listed: Optional[bytes] = None
    while capacity <= 65536:
        raw = ctypes.create_string_buffer(capacity * fd_size)
        written = library.proc_pidinfo(pid, _DARWIN_LIST_FDS, 0, raw, len(raw))
        if written < 0:
            return None
        if written < len(raw) or capacity >= 65536:
            listed = raw.raw[: max(written, 0)]
            break
        capacity *= 2
    if not listed:
        return []
    records: list[tuple[int, int]] = []
    info = ctypes.create_string_buffer(256)
    for offset in range(0, len(listed) - (fd_size - 1), fd_size):
        fd, fd_type = struct.unpack_from("@iI", listed, offset)
        if fd_type != _DARWIN_VNODE:
            continue
        size = library.proc_pidfdinfo(pid, fd, _DARWIN_FD_VNODE, info, len(info))
        if size < 40:
            continue
        # proc_fileinfo is 24 bytes; vinfo_stat.vst_dev then vst_ino at +8.
        device, inode = struct.unpack_from("@IQ", info.raw, 24)
        records.append((device, inode))
    return records


def _darwin_blocking_lock(fd: int) -> Optional[tuple[int, int]]:
    import fcntl

    query = _DARWIN_FLOCK.pack(0, 0, 0, fcntl.F_WRLCK, os.SEEK_SET)
    try:
        raw = fcntl.fcntl(fd, fcntl.F_GETLK, query)
    except OSError:
        return None
    if not isinstance(raw, (bytes, bytearray)) or len(raw) < _DARWIN_FLOCK.size:
        return None
    _start, _length, lock_pid, lock_type, _whence = _DARWIN_FLOCK.unpack_from(raw)
    return lock_type, lock_pid


def _darwin_write_flock_held_by(guard_path: Path, device: int, inode: int, pid: int) -> bool:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(guard_path, flags)
    except OSError:
        return False
    try:
        opened = os.fstat(descriptor)
        if opened.st_ino != inode or not _devices_match(opened.st_dev, device):
            return False
        import fcntl

        found = _darwin_blocking_lock(descriptor)
        if found is None:
            return False
        lock_type, lock_pid = found
        if lock_type != fcntl.F_WRLCK:
            return False
        if lock_pid == pid:
            return True
        if lock_pid != -1:
            return False
        records = _darwin_open_inodes(pid)
        if records is None:
            return False
        return _darwin_lock_is_held(
            lock_type, lock_pid, pid, fcntl.F_WRLCK, _open_inode_matches(device, inode, records)
        )
    except OSError:
        return False
    finally:
        os.close(descriptor)


def _non_proc_write_flock_held_by(guard_path: Path, device: int, inode: int, pid: int) -> bool:
    """Observe a write flock where /proc/locks does not exist.

    macOS reports the project's BSD flock through F_GETLK and attributes it
    with libproc. Tests replace this function to exercise that branch offline.
    """
    if sys.platform != "darwin":
        return False
    return _darwin_write_flock_held_by(guard_path, device, inode, pid)


def _write_flock_held_by(guard_path: Path, device: int, inode: int, pid: int) -> bool:
    """True when that PID holds the guard's write flock.

    Linux flock is not visible to fcntl F_GETLK, so /proc/locks is read without
    acquiring the lock. macOS uses F_GETLK plus the PID's open inodes. A poll
    never takes the guard, and a merely live PID is not enough.
    """
    text = _proc_locks_text()
    if text is not None:
        return _proc_locks_show_write_flock(text, device, inode, pid)
    return _non_proc_write_flock_held_by(guard_path, device, inode, pid)


def _live_cli_run_record(project_dir: Path) -> Dict[str, Any]:
    try:
        ensure_project_runtime_paths_safe(project_dir, anchor=project_dir.parent)
    except OSError:
        return {}
    lock_path = project_dir / RUN_LOCK_FILENAME
    guard_path = project_dir / RUN_LOCK_GUARD_FILENAME
    anchor = project_dir.parent
    if not artifact_path_is_safe(lock_path, allow_missing=False, anchor=anchor):
        return {}
    if not artifact_path_is_safe(guard_path, allow_missing=False, anchor=anchor):
        return {}
    try:
        lock_data = read_json_file(lock_path)
        guard_stat = guard_path.lstat()
    except OSError:
        return {}
    if not stat.S_ISREG(guard_stat.st_mode) or not isinstance(lock_data, dict):
        return {}
    mode = lock_data.get("mode")
    owner = lock_data.get("owner_token")
    model = lock_data.get("model")
    pid = _parse_lock_pid(lock_data.get("pid"))
    device = _lock_int(lock_data.get("guard_device"))
    inode = _lock_int(lock_data.get("guard_inode"))
    if (
        lock_data.get("schema_version") != RUN_LOCK_SCHEMA_VERSION
        or not isinstance(owner, str)
        or not owner
        or not isinstance(mode, str)
        or mode not in LIVE_RESEARCH_MODES
        or not isinstance(model, str)
        or not pid
        or not is_pid_running(pid)
        or device != guard_stat.st_dev
        or inode != guard_stat.st_ino
        or not _write_flock_held_by(guard_path, guard_stat.st_dev, guard_stat.st_ino, pid)
    ):
        return {}
    started = lock_data.get("started_at")
    return {
        "pid": pid,
        "mode": mode,
        "model": model,
        "started_at": started if isinstance(started, str) else "",
        "kind": "cli_run",
        "generation": hashlib.sha256(owner.encode()).hexdigest(),
        "stoppable": mode in STOPPABLE_RUN_MODES and lock_data.get("stoppable") is not False,
        "command": " ".join(part for part in (mode, model) if part),
    }


def read_live_cli_run(project_dir: Path) -> Dict[str, Any]:
    """Return a live owned research run, including a non-stoppable diagnostic.

    Ownerless metadata and edit/maintenance locks stay invisible. A matching
    UI process record is preferred by the dashboard and is not read here.
    """
    return _live_cli_run_record(project_dir)


def read_stoppable_cli_run(project_dir: Path) -> Dict[str, Any]:
    """Return a live run that will consume STOP_REQUESTED."""
    meta = _live_cli_run_record(project_dir)
    if not meta.get("stoppable"):
        return {}
    return meta


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

    stale_lock_error = (
        f"Stale run lock could not be cleared: {RUN_LOCK_FILENAME} is not removable. "
        "Move it aside manually and retry."
    )
    try:
        ensure_artifact_directory(project_dir, anchor=project_dir.parent)
    except OSError as exc:
        return None, f"Project runtime artifacts could not be validated: {exc.__class__.__name__}."

    try:
        ensure_artifact_paths_safe((lock_path,), anchor=project_dir.parent)
    except OSError:
        return None, stale_lock_error

    try:
        ensure_artifact_paths_safe((guard_path,), anchor=project_dir.parent)
    except OSError as exc:
        return None, f"Run lock guard could not be acquired: {exc.__class__.__name__}."

    try:
        ensure_project_runtime_paths_safe(project_dir, anchor=project_dir.parent)
    except OSError as exc:
        # Recheck the two lock leaves so an active replacement retains the most
        # actionable historical diagnosis instead of being mislabeled as a guard error.
        if not artifact_path_is_safe(
            lock_path,
            allow_missing=True,
            anchor=project_dir.parent,
        ):
            return None, stale_lock_error
        if not artifact_path_is_safe(
            guard_path,
            allow_missing=True,
            anchor=project_dir.parent,
        ):
            return None, f"Run lock guard could not be acquired: {exc.__class__.__name__}."
        return None, f"Project runtime artifacts could not be validated: {exc.__class__.__name__}."

    try:
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
        return None, stale_lock_error

    existing_pid = _parse_lock_pid(lock_data.get("pid")) if lock_data else 0
    same_guard = _metadata_guard_matches(lock_data, guard_device, guard_inode)
    if lock_data and existing_pid and not same_guard and is_pid_running(existing_pid):
        error = _active_lock_error(lock_data)
        _close_guard(guard_file)
        return None, error

    owner_token = uuid.uuid4().hex
    pid = os.getpid()
    try:
        with _stop_guard(project_dir) if mode in LIVE_RESEARCH_MODES else nullcontext():
            if mode in LIVE_RESEARCH_MODES:
                # Recover after a crash, or adopt a UI request made before its child acquired the guard.
                path = project_dir / "STOP_REQUESTED"
                previous = _dashboard_marker(path)
                if previous:
                    ui = get_active_process_meta(run_meta_path(project_dir), cleanup=False)
                    if ui.get("pid") == pid and previous == _ui_marker(ui):
                        write_file_text(
                            path, _owner_marker(owner_token) + "\n", anchor=project_dir.parent
                        )
                    else:
                        unlink_artifact_file(path)
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
            mode=mode,
            _guard_file=guard_file,
        ),
        None,
    )


def run_lock_handle_is_current(
    project_dir: Path,
    lock_handle: object,
) -> bool:
    """Return whether a live capability still owns this project's fixed lock."""
    if not isinstance(lock_handle, RunLockHandle):
        return False
    if lock_handle._guard_file.closed or lock_handle.pid != os.getpid():
        return False
    expected_path = Path(project_dir).expanduser().absolute() / RUN_LOCK_FILENAME
    if lock_handle.path.expanduser().absolute() != expected_path:
        return False
    try:
        lock_data, regular_or_missing = _lock_metadata(lock_handle.path)
    except OSError:
        return False
    return bool(
        regular_or_missing
        and lock_data.get("owner_token") == lock_handle.owner_token
        and _parse_lock_pid(lock_data.get("pid")) == lock_handle.pid
        and _metadata_guard_matches(
            lock_data,
            lock_handle.guard_device,
            lock_handle.guard_inode,
        )
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
        project = lock_handle.path.parent
        with _stop_guard(project) if lock_handle.mode in LIVE_RESEARCH_MODES else nullcontext():
            if run_lock_handle_is_current(project, lock_handle):
                if lock_handle.mode in LIVE_RESEARCH_MODES:
                    path = project / "STOP_REQUESTED"
                    if _dashboard_marker(path) == _owner_marker(lock_handle.owner_token):
                        unlink_artifact_file(path)
                    ui_path = run_meta_path(project)
                    if read_json_file(ui_path).get("pid") == lock_handle.pid:
                        unlink_artifact_file(ui_path)
                unlink_artifact_file(lock_handle.path)
    except OSError:
        pass
    finally:
        _close_guard(guard_file)
