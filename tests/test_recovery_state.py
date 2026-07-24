from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CURRENT_STATE = REPO_ROOT / ".codex" / "CURRENT_STATE.md"
TASK_QUEUE = REPO_ROOT / ".codex" / "TASK_QUEUE.md"
LAST_VALIDATION = REPO_ROOT / ".codex" / "LAST_VALIDATION.json"
RESUME_INSTRUCTIONS = REPO_ROOT / ".codex" / "RESUME_INSTRUCTIONS.md"


def _markdown_section(document: str, heading: str) -> str:
    marker = f"## {heading}\n"
    _, separator, remainder = document.partition(marker)
    if not separator:
        raise AssertionError(f"missing Markdown section: {heading}")
    return remainder.split("\n## ", 1)[0]


def _task_states(document: str) -> dict[str, str]:
    return dict(
        re.findall(
            r"^## (ARA-\d+) - .+?\n\n- Status: `([A-Z_]+)`$",
            document,
            flags=re.MULTILINE,
        )
    )


def _named_fallback_shas(document: str) -> set[str]:
    sha = r"([0-9a-f]{7,40})"
    return {
        *re.findall(rf"(?is)Last externally verified fallback:\s*`?{sha}`?", document),
        *re.findall(
            rf"(?is)\buse\s+`?{sha}`?\s+as\s+the\s+conservative\s+exact\s+"
            r"externally\s+verified\s+fallback",
            document,
        ),
        *re.findall(
            rf"(?is)\b{sha}\b\s+is\s+the\s+exact\s+conservative\s+externally\s+"
            r"verified\s+fallback",
            document,
        ),
    }


def _invalid_finalization_bullets(remaining_steps: str, active_tasks: set[str]) -> list[str]:
    invalid: list[str] = []
    for bullet in re.split(r"\n(?=- )", remaining_steps):
        if not re.search(r"(?i)\b(commit|push|checkpoint|closeout)\b", bullet):
            continue
        referenced_tasks = set(re.findall(r"\bARA-\d+\b", bullet))
        if not active_tasks or referenced_tasks != active_tasks:
            invalid.append(bullet)
    return invalid


class RecoveryStateConsistencyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.current_state = CURRENT_STATE.read_text(encoding="utf-8")
        self.task_queue = TASK_QUEUE.read_text(encoding="utf-8")
        self.validation = json.loads(LAST_VALIDATION.read_text(encoding="utf-8"))
        self.resume_instructions = RESUME_INSTRUCTIONS.read_text(encoding="utf-8")

    def test_current_snapshot_uses_live_worktree_state(self) -> None:
        repository_state = _markdown_section(self.current_state, "Repository State")
        worktree_state = _markdown_section(self.current_state, "Live Worktree Interpretation")
        current_scope = f"{repository_state}\n{worktree_state}"

        self.assertIn("git status --short --branch", repository_state)
        self.assertNotIn("remain uncommitted", current_scope)
        self.assertNotRegex(current_scope, r"(?i)active ARA-\d+ worktree")

    def test_current_remaining_steps_do_not_request_recursive_closeout(self) -> None:
        remaining_steps = _markdown_section(self.current_state, "Remaining Steps")
        task_states = _task_states(self.task_queue)
        active_tasks = {task for task, status in task_states.items() if status == "IN_PROGRESS"}

        self.assertEqual(_invalid_finalization_bullets(remaining_steps, active_tasks), [])

    def test_recursive_closeout_classifier_rejects_unattributed_work(self) -> None:
        self.assertEqual(
            _invalid_finalization_bullets("- Create and push the recovery closeout.\n", set()),
            ["- Create and push the recovery closeout.\n"],
        )
        self.assertEqual(
            _invalid_finalization_bullets(
                "- Commit and push one verified checkpoint.\n",
                set(),
            ),
            ["- Commit and push one verified checkpoint.\n"],
        )
        self.assertEqual(
            _invalid_finalization_bullets(
                "- Finish ARA-028, commit, and push.\n",
                {"ARA-028"},
            ),
            [],
        )
        self.assertEqual(
            _invalid_finalization_bullets(
                "- Create and push the ARA-022 closeout.\n",
                {"ARA-028"},
            ),
            ["- Create and push the ARA-022 closeout.\n"],
        )

    def test_active_task_matches_queue(self) -> None:
        task_states = _task_states(self.task_queue)
        task_id_list = re.findall(r"^## (ARA-\d+) -", self.task_queue, flags=re.MULTILINE)
        task_ids = set(task_id_list)
        self.assertEqual(set(task_states), task_ids)
        self.assertEqual(len(task_states), len(task_id_list))
        active_tasks = sorted(
            task for task, status in task_states.items() if status == "IN_PROGRESS"
        )
        todo_tasks = sorted(task for task, status in task_states.items() if status == "TODO")
        repository_state = _markdown_section(self.current_state, "Repository State")
        active_line = next(
            line for line in repository_state.splitlines() if line.startswith("- Active task")
        )

        self.assertLessEqual(len(active_tasks), 1)
        if active_tasks:
            self.assertIn(active_tasks[0], active_line)
            self.assertNotIn("none", active_line.lower())
            self.assertIn(active_tasks[0], self.resume_instructions)
            self.assertNotIn(
                "There is no unblocked implementation task",
                self.resume_instructions,
            )
        else:
            self.assertIn("none", active_line.lower())
            if todo_tasks:
                self.assertNotIn(
                    "There is no unblocked implementation task",
                    self.resume_instructions,
                )
            else:
                self.assertIn(
                    "There is no unblocked implementation task",
                    self.resume_instructions,
                )

    def test_validation_has_one_external_fallback(self) -> None:
        self.assertEqual(self.validation["schema_version"], 1)
        self.assertEqual(
            self.validation["current_head"],
            {
                "ref": "HEAD",
                "resolution_argv": ["git", "rev-parse", "--verify", "HEAD"],
                "authoritative": True,
            },
        )
        self.assertEqual(self.validation["working_tree_source"], "live_git_status")

        fallback = self.validation["last_external_verification"]["commit"]
        self.assertRegex(fallback, r"^[0-9a-f]{40}$")
        self.assertEqual(self.validation["head_commit"], fallback)
        self.assertEqual(self.validation["last_known_stable_commit"], fallback)
        self.assertEqual(self.validation["state_recorded_against_commit"], fallback)

        current_fallbacks = _named_fallback_shas(
            _markdown_section(self.current_state, "Repository State")
        )
        resume_fallbacks = _named_fallback_shas(
            _markdown_section(
                self.resume_instructions,
                "4. Validate the active task before continuing",
            )
        )
        self.assertTrue(current_fallbacks)
        self.assertTrue(resume_fallbacks)
        for abbreviated_sha in current_fallbacks | resume_fallbacks:
            with self.subTest(abbreviated_sha=abbreviated_sha):
                self.assertTrue(fallback.startswith(abbreviated_sha))

        for note in self.validation["notes"]:
            for abbreviated_sha in _named_fallback_shas(note):
                with self.subTest(note=note, abbreviated_sha=abbreviated_sha):
                    self.assertTrue(fallback.startswith(abbreviated_sha))

    def test_fallback_extraction_requires_an_explicit_label(self) -> None:
        full_sha = "a" * 40
        self.assertEqual(
            _named_fallback_shas(f"Last externally verified fallback: `{full_sha}`"),
            {full_sha},
        )
        self.assertEqual(
            _named_fallback_shas(
                f"use `{full_sha}` as the conservative exact\nexternally verified fallback"
            ),
            {full_sha},
        )
        self.assertEqual(
            _named_fallback_shas("fallback semantics; unrelated closeout ca3a2e8 follows"),
            set(),
        )
        self.assertEqual(
            _named_fallback_shas("0aee55e is the exact conservative externally verified fallback"),
            {"0aee55e"},
        )


if __name__ == "__main__":
    unittest.main()
