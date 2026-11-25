"""An open dashboard must notice an external CLI run that finishes between polls."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from urllib.request import urlopen

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import expect

UNSAVED = "Unsaved task while an external run finishes"
EMPTY_SCORE = "—"


def offline_env():
    blocked = ("TOKEN", "SECRET", "API_KEY", "PYTHONPATH")
    return {
        key: value
        for key, value in os.environ.items()
        if not any(part in key.upper() for part in blocked)
    }


def run_mock(dashboard):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.main",
            "--mock",
            "--max-rounds",
            "1",
            "--project",
            "example",
        ],
        cwd=dashboard.source,
        env=offline_env(),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def api_json(dashboard, route):
    with urlopen(f"{dashboard.url}/api/{route}?project=example", timeout=10) as response:
        return json.load(response)


def install_frozen_clock(page):
    """Stop the dashboard poll until the test advances it, after any real timer is gone."""
    page.clock.install()
    page.reload()
    page.locator("#editor").wait_for()
    page.evaluate("() => new Promise((resolve) => queueMicrotask(resolve))")
    try:
        advance_poll(page)
    except PlaywrightTimeout:
        advance_poll(page)
    page.wait_for_load_state("networkidle")


def advance_poll(page, route="/api/status"):
    with page.expect_response(lambda response: route in response.url, timeout=15000):
        page.clock.run_for(5000)


def arm_counters(page):
    page.evaluate(
        """() => {
      window.stay = 1;
      window.outputReads = 0;
      window.workspaceReads = 0;
      window.analyticsReads = 0;
      const original = window.fetch;
      window.fetch = async (...args) => {
        const url = String(args[0]?.url || args[0]);
        if (url.includes("/api/output")) window.outputReads += 1;
        if (url.includes("/api/workspace")) window.workspaceReads += 1;
        if (url.includes("/api/analytics")) window.analyticsReads += 1;
        return original.apply(window, args);
      };
    }"""
    )


def reads(page):
    return page.evaluate("() => ({outputReads, workspaceReads, analyticsReads, stay})")


def test_dashboard_count_tracks_external_mock_run(dashboard):
    page = dashboard.page
    install_frozen_clock(page)
    page.locator("#editor").fill(UNSAVED)
    expect(page.locator("#output-count")).to_have_text("00")
    expect(page.locator("#score")).to_have_text(EMPTY_SCORE)
    arm_counters(page)
    run_mock(dashboard)
    payload = api_json(dashboard, "workspace")
    assert payload["progress"]["best_score"] == 73
    assert any(row["label_key"] == "output_best" and row["exists"] for row in payload["outputs"])
    expect(page.locator("#output-count")).to_have_text("00")
    expect(page.locator("#score")).to_have_text(EMPTY_SCORE)
    advance_poll(page, "/api/workspace")
    expect(page.locator("#score")).to_have_text("73")
    expect(page.locator("#output-count")).not_to_have_text("00")
    expect(page.locator("#editor")).to_have_value(UNSAVED)
    expect(page.locator("#save-state")).to_contain_text("Unsaved")
    after = reads(page)
    assert after["workspaceReads"] == 1
    assert after["outputReads"] == 0
    assert after["stay"] == 1
    advance_poll(page)
    page.wait_for_load_state("networkidle")
    assert reads(page) == after
    page.locator('[data-nav="outputs"]').first.click()
    expect(page.locator("#document")).to_contain_text("Mock Revised Output Round 1")
    expect(page.locator('[data-action="download"]')).to_be_enabled()
    page.locator('[data-nav="dashboard"]').click()
    expect(page.locator("#editor")).to_have_value(UNSAVED)
    expect(page.locator("#output-count")).not_to_have_text("00")


def test_open_outputs_observe_external_mock_run(dashboard):
    page = dashboard.page
    install_frozen_clock(page)
    page.locator("#editor").fill(UNSAVED)
    page.locator('[data-nav="outputs"]').first.click()
    download = page.locator('[data-action="download"]')
    document = page.locator("#document")
    expect(download).to_be_disabled()
    expect(document).to_contain_text("This output has not been generated yet.")
    arm_counters(page)
    run_mock(dashboard)
    payload = api_json(dashboard, "workspace")
    assert payload["progress"]["best_score"] == 73
    assert any(row["label_key"] == "output_best" and row["exists"] for row in payload["outputs"])
    expect(download).to_be_disabled()
    expect(document).to_contain_text("This output has not been generated yet.")
    advance_poll(page, "/api/workspace")
    expect(document).to_contain_text("Mock Revised Output Round 1")
    expect(download).to_be_enabled()
    seen = reads(page)
    assert seen["workspaceReads"] == 1
    assert seen["outputReads"] == 1
    assert seen["analyticsReads"] == 0
    page.locator('[data-action="raw"]').click()
    expect(page.locator("#document pre")).to_contain_text("Mock Revised Output Round 1")
    expect(page.locator('[data-action="raw"]')).to_have_text("Read")
    chosen = reads(page)
    assert chosen["outputReads"] == 2
    advance_poll(page)
    page.wait_for_load_state("networkidle")
    assert reads(page) == chosen
    expect(page.locator("#document pre")).to_contain_text("Mock Revised Output Round 1")
    expect(page.locator('[data-action="raw"]')).to_have_text("Read")
    page.locator('[data-nav="dashboard"]').click()
    expect(page.locator("#editor")).to_have_value(UNSAVED)
    expect(page.locator("#score")).to_have_text("73")
    expect(page.locator("#output-count")).not_to_have_text("00")
    page.locator('[data-nav="outputs"]').first.click()
    expect(page.locator("#document pre")).to_contain_text("Mock Revised Output Round 1")
    expect(download).to_be_enabled()
    assert reads(page)["stay"] == 1


def test_open_comparison_observes_second_external_run(dashboard):
    run_mock(dashboard)
    page = dashboard.page
    install_frozen_clock(page)
    page.locator('[data-nav="analytics"]').click()
    page.locator('[data-chart="comparison"]').click()
    boxes = page.locator(".comparison-picker input")
    expect(boxes).to_have_count(1)
    old_run = boxes.first.get_attribute("data-compare")
    boxes.first.uncheck()
    expect(boxes.first).not_to_be_checked()
    arm_counters(page)
    run_mock(dashboard)
    payload = api_json(dashboard, "analytics")
    assert len(payload["comparison"]) == 2
    expect(boxes).to_have_count(1)
    advance_poll(page, "/api/analytics")
    expect(boxes).to_have_count(2)
    expect(page.locator(f'[data-compare="{old_run}"]')).not_to_be_checked()
    after = reads(page)
    assert after["analyticsReads"] == 1
    assert after["outputReads"] == 0
    assert after["workspaceReads"] == 1
    assert after["stay"] == 1
    advance_poll(page)
    page.wait_for_load_state("networkidle")
    assert reads(page) == after
    expect(boxes).to_have_count(2)
    expect(page.locator(f'[data-compare="{old_run}"]')).not_to_be_checked()
