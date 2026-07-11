# Codex Current State

Updated: 2026-07-11 (Asia/Shanghai)

## Repository State

- Current goal: remove confirmed tracked personal-path fragments and add a deterministic tracked-file
  privacy/safety gate without changing historical findings (`ARA-016`).
- Current branch: `codex/sol-autonomous-hardening`
- Current HEAD at state snapshot: `2b6523cda3d7a7943644692e276b6fdc7270573c`
- Last known stable commit: `2b6523cda3d7a7943644692e276b6fdc7270573c` (locally validated
  implementation commit; recovery checkpoint, remote push, and GitHub CI are pending)
- Active task: ARA-016 is `IN_PROGRESS`; implementation commit `2b6523c` is locally validated after
  focused/full tests and blocker-free independent review. Recovery checkpoint, push, PR update, and
  remote CI verification remain. ARA-004 is separately blocked.
- Uncommitted changes: yes; recovery metadata only.

## Modified Files

- `.codex/CURRENT_STATE.md`
- `.codex/TASK_QUEUE.md`
- `.codex/DECISIONS.md`
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
- Reproduced resume truncating both history files to the newly completed round, losing best-round metadata and previous-round context.
- Added fail-before-write validation for malformed, divergent, misattributed, or internally inconsistent histories and best-score metadata.
- Preserved prior history records byte-semantically, cumulative aggregates, best score/round, no-improvement state, last successful agent, and drafting-mode context.
- Added strict round-number validation and nonzero CLI status for any blocked resume preview/history condition.
- Verified normal, legacy fallback, partial-history, stop-before-round, stale/outlier metadata, recursive JSON-conflict, and analytics/compare paths.
- Committed the implementation, tests, and docs as `6d56d09`.
- Committed the ARA-010 recovery-state checkpoint as `b8b629b`, pushed both commits, and verified the local, remote-tracking, and GitHub branch SHAs match.
- Updated draft PR 13 with the resume-integrity scope and evidence.
- Verified all Python 3.10 and Python 3.13 GitHub Actions jobs passed for both push and pull-request triggers.
- Reproduced checkpoint roots escaping to arbitrary/cross-project paths and direct runner overrides writing outside the selected project.
- Added shared canonical root, round, state-artifact, accessibility, and privacy-safe error checks before resume inspection or writes.
- Preflighted every planned resume round and rechecked each current round, including future-round, previous-context, manifest, NUL, permission, and symlink cases.
- Reused the backend preview in the UI so unsafe checkpoints disable Resume; verified CLI exit status 2 and run-lock release.
- Preserved canonical legacy absolute roots and user-configured resolved `runs/` storage symlinks.
- Committed the implementation, tests, and public docs as `e47ba44`.
- Committed the ARA-012 recovery-state checkpoint as `31db3f8`, pushed both commits, and verified local, remote-tracking, and GitHub branch SHAs match.
- Updated draft PR 13 with the path boundary, validation matrix, and explicitly queued residual risks.
- Verified all Python 3.10 and Python 3.13 GitHub Actions jobs passed for both push and pull-request triggers.
- Reproduced UI metadata, analytics, and output-catalog reads from external checkpoint config,
  summary, metrics, run-root, and latest-round references; the initial focused regression failed
  in all three expected cases.
- Added a read-only canonical run-root validator while preserving the resume runner's read/write
  requirement and configured `runs/` storage symlink compatibility.
- Made UI run-local consumers ignore redundant path fields, derive fixed artifact names, reject
  unsafe/non-regular config/summary/metrics/manifest and round-output leaves before reads, and
  return partial/unavailable state without propagating unsafe catalog paths.
- Added guarded no-read, external-root, checkpoint/summary redirect, config/summary/metrics/manifest
  symlink, non-regular file, latest-round link, configured-storage, and read-only access coverage.
- Focused UI tests passed (`35 passed, 4 subtests passed`); UI/resume/analytics/compare regression
  passed (`83 passed, 47 subtests passed`). Ruff checks and `git diff --check` passed.
