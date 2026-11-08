# Auto Research Agent

[English](README.md) · [简体中文](README.zh-CN.md)

**A local-first workspace for turning a research task into drafts you can inspect, revise, and compare.**

Auto Research Agent runs **Draft → Review → Revise → Judge** with local Ollama or Google Gemini. A local dashboard keeps the task, progress, saved outputs, and run comparisons together. Model scores support iteration; they do not establish research validity.

**For users:** start with the [user README](app/docs/user/README.md).

**For agents:** read [AGENTS.md](AGENTS.md), then the [agent README](app/docs/agent/README.md).

![Research workspace with task editor, run controls and saved results](app/docs/assets/workspace-en.png)

*The local dashboard, showing a synthetic demo task. Scores are model feedback, not research validation.*

## Three steps

1. **Define a task.** Use the public example or create a separate project next to `app/`.
2. **Run and inspect.** Start the dashboard, choose a provider and model, and review each saved round.
3. **Continue with context.** Resume a valid checkpoint, inspect outputs, or compare runs before deciding what to try next.

## Start locally

Use Python **3.10+**, Git, and Make. The launcher prints the local URL; open it in your browser. Run these commands in a new checkout:

```bash
git clone https://github.com/ThineLord/auto-research-agent.git
cd auto-research-agent
./start
```

Open **[http://127.0.0.1:8501/](http://127.0.0.1:8501/)** and keep the server running. In an existing checkout, reuse its configuration and environment. Starting the dashboard does not start a research run. Real runs need a configured provider; `make mock` demonstrates saved outputs without model calls. See the [user guide](app/docs/user/README.md) before running a real task.

## Your workspace

```text
auto-research-agent/
├── app/                 application, dependencies, tests and documentation
├── example/             public starter research
├── projects/example/    one compatibility task file for old Git upgrades
├── research-topic-a/    your research (created from the dashboard)
├── research-topic-b/    another independent research
├── README.md
└── start                install if needed, then start the dashboard
```

Click **+** next to the research selector, enter a folder name and task, then switch projects using the same selector. Data and the last selection survive restarts. Configuration stays in the ignored workspace `config.yaml`. New research folders are ignored by Git.

Existing `projects/<name>/` folders load in place; no automatic migration occurs. See the [upgrade and rollback guide](app/docs/user/workspace-upgrade.md) before updating an older checkout. [Application documentation](app/docs/README.md) · [Agent guide](app/docs/agent/README.md)

## Versions and documentation

Current version: **0.3.0**. Releases use `vMAJOR.MINOR.PATCH` tags matched to `pyproject.toml`. Historical milestone tags remain available. Application releases and saved research artifacts have separate compatibility boundaries.

- [Releases](https://github.com/ThineLord/auto-research-agent/releases) · [0.3.0 notes](app/docs/releases/0.3.0.md) · [Changelog](app/CHANGELOG.md)
- [User README](app/docs/user/README.md) · [Agent README](app/docs/agent/README.md)
- [Documentation map](app/docs/README.md) · [Version and release policy](app/docs/agent/releases.md)

The dashboard runs from a source checkout. The installable Python package provides the CLI and bundled starter resources.
