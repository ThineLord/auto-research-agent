from __future__ import annotations

import unittest

from src.judge_output import parse_judge_payload, parse_judge_rubric, parse_judge_score


class JudgeOutputTests(unittest.TestCase):
    def test_parses_payload_and_rubric_from_structured_judge_json(self) -> None:
        judge_text = """
```json
{
  "score": 82,
  "rubric": {
    "novelty_and_research_value": 16,
    "technical_clarity_and_correctness": 17
  },
  "reasons": ["clear"],
  "blockers": [],
  "next_step": "CONTINUE"
}
```
"""

        self.assertEqual(parse_judge_score(judge_text), 82.0)
        self.assertEqual(parse_judge_payload(judge_text)["next_step"], "CONTINUE")
        self.assertEqual(
            parse_judge_rubric(judge_text),
            {
                "novelty_and_research_value": 16.0,
                "technical_clarity_and_correctness": 17.0,
            },
        )

    def test_legacy_score_text_has_no_structured_rubric(self) -> None:
        judge_text = "SCORE: 71\n- Useful but incomplete."

        self.assertEqual(parse_judge_score(judge_text), 71.0)
        self.assertEqual(parse_judge_payload(judge_text), {})
        self.assertEqual(parse_judge_rubric(judge_text), {})


if __name__ == "__main__":
    unittest.main()
