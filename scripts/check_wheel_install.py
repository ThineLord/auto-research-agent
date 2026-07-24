#!/usr/bin/env python3
"""Build and exercise one source-excluded wheel in temporary directories."""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]

RESOURCE_PAIRS = {
    "config.example.yaml": "src/_bundled/config.example.yaml",
    "prompts/draft.md": "src/_bundled/prompts/draft.md",
    "prompts/review.md": "src/_bundled/prompts/review.md",
    "prompts/revise.md": "src/_bundled/prompts/revise.md",
    "prompts/judge.md": "src/_bundled/prompts/judge.md",
    "projects/example/task.md": "src/_bundled/projects/example/task.md",
}

_REQUIRED_SOURCE_FILES = {
    "README.md",
    "pyproject.toml",
    "src/__init__.py",
    *RESOURCE_PAIRS,
    *RESOURCE_PAIRS.values(),
}
_GIT_SOURCE_SPECS = [
    "README.md",
    "pyproject.toml",
    "src",
    *RESOURCE_PAIRS,
]
_BUILD_TIMEOUT_SECONDS = 300
_INSTALL_TIMEOUT_SECONDS = 600
_RUNTIME_TIMEOUT_SECONDS = 120
_OVERALL_TIMEOUT_SECONDS = 600
_PASSTHROUGH_NETWORK_ENV_NAMES = {
    "ALL_PROXY",
    "CURL_CA_BUNDLE",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "LANG",
    "LC_ALL",
    "NO_PROXY",
    "REQUESTS_CA_BUNDLE",
    "SSL_CERT_FILE",
    "all_proxy",
    "http_proxy",
    "https_proxy",
    "no_proxy",
}
_PASSTHROUGH_PLATFORM_ENV_NAMES = {
    "COMSPEC",
    "PATHEXT",
    "SYSTEMROOT",
    "WINDIR",
}


class WheelSmokeError(RuntimeError):
    """Raised when the isolated wheel contract is not satisfied."""


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _run(
    argv: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    timeout: int,
    label: str,
    deadline: float,
) -> subprocess.CompletedProcess[str]:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise WheelSmokeError("wheel install smoke exceeded its overall time limit")
    effective_timeout = min(float(timeout), remaining)
    try:
        result = subprocess.run(
            list(argv),
            cwd=cwd,
            env=dict(env),
            capture_output=True,
            text=True,
            check=False,
            timeout=effective_timeout,
        )
    except subprocess.TimeoutExpired:
        raise WheelSmokeError(f"{label} exceeded its bounded time limit") from None
    except (OSError, UnicodeError):
        raise WheelSmokeError(f"{label} could not be executed") from None
    if result.returncode != 0:
        raise WheelSmokeError(f"{label} failed with status {result.returncode}")
    return result


def _tracked_source_paths(*, home: Path, deadline: float) -> list[str]:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise WheelSmokeError("wheel install smoke exceeded its overall time limit")
    try:
        result = subprocess.run(
            [
                str(_git_executable()),
                "--no-optional-locks",
                "-c",
                "core.fsmonitor=false",
                "ls-files",
                "-z",
                "--",
                *_GIT_SOURCE_SPECS,
            ],
            cwd=REPO_ROOT,
            env=_isolated_git_environment(home),
            capture_output=True,
            check=False,
            timeout=min(30.0, remaining),
        )
    except subprocess.TimeoutExpired:
        raise WheelSmokeError("git packaging-input enumeration exceeded its time limit") from None
    except OSError:
        raise WheelSmokeError("git could not enumerate tracked packaging inputs") from None
    if result.returncode != 0:
        raise WheelSmokeError("git could not enumerate tracked packaging inputs")
    try:
        paths = [item.decode("utf-8") for item in result.stdout.split(b"\0") if item]
    except UnicodeDecodeError as exc:
        raise WheelSmokeError("tracked packaging input paths must be valid UTF-8") from exc
    if not paths:
        raise WheelSmokeError("git reported no tracked packaging inputs")
    if len(paths) != len(set(paths)):
        raise WheelSmokeError("git reported duplicate packaging input paths")
    missing = sorted(_REQUIRED_SOURCE_FILES.difference(paths))
    if missing:
        raise WheelSmokeError(
            f"required tracked packaging inputs are missing: {', '.join(missing)}"
        )
    for value in paths:
        relative = Path(value)
        if relative.is_absolute() or ".." in relative.parts:
            raise WheelSmokeError("git reported an unsafe packaging input path")
        if value not in {"README.md", "pyproject.toml", *RESOURCE_PAIRS} and not value.startswith(
            "src/"
        ):
            raise WheelSmokeError(f"unexpected packaging input path: {value}")
    return sorted(paths)


