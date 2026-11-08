from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import wait_until
from playwright.sync_api import expect


def button(page, action):
    return page.locator(f'[data-action="{action}"]')


def completed(page):
    expect(button(page, "run")).to_be_enabled(timeout=30000)
    expect(button(page, "stop")).to_be_disabled()


def test_task_only_save_and_two_editor_conflict(dashboard):
    d = dashboard
    other = d.context.new_page()
    other.goto(d.url)
    other.locator("#editor").wait_for()
    d.page.locator("#editor").fill("First editor task")
    (d.project / "memory.md").write_text("Background memory must survive")
    button(d.page, "save").click()
    expect(d.page.locator("#save-state")).to_contain_text("Saved")
    assert (d.project / "memory.md").read_text() == "Background memory must survive"
    other.locator("#editor").fill("Second editor draft")
    button(other, "save").click()
    expect(button(other, "replace-inputs")).to_be_visible()
    assert (d.project / "task.md").read_text() == "First editor task"
    evidence = Path("output/browser")
    evidence.mkdir(parents=True, exist_ok=True)
    other.screenshot(path=str(evidence / "conflict.png"), full_page=True)
    button(other, "replace-inputs").click()
    expect(other.locator("#save-state")).to_contain_text("Saved")
    assert (d.project / "task.md").read_text() == "Second editor draft"
    d.page.locator("#editor").fill("Another stale draft")
    button(d.page, "save").click()
    button(d.page, "latest-inputs").click()
    expect(d.page.locator("#editor")).to_have_value("Second editor draft")


@pytest.mark.parametrize("expanded", [False, True])
def test_completion_refresh_preserves_editor_revision(dashboard, expanded):
    d = dashboard
    button(d.page, "run").click()
    expect(button(d.page, "stop")).to_be_enabled(timeout=10000)
    d.page.locator('[data-editor="memory"]').click()
    if expanded:
        button(d.page, "editor").click()
        editor = d.page.locator("#large-editor")
        editor.focus()
        # The panel remains open while focus moves to Done: preserve its baseline too.
        button(d.page, "close").last.focus()
    else:
        editor = d.page.locator("#editor")
        editor.focus()
    completed(d.page)
    assert (d.project / "memory.md").read_text() != "Original memory"
    expect(editor).to_have_value("Original memory")
    editor.fill("Local memory after background completion")
    if expanded:
        button(d.page, "close").last.click()
    button(d.page, "save").click()
    expect(button(d.page, "latest-inputs")).to_be_visible()
    assert (d.project / "memory.md").read_text() != "Local memory after background completion"
    button(d.page, "latest-inputs").click()
    expect(d.page.locator("#editor")).to_have_value((d.project / "memory.md").read_text())


def test_run_stop_resume_outputs_and_appearance(dashboard):
    d = dashboard
    button(d.page, "run").click()
    expect(button(d.page, "stop")).to_be_enabled(timeout=10000)
    checkpoint = d.project / "checkpoint.json"
    wait_until(lambda: checkpoint.exists())
    button(d.page, "stop").click()
    completed(d.page)
    expect(button(d.page, "resume")).to_be_enabled(timeout=10000)
    button(d.page, "resume").click()
    expect(button(d.page, "stop")).to_be_enabled(timeout=10000)
    completed(d.page)
    checkpoint_data = json.loads(checkpoint.read_text())
    assert checkpoint_data["last_completed_round"] == 3
    environment = json.loads(Path(checkpoint_data["run_config"]).read_text())[
        "current_session_environment"
    ]
    assert environment["ollama_model_digest"] == "a" * 64
    assert environment["constraints_sha256"]
    assert environment["python_version"]
    assert d.calls and all(call["model"] == "fixture:latest" for call in d.calls)
    d.page.locator('[data-nav="outputs"]').first.click()
    expect(d.page.locator("#document")).to_contain_text("Synthetic")
    d.page.locator('[data-nav="analytics"]').click()
    expect(d.page.locator("#view")).to_contain_text("80")
    button(d.page, "language").click()
    d.page.reload()
    expect(d.page.locator('[data-nav="dashboard"]')).to_have_attribute("aria-label", "工作台")
    evidence = Path("output/browser")
    evidence.mkdir(parents=True, exist_ok=True)
    d.page.screenshot(path=str(evidence / "completed-workflow.png"), full_page=True)


