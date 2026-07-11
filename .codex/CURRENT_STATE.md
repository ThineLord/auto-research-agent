# Codex Current State

Updated: 2026-07-12 (Asia/Shanghai)

## Repository State

- Current goal: retain the completed, locally validated ARA-036 Judge numeric boundary and continue
  next with the isolated ARA-037 survey interrupt status contract after live recovery checks.
- Current branch: `codex/sol-autonomous-hardening`
- Authoritative current HEAD reference: `HEAD`; resolve it without a shell using
  `git rev-parse --verify HEAD`. A tracked file cannot embed the SHA of the commit that contains it.
- State recorded against commit: `a99723c2a6d492faa8935bc0aa24b1e06cea6de2` (the exact HEAD
  observed immediately before this additive state snapshot).
- Last externally verified fallback: `a99723c2a6d492faa8935bc0aa24b1e06cea6de2` (exact local,
  remote-tracking, `ls-remote`, and GitHub branch equality plus all Python 3.10/3.13 push/PR jobs
  passed)
- Active task at this snapshot: none. ARA-036 is `DONE` with parser/round-loop, related, full-gate,
  and independent final review results passing locally. ARA-037 is the next unblocked P2 task. The
  exact external fallback remains ARA-035 commit `a99723c`; resolve the semantic current `HEAD`,
  remote, and CI state live.
- Uncommitted changes: not persisted as a static claim. Resolve live with
  `git status --short --branch`; a clean checkout of the commit containing this snapshot has none.

## Live Worktree Interpretation

- This committed snapshot does not assert a static dirty-file list. Resolve the exact live state
  with `git status --short --branch`; a clean checkout of the commit containing this file has no
  task-owned worktree changes.

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
- Committed recovery state as `975559d`, pushed both commits, and verified exact local,
  remote-tracking, and GitHub branch SHA equality.
- Updated draft PR 13 with the ARA-016 scope, validation, compatibility boundary, commits, and
  pending-status evidence while preserving its open draft state.
- Verified push run `29140074284` and pull-request run `29140075306`: Python 3.10 and 3.13 all
  passed, including the new repository-safety step in each of the four jobs.
- Committed and pushed final ARA-016 verified-state closeout `9192df8`, verified exact SHA equality,
  and confirmed all four Python 3.10/3.13 closeout jobs passed. Draft PR 13 was updated and remains
  open, draft, and mergeable.
- Reproduced ARA-014 with a temp historical run: its summary said `USER_STOP_REQUESTED`, while the
  latest project checkpoint belonged to another run and incorrectly made the report show `MAX_ROUNDS`.
- Added a regression that failed pre-fix (`1 failed, 4 passed`) for that exact mismatch.
- Implemented target-run stop-reason precedence: summary, config, legacy manifest, then only a
  checkpoint whose normalized run root and any supplied run ID match the target; otherwise unknown.
- Made metadata reads reject symlink/non-regular leaves and descriptor-verify regular files before
  reading, and restricted rendered stop reasons to the official `STOP_*` constant values.
- Added absolute/repo/project/runs-relative identity, ID/path conflict, malformed/nonobject JSON,
  config/manifest fallback, external symlink, directory/FIFO, and Markdown/private-text coverage.
- Independent delta reviews reproduced external metadata reads, Markdown/private-text injection,
  and a credential-shaped stop reason surviving the first sanitizer; fixed all three with no-follow
  regular-file reads and a dynamic official `STOP_*` allowlist. Final review reported green.
- Committed the scoped implementation, tests, changelog, and developer guidance as `588e32c` with
  no ignored artifacts, experiment values, providers, prompts, metrics, or unrelated files.
- Committed recovery state as `c893e63`, pushed both commits, and verified exact local,
  remote-tracking, and GitHub branch SHA equality.
- Updated draft PR 13 with ARA-014 scope, validation, safety/compatibility boundaries, and commits;
  it remains open, draft, and mergeable.
- Verified push run `29140847860` and pull-request run `29140848882`: Python 3.10 and 3.13 all
  passed, including repository-safety and test steps in each of the four jobs.
- Committed and pushed final ARA-014 verified-state closeout `2dd56f9`, verified exact SHA equality,
  and confirmed all four Python 3.10/3.13 closeout jobs passed. Draft PR 13 was updated and remains
  open, draft, and mergeable.
- Reproduced both CLI interrupt handlers printing `MANUAL_INTERRUPT`, releasing the lock, and then
  returning process status 0; reproduced runner-consumed interrupts completing resumable artifacts
  but likewise returning success.
- Added red regressions for mock/provider interrupt status and runner propagation before changing
  implementation; the expected pre-fix run failed all three new interrupt assertions.
- Made runner-caught manual interrupts propagate only after checkpoint, run summary/config, and
  interrupted report finalization; both CLI boundaries translate them to `SystemExit(130)`.
- Kept cooperative `STOP_REQUESTED` as successful status 0 with `USER_STOP_REQUESTED`, resumable
  artifacts, signal cleanup, and no reclassification from shared `can_resume`/report fields.
- Moved survey/mock/provider lock acquisition and error evaluation inside their lifecycle
  `try/finally` blocks after review found an interrupt cleanup window; a real-lock regression proves
  metadata removal before temporary-directory cleanup.
- Added an end-to-end module subprocess fault injection, direct handler controls, runner artifact
  assertions, session final-report suppression, and an actual provider-free safe-stop subprocess.
- Documented statuses 0/1/2/130 and limited artifact-completeness wording to the runner's protected
  agent-execution phase.
- Related regression passed (`63 passed, 61 subtests passed`); final `make check` passed with Ruff,
  imports, self/worktree/staged safety, and pytest (`231 passed, 154 subtests passed`).
- Two independent post-fix audits reported GO after the lock-lifecycle and documentation-boundary
  corrections; `git diff --check` passed and ignored project artifacts were not touched.
