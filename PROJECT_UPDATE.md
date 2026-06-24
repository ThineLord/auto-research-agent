# Phase 9 - Partial Next-Round Resume Safety

Date: 2026-06-24
Commit: 770d89fe50351a7908081ae2bfd61e89458b799e
Branch: master

## Goal

Make partial next-round resume behavior safer and more explicit while preserving completed rounds, legacy checkpoint compatibility, and existing research semantics.

## What Changed

Resume now inspects the next-round directory before continuing a run. Missing or empty next-round directories remain resumable, while non-empty next-round directories block resume with a clear fail-safe message that requires user action.

## Code

* Added next-round directory inspection and fail-safe resume blocking in `src/resume.py`.
* Recorded next-round resume safety metadata in runner resume metadata for checkpoint, run config, and summary propagation.
* Preserved completed round files and avoided automatic movement or deletion of partial next-round artifacts.

## UI

* Added partial next-round status to the Streamlit resume helper state.
* Updated resume wording to show next-round status, safety action, and privacy-safe paths.

## Tests

* Added resume tests for partial next-round detection and fail-safe blocking.
* Extended resume tests to verify completed rounds are preserved.
* Added UI helper coverage for partial next-round status display.

## Docs

* Updated README resume guidance.
* Updated `docs/USER_GUIDE.md`, `docs/DEVELOPER_GUIDE.md`, `docs/quickstart_zh.md`, and `docs/runbook_zh.md`.

## Validation

* `git diff --check`
* `.venv/bin/python -m src.main --help`
* `.venv/bin/python -m pytest tests/test_round_loop.py::RoundLoopTests::test_resume_starts_after_last_real_completed_round tests/test_round_loop.py::RoundLoopTests::test_resume_blocks_partial_next_round_without_overwriting tests/test_round_loop.py::RoundLoopTests::test_resume_preview_reports_missing_and_stale_checkpoints tests/test_ui_helpers.py::SharedUiBackendHelperTests::test_ui_progress_resume_and_output_helpers -q`
* `make check`

## Risks / Limitations

* The fail-safe behavior is conservative: users must manually inspect, move, or delete non-empty next-round directories before resuming.
* No automatic quarantine is performed, which avoids hidden file movement but leaves cleanup to the operator.

## Recommended Next Phase

Phase 10 - Documentation and release polish.

## Suggested Codex Prompt

Continue with Phase 10. Update documentation and release notes, preserve existing research semantics, validate with `git diff --check`, `.venv/bin/python -m src.main --help`, targeted documentation checks if applicable, and `make check`, then update `PROJECT_UPDATE.md`, commit, and push.
