from __future__ import annotations

from unittest.mock import patch

from src.llm import OllamaClient
from src.run_config import build_initial_run_config
from src.run_environment import collect_run_environment


def test_environment_has_versions_without_host_paths_or_secrets(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "private-key-do-not-record")
    result = collect_run_environment()
    assert result["application_version"]
    assert result["python_version"]
    assert set(result["dependencies"]) == {
        "google-genai",
        "requests",
        "PyYAML",
        "rich",
        "streamlit",
    }
    assert result["constraints_sha256"] and len(result["constraints_sha256"]) == 64
    assert "private-key" not in str(result)
    assert "hostname" not in result["platform"]
    assert result["ollama_digest_status"] == "not_applicable"


def test_digest_uses_configured_endpoint_and_no_generation():
    client = OllamaClient(base_url="http://user:secret@127.0.0.1:1234", model="fixture")
    with (
        patch(
            "src.run_environment.query_ollama_api_models",
            return_value=([{"name": "fixture:latest", "id": "a" * 64}], None),
        ) as query,
        patch.object(client, "generate") as generate,
    ):
        result = collect_run_environment(client)
    query.assert_called_once_with(base_url=client.base_url, timeout_seconds=2)
    generate.assert_not_called()
    assert result["ollama_model_digest"] == "a" * 64
    assert "secret" not in str(result)
    assert "1234" not in str(result)


def test_unavailable_or_untrusted_digest_is_explicit_and_nonfatal():
    client = OllamaClient(base_url="http://127.0.0.1:9", model="fixture")
    for response in [
        ([], "secret endpoint failure"),
        ([{"name": "fixture", "id": "unsafe text"}], None),
    ]:
        with patch("src.run_environment.query_ollama_api_models", return_value=response):
            result = collect_run_environment(client)
        assert result["ollama_digest_status"] == "unavailable"
        assert result["ollama_model_digest"] is None
        assert "secret" not in str(result)


def test_resume_preserves_initial_environment_and_records_current_session(tmp_path):
    common = dict(run_id="run", run_root=tmp_path, mode="normal", model_name="fake")
    with patch("src.run_config.collect_run_environment", return_value={"python_version": "old"}):
        original = build_initial_run_config(**common)
    with patch("src.run_config.collect_run_environment", return_value={"python_version": "new"}):
        resumed = build_initial_run_config(
            **common,
            existing_run_config=original,
            resume_metadata={"lifecycle_action": "resume_existing_run"},
        )
    assert resumed["environment"]["python_version"] == "old"
    assert resumed["current_session_environment"]["python_version"] == "new"
    assert resumed["resume_sessions"][-1]["environment"]["python_version"] == "new"


def test_legacy_resume_marks_original_environment_unknown(tmp_path):
    common = dict(
        run_id="old",
        run_root=tmp_path,
        mode="resume",
        model_name="fake",
        resume_metadata={"lifecycle_action": "resume_existing_run"},
    )
    with patch(
        "src.run_config.collect_run_environment", return_value={"python_version": "current"}
    ):
        resumed = build_initial_run_config(
            **common, existing_run_config={"started_at": "historical"}
        )
        again = build_initial_run_config(**common, existing_run_config=resumed)
    assert resumed["environment"] is None
    assert again["environment"] is None
    assert again["current_session_environment"]["python_version"] == "current"
    assert again["started_at"] == "historical"