- Staged only the 11 reviewed code/test/public-documentation paths, passed staged diff and repository
  safety checks, and committed implementation `4cae84e398821763a4680b99faa2aacb37550bfe`
  (`fix: propagate manual interrupt status`).
- Committed recovery checkpoint `37b3749`, pushed both commits, and verified exact local,
  remote-tracking, `ls-remote`, and GitHub PR head SHA equality.
- Verified push run `29141545223` and pull-request run `29141546331`: Python 3.10 and 3.13 all
  passed, including formatting, lint, import, repository-safety, and test steps in all four jobs.
- Updated and read back draft PR 13 with ARA-023 scope/evidence; it remains open, draft, and mergeable.
- Committed and pushed final ARA-023 verified-state closeout `48f5639`, verified exact SHA equality,
  and confirmed all four Python 3.10/3.13 closeout jobs passed. Draft PR 13 was updated and remains
  open, draft, and mergeable.
- Reproduced resume replacing original legacy manifest mode/model/drafting/start/project and unknown
  extension fields while preview accepted checkpoint IDs that disagreed with the canonical root.
- Added red provenance, direct/leaf-alias/non-string ID, missing-ID compatibility, malformed/UTF-8/
  nonobject/deep/mismatched/unmergeable manifest, and fail-before-write regressions.
- Made canonical `run_root.name` the identity, rejecting an explicit mismatch while deriving a
  missing ID; configured storage and canonical-ID leaf aliases remain compatible.
- Strictly snapshots an existing raw manifest before the first write, retains creation-time and
  unknown fields, canonicalizes ID/root/config pointers, and merges old-then-current resume metadata.
- Made unpreservable existing manifests fail with privacy-safe errors before config/checkpoint/round/
  summary writes; current session operational fields remain in `run_config.json`.
- Independent review found a sparse-manifest provenance gap; separated existing sparse, missing with
  persisted config, and new-run branches so current resume fields are never invented as creation data.
- Added two-consecutive-resume coverage proving a first resume's run_config cannot backfill absent
  provenance into the sparse manifest on a later resume.
- Focused new regression passed (`4 passed, 10 subtests passed`); related resume/config/consumer/UI
  regression passed (`119 passed, 100 subtests passed`). Final `make check` passed with Ruff,
  imports, both safety scans, and pytest (`235 passed, 164 subtests passed`).
- Independent code and adversarial reviews reported GO after the sparse provenance correction;
  `git diff --check` passed and ignored project artifacts were not touched.
- Staged only the nine reviewed code/test/public-documentation paths, passed staged diff and safety
  checks, and committed implementation `3b98c61d7cd7531266144d1d46d3c5aad29220c4`
  (`fix: preserve run manifest provenance on resume`).
- Committed recovery checkpoint `c1e8c57`, pushed both commits, and verified exact local,
  remote-tracking, `ls-remote`, and GitHub PR head SHA equality.
- Verified push run `29142234694` and pull-request run `29142235674`: Python 3.10 and 3.13 all
  passed, including formatting, lint, import, repository-safety, and test steps in all four jobs.
- Updated and read back draft PR 13 with ARA-020 scope/evidence; it remains open, draft, and mergeable.
- Committed and pushed final ARA-020 verified-state closeout `4d77a8c`, verified exact SHA equality,
  and confirmed all four Python 3.10/3.13 closeout jobs passed. Draft PR 13 was updated and remains
  open, draft, and mergeable.
- Reproduced direct builder and real repeated zero-round resumes leaving `resume_sessions` empty,
  while the new round-1 control correctly remained empty.
- Added direct lifecycle and two-consecutive-resume regressions before changing implementation; both
  failed exactly on the missing round-1 session entry.
- Changed session append to use `start_round > 1` or explicit `resume_existing_run` lifecycle,
  preserving old higher-round compatibility and new-run round-1 behavior.
- Related run-config/round-loop tests passed (`47 passed, 59 subtests passed`); final `make check`
  passed with Ruff, imports, both safety scans, and pytest (`236 passed, 164 subtests passed`).
- Independent focused review reported GO across new round 1, zero-round repeated resume, and
  start-round-greater-than-1 compatibility; no provider or ignored artifact was used.
- Staged only the five reviewed code/test/public-doc paths, passed staged diff/safety checks, and
  committed implementation `b961070a848c2cf67269b8c081c32641fd6990b5`
  (`fix: record zero-round resume sessions`).
- Committed recovery checkpoint `a3bef4d`, pushed both commits, and verified exact local,
  remote-tracking, `ls-remote`, and GitHub branch SHA equality.
- Verified push run `29142505314` and pull-request run `29142506476`: Python 3.10 and 3.13 all
  passed, including formatting, lint, import, repository-safety, and test steps in all four jobs.
- Verified ARA-024 final closeout `0112e108292847ddde864150331db4c3b05a9aed`: local,
  remote-tracking, and GitHub branch SHAs match; push run `29142573684` and pull-request run
  `29142574570` passed on Python 3.10 and 3.13, and draft PR 13 is updated.
- Started ARA-005 and independently cross-checked `docs/quickstart_zh.md` against the comparison,
  analytics, UI, and test implementations. README, CHANGELOG, and dated historical audit/gap
  reports remain unchanged.
- Reclassified completed CLI comparison, UI comparison, agent timing, estimated-token, Streamlit
  width, resume-preview, and drafting-mode work as implemented while retaining explicit boundaries
  around research quality, true cost, causal claims, and advanced cross-run analysis.
- A targeted stale-wording search returned no remaining ARA-005 phrases, and `git diff --check`
  passed.
- Independent final review first identified three fact-precision blockers: comparison rubric fields,
  already-implemented resume lifecycle distinctions, and the session report filename. All were
  corrected, the named drafting modes were made explicit, and the final re-review reported GO.
