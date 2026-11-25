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


def hold_next_analytics(page, *, fail=False):
    """Hold the next analytics body so a newer same-project response can arrive first."""
    page.evaluate(
        """(fail) => {
      const original = Response.prototype.json;
      let seen = 0;
      Response.prototype.json = async function () {
        const value = await original.call(this);
        const path = new URL(this.url, location.origin).pathname;
        if (path !== "/api/analytics" || seen++ !== 0) return value;
        await new Promise((resolve) => {
          window.releaseStaleAnalytics = resolve;
          document.body.dataset.analyticsHold = "stale";
        });
        setTimeout(() => {
          document.body.dataset.analyticsHold = "settled";
        }, 0);
        if (fail) throw new Error("stale analytics failed");
        return value;
      };
    }""",
        fail,
    )


def release_stale_analytics(page):
    page.evaluate("window.releaseStaleAnalytics()")
    page.clock.run_for(1)
    expect(page.locator("body")).to_have_attribute("data-analytics-hold", "settled")


def settle_idle_polls(page, before):
    for _ in range(2):
        advance_poll(page)
        page.wait_for_load_state("networkidle")
        assert reads(page) == before


def set_checkpoint_score(dashboard, score):
    path = dashboard.project / "checkpoint.json"
    checkpoint = json.loads(path.read_text(encoding="utf-8"))
    checkpoint["best_score"] = score
    path.write_text(json.dumps(checkpoint), encoding="utf-8")


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


def test_older_analytics_success_cannot_shrink_newer_comparison(dashboard):
    page = dashboard.page
    install_frozen_clock(page)
    page.locator("#editor").fill(UNSAVED)
    page.locator('[data-nav="analytics"]').click()
    page.locator('[data-chart="comparison"]').click()
    boxes = page.locator(".comparison-picker input")
    expect(page.locator(".comparison-picker")).to_be_visible()
    expect(boxes).to_have_count(0)
    arm_counters(page)
    hold_next_analytics(page)
    run_mock(dashboard)
    assert len(api_json(dashboard, "analytics")["comparison"]) == 1
    expect(boxes).to_have_count(0)
    advance_poll(page, "/api/analytics")
    expect(page.locator("body")).to_have_attribute("data-analytics-hold", "stale")
    run_mock(dashboard)
    assert len(api_json(dashboard, "analytics")["comparison"]) == 2
    advance_poll(page, "/api/analytics")
    expect(boxes).to_have_count(2)
    arrived = reads(page)
    assert arrived["analyticsReads"] == 2
    assert arrived["workspaceReads"] == 2
    assert arrived["outputReads"] == 0
    assert arrived["stay"] == 1
    release_stale_analytics(page)
    expect(boxes).to_have_count(2)
    assert reads(page) == arrived
    settle_idle_polls(page, arrived)
    expect(boxes).to_have_count(2)
    page.locator('[data-nav="dashboard"]').click()
    expect(page.locator("#editor")).to_have_value(UNSAVED)
    expect(page.locator("#save-state")).to_contain_text("Unsaved")


def test_older_analytics_error_cannot_clear_newer_comparison(dashboard):
    run_mock(dashboard)
    page = dashboard.page
    install_frozen_clock(page)
    page.locator("#editor").fill(UNSAVED)
    page.locator('[data-nav="analytics"]').click()
    page.locator('[data-chart="comparison"]').click()
    boxes = page.locator(".comparison-picker input")
    expect(boxes).to_have_count(1)
    kept = boxes.first.get_attribute("data-compare")
    arm_counters(page)
    hold_next_analytics(page, fail=True)
    set_checkpoint_score(dashboard, 74)
    advance_poll(page, "/api/analytics")
    expect(page.locator("body")).to_have_attribute("data-analytics-hold", "stale")
    set_checkpoint_score(dashboard, 75)
    advance_poll(page, "/api/analytics")
    expect(boxes).to_have_count(1)
    expect(page.locator(f'[data-compare="{kept}"]')).to_be_visible()
    arrived = reads(page)
    assert arrived["analyticsReads"] == 2
    assert arrived["workspaceReads"] == 2
    assert arrived["outputReads"] == 0
    release_stale_analytics(page)
    expect(boxes).to_have_count(1)
    expect(page.locator(".empty-state")).to_have_count(0)
    notice = page.locator("#notice").get_attribute("class") or ""
    assert "visible" not in notice.split()
    assert reads(page) == arrived
    settle_idle_polls(page, arrived)
    expect(boxes).to_have_count(1)
    page.locator('[data-nav="dashboard"]').click()
    expect(page.locator("#editor")).to_have_value(UNSAVED)
    expect(page.locator("#save-state")).to_contain_text("Unsaved")
