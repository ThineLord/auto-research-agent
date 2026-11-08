from __future__ import annotations

import json

import pytest
from rich.console import Console

import src.runner as runner
from src.mock_run import build_mock_agents


@pytest.mark.parametrize("stop_round", [1, 2])
def test_stop_after_attempt_creation_remains_resumable(tmp_path, monkeypatch, stop_round):
    memory = tmp_path / "memory.md"
    memory.write_text("Synthetic memory")
    create = runner.create_round_attempt

    def stop_after_create(**kwargs):
        attempt = create(**kwargs)
        if kwargs["round_index"] == stop_round:
            (tmp_path / "STOP_REQUESTED").write_text("stop at pre-draft boundary")
        return attempt

    common = dict(
        console=Console(),
        agents=build_mock_agents(),
        task_text="Synthetic stop test",
        project_dir=tmp_path,
        memory_path=memory,
        model_name="mock",
        max_rounds=3,
        stop_if_no_improvement_rounds=10,
        global_max_runtime_seconds=60,
        per_agent_timeout_seconds=1,
    )
    with monkeypatch.context() as scoped:
        scoped.setattr(runner, "create_round_attempt", stop_after_create)
        stopped = runner.run_iterative_rounds(**common, mode="mock")
    checkpoint = json.loads((tmp_path / "checkpoint.json").read_text())
    assert checkpoint["can_resume"]
    assert json.loads((stopped["run_root"] / "run_summary.json").read_text())["can_resume"]
    assert stopped["completed_rounds"] == stop_round - 1
    assert checkpoint["stop_reason"] == "USER_STOP_REQUESTED"
    run_root = stopped["run_root"]
    assert not (run_root / f"round_{stop_round:02d}").exists()
    attempts = list((run_root / "partial_rounds" / f"round_{stop_round:02d}").glob("attempt_*"))
    assert len(attempts) == 1
    assert json.loads((attempts[0] / "attempt.json").read_text())["state"] == "stopped"
    completed_bytes = {p: p.read_bytes() for p in run_root.glob("round_*/*.md")}
    resumed = runner.run_iterative_rounds(
        **common,
        mode="resume",
        start_round=stop_round,
        run_root_override=run_root,
        initial_best_score=stopped["best_score"],
    )
    assert resumed["completed_rounds"] == 3
    assert resumed["stop_reason"] == "MAX_ROUNDS"
    assert all(p.read_bytes() == content for p, content in completed_bytes.items())
    history = json.loads((tmp_path / "score_history.json").read_text())
    assert [item["round"] for item in history] == [1, 2, 3]
    assert all(item["score"] > 0 for item in history)
