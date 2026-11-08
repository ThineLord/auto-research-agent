# Auto Research Agent

[English](README.md) · [简体中文](README.zh-CN.md)

**A local-first workspace for turning a research task into drafts you can inspect, revise, and compare.**

Auto Research Agent runs **Draft → Review → Revise → Judge** with local Ollama or Google Gemini. A local dashboard keeps the task, progress, saved outputs, and run comparisons together. Model scores support iteration; they do not establish research validity.

**For users:** start with the [user README](docs/user/README.md).

**For agents:** read [AGENTS.md](AGENTS.md), then the [agent README](docs/agent/README.md).

## Three steps

1. **Define a task.** Use the public example or create a separate project under `projects/`.
2. **Run and inspect.** Start the dashboard, choose a provider and model, and review each saved round.
3. **Continue with context.** Resume a valid checkpoint, inspect outputs, or compare runs before deciding what to try next.

## Start locally

Use Python **3.10+**, Git, and Make. Run these commands in a new checkout:

```bash
git clone https://github.com/ThineLord/auto-research-agent.git
cd auto-research-agent
cp config.example.yaml config.yaml
make install
make ui
```

Open **[http://127.0.0.1:8501/](http://127.0.0.1:8501/)** and keep the server running. In an existing checkout, reuse its configuration and environment. Starting the dashboard does not start a research run. Real runs need a configured provider; `make mock` demonstrates saved outputs without model calls. See the [user guide](docs/user/README.md) before running a real task.

## Where things live

```text
auto-research-agent/
├── src/                 research workflow and command-line application
├── ui/                  local dashboard
├── prompts/             Draft / Review / Revise / Judge templates
├── projects/            public example and ignored local research projects
├── docs/                user, agent, release, reference, and design documents
├── scripts/             setup, validation, and performance tools
├── tests/               automated checks
├── AGENTS.md            agent entry and maintenance rules
└── CHANGELOG.md         changes by version
```

Local configuration, credentials, generated runs, and private project folders stay out of Git by default. The application stores run artifacts on your computer; Gemini sends model inputs to its cloud provider when selected.

## Versions and documentation

Current version: **0.2.0**. Releases use `vMAJOR.MINOR.PATCH` tags matched to `pyproject.toml`. Historical milestone tags remain available. Application releases and saved research artifacts have separate compatibility boundaries.

- [Releases](https://github.com/ThineLord/auto-research-agent/releases) · [0.2.0 notes](docs/releases/0.2.0.md) · [Changelog](CHANGELOG.md)
- [User README](docs/user/README.md) · [Agent README](docs/agent/README.md)
- [Documentation map](docs/README.md) · [Version and release policy](docs/agent/releases.md)

The dashboard runs from a source checkout. The installable Python package provides the CLI and bundled starter resources.
