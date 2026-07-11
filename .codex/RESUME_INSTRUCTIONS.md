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

`ARA-016` is locally implemented at `2b6523c`; recovery metadata, push, PR update, or remote CI may
still be pending depending on the interruption point. Compare HEAD/upstream and the current state
before repeating work. The last stable full validation command was:

```bash
make check
```

The expected result is Ruff/import/safety success and `217 passed, 134 subtests passed`. Also run
both scanner modes; each should report 91 tracked files and zero findings. If recovery metadata is
still uncommitted, review and stage only the named `.codex` files, then create the state checkpoint.
If the branch is ahead, push normally and verify exact remote SHA before checking draft PR 13 and
all Python 3.10/3.13 push/pull-request jobs.

`ARA-004` remains separately blocked. Do not repeat its unsafe local build harness or delete/rewrite
ignored `projects/example` state; read `KI-005`, `KI-013`, and `KI-023` before any packaging work.

## 5. Safety boundaries

- Do not modify or stage ignored `config.yaml`, `.env`, project runs, checkpoints, logs, reports, or model/provider artifacts.
- Do not use `git add -A`, force push, hard reset, or automatic stash.
- Do not run paid or long provider workflows as part of recovery.
- Stage only reviewed tracked paths after tests pass.

## Suggested immediate command

```bash
git status --short --branch && git log --oneline --decorate -n 5
```
