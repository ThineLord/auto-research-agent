"""New local API coverage: isolated artifacts and mocked external execution."""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ui import server as web


@pytest.fixture
def project(tmp_path: Path, monkeypatch):
    projects = tmp_path / "projects"
    root = projects / "example"
    root.mkdir(parents=True)
    (root / "task.md").write_text("Research brief", encoding="utf-8")
    (root / "memory.md").write_text("Context", encoding="utf-8")
    config = tmp_path / "config.yaml"
    config.write_text(web.h.CONFIG_EXAMPLE_PATH.read_text(), encoding="utf-8")
    monkeypatch.setattr(web.h, "ROOT", tmp_path)
    monkeypatch.setattr(web.h, "CONFIG_PATH", config)
    monkeypatch.setattr(web.h, "get_active_process_meta", lambda _: {})
    monkeypatch.setattr(web.h, "query_ollama_models", lambda **_: ([{"name": "qwen3:8b"}], ""))
    launch = Mock(return_value=SimpleNamespace(pid=4321, error=None))
    monkeypatch.setattr(web.h, "start_background_process", launch)
    return root, launch


def payload(**changes):
    return {"project": "example", "provider": "ollama", "model": "qwen3:8b", **changes}


def save_payload(**changes):
    return payload(
        action="save",
        changes=changes,
        revisions=web.read_inputs(web.project("example"))["revisions"],
    )


def test_workspace_and_save_keep_unicode_and_memory(project):
    root, launch = project
    current = web.workspace("example")
    assert current["task"] == "Research brief"
    assert current["memory"] == "Context"
    assert current["resume"]["can_resume"] is False
    web.action(save_payload(task="研究目标 / Research", memory="背景"))
    assert (root / "task.md").read_text() == "研究目标 / Research"
    assert (root / "memory.md").read_text() == "背景"
    launch.assert_not_called()


def test_workspace_reuses_request_inputs_for_all_recommendations(project, monkeypatch):
    root, _ = project
    config, _ = web.h.load_ui_config()
    expected = {
        preset: web.cloud_pool(root, config, preset)["recommendation"]
        for preset in web.h.FREE_RUNNER_PRESETS
    }
    names = (
        "read_json_file",
        "load_discovery_artifact",
        "load_profile_artifact",
        "build_cached_candidate_pool",
    )
    spies = {name: Mock(wraps=getattr(web.h, name)) for name in names}
    for name, spy in spies.items():
        monkeypatch.setattr(web.h, name, spy)
    project_spy = Mock(wraps=web.project)
    monkeypatch.setattr(web, "project", project_spy)

    result = web.workspace("example")

    assert result["recommendations"] == expected
    project_spy.assert_called_once_with("example")
    checkpoint_reads = [
        call
        for call in spies["read_json_file"].call_args_list
        if call.args[0] == root / "checkpoint.json"
    ]
    assert len(checkpoint_reads) == 1
    for name in names[1:]:
        spies[name].assert_called_once()


def test_workspace_refreshes_artifacts_on_each_request(project, monkeypatch):
    root, _ = project
    discovery = Mock(wraps=web.h.load_discovery_artifact)
    monkeypatch.setattr(web.h, "load_discovery_artifact", discovery)
    first = web.workspace("example")
    web.action(save_payload(task="Updated brief", memory="Updated context"))
    second = web.workspace("example")

    assert first["task"] == "Research brief"
    assert second["task"] == "Updated brief"
    assert second["memory"] == "Updated context"
    assert discovery.call_count == 2
    assert all(call.args == (root,) for call in discovery.call_args_list)


@pytest.mark.parametrize("name", ["../example", "../../", "/tmp", "missing"])
def test_project_boundaries(project, name):
    with pytest.raises(ValueError):
        web.workspace(name)


def test_symlinked_input_is_not_written(project, tmp_path):
    root, _ = project
    outside = tmp_path / "outside.txt"
    outside.write_text("Keep me")
    (root / "task.md").unlink()
    (root / "task.md").symlink_to(outside)
    with pytest.raises(OSError):
        web.action(save_payload(task="Changed", memory="Changed"))
    assert outside.read_text() == "Keep me"
    assert (root / "memory.md").read_text() == "Context"


