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

## 2026-07-11 - Gemini HTTP transport timeout enforcement

- Verified against installed `google-genai 2.7.0` that Client-level `http_options.timeout` is the
  supported public transport setting and uses milliseconds.
- Reproduced explicit-key, custom-environment, and SDK-default credential paths all omitting the
  configured timeout before the fix.
- Passed `timeout_seconds * 1000` to all three Client construction paths without changing model,
  prompt, temperature, top-p, structured-response configuration, or credential selection.
- Classified built-in/httpx-style transport timeouts and HTTP 408/504 as privacy-safe `timeout`
  errors while preserving the existing retry rule (native timeout/408 false, existing 504 true).
- Added negative coverage so unsupported timeout options and misleading exception class names are
  not mislabeled as network timeouts; exact configured credentials remain redacted from events and
  displayed traceback chains.
- Focused regression passed with `46 passed, 44 subtests passed`; final `make check` passed with
  `206 passed, 134 subtests passed`.
- Multiple independent SDK, compatibility, and adversarial reviews reported green after two
  reproduced timeout-classification false positives were corrected.
- Committed implementation, tests, and changelog as `817b8a1` and recovery state as `be37216`;
  pushed both and verified exact local/remote SHA equality.
- Updated draft PR 13 and confirmed Python 3.10/3.13 passed for both push and pull-request triggers.

## 2026-07-11 - Reliable CLI startup exit status and malformed-input boundaries

- Reproduced config, project, provider prerequisite, and survey/mock/normal lock errors printing a
  diagnostic but returning process status 0 through both supported CLI entrypoints.
- Made handled startup refusals status 2 and explicit failed cloud discovery status 1 while keeping
  help, successful provider-free analysis, and documented profile fallback status 0.
- Converted invalid/unreadable config and task input into privacy-safe errors and made tolerant
  checkpoint/cloud-cache readers handle invalid UTF-8, parser size/depth failures, wrong structure,
  invalid record fields, and bounded numeric provenance without traceback.
- Added an iterative resume-history depth guard so parsed histories fail before writes rather than
  overflowing during semantic comparison or persistence.
- Added entrypoint subprocess, direct-main, input privacy, provider/lock, cache compatibility, and
  resume no-write regression coverage; kept constructor exceptions as status 1 with lock cleanup.
- Focused regression passed with `103 passed, 103 subtests passed`; final `make check` passed with
  `203 passed, 128 subtests passed`.
- Multiple independent adversarial reviews found and verified the decode/parser/schema/numeric/depth
  corrections; the final delta review was green.
- Committed implementation, tests, changelog, and developer documentation as `8845adf` and recovery
  state as `a513e4d`; pushed both and verified exact local/remote SHA equality.
- Updated draft PR 13 and confirmed Python 3.10/3.13 passed for both push and pull-request triggers.

## 2026-07-11 - Tracked repository privacy and secret gate

- Confirmed the only baseline privacy findings were four real local-account fragments in two
  tracked historical reports; no ignored artifact was opened and no provider/private-key finding
  was present.
- Reworded those records with explicit account-redaction language while preserving their historical
  conclusions and avoiding a false claim that a placeholder was the original scan input.
- Added a stdlib-only byte scanner for the tracked worktree and complete stage-0 index, with
  privacy-safe category/location output, high-confidence path/key rules, and self-test controls.
- Covered partial staging, untracked content, invalid UTF-8/NUL bytes, missing files, static links,
  parent-directory links, unsupported traversal capability, operational errors, and safe examples.
- Independent reviews reproduced an outside read through a linked parent and a swap race in the
  initial compatibility fallback; descriptor-relative no-follow traversal and unsupported-platform
  fail-closed behavior corrected both. Final quality review reported no release blocker.
- Added `make repo-safety`, wired both scan modes and the self-test into `make check` and CI, and
  documented its tracked-only and ignored-artifact boundary.
- Focused validation passed with `11 passed`; final `make check` passed with `217 passed, 134
  subtests passed`; worktree/index scans reported 91 tracked files and zero findings.
- Committed implementation as `2b6523c` and recovery state as `975559d`, pushed both, verified exact
  local/tracking/GitHub SHA equality, updated draft PR 13, and confirmed all four Python 3.10/3.13
  push and pull-request jobs passed, including the new safety step.

## 2026-07-11 - Historical benchmark stop-reason attribution

- Reproduced a historical target run whose own summary said `USER_STOP_REQUESTED` being mislabeled
  `MAX_ROUNDS` from a newer project checkpoint; the initial regression failed exactly once.
- Resolved stop reason from target-run summary, config, then legacy manifest, and accepted project
  checkpoint only when normalized root and any supplied run ID positively match the target.
- Rejected malformed/nonobject and conflicting checkpoint identity data rather than borrowing it;
  covered absolute, repository/project/runs-relative, path-only, and legacy ID-only forms.
- Made fixed metadata leaves reject symlinks, directories, and FIFOs, with descriptor identity checks
  before reads. Unknown, injected, private, or credential-shaped values render as `unknown`.
- Restricted reportable reasons to official `STOP_*` constants and verified all 10 current constants
  remain compatible.
- Multiple independent audits reproduced and then verified fixes for the attribution bug, external
  metadata reads, Markdown/private-text injection, and credential-shaped output; final review was green.
- Focused tests passed with `11 passed, 20 subtests passed`; final `make check` passed with `224
  passed, 154 subtests passed`; both safety scans reported 91 tracked files and zero findings.
- Committed implementation as `588e32c` and recovery state as `c893e63`, pushed both, verified exact
  local/tracking/GitHub SHA equality, updated draft PR 13, and confirmed all four Python 3.10/3.13
  push and pull-request jobs passed, including safety and test steps.

## 2026-07-11 - Manual interrupt process-status propagation

- Reproduced mock and provider CLI handlers swallowing `KeyboardInterrupt` and returning status 0;
  runner-consumed interrupts finalized resumable artifacts but also returned success.
- Made runner-caught manual interrupts propagate after checkpoint, run summary/config, and
  interrupted-report finalization, then translated them to status 130 at both CLI boundaries.
- Preserved cooperative `STOP_REQUESTED` as successful status 0 with `USER_STOP_REQUESTED`,
  resumable artifacts, and signal cleanup; shared resume/report fields do not determine status.
- Moved survey/mock/provider lock acquisition and error evaluation inside lifecycle `try/finally`
  blocks and verified real lock metadata is removed across the earliest post-acquisition interrupt.
- Added direct and end-to-end module status controls, runner artifact assertions, an actual
  provider-free safe-stop subprocess, and session final-report suppression after interruption.
- Documented the 0/1/2/130 contract and limited artifact-completeness promises to the runner's
  protected agent-execution phase.
- Related regression passed with `63 passed, 61 subtests passed`; final `make check` passed with
  `231 passed, 154 subtests passed`; both safety scans reported 91 tracked files and zero findings.
- Two independent reviews reported GO after closing lock-lifecycle and documentation-boundary
  findings. No provider, prompt, score, metric, artifact schema, experiment, or ignored project
  artifact changed.
- Committed implementation as `4cae84e` and recovery state as `37b3749`, pushed both, verified exact
  local/tracking/GitHub SHA equality, updated draft PR 13, and confirmed all four Python 3.10/3.13
  push and pull-request jobs passed, including safety and test steps.

## 2026-07-11 - Legacy run-manifest provenance across resume