- Independent post-fix review reproduced one remaining selected-run read through project-level
  `score_history.json`; added a no-read regression and limited that fallback to no-`run_root`
  legacy projects.
- Re-ran the focused consumer suite (`84 passed, 47 subtests passed`) and final `make check`
  (`172 passed, 91 subtests passed`).
- Independent adversarial re-review reported green across selected, invalid, and legacy run scopes.
- Staged scans found no personal absolute path, credential pattern, or private-key material.
- Committed the ARA-021 implementation, tests, changelog, and public docs as `98ea4a3`.
- Committed recovery state as `3624385`, pushed both commits, and verified local,
  remote-tracking, and GitHub branch SHA equality.
- Updated draft PR 13 and confirmed all four Python 3.10/3.13 push and pull-request checks passed.
- Pushed final ARA-021 verified-state closeout `538d0be`, verified exact remote SHA equality, and
  confirmed all four Python 3.10/3.13 push and pull-request checks passed again.
- Reproduced malformed PID exceptions, two simultaneous acquisition successes, and an old release
  deleting replacement-owner metadata before implementing ARA-013.
- Replaced check/write/delete locking with a long-held cross-process OS guard, per-acquisition
  owner capability, atomic metadata replacement, guard device/inode provenance, and owner-checked
  release. Crash recovery now relies on kernel lock release instead of racy stale deletion.
- Moved the persistent guard to project-root `active_run.guard`, added its exact ignore rule, and
  rejected static symlink/FIFO/directory guards and metadata without following them.
- Hardened malformed metadata for invalid UTF-8, oversized/deep JSON, invalid/oversized PID values,
  POSIX permission probes, and non-destructive Windows process liveness checks.
- Prevented a fork child from unlocking its parent, prevented a recreated guard inode from
  displacing a live owner, and made bare paths fail closed while preserving path string/fspath use.
- Moved mock, client, and agent construction inside the lock-owning `try/finally` boundary.
- Added synchronized thread and multi-process contention, process crash, legacy live/dead,
  non-regular node, metadata failure, replacement/repeated release, fork, and constructor-failure
  regressions.
- Related runtime/UI/mock/round suites passed (`94 passed, 68 subtests passed`); the synchronized
  thread race passed 25 consecutive executions.
- Independent design, compatibility, adversarial, platform, and post-fix reviews reproduced interim
  gaps; all reported P1/P2 implementation issues were corrected, and the platform re-review is green.
- Final `make check` passed with Ruff format/lint, import smoke, and pytest (`189 passed, 110
  subtests passed`). Staged diff and sensitive-pattern scans passed.
- Committed the owner-safe lock implementation, regression matrix, ignore policy, changelog, and
  developer documentation as `55e7287`.
- Committed recovery state as `e93aa77`, pushed both commits, and verified exact local,
  remote-tracking, and GitHub branch SHA equality.
- Updated draft PR 13; all four Python 3.10/3.13 push and pull-request checks passed.
- Pushed the final ARA-013 state-only closeout as `4269056`, verified exact remote SHA equality,
  updated draft PR 13, and confirmed all four Python 3.10/3.13 checks passed again.
- Marked ARA-017 in progress and started parallel read-only CLI return-path and regression-matrix
  audits from a clean, synchronized branch.
- Reproduced module, editable console, and isolated missing-config/project failures printing errors
  while returning status 0; the success controls remained status 0 and argparse/resume refusals 2.
- Replaced every handled config/project/provider/lock startup return with status 2 and made explicit
  cloud discovery failure status 1, while preserving help, analysis, and profile fallback success.
- Normalized unreadable/non-UTF-8 config and task input into privacy-safe startup errors.
- Hardened tolerant checkpoint/cloud-cache JSON reads for invalid UTF-8, oversized integers, deep
  nesting, invalid top-level or record schema, non-finite/negative/oversized cached numbers, and
  missing/unknown fields without breaking valid cached defaults.
- Added an iterative resume-history nesting limit so semantic comparison and later persistence
  cannot overflow after parsing a deeply nested but otherwise valid JSON history.