@pytest.mark.parametrize(
    "mode,flag", [("normal", None), ("continuous", "--continuous"), ("diagnostic", "--diagnostic")]
)
def test_run_dispatch_keeps_backend_options(project, mode, flag):
    _, launch = project
    result = web.action(
        payload(action="run", mode=mode, drafting_mode="fresh_from_task_with_review")
    )
    assert result["pid"] == 4321
    command = launch.call_args.kwargs["command"]
    assert command[command.index("--project") + 1] == "example"
    assert command[command.index("--drafting-mode") + 1] == "fresh_from_task_with_review"
    if flag:
        assert flag in command
    if mode == "continuous":
        assert "--benchmark-preset" in command
    else:
        assert "--benchmark-preset" not in command


def test_resume_checks_existing_safety_gate(project):
    _, launch = project
    with pytest.raises(ValueError, match="checkpoint"):
        web.action(payload(action="run", mode="resume"))
    launch.assert_not_called()


@pytest.mark.parametrize(
    "changes",
    [
        {"model": "--help"},
        {"model": "qwen;touch /tmp/bad"},
        {"provider": "invalid"},
        {"drafting_mode": "invalid"},
        {"benchmark_preset": "invalid"},
        {"max_provider_quota_failures": 21},
        {"mode": "invalid"},
    ],
)
def test_invalid_execution_options_are_rejected(project, changes):
    _, launch = project
    with pytest.raises(ValueError):
        web.action(payload(action="run", **changes))
    launch.assert_not_called()


def test_active_run_blocks_new_run_and_model_operations(project, monkeypatch):
    _, launch = project
    monkeypatch.setattr(web.h, "get_active_process_meta", lambda _: {"pid": 42})
    for operation in ("run", "pull", "delete", "tests"):
        with pytest.raises(ValueError):
            web.action(payload(action=operation, target="qwen3:8b"))
    launch.assert_not_called()


def test_model_deletion_needs_exact_confirmation(project):
    _, launch = project
    with pytest.raises(ValueError, match="confirmation"):
        web.action(payload(action="delete", target="qwen3:8b", confirmation="yes"))
    launch.assert_not_called()
    web.action(payload(action="delete", target="qwen3:8b", confirmation="qwen3:8b"))
    assert launch.call_args.kwargs["command"] == ["ollama", "rm", "qwen3:8b"]


def test_cloud_key_goes_only_to_child_environment(project, monkeypatch):
    root, launch = project
    monkeypatch.setattr(web, "cloud_pool", lambda *_: {"recommendation": None})
    web.action(
        payload(
            action="run",
            provider="gemini",
            model="gemini-2.5-flash",
            api_key="test-secret",
            free_runner_preset="manual",
        )
    )
    args = launch.call_args.kwargs
    assert "test-secret" not in " ".join(args["command"])
    assert args["env_overrides"][web.h.UI_GEMINI_API_KEY_ENV] == "test-secret"
    assert "test-secret" not in web.h.CONFIG_PATH.read_text()
    assert "api_key" not in web.config_public()
    assert "test-secret" not in json.dumps(args["extra"])
    assert (root / "task.md").read_text() == "Research brief"


def test_output_api_exposes_missing_key_and_keeps_readable_text(project):
    root, _ = project
    (root / "best_output.md").write_text("Synthetic.\n", encoding="utf-8")
    workspace = web.workspace("example")
    metrics = next(
        row for row in workspace["outputs"] if row["label_key"] == "output_round_metrics"
    )
    best = next(row for row in workspace["outputs"] if row["label_key"] == "output_best")
    assert metrics["exists"] is False
    assert metrics["missing_key"] == "missing_round_metrics"
    assert best["exists"] is True
    metrics_body = web.output("example", metrics["id"])
    best_body = web.output("example", best["id"])
    assert metrics_body == {
        "content": "",
        "exists": False,
        "missing_key": "missing_round_metrics",
    }
    assert best_body["exists"] is True
    assert best_body["content"] == "Synthetic.\n"
    assert "missing_key" in best_body

    (root / ".round_commit_transaction.json").write_text("{not a journal", encoding="utf-8")
    (root / "best_output.md").write_text("Synthetic.\n", encoding="utf-8")
    blocked = web.workspace("example")
    blocked_best = next(row for row in blocked["outputs"] if row["label_key"] == "output_best")
    assert blocked_best["exists"] is False
    assert blocked_best["missing_key"] == "round_commit_recovery_conflict"
    blocked_body = web.output("example", blocked_best["id"])
    assert blocked_body["exists"] is False
    assert blocked_body["content"] == ""
    assert blocked_body["missing_key"] == "round_commit_recovery_conflict"
    assert "Synthetic." not in blocked_body["content"]


