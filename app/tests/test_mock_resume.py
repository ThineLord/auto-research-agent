"""Ordinary resume must not continue an offline mock into a real provider."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from rich.console import Console

import src.cli as cli_module
import src.runner as runner_module
from src.resume import OFFLINE_MOCK_BLOCKED_REASON, build_resume_preview, run_resume_mode
from src.round_commit_recovery import RUN_FINALIZE_JOURNAL_NAME, classify_run_finalize_recovery
from ui import app as ui_app
from ui import server as web

APP = Path(__file__).resolve().parents[1]
PROVIDER_ENV = ("GEMINI_API_KEY", "GOOGLE_API_KEY")


def hashes(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }


def clean_env() -> dict[str, str]:
    env = os.environ.copy()
    for name in PROVIDER_ENV:
        env.pop(name, None)
    return env


def cli(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "src.main", "--workspace", str(root), *args],
        cwd=APP,
        capture_output=True,
        text=True,
        timeout=40,
        env=clean_env(),
        check=False,
    )


def write_config(root: Path) -> None:
    (root / "config.yaml").write_text(
        (APP / "config.example.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )


def test_stopped_mock_stays_resumable_and_ordinary_resume_stays_offline(tmp_path, monkeypatch):
    write_config(tmp_path)
    created = cli(tmp_path, "--create-project", "demo", "--task", "Synthetic mock resume")
    assert created.returncode == 0, created.stdout + created.stderr
    project = tmp_path / "demo"
    (project / "STOP_REQUESTED").write_text("STOP_REQUESTED\n", encoding="utf-8")
    stopped = cli(tmp_path, "--project", "demo", "--mock", "--max-rounds", "1")
    assert stopped.returncode == 0, stopped.stdout + stopped.stderr
    assert "Mock mode:" in stopped.stdout
    assert "Failed to query Ollama" not in stopped.stdout

    checkpoint = json.loads((project / "checkpoint.json").read_text(encoding="utf-8"))
    assert checkpoint["mode"] == "mock"
    assert checkpoint["model"] == "mock-deterministic"
    assert checkpoint["can_resume"] is True
    run_root = Path(checkpoint["run_root"])
    run_config = json.loads((run_root / "run_config.json").read_text(encoding="utf-8"))
    assert run_config["mode"] == "mock"
    assert run_config["model"]["name"] == "mock-deterministic"
    assert (project / "interrupted_report.md").is_file()
    before = hashes(project)

    monkeypatch.setattr(ui_app, "ROOT", tmp_path)
    monkeypatch.setattr(ui_app, "CONFIG_PATH", tmp_path / "config.yaml")
    status = web.status("demo", "gemini:gemini-2.5-flash")
    assert status["progress"]["mode"] == "mock"
    assert status["progress"]["model"] == "mock-deterministic"
    assert status["progress"]["can_resume"] is True
    assert status["resume"]["can_resume"] is False
    assert status["resume"]["details"]["can_resume"] is True
    assert status["resume"]["message_key"] == "resume_offline_mock"
    assert "offline mock" in status["resume"]["message"]
    assert "Do not use --resume" in status["resume"]["message"]
    assert "--mock" in status["resume"]["message"]
    rows = {row["field_key"]: row["value"] for row in web.analytics("demo")["metadata"]}
    assert rows["run_meta_mode"] == "mock"
    assert rows["run_meta_model"] == "mock-deterministic"
    assert rows["run_meta_resume"] == "yes"

    monkeypatch.setattr(
        web.h,
        "start_background_process",
        lambda **kwargs: pytest.fail(f"started {kwargs}"),
    )
    with pytest.raises(ValueError, match="offline mock"):
        web.action(
            {
                "action": "run",
                "project": "demo",
                "provider": "gemini",
                "model": "gemini-2.5-flash",
                "mode": "resume",
                "api_key": "test-secret",
                "free_runner_preset": "manual",
            }
        )

    def refuse(argv: list[str]) -> None:
        monkeypatch.setattr(sys, "argv", argv)
        with (
            patch.object(cli_module, "create_llm_client") as create_client,
            patch.object(cli_module, "_validate_model_provider_startup") as precheck,
            patch.object(cli_module, "list_installed_ollama_models") as list_models,
            patch.object(cli_module, "run_resume_mode") as resume_mode,
            patch("src.resume.run_iterative_rounds") as run_rounds,
            pytest.raises(SystemExit) as raised,
        ):
            cli_module.main()
        assert raised.value.code == 2
        create_client.assert_not_called()
        precheck.assert_not_called()
        list_models.assert_not_called()
        resume_mode.assert_not_called()
        run_rounds.assert_not_called()
        assert str(run_root) not in "".join(
            str(call.kwargs.get("run_root_override", "")) for call in run_rounds.call_args_list
        )

    refuse([sys.executable, "--workspace", str(tmp_path), "--project", "demo", "--resume"])
    refuse(
        [
            sys.executable,
            "--workspace",
            str(tmp_path),
            "--project",
            "demo",
            "--resume",
            "--provider",
            "gemini",
            "--model",
            "gemini-2.5-flash",
        ]
    )
    resumed = cli(
        tmp_path,
        "--project",
        "demo",
        "--resume",
        "--provider",
        "gemini",
        "--model",
        "gemini-2.5-flash",
    )
    assert resumed.returncode == 2, resumed.stdout + resumed.stderr
    assert "offline mock" in resumed.stdout
    assert "Do not use --resume" in resumed.stdout
    assert "--mock" in resumed.stdout
    assert "Using provider" not in resumed.stdout
    assert "Gemini API key" not in resumed.stdout
    assert "Ollama" not in resumed.stdout
    assert "Resuming the existing run" not in resumed.stdout
    assert hashes(project) == before
    assert json.loads((project / "checkpoint.json").read_text(encoding="utf-8")) == checkpoint


def _old_project(tmp_path: Path, checkpoint: dict, run_files: dict[str, str]) -> tuple[Path, Path]:
    write_config(tmp_path)
    project = tmp_path / "demo"
    project.mkdir()
    (project / "task.md").write_text("Synthetic old mock\n", encoding="utf-8")
    run_root = project / "runs" / "old-mock"
    round_dir = run_root / "round_01"
    round_dir.mkdir(parents=True)
    (round_dir / "04_judge.md").write_text("OLD RESULT\n", encoding="utf-8")
    payload = {
        "run_id": "old-mock",
        "run_root": str(run_root),
        "can_resume": True,
        "last_completed_round": 1,
        "stop_reason": "USER_STOP_REQUESTED",
        "best_score": 70,
    }
    payload.update(checkpoint)
    (project / "checkpoint.json").write_text(json.dumps(payload), encoding="utf-8")
    for name, content in run_files.items():
        (run_root / name).write_text(content, encoding="utf-8")
    return project, run_root


@pytest.mark.parametrize(
    ("checkpoint", "run_files"),
    [
        ({"mode": "mock", "model": "mock"}, {}),
        (
            {},
            {
                "run_config.json": json.dumps(
                    {
                        "mode": "mock",
                        "model": {
                            "provider": "mock",
                            "name": "mock-deterministic",
                            "provider_free": True,
                        },
                        "runtime": {"max_rounds": 2},
                    }
                )
            },
        ),
        (
            {},
            {
                "run_manifest.json": json.dumps(
                    {"run_id": "old-mock", "mode": "mock", "model": "mock-deterministic"}
                )
            },
        ),
        ({"model": "mock-deterministic"}, {}),
        ({"model": "mock"}, {}),
        (
            {"mode": "mock", "model": "mock-deterministic"},
            {
                "run_config.json": json.dumps(
                    {
                        "mode": "normal",
                        "model": {"provider": "ollama", "name": "mock-deterministic"},
                        "runtime": {"max_rounds": 2},
                    }
                )
            },
        ),
        (
            {},
            {
                "run_config.json": json.dumps({"runtime": {"max_rounds": 2}}),
                "run_manifest.json": json.dumps(
                    {"run_id": "old-mock", "mode": "mock", "model": "mock-deterministic"}
                ),
            },
        ),
    ],
)
def test_synthetic_old_mock_records_do_not_start_a_provider(
    tmp_path, monkeypatch, checkpoint, run_files
):
    project, run_root = _old_project(tmp_path, checkpoint, run_files)
    saved = json.loads((project / "checkpoint.json").read_text(encoding="utf-8"))
    before = hashes(project)
    preview = build_resume_preview(project_dir=project, checkpoint=saved, repo_root=tmp_path)
    assert preview["can_resume"] is False
    assert preview["blocked_reason"] == OFFLINE_MOCK_BLOCKED_REASON
    assert "offline mock" in preview["message"]
    with patch("src.resume.run_iterative_rounds") as run_rounds:
        started = run_resume_mode(
            console=Console(quiet=True),
            agents=None,  # type: ignore[arg-type]
            task_text="Synthetic old mock",
            project_dir=project,
            memory_path=project / "memory.md",
            model_name="gemini:gemini-2.5-flash",
            model_provider="gemini",
            max_rounds=2,
            stop_if_no_improvement_rounds=2,
            global_max_runtime_seconds=60,
            per_agent_timeout_seconds=1,
            repo_root=tmp_path,
        )
    assert started is False
    run_rounds.assert_not_called()

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            sys.executable,
            "--workspace",
            str(tmp_path),
            "--project",
            "demo",
            "--resume",
            "--provider",
            "gemini",
            "--model",
            "gemini-2.5-flash",
        ],
    )
    with (
        patch.object(cli_module, "create_llm_client") as create_client,
        patch.object(cli_module, "_validate_model_provider_startup") as precheck,
        patch.object(cli_module, "run_resume_mode") as resume_mode,
        patch("src.resume.run_iterative_rounds") as run_rounds,
        pytest.raises(SystemExit) as raised,
    ):
        cli_module.main()
    assert raised.value.code == 2
    create_client.assert_not_called()
    precheck.assert_not_called()
    resume_mode.assert_not_called()
    run_rounds.assert_not_called()
    assert hashes(project) == before
    assert (run_root / "round_01" / "04_judge.md").read_text(encoding="utf-8") == "OLD RESULT\n"


def test_non_mock_model_switch_still_reaches_provider_precheck(tmp_path, monkeypatch, capsys):
    write_config(tmp_path)
    project = tmp_path / "demo"
    run_root = project / "runs" / "real-run"
    run_root.mkdir(parents=True)
    (project / "task.md").write_text("Synthetic real resume\n", encoding="utf-8")
    checkpoint = {
        "run_id": "real-run",
        "run_root": str(run_root),
        "mode": "normal",
        "model": "qwen3:8b",
        "can_resume": True,
        "last_completed_round": 0,
        "stop_reason": "USER_STOP_REQUESTED",
    }
    (project / "checkpoint.json").write_text(json.dumps(checkpoint), encoding="utf-8")
    (run_root / "run_config.json").write_text(
        json.dumps(
            {
                "mode": "normal",
                "model": {"provider": "ollama", "name": "qwen3:8b"},
                "runtime": {"max_rounds": 1},
            }
        ),
        encoding="utf-8",
    )
    before = (project / "checkpoint.json").read_bytes()
    preview = build_resume_preview(project_dir=project, checkpoint=checkpoint, repo_root=tmp_path)
    assert preview["can_resume"] is True
    dashboard = ui_app.describe_resume_state(
        project_dir=project,
        checkpoint=checkpoint,
        run_active=False,
        selected_model="gemini:gemini-2.5-flash",
    )
    assert dashboard["can_resume"] is True
    assert dashboard["model_mismatch"] is True

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            sys.executable,
            "--workspace",
            str(tmp_path),
            "--project",
            "demo",
            "--resume",
            "--provider",
            "gemini",
            "--model",
            "gemini-2.5-flash",
        ],
    )
    with pytest.raises(SystemExit) as raised:
        cli_module.main()
    assert raised.value.code == 2
    output = capsys.readouterr().out
    assert "offline mock" not in output
    assert "Gemini API key is missing" in output
    assert (project / "checkpoint.json").read_bytes() == before


@pytest.mark.parametrize("model_name", ["mock", "mock-deterministic", "fixture-model"])
def test_explicit_normal_ollama_model_is_not_an_offline_mock(
    tmp_path, monkeypatch, capsys, model_name
):
    write_config(tmp_path)
    project = tmp_path / "demo"
    run_root = project / "runs" / "real-run"
    run_root.mkdir(parents=True)
    (project / "task.md").write_text("Synthetic real resume\n", encoding="utf-8")
    checkpoint = {
        "run_id": "real-run",
        "run_root": str(run_root),
        "mode": "normal",
        "model": model_name,
        "can_resume": True,
        "last_completed_round": 0,
        "stop_reason": "USER_STOP_REQUESTED",
    }
    (project / "checkpoint.json").write_text(json.dumps(checkpoint), encoding="utf-8")
    (run_root / "run_config.json").write_text(
        json.dumps(
            {
                "run_id": "real-run",
                "run_root": str(run_root),
                "mode": "normal",
                "model": {"provider": "ollama", "name": model_name, "label": model_name},
                "runtime": {"max_rounds": 1},
            }
        ),
        encoding="utf-8",
    )
    before_checkpoint = (project / "checkpoint.json").read_bytes()
    before_config = (run_root / "run_config.json").read_bytes()
    preview = build_resume_preview(project_dir=project, checkpoint=checkpoint, repo_root=tmp_path)
    assert preview["can_resume"] is True
    assert preview.get("blocked_reason") != OFFLINE_MOCK_BLOCKED_REASON
    dashboard = ui_app.describe_resume_state(
        project_dir=project,
        checkpoint=checkpoint,
        run_active=False,
        selected_model="gemini:gemini-2.5-flash",
    )
    assert dashboard["can_resume"] is True
    assert dashboard["message_key"] == "resume_available"

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            sys.executable,
            "--workspace",
            str(tmp_path),
            "--project",
            "demo",
            "--resume",
            "--provider",
            "gemini",
            "--model",
            "gemini-2.5-flash",
        ],
    )
    with pytest.raises(SystemExit) as raised:
        cli_module.main()
    assert raised.value.code == 2
    output = capsys.readouterr().out
    assert "offline mock" not in output
    assert "Gemini API key is missing" in output
    assert (project / "checkpoint.json").read_bytes() == before_checkpoint
    assert (run_root / "run_config.json").read_bytes() == before_config


def test_manifest_for_a_different_run_is_not_loaded(tmp_path, monkeypatch, capsys):
    project, run_root = _old_project(
        tmp_path,
        {},
        {
            "run_config.json": json.dumps({"runtime": {"max_rounds": 2}}),
            "run_manifest.json": json.dumps(
                {
                    "run_id": "other-run",
                    "run_root": str(tmp_path / "elsewhere" / "other-run"),
                    "mode": "mock",
                    "model": "mock-deterministic",
                }
            ),
        },
    )
    saved = json.loads((project / "checkpoint.json").read_text(encoding="utf-8"))
    before_checkpoint = (project / "checkpoint.json").read_bytes()
    preview = build_resume_preview(project_dir=project, checkpoint=saved, repo_root=tmp_path)
    assert preview["can_resume"] is True
    assert preview.get("blocked_reason") != OFFLINE_MOCK_BLOCKED_REASON

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            sys.executable,
            "--workspace",
            str(tmp_path),
            "--project",
            "demo",
            "--resume",
            "--provider",
            "gemini",
            "--model",
            "gemini-2.5-flash",
        ],
    )
    with pytest.raises(SystemExit) as raised:
        cli_module.main()
    assert raised.value.code == 2
    output = capsys.readouterr().out
    assert "offline mock" not in output
    assert "Gemini API key is missing" in output
    assert (project / "checkpoint.json").read_bytes() == before_checkpoint
    assert (run_root / "round_01" / "04_judge.md").read_text(encoding="utf-8") == "OLD RESULT\n"


def test_explicit_mock_resume_without_config_explains_the_mock(tmp_path):
    created = cli(tmp_path, "--create-project", "demo", "--task", "Synthetic mock without config")
    assert created.returncode == 0, created.stdout + created.stderr
    decoy = tmp_path / "example"
    decoy.mkdir()
    (decoy / "sentinel.txt").write_text("keep\n", encoding="utf-8")
    project = tmp_path / "demo"
    (project / "STOP_REQUESTED").write_text("STOP_REQUESTED\n", encoding="utf-8")
    stopped = cli(tmp_path, "--project", "demo", "--mock", "--max-rounds", "2")
    assert stopped.returncode == 0, stopped.stdout + stopped.stderr
    assert "Mock mode:" in stopped.stdout
    checkpoint = json.loads((project / "checkpoint.json").read_text(encoding="utf-8"))
    assert checkpoint["mode"] == "mock"
    assert checkpoint["can_resume"] is True
    before = hashes(project)
    decoy_before = (decoy / "sentinel.txt").read_text(encoding="utf-8")

    resumed = cli(tmp_path, "--project", "demo", "--resume")
    output = resumed.stdout + resumed.stderr
    assert resumed.returncode == 2, output
    assert "offline mock" in output
    assert "--mock" in output
    assert "--project=demo" in output
    assert "--project=example" not in output
    assert "Config file not found" not in output
    assert "Using provider" not in output
    assert "Ollama" not in output
    assert "Gemini" not in output
    assert hashes(project) == before
    assert (decoy / "sentinel.txt").read_text(encoding="utf-8") == decoy_before
    assert json.loads((project / "checkpoint.json").read_text(encoding="utf-8")) == checkpoint


def test_missing_config_for_a_real_checkpoint_stays_a_config_error(tmp_path):
    created = cli(tmp_path, "--create-project", "demo", "--task", "Synthetic real without config")
    assert created.returncode == 0, created.stdout + created.stderr
    project = tmp_path / "demo"
    run_root = project / "runs" / "real-run"
    run_root.mkdir(parents=True)
    checkpoint = {
        "run_id": "real-run",
        "run_root": str(run_root),
        "mode": "normal",
        "model": "qwen3:8b",
        "can_resume": True,
        "last_completed_round": 0,
        "stop_reason": "USER_STOP_REQUESTED",
    }
    (project / "checkpoint.json").write_text(json.dumps(checkpoint), encoding="utf-8")
    (run_root / "run_config.json").write_text(
        json.dumps(
            {
                "run_id": "real-run",
                "run_root": str(run_root),
                "mode": "normal",
                "model": {"provider": "ollama", "name": "qwen3:8b"},
            }
        ),
        encoding="utf-8",
    )
    before = hashes(project)
    resumed = cli(tmp_path, "--project", "demo", "--resume")
    output = resumed.stdout + resumed.stderr
    assert resumed.returncode == 2, output
    assert "Config file not found" in output
    assert "offline mock" not in output
    assert "Using provider" not in output
    assert hashes(project) == before


def test_invalid_config_for_a_mock_keeps_the_config_error(tmp_path):
    created = cli(tmp_path, "--create-project", "demo", "--task", "Synthetic mock invalid config")
    assert created.returncode == 0, created.stdout + created.stderr
    project = tmp_path / "demo"
    (project / "STOP_REQUESTED").write_text("STOP_REQUESTED\n", encoding="utf-8")
    stopped = cli(tmp_path, "--project", "demo", "--mock", "--max-rounds", "1")
    assert stopped.returncode == 0, stopped.stdout + stopped.stderr
    (tmp_path / "config.yaml").write_text("[\n", encoding="utf-8")
    before = hashes(project)
    resumed = cli(tmp_path, "--project", "demo", "--resume")
    output = resumed.stdout + resumed.stderr
    assert resumed.returncode == 2, output
    assert "Config error" in output
    assert "offline mock" not in output
    assert "Using provider" not in output
    assert hashes(project) == before


def test_finalization_conflict_keeps_its_guidance_for_a_mock(tmp_path, monkeypatch):
    project, _run_root = _old_project(tmp_path, {"mode": "mock", "model": "mock"}, {})
    (project / RUN_FINALIZE_JOURNAL_NAME).write_text("{}\n", encoding="utf-8")
    saved = json.loads((project / "checkpoint.json").read_text(encoding="utf-8"))
    before = hashes(project)
    preview = build_resume_preview(project_dir=project, checkpoint=saved, repo_root=tmp_path)
    assert preview["can_resume"] is False
    assert preview["blocked_reason"] == "finalization_conflict"
    assert "inspect" in preview["message"]
    assert "offline mock" not in preview["message"]
    assert "Restart" not in preview["message"]
    dashboard = ui_app.describe_resume_state(
        project_dir=project,
        checkpoint=saved,
        run_active=False,
        selected_model="gemini:gemini-2.5-flash",
    )
    assert dashboard["can_resume"] is False
    assert dashboard["message_key"] == "finalization_conflict"
    assert "offline mock" not in dashboard["message"]

    monkeypatch.setattr(ui_app, "ROOT", tmp_path)
    monkeypatch.setattr(ui_app, "CONFIG_PATH", tmp_path / "config.yaml")
    monkeypatch.setattr(
        web.h,
        "start_background_process",
        lambda **kwargs: pytest.fail(f"started {kwargs}"),
    )
    with pytest.raises(ValueError, match="inspect"):
        web.action(
            {
                "action": "run",
                "project": "demo",
                "provider": "gemini",
                "model": "gemini-2.5-flash",
                "mode": "resume",
                "api_key": "test-secret",
                "free_runner_preset": "manual",
            }
        )

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            sys.executable,
            "--workspace",
            str(tmp_path),
            "--project",
            "demo",
            "--resume",
            "--provider",
            "gemini",
            "--model",
            "gemini-2.5-flash",
        ],
    )
    with (
        patch.object(cli_module, "create_llm_client") as create_client,
        patch.object(cli_module, "_validate_model_provider_startup") as precheck,
        patch.object(cli_module, "list_installed_ollama_models") as list_models,
        patch("src.resume.run_iterative_rounds") as run_rounds,
        pytest.raises(SystemExit) as raised,
    ):
        cli_module.main()
    assert raised.value.code == 2
    create_client.assert_not_called()
    precheck.assert_not_called()
    list_models.assert_not_called()
    run_rounds.assert_not_called()
    assert hashes(project) == before


def test_run_id_mismatch_keeps_path_guidance_for_a_mock(tmp_path, monkeypatch, capsys):
    project, _run_root = _old_project(
        tmp_path,
        {"mode": "mock", "model": "mock", "run_id": "other-run"},
        {},
    )
    saved = json.loads((project / "checkpoint.json").read_text(encoding="utf-8"))
    before = hashes(project)
    preview = build_resume_preview(project_dir=project, checkpoint=saved, repo_root=tmp_path)
    assert preview["blocked_reason"] == "run_id_mismatch"
    assert preview["can_resume"] is False
    assert "offline mock" not in preview["message"]

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            sys.executable,
            "--workspace",
            str(tmp_path),
            "--project",
            "demo",
            "--resume",
            "--provider",
            "gemini",
            "--model",
            "gemini-2.5-flash",
        ],
    )
    with (
        patch.object(cli_module, "_validate_model_provider_startup") as precheck,
        pytest.raises(SystemExit) as raised,
    ):
        cli_module.main()
    assert raised.value.code == 2
    precheck.assert_not_called()
    output = capsys.readouterr().out
    assert "run_id must match" in output
    assert "offline mock" not in output
    assert hashes(project) == before


def test_recovered_finalization_mock_is_refused_before_provider_precheck(
    tmp_path, monkeypatch, capsys
):
    write_config(tmp_path)
    created = cli(tmp_path, "--create-project", "demo", "--task", "Synthetic paused mock")
    assert created.returncode == 0, created.stdout + created.stderr
    project = tmp_path / "demo"
    (project / "STOP_REQUESTED").write_text("STOP_REQUESTED\n", encoding="utf-8")
    original_recover = runner_module.recover_run_finalize

    def pause_before_apply(_project_dir: Path) -> None:
        raise RuntimeError("paused before journal apply")

    monkeypatch.setattr(runner_module, "recover_run_finalize", pause_before_apply)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            sys.executable,
            "--workspace",
            str(tmp_path),
            "--project",
            "demo",
            "--mock",
            "--max-rounds",
            "1",
        ],
    )
    with pytest.raises(RuntimeError, match="paused before journal apply"):
        cli_module.main()
    monkeypatch.setattr(runner_module, "recover_run_finalize", original_recover)
    capsys.readouterr()

    assert not (project / "checkpoint.json").exists()
    inspection = classify_run_finalize_recovery(project)
    assert inspection.status == "apply_pending"
    assert (project / RUN_FINALIZE_JOURNAL_NAME).is_file()

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            sys.executable,
            "--workspace",
            str(tmp_path),
            "--project",
            "demo",
            "--resume",
            "--provider",
            "gemini",
            "--model",
            "gemini-2.5-flash",
        ],
    )
    with (
        patch.object(cli_module, "create_llm_client") as create_client,
        patch.object(cli_module, "_validate_model_provider_startup") as precheck,
        patch.object(cli_module, "list_installed_ollama_models") as list_models,
        patch("src.resume.run_iterative_rounds") as run_rounds,
        pytest.raises(SystemExit) as raised,
    ):
        cli_module.main()
    assert raised.value.code == 2
    create_client.assert_not_called()
    precheck.assert_not_called()
    list_models.assert_not_called()
    run_rounds.assert_not_called()
    output = capsys.readouterr().out
    assert "offline mock" in output
    assert "Gemini API key" not in output
    assert "Failed to query Ollama" not in output
    checkpoint = json.loads((project / "checkpoint.json").read_text(encoding="utf-8"))
    assert checkpoint["mode"] == "mock"
    assert checkpoint["can_resume"] is True
    assert not (project / RUN_FINALIZE_JOURNAL_NAME).exists()
    recovered = hashes(project)

    with (
        patch.object(cli_module, "_validate_model_provider_startup") as precheck,
        patch("src.resume.run_iterative_rounds") as run_rounds,
        pytest.raises(SystemExit) as raised,
    ):
        cli_module.main()
    assert raised.value.code == 2
    precheck.assert_not_called()
    run_rounds.assert_not_called()
    assert hashes(project) == recovered
