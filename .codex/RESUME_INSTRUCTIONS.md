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

`ARA-004` is `BLOCKED` before implementation at remotely verified audit checkpoint `89e95bf`. Its
safe wheel/sdist reproduction confirmed missing bundled assets and a combined resource/workspace
root. Read `KI-005`, `KI-013`, and `KI-023` in `.codex/KNOWN_ISSUES.md` before continuing. The last
stable full validation command was:

```bash
make check
```

Do not repeat the unsafe local build harness and do not delete or rewrite ignored `projects/example`
state. Wait for the owner's two decisions: approve the revised 45–90 minute package-resource/
workspace implementation, and choose whether to preserve or best-effort roll back deterministic run
`20260711_031915_776385`. If implementation is approved, keep UI/scripts publication, package
version/license, dependency policy (`ARA-019`), symlink policy (`ARA-022`), and provider behavior out
of scope. Run artifact builds from a Git export with isolated interpreters and a neutral CWD.

## 5. Safety boundaries

- Do not modify or stage ignored `config.yaml`, `.env`, project runs, checkpoints, logs, reports, or model/provider artifacts.
- Do not use `git add -A`, force push, hard reset, or automatic stash.
- Do not run paid or long provider workflows as part of recovery.
- Stage only reviewed tracked paths after tests pass.

## Suggested immediate command

```bash
git status --short --branch && git show --stat --oneline HEAD
```
