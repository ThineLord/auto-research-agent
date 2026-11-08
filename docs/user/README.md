# User README

[English](README.md) · [简体中文](README.zh-CN.md) · [Project home](../../README.md)

Auto Research Agent helps you iterate on a research task and inspect the saved work. The workflow drafts, reviews, revises, and scores text; you remain responsible for checking sources, methods, and conclusions.

## Install and open

Use Python 3.10+, Git, and Make. From a fresh checkout:

```bash
cp config.example.yaml config.yaml
make install
make ui
```

Open [the local dashboard](http://127.0.0.1:8501/). Reuse existing `config.yaml` and `.venv` when returning to the project. If the port is occupied, use `scripts/start_ui.sh --port 8502`. Stop the server with Ctrl+C in its terminal.

| Page | Purpose |
| --- | --- |
| Workspace | Edit a task and research memory, control a run, inspect progress |
| Outputs | Read saved Markdown, JSON, and logs |
| Run analytics | Inspect scores, timing, metadata, and comparisons |
| Settings | Choose model settings and appearance; access workspace tools |

Language and appearance preferences persist in the browser. Starting the dashboard does not start research. A normal run saves the edited inputs before starting.

## Try the workflow without a model

`make mock` writes deterministic demo artifacts without Ollama, Gemini, or an API key. It updates the selected project's run state. Use a separate project to preserve existing research:

```bash
mkdir projects/demo
cp projects/example/task.md projects/demo/task.md
make mock ARGS="--project demo --max-rounds 1"
```

Choose a new folder name if `demo` already exists; do not overwrite it. Select that project in the dashboard to inspect its outputs. A mock result demonstrates the application, not a research finding.

## Run your own task

1. Create `projects/<name>/task.md`, or select an existing project. Keep the public example unchanged for private research.
2. Set `project_name` and `topic` in local `config.yaml`, or select the project in the dashboard.
3. Choose a provider and an available model. Ollama must be running with the selected model installed. Gemini needs a valid API key and may incur provider charges; its configured free-runner policy is not a billing guarantee.
4. Run a diagnostic when ready for an actual model call, then start a bounded run. Inspect results before deciding to resume or start another run.

| Command | What it does |
| --- | --- |
| `make ui` | Start the local dashboard |
| `make mock` | Write deterministic demo outputs; no model calls |
| `make diagnostic` | Run a real-provider diagnostic round |
| `make run` | Start a new bounded research run |
| `make resume` | Continue the selected project's valid checkpoint |
| `make survey` | Synthesize saved local sources deterministically; no model calls |

`make bootstrap` installs dependencies, checks Ollama, and runs a real diagnostic. Use the installation steps above if you only want to open the dashboard.

## Saved work and privacy

Inputs, memory, checkpoints, and runs belong under the selected `projects/<name>/`. Run folders retain intermediate text, metadata, and metrics. Resume preserves prior history and rejects unsafe or inconsistent states; a new run is separate. Do not move or manually edit active run folders to repair a resume error.

Local configuration and generated research are ignored by Git. Ignore rules are not encryption or access control. Gemini sends supplied task/context to its service. Keep credentials in local environment/configuration and never commit them. Back up a stopped project's whole directory and local configuration privately, including any separately configured external run storage.

## Update by version

Choose a version from [GitHub Releases](https://github.com/ThineLord/auto-research-agent/releases) and read its notes. Stop active runs, back up private work, and keep the checkout clean before switching to a release tag. Re-run `make install` after an upgrade. Do not discard local changes or overwrite configuration to update.

Version **0.2.0** keeps existing runtime paths and artifact schemas. See [release notes](../releases/0.2.0.md) and the [documentation map](../README.md) for advanced commands and limits. The dashboard requires the source checkout; wheel installations provide the CLI only.
