# Resume Instructions

Use this sequence after any interruption. It is intentionally provider-free and non-destructive.

## 1. Recover repository context

```bash
git rev-parse --show-toplevel
git status --short --branch
git branch --show-current
git remote -v
git fetch --prune origin
git log --oneline --decorate -n 10
```

Expected branch: `codex/sol-autonomous-hardening`.

## 2. Read the durable state

```bash
cat .codex/CURRENT_STATE.md
cat .codex/TASK_QUEUE.md
cat .codex/LAST_VALIDATION.json
```

Compare the current HEAD, worktree, active task, and validation record. Do not assume an earlier command completed if it is not recorded in `LAST_VALIDATION.json`.

The recovery record uses an additive schema-v1 extension: `current_head.ref` is the authoritative
semantic reference and must be `HEAD`; resolve it with the fixed
`current_head.resolution_argv`. Legacy `head_commit` and `last_known_stable_commit` remain exact
40-hex fallback values for compatibility, but they are not the SHA of the commit containing the
state file.

## 3. Check for interrupted Git operations

```bash
git status --porcelain=v2 --branch
test -d "$(git rev-parse --git-path rebase-merge)" && echo active-rebase-merge
test -d "$(git rev-parse --git-path rebase-apply)" && echo active-rebase-apply
test -e "$(git rev-parse --git-path MERGE_HEAD)" && echo active-merge
test -e "$(git rev-parse --git-path CHERRY_PICK_HEAD)" && echo active-cherry-pick
git stash list
```

The checkout has a known stale invalid `.git/REBASE_HEAD`; do not interpret that file alone as an active rebase and do not delete it automatically.

## 4. Validate the active task before continuing

ARA-060 is complete through remote-equal closeout `b064a93`. Direct pytest 9.0.3 probes with one
and 16 subtest-only failures both return status 1; the historical apparent zero was an outer
parallel script that rendered nested output without propagating nested exit codes. A tracked
isolated subprocess sentinel now verifies failure returns 1 and passing subtests return 0 with no
plugin autoload, inherited pytest injection, or unbounded child process. Focused tests pass `2
passed`; the 14-file existing subtest cohort passes `321 passed, 618 subtests`, and indexed full
`make check` passes `397 passed, 618 subtests`. Implementation runs
`30002348583`/`30002350589` and closeout runs
`30002850097`/`30002852693` passed Python 3.10/3.13, all isolated-wheel steps, and zero annotations.
Do not change pytest configuration or dependencies, bulk rewrite the 102 call sites, change
production behavior, call a provider, or read ignored runtime.

ARA-059 is complete through remote-equal closeout `b196af9`. Closeout push/PR runs
`29266539401`/`29266544263` passed Python 3.10/3.13, all four isolated-wheel steps, and zero
annotations. Preserve its literal string lookalikes, metadata, request/redaction, list-container,
and installed-fallback behavior.
ARA-058 is complete through remote-equal closeout `1419d5e`; closeout push/PR runs
`29264305133`/`29264308515` passed Python 3.10/3.13, all four wheel steps, and zero annotations with
exact PR body readback. The later ARA-055 package-4 closeout `00a488d` remains historical evidence,
not the active recovery fallback.

Do not rebuild or rerun ARA-004 merely to recover context. Do not repeat the original local harness:
it imported the editable checkout and advanced ignored `projects/example` state after a missing
build backend. No cleanup or reuse of that ignored state was authorized.

All ARA-004 build/install/module/console/mock validation must use temporary isolated workspaces with
source-tree imports excluded. Never seed or run against the repository's actual `projects/example`.
Keep installed read-only assets separate from writable project output and fail rather than writing
runtime state into `site-packages`.

The last successful local full validation command was:

```bash
make check
```

ARA-048's final local result is Ruff/import/safety success and `373 passed, 416 subtests passed`;
its focused conflict/compatibility/entrypoint layer passes `6 passed, 100 subtests`, related tests
pass `122 passed, 238 subtests`, and three independent reviews returned GO. The expected pre-fix
focused result was `93 failed, 1 passed`; no provider or ignored runtime was used.

ARA-047's final local result is Ruff/import/safety success and `368 passed, 316 subtests passed`;
its focused unsafe-history/CLI/compatibility layer passes `4 passed, 20 subtests`, and related tests
pass `95 passed, 130 subtests`. Three independent reviews returned GO.

The current ARA-030 full expected result is Ruff/import/safety success and `359 passed, 277 subtests
passed`; its targeted CI/package/safety regression passes `19 passed, 23 subtests passed`. The final
real wheel canary passed with ambient pip/Git/provider redirects injected and did not create the
external guard path. Both final safety modes included 103 tracked/index files with zero findings;
the real push/PR matrix confirmed all four wheel steps.
Resolve `HEAD`, compare it with upstream and `ls-remote`, and inspect current PR checks before
starting another task. If the current HEAD lacks successful remote evidence, use
`last_external_verification.commit` as the conservative stable fallback. Do not restart ARA-005.

