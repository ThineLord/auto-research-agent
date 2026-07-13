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

No task is active. ARA-058 is complete at implementation `0511a47`: non-list nested `models` fail
closed before installed fallback while omitted/list-valued fields, valid records, exact requests,
and ARA-044/ARA-046/ARA-052 behavior remain compatible. Push/PR runs
`29263804804`/`29263808869` passed Python 3.10/3.13, all four wheel steps, and zero annotations with
exact local/upstream/`ls-remote`/PR-head equality. ARA-059 separately owns record-name typing and is
the preferred low-risk TODO after live recovery checks; ARA-056 remains independent. Do not call a
provider or read ignored runtime. Use `0511a47739168af76d7163716d82c56e19bef9d7` as the conservative
exact externally verified fallback.

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

No task is `IN_PROGRESS`; ARA-059 and ARA-056 are independent TODO tasks. ARA-018 requires an
explicit owner license/distribution decision. Do not start ARA-019, ARA-026, ARA-006, or ARA-007
until their recorded dependencies are satisfied.

## 5. Safety boundaries

- Do not modify or stage ignored `config.yaml`, `.env`, project runs, checkpoints, logs, reports, or model/provider artifacts.
- Do not use `git add -A`, force push, hard reset, or automatic stash.
- Do not run paid or long provider workflows as part of recovery.
- Stage only reviewed tracked paths after tests pass.

## Suggested immediate command

```bash
git status --short --branch
git rev-parse --verify HEAD
git rev-parse '@{upstream}'
git rev-list --left-right --count '@{upstream}'...HEAD
.venv/bin/python -m json.tool .codex/LAST_VALIDATION.json >/dev/null
.venv/bin/python -m pytest -q tests/test_recovery_state.py
```