- Added subprocess and direct-main coverage across both entrypoints, config/project/provider/lock,
  cloud discovery/profile, malformed resume/history/cache data, constructor boundaries, and success
  controls. Direct interrupt process status remains separately queued as ARA-023.
- Independent pre-fix and post-fix audits reproduced decoding, parser, schema, numeric overflow, and
  depth gaps; the final delta-only review reported green.
- Final `make check` passed with Ruff format/lint, import smoke, and pytest (`203 passed, 128
  subtests passed`). Focused startup/input/cache/resume regression passed (`103 passed, 103
  subtests passed`).
- `git diff --check`, staged diff checks, and staged personal-path/credential/private-key scans passed.
- Committed implementation, tests, changelog, and developer documentation as `8845adf`.
- Committed recovery state as `a513e4d`, pushed both commits, and verified exact local,
  remote-tracking, and GitHub branch SHA equality.
- Updated draft PR 13; all four Python 3.10/3.13 push and pull-request checks passed.
- Confirmed the installed `google-genai 2.7.0` public Client API accepts client-wide
  `http_options`, and its `timeout` value is milliseconds. A provider-free construction smoke
  preserved `37000` for a configured 37-second timeout.
- Reproduced all three Gemini credential branches omitting timeout before the fix; the new focused
  assertions and timeout-classification checks failed for the expected reasons.
- Passed `http_options={"timeout": timeout_seconds * 1000}` through explicit-key, custom-environment,
  and SDK-default credential paths without changing generation content or configuration.
- Classified transport timeouts as the privacy-safe `timeout` error while preserving the existing
  retry policy: native timeout/HTTP 408 remain non-retrying and HTTP 504 retains its existing 5xx
  retryability.
- Independent review found a generic `timeout` option error could be misclassified; narrowed the
  text heuristic to explicit `timed out` wording and added a negative regression.
- Replaced arbitrary timeout-like exception-name substring matching with exact timeout base-class
  matching after the final adversarial review reproduced misleading configuration-class names.
- Final focused regression passed with `46 passed, 44 subtests passed`; final `make check` passed
  with Ruff format/lint, import smoke, and pytest (`206 passed, 134 subtests passed`).
- Independent final delta-only review reported green, and the scoped staged path/key/private-key
  scan passed.
- Committed implementation, tests, and changelog as `817b8a1`.
- Committed recovery state as `be37216`, pushed both commits, and verified exact local,
  remote-tracking, and GitHub branch SHA equality.
- Updated draft PR 13 after bounded GitHub API retries; all four Python 3.10/3.13 push and
  pull-request checks passed, and the PR remains open, draft, and mergeable.
- Exported clean HEAD and independently built wheel and sdist with isolated PEP 517 tooling.
  Wheel/module and sdist/module/console `--help` controls returned 0 without source-tree imports.
- Verified the wheel contains only package modules plus distribution metadata and the sdist adds
  tests/basic metadata; both omit `config.example.yaml`, prompts, example project, UI, and scripts.
- Reproduced wheel and sdist console/module mock startup exiting 2 with
  `Config file not found: config.example.yaml` in empty neutral working directories before project
  or provider work; the safe reproduction wrote no artifacts.
- Confirmed the root cause is a combined source/resource/workspace root: installed `src/cli.py`
  resolves its package parent as `site-packages`, while runtime requires immutable repository assets
  and writable project output.
- Scoped the safe implementation to bundled public config/prompts/example assets, an
  `importlib.resources` resolver, CWD as installed writable workspace, and mock-only example seeding.
  Source/editable behavior, provider semantics, prompt bytes, UI/scripts distribution, versions,
  licenses, dependencies, and other projects remain unchanged/out of scope.
- Committed and pushed the audit/blocker recovery checkpoint as `89e95bf`, verified exact local,
  remote-tracking, and GitHub SHA equality, updated draft PR 13, and confirmed Python 3.10/3.13
  passed for both push and pull-request workflows.
