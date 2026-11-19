"""Workspace boundary and upgrade contracts; only synthetic temporary research."""

from __future__ import annotations

import hashlib
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from src.project_input import ProjectInputError, load_project_input
from src.workspace import (
    create_project,
    discover_projects,
    resolve_project_dir,
    select_project,
    selected_project,
)
from ui import server

APP = Path(__file__).resolve().parents[1]


def hashes(root):
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file()
    }


def cli(root, *args):
    return subprocess.run(
        [sys.executable, "-m", "src.main", "--workspace", str(root), *args],
        cwd=APP,
        capture_output=True,
        text=True,
        timeout=40,
    )


@pytest.mark.parametrize("legacy", [False, True])
def test_mock_workflow_and_selection_are_isolated(tmp_path, legacy):
    project = (tmp_path / "projects" if legacy else tmp_path) / "topic-a"
    project.mkdir(parents=True)
    (project / "task.md").write_text("Unique alpha research task")
    second = create_project(tmp_path, "topic-b", "Unique beta task")
    before = hashes(second)
    select_project(tmp_path, "topic-a")
    result = cli(tmp_path, "--mock", "--max-rounds", "1")
    assert result.returncode == 0, result.stdout + result.stderr
    assert hashes(second) == before
    assert (project / "checkpoint.json").is_file()
    assert (project / "memory.md").is_file()
    assert list((project / "runs").glob("*/round_01/01_draft.md"))
    assert selected_project(tmp_path, "example") == "topic-a"
    assert resolve_project_dir(tmp_path, "topic-a") == project
    assert not (tmp_path / "topic-a").exists() if legacy else not (tmp_path / "projects").exists()


def test_legacy_precedence_and_read_only_discovery(tmp_path):
    legacy = tmp_path / "projects" / "topic"
    legacy.mkdir(parents=True)
    (legacy / "task.md").write_text("Legacy task")
    flat = tmp_path / "topic"
    flat.mkdir()
    (flat / "task.md").write_text("Flat task must not substitute old data")
    before = hashes(tmp_path)
    assert discover_projects(tmp_path) == ["topic"]
    selected = load_project_input(root=tmp_path, project_name="topic", explicit_project=True)
    assert selected.project_dir == legacy
    assert selected.task_text == "Legacy task"
    assert hashes(tmp_path) == before
    with pytest.raises(FileExistsError):
        create_project(tmp_path, "topic", "overwrite")
    assert hashes(tmp_path) == before
    (legacy / "task.md").unlink()
    with pytest.raises(ProjectInputError):
        load_project_input(root=tmp_path, project_name="topic", explicit_project=True)


@pytest.mark.parametrize(
    "name",
    ["../escape", "a/b", r"a\b", ".git", "", "app", "projects", "src", "CON", " topic", "x:stream"],
)
def test_invalid_creation_never_writes(tmp_path, name):
    before = list(tmp_path.iterdir())
    with pytest.raises((ValueError, OSError)):
        create_project(tmp_path, name, "task")
    assert list(tmp_path.iterdir()) == before


@pytest.mark.parametrize("legacy", [False, True])
def test_links_and_conflicts_are_rejected(tmp_path, legacy):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "task.md").write_text("Private sentinel")
    parent = workspace / "projects" if legacy else workspace
    parent.mkdir(exist_ok=True)
    (parent / "linked").symlink_to(outside, target_is_directory=True)
    before = hashes(outside)
    assert "linked" not in discover_projects(workspace)
    with pytest.raises((ValueError, OSError)):
        resolve_project_dir(workspace, "linked")
    with pytest.raises(FileExistsError):
        create_project(workspace, "linked", "replacement")
    assert hashes(outside) == before