def test_create_two_projects_switch_save_and_restart(dashboard):
    d = dashboard
    page = d.page
    for name, task in [("alpha", "Alpha isolated task"), ("beta", "Beta isolated task")]:
        page.locator('[data-action="new-project"]').click()
        page.locator("#new-project-name").fill(name)
        page.locator("#new-project-task").fill(task)
        page.locator('[data-action="create-project"]').click()
        expect(page.locator("#project")).to_have_value(name)
        expect(page.locator("#editor")).to_have_value(task + "\n")
        assert (d.workspace_root / name / "task.md").read_text() == task + "\n"
    page.locator("#project").select_option("alpha")
    expect(page.locator("#editor")).to_have_value("Alpha isolated task\n")
    page.locator("#editor").fill("Alpha edited and persisted")
    button(page, "save").click()
    expect(page.locator("#save-state")).to_contain_text("Saved")
    wait_until(
        lambda: (d.workspace_root / "alpha" / "task.md").read_text() == "Alpha edited and persisted"
    )
    assert (d.workspace_root / "beta" / "task.md").read_text() == "Beta isolated task\n"
    d.restart()
    page.reload()
    expect(page.locator("#project")).to_have_value("alpha")
    expect(page.locator("#editor")).to_have_value("Alpha edited and persisted")
    page.locator("#project").select_option("beta")
    expect(page.locator("#editor")).to_have_value("Beta isolated task\n")
    assert not d.calls


@pytest.mark.parametrize("dashboard", ["legacy"], indirect=True)
def test_v022_legacy_run_resumes_in_place(dashboard):
    """Create a genuine 0.2.2 run with the loopback fixture, resume with current code."""
    import os
    import subprocess
    import sys

    d = dashboard
    root = Path(__file__).resolve().parents[3]
    tag = "v0.2.2"
    probe = subprocess.run(["git", "rev-parse", "--verify", tag], cwd=root, capture_output=True)
    if probe.returncode:
        pytest.skip("Historical compatibility test requires fetched v0.2.2 tag")
    import shutil

    upgrade = d.workspace_root.parent / "git-upgrade"
    subprocess.run(
        ["git", "clone", "--quiet", "--shared", "--no-checkout", str(root), str(upgrade)],
        check=True,
    )
    subprocess.run(["git", "checkout", "--quiet", tag], cwd=upgrade, check=True)
    shutil.copy2(d.workspace_root / "config.yaml", upgrade / "config.yaml")
    d.workspace_root = upgrade
    d.project = upgrade / "projects" / "example"
    # The old source discovers projects/example in its original physical workspace.
    process = subprocess.Popen(
        [sys.executable, "-m", "src.main", "--project", "example", "--max-rounds", "3"],
        cwd=d.workspace_root,
        env={
            k: v
            for k, v in os.environ.items()
            if not any(part in k.upper() for part in ("TOKEN", "SECRET", "API_KEY", "PYTHONPATH"))
        },
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        wait_until(
            lambda: (
                (d.project / "checkpoint.json").exists()
                and json.loads((d.project / "checkpoint.json").read_text()).get(
                    "last_completed_round", 0
                )
                >= 1
            )
        )
        (d.project / "STOP_REQUESTED").write_text("historical compatibility test")
        stdout, stderr = process.communicate(timeout=30)
        assert process.returncode == 0, stdout + stderr
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
    checkpoint = json.loads((d.project / "checkpoint.json").read_text())
    run_root = Path(checkpoint["run_root"])
    prior = {p: p.read_bytes() for p in (run_root / "round_01").glob("*") if p.is_file()}
    assert prior
    preserved = {
        p: p.read_bytes()
        for p in d.project.rglob("*")
        if p.is_file()
        and p.name not in {"README.md", "memory.example.md", "literature_survey_sources.md"}
    }
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    subprocess.run(["git", "checkout", "--quiet", head], cwd=upgrade, check=True)
    assert all(p.is_file() and p.read_bytes() == value for p, value in preserved.items())
    d.restart(workspace=upgrade)
    d.page.reload()
    expect(button(d.page, "resume")).to_be_enabled(timeout=30000)
    button(d.page, "resume").click()
    wait_until(
        lambda: (
            json.loads((d.project / "checkpoint.json").read_text()).get("last_completed_round", 0)
            >= 2
        ),
        timeout=50,
    )
    completed(d.page)
    updated = json.loads((d.project / "checkpoint.json").read_text())
    assert updated["run_root"] == str(run_root)
    assert all(p.read_bytes() == value for p, value in prior.items())
    assert (d.workspace_root / "example" / "task.md").is_file()
    assert d.project == d.workspace_root / "projects" / "example"
