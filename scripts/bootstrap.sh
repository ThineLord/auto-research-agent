#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
RECOMMENDED_MODEL="${BOOTSTRAP_MODEL:-qwen3:8b}"
MAKE_BIN="${MAKE:-make}"

log() {
  printf "\n==> %s\n" "$*"
}

fail() {
  printf "\nBootstrap stopped: %s\n" "$*" >&2
  exit 1
}

need_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    fail "Missing required command: $1"
  fi
}

cd "${ROOT_DIR}"

log "Checking required commands"
need_command python3
need_command make
need_command ollama

python3 - <<'PY'
import sys

required = (3, 10)
version = sys.version_info[:2]
if version < required:
    raise SystemExit(
        f"Python {required[0]}.{required[1]}+ is required; found "
        f"{sys.version.split()[0]}"
    )
print(f"Python {sys.version.split()[0]}")
PY

"${MAKE_BIN}" --version | sed -n '1p'

log "Checking Ollama availability"
if ! OLLAMA_LIST_OUTPUT="$(ollama list 2>&1)"; then
  printf "%s\n" "${OLLAMA_LIST_OUTPUT}" >&2
  fail "Ollama is installed, but 'ollama list' failed. Start Ollama, then rerun: make bootstrap"
fi

log "Preparing local config"
if [[ -f "config.yaml" ]]; then
  printf "Found existing config.yaml; leaving it untouched.\n"
else
  [[ -f "config.example.yaml" ]] || fail "Missing config.example.yaml"
  cp "config.example.yaml" "config.yaml"
  printf "Created config.yaml from config.example.yaml.\n"
fi

log "Creating .venv and installing runtime dependencies"
"${MAKE_BIN}" install

log "Checking recommended Ollama model: ${RECOMMENDED_MODEL}"
if ! printf "%s\n" "${OLLAMA_LIST_OUTPUT}" | awk 'NR > 1 {print $1}' | grep -Fxq "${RECOMMENDED_MODEL}"; then
  printf "Model %s is not installed.\n" "${RECOMMENDED_MODEL}" >&2
  printf "Run: ollama pull %s\n" "${RECOMMENDED_MODEL}" >&2
  printf "Then rerun: make bootstrap\n" >&2
  exit 1
fi

log "Running diagnostic workflow"
"${MAKE_BIN}" diagnostic ARGS="--model ${RECOMMENDED_MODEL}"

log "Bootstrap complete"
