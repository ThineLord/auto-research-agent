PYTHON ?= python3
VENV ?= .venv
ARGS ?=

VENV_PYTHON := $(VENV)/bin/python
VENV_PIP := $(VENV_PYTHON) -m pip
INSTALL_STAMP := $(VENV)/.install.stamp
DEV_STAMP := $(VENV)/.install-dev.stamp

.DEFAULT_GOAL := help

.PHONY: help venv install install-dev test run diagnostic continuous resume session ui

help:
	@printf "%s\n" \
		"Available commands:" \
		"  make install       Create .venv and install the app" \
		"  make install-dev   Create .venv and install app + test tools" \
		"  make test          Run the automated test suite" \
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

test: install-dev
	$(VENV_PYTHON) -m pytest -q

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
