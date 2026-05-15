from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional


class NullConsole:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def print(self, *args: object, **kwargs: object) -> None:
        del kwargs
        self.messages.append(" ".join(str(arg) for arg in args))

    def rule(self, *args: object, **kwargs: object) -> None:
        del kwargs
        self.messages.append(" ".join(str(arg) for arg in args))


class FakeLLM:
    def __init__(self, timeout_seconds: int = 300) -> None:
        self.timeout_seconds = timeout_seconds


class ConfigurableFakeAgents:
    def __init__(
        self,
        *,
        judge_outputs: Optional[list[str]] = None,
        errors: Optional[dict[str, str]] = None,
        draft_side_effect: Optional[Callable[[], None]] = None,
    ) -> None:
        self.llm = FakeLLM()
        self.judge_outputs = judge_outputs or [
            "SCORE: 50\n- Judge feedback for score 50.",
            "SCORE: 40\n- Judge feedback for score 40.",
        ]
        self.errors = errors or {}
        self.draft_side_effect = draft_side_effect
        self.calls: list[str] = []

    def _maybe_raise(self, agent_name: str) -> None:
        self.calls.append(agent_name)
        if agent_name in self.errors:
            raise RuntimeError(self.errors[agent_name])

    def draft(
        self,
        *,
        task: str,
        memory: str,
        round_index: int,
        previous_best: str,
        previous_judge: str,
    ) -> str:
        del memory, previous_judge
        self._maybe_raise("draft")
        if self.draft_side_effect:
            self.draft_side_effect()
        return f"Draft round {round_index}: {task[:20]} | previous={bool(previous_best)}"

    def review(self, *, task: str, memory: str, draft_output: str) -> str:
        del task, memory
        self._maybe_raise("review")
        return f"Review notes for {draft_output}"

    def revise(
        self,
        *,
        task: str,
        memory: str,
        draft_output: str,
        review_output: str,
    ) -> str:
        del task, memory, review_output
        self._maybe_raise("revise")
        return f"Revised output from {draft_output}"

    def judge(self, *, task: str, memory: str, revised_output: str) -> str:
        del task, memory, revised_output
        self._maybe_raise("judge")
        return self.judge_outputs.pop(0)


@dataclass
class ProjectFixture:
    project_dir: Path
    memory_path: Path


def make_project_fixture(root: Path, *, memory: str = "Manual memory.\n") -> ProjectFixture:
    project_dir = root / "project"
    project_dir.mkdir()
    memory_path = project_dir / "memory.md"
    memory_path.write_text(memory, encoding="utf-8")
    return ProjectFixture(project_dir=project_dir, memory_path=memory_path)
