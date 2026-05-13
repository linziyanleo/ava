#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_NANOBOT_ROOT="${REPO_ROOT}/../nanobot"
NANOBOT_ROOT="${AVA_NANOBOT_ROOT:-${DEFAULT_NANOBOT_ROOT}}"

json_string() {
  local value="$1"
  value="${value//\\/\\\\}"
  value="${value//\"/\\\"}"
  printf '"%s"' "$value"
}

if [[ ! -f "${NANOBOT_ROOT}/pyproject.toml" || ! -f "${NANOBOT_ROOT}/nanobot/__main__.py" || ! -f "${NANOBOT_ROOT}/nanobot/cli/commands.py" ]]; then
  if [[ "${AVA_DESKTOP:-}" == "1" ]]; then
    printf '{"error":"nanobot_not_found","path":%s,"message":"nanobot checkout not found"}\n' "$(json_string "${NANOBOT_ROOT}")" >&2
  fi
  echo "nanobot checkout not found: ${NANOBOT_ROOT}" >&2
  echo "Set AVA_NANOBOT_ROOT to a full HKUDS/nanobot checkout." >&2
  exit 1
fi

if [[ -n "${AVA_PYTHON:-}" ]]; then
  PYTHON_BIN="${AVA_PYTHON}"
elif [[ -x "${REPO_ROOT}/.venv/bin/python" ]]; then
  PYTHON_BIN="${REPO_ROOT}/.venv/bin/python"
elif [[ -x "${NANOBOT_ROOT}/.venv/bin/python" ]]; then
  PYTHON_BIN="${NANOBOT_ROOT}/.venv/bin/python"
else
  PYTHON_BIN="$(command -v python3 || command -v python)"
fi

export AVA_NANOBOT_ROOT="${NANOBOT_ROOT}"
export PYTHONPATH="${REPO_ROOT}:${NANOBOT_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"

exec "${PYTHON_BIN}" -m ava "$@"
