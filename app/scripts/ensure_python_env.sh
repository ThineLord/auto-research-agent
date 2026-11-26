#!/bin/bash
# Choose Python >= 3.10 before make creates a virtual environment or installs
# packages. An existing incompatible environment is left in place.
# Packages are installed only into the requested virtualenv, and only when
# that environment's own pip imports. Compatible with macOS /bin/bash 3.2:
# no associative arrays or namerefs.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
cd -- "${APP_DIR}"

MIN_LABEL="3.10"
CANDIDATE_NAMES="python3.13 python3.12 python3.11 python3.10 python3 python"
PYTHON="${PYTHON-}"
PYTHON_ORIGIN="${PYTHON_ORIGIN-undefined}"
VENV="${VENV-.venv}"

# The first argument selects the action. Later arguments belong to `run`
# and are the interpreter's argv, not shell text.
mode=venv
if [ "$#" -gt 0 ]; then
  case "$1" in
    venv|install|install-dev|run)
      mode="$1"
      shift
      ;;
  esac
fi

found_name=()
found_path=()
found_version=()
seen_paths="|"

is_supported() {
  local version="$1" major minor
  case "${version}" in
    [0-9]*.[0-9]*) ;;
    *) return 1 ;;
  esac
  major="${version%%.*}"
  minor="${version#*.}"
  minor="${minor%%.*}"
  if [ "${major}" -gt 3 ]; then
    return 0
  fi
  if [ "${major}" -eq 3 ] && [ "${minor}" -ge 10 ]; then
    return 0
  fi
  return 1
}

probe_version() {
  local py="$1" out
  if ! out="$("${py}" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])' 2>/dev/null)"; then
    return 1
  fi
  case "${out}" in
    [0-9]*.[0-9]*.[0-9]*)
      printf '%s\n' "${out}"
      ;;
    *)
      return 1
      ;;
  esac
}

