from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from rich.console import Console

from src.agents import ResearchAgents
from src.judge_output import (
    JUDGE_SCORING_INSTRUCTIONS,
    RUBRIC_LIMITS,
    InvalidJudgeOutput,
    parse_judge_score,
    validate_new_judge_output,
)
from src.mock_run import build_mock_agents
from src.runner import run_iterative_rounds


def valid_payload():
    return {
        "score": 80,
        "rubric": {key: limit * 0.8 for key, limit in RUBRIC_LIMITS.items()},
        "reasons": ["Concrete test plan"],
        "blockers": [],
        "next_step": "CONTINUE",
    }


@pytest.mark.parametrize(
    "mutation",
    [
        lambda p: p.update(score=999),
        lambda p: p.update(score=-1),
        lambda p: p.update(score=True),
        lambda p: p.update(score="80"),
        lambda p: p.update(score=float("nan")),
        lambda p: p.update(score=4.5),
        lambda p: p.pop("blockers"),
        lambda p: p.update(extra="unexpected"),
        lambda p: p.update(rubric={}),
        lambda p: p["rubric"].update(tomorrow_actionability=11),
        lambda p: p.update(reasons="text"),
        lambda p: p.update(blockers=[42]),
        lambda p: p.update(next_step="MAYBE"),
    ],
)
def test_reject_invalid_new_response(mutation):
    payload = valid_payload()
    mutation(payload)
    with pytest.raises(InvalidJudgeOutput):
        validate_new_judge_output(json.dumps(payload))


@pytest.mark.parametrize(
    "text", ['{"score":999}', "SCORE: 80", "```json\n{}\n```", '{"score":1,"score":2}']
)
def test_new_responses_are_strict_but_history_stays_readable(text):
    with pytest.raises(InvalidJudgeOutput):
        validate_new_judge_output(text)
    assert parse_judge_score("SCORE: 80") == 80
    assert parse_judge_score('{"score":999}') == 100


def test_shared_rubric_and_mock_contract():
    calls = []
    llm = SimpleNamespace(generate=lambda **kw: calls.append(kw) or json.dumps(valid_payload()))
    agents = ResearchAgents(llm, "draft", "review", "revise", "judge", 0.2, 0.8)
    validate_new_judge_output(agents.judge(task="Task", memory="", revised_output="Revision"))
    assert JUDGE_SCORING_INSTRUCTIONS in calls[0]["system_prompt"]
    for n in [1, 2, 20]:
        validate_new_judge_output(
            build_mock_agents().judge(task="Task", memory="", revised_output=f"Round {n}")
        )


def test_malformed_provider_score_cannot_promote_best(tmp_path):
    class LLM:
        timeout_seconds = 1

        def generate(self, **kwargs):
            return '{"score":999}' if kwargs["agent_name"] == "judge" else "Synthetic output"

    agents = ResearchAgents(LLM(), "draft", "review", "revise", "judge", 0.2, 0.8)
    memory = tmp_path / "memory.md"
    memory.write_text("Original memory")
    best = tmp_path / "best_output.md"
    best.write_text("Previously accepted output")
    result = run_iterative_rounds(
        console=Console(),
        agents=agents,
        task_text="Synthetic task",
        project_dir=tmp_path,
        memory_path=memory,
        mode="normal",
        model_name="fake",
        max_rounds=1,
        stop_if_no_improvement_rounds=2,
        global_max_runtime_seconds=30,
        per_agent_timeout_seconds=1,
    )
    metrics = json.loads((result["run_root"] / "round_metrics.json").read_text())
    assert not metrics[0]["successful_research_round"]
    assert "Invalid Judge output" in metrics[0]["agent_errors"]["judge"]
    assert best.read_text() == "Previously accepted output"
