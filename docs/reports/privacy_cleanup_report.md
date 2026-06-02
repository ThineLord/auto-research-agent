# Privacy Cleanup Report

Date: 2026-06-02

## 1. Found Risk Categories

- Local absolute paths in public docs and UI defaults.
- Local runtime configuration tracked as `config.yaml`.
- Auto-managed research memory tracked as the PAMA project memory file.
- Local run outputs and state files present in the worktree but already untracked.
- Generated reports under `docs/reports/` that contained local audit details.

No real API credentials or account values were found in the current tracked tree scan.

## 2. Removed From Git Tracking, Kept Locally

These files were removed from the Git index with `git rm --cached` and still exist locally:

- `config.yaml`
- the PAMA project memory file

Local run outputs such as `projects/pama/runs/`, `projects/pama/run.log`, `projects/pama/checkpoint.json`, `projects/pama/score_history.json`, `projects/pama/research_state.json`, `projects/pama/best_output.md`, and `projects/pama/interrupted_report.md` remain local-only through ignore rules.

## 3. Template Files Added

- `config.example.yaml`
- `.env.example`
- `projects/pama/memory.example.md`

Public setup docs now tell users to run:

```bash
cp config.example.yaml config.yaml
```

Optional project memory can be created with:

```bash
cp projects/pama/memory.example.md projects/<project>/memory.md
```

## 4. Ignore Rule Summary

`.gitignore` now covers:

- local config and env files while allowing `.env.example`
- project memory files and generated project state
- run, output, artifact, log, cache, and report directories
- model/data artifacts such as database, pickle, checkpoint, archive, and binary files
- Python caches, test caches, virtual environments, editor files, and macOS files
- generated `docs/reports/*` files while allowing this cleanup report

## 5. Code And Path Adaptations

- `ui/app.py` no longer defaults to a user home path for the canonical root. It now defaults to the current repository root and only uses `AUTO_RESEARCH_AGENT_ROOT` when explicitly set.
- `tests/test_config.py` now validates `config.example.yaml` instead of relying on private `config.yaml`.
- `README.md`, `docs/USER_GUIDE.md`, `docs/quickstart_zh.md`, and `docs/runbook_zh.md` were changed to use relative, public-safe commands.

## 6. Verification

- `python -m pytest -q`: failed because this machine has no `python` command on PATH.
- `.venv/bin/python -m pytest -q`: passed, `36 passed, 24 subtests passed`.
- Current path and credential scans found no private path or credential values in non-ignored files.
- The requested exact scan still reports benign wording in docs and the sample task related to model usage accounting and text processing. No real sensitive values were present in those hits.

## 7. Needs Manual Confirmation

- Confirm whether `projects/pama/task.md` is safe to publish as an example project. It contains a real-looking research direction, though no personal data or credentials were found.
- Confirm whether existing untracked local reports under `docs/reports/` should stay local-only or be rewritten as public docs later.
- Confirm whether Git author metadata and past commit attribution are acceptable for the public repository.

## 8. History Rewrite Recommendation

Recommended before publishing a fully clean public repository.

Reason: history contains local absolute paths in earlier README/User Guide/UI commits, and the PAMA project memory file has historically contained auto-managed run summaries. No real credentials were found by the scans run during this cleanup, but the historical path exposure and generated run memory are enough to justify cleanup if the repository will be made public.

Suggested approach:

1. Make a fresh backup clone.
2. Use `git filter-repo` or BFG to remove historical `config.yaml`, `projects/*/memory.md`, and any generated state/output paths.
3. Replace historical local absolute path strings if needed.
4. Re-run tests and scans on the rewritten clone.
5. Coordinate with collaborators before any force push.

Do not force push until the rewritten history has been reviewed.

## 9. History Rewrite Findings

The dry-run rewrite passed in a throwaway clone, then the same `git-filter-repo` rewrite was applied to the original local repository on 2026-06-02. No remote update was performed.

Pre-rewrite history contained:

- the tracked local config file
- the tracked PAMA project memory file
- older local absolute-path references in README/User Guide/UI history

No real credential values were found. The remaining keyword matches are benign references to text tokenization or model usage accounting.

## 10. Original Repository Rewrite Result