- Final `make check` after all wording corrections passed with Ruff, imports, both safety scans,
  and pytest (`236 passed, 164 subtests passed`).
- Staged only `docs/quickstart_zh.md`, verified its cached diff and staged safety scan, and committed
  implementation `15d99351ebef8fc7cccb38acd4205f8cc7e23917`
  (`docs: align implemented analytics roadmap`).
- Committed recovery checkpoint `6b590918b6ad7fc0e0ce4a83e4d011b7b479f0c8`, pushed both
  ARA-005 commits, and verified exact local, remote-tracking, `ls-remote`, and GitHub branch SHA
  equality with ahead/behind `0/0` and a clean worktree.
- Verified push run `29142879222` and pull-request run `29142880135`: Python 3.10 and 3.13 passed
  every formatting, lint, import, repository-safety, and test step in all four jobs.
- Confirmed four prior closeout commits permanently embedded their parent checkpoint and stale
  pending/dirty authoring state because a tracked file cannot contain its own final commit SHA.
- Confirmed no tracked runtime code, scripts, or tests consume the recovery JSON fields; unknown
  external readers remain protected through unchanged schema-v1 legacy 40-hex fields.
- Added authoritative semantic `current_head.ref`, fixed no-shell resolution argv, live worktree
  source, exact snapshot-base SHA, and exact external verification evidence for ARA-005 closeout
  `3fa33a7` including event/workflow/head/job conclusions.
- Updated recovery instructions and decisions so state snapshots never request another recursive
  closeout merely to embed their own SHA. ARA-025 consistency assertions and final `make check`
  passed; independent review's four synchronization blockers were corrected.
- Received explicit owner approval for ARA-004, reverified clean branch/upstream equality, GitHub
  authentication, the absence of active Git operations, and successful Python 3.10/3.13 CI at
  `08994be`.
- Restored the verified ARA-004 audit instead of repeating the unsafe harness: wheel and sdist omit
  config/prompts/example assets, installed mock exits 2 before provider work, and neutral temporary
  workspaces remain empty.
- Preserved KI-023 exactly as-is. Approval covers the packaging/resource implementation, not
  cleanup or reconstruction of ignored `projects/example` state.
- Reproduced the installed failure before the fix in both neutral and foreign-Git temporary
  workspaces: both subtests exited 2 because `config.example.yaml` was absent.
- Added an exact six-file package-data allowlist, byte-parity regression, source/editable layout
  compatibility, installed CWD workspace, bundled-prompt provenance, no-clobber default mock seed,
  and explicit source Git-root separation.
- Proved the installed mock path writes only its temporary workspace, does not create
  `config.yaml`, ignores untrusted CWD prompt files, leaves copied package files unchanged, and
  records no foreign workspace commit.
- Passed focused package/config/CLI/mock/diagnostic/session/runner tests, Ruff lint, and
  `git diff --check`.
- Corrected two independent-review findings before commit: interrupted staging-file creation now
  cleans up on `BaseException`, and final publication uses native no-replace primitives so a racing
  target directory is never overwritten.
- Passed final `make check` with Ruff, import smoke, repository-safety scans, and pytest (`246
  passed, 172 subtests passed in 3.79s`).
- Built wheel and sdist from the final worktree, verified their exact six-resource allowlists and
  canonical bytes, installed both into isolated environments, and passed console/module help/mock
  plus missing-config controls without source imports or package-directory writes.
- Verified four installed mock runs recorded no foreign CWD Git commit and used the canonical
  bundled prompts. A separate foreign-Git wheel smoke also retained a null run-config commit.
- Repeated eight-way seed concurrency 50 times with exactly one publisher each time; Darwin's
  native no-replace path was exercised locally, Linux ran in Python 3.10/3.13 CI, and Windows was
  statically/mocked reviewed.
- Committed the implementation as `0aee55e1a48dab3d56f0475f789c2134c548ddc5`, pushed it, verified
  local/upstream/`ls-remote` equality with ahead/behind `0/0`, and confirmed both GitHub Actions
  triggers passed every Python 3.10/3.13 job.
- Kept all validation artifacts under `/tmp`; none were committed or uploaded. The temporary sdist
  is explicitly not publication-ready because its tar headers expose the local builder owner/group
  and generated metadata timestamps are not reproducible. Follow-up ARA-026 records that boundary.

## ARA-022 Implementation Checkpoint

- Reproduced static leaf links, nested/ancestor link swaps, UI validation/read swaps, fresh-context
  metadata/log/stop-signal paths, and cross-thread boundary loss only in temporary fixtures.
- Added a process-wide trusted-boundary registry. Nested run roots inherit/rebase to the project
  anchor; only configured storage outside the project receives a separate physical anchor.
- Added POSIX component-by-component no-follow descriptor operations for automatic reads, appends,
  atomic replacement, unlink, coordination files, directory creation, and pruned recursive survey
  source traversal. Static hard links and special nodes fail closed.
- Preserved configured external `runs/` storage, stale real-directory tolerance, explicit
  analyze/compare aliases, and explicit export-parent behavior. Survey source helpers intentionally
  retain lexical `abspath` spelling so safe reads cannot be redirected by canonicalization.
- Hardened CLI, resume, survey/cloud, run lock, background-process, cooperative stop, and Streamlit
  direct-entry boundaries; preserved actionable lock/guard recovery classification.
- Independent implementation and state-consistency reviews report GO. The documented exclusions are
  same-UID replacement with another real directory, post-open/new-temp hard-link races, trusted
  ancestors above the anchor, and Windows active replacement.
- Committed the implementation as `544b26a` and pushed it with exact local/upstream/`ls-remote`
  equality. Python 3.13 CI passed, while both Python 3.10 runs exposed a test-only portability bug:
  the test constructed `Path` after mocking `os.name="nt"` on Linux.