def test_output_catalog_controls_read_access(project, tmp_path):
    root, _ = project
    (root / "best_output.md").write_text("# Output\n\nResult")
    assert web.output("example", 0)["content"].startswith("# Output")
    with pytest.raises(ValueError):
        web.output("example", -1)
    outside = tmp_path / "private.txt"
    outside.write_text("Do not expose")
    (root / "best_output.md").unlink()
    (root / "best_output.md").symlink_to(outside)
    with pytest.raises(OSError):
        web.output("example", 0)


@pytest.fixture
def http_server(project):
    server = web.ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_address[1]
    server.shutdown()
    server.server_close()
    thread.join()


def request(port, method, path, body=None, headers=None, timeout=5):
    connection = HTTPConnection("127.0.0.1", port, timeout=timeout)
    connection.request(method, path, body, headers or {})
    response = connection.getresponse()
    result = response.status, response.read(), dict(response.getheaders())
    connection.close()
    return result


def test_http_origin_token_and_asset_routes(http_server, project):
    port = http_server
    status, body, headers = request(port, "GET", "/")
    assert status == 200 and b"Auto research agent" in body
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    status, body, _ = request(port, "GET", "/api/bootstrap")
    bootstrap = json.loads(body)
    assert status == 200 and bootstrap["token"]
    assert "api_key" not in bootstrap["config"]
    for route in (
        "/app.js",
        "/theme.js",
        "/architecture.js",
        "/styles.css",
        "/vendor/marked.js",
        "/vendor/purify.js",
        "/api/workspace?project=example",
        "/api/status?project=example",
        "/api/analytics?project=example",
    ):
        assert request(port, "GET", route)[0] == 200
    assert request(port, "GET", "/config.yaml")[0] == 404
    assert request(port, "GET", "/api/bootstrap", headers={"Host": "evil.test"})[0] == 403
    body = json.dumps(save_payload(task="Updated", memory="Updated context"))
    assert request(port, "POST", "/api/action", body)[0] == 403
    token = {"X-Dashboard-Token": bootstrap["token"]}
    assert (
        request(port, "POST", "/api/action", body, {**token, "Origin": "https://evil.test"})[0]
        == 403
    )
    assert request(port, "POST", "/api/action", body, token)[0] == 200
    assert project[0].joinpath("task.md").read_text() == "Updated"


def test_http_conflict_returns_latest_inputs_without_writes(http_server, project):
    body = save_payload(task="Second editor", memory="Stale memory")
    (project[0] / "memory.md").write_text("New round evidence")
    status, response, _ = request(
        http_server, "POST", "/api/action", json.dumps(body), {"X-Dashboard-Token": web.TOKEN}
    )
    assert status == 409
    assert json.loads(response)["current"]["memory"] == "New round evidence"
    assert (project[0] / "task.md").read_text() == "Research brief"


def test_ui_started_metadata_stays_ahead_of_a_cli_lock(project, monkeypatch):
    from src.runtime import acquire_run_lock, get_active_process_meta, release_run_lock

    monkeypatch.setattr(web.h, "get_active_process_meta", get_active_process_meta)
    root, _launch = project
    (root / "ui_run_process.json").write_text(
        json.dumps({"pid": os.getpid(), "command": "ui-started", "kind": "run", "mode": "normal"}),
        encoding="utf-8",
    )
    handle, error = acquire_run_lock(root, mode="mock", model_name="mock-deterministic")
    assert error is None
    try:
        assert web.h.get_active_run_meta(root)["command"] == "ui-started"
        assert web.status("example")["progress"]["run_active"] is True
    finally:
        release_run_lock(handle)


