"""New local API coverage: isolated artifacts and mocked external execution."""

from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
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
    monkeypatch.setattr(web.h, "PROJECTS_DIR", projects)
    monkeypatch.setattr(web.h, "CONFIG_PATH", config)
    monkeypatch.setattr(web.h, "get_active_process_meta", lambda _: {})
    monkeypatch.setattr(web.h, "query_ollama_models", lambda **_: ([{"name": "qwen3:8b"}], ""))
    launch = Mock(return_value=SimpleNamespace(pid=4321, error=None))
    monkeypatch.setattr(web.h, "start_background_process", launch)
    return root, launch


def payload(**changes):
    return {"project": "example", "provider": "ollama", "model": "qwen3:8b", **changes}


def test_workspace_and_save_keep_unicode_and_memory(project):
    root, launch = project
    current = web.workspace("example")
    assert current["task"] == "Research brief"
    assert current["memory"] == "Context"
    assert current["resume"]["can_resume"] is False
    web.action(payload(action="save", task="研究目标 / Research", memory="背景"))
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
    web.action(payload(action="save", task="Updated brief", memory="Updated context"))
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
        web.action(payload(action="save", task="Changed", memory="Changed"))
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


def request(port, method, path, body=None, headers=None):
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
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
    body = json.dumps(payload(action="save", task="Updated", memory="Updated context"))
    assert request(port, "POST", "/api/action", body)[0] == 403
    token = {"X-Dashboard-Token": bootstrap["token"]}
    assert (
        request(port, "POST", "/api/action", body, {**token, "Origin": "https://evil.test"})[0]
        == 403
    )
    assert request(port, "POST", "/api/action", body, token)[0] == 200
    assert project[0].joinpath("task.md").read_text() == "Updated"