- Committed and pushed the verified ARA-004 audit-state closeout as `3d77729`; exact remote SHA and
  all four Python 3.10/3.13 push/pull-request jobs passed. Draft PR 13 points at this clean HEAD.
- Enumerated 89 tracked blobs without opening ignored artifacts; the only confirmed privacy hits
  were four historical local-account fragments in two tracked reports, with no high-confidence
  provider token or private-key hit.
- Added an initially failing scanner regression and then a stdlib-only byte scanner for the tracked
  worktree and complete stage-0 index. Findings expose only relative path, line, and category.
- Covered partial staging, untracked files, NUL/invalid UTF-8 content, static and parent-directory
  symlinks, missing tracked files, operational errors, safe placeholders, and provider/key shapes.
- Independent review reproduced an outside-repository read through a replaced symlinked parent;
  secure `dir_fd`/no-follow traversal now blocks it. A second review proved the portable fallback
  retained a swap race, so unsupported platforms now fail closed and have dedicated regression.
- Reworded the four historical findings so the account is explicitly redacted in the report without
  pretending that the redaction placeholder was the original scan input or changing conclusions.
- Added `make repo-safety`, wired worktree/index/self-test checks into `make check` and CI, and
  documented the tracked-only, ignored-artifact, symlink, and privacy-safe output boundaries.
- Final independent quality review confirmed the no-follow path walk, unsupported-platform
  fail-closed behavior, staged-index path, tests, and local/CI/documentation wiring with no blocker.
- Committed the reviewed implementation, tests, report redaction, Make/CI wiring, changelog, and
  public documentation as `2b6523c` with no unrelated or ignored artifacts.

## Remaining Steps

- Update and commit recovery metadata, push both commits, verify exact remote SHA, update draft PR 13,
  and verify all Python 3.10/3.13 push and pull-request jobs.

## Test Status

- ARA-016 focused regression: Ruff lint passed and `tests/test_repo_safety.py` passed (`11 passed`).
- Scanner controls: self-test, tracked worktree, and full staged-index scans passed with 91 tracked
  files, including the scanner and test; no tracked binary/NUL file or gitlink is currently present.
- Final local ARA-016 `make check`: Ruff format passed (54 files), Ruff lint passed, import smoke
  passed, both safety scans passed, and pytest passed (`217 passed, 134 subtests passed in 2.55s`).
- `git diff --check` and staged diff checks passed. Native Python 3.10 execution remains for CI;
  the current local environment is Python 3.13.14.
- Python 3.10 AST parsing passed for the scanner and its test module. Final independent review reran
  the 11 focused tests plus self/worktree/staged scans and reported no release blocker.
- Real provider smoke was not run because this task only changes repository validation and report
  wording; it makes no provider, prompt, metric, experiment, or runtime behavior change.
- Final ARA-015 focused regression: `46 passed, 44 subtests passed`; focused Ruff lint and
  `git diff --check` passed.
- Final ARA-015 `make check`: Ruff format passed (52 files), Ruff lint passed, import smoke passed,
  and pytest passed (`206 passed, 134 subtests passed in 2.18s`).
- Provider-free SDK construction smoke: `google-genai 2.7.0` accepted
  `http_options={"timeout": 37000}` without making a request.
- Independent compatibility review: three credential branches, Python 3.10 syntax parsing,
  HTTP 408/504 policy, and model/prompt/generation-config preservation passed. Native Python 3.10
  execution remains for GitHub Actions.
- Final ARA-015 state-only closeout `e202dfb`: exact remote SHA verified; Python 3.10/3.13 passed
  for both push and pull-request workflows.
- ARA-004 safe isolated build inventory: wheel/sdist built successfully; four console/module help
  controls passed, and four mock controls failed at missing bundled config with status 2. Neutral
  workspaces remained empty.
- ARA-004 implementation tests were not started because the verified fix exceeds 30 minutes and
  needs an explicit checkpoint approval.
