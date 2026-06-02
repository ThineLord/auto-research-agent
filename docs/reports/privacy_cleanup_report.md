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

Second-stage audit commit: `341b2ba745b4ef2265f1868964f520e6f62de934`.

History still contains:

- the tracked file path `config.yaml`
- the tracked PAMA project memory file path
- older local absolute-path references in README/User Guide/UI history

History audit did not find real credential values. The remaining keyword matches are benign references to text tokenization or model usage accounting.

`git-filter-repo` and BFG were not available on this machine, so no history rewrite was executed during this stage.

## 10. Commands Executed

```bash
git status --short
git diff --cached --stat
git commit -m "chore: make repository public-safe"
git log --all --stat -- "$PRIVATE_MEMORY_PATH" config.yaml
git log -S"<PRIVATE_USER_HOME>" --all --oneline --decorate --
git log -S"$PRIVATE_MEMORY_PATH" --all --oneline --decorate --
git rev-list --all | xargs -n 25 git grep -n -I -E "<path-and-config-patterns>"
git rev-list --all | xargs -n 25 git grep -n -I -i -E "<credential-patterns>"
git filter-repo --version
command -v bfg
.venv/bin/python -m pytest -q
```

## 11. Files To Remove From History

Use `git-filter-repo` to remove these file paths from all historical commits:

- `config.yaml`
- `$PRIVATE_MEMORY_PATH`

Do not remove `config.example.yaml`, `.env.example`, source files, tests, docs, prompts, or project templates.

## 12. Strings To Replace From History

Prepare a replacement file outside committed docs, for example `/tmp/auto-research-agent-replacements.txt`:

```text
literal:<PRIVATE_REPO_ABS_PATH>==><PROJECT_ROOT>
literal:<PRIVATE_USER_HOME>==><USER_HOME>
```

Only add a broad prefix replacement after manual review:

```text
literal:<PRIVATE_USERS_PREFIX>==><USER_HOME_PREFIX>
```

Avoid replacing ordinary `config.yaml` text in source/docs. The codebase legitimately refers to the local config filename.

## 13. Proposed Local Dry Run

Install `git-filter-repo` first, then test in a throwaway clone:

```bash
python3 -m pip install --user git-filter-repo

cd /tmp
PRIVATE_REPO_PATH="${PRIVATE_REPO_PATH:?set this to the local repo path first}"
git clone --no-local "$PRIVATE_REPO_PATH" auto-research-agent-rewrite-dryrun
cd auto-research-agent-rewrite-dryrun
git switch privacy/public-safe-cleanup
PRIVATE_MEMORY_PATH="${PRIVATE_MEMORY_PATH:?set this to the PAMA memory path first}"

cat > /tmp/auto-research-agent-replacements.txt <<'EOF'
literal:<PRIVATE_REPO_ABS_PATH>==><PROJECT_ROOT>
literal:<PRIVATE_USER_HOME>==><USER_HOME>
EOF

git filter-repo --force \
  --path config.yaml \
  --path "$PRIVATE_MEMORY_PATH" \
  --invert-paths \
  --replace-text /tmp/auto-research-agent-replacements.txt

cp config.example.yaml config.yaml
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m pytest -q
```

## 14. Proposed In-Repo Rewrite Commands

Run these only after reviewing the dry-run output:

```bash
git status --short
git branch backup/pre-history-rewrite
git tag backup-before-history-rewrite
git bundle create ../auto-research-agent-before-history-rewrite.bundle --all
PRIVATE_MEMORY_PATH="${PRIVATE_MEMORY_PATH:?set this to the PAMA memory path first}"

cat > /tmp/auto-research-agent-replacements.txt <<'EOF'
literal:<PRIVATE_REPO_ABS_PATH>==><PROJECT_ROOT>
literal:<PRIVATE_USER_HOME>==><USER_HOME>
EOF

git filter-repo --force \
  --path config.yaml \
  --path "$PRIVATE_MEMORY_PATH" \
  --invert-paths \
  --replace-text /tmp/auto-research-agent-replacements.txt
```

After rewriting, re-check:

```bash
git status --short
git log --oneline --decorate -n 10
git log --all --stat -- "$PRIVATE_MEMORY_PATH" config.yaml
PRIVATE_PATH_PATTERN="${PRIVATE_PATH_PATTERN:?set this to the escaped private path pattern first}"
PRIVATE_MEMORY_PATTERN="${PRIVATE_MEMORY_PATTERN:?set this to the escaped memory path pattern first}"
rg -n "$PRIVATE_PATH_PATTERN|$PRIVATE_MEMORY_PATH|$SENSITIVE_REGEX" .
git rev-list --all | xargs -n 25 git grep -n -I -E "$PRIVATE_PATH_PATTERN|$PRIVATE_MEMORY_PATTERN"
git rev-list --all | xargs -n 25 git grep -n -I -i -E "$SENSITIVE_REGEX"
.venv/bin/python -m pytest -q
```

## 15. Verification Result

- Cleanup commit was created successfully.
- History rewrite was not executed because `git-filter-repo` and BFG were unavailable.
- Current working tree remains public-safe after the cleanup commit.
- Historical sensitive-path findings remain until a reviewed rewrite is performed.
- Tests pass with `.venv/bin/python -m pytest -q`.

## 16. Push Instructions For Review Only

Do not run these until the rewrite is reviewed and collaborators are coordinated.

If pushing the rewritten cleanup branch for review:

```bash
git push --force-with-lease origin privacy/public-safe-cleanup
git push --force-with-lease origin --tags
```

If replacing the public default branch after review:

```bash
git push --force-with-lease origin privacy/public-safe-cleanup:master
git push --force-with-lease origin --tags
```

Use `--force-with-lease`, not plain `--force`.