- Moved `Path` construction before the mock, reran `make check` (`294 passed, 176 subtests passed`),
  committed the portable regression as `93026ca`, pushed, and verified exact remote equality.

## ARA-028 Recovery-State Regression

- Recovered a clean branch at `ca3a2e8`, verified exact local/upstream/`ls-remote` equality, and
  confirmed closeout push/PR runs `29153184085`/`29153185119` passed Python 3.10 and 3.13.
- Reproduced four stale-state failures: the queue and active-task snapshot disagreed, the worktree
  section claimed files remained uncommitted, remaining steps requested the already-completed
  ARA-022 closeout, and a JSON note named an obsolete fallback commit.
- Added a tracked recovery-state consistency regression covering live worktree sourcing,
  recursive-closeout instructions, active-task synchronization, semantic HEAD structure, and the
  single conservative external fallback contract.

## ARA-032 Finite Score Normalization

- Reproduced malformed numeric artifacts making `nan`/`Infinity` dominate ranking, create a false
  flat trend, and escape analysis/comparison output as non-standard JSON.
- Rejected boolean, non-finite numeric/string, and unrepresentably large numeric score values while
  preserving finite legacy numeric strings.
- Ranked score presence ahead of value so any valid negative score remains preferable to a missing
  score; within scored runs, score and completed-round ordering remains unchanged.
- Normalized overflowed trend and baseline deltas to `null` while retaining the direction inferred
  from their finite endpoints.
- Preserved the historical `sum(scores) / count` average whenever its total is finite. Only an
  overflowed total uses max-absolute scaling plus `math.fsum`, keeping representable finite-extreme
  averages such as three maximum floats finite without changing ordinary two-decimal results.
- Added strict-JSON, negative-ranking, huge-integer, finite-extreme, and ordinary-rounding
  regressions. Two independent adversarial reviews returned GO after the extreme-average fallback
  and finite-total compatibility path were added.

## ARA-033 Privacy-Safe Output Failure Boundary

- Reproduced analysis and comparison output parents implemented as ordinary files: both module
  commands returned 1 but emitted full tracebacks containing temporary and repository absolute
  paths. An unresolved `~user` output path exposed the same boundary through `RuntimeError`.
- Limited normalization to the explicit output argument branch: user expansion, parent resolution,
  and JSON writing catch `OSError`/`RuntimeError`, print a fixed path-free message, and raise the
  existing operation-error status 1 without exception chaining.
- Left analysis/comparison computation, storage propagation, final console rendering, successful
  JSON output, and explicitly authorized output-parent symlinks unchanged.
- Added real module subprocess regressions for both modes and both failure classes. Two independent
  reviews returned GO after checking exit semantics, failed writes, success paths, and symlink
  compatibility.

## ARA-034 Explicit Resume Eligibility Boundary

- Reproduced `"false"`, `"true"`, and integer `1` checkpoint flags entering the iterative runner;
  the end-to-end control invoked all agent stages, wrote a new round, and replaced checkpoint state.
- Reproduced a 400-digit preview score raising `OverflowError` and Infinity/NaN passing through the
  previous float conversion.
- Required identity with literal boolean `true`; all other types return the existing
  `not_resume_eligible` result before the runner or any agent stage. Preview score conversion now
  catches overflow and accepts only finite non-boolean values, preserving finite numeric strings.
- Direct byte-snapshot and real module CLI tests prove no project artifact write, no agent access,
  status 2, no traceback, and lock release. Two independent reviews returned GO.

## Remaining Steps

- Start ARA-037 with survey interrupt unit/subprocess controls; preserve lock release and normalize
  the manual-interrupt exit to the existing status-130 contract without widening survey behavior.
- Continue with the highest-priority queued P2 after ARA-036 unless newly confirmed evidence changes
  the ordering.
- Keep ARA-018, ARA-029, and ARA-030 behind their recorded owner/configuration/long-task approval
  gates; do not fold release or CI-configuration policy into the analysis/compare fixes.

## Test Status

- ARA-036 focused parser/round-loop and related regression passed `52 passed, 75 subtests passed`;
  local `make check` passed Ruff format/lint, imports, both repository-safety modes, and pytest (`323
  passed, 201 subtests passed`; 100 tracked files and zero findings).
- Independent ARA-036 final review returned GO after checking 400-digit float overflow, 5000-digit
  JSON decoder limits on Python 3.11+, Python 3.10 fallback behavior, valid numeric strings,
  finite/clamp semantics, legacy score fallback, valid rubric siblings, and raw payload compatibility.
- ARA-035 remote verification: exact local/upstream/`ls-remote` equality at `a99723c`, ahead/behind
  `0/0`; push run `29164052624` and pull-request run `29164053862` passed Python 3.10/3.13. Draft
  PR 13 is open, mergeable, and updated.
- ARA-035 focused strict-JSON metric/API/CLI regression passed `59 passed, 20 subtests passed`;
  broader runner/diagnostic/UI regression passed `172 passed, 116 subtests passed`.
- ARA-035 local `make check` passed Ruff format/lint, imports, repository-safety self-test,
  worktree/staged scans, and pytest (`321 passed, 201 subtests passed`; 100 tracked files and zero
  findings).
- Two independent ARA-035 final reviews returned GO after checking numeric/string NaN/Infinity,
  `10**400`, cross-agent/cross-round overflow, non-object agent leaves, raw legacy summary rubric,
  strict API/writer/CLI output, and ordinary-value compatibility. No provider call was made.
- ARA-034 remote verification: exact local/upstream/`ls-remote` equality at `bdbd9d5`, ahead/behind
  `0/0`; push run `29163467415` and pull-request run `29163468552` passed Python 3.10/3.13. Draft
  PR 13 is open, mergeable, and updated.