- Reproduced resume replacing original manifest mode/model/drafting/start/project and unknown
  fields, while checkpoint preview accepted IDs inconsistent with the canonical run root.
- Made canonical `run_root.name` the single identity; explicit checkpoint/manifest IDs must match,
  while missing IDs derive safely and configured storage/canonical-ID aliases remain compatible.
- Parsed and snapshotted existing raw manifests before the first write, preserved creation-time and
  unknown fields, canonicalized ID/root/config pointers, and merged current resume metadata.
- Made malformed, invalid UTF-8, nonobject, overly nested, identity-conflicting, or unmergeable
  manifests fail without modifying config, manifest, checkpoint, round, or summary artifacts.
- Prevented valid sparse manifests from inheriting current resume mode/model/time/project, including
  across two consecutive resumes after run_config exists.
- Added full legacy, sparse/repeated, direct/alias/non-string/missing ID, fail-before-write, and
  consumer/UI compatibility regressions without provider calls or ignored repository artifacts.
- Focused tests passed with `4 passed, 10 subtests passed`; related tests passed with `119 passed,
  100 subtests passed`; final `make check` passed with `235 passed, 164 subtests passed`.
- Two independent reviews reported GO after the sparse-provenance correction; both safety scans
  reported 91 tracked files and zero findings.
- Committed implementation as `3b98c61` and recovery state as `c1e8c57`, pushed both, verified exact
  local/tracking/GitHub SHA equality, updated draft PR 13, and confirmed all four Python 3.10/3.13
  push and pull-request jobs passed, including safety and test steps.

## 2026-07-11 - Zero-round resume-session provenance

- Reproduced an existing zero-round checkpoint resuming at round 1 without a `resume_sessions`
  entry, while a genuinely new round-1 run correctly kept an empty list.
- Made session append depend on either existing higher-round compatibility or explicit
  `resume_existing_run` lifecycle metadata, without changing round execution or eligibility.
- Added direct builder and two-consecutive real resume coverage; each resume invocation appends
  exactly one round-1 session, while new-run and start-round-greater-than-1 controls remain correct.
- Related tests passed with `47 passed, 59 subtests passed`; final `make check` passed with
  `236 passed, 164 subtests passed`; both safety scans reported 91 files and zero findings.
- Independent focused review reported GO. No manifest, provider, prompt, score, metric, experiment,
  ignored artifact, or artifact schema behavior changed.
- Committed implementation as `b961070` and recovery state as `a3bef4d`, pushed both, verified exact
  local/tracking/GitHub SHA equality, and confirmed all four Python 3.10/3.13 push and pull-request
  jobs passed, including safety and test steps.

## 2026-07-11 - Current analytics and comparison documentation alignment

- Cross-checked the current quickstart roadmap against CLI comparison, single-run analytics, UI
  dashboard/comparison, structured timing/token metrics, resume metadata, and drafting-mode code and
  tests without opening ignored experiment artifacts.
- Reclassified completed comparison, analytics, Streamlit width, resume-preview, timing, estimated-
  token, and drafting-mode work as implemented instead of future priorities.
- Preserved explicit limitations around research-quality judgment, true provider cost, uncertainty,
  causal inference, lineage, novelty/diff, and advanced cross-run analysis.
- Kept README, CHANGELOG, and dated historical audit/gap reports unchanged so historical evidence
  remains intact.
- Independent final review found and then verified corrections for rubric-field attribution,
  lifecycle-action wording, exact drafting-mode names, and `final_session_report.md`; final result GO.
- Targeted stale-wording search and `git diff --check` passed; final `make check` passed with `236
  passed, 164 subtests passed`, and both safety scans reported 91 files with zero findings.
- Committed implementation as `15d9935` and recovery state as `6b59091`, pushed both, verified exact
  local/tracking/GitHub SHA equality, and confirmed all four Python 3.10/3.13 push and pull-request
  jobs passed, including safety and test steps.

## 2026-07-11 - Self-resolving committed recovery state

- Reproduced the structural mismatch across four closeout commits: each tracked state file embedded
  its parent SHA and permanently claimed pending/dirty work after the containing closeout was already
  pushed and CI-verified.
- Confirmed no repository runtime code consumes these fields, then preserved unknown external
  consumers by keeping schema version 1 and the legacy exact 40-hex fields.
- Added authoritative `current_head.ref: HEAD`, fixed no-shell resolution argv, live worktree-state
  sourcing, exact snapshot-base semantics, and a conservative exact verified fallback.
- Recorded ARA-005 closeout `3fa33a7` external evidence with remote equality plus push/PR event,
  workflow, `head_sha`, conclusion, and Python 3.10/3.13 job results.
- Removed recursive closeout, static dirty-worktree, and stale pending instructions from the current
  recovery path while retaining all historical evidence.
- JSON/ancestry/state consistency assertions, live CI evidence checks, `git diff --check`, and final
  `make check` passed (`236 passed, 164 subtests passed`; 91 tracked files, zero safety findings).
- Independent design review approved the additive model and identified four final synchronization
  blockers; all were corrected before the semantic snapshot commit.

## 2026-07-11 - Self-contained installed mock package resources

- Reproduced clean wheel and sdist mock startup failing with status 2 because repository-only
  `config.example.yaml` was unavailable in both neutral and unrelated-Git temporary workspaces.
- Added an exact six-file package-data allowlist, byte-identical canonical config/prompt/example-task
  resources, and explicit source/editable versus installed runtime-layout detection.
- Kept installed resources read-only, placed runtime state in the invocation workspace, prevented
  CWD prompt trust and foreign Git provenance, and preserved explicit/partial/custom selection
  semantics without creating `config.yaml`.
- Made implicit installed-mock sample seeding interruption-safe and race-safe with same-parent
  staging, flush/fsync, native atomic no-replace publication, fail-closed platform behavior, and
  owned-staging cleanup. Eight-way concurrency produced exactly one publisher in 50 repetitions.
- Added package-resource, CLI, mock, run-config, diagnostic, session, runner, byte-parity,
  no-clobber, fault-injection, concurrency, foreign-Git, and source/editable compatibility tests.
- Final `make check` passed with Ruff, imports, both repository-safety modes, and pytest (`246
  passed, 172 subtests passed in 3.79s`; staged safety scanned 99 tracked files with zero findings).
- Built and independently audited final wheel/sdist contents and RECORD; installed both into fresh
  source-excluded environments and passed console/module help/mock plus missing-config controls
  without mutating package files. Final wheel SHA-256 is
  `02462324be35135d2b875b4e6cd3d29ae06b71790ea65e55e72814260eb8050d`; final sdist SHA-256 is
  `3e5917f7b2e80be550a563b29a1ae856bc9a2e38488ccf793b5281d5f9d2afd4`.
- Independent artifact, code, compatibility, and adversarial reviews reported GO after correcting
  interrupted staging residue, source detection, POSIX target replacement, and cleanup-window
  findings. The temporary sdist was not published because tar owner/group and generated timestamps
  require ARA-026 release hardening.
- Committed implementation as `0aee55e`, pushed it, verified exact local/upstream/`ls-remote`
  equality with ahead/behind `0/0`, and confirmed push run `29148635379` plus pull-request run
  `29148637631` passed every Python 3.10/3.13 job. Draft PR 13 remains the maintenance PR.

## 2026-07-11 - Automatic artifact filesystem boundary

