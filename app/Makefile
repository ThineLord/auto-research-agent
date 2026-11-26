PYTHON ?= python3
VENV ?= .venv
ARGS ?=

# VENV is exported as data. It is not a Make target and it is not inserted
# into a shell command, so a path with spaces or quotes stays one path.
# PYTHON reaches the recipe environment only when the user set it. The
# default above stays unexported, so it is not an explicit interpreter.
export VENV
ENSURE = PYTHON_ORIGIN='$(origin PYTHON)' ./scripts/ensure_python_env.sh

.DEFAULT_GOAL := help

.PHONY: help bootstrap venv install install-dev format format-check lint import-check repo-safety release-check test check ci performance run diagnostic continuous resume session survey mock ui

help:
	@printf "%s\n" \
		"Available commands:" \
		"  make bootstrap     Prepare a new checkout and run a diagnostic smoke test" \
		"  make install       Create .venv and install the app" \
		"  make install-dev   Create .venv and install app + test tools" \
		"  make format        Format Python code with Ruff" \
		"  make format-check  Verify Python formatting" \
		"  make lint          Run Ruff lint checks" \
		"  make import-check  Import all project modules" \
		"  make repo-safety   Scan tracked files for personal paths and secrets" \
		"  make release-check Check versions and tracked documentation links" \
		"  make test          Run the automated test suite" \
		"  make check         Run formatting, lint, imports, safety, and tests" \
		"  make performance   Benchmark local hot paths with synthetic data" \
		"  make run           Run the normal research workflow" \
		"  make diagnostic    Run the diagnostic workflow" \
		"  make continuous    Run continuous mode" \
		"  make resume        Resume from checkpoint" \
		"  make session       Run session mode" \
		"  make survey        Run local Literature Survey Mode" \
		"  make mock          Run deterministic provider-free demo mode" \
		"  make ui            Start the local research dashboard" \
		"" \
		"Run make install-dev once on a new checkout before testing or running." \
		"Python 3.10+ is selected from PATH. Pass PYTHON=python3.13 to choose one." \
		"Pass VENV=path to place the environment. ./start and Make then use that Python." \
		"An older or incomplete environment is left unchanged." \
		"Pass extra CLI flags with ARGS, for example:" \
		"  make diagnostic ARGS=\"--model qwen3:8b\""

bootstrap:
	./scripts/bootstrap.sh

venv:
	@$(ENSURE) venv

install:
	@$(ENSURE) install

install-dev:
	@$(ENSURE) install-dev

format: install-dev
	@$(ENSURE) run -m ruff check --fix --select I src tests ui scripts
	@$(ENSURE) run -m ruff format src tests ui scripts

format-check: install-dev
	@$(ENSURE) run -m ruff format --check src tests ui scripts

lint: install-dev
	@$(ENSURE) run -m ruff check src tests ui scripts

import-check: install-dev
	@$(ENSURE) run scripts/import_check.py

repo-safety: install-dev
	@$(ENSURE) run scripts/check_repo_safety.py --self-test
	@$(ENSURE) run scripts/check_repo_safety.py
	@$(ENSURE) run scripts/check_repo_safety.py --staged

test: install-dev
	@$(ENSURE) run -m pytest -q

release-check: install-dev
	@$(ENSURE) run scripts/check_release.py

check: format-check lint import-check repo-safety release-check test

.PHONY: browser-test
browser-test:
	@$(ENSURE) run -m pytest -q tests/browser

ci: check

performance: install
	@$(ENSURE) run scripts/benchmark_local_performance.py $(ARGS)

run: install
	@$(ENSURE) run -m src.main $(ARGS)

diagnostic: install
	@$(ENSURE) run -m src.main --diagnostic $(ARGS)

continuous: install
	@$(ENSURE) run -m src.main --continuous $(ARGS)

resume: install
	@$(ENSURE) run -m src.main --resume $(ARGS)

session: install
	@$(ENSURE) run -m src.main --session $(ARGS)

survey: install
	@$(ENSURE) run -m src.main --survey $(ARGS)

mock: install
	@$(ENSURE) run -m src.main --mock $(ARGS)

ui: install
	@$(ENSURE) run -m ui.server $(ARGS)