- ARA-004 audit checkpoint `89e95bf`: all four Python 3.10/3.13 push/pull-request CI jobs passed.
- ARA-004 verified-state closeout `3d77729`: all four Python 3.10/3.13 push/pull-request CI jobs
  passed; its Node.js 20 action deprecation annotation remains deferred under ARA-019.
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
- ARA-010 focused resume/consumer regression passed (`70 passed, 23 subtests passed`).
- Final ARA-010 `make check` passed: Ruff format (50 files), Ruff lint, import smoke, and pytest (`153 passed, 67 subtests passed`).
- Independent adversarial and code reviews reproduced the pre-fix failures, challenged cross-artifact conflicts, and reported no remaining confirmed P1/P2 issue after the final corrections.
- Final `git diff --check` and staged sensitive-pattern scans passed.
- GitHub Actions for the pushed ARA-010 checkpoint: Python 3.10 and Python 3.13 passed for both push and pull-request triggers.
- GitHub sync: local, remote-tracking, and GitHub branch SHAs match at `b8b629baa728ec30279bce55bb86e039ef31c2c3`; draft PR 13 is updated and mergeable.
- ARA-012 focused resume/UI/config/analytics/compare regression passed (`80 passed, 43 subtests passed`).
- Final ARA-012 `make check` passed: Ruff format (51 files), Ruff lint, import smoke including `src.resume_safety`/`ui.app`, and pytest (`165 passed, 87 subtests passed`).
- CLI unsafe-resume smoke exited 2 and removed the run lock without agent calls, run-log creation, or external writes.
- Independent bounded adversarial review confirmed canonical/legacy, cross-project/traversal/relative, root/round/state symlink, future-round, NUL, access-permission, no-write, UI, and CLI behavior; no confirmed issue remains in the static ARA-012 scope.
- Final `git diff --check`, staged diff check, and personal-path/credential/private-key scans passed.
- GitHub Actions for the pushed ARA-012 checkpoint: Python 3.10 and Python 3.13 passed for both push and pull-request triggers.
- GitHub sync: local, remote-tracking, and GitHub branch SHAs match at `31db3f8286b3cbe0874d6ab0e938bd496e5d3730`; draft PR 13 is updated and mergeable.
- ARA-021 pre-fix focused reproduction: `3 failed, 29 deselected`; external provider/model and
  run paths reached metadata/dashboard/catalog as expected before the fix.
- ARA-021 focused UI regression after final correction: `36 passed, 4 subtests passed`.
- ARA-021 UI/resume/analytics/compare regression: `84 passed, 47 subtests passed`.
- Final ARA-021 `make check`: Ruff format (51 files), Ruff lint, import smoke, and pytest
  (`172 passed, 91 subtests passed`).
- Independent post-fix re-review: green after the project score-history correction.
- `git diff --check`, staged diff check, and staged personal-path/credential/private-key scans passed.
- GitHub Actions for ARA-021: Python 3.10 and Python 3.13 passed for both push and pull-request triggers.
- GitHub sync: local, remote-tracking, and GitHub branch SHAs match at
  `3624385fe368c4593b452418e4b000463933a87c`; draft PR 13 is updated and mergeable.
- Final ARA-021 state-only closeout: local and remote match at
  `538d0bef9d75f8794fe2793bba89e16e9eb16e4f`; all four GitHub checks passed.
- ARA-013 pre-fix focused regression: `3 failed, 1 passed, 35 deselected`; each failure matched a
  reproduced acquisition/ownership defect.
- Final related ARA-013 module regression before the full gate: `94 passed, 68 subtests passed`.
- PID/lock focused matrix: `17 passed, 17 subtests passed`.
- Final ARA-013 `make check`: Ruff format (51 files), Ruff lint, import smoke, and pytest
  (`189 passed, 110 subtests passed in 0.87s`).
- Ruff format/lint, `git diff --check`, staged diff check, and staged personal-path/credential/
  private-key scans passed on the committed implementation.
- Independent final adversarial and platform re-review: green; native Windows was not available,
  so Windows-specific process probes were covered by mocked/static tests.
- Provider-backed tests: not planned; locking and constructor cleanup require no model/network call.
- GitHub Actions for pushed ARA-013 checkpoint `e93aa77`: Python 3.10 and Python 3.13 passed for
  both push and pull-request triggers.