- ARA-034 focused preview/end-to-end/CLI regressions passed `3 passed, 11 subtests passed`; the
  pre-fix run had failed for truthy strings/integer, huge/non-finite scores, agent access, writes,
  and CLI status exactly as expected.
- ARA-034 related resume/CLI/UI regression passed `137 passed, 114 subtests passed`; final local
  `make check` passed Ruff format/lint, imports, repository-safety self-test, worktree/staged scans,
  and pytest (`314 passed, 199 subtests passed`; 100 tracked files and zero findings).
- Two independent ARA-034 reviews returned GO. They verified identity-true semantics, finite-score
  compatibility, no runner/agent-stage invocation, byte preservation, CLI status 2, no traceback,
  and run-lock release. No real provider call was made.
- ARA-034 pre-fix provider-free probe: checkpoint `can_resume: "false"` produced
  `preview.can_resume=True`, `run_resume_mode=True`, and invoked the runner; a 400-digit integer
  `best_score` raised `OverflowError`.
- ARA-033 remote verification: exact local/upstream/`ls-remote` equality at `f44687e`, ahead/behind
  `0/0`; push run `29162704235` and pull-request run `29162705572` passed Python 3.10/3.13. Draft PR
  13 is open, mergeable, and updated.
- ARA-033 focused failure boundary passed `2 passed, 23 deselected, 4 subtests passed`; related
  CLI/analysis/comparison/storage regression passed `72 passed, 22 subtests passed`.
- ARA-033 full provider-free gate passed Ruff format/lint, imports, repository-safety self-test,
  worktree/staged safety scans, and pytest after explicit staging (`311 passed, 188 subtests passed
  in 9.48s`; 100 tracked files and zero findings).
- Two independent ARA-033 reviews returned GO. They verified status 1, no traceback/path disclosure,
  unchanged blocker bytes, successful provider-free output, and explicit parent-symlink support.
- ARA-032 remote verification: exact local/upstream/`ls-remote` equality at `21fea11`, ahead/behind
  `0/0`; push run `29162165065` and pull-request run `29162166082` passed Python 3.10/3.13. Draft PR
  13 is open, mergeable, and updated.
- ARA-032 final provider-free gate: Ruff format/lint, imports, repository-safety self-test,
  worktree/staged safety scans, and pytest passed after explicit staging (`309 passed, 184 subtests
  passed in 8.96s`; 100 tracked files and zero findings).
- ARA-032 related analytics/compare/metrics suite passed `26 passed`; six focused non-finite,
  negative-ranking, finite-extreme, and finite-total compatibility regressions passed together.
- Two independent final reviews returned GO. One exercised 300,000 ordinary score groups against
  the historical rounded-average path plus 1–512 maximum-float matrices; the other checked mixed
  extreme signs, zero, negative scores, legacy strings, trend direction, and strict JSON.
- ARA-032 pre-fix reproduction: malformed score strings produced `nan`/`Infinity`, a false `flat`
  trend, selected the malformed run over a valid score-75 run, and raised `ValueError` under strict
  JSON serialization.
- ARA-031 recovery baseline: `make check` passed with Ruff, imports, both safety modes, and pytest
  (`300 passed, 177 subtests passed in 9.02s`; 100 tracked files, zero findings).
- ARA-031 pre-fix reproduction: provider-free zero-round resume returned success and overwrote the
  malformed config while invoking no agent; the regenerated `started_at` replaced original
  provenance instead of blocking before writes.
- ARA-031 focused reader/resume validation: `7 passed, 46 deselected, 14 subtests passed`; complete
  run-config/round-loop regression: `53 passed, 66 subtests passed`.
- ARA-031 full provider-free gate: Ruff format/lint, imports, repository-safety self-test, worktree
  and staged safety scans, and pytest passed (`303 passed, 184 subtests passed in 9.11s`; 100 tracked
  files and zero findings before final metadata staging).
- Two independent reviews returned GO after one reviewer reproduced the JSON `null`/missing-sentinel
  collision; the sentinel and unit/end-to-end `null` cases were added before the final gate.
- ARA-028 recovery baseline: `make check` passed with Ruff, imports, both safety modes, and pytest
  (`294 passed, 176 subtests passed in 9.52s`; 99 tracked files, zero findings).
- ARA-028 pre-fix regression: `4 failed, 1 passed`; each failure maps to a confirmed stale or
  contradictory recovery-state claim, with no runtime code exercised.
- ARA-028 focused post-fix regression: `6 passed, 1 subtest passed`; independent review exposed two
  omitted cross-file checks and two classifier counterexamples, each added before final validation.
- ARA-028 final provider-free gate: Ruff format/lint, imports, repository-safety self-test, worktree
  and staged safety scans, and pytest passed after explicit staging (`300 passed, 177 subtests passed
  in 9.07s`; 100 tracked files and zero safety findings).
- Independent final staged-diff review: GO; both classifier counterexamples are rejected, explicit
  fallback labels agree, shallow CI is supported, and no remaining blocker or P1/P2 was found.
- ARA-022 start baseline: `make check` passed with Ruff, imports, both safety modes, and pytest
  (`246 passed, 172 subtests passed in 3.72s`; 99 tracked files, zero findings).
- ARA-022 focused final layer passed (`181 passed, 104 subtests passed`); independent full pytest
  passed (`294 passed, 176 subtests passed in 9.43s`).
- Final local `make check` passed with Ruff format/lint, imports, repository-safety self-test,
  worktree/staged safety scans of 99 tracked files with zero findings, and pytest (`294 passed, 176
  subtests passed in 9.44s`). `git diff --check` also passed.
- Corrected before the final gate: early project preflight temporarily changed stale lock/FIFO
  diagnostics (`2 failed, 278 passed, 170 subtests`); a misplaced test caused round-loop collection
  `IndentationError`; canonical survey path spelling caused one compatibility assertion failure
  (`1 failed, 282 passed, 172 subtests`). None remains in the final result.