Read `KI-023`, `KI-026`, and `KI-027` before any packaging/release follow-up. Do not delete/rewrite
ignored `projects/example` state or the recorded pip-cache residue, and do not publish the temporary
sdist. Versions, license, dependency policy, UI/scripts distribution, and active filesystem swaps
remain separate tasks.

ARA-022 used only tracked code/docs plus temporary fixtures; repository ignored runtime remains out
of scope. Preserve configured resolved `runs/` storage links. The implementation protects
registered link-based replacement but explicitly does
not claim same-UID real-directory replacement, post-open/new-temp hard-link races, trusted-anchor
ancestors, or Windows active replacement. ARA-018 remains owner-blocked; ARA-019, ARA-026, ARA-006,
and ARA-007 remain deferred under their recorded dependencies.

ARA-056 is complete through remote-equal closeout `d60a7a1`. The pre-fix
round-directory, round-log, and memory-load matrix produced `3 failed`; the local fix now routes
those points through standard manual-interrupt finalization, leaves the empty pending round
reusable, and re-raises for CLI status 130. Focused tests pass `2 passed, 3 subtests`, related tests
pass `135 passed, 339 subtests`, and indexed `make check` passes `399 passed, 621 subtests`.
Push/PR runs `30004044807`/`30004047971` passed Python 3.10/3.13, all four isolated-wheel steps,
and zero annotations. Preserve ARA-041 startup transaction ordering, cooperative status-0 stops,
schemas, and ordinary exception behavior.

ARA-054 is complete through runtime commit `75f3d9a8446db87ad2030e361f8147762263d8c4`.
Provider-free publication/crash coverage and the four-stage manual-interrupt/cloud-quota matrix
pass; full pytest reports `417 passed, 633 subtests`. Push/PR runs
`30016026758`/`30016026741` passed Python 3.10/3.13 and isolated-wheel validation. Read
`docs/ARA_054_PARTIAL_ROUND_RECOVERY_DESIGN.md` before any follow-up. Preserve append-only stopped
attempts, whole-round retry, shared classifier eligibility, bounded disk/attempt use, no-replace
publication, and nonempty legacy canonical fail-closed behavior.

ARA-055 packages 1-4 are complete. Package-4 implementation `efcad88` is exact local/upstream/
`ls-remote`/PR-head equal; push/PR runs `30034539432`/`30034542276` passed Python 3.10/3.13 and
every workflow step. Focused validation passes `9 passed`, related validation passes `256 passed,
540 subtests`, the recovery matrix passes `16 passed, 99 subtests`, and full `make check` passes
`462 passed, 791 subtests`. It recovers under the existing lock before provider/client/agent work
and blocks read-only mixed-generation consumers without mutation. PR 13 comment `5062099962`
records the result.

ARA-061 is the sole active task after the owner said `批准ARA061` on 2026-07-24. Use
`2ac99e0fde929dc9d919702e2e7195ced1d0f7af` as the conservative exact externally verified
fallback; activation push/PR runs `30080995141`/`30080997040` passed. The local implementation,
tests, and docs are uncommitted: focused validation passes `4 passed, 18 subtests`, related
regression passes `244 passed, 554 subtests`, and full `make check` passes `466 passed, 809
subtests` plus formatting, lint, imports, and zero-finding safety scans. Review and stage only the
recorded task paths, rerun staged safety, then commit and push if green. Preserve valid zero/
boundary behavior and fail invalid values before project writes or provider work.

ARA-055 package 5 finalization journaling remains separately approval-gated. Do not add
finalization writer/reader behavior, diagnostic routing, migration, configuration schema/default
changes, dependencies, providers, ignored-runtime access, scheduler-policy changes, or packages
6-7 while implementing ARA-061.
ARA-018 requires an explicit owner license/distribution decision. Do not start ARA-019, ARA-026,
ARA-006, or ARA-007 until their recorded dependencies are satisfied.

## 5. Safety boundaries

- Do not modify or stage ignored `config.yaml`, `.env`, project runs, checkpoints, logs, reports, or model/provider artifacts.
- Do not use `git add -A`, force push, hard reset, or automatic stash.
- Do not run paid or long provider workflows as part of recovery.
- Stage only reviewed tracked paths after tests pass.

## Suggested immediate command

```bash
git status --short --branch
git rev-parse --verify HEAD
.venv/bin/python -m json.tool .codex/LAST_VALIDATION.json >/dev/null
.venv/bin/python -m pytest -q tests/test_recovery_state.py
git diff --check
```
