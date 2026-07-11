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

ARA-022 is owner-approved and `IN_PROGRESS`. Resume from the exact checkpoint in
`CURRENT_STATE.md`; do not assume baseline, reproduction, or implementation completed unless
`LAST_VALIDATION.json` records it. If newer state-only evidence is unavailable, use
`094446f3dfa8ee876dd0d7505ad0087988eef32d` as the conservative stable fallback.

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

The current full expected result is Ruff/import/safety success and `246 passed, 172 subtests
passed`; the final focused ARA-004 package/run-config/CLI/mock layer passes `35 passed, 20 subtests
passed`. Both safety modes should scan only tracked/staged files with zero findings.
Resolve `HEAD`, compare it with upstream and `ls-remote`, and inspect current PR checks before
starting another task. If the current HEAD lacks successful remote evidence, use
`last_external_verification.commit` as the conservative stable fallback. Do not restart ARA-005.

Read `KI-023`, `KI-026`, and `KI-027` before any packaging/release follow-up. Do not delete/rewrite
ignored `projects/example` state or the recorded pip-cache residue, and do not publish the temporary
sdist. Versions, license, dependency policy, UI/scripts distribution, and active filesystem swaps
remain separate tasks.

ARA-022 may inspect and modify only tracked code/docs plus temporary fixtures. Never probe the
repository's ignored project runtime to discover links. Preserve configured resolved `runs/`
storage links, distinguish static leaf links from active parent replacement, and record any
platform capability gap explicitly. ARA-018 remains owner-blocked; ARA-019, ARA-026, ARA-006, and
ARA-007 remain deferred under their recorded dependencies.

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
make check
```