- Initial implementation CI runs `29152939334` (push) and `29152940413` (PR) failed only on Python
  3.10: `Path("automatic-directory")` was constructed while `os.name` was mocked to `nt`, causing
  Linux Python 3.10 to instantiate unsupported `WindowsPath`. Python 3.13 passed both runs. The
  test-only fix is `93026ca`; local full validation remained green and replacement CI passed.
- Replacement runs `29153023802` (push) and `29153024964` (PR) passed all Python 3.10/3.13 format,
  lint, import, repository-safety, and test jobs at `93026ca`.
- ARA-004 recovery checkpoint `094446f`: push run `29148953536` and pull-request run `29148955113`
  passed on Python 3.10 and 3.13; local/upstream/`ls-remote` equality is `0/0`.
- ARA-004 pre-fix regression: two installed-layout subtests failed with status 2 and missing
  `config.example.yaml`, covering neutral and unrelated-Git CWDs.
- ARA-004 final package-resource suite: `9 passed, 8 subtests passed`; final combined package/
  run-config/CLI/mock suite: `35 passed, 20 subtests passed`.
- Related package, CLI, mock, run-config, diagnostic, session, and round-loop layers passed; the
  run-config/round-loop result was `47 passed, 59 subtests passed`. Ruff and `git diff --check`
  passed.
- Final ARA-004 `make check`: Ruff formatted 56 files, lint/import/safety passed, and pytest passed
  (`246 passed, 172 subtests passed in 3.79s`). The staged safety scan covered 99 tracked files with
  zero findings.
- The same full gate rerun after the recovery-state updates passed (`246 passed, 172 subtests passed
  in 3.68s`; 99 tracked files and zero safety findings).
- Final wheel SHA-256: `02462324be35135d2b875b4e6cd3d29ae06b71790ea65e55e72814260eb8050d`;
  final sdist SHA-256: `3e5917f7b2e80be550a563b29a1ae856bc9a2e38488ccf793b5281d5f9d2afd4`.
- Wheel/sdist isolated install matrix passed eight help/mock entrypoint controls, two expected
  missing-config status-2 controls, exact RECORD verification, canonical resource-byte checks,
  source/editable compatibility, no package-directory mutation, and no foreign Git provenance.
- Independent artifact, compatibility, code, and adversarial reviews are GO for the code change.
  Publication of the temporary sdist is NO-GO until ARA-026 normalizes owner/group and generated
  timestamp metadata.
- GitHub Actions at `0aee55e`: push run `29148635379` and pull-request run `29148637631` passed on
  Python 3.10 and 3.13, including install, formatting, lint, imports, safety, and tests in all jobs.
- Independent recovery-state review: GO after replacing truncated read commands with full-file
  reads; all seven staged state files, task/issue identifiers, CI evidence, and NO-GO publication
  boundary are consistent.
- ARA-025 JSON parsing and semantic consistency assertions: passed; fixed argv resolves current
  `HEAD`, all legacy/fallback fields remain 40-hex, verified commit exists and is an ancestor, and
  recorded CI events/workflow/head/jobs match live GitHub evidence.
- ARA-025 final `make check`: Ruff format passed (54 files), Ruff lint passed, imports passed, both
  safety scans passed, and pytest passed (`236 passed, 164 subtests passed in 2.70s`).
- ARA-025 independent review: core design GO; its four final state-synchronization blockers were
  corrected before the completed semantic snapshot, and no recursive closeout is required.
- ARA-005 targeted stale-wording search: passed; no known-completed comparison, analytics,
  dashboard, drafting-mode, timing, or estimated-token item remains described as future work in the
  current-state quickstart roadmap.
- ARA-005 `git diff --check`: passed. Final `make check`: Ruff format passed (54 files), Ruff lint
  passed, imports passed, both safety scans passed, and pytest passed (`236 passed, 164 subtests
  passed in 2.69s`).
- ARA-005 independent read-only evidence audit and final corrected-diff review: GO; README,
  CHANGELOG, and dated historical reports remain unchanged.
- GitHub Actions at `6b59091`: push run `29142879222` and pull-request run `29142880135` passed on
  Python 3.10 and 3.13, including repository-safety and test steps in all four jobs.
- ARA-024 pre-fix regression: `2 failed`; direct and real zero-round resume both omitted the session.
- ARA-024 related regression: `47 passed, 59 subtests passed`.
- Final ARA-024 `make check`: Ruff format passed (54 files), Ruff lint passed, imports passed, both
  safety scans passed, and pytest passed (`236 passed, 164 subtests passed in 2.69s`).
- Independent review: GO; new run round 1 remains empty, each zero-round resume adds exactly one,
  and existing start-round-greater-than-1 behavior passes. No provider-backed test was needed.
- GitHub Actions at `a3bef4d`: Python 3.10/3.13 passed for both push and pull-request events;
  formatting, lint, imports, repository safety, and tests passed in all four jobs.
- ARA-020 pre-fix regression: `8 failed, 2 passed, 39 deselected`; manifest provenance was replaced,
  explicit direct/alias IDs were accepted, and five unpreservable manifest cases were overwritten.
- ARA-020 focused regression after the final sparse correction: `4 passed, 10 subtests passed`.
- ARA-020 resume/config/compare/analytics/benchmark/UI regression: `119 passed, 100 subtests passed`.
- Final ARA-020 `make check`: Ruff format passed (54 files), Ruff lint passed, import smoke passed,
  both repository-safety scans passed, and pytest passed (`235 passed, 164 subtests passed in 2.68s`).
- Two independent reviewers reported GO after reproducing and correcting sparse-manifest current-
  session contamination. Provider calls and ignored project artifacts were not used.
