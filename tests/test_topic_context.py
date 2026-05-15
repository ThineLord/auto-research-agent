from __future__ import annotations

import unittest
from pathlib import Path

from rich.console import Console

from src.agents import ResearchAgents
from src.session import generate_focus_objective

ROOT = Path(__file__).resolve().parents[1]


class CapturingLLM:
    def __init__(self, response: str = "done") -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def generate(self, **kwargs: object) -> str:
        self.calls.append(kwargs)
        return self.response


class FailingLLM:
    def generate(self, **_: object) -> str:
        raise RuntimeError("offline")


class TopicContextTests(unittest.TestCase):
    def test_prompt_templates_do_not_hardcode_pama(self) -> None:
        for prompt_path in (ROOT / "prompts").glob("*.md"):
            with self.subTest(prompt=prompt_path.name):
                content = prompt_path.read_text(encoding="utf-8")
                self.assertNotIn("PAMA", content)
                self.assertNotIn("Privacy-Aware Memory Adapter", content)

    def test_agents_inject_configured_topic_context_into_user_prompt(self) -> None:
        llm = CapturingLLM()
        agents = ResearchAgents(
            llm=llm,  # type: ignore[arg-type]
            draft_prompt="draft system",
            review_prompt="review system",
            revise_prompt="revise system",
            judge_prompt="judge system",
            temperature=0.2,
            top_p=0.8,
            topic_context="Title: Graph Retrieval Evaluation\nKeywords: graph, retrieval",
        )

        agents.draft(
            task="Design an evaluation.",
            memory="Prior notes.",
            round_index=1,
            previous_best="",
            previous_judge="",
        )

        user_prompt = str(llm.calls[-1]["user_prompt"])
        self.assertIn("# Topic Context", user_prompt)
        self.assertIn("Graph Retrieval Evaluation", user_prompt)
        self.assertIn("# Research Task", user_prompt)

    def test_session_fallback_uses_configured_topic_title(self) -> None:
        objective = generate_focus_objective(
            llm=FailingLLM(),  # type: ignore[arg-type]
            task_text="Task",
            memory_text="Memory",
            console=Console(),
            topic_context="Title: Graph Retrieval Evaluation",
            topic_title="Graph Retrieval Evaluation",
        )

        self.assertIn("Graph Retrieval Evaluation", objective)
        self.assertNotIn("PAMA", objective)


if __name__ == "__main__":
    unittest.main()
