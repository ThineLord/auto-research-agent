"""Python selection for make venv/install and ./start.

The macOS failure is python3==3.9 with python3.13 also on PATH. Setup must not
create that 3.9 environment, must not install into it, and must not delete an
environment that already exists.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
APP_VENV = REPO / "app" / ".venv"
MAKE_ENV_KEYS = ("MAKEFLAGS", "MFLAGS", "MAKELEVEL", "MAKEOVERRIDES")
CANDIDATES = ("python3.13", "python3.12", "python3.11", "python3.10", "python3", "python")


def _cfg(path: Path) -> bytes | None:
    cfg = path / "pyvenv.cfg"
    if not path.exists():
        return None
    if cfg.is_file():
        return cfg.read_bytes()
    return b""


@pytest.fixture(autouse=True)
def preserve_workspace_venv() -> object:
    before = (APP_VENV.exists(), _cfg(APP_VENV))
    yield
    assert (APP_VENV.exists(), _cfg(APP_VENV)) == before


def _output(result: subprocess.CompletedProcess[str]) -> str:
    return f"{result.stdout}{result.stderr}"


def _tool_path(bin_dir: Path) -> dict[str, str]:
    env = os.environ.copy()
    for key in (*MAKE_ENV_KEYS, "PYTHON", "VENV"):
        env.pop(key, None)
    make = shutil.which("make")
    assert make is not None
    link = bin_dir / "make"
    if not link.exists():
        link.symlink_to(make)
    # Core utilities stay available. Interpreter names in bin_dir come first,
    # so a system python3.12 cannot skip ahead of these fakes.
    env["PATH"] = f"{bin_dir}:/usr/bin:/bin"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _fake_python(path: Path, version: str, log: Path, delegate: Path | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if delegate is None:
        action = 'printf "refusing %s\\n" "$*" >> "$LOG"\nexit 99\n'
    else:
        action = f'exec {shlex_quote(delegate)} "$@"\n'
    path.write_text(
        "#!/bin/bash\n"
        "set -euo pipefail\n"
        f"LOG={shlex_quote(log)}\n"
        'printf "%s\\n" "$*" >> "$LOG"\n'
        'if [[ "${1:-}" == "-c" ]]; then\n'
        f"  printf '%s\\n' {shlex_quote(version)}\n"
        "  exit 0\n"
        "fi\n"
        f"{action}",
        encoding="utf-8",
    )
    path.chmod(0o755)


def shlex_quote(path: Path) -> str:
    text = str(path)
    return "'" + text.replace("'", "'\\''") + "'"


def _run_make(
    goal: str,
    venv: Path,
    env: dict[str, str],
    *extra: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["make", goal, f"VENV={venv}", *extra],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


def _log(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def test_make_venv_selects_supported_python_over_older_python3(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    old_log = tmp_path / "old.log"
    new_log = tmp_path / "new.log"
    _fake_python(bin_dir / "python3", "3.9.6", old_log, None)
    _fake_python(bin_dir / "python3.13", "3.13.15", new_log, Path(sys.executable))
    venv = tmp_path / "venv"
    result = _run_make("venv", venv, _tool_path(bin_dir))
    output = _output(result)

    assert result.returncode == 0, output
    assert "Using Python 3.13.15 (python3.13)" in output
    assert (venv / "pyvenv.cfg").is_file()
    assert "venv" not in _log(old_log)
    assert "venv" in _log(new_log)
    version = subprocess.check_output(
        [venv / "bin" / "python", "-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
        text=True,
    )
    major, minor = (int(part) for part in version.strip().split("."))
    assert (major, minor) >= (3, 10)


def test_environment_python_override_beats_a_newer_candidate(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    preferred = tmp_path / "preferred.log"
    chosen = tmp_path / "chosen.log"
    _fake_python(bin_dir / "python3.13", "3.13.15", preferred, None)
    _fake_python(bin_dir / "python3.11", "3.11.9", chosen, Path(sys.executable))
    env = _tool_path(bin_dir)
    env["PYTHON"] = "python3.11"
    venv = tmp_path / "venv"
    result = _run_make("venv", venv, env)
    output = _output(result)

    assert result.returncode == 0, output
    assert "Using Python 3.11.9 (python3.11)" in output
    assert "venv" not in _log(preferred)
    assert "venv" in _log(chosen)


def test_command_line_python_override_is_the_interpreter_that_creates_venv(
    tmp_path: Path,
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    preferred = tmp_path / "preferred.log"
    chosen = tmp_path / "chosen.log"
    old_log = tmp_path / "old.log"
    _fake_python(bin_dir / "python3.13", "3.13.15", preferred, None)
    _fake_python(bin_dir / "python3", "3.9.6", old_log, None)
    _fake_python(bin_dir / "python3.10", "3.10.14", chosen, Path(sys.executable))
    venv = tmp_path / "venv"
    result = _run_make("venv", venv, _tool_path(bin_dir), "PYTHON=python3.10")
    output = _output(result)

    assert result.returncode == 0, output
    assert "Using Python 3.10.14 (python3.10)" in output
    assert "venv" not in _log(preferred)
    assert "venv" not in _log(old_log)
    assert "venv" in _log(chosen)


def test_make_venv_stops_before_create_when_only_unsupported_pythons_exist(
    tmp_path: Path,
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "old.log"
    for name in CANDIDATES:
        _fake_python(bin_dir / name, "3.9.6", log, None)
    venv = tmp_path / "venv"
    result = _run_make("venv", venv, _tool_path(bin_dir))
    output = _output(result)

    assert result.returncode == 2, output
    assert not venv.exists()
    assert "Python 3.10 or newer is required." in output
    assert "No virtual environment was created and no packages were installed." in output
    assert "python3: Python 3.9.6" in output
    assert "Install Python 3.10 or newer, then rerun:" in output
    assert "make install-dev" in output
    assert "venv" not in _log(log)


def test_explicit_unsupported_python_does_not_create_when_newer_exists(
    tmp_path: Path,
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    old_log = tmp_path / "old.log"
    new_log = tmp_path / "new.log"
    _fake_python(bin_dir / "python3", "3.9.6", old_log, None)
    _fake_python(bin_dir / "python3.13", "3.13.15", new_log, None)
    venv = tmp_path / "venv"
    result = _run_make("venv", venv, _tool_path(bin_dir), "PYTHON=python3")
    output = _output(result)

    assert result.returncode == 2, output
    assert not venv.exists()
    assert "Python 3.10 or newer is required." in output
    assert "Python 3.9.6" in output
    assert "No virtual environment was created and no packages were installed." in output
    assert "make install-dev" in output
    assert "PYTHON=python3.13" in output
    assert "venv" not in _log(old_log)
    assert "venv" not in _log(new_log)


def _incompatible_venv(path: Path, log: Path) -> None:
    _fake_python(path / "bin" / "python", "3.9.6", log, None)
    (path / "KEEP").write_text("keep", encoding="utf-8")


def test_install_keeps_incompatible_venv_and_does_not_install(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    old_log = tmp_path / "old.log"
    new_log = tmp_path / "new.log"
    _fake_python(bin_dir / "python3.13", "3.13.15", new_log, None)
    venv = tmp_path / "old-venv"
    _incompatible_venv(venv, old_log)
    env = _tool_path(bin_dir)

    plain = _run_make("install", venv, env)
    explicit = _run_make("install-dev", venv, env, "PYTHON=python3.13")

    for result in (plain, explicit):
        output = _output(result)
        assert result.returncode == 2, output
        assert "Python 3.10 or newer is required." in output
        assert "Python 3.9.6" in output
        assert "left unchanged and was not deleted" in output
        assert f"mv {venv} {venv}-python3.9" in output
        assert "make install-dev" in output
        assert "PYTHON=python3.13" in output
        assert "No packages were installed." in output
    assert (venv / "KEEP").read_text(encoding="utf-8") == "keep"
    assert not (venv / ".install.stamp").exists()
    assert not (venv / ".install-dev.stamp").exists()
    assert "pip" not in _log(old_log)
    assert "venv" not in _log(old_log)
    assert "venv" not in _log(new_log)


def test_empty_environment_directory_is_not_filled_in(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    new_log = tmp_path / "new.log"
    _fake_python(bin_dir / "python3.13", "3.13.15", new_log, None)
    venv = tmp_path / "empty-venv"
    venv.mkdir()
    marker = venv / "KEEP"
    marker.write_text("keep", encoding="utf-8")
    result = _run_make("venv", venv, _tool_path(bin_dir))
    output = _output(result)

    assert result.returncode == 2, output
    assert marker.read_text(encoding="utf-8") == "keep"
    assert not (venv / "bin").exists()
    assert "left unchanged and was not deleted" in output
    assert "venv" not in _log(new_log)


def test_qualified_venv_survives_a_different_python_override(tmp_path: Path) -> None:
    venv = tmp_path / "good"
    created = subprocess.run(
        [sys.executable, "-m", "venv", str(venv)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert created.returncode == 0, created.stderr
    cfg = (venv / "pyvenv.cfg").read_bytes()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    result = _run_make("venv", venv, _tool_path(bin_dir), "PYTHON=/missing/python")
    output = _output(result)

    assert result.returncode == 0, output
    assert (venv / "pyvenv.cfg").read_bytes() == cfg
    assert "required" not in output.lower()
    assert "No packages were installed." not in output


def test_venv_variable_override_creates_the_requested_directory(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    old_log = tmp_path / "old.log"
    new_log = tmp_path / "new.log"
    _fake_python(bin_dir / "python3", "3.9.6", old_log, None)
    _fake_python(bin_dir / "python3.13", "3.13.15", new_log, Path(sys.executable))
    env = _tool_path(bin_dir)
    target = tmp_path / "custom" / "env"
    env["VENV"] = str(target)
    result = subprocess.run(
        ["make", "venv"],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    output = _output(result)

    assert result.returncode == 0, output
    assert (target / "pyvenv.cfg").is_file()
    assert "venv" not in _log(old_log)
    assert "venv" in _log(new_log)


def _mini_checkout(tmp_path: Path) -> Path:
    checkout = tmp_path / "checkout"
    app = checkout / "app"
    deps = app / "scripts" / "dependencies"
    deps.mkdir(parents=True)
    shutil.copy2(REPO / "start", checkout / "start")
    shutil.copy2(REPO / "app" / "Makefile", app / "Makefile")
    script = REPO / "app" / "scripts" / "ensure_python_env.sh"
    copied = app / "scripts" / "ensure_python_env.sh"
    shutil.copy2(script, copied)
    copied.chmod(0o755)
    shutil.copy2(REPO / "app" / "pyproject.toml", app / "pyproject.toml")
    shutil.copy2(
        REPO / "app" / "scripts" / "dependencies" / "constraints.txt",
        deps / "constraints.txt",
    )
    return checkout


def _start(
    checkout: Path, env: dict[str, str], args: list[str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/bash", str(checkout / "start"), *args],
        cwd=checkout.parent,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


def test_start_does_not_create_venv_when_only_python39_exists(tmp_path: Path) -> None:
    checkout = _mini_checkout(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "old.log"
    for name in CANDIDATES:
        _fake_python(bin_dir / name, "3.9.6", log, None)
    result = _start(checkout, _tool_path(bin_dir), ["--help"])
    output = _output(result)

    assert result.returncode == 2, output
    assert not (checkout / "app" / ".venv").exists()
    assert "Python 3.10 or newer is required." in output
    assert "No virtual environment was created and no packages were installed." in output
    assert "usage:" not in output.lower()
    assert "venv" not in _log(log)


def test_start_keeps_incompatible_venv_instead_of_reusing_it(tmp_path: Path) -> None:
    checkout = _mini_checkout(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    old_log = tmp_path / "old.log"
    new_log = tmp_path / "new.log"
    _fake_python(bin_dir / "python3", "3.9.6", old_log, None)
    _fake_python(bin_dir / "python3.13", "3.13.15", new_log, None)
    venv = checkout / "app" / ".venv"
    _incompatible_venv(venv, old_log)
    result = _start(checkout, _tool_path(bin_dir), ["--help"])
    output = _output(result)

    assert result.returncode == 2, output
    assert (venv / "KEEP").read_text(encoding="utf-8") == "keep"
    assert not (venv / ".install.stamp").exists()
    assert "left unchanged and was not deleted" in output
    assert "PYTHON=python3.13" in output
    assert "No packages were installed." in output
    assert "usage:" not in output.lower()
    assert "pip" not in _log(old_log)
    assert "venv" not in _log(new_log)


def _real_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in (*MAKE_ENV_KEYS, "PYTHON", "VENV"):
        env.pop(key, None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _patch_pip_main(venv: Path, log: Path, code: int) -> None:
    location = subprocess.check_output(
        [
            str(venv / "bin" / "python"),
            "-c",
            "import pathlib, pip\n"
            "print(pathlib.Path(pip.__file__).resolve().parent / '__main__.py')",
        ],
        text=True,
        env=_real_env(),
    ).strip()
    Path(location).write_text(
        "import pathlib, sys\n"
        f"path = pathlib.Path({str(log)!r})\n"
        "with path.open('a', encoding='utf-8') as handle:\n"
        "    handle.write(' '.join(sys.argv[1:]) + '\\n')\n"
        f"raise SystemExit({code})\n",
        encoding="utf-8",
    )


def _remove_pip(venv: Path) -> None:
    for site in venv.glob("lib/python*/site-packages"):
        for child in list(site.iterdir()):
            if child.name == "pip" or child.name.startswith("pip-"):
                shutil.rmtree(child)
    for name in ("pip", "pip3", "pip3.12"):
        path = venv / "bin" / name
        if path.is_symlink() or path.exists():
            path.unlink()


def _make(
    goal: str, venv: Path, env: dict[str, str], *extra: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["make", goal, f"VENV={venv}", *extra],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=90,
    )


def test_spaced_and_quoted_venv_paths_stay_one_directory(tmp_path: Path) -> None:
    env = _real_env()
    for name in ("my env", "my'env", 'my"env'):
        target = tmp_path / name
        result = _make("venv", target, env)
        output = _output(result)
        assert result.returncode == 0, output
        assert (target / "pyvenv.cfg").is_file()
        assert not (target / ".install.stamp").exists()
        assert not (target / ".install-dev.stamp").exists()
        assert "pip install" not in output
        assert ".[dev]" not in output
        assert "overriding recipe" not in output
        cfg = (target / "pyvenv.cfg").read_bytes()
        quoted = subprocess.run(
            ["make", "venv"],
            cwd=REPO,
            env={**env, "VENV": str(target)},
            capture_output=True,
            text=True,
            check=False,
            timeout=90,
        )
        assert quoted.returncode == 0, _output(quoted)
        assert (target / "pyvenv.cfg").read_bytes() == cfg


def test_install_stamp_retries_until_pip_succeeds(tmp_path: Path) -> None:
    venv = tmp_path / "venv"
    created = subprocess.run(
        [sys.executable, "-m", "venv", str(venv)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert created.returncode == 0, created.stderr
    log = tmp_path / "pip.log"
    _patch_pip_main(venv, log, 0)
    env = _real_env()

    first = _make("install", venv, env)
    assert first.returncode == 0, _output(first)
    recorded = log.read_text(encoding="utf-8")
    assert "-e ." in recorded
    assert ".[dev]" not in recorded
    assert (venv / ".install.stamp").is_file()
    assert not (venv / ".install-dev.stamp").exists()

    again = _make("install", venv, env)
    assert again.returncode == 0, _output(again)
    assert log.read_text(encoding="utf-8") == recorded

    dev = _make("install-dev", venv, env)
    assert dev.returncode == 0, _output(dev)
    dev_log = log.read_text(encoding="utf-8")
    assert ".[dev]" in dev_log
    assert (venv / ".install-dev.stamp").is_file()
    skipped = _make("install-dev", venv, env)
    assert skipped.returncode == 0, _output(skipped)
    assert log.read_text(encoding="utf-8") == dev_log

    os.utime(venv / ".install.stamp", (1, 1))
    _patch_pip_main(venv, log, 9)
    failed = _make("install", venv, env)
    assert failed.returncode != 0, _output(failed)
    assert (venv / ".install.stamp").stat().st_mtime == 1
    retry = log.read_text(encoding="utf-8")
    assert retry != dev_log
    held = retry
    _patch_pip_main(venv, log, 0)
    recovered = _make("install", venv, env)
    assert recovered.returncode == 0, _output(recovered)
    assert (venv / ".install.stamp").stat().st_mtime != 1
    assert log.read_text(encoding="utf-8") != held
    final = log.read_text(encoding="utf-8")
    quiet = _make("install", venv, env)
    assert quiet.returncode == 0, _output(quiet)
    assert log.read_text(encoding="utf-8") == final


def test_directory_pointing_at_system_python_does_not_install(tmp_path: Path) -> None:
    target = tmp_path / "not-a-venv"
    log = tmp_path / "python.log"
    bindir = target / "bin"
    bindir.mkdir(parents=True)
    real = Path(sys.executable).resolve()
    launcher = bindir / "python"
    launcher.write_text(
        "#!/bin/bash\n"
        f"printf '%s\\n' \"$*\" >> {shlex_quote(log)}\n"
        f'exec {shlex_quote(real)} "$@"\n',
        encoding="utf-8",
    )
    launcher.chmod(0o755)
    (target / "KEEP").write_text("keep", encoding="utf-8")
    env = _real_env()
    env["PIP_REQUIRE_VIRTUALENV"] = "true"
    result = _make("install", target, env)
    output = _output(result)

    assert result.returncode == 2, output
    assert (target / "KEEP").read_text(encoding="utf-8") == "keep"
    assert not (target / ".install.stamp").exists()
    assert "not a virtual environment" in output
    assert "write outside this directory" in output
    assert "left unchanged and was not deleted" in output
    assert "Keep it where it is" in output
    assert "No packages were installed." in output
    assert "pip" not in _log(log)
    assert "Successfully installed" not in output

    linked = tmp_path / "linked"
    (linked / "bin").mkdir(parents=True)
    (linked / "bin" / "python").symlink_to(real)
    (linked / "pyvenv.cfg").write_text(
        "home = /usr/bin\ninclude-system-site-packages = true\nversion = 3.12.3\n",
        encoding="utf-8",
    )
    (linked / "KEEP").write_text("keep", encoding="utf-8")
    linked_result = _make("install", linked, env)
    linked_output = _output(linked_result)
    assert linked_result.returncode == 2, linked_output
    assert (linked / "KEEP").read_text(encoding="utf-8") == "keep"
    assert not (linked / ".install.stamp").exists()
    assert "write outside this directory" in linked_output
    assert "No packages were installed." in linked_output
    assert "Successfully installed" not in linked_output


def test_interrupted_ensurepip_is_not_qualified(tmp_path: Path) -> None:
    venv = tmp_path / "half"
    created = subprocess.run(
        [sys.executable, "-m", "venv", str(venv)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert created.returncode == 0, created.stderr
    _remove_pip(venv)
    (venv / "KEEP").write_text("keep", encoding="utf-8")
    result = _make("install", venv, _real_env())
    output = _output(result)

    assert result.returncode == 2, output
    assert (venv / "KEEP").read_text(encoding="utf-8") == "keep"
    assert (venv / "pyvenv.cfg").is_file()
    assert (venv / "bin" / "python").exists()
    assert not (venv / ".install.stamp").exists()
    assert "pip is missing" in output
    assert "interrupted ensurepip" in output
    assert "left unchanged and was not deleted" in output
    assert "Keep it where it is" in output
    assert "ensurepip --upgrade" in output
    assert "No packages were installed." in output
    assert "No module named pip" not in output


def test_start_and_make_use_custom_venv_python(tmp_path: Path) -> None:
    checkout = _mini_checkout(tmp_path)
    app = checkout / "app"
    ui = app / "ui"
    ui.mkdir()
    (ui / "__init__.py").write_text("", encoding="utf-8")
    (ui / "server.py").write_text(
        "import pathlib, sys\n"
        "pathlib.Path(sys.argv[1]).write_text(sys.executable, encoding='utf-8')\n",
        encoding="utf-8",
    )
    src = app / "src"
    src.mkdir()
    (src / "__init__.py").write_text("", encoding="utf-8")
    (src / "main.py").write_text(
        "import pathlib, sys\n"
        "pathlib.Path(sys.argv[1]).write_text(sys.executable, encoding='utf-8')\n",
        encoding="utf-8",
    )
    custom = tmp_path / "custom env"
    created = subprocess.run(
        [sys.executable, "-m", "venv", str(custom)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert created.returncode == 0, created.stderr
    stamp_time = (app / "pyproject.toml").stat().st_mtime + 10
    for name in (".install.stamp", ".install-dev.stamp"):
        stamp = custom / name
        stamp.write_text("ready", encoding="utf-8")
        os.utime(stamp, (stamp_time, stamp_time))
    env = _real_env()
    env["VENV"] = str(custom)
    marker = tmp_path / "start-python"
    started = _start(checkout, env, [str(marker)])
    assert started.returncode == 0, _output(started)
    python = Path(marker.read_text(encoding="utf-8")).resolve()
    assert python == (custom / "bin" / "python").resolve()
    assert not (app / ".venv").exists()
    assert "pip install" not in _output(started)

    ran_marker = tmp_path / "make-python"
    ran = subprocess.run(
        ["make", "run", f"ARGS={ran_marker}"],
        cwd=app,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=90,
    )
    assert ran.returncode == 0, _output(ran)
    assert Path(ran_marker.read_text(encoding="utf-8")).resolve() == python
    assert not (app / ".venv").exists()