- GitHub Actions at `c1e8c57`: Python 3.10/3.13 passed for both push and pull-request events;
  formatting, lint, imports, repository safety, and tests passed in all four jobs.
- Final ARA-020 closeout `4d77a8c`: exact remote SHA verified and Python 3.10/3.13 passed for push
  run `29142308598` and pull-request run `29142309509`, including all safety/test steps.
- ARA-023 pre-fix interrupt regression: `3 failed, 1 passed, 50 deselected`; both CLI boundaries
  returned normally and runner did not re-propagate after safe artifact finalization.
- ARA-023 final related regression: `63 passed, 61 subtests passed in 1.49s` across CLI exit,
  round-loop, mock, and session modules.
- ARA-023 final `make check`: Ruff format passed (54 files), Ruff lint passed, import smoke passed,
  both repository-safety scans passed, and pytest passed (`231 passed, 154 subtests passed in 2.64s`).
- End-to-end temporary-project subprocesses proved manual status 130 plus three finalized resumable
  artifacts/report/lock cleanup, and cooperative safe-stop status 0 plus signal cleanup. No provider
  call, real credential, ignored repository artifact, prompt, score, metric, or experiment changed.
- Independent implementation and test/docs reviews reran focused tests and reported GO after the
  protected-phase wording and acquisition-lifecycle fixes; `git diff --check` passed.
- GitHub Actions at `37b3749`: Python 3.10/3.13 passed for both push and pull-request events;
  formatting, lint, imports, repository safety, and tests passed in all four jobs.
- Final ARA-023 closeout `48f5639`: exact remote SHA verified and Python 3.10/3.13 passed for both
  push run `29141633704` and pull-request run `29141634930`, including all safety/test steps.
- ARA-014 pre-fix regression: `1 failed, 4 passed`; the report borrowed the unrelated checkpoint's
  `MAX_ROUNDS` instead of the target summary's `USER_STOP_REQUESTED`.
- ARA-014 final focused regression: Ruff passed and `tests/test_benchmark_report.py` passed
  (`11 passed, 20 subtests passed`). Related benchmark/config/storage/analytics tests passed
  (`33 passed, 14 subtests passed`) before the final metadata hardening additions.
- Final local `make check`: Ruff format/lint, import smoke, self/worktree/staged safety, and pytest
  passed (`224 passed, 154 subtests passed in 2.36s`). Final focused rerun after strengthening the
  symlink fixture remained `11 passed, 20 subtests passed`.
- Current worktree and staged-index repository-safety scans passed with 91 tracked files and zero
  findings; `git diff --check` passed. Real provider tests were not needed or run.
- GitHub Actions at `c893e63`: Python 3.10/3.13 passed for both push and pull-request events; safety
  and test steps passed in all four jobs.
- Final ARA-014 closeout `2dd56f9`: exact remote SHA verified and Python 3.10/3.13 passed for both
  push and pull-request events, including all safety and test steps.
- ARA-016 focused regression: Ruff lint passed and `tests/test_repo_safety.py` passed (`11 passed`).
- Scanner controls: self-test, tracked worktree, and full staged-index scans passed with 91 tracked
  files, including the scanner and test; no tracked binary/NUL file or gitlink is currently present.
- Final local ARA-016 `make check`: Ruff format passed (54 files), Ruff lint passed, import smoke
  passed, both safety scans passed, and pytest passed (`217 passed, 134 subtests passed in 2.55s`).
- `git diff --check` and staged diff checks passed. Native Python 3.10 execution remains for CI;
  the current local environment is Python 3.13.14.
- Python 3.10 AST parsing passed for the scanner and its test module. Final independent review reran
  the 11 focused tests plus self/worktree/staged scans and reported no release blocker.
- GitHub Actions at `975559d`: Python 3.10/3.13 passed for both push and pull-request events; the
  repository-safety step passed in all four jobs.
- Final ARA-016 closeout `9192df8`: exact remote SHA verified and Python 3.10/3.13 passed for both
  push and pull-request events, including all four safety steps.
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
- ARA-004 implementation tests were initially withheld because the verified fix exceeded 30
  minutes; owner approval was later received, and current progress is recorded at the top of this
  file.
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

- The initial ARA-034 regressions failed two tests and seven subtests as expected: truthy malformed
  flags entered the runner, huge/non-finite scores raised or propagated, and the module control
  exited 1 after agent access and writes. The final focused and full gates pass.
- One post-fix `rg` audit put a backticked task-state token inside a double-quoted zsh pattern, so
  zsh attempted the token as a command. It had no file or Git impact and was immediately rerun with
  a literal single-quoted pattern.
- ARA-033 pre-fix provider-free subprocesses for analysis and comparison each returned 1 but emitted
  a traceback containing both temporary and repository absolute paths. The first regression failed
  two subtests as expected; an additional unresolved-`~user` regression also failed two subtests
  until output argument expansion moved inside the normalized boundary.
- ARA-032's initial strict-JSON tests failed twice as expected because score-derived output still
  contained `NaN`; a later huge-integer extension exposed uncaught `OverflowError` before the
  conversion boundary was widened.
- Three adversarial regressions then failed as expected: an unscored run outranked a valid `-5.0`
  run, and finite-extreme average/delta operations escaped as `Infinity`.
- The first overflow-resistant average passed two `1e308` values but failed three maximum floats;
  max-absolute scaling corrected that case. Independent review then found the scaled path changed a
  historical ordinary average from `46.48` to `46.47`; the final implementation preserves the old
  finite-total path and uses scaling only after overflow.
- One metadata inspection used unavailable unqualified `python` and returned command-not-found; it
  was rerun with the repository `.venv/bin/python` without modifying files.
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
- The initial ARA-014 mismatch regression failed as expected because `write_benchmark_report`
  unconditionally used the newer project checkpoint. Independent post-fix review then reproduced
  external metadata symlink reads and Markdown/private-text injection through stop reason; both now
  have focused regressions and fail-closed handling.