- Reproduced static leaf links, ancestor/nested symlink swaps, UI validation/read replacement,
  fresh-context metadata/log/stop-signal access, survey traversal escape, and cross-thread boundary
  loss only in temporary fixtures; ignored repository runtime remained untouched.
- Added a process-wide project boundary registry. Nested run roots inherit or rebase to the project
  anchor, while configured run storage outside the project receives its own physical anchor.
- Routed automatic POSIX reads, appends, atomic replacement, unlink, coordination files, directory
  creation, and pruned/stable survey traversal through descriptor-relative no-follow operations;
  rejected static symbolic links, hard-linked files, linked directories, and special nodes.
- Established self-contained boundaries for CLI, resume, survey/cloud, run locks, background
  processes, cooperative stop handling, and Streamlit live fragments without changing providers,
  prompts, scoring, experiment artifacts, conclusions, or schemas.
- Preserved configured external `runs/` storage, stale real-directory tolerance, explicit
  analyze/compare aliases, explicit export parents, and actionable lock/guard recovery diagnostics.
  Survey source paths intentionally retain lexical `abspath` spelling for safe reads.
- Documented the exact residual threat boundary: trusted ancestors, malicious same-UID replacement
  with another real directory, post-open/new-temp hard-link races, and Windows active replacement
  are not claimed as protected. Native Windows integration was not available.
- Final local `make check` passed with Ruff, imports, both repository-safety modes, and pytest (`294
  passed, 176 subtests passed`; 99 tracked files, zero findings). Independent implementation,
  adversarial, state-consistency, and documentation reviews reported GO.
- Initial Python 3.10 CI exposed only a test construction bug caused by creating `Path` while
  `os.name` was mocked to `nt`; Python 3.13 passed. Moved construction before the mock, reran the
  full gate, and committed the correction separately.
- Committed implementation as `544b26a` and the Python-3.10 portability fix as `93026ca`, pushed
  both, verified exact local/upstream/`ls-remote` equality, updated draft PR 13, and confirmed push
  run `29153023802` plus pull-request run `29153024964` passed every Python 3.10/3.13 job.

## 2026-07-12 - Persistent recovery-state consistency gate

- Recovered ARA-022 closeout `ca3a2e8` as a clean, remote-equal, CI-verified baseline, then confirmed
  its committed recovery snapshot still claimed uncommitted files and requested the already-finished
  closeout again.
- Added a focused regression that initially failed on stale worktree, active-task,
  recursive-closeout, and fallback claims, then expanded it after independent review to validate
  `CURRENT_STATE.md`, `TASK_QUEUE.md`, `RESUME_INSTRUCTIONS.md`, and `LAST_VALIDATION.json` together.
- Replaced authored dirty-file claims with live Git sourcing, removed task-owned recursive closeout
  steps, synchronized the exact conservative fallback, and preserved semantic `HEAD` as the
  authoritative current commit reference.
- Kept runtime code, ignored project state, provider behavior, artifacts, experiments, dependency,
  license, version, and publication policy unchanged.
- Final staged `make check` passed with Ruff, imports, both repository-safety modes, and pytest
  (`300 passed, 177 subtests passed in 9.07s`; 100 tracked files and zero findings).
- Independent final staged review returned GO with no remaining blocker after directly exercising
  both unattributed commit/push counterexamples and the explicit fallback-label parser.

## 2026-07-12 - Fail-before-write invalid run-config resume handling

- Reproduced a provider-free zero-round resume replacing malformed existing `run_config.json` with
  newly generated provenance while no agent was invoked.
- Added strict existing-config mode only for resume. Invalid JSON, invalid UTF-8, arrays, `null`,
  excessive nesting, and read failures now produce path-safe `ResumeHistoryError` failures before
  any automatic artifact write; a truly missing file still falls back to the legacy manifest.
- Added unit compatibility coverage plus an end-to-end preservation matrix that keeps config,
  manifest, checkpoint, and stop-signal bytes unchanged, creates no log/history/summary/metrics/
  round artifacts, and invokes no agent.
- Independent review found and reproduced a JSON `null`/missing sentinel collision; an identity-only
  sentinel and `null` regressions corrected it before final validation. Both final reviews are GO.
- Focused validation passed (`7 passed, 14 subtests passed`); complete run-config/round-loop tests
  passed (`53 passed, 66 subtests passed`); local `make check` passed (`303 passed, 184 subtests
  passed`; 100 tracked files and zero safety findings).

## 2026-07-12 - Finite score analysis and comparison boundary

- Reproduced provider-free malformed scores dominating comparison ranking, producing a false flat
  trend, and escaping analysis/comparison files as non-standard `NaN`/`Infinity` JSON.
- Rejected booleans, non-finite values and strings, and unrepresentably large numeric scores while
  preserving finite legacy numeric strings and negative scores.
- Made score presence the first ranking key so missing scores cannot outrank valid negative scores;
  preserved score and completed-round ordering for otherwise comparable runs.
- Converted overflowed trend/baseline deltas to `null` while preserving finite endpoint direction.
- Retained the historical finite-total average operation and added an overflow-only scaled
  `math.fsum` fallback, so ordinary two-decimal results stay unchanged and representable extreme
  averages remain finite.
- Added strict-JSON, huge-integer, negative-ranking, finite-extreme, and historical-rounding
  regressions. Related tests passed `26 passed`; final `make check` passed `309 passed, 184 subtests
  passed` with 100 tracked files and zero safety findings.
- Two independent adversarial reviews returned GO after finding and driving fixes for the missing
  negative-score rank, derived overflow, maximum-float average, and ordinary 0.01 rounding drift.

## 2026-07-12 - Privacy-safe analysis and comparison output failures

- Reproduced both module entrypoints returning status 1 with a full traceback and temporary/repo
  absolute paths when an explicit output parent was an ordinary file. Unresolved `~user` output
  paths produced the same leak through path expansion.
- Kept the documented operation-failure status 1 and added fixed analysis/comparison output error
  messages without exception text, traceback, or path content.
- Scoped catches to explicit output argument expansion, parent resolution, and JSON writing; lower
  analysis/comparison helpers, storage exceptions, console rendering, successful output, and
  explicit output-parent symlink authorization remain unchanged.
- Focused subprocess tests passed `2 passed, 4 subtests passed`; related
  CLI/analysis/comparison/storage tests passed `72 passed, 22 subtests passed`; local `make check`
  passed `311 passed, 188 subtests passed` with 100 tracked files and zero safety findings.
- Two independent final reviews returned GO after running failure, success, and symlink matrices.

## 2026-07-12 - Explicit resume eligibility and finite preview score

- Reproduced malformed checkpoint values `"false"`, `"true"`, and integer `1` being treated as
  resume-eligible; the end-to-end control invoked all agent stages, wrote a new round, and replaced
  the explicitly ineligible checkpoint.
- Reproduced a 400-digit preview score raising `OverflowError`, while Infinity and NaN propagated
  into resume metadata.
- Required checkpoint `can_resume` to be the literal JSON boolean `true`; every other type now
  returns the existing ineligible-checkpoint result before runner or agent-stage invocation and
  before any project artifact write.
- Made preview score conversion catch unrepresentable integers and reject non-finite or boolean
  values while preserving finite legacy numeric strings and the existing `-1.0` safe default.
- Added direct preview, byte-preservation end-to-end, and real module CLI regressions. The CLI test
  verifies status 2, no traceback, no agent access, unchanged checkpoint bytes, no run config, and
  released run lock.
