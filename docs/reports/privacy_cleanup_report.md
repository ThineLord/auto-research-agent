# Privacy Cleanup Report

Date: 2026-06-02

## 1. Found Risk Categories

- Local absolute paths in public docs and UI defaults.
- Local runtime configuration tracked as `config.yaml`.
- Auto-managed research memory tracked as `<PROJECT_MEMORY_FILE>`.
- Local run outputs and state files present in the worktree but already untracked.
- Generated reports under `docs/reports/` that contained local audit details.

No real API credentials or account values were found in the current tracked tree scan.

## 2. Removed From Git Tracking, Kept Locally

These files were removed from the Git index with `git rm --cached` and still exist locally:

- `config.yaml`
- `<PROJECT_MEMORY_FILE>`

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
cp projects/pama/memory.example.md <PROJECT_MEMORY_FILE>
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

Reason: history contains local absolute paths in earlier README/User Guide/UI commits, and `<PROJECT_MEMORY_FILE>` has historically contained auto-managed run summaries. No real credentials were found by the scans run during this cleanup, but the historical path exposure and generated run memory are enough to justify cleanup if the repository will be made public.

Suggested approach:

1. Make a fresh backup clone.
2. Use `git filter-repo` or BFG to remove historical `config.yaml`, `projects/*/memory.md`, and any generated state/output paths.
3. Replace historical local absolute path strings if needed.
4. Re-run tests and scans on the rewritten clone.
5. Coordinate with collaborators before any force push.

Do not force push until the rewritten history has been reviewed.