def test_status_recognizes_a_live_cli_mock_and_isolates_projects(project, monkeypatch):
    from src.runtime import acquire_run_lock, get_active_process_meta, release_run_lock

    monkeypatch.setattr(web.h, "get_active_process_meta", get_active_process_meta)
    root, _launch = project
    other = root.parent / "beta"
    other.mkdir()
    (other / "task.md").write_text("Other synthetic project\n", encoding="utf-8")
    handle, error = acquire_run_lock(root, mode="mock", model_name="mock-deterministic")
    assert error is None
    try:
        current = web.status("example")
        assert current["progress"]["run_active"] is True
        assert current["progress"]["mode"] == "mock"
        assert current["progress"]["pid"] == os.getpid()
        assert web.status("beta")["progress"]["run_active"] is False
        stopped = web.action({"action": "stop", "project": "example"})
        assert stopped["message_key"] == "stop_signal_created"
        assert (root / "STOP_REQUESTED").is_file()
        assert not (other / "STOP_REQUESTED").exists()
    finally:
        release_run_lock(handle)
    assert web.status("example")["progress"]["run_active"] is False
    assert web.status("example")["progress"]["stage"] == "Idle"


def test_operation_lock_still_blocks_stop_and_start(http_server, project):
    root, launch = project
    assert web.ACTION_LOCK.acquire(blocking=False)
    try:
        token = {"X-Dashboard-Token": web.TOKEN}
        listed, body, _headers = request(
            http_server,
            "POST",
            "/api/action",
            json.dumps(payload(action="models")),
            token,
        )
        assert listed == 200
        assert json.loads(body)["models"]
        stopped, stop_body, _headers = request(
            http_server,
            "POST",
            "/api/action",
            json.dumps(payload(action="stop")),
            token,
        )
        started, _start_body, _headers = request(
            http_server,
            "POST",
            "/api/action",
            json.dumps(payload(action="run")),
            token,
        )
    finally:
        web.ACTION_LOCK.release()
    assert stopped == 409
    assert json.loads(stop_body)["error"] == "Another operation is in progress"
    assert not (root / "STOP_REQUESTED").exists()
    assert started == 409
    launch.assert_not_called()


