"""Judge output schema and parsing helpers."""

from __future__ import annotations

import json
import math
import re
from typing import Any, Dict, Optional

RUBRIC_LIMITS = {
    "novelty_and_research_value": 25,
    "technical_clarity_and_correctness": 25,
    "feasibility_and_implementation_realism": 20,
    "evaluation_design_quality": 20,
    "tomorrow_actionability": 10,
}
JUDGE_SCORING_INSTRUCTIONS = (
    "Return JSON only with rubric, score, reasons, blockers, next_step. "
    "Use a 0-100 total, NOT a 0-5 or 0-10 rating. Rubric values are earned points: "
    + ", ".join(f"{key}: 0-{limit}" for key, limit in RUBRIC_LIMITS.items())
    + ". First assign the five rubric points. Emit rubric before score, then calculate score "
    "by adding those exact values. Example: 20 + 20 + 15 + 15 + 10 = 80, not 90. "
    "Do not estimate a separate overall score. "
    "reasons and blockers must be arrays of strings; next_step must be CONTINUE or STOP."
)

JUDGE_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
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
        "score": {
            "type": "number",
            "minimum": 0,
            "maximum": 100,
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

for _key, _limit in RUBRIC_LIMITS.items():
    JUDGE_OUTPUT_SCHEMA["properties"]["rubric"]["properties"][_key].update(
        minimum=0, maximum=_limit
    )


class InvalidJudgeOutput(RuntimeError):
    """A new provider response violated the scoring contract."""


def validate_new_judge_output(text: str) -> str:
    """Validate new responses; legacy artifact parsers below remain permissive."""

    def reject_duplicates(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result

    try:
        payload = json.loads(text, object_pairs_hook=reject_duplicates)
        if not isinstance(payload, dict) or set(payload) != set(JUDGE_OUTPUT_SCHEMA["required"]):
            raise ValueError("required fields")
        rubric = payload["rubric"]
        if not isinstance(rubric, dict) or set(rubric) != set(RUBRIC_LIMITS):
            raise ValueError("rubric fields")
        for key, maximum in {"score": 100, **RUBRIC_LIMITS}.items():
            value = payload["score"] if key == "score" else rubric[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError("numeric points required")
            if not math.isfinite(value) or not 0 <= value <= maximum:
                raise ValueError("points out of range")
        if not math.isclose(payload["score"], sum(rubric.values()), abs_tol=0.01, rel_tol=0):
            raise ValueError("score must equal rubric sum")
        for key in ("reasons", "blockers"):
            if not isinstance(payload[key], list) or any(
                not isinstance(v, str) for v in payload[key]
            ):
                raise ValueError("string arrays required")
        if payload["next_step"] not in ("CONTINUE", "STOP"):
            raise ValueError("next_step")
    except (ValueError, TypeError, OverflowError, RecursionError) as exc:
        # Do not echo provider text (which can contain private task material).
        raise InvalidJudgeOutput(
            "Invalid Judge output: complete 0-100 JSON scoring required"
        ) from exc
    return text


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
    try:
        if isinstance(value, (int, float)):
            score = float(value)
        elif isinstance(value, str):
            score = float(value.strip())
        else:
            return None
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(score):
        return None
    return _clamp_score(score)


def _parse_json_score(candidate: str) -> Optional[float]:
    try:
        data = json.loads(candidate)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    return _coerce_score(data.get("score"))


def _parse_json_object(candidate: str) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(candidate)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


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


def parse_judge_payload(judge_text: str) -> Dict[str, Any]:
    """Parse the first structured judge JSON object, returning {} for legacy text."""
    text = judge_text.strip()
    if not text:
        return {}

    direct = _parse_json_object(text)
    if direct is not None:
        return direct

    fenced_match = _FENCED_JSON_RE.search(text)
    if fenced_match:
        fenced = _parse_json_object(fenced_match.group(1).strip())
        if fenced is not None:
            return fenced

    object_text = _extract_first_json_object(text)
    if object_text:
        parsed = _parse_json_object(object_text)
        if parsed is not None:
            return parsed
    return {}


def parse_judge_rubric(judge_text: str) -> Dict[str, float]:
    payload = parse_judge_payload(judge_text)
    rubric = payload.get("rubric")
    if not isinstance(rubric, dict):
        return {}
    normalized: Dict[str, float] = {}
    for key, value in rubric.items():
        score = _coerce_score(value)
        if score is not None:
            normalized[str(key)] = score
    return normalized


def parse_judge_score(judge_text: str) -> Optional[float]:
    """Parse a judge score from strict JSON first, then legacy SCORE lines."""
    structured_score = _parse_structured_score(judge_text)
    if structured_score is not None:
        return structured_score

    legacy_match = _LEGACY_SCORE_RE.search(judge_text)
    if not legacy_match:
        return None
    return _coerce_score(legacy_match.group(1))