- Original branch: `privacy/public-safe-cleanup`
- Cleanup commit before rewrite: `341b2ba745b4ef2265f1868964f520e6f62de934`
- Report commit before rewrite: `a0bd1eff86baa5d0e44c6225662d27c0d68b901b`
- Rewritten HEAD before this report update: `50d500a32f628b3fbe0f7ee3aff9f33c041795b0`
- Rewrite tool: `git-filter-repo` from the verified local user install
- Remote action: none

## 11. Backup Branch, Tag, And Bundle

Created before rewrite:

- Branch: `backup/pre-history-rewrite`
- Tag: `backup-before-history-rewrite`
- Bundle: `../auto-research-agent-before-history-rewrite.bundle`

The bundle is the authoritative pre-rewrite backup and should remain local-only. Because `git-filter-repo` rewrites all local refs, the backup branch and tag now resolve to rewritten commits while preserving their names.

## 12. Files Removed From History

The original-repository rewrite removed these paths from all rewritten commits:

- `config.yaml`
- the PAMA project memory file

The rewrite did not remove `config.example.yaml`, `.env.example`, source files, tests, docs, prompts, or project templates.

## 13. Strings Replaced From History

The temporary replacement file mapped:

- the previous absolute repository path to `<PROJECT_ROOT>`
- the previous local user home path to `<USER_HOME>`
- the previous PAMA memory file text path to `<PROJECT_MEMORY_FILE>`

Ordinary `config.yaml` text was not replaced because the codebase legitimately refers to that local config filename in docs, source, and tests.

## 14. Remote Status After Rewrite

`git-filter-repo` removed `origin` during rewrite. The remote was restored locally:

```bash
origin  https://github.com/ThineLord/auto-research-agent.git
```

Read-only remote check after restore:

- `refs/heads/master`: `33f1c166e4b8e0bf6f612d7fd2bac0ac4e4de7f9`
- `refs/heads/privacy/public-safe-cleanup`: not present
- `refs/heads/main`: not present

No push was performed.

## 15. Verification Commands And Results

Commands run after rewrite:

```bash
git status --short
git branch --show-current
git log --oneline --decorate -n 10
git log --all --stat -- config.yaml <PAMA_MEMORY_FILE>
git log -S"<LOCAL_USER_PATH>" --all --oneline --decorate --
git rev-list --all | xargs -n 25 git grep -n -I -E "<local-path-or-memory-patterns>"
git rev-list --all | xargs -n 25 git grep -n -I -i -E "<credential-keyword-patterns>"
rg -n "<current-tree-sensitive-patterns>" .
.venv/bin/python -m pytest -q
```

Results:

- Working tree was clean before the report update.
- Current branch remained `privacy/public-safe-cleanup`.
- Historical file-level scan for the removed local config file and removed PAMA memory file returned no output.
- Historical exact local user path search returned no output.
- Historical grep for exact local path and removed memory path returned no output.
- Current-tree sensitive scan returned no output.
- Historical credential-keyword grep only returned benign tokenization/model-cost wording.
- Tests passed with `36 passed, 24 subtests passed`.

## 16. Whether It Is Now Safe To Push

It is safe to prepare a reviewed `--force-with-lease` update after manually reviewing the rewritten branch, confirming collaborator coordination, and deciding whether this cleanup branch should replace the public default branch.

Do not publish the pre-rewrite bundle.

## 17. Recommended Push Commands - NOT EXECUTED

These commands were not run.

If pushing the rewritten cleanup branch for review, the remote branch was not present during the final read-only check, so no force is required:

```bash
git push -u origin privacy/public-safe-cleanup
```

If you want an absent-branch lease check anyway:

```bash
git push --force-with-lease=refs/heads/privacy/public-safe-cleanup: -u origin privacy/public-safe-cleanup
```

If replacing the public `master` branch after review, use the exact remote value observed during the final read-only check:

```bash
git push --force-with-lease=refs/heads/master:33f1c166e4b8e0bf6f612d7fd2bac0ac4e4de7f9 origin privacy/public-safe-cleanup:master
```

Do not push the local pre-rewrite bundle. Do not push the backup tag unless you intentionally want that public marker.

Use `--force-with-lease`, not plain force.