- Focused tests passed (`3 passed, 11 subtests passed`); related resume/CLI/UI tests passed (`137
  passed, 114 subtests passed`); full `make check` passed (`314 passed, 199 subtests passed`; 100
  tracked files and zero safety findings).
- Two independent final reviews returned GO after checking literal-type semantics, valid-checkpoint
  compatibility, finite-score behavior, artifact preservation, CLI exit status, and lock release.
- Committed as `bdbd9d5`, pushed with exact local/upstream/`ls-remote` equality, updated draft PR
  13, and confirmed push run `29163467415` plus pull-request run `29163468552` passed every Python
  3.10/3.13 job.

## 2026-07-12 - Finite legacy metric aggregation and strict JSON

- Reproduced provider-free analysis/comparison status-0 output containing Infinity for timing,
  evolution, and rubric derived values; `10**400` timing/rubric/evolution and numeric NaN/Infinity
  token counters instead raised conversion exceptions with traceback.
- Made required additive float values use the existing zero default when malformed/non-finite and
  optional values become unavailable. Float/int conversion now catches unrepresentable inputs.
- Propagated unrepresentable elapsed totals as `None` across the within-round cross-agent,
  cross-round overall, and per-agent cross-round accumulation layers.
- Preserved ordinary sum/round behavior and used a scaled finite average only when ordinary
  evolution/rubric summation overflowed; unrepresentable score/rubric deltas become `None`.
- Filtered invalid raw `run_summary.json` rubric averages while retaining finite numeric strings and
  unknown finite keys. Evolution numeric strings remain ignored, token floats retain truncation,
  exact huge integers remain exact, and no positivity/range clamp was introduced.
- Added strict direct/API/writer/real-CLI matrices for numeric/string NaN/Infinity, `10**400`,
  cross-agent/cross-round overflow, malformed agent leaves, raw summary fallback, and compatibility
  controls. Analysis and comparison both return status 0 without traceback and write strict JSON.
- Related tests passed `59 passed, 20 subtests passed`; broad affected regression passed `172
  passed, 116 subtests passed`; local `make check` passed `321 passed, 201 subtests passed` with 100
  tracked files and zero findings.
- One independent review found a non-Mapping agent leaf traceback; it received direct/CLI coverage
  and a minimal empty-mapping fallback. Both final independent reviews returned GO.
- Committed as `a99723c`, pushed with exact local/upstream/`ls-remote` equality, updated draft PR
  13, and confirmed push run `29164052624` plus pull-request run `29164053862` passed every Python
  3.10/3.13 job.

## 2026-07-12 - Unrepresentable structured Judge numbers

- Reproduced a 400-digit structured Judge score raising `OverflowError` after Judge output was saved
  but before the runner could enter its existing invalid-score path; rubric coercion had the same
  conversion gap.
- Added parser coverage proving an invalid structured score still permits the existing trailing
  legacy `SCORE:` fallback and invalid rubric entries are omitted without losing valid siblings.
- Caught conversion `TypeError`/`ValueError`/`OverflowError` at the shared score/rubric coercion
  boundary while preserving boolean/non-finite rejection, finite numeric strings, and 0..100 clamp.
- Reproduced Python 3.11+ `json.loads` raising plain `ValueError` for a 5000-digit numeric literal;
  both structured score and payload/rubric parse entrypoints now treat that as invalid JSON. Python
  3.10 parses the integer and is covered by the float-overflow boundary.
- Added a real round-loop control proving the run stops with `INVALID_SCORE`, preserves trusted best
  output, records an invalid unsuccessful round, and retains the valid rubric sibling.
- Related Judge/round-loop tests passed `52 passed, 75 subtests passed`; local `make check` passed
  `323 passed, 201 subtests passed` with 100 tracked files and zero findings. Independent final
  review returned GO.
- Committed as `3d13b2f`, pushed with exact local/upstream/`ls-remote` equality, updated draft PR
  13, and confirmed push run `29164348550` plus pull-request run `29164349968` passed every Python
  3.10/3.13 job.

## 2026-07-12 - Literature survey manual-interrupt exit contract

- Reproduced a survey `KeyboardInterrupt` exiting the real module process with signal status `-2`
  and a traceback containing source paths; the existing `finally` still released the run lock.
- Added a survey-local interrupt boundary that prints a fixed `MANUAL_INTERRUPT` diagnostic and
  raises the existing CLI interrupted status 130 before the unchanged lock-release `finally`.
- Updated the direct lock-result interrupt control and added a real `src.main` subprocess using the
  actual run lock; it proves status 130, no traceback, fixed diagnostic, and lock removal.
- Preserved successful survey status 0 and the existing path-safe artifact-I/O status 1 behavior.
- Focused tests passed `2 passed`; related survey/CLI tests passed `36 passed, 20 subtests passed`;
  local `make check` passed `324 passed, 201 subtests passed` with 100 tracked files and zero
  findings. Independent final review returned GO.
- Committed as `cd21143`, pushed with exact local/upstream/`ls-remote` equality, updated draft PR
  13, and confirmed push run `29164609427` plus pull-request run `29164610776` passed every Python
  3.10/3.13 job.

## 2026-07-12 - Cloud-free lazy discovery and artifact-write containment

- Reproduced a fake SDK pager yielding one model before raising outside the discovery error tuple;
  explicit discovery leaked a traceback, and profile mode could not enter its documented configured-
  seed fallback.
- Reproduced `OSError` at explicit discovery save, profile discovery-cache save, successful profile
  result save, and discovery-error fallback profile save; all four leaked traceback/path details.
- Consumed lazy model iterators and converted model records inside a safe classified-error boundary.
  Iterator acquisition alone retains compatibility with legacy non-iterable `.models` wrappers, so
  iterator-time `TypeError` cannot become a false-success empty discovery.
- Converted each automatic discovery/profile artifact-write `OSError` to status 1 with one fixed,
  path-free diagnostic. Explicit discovery remains status 1, and profile discovery failure retains
  status-0 configured-seed fallback when profiling and result persistence succeed.
- Focused tests passed `3 passed, 6 subtests passed`; related cloud-free/CLI tests passed `50 passed,
  34 subtests passed`; local `make check` passed `326 passed, 207 subtests passed` with 100 tracked
  files and zero findings. Two independent final reviews returned GO; no provider call was made.
- Committed as `25ae39b`, pushed with exact local/upstream/`ls-remote` equality, updated draft PR
  13, and confirmed push run `29165142777` plus pull-request run `29165143905` passed every Python
  3.10/3.13 job.

## 2026-07-12 - Fail-before-write prior-round resume context handling

- Reproduced invalid UTF-8 and injected read failures in the previous round's Judge context being
  silently converted to empty text after new run config, log, and manifest content had been written;
  resume then invoked the draft agent instead of failing safely.
- Replaced the tolerant context reader with a resume-specific boundary: genuinely missing leaves or
  an entirely missing legacy round directory remain empty, while other I/O and Unicode failures
  become a basename-only `ResumeHistoryError` with suppressed exception chaining.
- Preloaded draft, review, revised, and Judge context once after path checks and before any startup
  artifact write or agent invocation; the later round loop reuses those in-memory values.
- Added a four-file by two-error matrix proving every existing file remains byte-identical, no new
  round directory or automatic file is created, agents are not called, and exception/console output
  contains no temporary path. A missing-parent legacy control proves compatibility.