def _read_regular_tracked_file(relative_path: str) -> bytes:
    source = REPO_ROOT / relative_path
    current = REPO_ROOT
    for part in Path(relative_path).parts:
        current = current / part
        try:
            mode = current.lstat().st_mode
        except OSError as exc:
            raise WheelSmokeError(
                f"tracked packaging input is unavailable: {relative_path}"
            ) from exc
        if stat.S_ISLNK(mode):
            raise WheelSmokeError(
                f"tracked packaging input traverses a symbolic link: {relative_path}"
            )
    try:
        mode = source.lstat().st_mode
        if not stat.S_ISREG(mode):
            raise WheelSmokeError(f"tracked packaging input is not a regular file: {relative_path}")
        return source.read_bytes()
    except OSError as exc:
        raise WheelSmokeError(f"tracked packaging input cannot be read: {relative_path}") from exc


def _stage_source_snapshot(source_root: Path, *, deadline: float) -> None:
    for relative_path in _tracked_source_paths(
        home=source_root.parent / "source-git-home",
        deadline=deadline,
    ):
        destination = source_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(_read_regular_tracked_file(relative_path))


def _selected_environment(names: set[str]) -> dict[str, str]:
    return {name: os.environ[name] for name in names if name in os.environ}


def _isolated_git_environment(home: Path) -> dict[str, str]:
    home.mkdir(exist_ok=True)
    env = _selected_environment(_PASSTHROUGH_PLATFORM_ENV_NAMES | {"LANG", "LC_ALL"})
    env.update(
        {
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
            "HOME": str(home),
            "PATH": os.environ.get("PATH", ""),
            "USERPROFILE": str(home),
            "XDG_CONFIG_HOME": str(home / ".config"),
        }
    )
    return env


def _safe_temp_base() -> Path:
    repo_root = REPO_ROOT.resolve()
    for name in ("TMPDIR", "TEMP", "TMP"):
        raw_value = os.environ.get(name)
        if raw_value and _is_relative_to(Path(raw_value).resolve(), repo_root):
            raise WheelSmokeError("temporary directory configuration points inside the checkout")
    try:
        temp_base = Path(tempfile.gettempdir()).resolve()
    except OSError:
        raise WheelSmokeError("system temporary directory is unavailable") from None
    if _is_relative_to(temp_base, repo_root):
        raise WheelSmokeError("system temporary directory points inside the checkout")
    return temp_base


def _pip_environment(temp_root: Path) -> dict[str, str]:
    home = temp_root / "pip-home"
    process_tmp = temp_root / "process-tmp"
    home.mkdir()
    process_tmp.mkdir()
    env = _selected_environment(_PASSTHROUGH_NETWORK_ENV_NAMES | _PASSTHROUGH_PLATFORM_ENV_NAMES)
    env.update(
        {
            "HOME": str(home),
            "PATH": os.environ.get("PATH", ""),
            "PIP_CONFIG_FILE": os.devnull,
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            "PIP_NO_CACHE_DIR": "1",
            "PIP_NO_INPUT": "1",
            "PYTHONNOUSERSITE": "1",
            "PYTHONSAFEPATH": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "TEMP": str(process_tmp),
            "TMP": str(process_tmp),
            "TMPDIR": str(process_tmp),
            "USERPROFILE": str(home),
        }
    )
    return env


