"""Real dashboard + CLI children in a disposable checkout; no real provider calls."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.request import urlopen

import pytest
import yaml
from playwright.sync_api import sync_playwright

from src.runtime import get_active_process_meta

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(params=[os.environ.get("ARA_BROWSER", "chromium")])
def browser(request):
    with sync_playwright() as playwright:
        instance = getattr(playwright, request.param).launch()
        yield instance
        instance.close()


def wait_until(predicate, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.1)
    raise AssertionError("Timed out waiting for dashboard workflow")


@pytest.fixture
def dashboard(tmp_path, browser, request):
    calls = []

    class Provider(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, payload):
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_HEAD(self):
            self.send_response(200)
            self.end_headers()

        def do_GET(self):
            self.reply(
                {
                    "version": "fixture",
                    "models": [{"name": "fixture:latest", "digest": "a" * 64, "size": 1}],
                }
            )

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append(payload)
            time.sleep(0.45)
            content = "Synthetic browser research output with an actionable evaluation plan."
            if isinstance(payload.get("format"), dict):
                content = json.dumps(
                    {
                        "score": 80,
                        "rubric": {
                            "novelty_and_research_value": 20,
                            "technical_clarity_and_correctness": 20,
                            "feasibility_and_implementation_realism": 16,
                            "evaluation_design_quality": 16,
                            "tomorrow_actionability": 8,
                        },
                        "reasons": ["Synthetic fixture"],
                        "blockers": [],
                        "next_step": "CONTINUE",
                    }
                )
            self.reply(
                {
                    "model": "fixture:latest",
                    "message": {"role": "assistant", "content": content},
                    "done": True,
                }
            )

    provider = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
    threading.Thread(target=provider.serve_forever, daemon=True).start()
    source = tmp_path / "source"
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    for name in filter(None, tracked):
        original = ROOT / name
        if original.is_file() and (
            name == "scripts/dependencies/constraints.txt"
            or name.split("/")[0]
            in {
                "src",
                "ui",
                "prompts",
                "projects",
                "pyproject.toml",
                "config.example.yaml",
            }
        ):
            target = source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, target)
    # Dashboard child commands locate this interpreter without installing into the copy.
    (source / ".venv").symlink_to(Path(sys.executable).parent.parent, target_is_directory=True)
    config = yaml.safe_load((source / "config.example.yaml").read_text())
    config.update(
        ollama_base_url=f"http://127.0.0.1:{provider.server_port}",
        max_rounds=3,
        stop_if_no_improvement_rounds=10,
    )
    config["model"].update(name="fixture:latest", timeout_seconds=10)
    (source / "config.yaml").write_text(yaml.safe_dump(config))
    project = source / "projects" / "example"
    (project / "task.md").write_text("Synthetic browser task")
    (project / "memory.md").write_text("Original memory")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    log = (tmp_path / "server.log").open("w")
    env = {
        key: value
        for key, value in os.environ.items()
        if not any(word in key.upper() for word in ("API_KEY", "TOKEN", "SECRET", "OLLAMA_HOST"))
    }
    process = subprocess.Popen(
        [sys.executable, "-m", "ui.server", "--port", str(port)],
        cwd=source,
        env=env,
        stdout=log,
        stderr=log,
    )

    def ready():
        try:
            with urlopen(url + "/api/bootstrap", timeout=1) as response:
                return response.status == 200
        except OSError:
            assert process.poll() is None, (tmp_path / "server.log").read_text()
            return False

    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    context.add_init_script(
        "if (!localStorage.getItem('ara-language')) localStorage.setItem('ara-language', 'en')"
    )
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        wait_until(ready)
        page.goto(url)
        page.locator("#editor").wait_for()
        yield SimpleNamespace(
            page=page, context=context, project=project, url=url, calls=calls, errors=errors
        )
        assert not errors
    finally:
        (project / "STOP_REQUESTED").write_text("browser fixture cleanup")
        evidence = ROOT / "output" / "browser"
        evidence.mkdir(parents=True, exist_ok=True)
        try:
            page.screenshot(path=str(evidence / f"{request.node.name}.png"), full_page=True)
        finally:
            try:
                wait_until(
                    lambda: not get_active_process_meta(project / "ui_run_process.json"), timeout=20
                )
            finally:
                context.close()
                process.terminate()
                process.wait(timeout=10)
                log.close()
                shutil.copy2(tmp_path / "server.log", evidence / f"{request.node.name}.log")
                provider.shutdown()
                provider.server_close()