- Focused tests passed `4 passed, 8 subtests passed`; related round-loop/CLI tests passed `80 passed,
  107 subtests passed`; local `make check` passed `328 passed, 215 subtests passed` with 100 tracked
  files and zero findings. Two independent final reviews returned GO; no provider call was made.
- Committed as `9191a35`, pushed with exact local/upstream/`ls-remote` equality, updated draft PR
  13, and confirmed push run `29165593346` plus pull-request run `29165594723` passed every Python
  3.10/3.13 job.

## 2026-07-12 - Cached cloud discovery/profile membership reconciliation

- Reproduced a true two-process disk round trip: stale discovery retained `gemma-3-high-tpm`, a new
  discovery-error fallback profile covered only the default seeds, and the next process recommended
  the stale unprofiled Gemma.
- Added a non-destructive cached-candidate guard shared by CLI and UI recommendation. Empty/missing
  profiles preserve discovery-only compatibility; exact unique profile/candidate membership retains
  discovery metadata; every mismatch ignores discovery and keeps only current configured candidates
  also represented by safe profile IDs.
- Reclassified cached discovery records under the current allow/block policy before membership
  comparison, so artifact-era or forged safe flags cannot override current configuration. Duplicate,
  unsafe, partial, and noncanonical `models/...` profile IDs all take the conservative mismatch path.
- Kept explicit discovery/profile commands on their in-memory candidate pool and made no artifact
  schema, file, deletion, migration, provider, selection preset, or historical artifact change.
- Focused/two-process and compatibility controls plus cloud-free/CLI/UI/recovery tests passed `120
  passed, 56 subtests passed`; local `make check` passed `329 passed, 215 subtests passed` with 100
  tracked files and zero findings. Two independent final reviews returned GO; no provider call was
  made.
- Committed as `ba4b2c1`, pushed with exact local/upstream/`ls-remote` equality, updated draft PR
  13, and confirmed push run `29166208230` plus pull-request run `29166209758` passed every Python
  3.10/3.13 job.

## 2026-07-12 - All-blocked cloud recommendation handling

- Reproduced unreachable, daily-quota, billing/safety, and token-context profiles being excluded
  from scoring but immediately selected again by the no-scored-candidate fallback; all four controls
  failed before the fix.
- Reused one blocking predicate across Quality's fast path, normal Auto/Quality/Volume scoring, and
  `choose_fallback_model`, including profile-level unsafe-text results. When every candidate is
  blocked, both automatic recommendation and runtime fallback now return no selection.
- Preserved healthy, missing-profile, ordinary rate-limited, and mixed blocked/unprofiled behavior;
  Manual remains no automatic recommendation. UI keeps the picker/manual effective model and now
  distinguishes Manual mode from a non-manual no-eligible result.
- Related cloud-free/CLI/UI/recovery tests passed `121 passed, 68 subtests passed`; local `make
  check` passed `330 passed, 227 subtests passed` with 100 tracked files and zero findings. Two
  independent final reviews and extended property matrices returned GO; no provider call was made.
- Committed as `685a36c`, pushed with exact local/upstream/`ls-remote` equality, updated draft PR
  13, and confirmed push run `29166629408` plus pull-request run `29166630511` passed every Python
  3.10/3.13 job.

## 2026-07-12 - CI least-privilege and runtime boundary

- Added a workflow contract regression that initially failed three checks because token permissions
  and job timeout were absent and checkout still used a deprecated Node 20 action major.
- Restricted the workflow token to `contents: read`, asserted that the test job cannot override that
  boundary, and capped each matrix job at 15 minutes while preserving its triggers, branches,
  Python 3.10/3.13 matrix, pip cache, install command, and validation steps.
- Updated only the JavaScript action majors to official current Node 24 releases:
  `actions/checkout@v7` and `actions/setup-python@v6`. Dependency, immutable action pinning, wheel
  smoke, release, publication, application, provider, and artifact policy remain separate.
- CI/recovery contract tests passed `10 passed, 1 subtest passed`; local `make check` passed `334
  passed, 227 subtests passed` with zero safety findings. Two independent reviews returned GO;
  `actionlint` was unavailable and was not installed, so GitHub's four real jobs remain the final
  publication validation.
- Committed as `6f03ec8`, pushed with exact local/upstream/`ls-remote` equality, updated draft PR
  13, and confirmed push run `29180344621` plus pull-request run `29180345488` passed every Python
  3.10/3.13 job with zero annotations.

## 2026-07-12 - Project- and artifact-scoped UI cloud cache

- Reproduced global Streamlit discovery/profile lists retaining the first project's data across an
  A-to-B switch and ignoring external same-model-ID metadata changes; both controls failed before
  the helper existed.
- Bound the two lists to one joint identity containing the validated canonical project path,
  device/inode, and safe SHA-256 content states for both artifacts. Missing, unreadable, and unsafe
  content receives non-content sentinels without exposing file content or paths.
- On a miss, old session state is cleared before loading; the joint identity is rechecked, retried
  once if it changes, and never committed when instability persists. UI-owned saves invalidate the
  identity before publishing their new in-memory list.
- Added provider-free regressions for A-to-B-to-A switching, legacy global session values,
  equal-length same-inode/size/mtime content rewrites, blocked-to-healthy recommendation refresh,
  stable retry, persistent-instability fail-empty, unreadable recovery, and unsafe symlink clearing.
- Related UI/cloud-free/recovery tests passed `97 passed, 44 subtests passed`; local `make check`
  passed `339 passed, 227 subtests passed` with zero safety findings. Two independent final reviews
  returned GO; no provider call, artifact/schema migration, or ignored runtime access occurred.
- Committed as `609de6c`, pushed with exact local/upstream/`ls-remote` equality, updated draft PR
  13, and confirmed push run `29180830633` plus pull-request run `29180831707` passed every Python
  3.10/3.13 job with zero annotations.

## 2026-07-12 - Target-scoped UI health snapshots

- Confirmed raw Ollama/Gemini health dicts remained under provider-global session keys and could be
  displayed after changing the effective model or Ollama endpoint. The new provider-free scoped
  snapshot regression failed before the helper existed.
- Wrapped each result with normalized provider/model and a non-secret connection identity. Ollama
  scope normalizes scheme/host/default port, allowlists only fixed safe path labels, redacts all
  other path values, and records only the presence of userinfo/query. Gemini scope follows the
  actual session/config/custom-env/Google/Gemini source order without storing or hashing key values.
- Legacy, malformed, mismatched, unknown-message, and missing-format-argument snapshots are evicted.
  Same-target success or failure remains visible; target/source changes disappear. Password/env
  widget changes and Ollama model refresh explicitly invalidate their snapshots.
- Sanitized Ollama/Gemini health errors to fixed endpoint/type details before session storage.
  Whitespace-only Gemini password input no longer masks a valid configured key, and the same
  resolved inline key is used by discovery, profiling, and health operations.
- Related UI/recovery tests passed `75 passed, 30 subtests passed`; local `make check` passed `340
  passed, 235 subtests passed` with zero safety findings. Two independent final reviews returned GO;
  no real provider/network call, credential persistence/hash, configuration write, or artifact
  change occurred.
- Committed as `dbf8e24`, pushed with exact local/upstream/`ls-remote` equality, updated draft PR
  13, and confirmed push run `29181528872` plus pull-request run `29181529568` passed every Python
  3.10/3.13 job with zero annotations.

## 2026-07-12 - Gemini effective-key and exception-graph redaction

