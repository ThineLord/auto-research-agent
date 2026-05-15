PYTHON ?= python3
VENV ?= .venv
ARGS ?=

VENV_PYTHON := $(VENV)/bin/python
VENV_PIP := $(VENV_PYTHON) -m pip
INSTALL_STAMP := $(VENV)/.install.stamp
DEV_STAMP := $(VENV)/.install-dev.stamp

.DEFAULT_GOAL := help

.PHONY: help venv install install-dev format format-check lint import-check test check ci run diagnostic continuous resume session ui

help:
	@printf "%s\n" \
		"Available commands:" \
		"  make install       Create .venv and install the app" \
		"  make install-dev   Create .venv and install app + test tools" \
		"  make format        Format Python code with Ruff" \
		"  make format-check  Verify Python formatting" \
		"  make lint          Run Ruff lint checks" \
		"  make import-check  Import all project modules" \
		"  make test          Run the automated test suite" \
		"  make check         Run formatting, lint, imports, and tests" \
		"  make run           Run the normal research workflow" \
		"  make diagnostic    Run the diagnostic workflow" \
		"  make continuous    Run continuous mode" \
		"  make resume        Resume from checkpoint" \
		"  make session       Run session mode" \
		"  make ui            Start the Streamlit UI" \
		"" \
		"Run make install-dev once on a new checkout before testing or running." \
		"Pass extra CLI flags with ARGS, for example:" \
		"  make diagnostic ARGS=\"--model qwen3:8b\""

$(VENV_PYTHON):
	$(PYTHON) -m venv $(VENV)

venv: $(VENV_PYTHON)

$(INSTALL_STAMP): pyproject.toml | $(VENV_PYTHON)
	$(VENV_PIP) install -e .
	@touch $(INSTALL_STAMP)

$(DEV_STAMP): pyproject.toml | $(VENV_PYTHON)
	$(VENV_PIP) install -e ".[dev]"
	@touch $(INSTALL_STAMP) $(DEV_STAMP)

install: $(INSTALL_STAMP)

install-dev: $(DEV_STAMP)

format: install-dev
	$(VENV_PYTHON) -m ruff check --fix --select I src tests ui scripts
	$(VENV_PYTHON) -m ruff format src tests ui scripts

format-check: install-dev
	$(VENV_PYTHON) -m ruff format --check src tests ui scripts

lint: install-dev
	$(VENV_PYTHON) -m ruff check src tests ui scripts

import-check: install-dev
	$(VENV_PYTHON) scripts/import_check.py

test: install-dev
	$(VENV_PYTHON) -m pytest -q

check: format-check lint import-check test

ci: check

run: install
	$(VENV_PYTHON) -m src.main $(ARGS)

diagnostic: install
	$(VENV_PYTHON) -m src.main --diagnostic $(ARGS)

continuous: install
	$(VENV_PYTHON) -m src.main --continuous $(ARGS)

resume: install
	$(VENV_PYTHON) -m src.main --resume $(ARGS)

session: install
	$(VENV_PYTHON) -m src.main --session $(ARGS)

ui: install
	$(VENV_PYTHON) -m streamlit run ui/app.py $(ARGS)
