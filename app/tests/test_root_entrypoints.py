"""Offline regressions for the root Makefile forwarder and ./start."""

from __future__ import annotations

import json
import os
import select
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MAKE_ENV_KEYS = ("MAKEFLAGS", "MFLAGS", "MAKELEVEL", "MAKEOVERRIDES")
APP_STUB = """\
ARGS ?=
.PHONY: help mock check test format
help:
\t@printf '%s\\n' help >> "$$TRACE"
mock:
\t@printf '%s\\n' "mock:[$(ARGS)]" >> "$$TRACE"
\t@printf '%s\\n' checkpoint > "$$WORK/mock/checkpoint.json"
check:
\t@printf '%s\\n' check >> "$$TRACE"
test:
\t@printf '%s\\n' test >> "$$TRACE"
\t@exit 9
format:
\t@printf '%s\\n' "format:[$(ARGS)]" >> "$$TRACE"
"""
INSTALL_STUB = ".PHONY: install\ninstall:\n\t@test -x .venv/bin/python\n"
INIT_FILES = {
    "config.yaml",
    "example/task.md",
    "example/memory.md",
}


def _clean_env(**extra: str) -> dict[str, str]:
    env = os.environ.copy()
    for key in (*MAKE_ENV_KEYS, "AUTO_RESEARCH_AGENT_ROOT", "AUTO_RESEARCH_AGENT_START_CWD"):
        env.pop(key, None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.update(extra)
    return env


def _run_make(root: Path, *args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["make", *args],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _forwarding_tree(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "repo"
    app = root / "app"
    app.mkdir(parents=True)
    shutil.copyfile(REPO / "Makefile", root / "Makefile")
    (app / "Makefile").write_text(APP_STUB, encoding="utf-8")
    for name in ("mock", "check", "help", "test"):
        (root / name).mkdir()
    return root, tmp_path / "trace.txt"


def _output(result: subprocess.CompletedProcess[str]) -> str:
    return f"{result.stdout}{result.stderr}"


def test_root_make_forwards_when_same_named_directory_exists(tmp_path: Path) -> None:
    root, trace = _forwarding_tree(tmp_path)
    env = _clean_env(TRACE=str(trace), WORK=str(root))
    args = "--project mock --max-rounds 1"

    forwarded = _run_make(root, "mock", f"ARGS={args}", env=env)
    assert forwarded.returncode == 0, _output(forwarded)
    assert "up to date" not in _output(forwarded)
    assert "Nothing to be done" not in _output(forwarded)
    assert trace.read_text(encoding="utf-8").splitlines() == [f"mock:[{args}]"]
    assert (root / "mock" / "checkpoint.json").read_text(encoding="utf-8") == "checkpoint\n"
    assert list((root / "check").iterdir()) == []

    check = _run_make(root, "check", env=env)
    assert check.returncode == 0, _output(check)
    assert "up to date" not in _output(check)
    assert trace.read_text(encoding="utf-8").splitlines()[-1] == "check"

    help_dir = _run_make(root, "help", env=env)
    default = _run_make(root, env=env)
    assert help_dir.returncode == 0, _output(help_dir)
    assert default.returncode == 0, _output(default)
    assert trace.read_text(encoding="utf-8").splitlines()[-2:] == ["help", "help"]

    plain = _run_make(root, "format", "ARGS=plain", env=env)
    assert plain.returncode == 0, _output(plain)
    assert trace.read_text(encoding="utf-8").splitlines()[-1] == "format:[plain]"

    both = _run_make(root, "check", "mock", f"ARGS={args}", env=env)
    assert both.returncode == 0, _output(both)
    assert "overriding" not in _output(both).lower()
    assert trace.read_text(encoding="utf-8").splitlines()[-2:] == ["check", f"mock:[{args}]"]


def test_root_make_preserves_submake_failure_exit_code(tmp_path: Path) -> None:
    root, trace = _forwarding_tree(tmp_path)
    env = _clean_env(TRACE=str(trace), WORK=str(root))
    direct = _run_make(root, "--no-print-directory", "-C", "app", "test", env=env)
    forwarded = _run_make(root, "test", env=env)

    assert direct.returncode != 0, _output(direct)
    assert forwarded.returncode == direct.returncode
    assert "up to date" not in _output(forwarded)
    assert trace.read_text(encoding="utf-8").splitlines() == ["test", "test"]
    assert "Error 9" in _output(forwarded)


def _files(root: Path) -> set[str]:
    found: set[str] = set()
    for path in root.rglob("*"):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        found.add(path.relative_to(root).as_posix())
    return found


def _isolated_checkout(tmp_path: Path) -> Path:
    checkout = tmp_path / "checkout"
    app = checkout / "app"
    shutil.copytree(
        REPO / "app" / "src",
        app / "src",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    shutil.copytree(
        REPO / "app" / "ui",
        app / "ui",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    shutil.copy2(REPO / "app" / "config.example.yaml", app / "config.example.yaml")
    shutil.copy2(REPO / "start", checkout / "start")
    checkout.joinpath("start").chmod(0o755)
    (app / "Makefile").write_text(INSTALL_STUB, encoding="utf-8")
    wrapper = app / ".venv" / "bin" / "python"
    wrapper.parent.mkdir(parents=True)
    wrapper.write_text(
        f'#!/usr/bin/env bash\nexec {shlex.quote(sys.executable)} "$@"\n',
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    return checkout


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _occupy_loopback(port: int) -> socket.socket | None:
    """Listen on port when it is free. An existing listener is left running."""
    sock = socket.socket()
    try:
        sock.bind(("127.0.0.1", port))
        sock.listen(1)
    except OSError:
        sock.close()
        return None
    return sock


def _install_zero_argument_port_probe(checkout: Path, port: int, argv_log: Path) -> None:
    """Record the shell argv, then bind a free port from the fixture interpreter.

    ./start is still executed with no arguments. The wrapper sees that empty
    forwarding as `-m ui.server` and is the only place that adds `--port`.
    """
    wrapper = checkout / "app" / ".venv" / "bin" / "python"
    wrapper.write_text(
        "#!/usr/bin/env bash\n"
        f"printf '%s\\n' \"$@\" > {shlex.quote(str(argv_log))}\n"
        f'exec {shlex.quote(sys.executable)} "$@" --port {shlex.quote(str(port))}\n',
        encoding="utf-8",
    )
    wrapper.chmod(0o755)


def _read_ready(proc: subprocess.Popen[bytes], timeout: float = 60) -> str:
    assert proc.stdout is not None
    chunks: list[bytes] = []
    deadline = time.monotonic() + timeout
    fd = proc.stdout.fileno()
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        ready, _, _ = select.select([fd], [], [], min(0.5, remaining))
        if not ready:
            if proc.poll() is not None:
                break
            continue
        chunk = os.read(fd, 4096)
        if not chunk:
            break
        chunks.append(chunk)
        if b"http://127.0.0.1:" in b"".join(chunks):
            return b"".join(chunks).decode()
    output = b"".join(chunks).decode()
    raise AssertionError(f"start did not become ready ({proc.poll()})\n{output}")


class _Started:
    def __init__(self, proc: subprocess.Popen[bytes], port: int, output: str) -> None:
        self.proc = proc
        self.port = port
        self.output = output

    def bootstrap(self) -> dict[str, object]:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{self.port}/api/bootstrap", timeout=10
            ) as response:
                assert response.status == 200
                payload = json.loads(response.read().decode())
        except (urllib.error.URLError, AssertionError) as exc:
            raise AssertionError(f"{exc}\n{self.output}") from exc
        assert isinstance(payload, dict)
        return payload

    def close(self) -> None:
        if self.proc.poll() is None:
            os.killpg(self.proc.pid, signal.SIGTERM)
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(self.proc.pid, signal.SIGKILL)
                self.proc.wait(timeout=5)


def _published_port(output: str) -> int:
    marker = "http://127.0.0.1:"
    start = output.rfind(marker)
    if start < 0:
        raise AssertionError(f"start did not publish a port\n{output}")
    digits: list[str] = []
    for char in output[start + len(marker) :]:
        if not char.isdigit():
            break
        digits.append(char)
    if not digits:
        raise AssertionError(f"start did not publish a port\n{output}")
    return int("".join(digits))


def _start_env(home: Path) -> dict[str, str]:
    return _clean_env(
        HOME=str(home),
        STREAMLIT_BROWSER_GATHER_USAGE_STATS="false",
        STREAMLIT_SERVER_HEADLESS="true",
    )


def _bash(script: Path, args: list[str]) -> list[str]:
    # /bin/bash is bash 3.2 on macOS. The shebang can select a newer bash and
    # hide an empty-array nounset failure.
    return ["/bin/bash", str(script), *args]


def _launch(script: Path, cwd: Path, args: list[str], home: Path) -> _Started:
    proc = subprocess.Popen(
        _bash(script, args),
        cwd=cwd,
        env=_start_env(home),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    try:
        output = _read_ready(proc)
    except Exception:
        _Started(proc, 0, "").close()
        raise
    return _Started(proc, _published_port(output), output)


def _start(script: Path, cwd: Path, args: list[str], home: Path) -> _Started:
    port = _free_port()
    started = _launch(script, cwd, ["--port", str(port), *args], home)
    assert started.port == port, started.output
    return started


def _assert_initialized(workspace: Path, *, sentinel: bool) -> None:
    found = _files(workspace) - ({"sentinel.txt"} if sentinel else set())
    assert found == INIT_FILES
    if sentinel:
        assert (workspace / "sentinel.txt").read_text(encoding="utf-8") == "keep"
    assert not (workspace / "example" / "checkpoint.json").exists()


def test_start_relative_workspace_with_spaces_uses_caller_directory(tmp_path: Path) -> None:
    checkout = _isolated_checkout(tmp_path)
    caller = tmp_path / "caller"
    workspace = caller / "my workspace"
    workspace.mkdir(parents=True)
    (workspace / "sentinel.txt").write_text("keep", encoding="utf-8")
    home = tmp_path / "home"
    home.mkdir()
    checkout_before = _files(checkout)
    started = _start(checkout / "start", caller, ["--workspace", "my workspace"], home)
    try:
        payload = started.bootstrap()
        assert payload["projects"] == ["example"]
        _assert_initialized(workspace, sentinel=True)
        assert {path.name for path in caller.iterdir()} == {"my workspace"}
        assert _files(checkout) == checkout_before
    finally:
        started.close()


def test_start_absolute_workspace_with_spaces_stays_put(tmp_path: Path) -> None:
    checkout = _isolated_checkout(tmp_path)
    caller = tmp_path / "elsewhere"
    caller.mkdir()
    workspace = tmp_path / "abs workspace"
    workspace.mkdir()
    (workspace / "sentinel.txt").write_text("keep", encoding="utf-8")
    home = tmp_path / "home"
    home.mkdir()
    checkout_before = _files(checkout)
    started = _start(checkout / "start", caller, [f"--workspace={workspace}"], home)
    try:
        payload = started.bootstrap()
        assert payload["projects"] == ["example"]
        _assert_initialized(workspace, sentinel=True)
        assert _files(checkout) == checkout_before
        assert list(caller.iterdir()) == []
    finally:
        started.close()


def test_start_default_workspace_is_checkout_root_from_another_directory(tmp_path: Path) -> None:
    checkout = _isolated_checkout(tmp_path)
    caller = tmp_path / "unrelated dir"
    caller.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    checkout_before = _files(checkout)
    started = _start(checkout / "start", caller, [], home)
    try:
        payload = started.bootstrap()
        assert payload["projects"] == ["example"]
        assert _files(checkout) - checkout_before == INIT_FILES
        assert not (checkout / "app" / "config.yaml").exists()
        assert list(caller.iterdir()) == []
    finally:
        started.close()


def test_start_with_no_arguments_uses_checkout_root(tmp_path: Path) -> None:
    checkout = _isolated_checkout(tmp_path)
    caller = tmp_path / "unrelated dir"
    caller.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    # The shell contract is zero arguments, so the product default stays 8501.
    # Hold that port when it is free; a dashboard already listening there stays up.
    # The temporary interpreter injects a different port after argv is recorded.
    occupied = _occupy_loopback(8501)
    port = _free_port()
    argv_log = tmp_path / "python-argv.txt"
    _install_zero_argument_port_probe(checkout, port, argv_log)
    checkout_before = _files(checkout)
    try:
        started = _launch(checkout / "start", caller, [], home)
        try:
            assert "unbound variable" not in started.output
            assert argv_log.read_text(encoding="utf-8").splitlines() == ["-m", "ui.server"]
            assert started.port == port
            if occupied is not None:
                assert port != 8501
            payload = started.bootstrap()
            assert payload["projects"] == ["example"]
            assert _files(checkout) - checkout_before == INIT_FILES
            assert not (checkout / "app" / "config.yaml").exists()
            assert list(caller.iterdir()) == []
        finally:
            started.close()
    finally:
        if occupied is not None:
            occupied.close()


def test_start_missing_workspace_value_exits(tmp_path: Path) -> None:
    checkout = _isolated_checkout(tmp_path)
    caller = tmp_path / "caller"
    caller.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    checkout_before = _files(checkout)
    proc = subprocess.Popen(
        _bash(checkout / "start", ["--workspace"]),
        cwd=caller,
        env=_start_env(home),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    try:
        output, _ = proc.communicate(timeout=60)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait(timeout=5)
        raise AssertionError("start hung when --workspace had no value") from None
    assert proc.returncode == 2, output
    assert "unbound variable" not in output
    assert "expected one argument" in output
    assert "http://127.0.0.1:" not in output
    assert _files(checkout) == checkout_before
    assert list(caller.iterdir()) == []
