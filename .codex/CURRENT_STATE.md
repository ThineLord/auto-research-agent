# Codex Current State

Updated: 2026-07-10 (Asia/Shanghai)

## Repository State

- Current goal: stable remote checkpoint reached; resume with `ARA-010` (preserve run history across resume).
- Current branch: `codex/sol-autonomous-hardening`
- Current HEAD commit at snapshot start: `5ab7119b925b7c9c1281c7d942c9da6b0b410463` (use `git rev-parse HEAD` after the state-only closeout commit)
- Last known stable commit: `5ab7119b925b7c9c1281c7d942c9da6b0b410463` (`make check`, remote SHA, and GitHub Actions verified)
- Active task: none; next task is `ARA-010` in `.codex/TASK_QUEUE.md`
- Uncommitted changes: expected none after this state-only closeout commit; inspect any difference before resuming.

## Modified Files

- `.codex/CURRENT_STATE.md`
- `.codex/COMPLETED.md`
- `.codex/KNOWN_ISSUES.md`
- `.codex/LAST_VALIDATION.json`
- `.codex/RESUME_INSTRUCTIONS.md`

## Completed Steps

- Confirmed repository root, branch, remotes, recent history, upstream, and ahead/behind state.
- Fetched `origin`; `master` matched `origin/master` at `a94c4e2` before branching.
- Confirmed there is no active merge, rebase, cherry-pick, revert, sequencer, or stash.
- Identified a stale invalid `.git/REBASE_HEAD` file; no active rebase directories exist, so it was left untouched.
- Created `codex/sol-autonomous-hardening` from the synchronized `master` head.
- Reviewed the tracked workflow, CI, packaging, release, test, and maintenance documentation.
- Classified ignored project runs, logs, local configuration, and research artifacts as out of scope for cleanup or commit.
- Ran the current canonical baseline: `make check` passed with 137 tests and 43 subtests.
- Reproduced the single-path compare CLI mismatch with exit code 0 and `run_count: 1`.
- Added a regression test that failed before the fix and passed after it.
- Added CLI-boundary validation while preserving the single-run internal helper behavior.
- Verified the two-or-more path with a three-path parser test and a two-path CLI smoke.
- Committed recovery state as `a1fec51` and the compare-runs fix as `033ed01`.
- Pushed `codex/sol-autonomous-hardening` and verified the remote SHA matches local HEAD.
- Opened draft PR 13 for continued maintenance checkpoints.
- Reproduced exact-key leakage in provider events and formatted exception tracebacks.
- Added failing regression coverage for explicit and custom-environment credentials.
- Redacted known configured secrets before event persistence and before constructing displayed exception chains.
- Committed the credential-redaction fix as `bb26c6d`.
- Committed the security state checkpoint as `c8d6c17`, pushed both commits, and updated draft PR 13.
- Reproduced failed provider rounds and invalid Judge output replacing a trusted best file.
- Added focused regression coverage for both failure classes.
- Reused the existing successful-round predicate to gate best-score and best-output updates.
- Committed the best-output integrity fix as `198f9ec`.
- Committed the integrity state checkpoint as `7e9a1f5`, pushed both commits, and updated draft PR 13.
- Reproduced zero and negative CLI values being silently normalized to one round.
- Added failing parser and direct-runner tests before implementation.
- Added positive-integer argument validation and a runner guard before any run artifact creation.
- Committed the round-limit validation fix as `e6bffa6`.
- Committed the round-limit state checkpoint as `5c5bdc0`, pushed both commits, and updated the remote branch.
- Added failing fault-injection coverage for `fsync` and atomic-replace failures.
- Centralized replacement writes through same-directory temp files with flush, fsync, atomic replace, and cleanup.
- Preserved append-only best-effort logging behavior outside the atomic replacement helper.
- Committed the atomic state-write fix as `7d226f8`.
- Committed state checkpoint `5ab7119`, pushed both commits, verified local/remote equality, and confirmed all Python 3.10/3.13 push and PR checks passed.