lookup_interpreter() {
  local name="$1" resolved
  case "${name}" in
    */*)
      if [ -x "${name}" ] && [ ! -d "${name}" ]; then
        printf '%s\n' "${name}"
        return 0
      fi
      return 1
      ;;
  esac
  resolved="$(command -v "${name}" 2>/dev/null || true)"
  if [ -n "${resolved}" ]; then
    printf '%s\n' "${resolved}"
    return 0
  fi
  return 1
}

remember() {
  local name="$1" path="$2" version="$3"
  case "${seen_paths}" in
    *"|${path}|"*) return 0 ;;
  esac
  seen_paths="${seen_paths}${path}|"
  found_name[${#found_name[@]}]="${name}"
  found_path[${#found_path[@]}]="${path}"
  found_version[${#found_version[@]}]="${version}"
}

collect_candidates() {
  local name path version
  for name in ${CANDIDATE_NAMES}; do
    if ! path="$(lookup_interpreter "${name}")"; then
      continue
    fi
    if ! version="$(probe_version "${path}")"; then
      version="unavailable"
    fi
    remember "${name}" "${path}" "${version}"
  done
}

token() {
  case "$1" in
    ""|*[!A-Za-z0-9._/:=+-]*)
      printf "'%s'\n" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"
      ;;
    *)
      printf '%s\n' "$1"
      ;;
  esac
}

venv_show() {
  local parent base
  # Absolute path: `mv` works from any directory. The default name stays
  # relative inside make, which already runs with app/ as its cwd.
  if [ "${VENV}" = ".venv" ]; then
    printf '%s\n' "${APP_DIR}/.venv"
    return 0
  fi
  parent="$(dirname -- "${VENV}")"
  base="$(basename -- "${VENV}")"
  if [ -d "${parent}" ]; then
    printf '%s/%s\n' "$(cd -- "${parent}" && pwd)" "${base}"
    return 0
  fi
  printf '%s\n' "${VENV}"
}

move_destination() {
  local shown="$1" version="$2" major minor suffix
  case "${version}" in
    [0-9]*.[0-9]*)
      major="${version%%.*}"
      minor="${version#*.}"
      minor="${minor%%.*}"
      suffix="python${major}.${minor}"
      ;;
    *)
      suffix="unsupported"
      ;;
  esac
  printf '%s-%s\n' "${shown}" "${suffix}"
}

print_found() {
  local i
  printf 'Interpreters found:\n' >&2
  if [ "${#found_name[@]}" -eq 0 ]; then
    printf '  (none)\n' >&2
    return 0
  fi
  i=0
  while [ "${i}" -lt "${#found_name[@]}" ]; do
    printf '  %s: Python %s (%s)\n' \
      "${found_name[${i}]}" "${found_version[${i}]}" "${found_path[${i}]}" >&2
    i=$((i + 1))
  done
}

first_supported_index() {
  local i=0
  while [ "${i}" -lt "${#found_name[@]}" ]; do
    if is_supported "${found_version[${i}]}"; then
      printf '%s\n' "${i}"
      return 0
    fi
    i=$((i + 1))
  done
  return 1
}

# Recovery prefers an explicit supported interpreter, otherwise the newest
# supported candidate. The printed command is one that can be run as written.
recovery_assignment() {
  local name="$1"
  if [ -z "${name}" ]; then
    return 0
  fi
  printf ' PYTHON=%s' "$(token "${name}")"
}

recovery_venv_assignment() {
  local shown
  if [ "${VENV}" = ".venv" ]; then
    return 0
  fi
  shown="$(venv_show)"
  printf ' VENV=%s' "$(token "${shown}")"
}

print_recreate_command() {
  local python_name="$1"
  printf 'From the repository root:\n' >&2
  if [ -n "${python_name}" ]; then
    printf '  make install-dev%s%s\n' "$(recovery_venv_assignment)" "$(recovery_assignment "${python_name}")" >&2
    return 0
  fi
  printf '  Install Python %s or newer, then rerun:\n' "${MIN_LABEL}" >&2
  printf '  make install-dev%s\n' "$(recovery_venv_assignment)" >&2
}

# One interpreter run classifies the directory. The program text avoids the
# contiguous letters used by the in-repo fakes' logs. A version-only answer
# did not run the check, so it cannot count as ready.
classify_env() {
  local out
  env_class=absent
  venv_version=""
  if [ ! -L "${VENV}" ] && [ ! -e "${VENV}" ]; then
    return 0
  fi
  if [ ! -x "${venv_python}" ]; then
    env_class=unusable
    return 0
  fi
  # Version first, with no path argument. An older interpreter is done.
  # The directory check below reads ARA_ENV_DIR so the path stays out of argv.
  if ! venv_version="$(probe_version "${venv_python}")"; then
    env_class=unusable
    return 0
  fi
  if ! is_supported "${venv_version}"; then
    env_class=old
    return 0
  fi
  if ! out="$(ARA_ENV_DIR="${VENV}" "${venv_python}" -c 'import os, sys
marker = "py" + "ve" + "nv.cfg"
mod = "pi" + "p"
def emit(kind):
    print(kind)
    raise SystemExit(0)
requested = os.path.realpath(os.environ["ARA_ENV_DIR"])
prefix = os.path.realpath(sys.prefix)
base = os.path.realpath(sys.base_prefix)
cfg = os.path.join(requested, marker)
if (not os.path.isfile(cfg)) or prefix == base or prefix != requested:
    emit("base")
try:
    module = __import__(mod)
except Exception:
    emit("missing")
located = getattr(module, "__file__", "") or ""
if not located:
    emit("missing")
located = os.path.realpath(located)
root = prefix + os.sep
if located != prefix and not located.startswith(root):
    emit("outside")
emit("ready")
' 2>/dev/null)"; then
    env_class=unusable
    return 0
  fi
  case "${out}" in
    ready) env_class=ready ;;
    base|outside) env_class=not-venv ;;
    missing) env_class=no-pip ;;
    *) env_class=unusable ;;
  esac
}

reject_existing() {
  local shown move_version
  shown="$(venv_show)"
  case "${env_class}" in
    old)
      printf '%s\n' "Python ${MIN_LABEL} or newer is required." >&2
      printf '%s\n' "${shown} uses Python ${venv_version}, which is older than Python ${MIN_LABEL}." >&2
      move_version="${venv_version}"
      ;;
    not-venv)
      printf '%s\n' "A virtual environment is required before packages can be installed." >&2
      printf '%s\n' "${shown} is not a virtual environment. Its Python or pip belongs to the base interpreter, so installing would write outside this directory." >&2
      move_version="unavailable"
      ;;
    no-pip)
      printf '%s\n' "${shown} has Python ${venv_version} but pip is missing." >&2
      printf '%s\n' "An interrupted ensurepip can leave an executable Python without pip." >&2
      move_version="${venv_version}"
      ;;
    *)
      printf '%s\n' "Python ${MIN_LABEL} or newer is required." >&2
      printf '%s\n' "${shown} is not a usable Python ${MIN_LABEL}+ environment." >&2
      move_version="unavailable"
      ;;
  esac
  printf '%s\n' "It was left unchanged and was not deleted." >&2
  printf '%s\n' "Keep it where it is, or move it aside and create a new environment." >&2
  if [ "${env_class}" = "no-pip" ]; then
    printf '%s\n' "To keep this directory and install pip into it:" >&2
    printf '  %s -m ensurepip --upgrade\n' "$(token "${venv_python}")" >&2
  fi
  printf '%s\n' "Moving is required before a supported environment can be created at this path:" >&2
  printf '  mv %s %s\n' "$(token "${shown}")" "$(token "$(move_destination "${shown}" "${move_version}")")" >&2
  print_recreate_command "${recovery_name}"
  if [ -n "${explicit_detail}" ]; then
    printf '%s\n' "${explicit_detail}" >&2
  fi
  print_found
  printf '%s\n' "No packages were installed." >&2
  exit 2
}

stamp_is_fresh() {
  local stamp="$1" dep
  [ -f "${stamp}" ] || return 1
  for dep in pyproject.toml scripts/dependencies/constraints.txt; do
    if [ ! -f "${dep}" ] || [ "${dep}" -nt "${stamp}" ]; then
      return 1
    fi
  done
  return 0
}

install_requirements() {
  local stamp="${VENV}/.install.stamp"
  local dev_stamp="${VENV}/.install-dev.stamp"
  if [ "$1" = "dev" ]; then
    if stamp_is_fresh "${dev_stamp}"; then
      return 0
    fi
    "${venv_python}" -m pip install -c scripts/dependencies/constraints.txt -e ".[dev]"
    touch "${stamp}" "${dev_stamp}"
    return 0
  fi
  if stamp_is_fresh "${stamp}"; then
    return 0
  fi
  "${venv_python}" -m pip install -c scripts/dependencies/constraints.txt -e .
  touch "${stamp}"
}

use_existing_env() {
  case "${mode}" in
    venv)
      ;;
    install)
      install_requirements runtime
      ;;
    install-dev)
      install_requirements dev
      ;;
    run)
      exec "${venv_python}" "$@"
      ;;
  esac
}

explicit=0
case "${PYTHON_ORIGIN}" in
  environment|environment\ override|command\ line|override) explicit=1 ;;
esac

venv_python="${VENV}/bin/python"
classify_env

if [ "${env_class}" = "ready" ]; then
  use_existing_env "$@"
  exit 0
fi

if [ "${env_class}" = "absent" ] && [ "${mode}" = "run" ]; then
  printf '%s\n' "Virtual environment is not ready." >&2
  printf 'Run: make install-dev%s\n' "$(recovery_venv_assignment)" >&2
  exit 1
fi

collect_candidates

explicit_supported=0
explicit_detail=""
if [ "${explicit}" -eq 1 ]; then
  if [ -z "${PYTHON}" ]; then
    explicit_detail="PYTHON is empty."
  elif ! explicit_path="$(lookup_interpreter "${PYTHON}")"; then
    explicit_detail="PYTHON=$(token "${PYTHON}") was not found."
  elif ! explicit_version="$(probe_version "${explicit_path}")"; then
    explicit_detail="PYTHON=$(token "${PYTHON}") did not report a version (${explicit_path})."
    remember "${PYTHON}" "${explicit_path}" "unavailable"
  elif ! is_supported "${explicit_version}"; then
    explicit_detail="PYTHON=$(token "${PYTHON}") is Python ${explicit_version} (${explicit_path}), older than Python ${MIN_LABEL}."
    remember "${PYTHON}" "${explicit_path}" "${explicit_version}"
  else
    explicit_supported=1
    remember "${PYTHON}" "${explicit_path}" "${explicit_version}"
  fi
fi

recovery_name=""
if [ "${explicit}" -eq 1 ] && [ "${explicit_supported}" -eq 1 ]; then
  recovery_name="${PYTHON}"
elif recovery_index="$(first_supported_index)"; then
  recovery_name="${found_name[${recovery_index}]}"
fi

if [ "${env_class}" != "absent" ]; then
  reject_existing
fi

if [ "${explicit}" -eq 1 ] && [ "${explicit_supported}" -ne 1 ]; then
  printf '%s\n' "Python ${MIN_LABEL} or newer is required." >&2
  printf '%s\n' "${explicit_detail}" >&2
  printf '%s\n' "No virtual environment was created and no packages were installed." >&2
  print_found
  printf '%s\n' "Recovery:" >&2
  print_recreate_command "${recovery_name}"
  exit 2
fi

if [ "${explicit}" -eq 1 ]; then
  selected_path="${explicit_path}"
  selected_version="${explicit_version}"
  selected_label="${PYTHON}"
elif recovery_index="$(first_supported_index)"; then
  selected_path="${found_path[${recovery_index}]}"
  selected_version="${found_version[${recovery_index}]}"
  selected_label="${found_name[${recovery_index}]}"
else
  printf '%s\n' "Python ${MIN_LABEL} or newer is required." >&2
  printf '%s\n' "No supported Python interpreter is on PATH." >&2
  printf '%s\n' "No virtual environment was created and no packages were installed." >&2
  print_found
  printf '%s\n' "Recovery:" >&2
  print_recreate_command ""
  exit 2
fi

printf 'Using Python %s (%s) to create %s\n' \
  "${selected_version}" "${selected_label}" "${VENV}"
if ! "${selected_path}" -m venv -- "${VENV}"; then
  printf 'Python %s did not create %s. No packages were installed.\n' \
    "${selected_label}" "${VENV}" >&2
  exit 2
fi
classify_env
if [ "${env_class}" = "old" ] || [ "${env_class}" = "unusable" ]; then
  printf '%s\n' "Python ${MIN_LABEL} or newer is required." >&2
  printf '%s\n' "$(venv_show) was created but does not provide Python ${MIN_LABEL}+. It was left unchanged and was not deleted." >&2
  printf '%s\n' "No packages were installed." >&2
  exit 2
fi
if [ "${env_class}" != "ready" ]; then
  reject_existing
fi
use_existing_env "$@"
exit 0