- Reproduced the SDK selecting `GOOGLE_API_KEY` while wrapper redaction selected
  `GEMINI_API_KEY` when both were populated. Separate provider-free controls exposed the used key
  in provider events and through an implicit exception `__context__`.
- Added one request-scoped credential snapshot for explicit, custom, Google-only, Gemini-only,
  both-built-in, missing-custom fallback, and raw-truthy whitespace Google sources. Explicit/custom
  values remain direct SDK arguments; built-in values remain delegated to google-genai.
- Redacted every captured candidate before provider-event persistence, exception construction, SDK
  client-initialization wrapping, and cloud-discovery truncation. Short and overlapping candidate
  values are handled longest-first; the existing missing-dependency diagnostic is preserved.
- Provider-free LLM/cloud/security tests passed `53 passed, 33 subtests passed`; related
  UI/LLM/cloud/recovery tests passed `116 passed, 61 subtests passed`; final local `make check`
  passed `346 passed, 246 subtests passed` with zero repository-safety findings. Two independent
  final reviews returned GO and no real provider or ignored runtime artifact was accessed.
- Committed the implementation, tests, and changelog as `938b9a2` and recovery state as `47c0c26`.
  Pushed with exact local/upstream/`ls-remote` equality, updated draft PR 13 with exact body readback,
  and confirmed push run `29182280005` plus pull-request run `29182281056` passed every Python
  3.10/3.13 job with zero annotations.
- Pushed final remote-verification state closeout `510ef84`; push run `29182427059` and pull-request
  run `29182428029` passed every Python 3.10/3.13 job with zero annotations, and draft PR 13 was
  updated with exact readback at the final HEAD.

## 2026-07-12 - Recoverable resume startup metadata

- Reproduced `run_config.json` advancing to a new running resume session when the following
  `run_manifest.json` write failed before any agent ran.
- Added a fixed hidden write-ahead journal for the two existing-run startup files. It stores exact
  prior text and before/after SHA-256 values, restores pre-commit failures idempotently, recovers a
  surviving journal before logging or agent work, and fails closed on malformed/conflicting state.
- Covered journal/config/manifest writes, `KeyboardInterrupt`, unlink-before/after failures,
  interrupted rollback and retry, every reachable mixed disk generation, legacy missing/sparse
  artifacts, external hash conflicts, unsafe journal leaves, no-agent/no-log guarantees, and the
  unchanged new-run write order.
- Documented provider/client initialization ordering, unlink commit semantics, zero-work sessions,
  parent-directory durability limits, and the cooperative-lock same-UID TOCTOU boundary.
- Targeted tests passed `8 passed, 50 deselected, 20 subtests passed`; related runner/config/storage
  tests passed `90 passed, 103 subtests passed`; local `make check` passed `353 passed, 262 subtests
  passed` with zero safety findings. Two independent reviews and focused re-reviews were green.
- Committed implementation/docs/tests/changelog as `2480a61` and validation state as `877562e`.
  Exact local/upstream/`ls-remote` equality was verified; push run `29187626378` and pull-request run
  `29187628011` passed Python 3.10/3.13 with zero annotations.

## 2026-07-13 - Isolated real-wheel CI smoke

- Reproduced that the CI matrix installed only the editable checkout and that the installed-layout
  unit fixture copied `src`, leaving build-backend, entry-point, wheel package-data, and RECORD
  regressions outside the recurring gate.
- Added a standard-library helper that copies only explicit tracked inputs to an external temporary
  source tree, builds exactly one wheel, installs it with dependencies into a fresh venv, and checks
  source-excluded/non-editable import origin, exact six-resource bytes/RECORD, console/module help,
  one deterministic mock round, null foreign-Git provenance, and package-tree immutability.
- Closed review-found ambient pip/Git/temp redirect and child-output risks with minimal environments,
  isolated pip/Git config, checkout-local temp rejection, fixed diagnostics, dead runtime proxies,
  and one 600-second deadline. A hostile-environment real smoke passed without creating its guard
  path, using pip cache, calling a provider, touching ignored runtime, building an sdist, or upload.
- Targeted tests passed `19 passed, 23 subtests passed`; final local `make check` passed `359 passed,
  277 subtests passed` with 103 tracked/index files and zero findings. Three independent final
  reviews reported no P0/P1/P2 blocker.
- Committed implementation/workflow/tests/docs/recovery state as `4cda430` and pushed with exact
  local/upstream/`ls-remote` equality. Push run `29232341316` and PR run `29232344581` passed every
  Python 3.10/3.13 job, all four real-wheel steps, and zero annotations.

## 2026-07-13 - Ollama endpoint failure redaction

- Reproduced URL userinfo, private path, and query values escaping through Ollama public errors,
  provider events, linked request exceptions, API fallback diagnostics, and failed `ollama list`
  output using only mocked requests and temporary files.
- Added one safe endpoint formatter: ordinary IPv4/IPv6 and IDN hosts retain an origin label, while
  invalid ports, delimiter ambiguity, encoded/scoped authorities, and backslashes fail to a fixed
  placeholder without changing the accepted URL or actual request target.
- Replaced provider-controlled requests/urllib/command error text with fixed timeout, HTTP-status,
  invalid-JSON, or request-failure classifications and raised only after leaving the raw exception
  handler, preventing credential recovery through `__cause__` or `__context__`.
- Preserved request URLs/timeouts, ordinary public error wording, event fields/error types, model
  discovery return shape, and healthy response parsing. No real provider, ignored runtime, config,
  experiment artifact, score, prompt, or research result was accessed or changed.
- Related config/LLM/UI/CLI tests passed `138 passed, 129 subtests`; final `make check` passed `366
  passed, 310 subtests` with 103 tracked/index files and zero findings. Two independent final reviews
  reported GO with no remaining P1/P2 blocker.
- Committed as `3f3826b`, pushed with exact local/upstream/`ls-remote`/PR-head equality, and updated
  draft PR 13. Push run `29250140431` and pull-request run `29250143238` passed Python 3.10/3.13,
  every isolated-wheel step, and all four job annotation sets are empty.

## 2026-07-13 - Unrepresentable resume-history score boundary

- Reproduced positive and negative 400-digit JSON scores escaping dual-history resume as raw
  `OverflowError`, then found the `round_metrics.json`-only legacy path silently ignored the same
  values and continued into agent work and artifact writes.
- Converted overflow to the existing invalid-history result and rejected explicit native numeric
  scores that cannot become finite floats for any round not explicitly marked unsuccessful.
  Finite scores, legacy numeric strings, missing/bool scores, and explicit unsuccessful rounds keep
  their prior read behavior.
- Added dual- and single-history positive/negative regressions, complete temporary-project byte
  snapshots, no-agent/no-new-round/path-safe checks, CLI status-2 and lock-release coverage, plus
  explicit unsuccessful-round compatibility.
- Focused tests passed `4 passed, 20 subtests`; related resume/CLI/recovery tests passed `95 passed,
  130 subtests`; final `make check` passed `368 passed, 316 subtests` with 103 tracked/index files
  and zero safety findings. Three independent final reviews returned GO with no P1/P2 blocker.
- Committed as `d7708b3` and pushed with exact local/upstream/`ls-remote`/PR-head equality. Push run
  `29251545910` and pull-request run `29251548644` passed Python 3.10/3.13, every isolated-wheel
  step, and all four job annotation sets are empty.

## 2026-07-13 - Conflicting primary CLI mode rejection

