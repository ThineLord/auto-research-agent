# Completed Maintenance Work

## 2026-07-10 - Startup and recovery audit

- Confirmed the checkout root and `origin` URL.
- Confirmed `master` and `origin/master` were synchronized at `a94c4e2` after fetching.
- Reviewed the latest 15 commits and the existing hardening release history.
- Confirmed a clean tracked worktree, no stash, and no active merge/rebase/cherry-pick/revert sequence.
- Preserved all ignored local configuration, generated runs, logs, reports, and research artifacts.
- Created the dedicated branch `codex/sol-autonomous-hardening`.
- Reviewed `README.md`, `Makefile`, `pyproject.toml`, CI configuration, developer guidance, changelog, release review, tests, and ignore policy.
- Established the tracked `.codex/` recovery system requested for autonomous maintenance.

Validation and implementation outcomes will be appended only after they are actually verified.

## 2026-07-10 - Provider-free baseline validation

- Ran `make check` on `codex/sol-autonomous-hardening` at commit `a94c4e2`.
- Ruff formatting check passed for 50 files.
- Ruff lint passed.
- Import smoke passed for all listed `src` modules and `ui.app`.
- Pytest passed with `137 passed, 43 subtests passed in 0.47s`.
- No baseline failures were found.

## 2026-07-10 - Compare-runs CLI arity contract

- Reproduced the documented mismatch: one run directory returned exit code 0 and `run_count: 1`.
- Added a regression test that failed before the fix because no `SystemExit` was raised.
- Added an argparse boundary check requiring at least two run directories.
- Preserved the lower-level one-run helper behavior used by compatibility and metadata tests.
- Verified one path exits 2 with a clear error, while two and three paths remain accepted.
- Targeted suite passed with `7 passed`; full `make check` passed with `139 passed, 43 subtests passed`.

## 2026-07-10 - First published maintenance checkpoint

- Committed recovery state as `a1fec51`.
- Committed the compare-runs CLI fix as `033ed01`.
- Pushed `codex/sol-autonomous-hardening`; remote HEAD was verified as `033ed01638965d873a08da05d3ad02dc3529b162`.
- Opened draft PR 13 for continued independently validated checkpoints.
- The initial unproxied HTTPS push was safely interrupted after hanging; a command-scoped local proxy retry succeeded without changing global Git configuration.

## 2026-07-10 - Provider credential redaction

- Reproduced an arbitrary configured key in `provider_events.jsonl` when a fake upstream error echoed it.
- Confirmed the same raw provider exception was visible through a standard formatted traceback cause chain.
- Added regression tests for an explicit key and a custom environment-variable key.
- Extended provider-message redaction to replace exact configured secrets before pattern-based masking.
- Rebuilt outward exception chains from sanitized diagnostic messages while preserving public error types and classifications.
- Targeted LLM tests passed with `11 passed`; full `make check` passed with `141 passed, 43 subtests passed`.
- Committed the fix as `bb26c6d`.
- Committed the security checkpoint state as `c8d6c17`, pushed through the command-scoped proxy, verified the exact remote SHA, and updated draft PR 13.

## 2026-07-10 - Best-output integrity on failed rounds

- Reproduced a provider review failure overwriting trusted prior content with `[REVISE SKIPPED]` because synthetic score 0 exceeded the `-1` sentinel.
- Added a failing regression assertion for provider-stage failure and coverage for a Judge output with no numeric score.
- Required a round to have no agent errors and a parsed score before it can improve best score/output.
- Preserved failure round artifacts, error classifications, stop evidence, score history, and round metrics.
- Runner suite passed with `17 passed, 3 subtests passed`; full `make check` passed with `142 passed, 43 subtests passed`.
- Committed the fix as `198f9ec`.
- Committed the integrity checkpoint state as `7e9a1f5`, pushed through the command-scoped proxy, verified the exact remote SHA, and updated draft PR 13.

## 2026-07-10 - Explicit positive round limits

- Reproduced `--max-rounds 0` and negative values being silently coerced to one provider-capable round.
- Reproduced direct non-positive runner calls generating misleading zero-round completion artifacts.
- Added parser tests for zero/negative values and a runner fault-boundary test for no agent calls or run artifacts.
- Added a positive-integer argparse type and a pre-artifact runner `ValueError` guard; removed silent clamps.
- Target suites passed with `22 passed, 7 subtests passed`; full `make check` passed with `144 passed, 47 subtests passed`.
- Committed the fix as `e6bffa6`.
