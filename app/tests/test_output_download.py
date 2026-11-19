"""Outputs download follows a recovery block and does not save an empty file."""

from __future__ import annotations

import os
import threading
from pathlib import Path

import pytest

pytest.importorskip("playwright")
from playwright.sync_api import expect, sync_playwright

from ui import server as web


def _launch(playwright):
    name = os.environ.get("ARA_BROWSER", "chromium")
    browser_type = getattr(playwright, name)
    options = {"headless": True}
    if name == "chromium":
        options["args"] = ["--no-sandbox"]
    try:
        return browser_type.launch(**options)
    except Exception:
        if name != "chromium":
            raise
        return browser_type.launch(channel="chrome", headless=True, args=["--no-sandbox"])


def test_download_disables_after_recovery_blocks_output(tmp_path: Path):
    project = tmp_path / "example"
    project.mkdir()
    (project / "task.md").write_text("Synthetic task\n")
    (project / "memory.md").write_text("")
    (project / "best_output.md").write_text("Synthetic.\n")
    (tmp_path / "config.yaml").write_text(web.h.CONFIG_EXAMPLE_PATH.read_text())
    previous_root = web.h.ROOT
    previous_config = web.h.CONFIG_PATH
    web.h.ROOT = tmp_path
    web.h.CONFIG_PATH = tmp_path / "config.yaml"
    server = web.ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as playwright:
            browser = _launch(playwright)
            page = browser.new_page()
            page.add_init_script("localStorage.setItem('ara-language','en')")
            page.goto(f"http://127.0.0.1:{port}/#outputs", wait_until="networkidle")
            expect(page.locator("#document")).to_contain_text("Synthetic.")
            expect(page.locator('[data-action="download"]')).to_be_enabled()
            (project / ".round_commit_transaction.json").write_text("{not a journal")
            page.locator(".file-row").first.click()
            expect(page.locator("#document")).to_contain_text("Round commit recovery is blocked.")
            expect(page.locator('[data-action="download"]')).to_be_disabled()
            page.evaluate(
                """() => {
                  const orig = URL.createObjectURL;
                  window.__blobSizes = [];
                  URL.createObjectURL = (blob) => {
                    window.__blobSizes.push(blob.size);
                    return orig.call(URL, blob);
                  };
                  document.querySelector('[data-action="download"]').disabled = false;
                }"""
            )
            page.locator('[data-action="download"]').click()
            expect(page.locator('[data-action="download"]')).to_be_disabled()
            expect(page.locator("#document")).to_contain_text("Round commit recovery is blocked.")
            assert page.evaluate("() => window.__blobSizes") == []
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        web.h.ROOT = previous_root
        web.h.CONFIG_PATH = previous_config
