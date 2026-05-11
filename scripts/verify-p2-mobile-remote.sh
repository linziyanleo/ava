#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UV_CACHE_DIR="${UV_CACHE_DIR:-/private/tmp/ava-uv-cache}"
export UV_CACHE_DIR

if [[ -s "${HOME}/.nvm/nvm.sh" && -f "${REPO_ROOT}/.nvmrc" ]]; then
  # shellcheck source=/dev/null
  source "${HOME}/.nvm/nvm.sh"
  nvm use >/dev/null
fi

if [[ -z "${AVA_NANOBOT_ROOT:-}" ]]; then
  for candidate in \
    "${REPO_ROOT}/../nanobot" \
    "${REPO_ROOT}/../../../nanobot"; do
    if [[ -f "${candidate}/pyproject.toml" && -f "${candidate}/nanobot/__main__.py" ]]; then
      export AVA_NANOBOT_ROOT="${candidate}"
      break
    fi
  done
fi

if [[ -z "${AVA_NANOBOT_ROOT:-}" ]]; then
  echo "AVA_NANOBOT_ROOT is required for P2 verification." >&2
  exit 1
fi

run() {
  echo "+ $*"
  "$@"
}

run_logged() {
  local log_name="$1"
  shift
  local log_dir="${P2_BROWSER_LOG_DIR:-${TMPDIR:-/tmp}/ava-p2-browser-e2e}"
  mkdir -p "$log_dir"
  echo "+ $*"
  "$@" 2>&1 | tee "${log_dir}/${log_name}.log"
}

preview_pid=""
preview_log=""
cleanup_preview() {
  if [[ -n "$preview_pid" ]]; then
    kill "$preview_pid" >/dev/null 2>&1 || true
  fi
}
trap cleanup_preview EXIT

start_preview_if_needed() {
  if [[ -n "${BASE_URL:-}" ]]; then
    return
  fi
  local port="${P2_PREVIEW_PORT:-4174}"
  BASE_URL="http://127.0.0.1:${port}"
  export BASE_URL
  preview_log="${TMPDIR:-/tmp}/ava-p2-preview-${port}.log"
  echo "+ npm run preview -- --host 127.0.0.1 --port ${port} --strictPort"
  (cd "${REPO_ROOT}/console-ui" && npm run preview -- --host 127.0.0.1 --port "$port" --strictPort) >"$preview_log" 2>&1 &
  preview_pid="$!"
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    if curl -fsSI "${BASE_URL}/lan/pair?pin=123456" >/dev/null 2>&1; then
      return
    fi
    sleep 1
  done
  cat "$preview_log" >&2
  echo "Vite preview did not become ready at ${BASE_URL}" >&2
  exit 1
}

run uv run --extra dev pytest tests/console tests/guardrails -q

pushd "${REPO_ROOT}/console-ui" >/dev/null
run npm run build
run node --check e2e/p2-lan-access.mjs
run node --check e2e/p2-mobile-pair.mjs
run node --check e2e/p2-responsive.mjs
run node e2e/p2-chain-bubble.mjs

if [[ "${RUN_BROWSER_E2E:-0}" == "1" ]]; then
  start_preview_if_needed
  export PW_BROWSER="${PW_BROWSER:-chromium}"
  run_logged p2-lan-access node e2e/p2-lan-access.mjs
  run_logged p2-mobile-pair node e2e/p2-mobile-pair.mjs
  run_logged p2-responsive node e2e/p2-responsive.mjs
fi
popd >/dev/null

run node electron/scripts/build.mjs --dry-run

if [[ "${RUN_PREVIEW_SMOKE:-0}" == "1" ]]; then
  start_preview_if_needed
  run curl -fsSI "${BASE_URL}/lan/pair?pin=123456"
fi

run git diff --check