- Reproduced all 45 pairs of ten primary selectors being accepted in both argument orders. Direct,
  module, and copied-installed entrypoints also continued beyond parsing; a temporary
  `--mock --resume` probe selected mock mode and replaced its temporary checkpoint.
- Placed only the ten primary selectors in one optional `argparse` mutually exclusive group.
  Normal mode, each selector alone, and ordinary output/runtime modifiers retain their prior
  behavior; orphan mode-specific output options remain the separate ARA-057 task.
- Added 90 pair/order subtests plus compatible-mode, direct/module pre-runtime, and copied-installed
  no-write/package-hash controls. Focused tests passed `6 passed, 100 subtests`; related tests passed
  `122 passed, 238 subtests`; final `make check` passed `373 passed, 416 subtests` with 103 tracked
  files and zero safety findings. Three independent reviews returned GO.
- Committed as `1ab338a` and pushed with exact local/upstream/`ls-remote`/PR-head equality. PR run
  `29253180079` passed Python 3.10/3.13. Push run `29253175885` reached final success after retrying
  one Python 3.13 pre-checkout GitHub HTTP 503 action-download outage; all four final wheel steps
  passed and all four annotation sets are empty. Draft PR 13 was updated with exact normalized
  readback.

## 2026-07-13 - Authoritative UI session credential for child runs

- Reproduced Streamlit health/discovery selecting the password-box key while the launched child
  selected an explicit config key or inherited `GOOGLE_API_KEY` instead.
- Added a fixed child-only environment transport plus a hidden activation option carrying only its
  environment variable name. Nonempty sessions now become the explicit key for preflight, cloud
  helpers, and real client creation; empty sessions clear stale transport state without activation.
- Preserved config/custom/Google/Gemini no-session precedence and ARA-045 provider-error redaction.
  Synthetic provider-free tests prove the key is absent from argv and process metadata, activated
  session values beat every competing source, and stale unactivated transport remains inert.
- Focused tests passed `4 passed, 10 subtests`; related UI/CLI/LLM/cloud/recovery tests passed `157
  passed, 127 subtests`; final `make check` passed `376 passed, 426 subtests` with 103 tracked/index
  files and zero findings. Three independent reviews returned GO.
- Committed as `d75fe11` and pushed with exact local/upstream/`ls-remote`/PR-head equality. Push run
  `29255525721` and pull-request run `29255530241` passed Python 3.10/3.13, every isolated-wheel
  step, and all four annotation sets are empty. Draft PR 13 remains open, draft, mergeable, and its
  normalized body readback is exact.

## 2026-07-13 - Installed generation resource preflight

- Reproduced installed deterministic mock generation succeeding with a missing prompt and writing
  incomplete prompt provenance.
- Added anchored, no-follow, stable-identity validation for all four nonblank UTF-8 generation
  prompts before config, seeding, provider startup, locks, or artifacts in the six prompt-consuming
  modes. Analysis, comparison, survey, and cloud helpers preserve their prompt-independent paths.
- Preserved valid hardlink-based package installations while keeping automatic artifact reads
  single-link by default; symlink and special-node rejection remains intact.
- Focused tests passed `5 passed, 23 subtests`; related tests passed `92 passed, 71 subtests`;
  isolated real-wheel smoke and final `make check` (`381 passed, 449 subtests`) passed. Three
  independent final reviews returned GO.
- Committed as `be3bc04` and pushed with exact local/upstream/`ls-remote`/PR-head equality. Push run
  `29257476266` and pull-request run `29257478876` passed Python 3.10/3.13, every isolated-wheel
  step, and all four job annotation sets are empty. Draft PR 13 remains open, draft, and mergeable.

## 2026-07-13 - Conflicting duplicate cloud profile handling

- Reproduced cached pooling retaining a duplicate-conflicted model in both orders and
  blocked-then-healthy ordering re-enabling it across auto/quality/volume recommendation and
  fallback.
- Added one exact-ID profile index that marks non-identical parsed duplicate records conflicted and
  explicitly excludes only those IDs from cached pooling, recommendation, and fallback.
- Preserved different-instance value-equivalent duplicates, unique healthy cohort candidates,
  unprofiled safe alternatives, exact legacy IDs, ARA-040 reconciliation, and ARA-043 all-blocked
  behavior without changing artifacts or schemas.
- Focused tests passed `4 passed, 22 subtests`; related cloud/CLI/UI/recovery tests passed `139
  passed, 127 subtests`; final `make check` passed `383 passed, 459 subtests`. Three independent
  final reviews returned GO.
- Committed as `ab7d6fe` and pushed with exact local/upstream/`ls-remote`/PR-head equality. Push run
  `29258640040` and pull-request run `29258641820` passed Python 3.10/3.13, every isolated-wheel
  step, and all four job annotation sets are empty. Draft PR 13 remains open, draft, and mergeable.

## 2026-07-13 - Malformed Ollama health response normalization

- Reproduced valid top-level list, string, number, boolean, and null JSON reaching
  `payload.get(...)` and raising `AttributeError` rather than returning UI health state.
- Added one post-decode `Mapping` guard that returns the existing localizable unhealthy result with
  a fixed `InvalidResponse` classification and the already-redacted display endpoint.
- Preserved valid and empty mapping behavior, exact request URL/timeout, private endpoint redaction,
  and ARA-044 target-scoped health snapshots. Provider-controlled response content is never stored
  or rendered by the new branch.
- Focused tests passed `3 passed, 14 subtests`; related config/UI/recovery tests passed `96 passed,
  92 subtests`; final `make check` passed `384 passed, 465 subtests`. Three independent reviews
  returned GO.
- Committed as `2141b7d` and pushed with exact local/upstream/`ls-remote`/PR-head equality. Push run
  `29259494746` and pull-request run `29259495850` passed Python 3.10/3.13, every isolated-wheel
  step, and all four job annotation sets are empty. Nested malformed `models` values remain queued
  separately as ARA-058.

## 2026-07-13 - Mode-specific output dependency rejection

- Reproduced all three output options being accepted in normal mode and with every non-owner
  primary selector in either argument order. Direct and module entrypoints reached runtime layout;
  copied-installed mock mismatches completed ordinary writes in isolated temporary workspaces.
- Added one post-parse dependency table that exits 2 with fixed option-only diagnostics before
  logging, runtime layout, configuration, project, provider, or artifact work.
- Preserved compare arity and ARA-048 mutual-exclusion precedence, correct pairs in both orders,
  explicit empty output values owned by a valid mode, `--help`, and output-free behavior. Private
  output values are not echoed.
- Focused tests passed `4 passed, 90 subtests`; related CLI/runner/package/survey/compare/recovery
  tests passed `141 passed, 352 subtests`; final `make check` passed `388 passed, 555 subtests`.
  Three independent final reviews returned GO.
- Committed as `eabedff` and pushed with exact local/upstream/`ls-remote`/PR-head equality. Push run
  `29260853734` and pull-request run `29260855184` passed Python 3.10/3.13, every isolated-wheel
  step, and all four job annotation sets are empty.

## 2026-07-13 - Private Ollama health path identity

- Reproduced three equal-shape private-path pairs sharing the length-only health identity and a
  valid `/alpha` health result being returned for `/bravo`.
- Replaced private path shapes with a domain-separated full HMAC-SHA256 identifier keyed by random
  process-local bytes held only in an imported helper module. Raw paths, key material, userinfo,
  query values, fragments, and reversible encodings never enter session state or files.
