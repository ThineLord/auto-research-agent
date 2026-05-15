"""Judge output schema and parsing helpers."""

from __future__ import annotations

import json
import math
import re
from typing import Any, Dict, Optional

JUDGE_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "score": {
            "type": "number",
            "minimum": 0,
            "maximum": 100,
        },
        "rubric": {
            "type": "object",
            "properties": {
                "novelty_and_research_value": {"type": "number"},
                "technical_clarity_and_correctness": {"type": "number"},
                "feasibility_and_implementation_realism": {"type": "number"},
                "evaluation_design_quality": {"type": "number"},
                "tomorrow_actionability": {"type": "number"},
            },
            "required": [
                "novelty_and_research_value",
                "technical_clarity_and_correctness",
                "feasibility_and_implementation_realism",
                "evaluation_design_quality",
                "tomorrow_actionability",
            ],
            "additionalProperties": False,
        },
        "reasons": {
            "type": "array",
            "items": {"type": "string"},
        },
        "blockers": {
            "type": "array",
            "items": {"type": "string"},
        },
        "next_step": {
            "type": "string",
            "enum": ["CONTINUE", "STOP"],
        },
    },
    "required": ["score", "rubric", "reasons", "blockers", "next_step"],
    "additionalProperties": False,
}

_LEGACY_SCORE_RE = re.compile(
    r"\bSCORE:\s*([-+]?[0-9]+(?:\.[0-9]+)?)\b",
    flags=re.IGNORECASE,
)
_FENCED_JSON_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", flags=re.DOTALL)


def _clamp_score(score: float) -> float:
    return max(0.0, min(100.0, score))


def _coerce_score(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        score = float(value)
    elif isinstance(value, str):
        try:
            score = float(value.strip())
        except ValueError:
            return None
    else:
        return None
    if not math.isfinite(score):
        return None
    return _clamp_score(score)


def _parse_json_score(candidate: str) -> Optional[float]:
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return _coerce_score(data.get("score"))


def _extract_first_json_object(text: str) -> Optional[str]:
    start = text.find("{")
    if start < 0:
        return None

    depth = 0
    in_string = False
    escape = False
    for index, char in enumerate(text[start:], start=start):
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def _parse_structured_score(judge_text: str) -> Optional[float]:
    text = judge_text.strip()
    if not text:
        return None

    direct_score = _parse_json_score(text)
    if direct_score is not None:
        return direct_score

    fenced_match = _FENCED_JSON_RE.search(text)
    if fenced_match:
        fenced_score = _parse_json_score(fenced_match.group(1).strip())
        if fenced_score is not None:
            return fenced_score

    object_text = _extract_first_json_object(text)
    if object_text:
        return _parse_json_score(object_text)
    return None


def parse_judge_score(judge_text: str) -> Optional[float]:
    """Parse a judge score from strict JSON first, then legacy SCORE lines."""
    structured_score = _parse_structured_score(judge_text)
    if structured_score is not None:
        return structured_score

    legacy_match = _LEGACY_SCORE_RE.search(judge_text)
    if not legacy_match:
        return None
    return _coerce_score(legacy_match.group(1))
