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

`ARA-015` should be `DONE` at implementation commit `817b8a1`. Its final local validation command was:

```bash
make check
```

If the branch is ahead of origin by the ARA-015 implementation and recovery-state checkpoint,
inspect and push them without force, then verify exact remote SHA and all four Python 3.10/3.13
push/pull-request checks; do not repeat the implementation. No real Gemini call is needed. After
synchronization, choose the next P1 from `.codex/TASK_QUEUE.md`; keep interrupt status (`ARA-023`),
package assets (`ARA-004`), dependency policy (`ARA-019`), project-level symlink policy (`ARA-022`),
and manifest provenance (`ARA-020`) separate. If another task is active, run its exact validation
command first. Understand any uncommitted diff before editing it.

## 5. Safety boundaries

- Do not modify or stage ignored `config.yaml`, `.env`, project runs, checkpoints, logs, reports, or model/provider artifacts.
- Do not use `git add -A`, force push, hard reset, or automatic stash.
- Do not run paid or long provider workflows as part of recovery.
- Stage only reviewed tracked paths after tests pass.

## Suggested immediate command

```bash
git status --short --branch && git show --stat --oneline HEAD
```