## Remaining Steps

- Start `ARA-010` by first reproducing resume history loss against the preserved remote checkpoint.
- Restore existing round metrics, score history, best-round metadata, and prior-round context without altering completed round files.
- Keep `ARA-012` path-containment work separate from the history-preservation change.

## Test Status

- Current branch validation: `make check` passed at 2026-07-10T16:27:39+08:00.
- Results: Ruff format passed (50 files), Ruff lint passed, import smoke passed, pytest passed (`139 passed, 43 subtests passed`).
- Compare-runs targeted validation: module suite passed (`7 passed`).
- Single-path CLI reproduction after the fix: rejected with exit code 2 and the expected argument error.
- Two-path CLI smoke after the fix: exit code 0 and `run_count: 2`.
- GitHub sync: local and remote `033ed01638965d873a08da05d3ad02dc3529b162` match; PR 13 is draft.
- Credential-redaction targeted suite: `tests/test_llm.py` passed (`11 passed`).
- Full regression after the security fix: `make check` passed (`141 passed, 43 subtests passed`).
- `git diff --check` passed.
- GitHub sync: local and remote `7e9a1f5839d75a2056810a619919886560bddb97` match; PR 13 is draft and updated.
- Round-limit target suites: `22 passed, 7 subtests passed`.
- Zero and negative provider-free CLI smoke paths both exited 2 before startup.
- Full regression after the round-limit fix: `make check` passed (`144 passed, 47 subtests passed`).
- `git diff --check` passed and no silent round-limit clamp remains.
- GitHub sync: local and remote `5c5bdc0a22c47b466356be8005b9b27882622f7f` match.
- Atomic-write related regression: `63 passed, 9 subtests passed`.
- Fault injection preserved the prior JSON and cleaned temp files for both `fsync` and `replace` failures.
- Full regression after the atomic-write fix: `make check` passed (`145 passed, 49 subtests passed`).
- `git diff --check` passed and storage replacement paths no longer call `Path.write_text` directly.
- GitHub Actions: Python 3.10 and Python 3.13 both passed for push and pull-request triggers on the remote checkpoint.
- GitHub sync: local and remote `5ab7119b925b7c9c1281c7d942c9da6b0b410463` match; PR 13 is draft and updated.
- Runner target validation: `17 passed, 3 subtests passed`.
- Full regression after the integrity fix: `make check` passed (`142 passed, 43 subtests passed`).
- `git diff --check` passed.
- Provider-backed tests: not planned for this checkpoint; no paid or network model calls are needed.

## Recent Failed Command

- `git show --no-patch --format='%H %P %s' REBASE_HEAD` failed with `fatal: bad object REBASE_HEAD` because the stale file references an unavailable object. This is not an active Git operation.
- The first unproxied push hung without output and was interrupted safely; the command-scoped proxy retry succeeded.
- One post-push GitHub API verification hit a TLS handshake timeout; scoped `git ls-remote` independently verified the exact remote SHA.

## Next Command

```bash
git status --short --branch
```

## Interruption Recovery

Read `.codex/RESUME_INSTRUCTIONS.md`, then compare this file with `git status --short --branch` and `git log --oneline -n 10`. Do not touch ignored runtime artifacts or the local `config.yaml`.

## Current Risks And Prohibitions

- Do not delete or rewrite ignored experiment artifacts, local logs, or private configuration.
- Do not remove the stale `.git/REBASE_HEAD` without an explicit cleanup decision; it is harmless while no rebase directory exists.
- Do not run paid-provider workflows without credential presence checks, a dry run, and an explicit cost cap.
- Do not change prompts, scoring semantics, provider behavior, benchmark results, or artifact interpretation as part of a maintenance-only fix.
- Do not stage with `git add -A`; stage only reviewed paths.