- GitHub sync: local, remote-tracking, and GitHub branch SHAs match at
  `e93aa773daafaae690a3e25737b04c27752e5519`; draft PR 13 is updated and mergeable.
- ARA-017 pre-fix process probes: missing/invalid config, invalid/missing project, provider
  prerequisites, and all three lock entrypoints printed a diagnostic but returned status 0.
- Final ARA-017 focused startup/input/cache/resume regression: `103 passed, 103 subtests passed`.
- Final ARA-017 `make check`: Ruff format (52 files), Ruff lint, import smoke, and pytest
  (`203 passed, 128 subtests passed in 2.18s`).
- Process smoke after the fix: module and editable console invalid-project paths returned 2;
  isolated missing/invalid UTF-8/huge/deep config and invalid task/checkpoint paths returned 2
  without traceback; `--help` and provider-free analysis returned 0.
- Malformed cloud caches returned empty safe records for invalid UTF-8, huge/deep JSON, wrong
  top-level/record types, non-finite/negative/over-64-bit numeric values, and the valid-cache
  compatibility controls passed.
- Independent final delta-only review: green; no remaining non-interrupt ARA-017 startup
  false-success or traceback gap was confirmed.
- Real provider smoke: not run; all changes are provider-free startup/input boundary behavior.
- GitHub Actions for pushed ARA-017 checkpoint `a513e4d`: Python 3.10 and Python 3.13 passed for
  both push and pull-request triggers.
- GitHub sync: local, remote-tracking, and GitHub branch SHAs match at
  `a513e4dfd4bb99f6b24a12195c0c40bf55feb274`; draft PR 13 is updated and mergeable.

## Recent Failed Command

- `git show --no-patch --format='%H %P %s' REBASE_HEAD` failed with `fatal: bad object REBASE_HEAD` because the stale file references an unavailable object. This is not an active Git operation.
- The first unproxied push hung without output and was interrupted safely; the command-scoped proxy retry succeeded.
- One post-push GitHub API verification hit a TLS handshake timeout; scoped `git ls-remote` independently verified the exact remote SHA.
- The new resume-integrity regression initially failed because both histories were truncated to the new round; this was the expected pre-fix reproduction.
- An interim `make check` stopped at Ruff formatting while implementation was still in progress; formatting was applied and the final full gate passed.
- The initial ARA-012 regression accepted absolute, traversal, symlink, and `runs/` container roots and allowed a direct runner override to write externally; these were the expected pre-fix failures.
- Interim adversarial probes found future-round symlink, malformed NUL, unreadable directory, legacy-manifest, non-file artifact, and permission-error gaps; each received a focused regression before the final full gate.
- The initial ARA-021 focused regression failed all three new tests by reading an external root,
  explicit checkpoint config/summary references, and a config/round symlink; this was the expected
  pre-fix reproduction.
- The first post-fix focused run had one path-equality failure because macOS canonicalized `/var`
  to `/private/var`; the assertion now compares canonical paths and the security behavior passed.
- An interim Ruff format check requested formatting in `ui/app.py`; formatting was applied and the
  subsequent focused Ruff check passed.
- The first independent ARA-021 review found selected runs still loading project score history; a
  dedicated no-read test failed before the correction and passed afterward. The second review was green.
- Initial ARA-013 tests failed on malformed PID, dual acquisition, and replacement deletion as
  expected. Interim reviews then found invalid bytes/deep JSON, oversized PID, fork release,
  disposable/symlink guard, POSIX EPERM, and Windows probe gaps; each now has code and regression
  coverage.
- The first post-push `fetch` and one independent `ls-remote` verification hit transient GitHub TLS
  handshake errors; command-scoped proxy retries succeeded without changing commits or Git config.
- The first `gh pr checks --watch` poll hit a TLS handshake timeout; a non-watching retry returned
  all four completed successful jobs.
- Initial ARA-017 subprocess probes and new regression assertions failed because handled startup
  errors returned 0; these were the expected pre-fix reproductions.