def test_api_first_start_create_switch_and_restart(tmp_path, monkeypatch):
    monkeypatch.setattr(server.h, "ROOT", tmp_path)
    monkeypatch.setattr(server.h, "CONFIG_PATH", tmp_path / "config.yaml")
    server.initialize_workspace()
    assert discover_projects(tmp_path) == ["example"]
    assert not (tmp_path / "projects").exists()
    for name in ["topic-a", "topic-b"]:
        server.action({"action": "create_project", "name": name, "task": f"Task {name}"})
    server.action({"action": "select_project", "project": "topic-a"})
    current = server.workspace("topic-a")
    server.action(
        {
            "action": "save",
            "project": "topic-a",
            "changes": {"task": "Edited alpha"},
            "revisions": current["revisions"],
        }
    )
    before = hashes(tmp_path)
    server.initialize_workspace()
    assert hashes(tmp_path) == before
    assert server.config_public()["project"] == "topic-a"
    assert server.workspace("topic-a")["task"] == "Edited alpha"
    assert server.workspace("topic-b")["task"].strip() == "Task topic-b"
    assert server.workspace("topic-a")["project_path"] == "topic-a"


def test_empty_create_project_rejects_startup_without_writes(tmp_path):
    project = tmp_path / "example"
    project.mkdir()
    (project / "task.md").write_text("synthetic task\n")
    before = hashes(tmp_path)
    result = cli(
        tmp_path,
        "--create-project",
        "",
        "--task",
        "Synthetic",
        "--mock",
        "--max-rounds",
        "1",
    )
    assert result.returncode == 2, result.stdout + result.stderr
    assert "Project creation error" in result.stdout
    assert "checkpoint.json" not in result.stdout
    assert hashes(tmp_path) == before
    assert not (project / "checkpoint.json").exists()


def test_create_project_does_not_change_persistent_selection(tmp_path):
    example = tmp_path / "example"
    example.mkdir()
    (example / "task.md").write_text("example task\n")
    created = cli(tmp_path, "--create-project", "demo", "--task", "Synthetic")
    assert created.returncode == 0, created.stdout + created.stderr
    assert not (tmp_path / ".ara-workspace.json").exists()
    result = cli(tmp_path, "--mock", "--max-rounds", "1")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "name=example" in result.stdout
    assert (example / "checkpoint.json").is_file()
    assert not (tmp_path / "demo" / "checkpoint.json").exists()


def test_interrupted_report_resume_command_locates_workspace(tmp_path):
    app_root = tmp_path / "app"
    (app_root / "src").mkdir(parents=True)
    (app_root / "pyproject.toml").write_text("[project]\nname='synthetic'\n")
    (app_root / "src" / "cli.py").write_text("# marker\n")
    (tmp_path / ".venv" / "bin").mkdir(parents=True)
    leftover = tmp_path / ".venv" / "bin" / "python"
    marker = tmp_path / "leftover-ran"
    leftover.write_text(f"#!/bin/sh\ntouch {shlex.quote(str(marker))}\necho LEFTOVER\nexit 42\n")
    leftover.chmod(0o755)
    (tmp_path / "config.yaml").write_text((APP / "config.example.yaml").read_text())
    name = "demo topic"
    result = cli(tmp_path, "--create-project", name, "--task", "Synthetic interrupt recovery")
    assert result.returncode == 0, result.stdout + result.stderr
    (tmp_path / name / "STOP_REQUESTED").write_text("")
    result = cli(tmp_path, "--project", name, "--mock", "--max-rounds", "1")
    assert result.returncode == 0, result.stdout + result.stderr
    report = (tmp_path / name / "interrupted_report.md").read_text()
    assert "- recovery:" in report
    assert "offline mock" in report
    assert "Do not use --resume" in report
    command = report.split("`", 2)[1]
    parsed = shlex.split(command)
    assert "--mock" in parsed
    assert "--resume" not in command
    assert (
        next(token for token in parsed if token.startswith("--project=")).split("=", 1)[1] == name
    )
    assert (
        Path(
            next(token for token in parsed if token.startswith("--workspace=")).split("=", 1)[1]
        ).resolve()
        == tmp_path.resolve()
    )
    assert Path(parsed[0]).name == "auto-research-agent"
    assert parsed[0] != str(leftover)
    assert ".venv/bin/python -m src.main" not in command
    other = tmp_path / "elsewhere"
    other.mkdir()
    restarted = subprocess.run(
        parsed,
        cwd=other,
        capture_output=True,
        text=True,
        timeout=40,
    )
    assert restarted.returncode == 0, restarted.stdout + restarted.stderr
    assert "Mock mode:" in restarted.stdout
    assert f"name={name}" in restarted.stdout
    assert "Failed to query Ollama" not in restarted.stdout
    assert not marker.exists()