def _build_wheel(
    source_root: Path,
    wheel_root: Path,
    env: Mapping[str, str],
    deadline: float,
) -> Path:
    wheel_root.mkdir()
    _run(
        [
            sys.executable,
            "-m",
            "pip",
            "--isolated",
            "wheel",
            "--quiet",
            "--no-cache-dir",
            "--no-deps",
            "--wheel-dir",
            str(wheel_root),
            str(source_root),
        ],
        cwd=source_root.parent,
        env=env,
        timeout=_BUILD_TIMEOUT_SECONDS,
        label="wheel build",
        deadline=deadline,
    )
    wheels = sorted(wheel_root.glob("*.whl"))
    other_outputs = sorted(path.name for path in wheel_root.iterdir() if path not in wheels)
    if len(wheels) != 1 or other_outputs:
        raise WheelSmokeError(
            "wheel build must emit exactly one wheel and no other distribution artifacts"
        )
    return wheels[0]


def _expected_resource_bytes(source_root: Path) -> dict[str, bytes]:
    expected: dict[str, bytes] = {}
    for canonical, bundled in RESOURCE_PAIRS.items():
        canonical_bytes = (source_root / canonical).read_bytes()
        bundled_bytes = (source_root / bundled).read_bytes()
        if bundled_bytes != canonical_bytes:
            raise WheelSmokeError(
                f"bundled resource differs from its canonical source: {canonical}"
            )
        expected[bundled] = canonical_bytes
    return expected


def _record_rows(archive: zipfile.ZipFile) -> dict[str, tuple[str, str]]:
    record_names = [name for name in archive.namelist() if name.endswith(".dist-info/RECORD")]
    if len(record_names) != 1:
        raise WheelSmokeError("wheel must contain exactly one dist-info/RECORD")
    try:
        rows = list(csv.reader(io.StringIO(archive.read(record_names[0]).decode("utf-8"))))
    except (UnicodeDecodeError, csv.Error, KeyError) as exc:
        raise WheelSmokeError("wheel RECORD is unreadable") from exc
    records: dict[str, tuple[str, str]] = {}
    for row in rows:
        if len(row) != 3 or not row[0] or row[0] in records:
            raise WheelSmokeError("wheel RECORD contains an invalid or duplicate row")
        records[row[0]] = (row[1], row[2])
    return records


