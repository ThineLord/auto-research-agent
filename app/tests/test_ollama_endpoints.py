from __future__ import annotations

import io
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from rich.console import Console

from src.cli import _validate_model_provider_startup
from src.config import query_ollama_models
from src.llm import OllamaClient


@pytest.fixture
def endpoints():
    servers = []
    for name in ("server-a:latest", "server-b:latest"):
        calls = []

        def handler_factory(model, requests):
            class Handler(BaseHTTPRequestHandler):
                def log_message(self, *args):
                    pass

                def reply(self, value):
                    body = json.dumps(value).encode()
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)

                def do_GET(self):
                    requests.append(self.path)
                    self.reply({"models": [{"name": model, "digest": "0" * 64}]})

                def do_POST(self):
                    request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                    requests.append((self.path, request["model"]))
                    self.reply({"message": {"content": "Synthetic response"}})

            return Handler

        server = ThreadingHTTPServer(("127.0.0.1", 0), handler_factory(name, calls))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        servers.append((server, thread, name, calls))
    yield [(f"http://127.0.0.1:{s.server_port}", name, calls) for s, _, name, calls in servers]
    for server, thread, _, _ in servers:
        server.shutdown()
        server.server_close()
        thread.join()


def test_discovery_preflight_and_generation_use_same_endpoint(endpoints, monkeypatch):
    (url_a, _, calls_a), (url_b, model_b, calls_b) = endpoints
    monkeypatch.setenv("OLLAMA_HOST", url_a)
    with patch(
        "subprocess.run", return_value=SimpleNamespace(returncode=0, stdout="server-a")
    ) as cli:
        models, error = query_ollama_models(base_url=url_b)
        assert error is None and [m["name"] for m in models] == [model_b]
        _validate_model_provider_startup(
            args=SimpleNamespace(model=model_b),
            console=Console(file=io.StringIO()),
            provider="ollama",
            model_name=model_b,
            gemini_api_key_env="GEMINI_API_KEY",
            effective_gemini_api_key="",
            ollama_base_url=url_b,
        )
        result = OllamaClient(base_url=url_b, model=model_b).generate(
            system_prompt=None, user_prompt="Synthetic endpoint test"
        )
        assert result == "Synthetic response"
        cli.assert_not_called()
    assert calls_a == []
    assert calls_b == ["/api/tags", "/api/tags", ("/api/chat", model_b)]