def test_wheel_resume_command_locates_explicit_workspace(tmp_path):
    from src.runner import format_safe_resume_command

    name = "wheel topic"
    project = tmp_path / name
    project.mkdir()
    (project / "task.md").write_text("Synthetic task\n")
    (project / "checkpoint.json").write_text("{not json")
    (tmp_path / "config.yaml").write_text((APP / "config.example.yaml").read_text())
    command = format_safe_resume_command(
        project,
        tmp_path,
        explicit_workspace=tmp_path,
        provider="gemini",
        model="gemini:synthetic-original",
        max_rounds=1,
    )
    assert command is not None
    assert command.startswith("auto-research-agent ")
    assert ".venv" not in command
    assert "src.main" not in command
    assert "api_key" not in command
    parsed = shlex.split(command)
    assert (
        next(token for token in parsed if token.startswith("--project=")).split("=", 1)[1] == name
    )
    assert (
        Path(
            next(token for token in parsed if token.startswith("--workspace=")).split("=", 1)[1]
        ).resolve()
        == tmp_path.resolve()
    )
    assert "--provider=gemini" in parsed
    assert "--model=synthetic-original" in parsed
    assert "--max-rounds=1" in parsed
    env = os.environ.copy()
    env["PATH"] = str(APP / ".venv" / "bin") + os.pathsep + env.get("PATH", "")
    other = tmp_path / "elsewhere"
    other.mkdir()
    resumed = subprocess.run(
        parsed,
        cwd=other,
        env=env,
        capture_output=True,
        text=True,
        timeout=40,
    )
    assert resumed.returncode == 2, resumed.stdout + resumed.stderr
    assert f"name={name}" in resumed.stdout
    assert "checkpoint.json is corrupt" in resumed.stdout
    assert "Ollama" not in resumed.stdout


