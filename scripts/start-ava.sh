#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_NANOBOT_ROOT="${REPO_ROOT}/../nanobot"
NANOBOT_ROOT="${AVA_NANOBOT_ROOT:-${DEFAULT_NANOBOT_ROOT}}"

if [[ ! -f "${NANOBOT_ROOT}/pyproject.toml" || ! -f "${NANOBOT_ROOT}/nanobot/__main__.py" ]]; then
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
