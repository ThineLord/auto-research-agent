"""Workspace boundary and upgrade contracts; only synthetic temporary research."""

from __future__ import annotations

import hashlib
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