def _record_digest(data: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=")
    return f"sha256={digest.decode('ascii')}"


def _inspect_wheel(wheel_path: Path, expected_resources: Mapping[str, bytes]) -> None:
    try:
        with zipfile.ZipFile(wheel_path) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise WheelSmokeError("wheel contains duplicate archive member names")
            bundled_names = {
                name
                for name in names
                if name.startswith("src/_bundled/") and not name.endswith("/")
            }
            if bundled_names != set(expected_resources):
                raise WheelSmokeError(
                    "wheel bundled-resource inventory does not match the allowlist"
                )
            records = _record_rows(archive)
            for name, expected_bytes in expected_resources.items():
                actual_bytes = archive.read(name)
                if actual_bytes != expected_bytes:
                    raise WheelSmokeError(f"wheel resource bytes differ: {name}")
                if records.get(name) != (_record_digest(actual_bytes), str(len(actual_bytes))):
                    raise WheelSmokeError(f"wheel RECORD hash or size differs: {name}")
    except (OSError, zipfile.BadZipFile) as exc:
        raise WheelSmokeError("built wheel cannot be inspected") from exc


def _venv_python(venv_root: Path) -> Path:
    if os.name == "nt":
        return venv_root / "Scripts" / "python.exe"
    return venv_root / "bin" / "python"


def _create_and_install_venv(
    venv_root: Path,
    wheel_path: Path,
    env: Mapping[str, str],
    deadline: float,
) -> Path:
    _run(
        [sys.executable, "-m", "venv", str(venv_root)],
        cwd=venv_root.parent,
        env=env,
        timeout=120,
        label="fresh virtual environment creation",
        deadline=deadline,
    )
    python = _venv_python(venv_root)
    _run(
        [
            str(python),
            "-m",
            "pip",
            "--isolated",
            "install",
            "--quiet",
            "--no-cache-dir",
            "--no-compile",
            str(wheel_path),
        ],
        cwd=venv_root.parent,
        env=env,
        timeout=_INSTALL_TIMEOUT_SECONDS,
        label="wheel dependency installation",
        deadline=deadline,
    )
    return python


def _runtime_environment(venv_root: Path, home: Path) -> dict[str, str]:
    home.mkdir()
    env = _selected_environment(_PASSTHROUGH_PLATFORM_ENV_NAMES | {"LANG", "LC_ALL"})
    scripts_dir = venv_root / ("Scripts" if os.name == "nt" else "bin")
    inherited_path = os.environ.get("PATH", "")
    runtime_path = str(scripts_dir)
    if inherited_path:
        runtime_path = os.pathsep.join([runtime_path, inherited_path])
    env.update(
        {
            "ALL_PROXY": "http://127.0.0.1:9",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "HOME": str(home),
            "HTTP_PROXY": "http://127.0.0.1:9",
            "HTTPS_PROXY": "http://127.0.0.1:9",
            "NO_PROXY": "",
            "PATH": runtime_path,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "PYTHONSAFEPATH": "1",
            "USERPROFILE": str(home),
            "VIRTUAL_ENV": str(venv_root),
            "XDG_CACHE_HOME": str(home / ".cache"),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "XDG_DATA_HOME": str(home / ".local" / "share"),
            "all_proxy": "http://127.0.0.1:9",
            "http_proxy": "http://127.0.0.1:9",
            "https_proxy": "http://127.0.0.1:9",
            "no_proxy": "",
        }
    )
    return env


def _json_object(output: str, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(output)
    except json.JSONDecodeError as exc:
        raise WheelSmokeError(f"{label} did not emit valid JSON") from exc
    if not isinstance(value, dict):
        raise WheelSmokeError(f"{label} did not emit a JSON object")
    return value


def _probe_install(
    python: Path,
    workspace: Path,
    env: Mapping[str, str],
    deadline: float,
) -> dict[str, Any]:
    script = r"""
import importlib.metadata
import json
import sys
import sysconfig
from pathlib import Path

import src
import src.cli
from src.package_resources import resolve_runtime_layout

distribution = importlib.metadata.distribution("auto-research-agent")
direct_url_text = distribution.read_text("direct_url.json")
direct_url = json.loads(direct_url_text) if direct_url_text else {}
layout = resolve_runtime_layout(cli_file=Path(src.cli.__file__), cwd=Path.cwd())
print(json.dumps({
    "direct_url": direct_url,
    "git_root": str(layout.git_root) if layout.git_root is not None else None,
    "package_file": str(Path(src.__file__).resolve()),
    "purelib": str(Path(sysconfig.get_path("purelib")).resolve()),
    "resource_root": str(layout.resource_root.resolve()),
    "scripts": str(Path(sysconfig.get_path("scripts")).resolve()),
    "source_layout": layout.source_layout,
    "sys_path": sys.path,
    "workspace_root": str(layout.workspace_root.resolve()),
}, sort_keys=True))
"""
    result = _run(
        [str(python), "-I", "-c", script],
        cwd=workspace,
        env=env,
        timeout=_RUNTIME_TIMEOUT_SECONDS,
        label="installed-layout probe",
        deadline=deadline,
    )
    return _json_object(result.stdout, label="installed-layout probe")


def _validate_probe(
    probe: Mapping[str, Any],
    *,
    repo_root: Path,
    source_root: Path,
    venv_root: Path,
    workspace: Path,
) -> tuple[Path, Path]:
    repo_root = repo_root.resolve()
    source_root = source_root.resolve()
    venv_root = venv_root.resolve()
    try:
        package_file = Path(str(probe["package_file"])).resolve()
        purelib = Path(str(probe["purelib"])).resolve()
        scripts_dir = Path(str(probe["scripts"])).resolve()
        resource_root = Path(str(probe["resource_root"])).resolve()
        workspace_root = Path(str(probe["workspace_root"])).resolve()
        sys_path = probe["sys_path"]
        direct_url = probe["direct_url"]
    except (KeyError, TypeError) as exc:
        raise WheelSmokeError("installed-layout probe omitted required fields") from exc
    if not isinstance(sys_path, list) or not isinstance(direct_url, dict):
        raise WheelSmokeError("installed-layout probe returned invalid field types")
    if not _is_relative_to(package_file, purelib) or not _is_relative_to(package_file, venv_root):
        raise WheelSmokeError("src import did not originate from the fresh virtual environment")
    if _is_relative_to(package_file, repo_root) or _is_relative_to(package_file, source_root):
        raise WheelSmokeError("src import leaked from a source checkout")
    for raw_entry in sys_path:
        if not isinstance(raw_entry, str) or not raw_entry:
            continue
        entry = Path(raw_entry).resolve()
        if _is_relative_to(entry, repo_root) or _is_relative_to(entry, source_root):
            raise WheelSmokeError("fresh interpreter search path contains a source checkout")
    if probe.get("source_layout") is not False:
        raise WheelSmokeError("installed package was misclassified as a source layout")
    if probe.get("git_root") is not None:
        raise WheelSmokeError("installed layout retained source Git provenance")
    if workspace_root != workspace.resolve():
        raise WheelSmokeError("installed layout did not use the invocation workspace")
    if resource_root != purelib / "src" / "_bundled":
        raise WheelSmokeError("installed layout did not resolve its bundled resource root")
    dir_info = direct_url.get("dir_info")
    if isinstance(dir_info, dict) and dir_info.get("editable") is True:
        raise WheelSmokeError("wheel installation was unexpectedly editable")
    return purelib, scripts_dir


def _file_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _validate_installed_resources(
    package_root: Path,
    expected_resources: Mapping[str, bytes],
) -> None:
    bundle_root = package_root / "_bundled"
    actual_names = {
        f"src/_bundled/{path.relative_to(bundle_root).as_posix()}"
        for path in bundle_root.rglob("*")
        if path.is_file()
    }
    if actual_names != set(expected_resources):
        raise WheelSmokeError("installed bundled-resource inventory does not match the allowlist")
    for name, expected_bytes in expected_resources.items():
        relative = Path(name).relative_to("src")
        if (package_root / relative).read_bytes() != expected_bytes:
            raise WheelSmokeError(f"installed resource bytes differ: {name}")


def _console_script(scripts_dir: Path) -> Path:
    candidates = [scripts_dir / "auto-research-agent"]
    if os.name == "nt":
        candidates.insert(0, scripts_dir / "auto-research-agent.exe")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise WheelSmokeError("installed console entry point is missing")


def _assert_help(
    argv: Sequence[str],
    *,
    workspace: Path,
    env: Mapping[str, str],
    label: str,
    deadline: float,
) -> None:
    result = _run(
        argv,
        cwd=workspace,
        env=env,
        timeout=_RUNTIME_TIMEOUT_SECONDS,
        label=label,
        deadline=deadline,
    )
    help_text = result.stdout + result.stderr
    if "usage:" not in help_text.lower() or "--mock" not in help_text:
        raise WheelSmokeError("installed help output omitted the expected CLI contract")


def _git_executable() -> Path:
    executable = shutil.which("git", path=os.environ.get("PATH"))
    if executable is None:
        raise WheelSmokeError("git executable is unavailable for the provenance fixture")
    return Path(executable).resolve()


def _init_foreign_git(
    workspace: Path,
    env: Mapping[str, str],
    *,
    deadline: float,
) -> str:
    git = _git_executable()
    hooks = workspace.parent / "empty-git-hooks"
    hooks.mkdir(exist_ok=True)
    isolated_git = [
        str(git),
        "-c",
        f"core.hooksPath={hooks}",
        "-c",
        "commit.gpgSign=false",
    ]
    _run(
        [*isolated_git, "init", "--quiet"],
        cwd=workspace,
        env=env,
        timeout=30,
        label="foreign Git fixture initialization",
        deadline=deadline,
    )
    (workspace / "foreign.txt").write_text("foreign workspace\n", encoding="utf-8")
    _run(
        [*isolated_git, "add", "foreign.txt"],
        cwd=workspace,
        env=env,
        timeout=30,
        label="foreign Git fixture staging",
        deadline=deadline,
    )
    _run(
        [
            *isolated_git,
            "-c",
            "user.name=Wheel Smoke Fixture",
            "-c",
            "user.email=wheel-smoke@example.invalid",
            "commit",
            "--quiet",
            "--no-gpg-sign",
            "-m",
            "foreign fixture",
        ],
        cwd=workspace,
        env=env,
        timeout=30,
        label="foreign Git fixture commit",
        deadline=deadline,
    )
    return _run(
        [*isolated_git, "rev-parse", "HEAD"],
        cwd=workspace,
        env=env,
        timeout=30,
        label="foreign Git fixture revision probe",
        deadline=deadline,
    ).stdout.strip()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WheelSmokeError(f"mock artifact is unreadable: {path.name}") from exc
    if not isinstance(value, dict):
        raise WheelSmokeError(f"mock artifact is not an object: {path.name}")
    return value


def _validate_mock_artifacts(
    workspace: Path,
    expected_resources: Mapping[str, bytes],
    foreign_commit: str,
) -> None:
    if (workspace / "config.yaml").exists():
        raise WheelSmokeError("installed mock unexpectedly created config.yaml")
    project_root = workspace / "projects" / "example"
    expected_task = expected_resources["src/_bundled/projects/example/task.md"]
    if (project_root / "task.md").read_bytes() != expected_task:
        raise WheelSmokeError("installed mock did not seed the canonical example task")
    runs_root = project_root / "runs"
    run_roots = sorted(path for path in runs_root.iterdir() if path.is_dir())
    if len(run_roots) != 1:
        raise WheelSmokeError("installed mock must create exactly one run directory")
    run_root = run_roots[0]
    round_directories = sorted(
        path.name for path in run_root.iterdir() if path.is_dir() and path.name.startswith("round_")
    )
    if round_directories != ["round_01"]:
        raise WheelSmokeError("installed mock did not create exactly the round-1 directory")
    run_config = _load_json(run_root / "run_config.json")
    run_summary = _load_json(run_root / "run_summary.json")
    try:
        round_metrics = json.loads((run_root / "round_metrics.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WheelSmokeError("mock round_metrics.json is unreadable") from exc
    if run_config.get("mode") != "mock":
        raise WheelSmokeError("installed mock run config did not record mock mode")
    runtime = run_config.get("runtime")
    if not isinstance(runtime, dict) or runtime.get("max_rounds") != 1:
        raise WheelSmokeError("installed mock run config did not retain the one-round cap")
    model = run_config.get("model")
    if not isinstance(model, dict) or model.get("provider") != "mock":
        raise WheelSmokeError("installed mock run config did not record the mock provider")
    if model.get("provider_free") is not True or model.get("deterministic") is not True:
        raise WheelSmokeError("installed mock run config omitted provider-free determinism flags")
    git_metadata = run_config.get("git")
    if not isinstance(git_metadata, dict) or git_metadata.get("commit") is not None:
        raise WheelSmokeError("installed mock recorded unrelated workspace Git provenance")
    if git_metadata.get("commit") == foreign_commit:
        raise WheelSmokeError("installed mock captured the foreign workspace commit")
    prompt_files = run_config.get("prompt_files")
    if not isinstance(prompt_files, dict):
        raise WheelSmokeError("installed mock run config omitted prompt metadata")
    expected_prompt_hashes = {
        Path(name).name: hashlib.sha256(data).hexdigest()
        for name, data in expected_resources.items()
        if name.startswith("src/_bundled/prompts/")
    }
    actual_prompt_hashes = {
        name: metadata.get("sha256")
        for name, metadata in prompt_files.items()
        if isinstance(name, str) and isinstance(metadata, dict)
    }
    if actual_prompt_hashes != expected_prompt_hashes:
        raise WheelSmokeError("installed mock prompt hashes differ from bundled canonical bytes")
    if run_summary.get("mode") != "mock" or run_summary.get("completed_rounds") != 1:
        raise WheelSmokeError("installed mock summary did not complete exactly one round")
    if run_summary.get("best_score") != 73:
        raise WheelSmokeError("installed mock summary score is not the deterministic round-1 value")
    if (
        not isinstance(round_metrics, list)
        or len(round_metrics) != 1
        or not isinstance(round_metrics[0], dict)
    ):
        raise WheelSmokeError("installed mock must write exactly one round-metrics entry")
    if round_metrics[0].get("round") != 1 or round_metrics[0].get("score") != 73.0:
        raise WheelSmokeError("installed mock round metrics differ from the deterministic contract")


def _exercise_install(
    *,
    temp_root: Path,
    source_root: Path,
    venv_root: Path,
    python: Path,
    expected_resources: Mapping[str, bytes],
    deadline: float,
) -> None:
    help_workspace = temp_root / "help-workspace"
    mock_workspace = temp_root / "mock-workspace"
    home = temp_root / "home"
    help_workspace.mkdir()
    mock_workspace.mkdir()
    runtime_env = _runtime_environment(venv_root, home)

    probe = _probe_install(python, help_workspace, runtime_env, deadline)
    purelib, scripts_dir = _validate_probe(
        probe,
        repo_root=REPO_ROOT,
        source_root=source_root,
        venv_root=venv_root,
        workspace=help_workspace,
    )
    package_root = purelib / "src"
    _validate_installed_resources(package_root, expected_resources)
    console_script = _console_script(scripts_dir)

    _assert_help(
        [str(console_script), "--help"],
        workspace=help_workspace,
        env=runtime_env,
        label="installed console help",
        deadline=deadline,
    )
    _assert_help(
        [str(python), "-I", "-m", "src.main", "--help"],
        workspace=help_workspace,
        env=runtime_env,
        label="installed module help",
        deadline=deadline,
    )
    if list(help_workspace.iterdir()):
        raise WheelSmokeError("installed help commands unexpectedly wrote workspace files")

    foreign_commit = _init_foreign_git(mock_workspace, runtime_env, deadline=deadline)
    package_before = _file_hashes(package_root)
    _run(
        [str(console_script), "--mock", "--max-rounds", "1"],
        cwd=mock_workspace,
        env=runtime_env,
        timeout=_RUNTIME_TIMEOUT_SECONDS,
        label="installed one-round mock",
        deadline=deadline,
    )
    _validate_mock_artifacts(mock_workspace, expected_resources, foreign_commit)
    if _file_hashes(package_root) != package_before:
        raise WheelSmokeError("installed mock mutated the package directory")


def main() -> int:
    try:
        deadline = time.monotonic() + _OVERALL_TIMEOUT_SECONDS
        with tempfile.TemporaryDirectory(
            prefix="ara-wheel-smoke-",
            dir=_safe_temp_base(),
        ) as tmp:
            temp_root = Path(tmp)
            source_root = temp_root / "source"
            wheel_root = temp_root / "wheel"
            venv_root = temp_root / "venv"
            source_root.mkdir()
            _stage_source_snapshot(source_root, deadline=deadline)
            expected_resources = _expected_resource_bytes(source_root)
            pip_env = _pip_environment(temp_root)
            wheel_path = _build_wheel(source_root, wheel_root, pip_env, deadline)
            _inspect_wheel(wheel_path, expected_resources)
            python = _create_and_install_venv(venv_root, wheel_path, pip_env, deadline)
            _exercise_install(
                temp_root=temp_root,
                source_root=source_root,
                venv_root=venv_root,
                python=python,
                expected_resources=expected_resources,
                deadline=deadline,
            )
    except WheelSmokeError as exc:
        print(f"wheel install smoke failed: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("wheel install smoke interrupted", file=sys.stderr)
        return 130
    except Exception:
        print("wheel install smoke failed: unexpected internal error", file=sys.stderr)
        return 1

    print("wheel install smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
