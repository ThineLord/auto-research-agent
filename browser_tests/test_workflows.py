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
