# Known Issues

Updated: 2026-07-10 (Asia/Shanghai)

## KI-001 - Stale invalid `.git/REBASE_HEAD`

- Status: observed; non-blocking
- Severity: P3
- Evidence: the file exists and references an unavailable object, while `rebase-merge`, `rebase-apply`, and sequencer state are absent and `git status --porcelain=v2 --branch` is clean.
- Impact: diagnostic scripts that test only for `.git/REBASE_HEAD` can falsely report an active rebase.
- Current action: leave untouched; use actual rebase directories and porcelain status to determine operation state.

## KI-002 - Compare-runs arity contract may be inconsistent

- Status: fixed, validated, committed, and pushed
- Severity: P1
- Evidence source: tracked `TEST_AND_NEXT_STEPS.md` reports that one run was accepted while CLI help and docs require two or more.
- Impact: users cannot tell whether a one-run self-baseline is supported or accidental.
- Current action: task `ARA-002` completed at remote commit `033ed01`.

## KI-003 - Non-positive max-round override may be silently coerced

- Status: fixed, validated, committed, and pushed
- Severity: P1
- Evidence source: tracked `TEST_AND_NEXT_STEPS.md` reports that `--max-rounds 0` produced a one-round mock run.
- Impact: surprising automation behavior and a possible unintended provider call when zero rounds were expected.
- Current action: task `ARA-003` completed at remote checkpoint `5c5bdc0`.

## KI-004 - Source tag and package metadata use different versions

- Status: confirmed by tracked metadata; policy decision deferred
- Severity: P2 for packaged distribution, P3 for cloned-checkout use
- Evidence: `pyproject.toml` declares `0.1.0`; tracked release documentation identifies `v0.1.1-hardening`.
- Impact: wheel metadata and source release naming may diverge.
- Current action: task `ARA-006`; do not change version without a distribution policy.

## KI-005 - Non-editable package assets are not yet verified

- Status: verified incomplete in both wheel and sdist
- Severity: P2
- Evidence: the project declares only the `src` package while runtime workflows also reference repository assets and UI/scripts.
- Impact: wheel-installed behavior may differ from editable or cloned-checkout behavior.
- Current action: task `ARA-004`; audit checkpoint `89e95bf` is remotely verified. Safe
  implementation requires separating installed read-only resources from a writable workspace and
  is awaiting the recorded long-task checkpoint approval.

## KI-006 - Legacy ignored logs can predate path masking

- Status: known local-data risk; no tracked-code regression
- Severity: P3
- Evidence source: tracked release review; current ignored runtime data is intentionally not opened, rewritten, or committed during startup.
- Impact: manually shared old artifacts may disclose local paths.
- Current action: never publish ignored artifacts without a scoped privacy scan.

## KI-007 - Configured credentials can be echoed into provider events

- Status: fixed, validated, committed, pushed, and CI-verified
- Severity: P0
- Impact: an arbitrary configured API key echoed by a provider response can survive pattern-only redaction and be serialized locally.
- Current action: task `ARA-008` completed at remote checkpoint `c8d6c17`.

## KI-008 - Interrupted JSON writes can destroy the last checkpoint

- Status: fixed, validated, committed, pushed, and CI-verified
- Severity: P1
- Impact: an in-place write failure truncates the old valid checkpoint, after which tolerant reads can silently return empty state.
- Current action: task `ARA-009` completed at remote checkpoint `5ab7119`.

## KI-009 - Resume can discard historical metrics

- Status: fixed, validated, committed, pushed, and CI-verified
- Severity: P1
- Impact: appending a resumed round can rewrite metrics and summaries with only the new round, corrupting longitudinal interpretation.
- Current action: task `ARA-010` completed at remote checkpoint `b8b629b`.

## KI-010 - Failed rounds can replace prior best output

- Status: fixed, validated, committed, pushed, and CI-verified
- Severity: P1
- Impact: synthetic failure output can beat the internal sentinel score and overwrite trusted prior content.
- Current action: task `ARA-011` completed at remote checkpoint `7e9a1f5`.

## KI-011 - Resume roots are not constrained to the project runs directory

- Status: fixed, validated, committed, pushed, and CI-verified
- Severity: P1
- Impact: a crafted or stale checkpoint can direct resumed artifact writes outside the selected project's run tree.
- Current action: task `ARA-012` completed at remote checkpoint `31db3f8`.

## KI-012 - Run locks are not atomic or owner-safe

- Status: fixed, pushed, and CI-verified
- Severity: P1
- Impact: concurrent acquisition can race, an old owner can remove a newer lock, and malformed PID metadata can raise.
- Current action: task `ARA-013` completed at implementation commit `55e7287` and remotely verified
  checkpoint `e93aa77`.

## KI-013 - Wheel-installed mock workflow cannot find repository assets