- The first post-fix `make check` found two existing project-input tests that still expected the old
  normal-return contract; they now assert status 2 while preserving path-masking/order checks.
- Independent adversarial probes successively found invalid UTF-8/OSError input, huge/deep parser,
  cloud-cache schema/numeric, and deep semantic-history gaps; each received a focused regression
  before the final green review and full gate.
- The first ARA-015 pytest selector used the wrong test class name and collected no tests; the
  corrected selector then produced the intended pre-fix failures.
- Initial ARA-015 regressions failed because all Gemini Client branches omitted `http_options` and
  timeout exceptions were classified as `unknown`; these were the expected pre-fix reproductions.
- Independent ARA-015 review found the initial generic `timeout` text match also classified an
  unsupported timeout option as a network timeout; the heuristic is now narrowed and the negative
  regression passes.
- The first non-interactive PR body update closed stdin and temporarily produced an empty body;
  subsequent GraphQL/REST attempts hit EOF/TLS handshake errors. A bounded REST retry restored a
  verified 2260-character ARA-015 body without changing the draft state or branch.
- The first local ARA-004 harness tried to call an unavailable `.venv` build backend, then failed to
  stop after that error. Editable-path leakage imported the source checkout and completed one
  deterministic mock run (`20260711_031915_776385`) in ignored `projects/example` state.
- That incident created one run directory, atomically replaced `best_output.md`, `checkpoint.json`,
  `memory.md`, `research_state.json`, and `score_history.json`, and appended `run.log`. No provider,
  secret, tracked file, or canonical research artifact was involved. No cleanup was attempted.
- The first audit-checkpoint GitHub run-list query returned EOF; a bounded retry succeeded and both
  workflow runs plus all four version jobs were verified successful.
- The initial ARA-016 test import failed before the scanner existed, and the first staged-index scan
  reported the four original report hits while the worktree scan was already clean; both were the
  expected pre-fix controls.
- One shell wrapper used zsh's read-only `status` parameter after a scanner probe; the scanner itself
  correctly returned four categorized findings, and subsequent wrappers avoided that variable.
- Independent ARA-016 review reproduced a tracked nested path reading an external file through a
  replaced parent-directory symlink. A no-follow directory-descriptor walk and regression now make
  that state an operational failure before external content is read.
- The final ARA-016 audit proved the first non-`dir_fd` compatibility fallback retained an active
  parent-swap race. The fallback was removed; unsupported platforms now fail closed before reading
  the worktree, while the complete staged-index mode remains available.

## Next Command

```bash
git add -- .codex/CURRENT_STATE.md .codex/TASK_QUEUE.md .codex/DECISIONS.md .codex/KNOWN_ISSUES.md .codex/LAST_VALIDATION.json .codex/RESUME_INSTRUCTIONS.md
```

## Interruption Recovery

Read `.codex/RESUME_INSTRUCTIONS.md`, then compare this file with `git status --short --branch` and `git log --oneline -n 10`. Do not touch ignored runtime artifacts or the local `config.yaml`.

## Current Risks And Prohibitions

- Do not delete or rewrite ignored experiment artifacts, local logs, or private configuration.
- Do not remove the stale `.git/REBASE_HEAD` without an explicit cleanup decision; it is harmless while no rebase directory exists.
- Do not run paid-provider workflows without credential presence checks, a dry run, and an explicit cost cap.
- Do not change prompts, scoring semantics, provider behavior, benchmark results, or artifact interpretation as part of a maintenance-only fix.
- Do not widen the completed `ARA-021` checkpoint into project-level output/log symlink or active
  filesystem-swap policy; those remain `ARA-022`.
- Keep ARA-017 scoped to non-interrupt startup/input failures. Direct and runner-consumed
  `KeyboardInterrupt` process status remains `ARA-023`; wheel asset completeness remains `ARA-004`.
- Active non-cooperating filesystem replacement remains `ARA-022`.
- Do not stage with `git add -A`; stage only reviewed paths.
