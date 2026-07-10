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
- Committed the round-limit checkpoint state as `5c5bdc0`, pushed through the command-scoped proxy, and verified the exact remote SHA.

## 2026-07-10 - Atomic state and artifact replacement

- Reproduced the lack of a failure boundary around checkpoint replacement.
- Added `fsync` and `os.replace` fault injection that requires the previous checkpoint to remain valid and temp files to be cleaned.
- Routed JSON, score history, research state, memory, best output, round text, and exact text replacements through one same-directory atomic writer.
- Kept log append behavior unchanged and best effort.
- Related suites passed with `63 passed, 9 subtests passed`; full `make check` passed with `145 passed, 49 subtests passed`.
- Committed the fix as `7d226f8`.
- Committed state checkpoint `5ab7119`, pushed it, verified exact local/remote SHA equality, and confirmed all Python 3.10/3.13 push and PR checks passed.

## 2026-07-10 - Resume history integrity

- Reproduced resumed round 4 replacing both prior history arrays with only round 4, clearing best-round metadata, resetting cumulative runtime/streak state, and omitting previous-round context.
- Loaded run-local metrics as the primary history and used project score history only as a checkpoint-correlated legacy fallback.
- Preserved opaque legacy fields while requiring strictly increasing prior rounds and recursively consistent shared semantics across both histories.
- Failed before any run artifact write for malformed JSON, wrong types, duplicate/out-of-order/future rounds, cross-history conflicts, unsupported checkpoint best scores, or unresolved partial-history best metadata.
- Reconciled best score/round only from supported evidence, retained tied strict-improvement rounds, restored last successful agent and drafting-mode context, and kept cumulative runtime/analytics accurate.
- Made unsafe history and blocked resume previews return CLI status 2 while retaining run-lock cleanup.
- Added strict `start_round` and checkpoint `last_completed_round` validation before artifact creation.
- Focused resume/consumer validation passed with `70 passed, 23 subtests passed`; final `make check` passed with `153 passed, 67 subtests passed`.
- Independent read-only adversarial and code reviews reported no remaining confirmed P1/P2 defect in the tested resume-integrity matrix.
- Committed the implementation as `6d56d09`.
- Committed its recovery-state checkpoint as `b8b629b`, pushed both commits, and verified exact local/remote SHA equality.
- Updated draft PR 13 and confirmed Python 3.10/3.13 passed for both push and pull-request GitHub Actions triggers.

## 2026-07-10 - Checkpoint resume path containment

- Reproduced absolute, cross-project, traversal, relative, nested, container-root, and escaping-symlink checkpoint paths being accepted for resume.
- Reproduced direct runner overrides and future round symlinks writing run artifacts outside the selected project in temporary fixtures.
- Added `src/resume_safety.py` as the shared canonical boundary for CLI preview, runner defense-in-depth, and UI Resume state.
- Required an existing absolute per-run direct child of the selected project's resolved `runs/` storage root while preserving repository-generated legacy roots and configured runs-storage symlinks.
- Validated run config, legacy manifest, summary, metrics/history, previous-round context, and every planned/current round path before resume reads or writes.
- Rejected path traversal, invalid/non-file state, escaping links, malformed NUL paths, inaccessible directories/files, unsafe future rounds, and privacy-leaking I/O failures with generic blockers.
- Made the UI disable Resume for the same backend blockers and verified unsafe CLI resume exits 2 while releasing its run lock.
- Focused consumer regression passed with `80 passed, 43 subtests passed`; final `make check` passed with `165 passed, 87 subtests passed`.
- Independent bounded adversarial review found no remaining confirmed defect within the static ARA-012 scope.
- Committed the implementation, regression matrix, UI integration, translations, changelog, and public docs as `e47ba44`.
- Committed recovery state as `31db3f8`, pushed both commits, verified exact local/remote SHA equality, updated draft PR 13, and confirmed Python 3.10/3.13 passed for both push and pull-request triggers.

## 2026-07-10 - UI checkpoint artifact read containment

- Reproduced metadata, analytics, and output browsing following external checkpoint config/summary,
  summary metrics, external run roots, and run/round symlinks.
- Added a read-only canonical run-root validation mode while preserving writable resume semantics.
- Derived fixed run artifact names, rejected unsafe/non-regular config/summary/metrics/manifest and
  round leaves before reads, and returned unavailable entries without propagating unsafe paths.
- Restricted project-level score-history fallback to the no-`run_root` legacy layout after an
  independent adversarial review reproduced the remaining selected-run external read.
- Preserved safe legacy metadata, configured `runs/` storage symlinks, and read-only artifact viewing.
- Focused UI/resume/analytics/compare regression passed with `84 passed, 47 subtests passed`; final
  `make check` passed with `172 passed, 91 subtests passed`.
- Two independent read-only reviews reported no remaining actionable finding within ARA-021 after
  the score-history correction.
- Committed the implementation, tests, changelog, and public docs as `98ea4a3` and recovery state as
  `3624385`; pushed both, verified exact local/remote SHA equality, updated draft PR 13, and
  confirmed Python 3.10/3.13 passed for both push and pull-request triggers.

## 2026-07-11 - Owner-safe atomic run locking

- Reproduced malformed PID exceptions, two synchronized contenders both reporting success, and an
  old release deleting replacement-owner metadata.
- Replaced check/write/delete coordination with a long-held cross-process OS guard and an owner
  capability whose metadata includes token, PID, and guard device/inode identity.
- Added crash recovery without stale deletion, live legacy-owner preservation, malformed legacy
  recovery, static symlink/FIFO/directory rejection, safe bare-path behavior, and fork-child
  ownership protection.
- Hardened invalid UTF-8, oversized/deep JSON, oversized PID, POSIX permission, and Windows process
  liveness paths so diagnostic metadata cannot crash or destructively probe lock owners.
- Moved mock/client/agent construction inside lock-owning `try/finally` scopes and added exact stale
  metadata/guard recovery guidance.
- Added synchronized thread and four-process competition, live cross-process blocking, process
  crash, guard recreation, fork inheritance, metadata failure, legacy, replacement/repeat release,
  non-regular node, and constructor-failure regressions.
- Related runtime/UI/mock/round tests passed with `94 passed, 68 subtests passed`; final `make check`
  passed with `189 passed, 110 subtests passed`; the synchronized thread test passed 25 repeats.
- Multiple independent design/adversarial/platform/post-fix reviews reported green after all
  reproduced P1/P2 protocol gaps were corrected.
- Committed implementation, tests, ignore policy, changelog, and developer docs as `55e7287` and
  recovery state as `e93aa77`; pushed both and verified exact local/remote SHA equality.
- Updated draft PR 13 and confirmed Python 3.10/3.13 passed for both push and pull-request triggers.
