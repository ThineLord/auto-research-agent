# Workspace upgrade and rollback (0.3.0)

[English](workspace-upgrade.md) · [简体中文](workspace-upgrade.zh-CN.md)

## Before upgrading

Stop runs and the dashboard using the old version, then back up the whole private workspace (including `config.yaml`, `projects/`, external run storage if configured, and any new sibling research). Keep the backup private and verify it can be read. Do not change the program files of a running process. This release never moves, rewrites or deletes old research automatically.

For a clean checkout, fetch the release, review `git status`, switch to `v0.3.0`, then run `./start`. Git should refuse a switch that would overwrite tracked local edits; do not use a force switch, `reset --hard` or `clean` to resolve that. If unsure, keep the old checkout untouched and inspect a separate checkout of the release first. Use Python 3.10+; the new environment lives in `app/.venv/` and the old `.venv/` may be retained for rollback.

## Existing research stays in place

`projects/<name>/` remains supported by both CLI and dashboard, including Task, Memory, Runs, Scores and Checkpoints. Discovery is read-only. Legacy projects take precedence over a same-named sibling folder, including `example`; the dashboard's Settings → Advanced location shows the actual relative path. An invalid legacy project reports an error instead of silently loading another folder. New projects cannot reuse any occupied legacy or sibling name.

No migration command for relocating research is included. **Do not drag an existing run folder into a new location:** checkpoints and recovery journals can contain absolute paths and identity information. Relocation is not needed to use this release. A future relocation requires a verified backup, conflict checks and explicit approval; copying folders alone is not a validated migration. The existing legacy-history repair CLI is unrelated to directory relocation and retains its explicit approval/evidence requirements.

## New workspace and CLI

Run `./start`, open the printed loopback URL, and use **+** beside the research selector. A non-hidden folder name and task create `<workspace>/<name>/task.md` plus `memory.md` without overwriting a folder. Selection is saved in ignored `.ara-workspace.json`; project inputs and outputs remain inside their own folder. Switching does not restart or move a running project. The running project can be selected again to request a safe stop/resume.

```bash
make install-dev
app/.venv/bin/auto-research-agent --create-project topic-a --task "Describe the experiment"
app/.venv/bin/auto-research-agent --project topic-a --mock --max-rounds 1
make check
make browser-test
```

CLI and dashboard accept `--workspace /path/to/workspace` for an explicit workspace. Source installations otherwise use the parent of `app/`; a wheel uses the current working directory. Wheel CLI fresh `--mock` seeds a missing `example/` without overwriting anything. The source dashboard's first start creates missing config/example only. Real model runs retain their existing provider requirements. The wheel does not include the web dashboard; use the source launcher for the unified UI. Internal Streamlit remains available via `cd app && .venv/bin/python -m streamlit run ui/app.py`; the supported primary entry is `./start`.

## Roll back

Stop all runs and services first. Keep a private backup of the current state. Switch application code to the prior tag only from a clean checkout; rebuild the matching environment. Unmoved `projects/<name>/` retains its old paths and artifact formats. New sibling research is **not discovered by 0.2.x**: preserve it untouched and return to 0.3.0 to use it. Do not move it into `projects/` or edit checkpoints to force compatibility. If artifacts were changed after upgrading and the old application cannot resume them, use the verified pre-upgrade backup at its original workspace path after checking conflicts and explicitly choosing what to restore. No automatic rollback of research data is performed.

Root Git rules allowlist application/public files; private folders, config and selection state remain ignored. Wheel builds use only explicit application files and bundled starter resources, never your mutable workspace example or research. Git ignore is not encryption; private backups must remain private.

### Minimal legacy-example compatibility file

`projects/example/task.md` remains tracked so a real Git upgrade cannot delete the task underneath ignored old Runs, Memory or Checkpoints. New installations select top-level `example/` when this old directory contains only the untouched public task file and the top-level example has a readable task. Any old research file or customized legacy task keeps legacy precedence. This one-file compatibility directory is intentional; it is not automatically removed.