def test_resume_names_corrupt_or_unreadable_checkpoint(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text((APP / "config.example.yaml").read_text())
    project = tmp_path / "demo"
    project.mkdir()
    (project / "task.md").write_text("Synthetic task\n")
    (project / "checkpoint.json").write_text("{not json")
    result = cli(tmp_path, "--project", "demo", "--resume")
    assert result.returncode == 2, result.stdout + result.stderr
    assert "checkpoint.json is corrupt" in result.stdout
    assert "missing or empty" not in result.stdout
    assert "Ollama" not in result.stdout
    assert not (project / "runs").exists()

    if os.geteuid() == 0:
        return
    locked = project / "checkpoint.json"
    locked.write_text('{"can_resume": true}\n')
    locked.chmod(0)
    try:
        result = cli(tmp_path, "--project", "demo", "--resume")
    finally:
        locked.chmod(0o600)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "checkpoint.json is unreadable" in result.stdout
    assert "missing or empty" not in result.stdout
    assert not (project / "runs").exists()


def test_resume_command_names_wheel_script_without_a_checkout_venv(tmp_path):
    from src.runner import format_safe_resume_command

    project = tmp_path / "demo"
    project.mkdir()
    assert format_safe_resume_command(project, tmp_path) is None
    command = format_safe_resume_command(
        project,
        tmp_path,
        provider="ollama",
        model="qwen3:8b",
        max_rounds=5,
        source_layout=False,
    )
    assert command is not None
    assert command.startswith("auto-research-agent --resume ")
    assert "--project=demo" in command
    assert "--provider=ollama" in command
    assert "--model=qwen3:8b" in command
    assert "--max-rounds=5" in command
    assert f"--workspace={shlex.quote(str(tmp_path.resolve()))}" in command
    spaced = tmp_path / "o'reilly lab"
    spaced.mkdir()
    workspace = tmp_path / "nested ws"
    quoted = format_safe_resume_command(
        spaced,
        tmp_path,
        explicit_workspace=workspace,
        provider="gemini",
        model="synthetic-original",
        max_rounds=1,
    )
    assert quoted is not None
    parsed = shlex.split(quoted)
    from src.cli import parse_args

    namespace = parse_args(parsed[1:])
    assert namespace.project == "o'reilly lab"
    assert namespace.provider == "gemini"
    assert namespace.model == "synthetic-original"
    assert namespace.max_rounds == 1
    assert namespace.workspace.resolve() == workspace.resolve()
    (tmp_path / "pyproject.toml").write_text("[project]\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "cli.py").write_text("# marker\n")
    source_command = format_safe_resume_command(
        project,
        tmp_path,
        provider="ollama",
        model="qwen3:8b",
        max_rounds=5,
    )
    assert source_command is not None
    assert source_command.startswith(".venv/bin/python -m src.main --resume ")
    assert "--project=demo" in source_command
    assert "--workspace" not in source_command


def test_leading_dash_project_keeps_original_wheel_workspace(tmp_path):
    from src.cli import parse_args
    from src.runner import format_safe_resume_command

    rejected = cli(tmp_path, "--project", "-lab", "--mock", "--max-rounds", "1")
    assert rejected.returncode == 2, rejected.stdout + rejected.stderr
    assert "expected one argument" in rejected.stderr
    project = tmp_path / "-lab"
    project.mkdir()
    (project / "task.md").write_text("Dash task\n")
    (project / "checkpoint.json").write_text("{not json")
    (tmp_path / "config.yaml").write_text((APP / "config.example.yaml").read_text())
    command = format_safe_resume_command(
        project,
        tmp_path,
        source_layout=False,
        provider="gemini",
        model="synthetic-original",
        max_rounds=1,
    )
    assert command is not None
    assert "--project=-lab" in command
    parsed = shlex.split(command)
    namespace = parse_args(parsed[1:])
    assert namespace.project == "-lab"
    assert namespace.max_rounds == 1
    decoy = tmp_path / "decoy"
    (decoy / "-lab").mkdir(parents=True)
    ((decoy / "-lab") / "task.md").write_text("Decoy task\n")
    (decoy / "config.yaml").write_text((APP / "config.example.yaml").read_text())
    env = os.environ.copy()
    env["PATH"] = str(APP / ".venv" / "bin") + os.pathsep + env.get("PATH", "")
    resumed = subprocess.run(parsed, cwd=decoy, env=env, capture_output=True, text=True, timeout=40)
    assert resumed.returncode == 2, resumed.stdout + resumed.stderr
    assert "name=-lab" in resumed.stdout
    assert "title=Dash task" in resumed.stdout
    assert "Decoy" not in resumed.stdout
    assert "Ollama" not in resumed.stdout
    assert "checkpoint.json is corrupt" in resumed.stdout


def test_normal_interrupt_pins_provider_model_and_rounds(tmp_path):
    from rich.console import Console

    from src.mock_run import build_mock_agents
    from src.runner import run_iterative_rounds

    project = tmp_path / "demo"
    project.mkdir()
    (project / "memory.md").write_text("")
    (project / "task.md").write_text("Synthetic\n")

    def interrupt(**changes):
        (project / "STOP_REQUESTED").write_text("")
        settings = {
            "model_name": "gemini:synthetic-original",
            "model_provider": "gemini",
            "max_rounds": 1,
        }
        settings.update(changes)
        run_iterative_rounds(
            console=Console(quiet=True),
            agents=build_mock_agents(),
            task_text="Synthetic",
            project_dir=project,
            memory_path=project / "memory.md",
            mode="normal",
            stop_if_no_improvement_rounds=2,
            global_max_runtime_seconds=60,
            per_agent_timeout_seconds=1,
            repo_root=tmp_path,
            source_layout=False,
            **settings,
        )
        return (project / "interrupted_report.md").read_text()

    cloud = interrupt()
    assert "--provider=gemini" in cloud
    assert "--model=synthetic-original" in cloud
    assert "--max-rounds=1" in cloud
    assert "qwen3:8b" not in cloud
    assert "api_key" not in cloud
    local = interrupt(model_name="ollama:latest", model_provider="ollama", max_rounds=2)
    assert "--provider=ollama" in local
    assert "--model=ollama:latest" in local
    assert "--max-rounds=2" in local
    assert "--provider=gemini" not in local
    missing = interrupt(model_name="", model_provider="", max_rounds=1)
    assert "must be specified again" in missing
    assert "safe resume command" not in missing
    assert "`" not in missing


def test_cli_creation_and_git_privacy(tmp_path):
    result = cli(tmp_path, "--create-project", "topic-a", "--task", "Synthetic task")
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / "topic-a" / "task.md").read_text() == "Synthetic task\n"
    (tmp_path / ".gitignore").write_text((APP.parent / ".gitignore").read_text())
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    paths = [
        "topic-a/task.md",
        "topic-b/memory.md",
        "projects/old/checkpoint.json",
        "example/runs/private.json",
        "config.yaml",
        ".ara-workspace.json",
        "app/.venv/private",
        "app/config.yaml",
    ]
    result = subprocess.run(
        ["git", "check-ignore", "--stdin"],
        cwd=tmp_path,
        input="\n".join(paths),
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0
    assert result.stdout.splitlines() == paths
    public = ["app/src/workspace.py", "example/task.md", "README.md", "start"]
    result = subprocess.run(
        ["git", "check-ignore", "--stdin"],
        cwd=tmp_path,
        input="\n".join(public),
        text=True,
        capture_output=True,
    )
    assert result.returncode == 1 and not result.stdout


@pytest.mark.parametrize("name", [".research", "topic:2026", "a" * 120, "app", " topic "])
def test_old_project_names_remain_readable_but_not_creatable(tmp_path, name):
    legacy = tmp_path / "projects" / name
    legacy.mkdir(parents=True)
    (legacy / "task.md").write_text("Legacy research")
    before = hashes(legacy)
    assert name in discover_projects(tmp_path)
    assert resolve_project_dir(tmp_path, name) == legacy
    assert (
        load_project_input(root=tmp_path, project_name=name, explicit_project=True).task_text
        == "Legacy research"
    )
    select_project(tmp_path, name)
    assert selected_project(tmp_path, "example") == name
    from src.cli import _validate_project_override

    assert _validate_project_override(name) is None
    with pytest.raises((ValueError, FileExistsError)):
        create_project(tmp_path, name, "replacement")
    assert hashes(legacy) == before
    result = cli(tmp_path, "--mock", "--project", name, "--max-rounds", "1")
    assert result.returncode == 0, result.stdout + result.stderr
    assert (legacy / "checkpoint.json").is_file()


def test_unused_compatibility_stub_yields_only_when_old_data_absent(tmp_path):
    legacy = tmp_path / "projects" / "example"
    legacy.mkdir(parents=True)
    task = (APP / "src" / "_bundled" / "projects" / "example" / "task.md").read_text()
    (legacy / "task.md").write_text(task)
    flat = tmp_path / "example"
    flat.mkdir()
    (flat / "task.md").write_text("New example task")
    assert resolve_project_dir(tmp_path, "example") == flat
    assert discover_projects(tmp_path) == ["example"]
    (legacy / "memory.md").write_text("Old research memory")
    assert resolve_project_dir(tmp_path, "example") == legacy
    (legacy / "memory.md").unlink()
    (legacy / "task.md").write_text("A customized old task")
    assert resolve_project_dir(tmp_path, "example") == legacy
