"""Deterministic provider-free agents for CI-safe demo runs."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

MOCK_MODEL_NAME = "mock-deterministic"
MOCK_MODEL_PROVIDER = "mock"
MOCK_DEFAULT_ROUNDS = 2
MOCK_TOKEN_ESTIMATE_METHOD = "deterministic_mock_visible_chars_div_4"


@dataclass
class MockLLM:
    """Minimal LLM-like object expected by the normal runner."""

    timeout_seconds: int = 1
    max_prompt_chars: int = 12000


class MockResearchAgents:
    """Fake Draft/Review/Revise/Judge agents that never call a model provider."""

    def __init__(self, *, topic_context: str = "") -> None:
        self.llm = MockLLM()
        self.topic_context = topic_context
        self.temperature = 0.0
        self.top_p = 1.0
        self.draft_prompt = "Deterministic mock draft prompt."
        self.review_prompt = "Deterministic mock review prompt."
        self.revise_prompt = "Deterministic mock revise prompt."
        self.judge_prompt = "Deterministic mock judge prompt."

    def draft(
        self,
        *,
        task: str,
        memory: str,
        round_index: int,
        previous_best: str,
        previous_judge: str,
        drafting_mode: str = "best_guided",
        previous_review: str = "",
        previous_draft: str = "",
        previous_revised: str = "",
    ) -> str:
        context_flags = [
            f"previous_best={bool(previous_best.strip())}",
            f"previous_judge={bool(previous_judge.strip())}",
            f"previous_review={bool(previous_review.strip())}",
            f"previous_draft={bool(previous_draft.strip())}",
            f"previous_revised={bool(previous_revised.strip())}",
        ]
        return "\n".join(
            [
                f"# Mock Draft Round {round_index}",
                "",
                f"Drafting mode: {drafting_mode}",
                f"Task excerpt: {_excerpt(task, 180)}",
                f"Memory excerpt: {_excerpt(memory, 120) or 'No project memory provided.'}",
                f"Topic context: {_excerpt(self.topic_context, 120) or 'No topic context provided.'}",
                f"Context flags: {', '.join(context_flags)}",
                "",
                "Deterministic proposal:",
                f"- Clarify the research objective for round {round_index}.",
                "- Preserve reproducibility metadata and avoid external provider calls.",
                "- Inspect the generated artifacts before using this as a real experiment.",
            ]
        )

    def review(self, *, task: str, memory: str, draft_output: str) -> str:
        round_index = _extract_round_index(draft_output)
        return "\n".join(
            [
                f"# Mock Review Round {round_index}",
                "",
                "- The draft is deterministic and suitable for CI/docs smoke coverage.",
                "- Treat scores as synthetic demo signals, not research evaluation results.",
                f"- Task coverage cue: {_excerpt(task, 100)}",
                f"- Memory cue: {_excerpt(memory, 80) or 'No memory available.'}",
            ]
        )

    def revise(
        self,
        *,
        task: str,
        memory: str,
        draft_output: str,
        review_output: str,
    ) -> str:
        round_index = _extract_round_index(draft_output)
        return "\n".join(
            [
                f"# Mock Revised Output Round {round_index}",
                "",
                "This deterministic output demonstrates the normal artifact lifecycle.",
                "",
                "Action checklist:",
                f"- Confirm task focus: {_excerpt(task, 120)}",
                "- Confirm run_config.json, round_metrics.json, run_summary.json, and checkpoint.json were written.",
                "- Confirm no Ollama, Gemini, network, or API key dependency was required.",
                "",
                "Review incorporated:",
                _excerpt(review_output, 220),
                "",
                f"Memory retained: {_excerpt(memory, 120) or 'No project memory available.'}",
            ]
        )

    def judge(self, *, task: str, memory: str, revised_output: str) -> str:
        round_index = _extract_round_index(revised_output)
        score = min(95, 70 + round_index * 3)
        rubric_value = min(20, 12 + round_index)
        return json.dumps(
            {
                "score": score,
                "rubric": {
                    "novelty_and_research_value": rubric_value,
                    "technical_clarity_and_correctness": rubric_value + 1,
                    "feasibility_and_implementation_realism": rubric_value + 2,
                    "evaluation_design_quality": rubric_value,
                    "tomorrow_actionability": rubric_value + 1,
                },
                "reasons": [
                    "Synthetic deterministic score for provider-free artifact smoke testing.",
                    f"Task signal length: {len(task)} chars; memory signal length: {len(memory)} chars.",
                ],
                "blockers": [],
                "next_step": "CONTINUE",
            },
            sort_keys=True,
        )


def build_mock_agents(*, topic_context: str = "") -> MockResearchAgents:
    return MockResearchAgents(topic_context=topic_context)


def mock_model_parameters(*, max_prompt_chars: int = 12000) -> dict[str, object]:
    return {
        "temperature": 0.0,
        "top_p": 1.0,
        "timeout_seconds": 1,
        "max_prompt_chars": max_prompt_chars,
        "provider_free": True,
        "deterministic": True,
        "token_estimate_method": MOCK_TOKEN_ESTIMATE_METHOD,
    }


def _excerpt(text: str, limit: int) -> str:
    normalized = " ".join(str(text or "").split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: max(0, limit - 3)].rstrip() + "..."


def _extract_round_index(text: str) -> int:
    match = re.search(r"\bRound\s+(\d+)\b", str(text or ""), re.IGNORECASE)
    if not match:
        return 1
    try:
        return max(1, int(match.group(1)))
    except ValueError:
        return 1