- Status: reproduced in isolated wheel and sdist installs; implementation blocked before changes
- Severity: P1 for packaged distribution
- Impact: console help works, but mock startup cannot locate `config.example.yaml`; a source checkout works.
- Current action: task `ARA-004`; audit checkpoint `89e95bf` is remotely verified. Do not advertise
  wheel readiness or use package-root data files that would make installed workflows write into
  `site-packages`.

## KI-014 - Tracked reports contain a personal absolute-path fragment

- Status: fixed, pushed, and CI-verified
- Severity: P1 privacy/release hygiene
- Impact: the repository embeds a real local username in historical scan examples and evidence text.
- Current action: task `ARA-016` completed at implementation commit `2b6523c` and remotely verified
  recovery checkpoint `975559d` with all Python 3.10/3.13 push and pull-request jobs passing.

## KI-015 - Some CLI startup failures exit successfully

- Status: fixed, pushed, and CI-verified
- Severity: P1 automation/release reliability
- Impact: missing config/resources can print an error while returning status 0, allowing a smoke check to pass falsely.
- Current action: task `ARA-017` completed at implementation commit `8845adf` and remotely verified
  checkpoint `a513e4d`. Wheel asset completeness remains separate task `ARA-004`.

## KI-016 - Public distribution license is absent

- Status: confirmed; owner decision required
- Severity: P1 release blocker, not a runtime defect
- Impact: public package publication has no declared license or complete project metadata.
- Current action: task `ARA-018`; do not choose a license autonomously.

## KI-017 - Gemini transport timeout is not wired to the SDK client

- Status: fixed, pushed, and CI-verified
- Severity: P1 bounded-runtime reliability
- Impact: one SDK request can exceed configured per-agent and global runtime expectations.
- Current action: task `ARA-015` completed at implementation commit `817b8a1` and remotely verified
  checkpoint `be37216`; no real provider call was required.

## KI-018 - Historical benchmark report can use another run's stop reason

- Status: fixed, pushed, and CI-verified
- Severity: P2
- Impact: a historical target run can be mislabeled from the project's latest checkpoint.
- Current action: task `ARA-014` completed at implementation commit `588e32c` and remotely verified
  recovery checkpoint `c893e63`; all Python 3.10/3.13 push and pull-request jobs passed.

## KI-019 - Resume can rewrite original run-manifest provenance

- Status: fixed, pushed, and CI-verified
- Severity: P2
- Impact: rebuilding `run_manifest.json` during resume can replace original start/mode provenance and discard unknown legacy fields, even though `run_config.json` retains resume sessions; a safe in-runs path alias can also disagree with checkpoint `run_id`.
- Current action: task `ARA-020` completed at implementation `3b98c61` and remotely verified
  checkpoint `c1e8c57` with Python 3.10/3.13 push and PR jobs passing.

## KI-020 - UI artifact viewers can follow external checkpoint references

- Status: fixed, validated, committed, pushed, and CI-verified
- Severity: P1 privacy
- Impact: metadata, analytics, and output-catalog helpers can read checkpoint-supplied run config/summary paths or a summary-supplied metrics path outside the selected run.
- Current action: task `ARA-021` completed at remote checkpoint `3624385`.

## KI-021 - Static resume checks do not close active filesystem swap races

- Status: confirmed residual under an active local-filesystem attacker
- Severity: P2 under the project's local single-user threat model
- Impact: renaming a validated run directory and replacing its path with a symlink between checks and stage persistence can redirect later writes; project-level artifact symlinks also remain broader than checkpoint scope.
- Current action: task `ARA-022`; document the trust boundary before considering descriptor-based no-follow I/O or a repository-wide symlink policy.

## KI-022 - Manual interrupts can still produce process status 0

- Status: fixed, pushed, and CI-verified
- Severity: P2 automation semantics
- Impact: direct interrupts caught by the CLI and runner-consumed safe interrupts do not yet share a
  documented process-status contract, so changing only one path could make automation inconsistent.
- Current action: task `ARA-023` completed at implementation `4cae84e` and remotely verified
  checkpoint `37b3749`; cooperative `STOP_REQUESTED` remains status 0.

## KI-023 - A maintenance smoke advanced ignored example-project state

- Status: awaiting owner disposition; no cleanup attempted
- Severity: local-state integrity incident, no tracked-code/provider impact
- Impact: deterministic run `20260711_031915_776385` created one ignored run and replaced five
  ignored project-level state files plus appended `run.log` under `projects/example`.
- Current action: preserve all touched files as-is until the owner chooses to keep the transparent
  mock checkpoint or authorizes a backed-up best-effort rollback. Repository history cannot restore
  the prior ignored state byte-for-byte.

## KI-024 - Zero-round resume omits a run-config resume session entry

- Status: fixed, pushed, and CI-verified
- Severity: P3 provenance completeness
- Impact: resuming a checkpoint with `last_completed_round=0` records resume lifecycle metadata and
  current-session time but does not append `resume_sessions` because the next round is still 1.
- Current action: task `ARA-024` completed at implementation `b961070` and remotely verified
  checkpoint `a3bef4d`; all Python 3.10/3.13 push and PR jobs passed.
