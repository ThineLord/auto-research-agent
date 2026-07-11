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
sed -n '1,240p' .codex/CURRENT_STATE.md
sed -n '1,320p' .codex/TASK_QUEUE.md
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

ARA-004 is approved and `IN_PROGRESS`. Resume from the highest completed checkpoint recorded in
`CURRENT_STATE.md`; do not repeat the original local harness. It imported the editable checkout and
advanced ignored `projects/example` state after a missing build backend. Owner approval covers the
packaging/resource fix but does not authorize cleanup or reuse of that ignored state.

All ARA-004 build/install/module/console/mock validation must use temporary isolated workspaces with
source-tree imports excluded. Never seed or run against the repository's actual `projects/example`.
Keep installed read-only assets separate from writable project output and fail rather than writing
runtime state into `site-packages`.

The last successful local full validation command was:

```bash
make check
```

The pre-implementation expected result is Ruff/import/safety success and `236 passed, 164 subtests
passed`; both safety modes should scan 91 tracked files with zero findings.
Resolve `HEAD`, compare it with upstream and `ls-remote`, and inspect current PR checks before
starting another task. If the current HEAD lacks successful remote evidence, use
`last_external_verification.commit` as the conservative stable fallback. Do not restart ARA-005.

Read `KI-005`, `KI-013`, and `KI-023` before continuing ARA-004. Do not delete/rewrite ignored
`projects/example` state, and do not widen packaging scope into versions, licenses, dependency
policy, UI/scripts distribution, or ARA-022 filesystem-swap behavior.
Active non-cooperating filesystem replacement remains ARA-022 and was not widened into ARA-020.

## 5. Safety boundaries

- Do not modify or stage ignored `config.yaml`, `.env`, project runs, checkpoints, logs, reports, or model/provider artifacts.
- Do not use `git add -A`, force push, hard reset, or automatic stash.
- Do not run paid or long provider workflows as part of recovery.
- Stage only reviewed tracked paths after tests pass.

## Suggested immediate command

```bash
git status --short --branch && git diff --check && git log --oneline -n 5
git rev-parse --verify HEAD
.venv/bin/python -m json.tool .codex/LAST_VALIDATION.json >/dev/null
```
