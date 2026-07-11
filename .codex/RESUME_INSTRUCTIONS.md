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

`ARA-005` implementation `15d9935`, recovery checkpoint `6b59091`, and verified closeout `3fa33a7`
are pushed and reflected in draft PR 13. The closeout's push run `29142941351` and pull-request run
`29142943132` passed on Python 3.10 and 3.13. Do not recreate another state-only closeout merely to
embed its own SHA; resolve the current commit from Git and verify remote/CI evidence live.

The last successful local full validation command was:

```bash
make check
```

The expected result is Ruff/import/safety success and `236 passed, 164 subtests passed`; both safety
modes should scan 91 tracked files with zero findings. The ARA-005 corrected-diff review is GO.
Resolve `HEAD`, compare it with upstream and `ls-remote`, and inspect current PR checks before
starting another task. If the current HEAD lacks successful remote evidence, use
`last_external_verification.commit` as the conservative stable fallback. Do not restart ARA-005.

`ARA-004` remains separately blocked. Do not repeat its unsafe local build harness or delete/rewrite
ignored `projects/example` state; read `KI-005`, `KI-013`, and `KI-023` before any packaging work.
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