- A final ARA-014 review showed the enum-style sanitizer still accepted credential-shaped text;
  rendering is now restricted to official `STOP_*` constants, with every current constant and a
  synthetic credential-shaped rejection covered.
- Initial ARA-023 regressions failed because the mock/provider handlers swallowed `KeyboardInterrupt`
  and the runner returned after recording `MANUAL_INTERRUPT`; these were expected pre-fix failures.
- The first two ARA-023 subprocess fixtures embedded unescaped newlines and failed with a local
  `SyntaxError`; the fixture strings were corrected before any behavioral result was accepted.
- Independent ARA-023 review found acquisition/error checks outside the lock lifecycle and docs
  overstating the protected interrupt window; both received focused corrections and green re-review.
- The first post-fix ARA-020 provenance assertion compared macOS `/var` with canonical
  `/private/var`; the assertion now compares the canonical run-config path and all behavior passed.
- Independent ARA-020 review found valid sparse manifests would inherit current resume fields and
  preserve them falsely; the three-way provenance source policy and repeated-resume regression fixed it.
- Initial ARA-024 direct and runner-level regressions both failed because `start_round == 1` was the
  only session-append gate; these were expected pre-fix failures.
- The ARA-004 pre-fix installed-layout regression failed in both neutral and unrelated-Git
  workspaces with status 2 because `config.example.yaml` was absent; this was the expected defect
  reproduction.
- The first ARA-004 full `make check` stopped only at Ruff formatting for the new package-resource
  module. Formatting was applied and the complete gate then passed.
- Independent adversarial review first reproduced partial staging residue after an interrupt and
  weak source-layout detection; the implementation and focused regressions corrected both.
- A second review found that POSIX rename could replace a concurrently created empty target and
  identified a cleanup-flag interruption window. Native no-replace publication and unconditional
  owned-staging cleanup closed both before commit; final reviews were green.
- The first isolated build emitted a setuptools package-data discovery warning. Setting
  `include-package-data = false` and retaining the exact package-data allowlist removed implicit
  discovery without broadening artifact contents.
- Two clean `SOURCE_DATE_EPOCH=0` builds produced identical wheels but non-identical sdists because
  generated directories/metadata retained build timestamps. The sdist tar headers also recorded
  local owner/group identity; the artifact was kept in `/tmp` and was not uploaded.
- The initial ARA-028 regression produced the expected four failures for stale worktree,
  active-task, recursive-closeout, and fallback claims. Independent review then exposed two omitted
  resume-state checks; the strengthened test failed until both cross-file inconsistencies were fixed.
- One stale-wording audit placed a backticked task-state token inside a double-quoted zsh pattern,
  causing a harmless `command not found`. A literal-safe rerun completed; no file or Git state changed.
- The first synthetic recursive-closeout classifier run had one incorrect expected string with an
  extra leading newline; the classifier output was correct, the fixture was fixed, and all six
  focused tests passed.
- The ARA-031 pre-fix regression failed all five invalid-config subcases as expected because resume
  did not raise and replaced the existing file. The first independent review then found JSON
  `null` still shared the missing-file sentinel; an identity-only sentinel and `null` regressions
  corrected that gap before final validation.

## Next Command

```bash
git status --short --branch
.venv/bin/python -m json.tool .codex/LAST_VALIDATION.json >/dev/null
.venv/bin/python scripts/check_repo_safety.py --staged
```

## Interruption Recovery

Read `.codex/RESUME_INSTRUCTIONS.md`, then compare this file with `git status --short --branch` and `git log --oneline -n 10`. Do not touch ignored runtime artifacts or the local `config.yaml`.

## Current Risks And Prohibitions

- Do not delete or rewrite ignored experiment artifacts, local logs, or private configuration.
- Do not remove the stale `.git/REBASE_HEAD` without an explicit cleanup decision; it is harmless while no rebase directory exists.
- Do not run paid-provider workflows without credential presence checks, a dry run, and an explicit cost cap.
- Do not change prompts, scoring semantics, provider behavior, benchmark results, or artifact interpretation as part of a maintenance-only fix.
- ARA-032 normalizes overall score selection, ranking, trend, average, delta, and their exported
  fields. It does not claim to sanitize arbitrary non-score metadata embedded in legacy artifacts.
- ARA-033 catches only explicit output argument expansion, parent resolution, and JSON-write
  failures. Analysis/comparison computation and terminal rendering errors remain visible runtime
  failures rather than being mislabeled as output-path problems.
- ARA-022 blocks static link/hard-link/special-node escapes and link-based active replacement within
  its registered boundary. It is not a hostile same-UID sandbox: real-directory entry replacement,
  post-open/new-temp hard-link races, trusted-anchor ancestors, and Windows active replacement are
  explicitly outside the guarantee.
- Keep ARA-023 scoped to manual-interrupt propagation, cooperative stop status, and the associated
  lock lifecycle; the separately completed ARA-004 packaging behavior must not be folded into it.
- Do not publish ARA-004's temporary sdist: its tar metadata contains the local builder owner/group
  and generated timestamps are not reproducible. ARA-026 owns that release-hardening work.
- A pip build review created one cache entry under the user's pip cache containing a pre-fix wheel.
  It is not tracked and was not deleted because cleanup was not authorized; never treat it as a
  release artifact.
- ARA-022 changes the filesystem trust/write policy and is high risk. Owner approval was received;
  preserve configured `runs/` storage-link compatibility and fail closed on unsupported no-follow
  primitives rather than silently widening the trust boundary.
- Do not start ARA-029 without explicit CI-configuration approval or ARA-030 without its separate
  greater-than-30-minute approval checkpoint; keep release policy out of both scopes.
- Do not stage with `git add -A`; stage only reviewed paths.
