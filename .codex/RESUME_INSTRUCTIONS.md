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

`ARA-012` should be `DONE`. If the maintenance branch is ahead of origin, inspect the local containment commit and state-only closeout before pushing; do not repeat the implementation. Its final local validation command was:

```bash
make check
```

After the branch is clean, pushed, and CI-verified, the next task is `ARA-021`. Mark it `IN_PROGRESS` before editing and begin with focused UI metadata/dashboard/catalog tests proving external checkpoint artifact references are not read. Keep project-level symlink/TOCTOU policy (`ARA-022`) and manifest provenance/identity (`ARA-020`) separate. If another task is active, run its exact validation command from `.codex/TASK_QUEUE.md` first. Understand any uncommitted diff before editing it.

## 5. Safety boundaries

- Do not modify or stage ignored `config.yaml`, `.env`, project runs, checkpoints, logs, reports, or model/provider artifacts.
- Do not use `git add -A`, force push, hard reset, or automatic stash.
- Do not run paid or long provider workflows as part of recovery.
- Stage only reviewed tracked paths after tests pass.

## Suggested immediate command

```bash
git status --short --branch && git rev-list --left-right --count origin/codex/sol-autonomous-hardening...HEAD
```
