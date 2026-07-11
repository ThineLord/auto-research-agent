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