def test_stop_verified_run_during_other_project_model_read(http_server, project, monkeypatch):
    """t1396u: another project's model list must not hold a verified cooperative stop."""
    from src.config import query_ollama_models
    from src.runtime import (
        get_active_process_meta,
        read_stoppable_cli_run,
        start_background_process,
    )

    root, _launch = project
    monkeypatch.setattr(web.h, "get_active_process_meta", get_active_process_meta)
    monkeypatch.setattr(web.h, "query_ollama_models", query_ollama_models)
    monkeypatch.setattr(web.h, "start_background_process", start_background_process)
    other = root.parent / "beta"
    other.mkdir()
    (other / "task.md").write_text("Other synthetic project\n", encoding="utf-8")
    (other / "memory.md").write_text("Context\n", encoding="utf-8")
    config_path = web.h.CONFIG_PATH
    config_text = config_path.read_text(encoding="utf-8")
    config_path.write_text(
        config_text.replace(
            "stop_if_no_improvement_rounds: 2",
            "stop_if_no_improvement_rounds: 100",
        ),
        encoding="utf-8",
    )
    entered = threading.Event()
    release = threading.Event()

    class SlowModels(BaseHTTPRequestHandler):
        def log_message(self, _format, *_args):
            pass

        def do_GET(self):
            entered.set()
            release.wait(timeout=8)
            body = json.dumps({"models": [{"name": "slow-local:latest"}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    fake = ThreadingHTTPServer(("127.0.0.1", 0), SlowModels)
    fake_thread = threading.Thread(target=fake.serve_forever, daemon=True)
    fake_thread.start()
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "http://localhost:11434", f"http://127.0.0.1:{fake.server_address[1]}"
        ),
        encoding="utf-8",
    )
    import src.runtime as runtime_module

    launched = []

    def tracking_popen(*args, **kwargs):
        process = original_popen(*args, **kwargs)
        launched.append(process)
        return process

    original_popen = runtime_module.subprocess.Popen
    monkeypatch.setattr(runtime_module.subprocess, "Popen", tracking_popen)
    child = start_background_process(
        command=[
            sys.executable,
            "-m",
            "src.main",
            "--mock",
            "--max-rounds",
            "40",
            "--workspace",
            str(web.h.ROOT),
            "--project",
            "example",
        ],
        cwd=web.h.APP_ROOT,
        log_path=root / "run.log",
        meta_path=web.h.run_meta_path(root),
        kind="run",
        extra={"mode": "mock", "model": "mock-deterministic", "provider": "mock"},
    )
    token = {"X-Dashboard-Token": web.TOKEN}
    models_result = {}
    lister = None
    verified = False

    def list_models():
        models_result["value"] = request(
            http_server,
            "POST",
            "/api/action",
            json.dumps(payload(action="models", project="beta")),
            token,
            timeout=15,
        )

    try:
        assert child.pid
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if read_stoppable_cli_run(root).get("mode") == "mock":
                break
            time.sleep(0.05)
        else:
            log_path = root / "run.log"
            log = log_path.read_text(encoding="utf-8") if log_path.is_file() else ""
            raise AssertionError(f"CLI mock did not become active\n{log}")
        assert web.status("example")["progress"]["run_active"] is True
        (root / "ui_run_process.json").unlink()
        assert web.status("example")["progress"]["run_active"] is True
        assert web.status("beta")["progress"]["run_active"] is False
        original = (root / "task.md").read_text(encoding="utf-8")
        revisions = web.read_inputs(root)["revisions"]
        lister = threading.Thread(target=list_models)
        lister.start()
        assert entered.wait(5)
        saved, saved_body, _headers = request(
            http_server,
            "POST",
            "/api/action",
            json.dumps(
                {
                    "action": "save",
                    "project": "example",
                    "changes": {"task": "Must not land"},
                    "revisions": revisions,
                }
            ),
            token,
        )
        started, started_body, _headers = request(
            http_server,
            "POST",
            "/api/action",
            json.dumps(payload(action="run", mode="normal")),
            token,
        )
        stopped, stopped_body, _headers = request(
            http_server,
            "POST",
            "/api/action",
            json.dumps(payload(action="stop")),
            token,
        )
        assert not release.is_set()
        assert saved == 409
        assert json.loads(saved_body)["code"] == "input_busy"
        assert (root / "task.md").read_text(encoding="utf-8") == original
        assert started == 400
        assert "active" in json.loads(started_body)["error"]
        assert stopped == 200
        assert json.loads(stopped_body)["message_key"] == "stop_signal_created"
        assert (root / "STOP_REQUESTED").is_file()
        assert not (other / "STOP_REQUESTED").exists()
        assert b"Another operation is in progress" not in stopped_body
        verified = True
    finally:
        release.set()
        if lister is not None:
            lister.join(timeout=15)
        fake.shutdown()
        fake.server_close()
        fake_thread.join(timeout=5)
        if not verified and launched and launched[0].poll() is None:
            launched[0].kill()
            launched[0].wait(timeout=5)
    process = launched[0]
    try:
        process.wait(timeout=20)
    except Exception:
        process.kill()
        process.wait(timeout=5)
        raise AssertionError((root / "run.log").read_text(encoding="utf-8")) from None
    assert process.returncode == 0
    checkpoint = json.loads((root / "checkpoint.json").read_text(encoding="utf-8"))
    assert checkpoint["stop_reason"] == "USER_STOP_REQUESTED"
    assert web.status("example")["progress"]["run_active"] is False
    assert web.status("example")["progress"]["stage"] == "Idle"
    assert web.status("beta")["progress"]["run_active"] is False
    assert models_result["value"][0] == 200
    assert json.loads(models_result["value"][1])["models"][0]["name"] == "slow-local:latest"
