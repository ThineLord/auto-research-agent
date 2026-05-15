#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

cd "${ROOT_DIR}"

if [[ ! -x ".venv/bin/python" ]]; then
  echo "Virtual environment is not ready."
  echo "Run: make install-dev"
  exit 1
fi

if ! .venv/bin/python -c "import streamlit" >/dev/null 2>&1; then
  echo "Streamlit is not installed in .venv."
  echo "Run: make install-dev"
  exit 1
fi

exec .venv/bin/python -m streamlit run ui/app.py
