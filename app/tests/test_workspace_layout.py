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
    command = report.split("- safe resume command: `", 1)[1].split("`", 1)[0]
    parsed = shlex.split(command)
    assert parsed[parsed.index("--project") + 1] == name
    assert Path(parsed[parsed.index("--workspace") + 1]).resolve() == tmp_path.resolve()
    assert Path(parsed[0]).name == "auto-research-agent"
    assert parsed[0] != str(leftover)
    assert ".venv/bin/python -m src.main" not in command
    assert not command.startswith("app/.venv/bin/")
    (tmp_path / name / "checkpoint.json").write_text("{not json")
    other = tmp_path / "elsewhere"
    other.mkdir()
    resumed = subprocess.run(
        parsed,
        cwd=other,
        capture_output=True,
        text=True,
        timeout=40,
    )
    assert resumed.returncode == 2, resumed.stdout + resumed.stderr
    assert f"name={name}" in resumed.stdout
    assert "checkpoint.json is corrupt" in resumed.stdout
    assert "Ollama" not in resumed.stdout
    assert not marker.exists()


def test_wheel_resume_command_locates_explicit_workspace(tmp_path):
    from src.runner import format_safe_resume_command

    name = "wheel topic"
    project = tmp_path / name
    project.mkdir()
    (project / "task.md").write_text("Synthetic task\n")
    (project / "checkpoint.json").write_text("{not json")
    (tmp_path / "config.yaml").write_text((APP / "config.example.yaml").read_text())
    command = format_safe_resume_command(project, tmp_path, explicit_workspace=tmp_path)
    assert command.startswith("auto-research-agent ")
    assert ".venv" not in command
    assert "src.main" not in command
    parsed = shlex.split(command)
    assert parsed[parsed.index("--project") + 1] == name
    assert Path(parsed[parsed.index("--workspace") + 1]).resolve() == tmp_path.resolve()
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
    assert (
        format_safe_resume_command(project, tmp_path)
        == "auto-research-agent --resume --project demo"
    )
    spaced = tmp_path / "demo topic"
    spaced.mkdir()
    workspace = tmp_path / "nested ws"
    quoted = format_safe_resume_command(spaced, tmp_path, explicit_workspace=workspace)
    assert quoted == (
        "auto-research-agent --resume --project 'demo topic' --workspace "
        + shlex.quote(str(workspace.resolve()))
    )
    (tmp_path / "pyproject.toml").write_text("[project]\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "cli.py").write_text("# marker\n")
    assert (
        format_safe_resume_command(project, tmp_path)
        == ".venv/bin/python -m src.main --resume --project demo"
    )


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
