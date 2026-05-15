"""Agent wrappers for the iterative research pipeline."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from .judge_output import JUDGE_OUTPUT_SCHEMA
from .llm import OllamaClient

logger = logging.getLogger(__name__)


def _read_prompt(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


@dataclass
class ResearchAgents:
    llm: OllamaClient
    draft_prompt: str
    review_prompt: str
    revise_prompt: str
    judge_prompt: str
    temperature: float
    top_p: float

    @classmethod
    def from_prompt_dir(
        cls,
        *,
        llm: OllamaClient,
        prompt_dir: Path,
        temperature: float,
        top_p: float,
    ) -> "ResearchAgents":
        return cls(
            llm=llm,
            draft_prompt=_read_prompt(prompt_dir / "draft.md"),
            review_prompt=_read_prompt(prompt_dir / "review.md"),
            revise_prompt=_read_prompt(prompt_dir / "revise.md"),
            judge_prompt=_read_prompt(prompt_dir / "judge.md"),
            temperature=temperature,
            top_p=top_p,
        )

    def draft(
        self,
        *,
        task: str,
        memory: str,
        round_index: int,
        previous_best: str,
        previous_judge: str,
    ) -> str:
        prompt = (
            f"# Round\n{round_index}\n\n"
            f"# Research Task\n{task}\n\n"
            f"# Project Memory\n{memory}\n\n"
            f"# Previous Best (optional)\n{previous_best or '(none)'}\n\n"
            f"# Previous Judge Feedback (optional)\n{previous_judge or '(none)'}\n"
        )
        logger.info(
            "agent_prompt_prepared",
            extra={
                "event": "agent_prompt_prepared",
                "agent_name": "draft",
                "round": round_index,
                "prompt_chars": len(prompt),
                "memory_words": len(memory.split()),
            },
        )
        return self.llm.generate(
            agent_name="draft",
            system_prompt=self.draft_prompt,
            user_prompt=prompt,
            temperature=self.temperature,
            top_p=self.top_p,
        )

    def review(self, *, task: str, memory: str, draft_output: str) -> str:
        prompt = (
            f"# Research Task\n{task}\n\n"
            f"# Project Memory\n{memory}\n\n"
            f"# Draft Output\n{draft_output}\n"
        )
        logger.info(
            "agent_prompt_prepared",
            extra={
                "event": "agent_prompt_prepared",
                "agent_name": "review",
                "prompt_chars": len(prompt),
                "memory_words": len(memory.split()),
            },
        )
        return self.llm.generate(
            agent_name="review",
            system_prompt=self.review_prompt,
            user_prompt=prompt,
            temperature=self.temperature,
            top_p=self.top_p,
        )

    def revise(
        self,
        *,
        task: str,
        memory: str,
        draft_output: str,
        review_output: str,
    ) -> str:
        prompt = (
            f"# Research Task\n{task}\n\n"
            f"# Project Memory\n{memory}\n\n"
            f"# Draft Output\n{draft_output}\n\n"
            f"# Review Feedback\n{review_output}\n"
        )
        logger.info(
            "agent_prompt_prepared",
            extra={
                "event": "agent_prompt_prepared",
                "agent_name": "revise",
                "prompt_chars": len(prompt),
                "memory_words": len(memory.split()),
            },
        )
        return self.llm.generate(
            agent_name="revise",
            system_prompt=self.revise_prompt,
            user_prompt=prompt,
            temperature=self.temperature,
            top_p=self.top_p,
        )

    def judge(self, *, task: str, memory: str, revised_output: str) -> str:
        prompt = (
            f"# Research Task\n{task}\n\n"
            f"# Project Memory\n{memory}\n\n"
            f"# Revised Output\n{revised_output}\n"
        )
        logger.info(
            "agent_prompt_prepared",
            extra={
                "event": "agent_prompt_prepared",
                "agent_name": "judge",
                "prompt_chars": len(prompt),
                "memory_words": len(memory.split()),
            },
        )
        return self.llm.generate(
            agent_name="judge",
            system_prompt=self.judge_prompt,
            user_prompt=prompt,
            temperature=self.temperature,
            top_p=self.top_p,
            response_format=JUDGE_OUTPUT_SCHEMA,
        )