- Preserved safe allowlisted path identities, origin/default-port/trailing-slash normalization,
  userinfo/query presence markers, fragment omission, exact request behavior, and same-target reuse.
- The expected pre-fix layer produced `4 failed, 1 passed`; focused final tests pass `4 passed, 14
  subtests`, related tests pass `104 passed, 110 subtests`, and indexed full `make check` passes `392
  passed, 569 subtests`. Three independent final reviews returned GO.
- Committed as `98dffb5` and pushed with exact local/upstream/`ls-remote`/PR-head equality. Push run
  `29262351625` and pull-request run `29262353455` passed Python 3.10/3.13, every isolated-wheel
  step, and all four job annotation sets are empty.

## 2026-07-13 - Nested Ollama models container validation

- Reproduced null, zero, other numeric, and boolean nested `models` values raising `TypeError`, plus
  string and mapping containers being rescued into false healthy state by installed-model fallback.
- Required the decoded nested container to be an actual list before record iteration or fallback;
  every other JSON shape now returns the existing fixed credential-safe `InvalidResponse` result.
- Preserved omitted and list-valued containers, mixed invalid records, trimmed valid names, installed
  model union, exact request URL/timeout, endpoint redaction, and ARA-044/046/052/053 behavior.
- The expected pre-fix layer produced `7 failed, 1 passed, 3 subtests passed`; focused final tests
  pass `3 passed, 18 subtests`, related tests pass `101 passed, 120 subtests`, and indexed full
  `make check` passes `393 passed, 581 subtests`. Three independent final reviews returned GO.
- Committed as `0511a47` and pushed with exact local/upstream/`ls-remote`/PR-head equality. Push run
  `29263804804` and pull-request run `29263808869` passed Python 3.10/3.13, every isolated-wheel
  step, and all four job annotation sets are empty. Non-string record names remain separately queued
  as ARA-059.

## 2026-07-14 - String-only Ollama model-name normalization

- Reproduced null, boolean, numeric, list, and object record names being coerced to text by both the
  shared inventory parser and UI health check, allowing malformed provider data to report a false
  healthy match.
- Added one shared scalar normalizer that trims only actual strings. Provider API records with
  non-string names are ignored while literal string lookalikes, valid siblings, first-record
  metadata/de-duplication, exact requests, redaction, list-container validation, and the verbatim
  installed-model fallback remain compatible.
- Added parent-level aggregate regressions after an orchestration wrapper appeared to report zero
  for nested subtest failures. ARA-060 later proved direct pytest already returns 1 and the wrapper
  had not propagated nested exit codes; the aggregate mutation probes remain defense in depth.
- Focused tests pass `2 passed, 37 subtests`; related UI/config/recovery tests pass `103 passed, 157
  subtests`; indexed full `make check` passes `395 passed, 618 subtests` with 104 tracked/index files
  and zero safety findings. Three independent final reviews returned GO.
- Committed as `a7d00a6` and pushed with exact local/upstream/`ls-remote`/PR-head equality. Push run
  `29266119109` and pull-request run `29266121277` passed Python 3.10/3.13, every isolated-wheel
  step, and all four job annotation sets are empty.

## 2026-07-23 - Pytest unittest subtest exit-contract verification

- Reproduced one and 16 subtest-only failures directly under pytest 9.0.3; both returned status 1.
  Archived evidence showed the historical apparent zero was the successful outer orchestration
  status, which printed nested output without checking or propagating nested exit codes.
- Added a no-new-dependency subprocess sentinel that verifies subtest-only failure returns 1 and
  passing subtests return 0. The child run uses a temporary root, disables third-party plugin
  autoload, removes inherited pytest injection options, and has a 30-second timeout.
- Focused sentinel tests pass `2 passed`; the existing 14-file cohort passes `321 passed, 618
  subtests`; indexed `make check` passes `397 passed, 618 subtests` with 105 tracked files and zero
  safety findings.
- Committed as `0a0036f` and pushed with exact local/upstream/`ls-remote`/PR-head equality. Push run
  `30002348583` and pull-request run `30002350589` passed Python 3.10/3.13, every isolated-wheel
  step, and all four job annotation sets are empty.

## 2026-07-23 - Pre-agent manual-interrupt finalization

- Reproduced interrupts immediately after pending round-directory creation, round-entry logging,
  and project-memory loading. All three propagated before standard finalization and left no
  checkpoint, producing the expected `3 failed`.
- Extended only the existing manual-interrupt boundary over pre-agent round setup and routed both
  boundaries through one marker. Standard checkpoint, summary, config, and interrupted-report
  finalization now records zero completed rounds and leaves the empty pending round reusable.
- Preserved CLI status 130, lock release, traceback suppression, ARA-041 startup ordering,
  cooperative status-0 stops, artifact schemas, ordinary exception propagation, provider behavior,
  and successful/resume behavior.
- Focused tests pass `2 passed, 3 subtests`; CLI status/lock tests pass `3 passed`; related tests
  pass `135 passed, 339 subtests`; indexed `make check` passes `399 passed, 621 subtests` with 105
  tracked files and zero safety findings.
- Committed as `795665d` and pushed with exact local/upstream/`ls-remote`/PR-head equality. Push run
  `30004044807` and pull-request run `30004047971` passed Python 3.10/3.13, every isolated-wheel
  step, and all four job annotation sets are empty.

## 2026-07-23 - ARA-054 partial-round recovery design

- Reproduced eight post-persistence cases across draft/review/revise/Judge and manual
  interrupt/cloud quota. All wrote `can_resume=true` for zero completed rounds, but preview and
  actual resume rejected the four canonical files as `complete_uncheckpointed`; the rejected
  resume preserved every artifact byte.
- Confirmed that each stage currently writes all four canonical files, using one newline for future
  outputs, while eligibility uses only stop reason. File presence and `last_successful_agent` cannot
  safely identify a continuation boundary.
- Selected append-only attempt staging with immutable stopped evidence and whole-round retry.
  Rejected deletion, overwrite, rollback, and mid-stage continuation. Kept ambiguous legacy
  canonical partials fail-closed and ARA-055's cross-artifact transaction separate.
- Added `docs/ARA_054_PARTIAL_ROUND_RECOVERY_DESIGN.md`; no runtime, test behavior, artifact schema,
  provider, prompt, score, experiment, or canonical artifact changed.
- Design contract and indexed `make check` pass with `399 passed, 621 subtests` over 106 files.
  Design commit `946f40f` is remote-equal; push/PR runs `30007167214`/`30007170465` passed Python
  3.10/3.13 and every isolated-wheel step.

## 2026-07-23 - ARA-054 storage and classifier foundation

- Added anchored create-only text/JSON primitives and exclusive append-only attempt directory
  allocation. Existing leaves, stopped evidence, and canonical round files are never overwritten.
- Added strict attempt identity, timestamp, schema, stage-prefix, size, SHA-256, and filesystem
  validation with path-redacted classifications and an initial 32-attempt cap.
- Preserved current runner/resume behavior, canonical output format, legacy fail-closed handling,
  provider behavior, experiment results, and the separate ARA-055 transaction boundary.
- Focused coverage passes `9 passed, 4 subtests`; indexed `make check` passes `408 passed, 625
  subtests` over 108 tracked/index files with zero safety findings.
- Foundation commit `e4e784e` is remote-equal; push/PR runs
  `30012047804`/`30012050777` passed Python 3.10/3.13 and every isolated-wheel step.
