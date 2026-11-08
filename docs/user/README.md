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

Version **0.2.2** simplifies the repository layout while preserving runtime paths, checkpoints and environment metadata. Use `make install-dev` in place of the removed `requirements.txt` shim. See [release notes](../releases/0.2.2.md) and the [documentation map](../README.md) for advanced commands and limits. The dashboard requires the source checkout; wheel installations provide the CLI only.

Saving submits only edited fields. If another tab or a run changed the same field, the dashboard shows both versions and keeps your draft; choose the latest version or explicitly replace the conflicting fields. Saves are blocked while a run owns the project or recovery is pending.

New Judge responses must contain all five weighted rubric fields (25/25/20/20/10), a matching 0–100 total, reasons, blockers, and `CONTINUE`/`STOP`. Invalid responses count as failed scoring and cannot replace the best output. Diagnostic mode uses the same scoring contract. Existing historical score records remain readable; scores are model judgments, not evidence of scientific validity.
Model discovery, startup validation, and generation all use `ollama_base_url` from the application configuration. `OLLAMA_HOST` does not override this address.

`make install` and `make install-dev` use the release dependency constraints. New `run_config.json` files record installed application/Python/direct runtime dependency versions and, in source checkouts, the constraints fingerprint (null when unavailable in wheel installs). Ollama runs also attempt a bounded, read-only model digest lookup; unavailable metadata is explicit and does not stop research. Resume preserves the initial environment and records the current session separately; legacy runs without original metadata keep an explicitly unknown initial environment. These fields do not guarantee deterministic model outputs or record credentials, hostnames, or endpoint URLs.
