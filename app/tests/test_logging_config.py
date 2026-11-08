from __future__ import annotations

import json
import logging
import unittest

from src.logging_config import JsonLogFormatter


class LoggingConfigTests(unittest.TestCase):
    def test_json_log_formatter_emits_structured_fields(self) -> None:
        record = logging.getLogger("src.llm").makeRecord(
            "src.llm",
            logging.INFO,
            __file__,
            10,
            "llm_request_start",
            (),
            None,
            extra={
                "event": "llm_request_start",
                "agent_name": "judge",
                "timeout_seconds": 120,
            },
        )

        payload = json.loads(JsonLogFormatter().format(record))

        self.assertEqual(payload["level"], "INFO")
        self.assertEqual(payload["logger"], "src.llm")
        self.assertEqual(payload["message"], "llm_request_start")
        self.assertEqual(payload["event"], "llm_request_start")
        self.assertEqual(payload["agent_name"], "judge")
        self.assertEqual(payload["timeout_seconds"], 120)
        self.assertIn("timestamp", payload)


if __name__ == "__main__":
    unittest.main()
