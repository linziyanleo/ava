#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ORIGINAL_COMMAND="$(printf '%q ' "$0" "$@")"
ORIGINAL_COMMAND="${ORIGINAL_COMMAND% }"
SKIP_BUILD=0
WITH_PORT_CONFLICT=0
EVIDENCE_LOG=""
EVIDENCE_LOG_STARTED=0
PORT_CONFLICT_PORT=6688
# Executed acceptance must always use 6688; sourced helper tests may override.
if [[ "${BASH_SOURCE[0]}" != "$0" && "${AVA_DESKTOP_VERIFY_ALLOW_CONFLICT_PORT_OVERRIDE:-0}" == "1" ]]; then
  PORT_CONFLICT_PORT="${AVA_DESKTOP_VERIFY_CONFLICT_PORT:-6688}"
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-build)
      SKIP_BUILD=1
      shift
      ;;
    --with-port-conflict)
      WITH_PORT_CONFLICT=1
      shift
      ;;
    --evidence-log)
      EVIDENCE_LOG="${2:-}"
      if [[ -z "${EVIDENCE_LOG}" ]]; then
        echo "--evidence-log requires a path" >&2
        exit 1
      fi
      shift 2
      ;;
    *)
      break
      ;;
  esac
done

APP_PATH="${1:-${REPO_ROOT}/electron/dist/Ava-darwin-arm64/Ava.app}"
PORT_CONFLICT_LOG="$(mktemp "${TMPDIR:-/tmp}/ava-port-conflict.XXXXXX")"
PORT_CONFLICT_DIR="$(mktemp -d "${TMPDIR:-/tmp}/ava-port-conflict-dir.XXXXXX")"
PORT_CONFLICT_MARKER="ava-port-conflict-${$}-${RANDOM}"
PORT_CONFLICT_PID=""

cleanup() {
  if [[ -n "${PORT_CONFLICT_PID}" ]]; then
    kill "${PORT_CONFLICT_PID}" 2>/dev/null || true
    wait "${PORT_CONFLICT_PID}" 2>/dev/null || true
  fi
  rm -f "${PORT_CONFLICT_LOG}"
  rm -rf "${PORT_CONFLICT_DIR}"
}

write_output() {
  if [[ -n "${EVIDENCE_LOG}" ]]; then
    tee -a "${EVIDENCE_LOG}"
  else
    cat
  fi
}

write_error_output() {
  if [[ -n "${EVIDENCE_LOG}" ]]; then
    tee -a "${EVIDENCE_LOG}" >&2
  else
    cat >&2
  fi
}

emit() {
  printf '%s\n' "$*" | write_output
}

emit_error() {
  printf '%s\n' "$*" | write_error_output
}

on_exit() {
  local status="$?"
  trap - EXIT
  cleanup
  if (( status != 0 )) && [[ -n "${EVIDENCE_LOG}" && "${EVIDENCE_LOG_STARTED}" == "1" ]]; then
    emit_error
    emit_error "Automated desktop acceptance checks failed with exit status ${status}."
    emit_error "Do not paste this evidence log into Result Records as a successful acceptance run."
  fi
  exit "${status}"
}
trap on_exit EXIT

run_step() {
  emit
  emit "==> $*"
  if [[ -n "${EVIDENCE_LOG}" ]]; then
    set +e
    "$@" 2>&1 | tee -a "${EVIDENCE_LOG}"
    local status="${PIPESTATUS[0]}"
    set -e
    return "${status}"
  fi
  "$@"
}

run_pre_evidence_step() {
  printf '\n==> %s\n' "$*"
  "$@"
}

require_node_for_build() {
  local version
  if ! version="$(node -p "process.versions.node" 2>/dev/null)"; then
    emit_error "Node.js 20.19.0 or newer is required to run pnpm electron:build; run nvm use 20.19.0 and retry."
    return 1
  fi
  if ! node -e "const [major, minor] = process.versions.node.split('.').map(Number); process.exit(major > 20 || (major === 20 && minor >= 19) ? 0 : 1)" >/dev/null 2>&1; then
    emit_error "Node.js 20.19.0 or newer is required to run pnpm electron:build; current Node is ${version}. Run nvm use 20.19.0 and retry."
    return 1
  fi
}

start_port_conflict_server() {
  emit
  emit "==> starting non-Ava server on 127.0.0.1:${PORT_CONFLICT_PORT}"
  printf '%s\n' "${PORT_CONFLICT_MARKER}" >"${PORT_CONFLICT_DIR}/ava-port-conflict.txt"
  python3 -m http.server "${PORT_CONFLICT_PORT}" --bind 127.0.0.1 --directory "${PORT_CONFLICT_DIR}" >"${PORT_CONFLICT_LOG}" 2>&1 &
  PORT_CONFLICT_PID="$!"
  local marker_body
  for _ in {1..20}; do
    if ! kill -0 "${PORT_CONFLICT_PID}" 2>/dev/null; then
      cat "${PORT_CONFLICT_LOG}" | write_error_output || true
      emit_error "failed to occupy 127.0.0.1:${PORT_CONFLICT_PORT}; stop the current listener and retry"
      exit 1
    fi
    marker_body="$(curl -fsS --max-time 1 "http://127.0.0.1:${PORT_CONFLICT_PORT}/ava-port-conflict.txt" 2>/dev/null || true)"
    if [[ "${marker_body}" == "${PORT_CONFLICT_MARKER}" ]]; then
      emit "127.0.0.1:${PORT_CONFLICT_PORT} is occupied by temporary non-Ava server"
      return
    fi
    sleep 0.2
  done
  cat "${PORT_CONFLICT_LOG}" | write_error_output || true
  emit_error "timed out waiting for temporary 127.0.0.1:${PORT_CONFLICT_PORT} server"
  exit 1
}

fail_if_runtime_meta_has_healthy_core() {
  local ava_home="${AVA_HOME:-${HOME}/.ava}"
  local meta_path="${ava_home}/console.json"
  [[ -f "${meta_path}" ]] || return 0

  local existing_core
  existing_core="$(python3 - "${meta_path}" <<'PY' || true
import json
import sys
import urllib.request
from pathlib import Path

meta_path = Path(sys.argv[1])
try:
    payload = json.loads(meta_path.read_text())
    port = int(payload.get("console_port"))
except Exception:
    sys.exit(1)

if port <= 0:
    sys.exit(1)

host = payload.get("console_host")
if not isinstance(host, str) or not host:
    host = "127.0.0.1"
if host in {"0.0.0.0", "::"}:
    host = "127.0.0.1"

try:
    with urllib.request.urlopen(f"http://{host}:{port}/api/gateway/health", timeout=0.5) as response:
        health = json.loads(response.read().decode("utf-8"))
except Exception:
    sys.exit(1)

is_ready = (
    isinstance(health, dict)
    and health.get("ready") is True
    and health.get("shutting_down") is False
    and isinstance(health.get("boot_generation"), (int, float))
)
if not is_ready:
    sys.exit(1)

print(f"{host}:{port}")
PY
)"
  if [[ -n "${existing_core}" ]]; then
    emit_error "runtime metadata points to an existing healthy Ava core at ${existing_core}; stop that core or clear ${meta_path} before running --with-port-conflict."
    exit 1
  fi
}

fail_if_conflict_port_has_healthy_core() {
  local existing_core
  existing_core="$(python3 - "${PORT_CONFLICT_PORT}" <<'PY' || true
import json
import sys
import urllib.request

port = int(sys.argv[1])
try:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/gateway/health", timeout=0.5) as response:
        health = json.loads(response.read().decode("utf-8"))
except Exception:
    sys.exit(1)

is_ready = (
    isinstance(health, dict)
    and health.get("ready") is True
    and health.get("shutting_down") is False
    and isinstance(health.get("boot_generation"), (int, float))
)
if not is_ready:
    sys.exit(1)

print(f"127.0.0.1:{port}")
PY
)"
  if [[ -n "${existing_core}" ]]; then
    emit_error "${existing_core} already hosts a healthy Ava core; stop that core before running --with-port-conflict."
    exit 1
  fi
}

validate_closeout_handoff_command() {
  local expected_command=""
  if [[ "${EVIDENCE_LOG}" == "docs/desktop-acceptance-happy.log" ]]; then
    expected_command="scripts/verify-desktop-acceptance.sh --evidence-log docs/desktop-acceptance-happy.log"
  elif [[ "${EVIDENCE_LOG}" == "docs/desktop-acceptance-port-conflict.log" ]]; then
    expected_command="scripts/verify-desktop-acceptance.sh --skip-build --with-port-conflict --evidence-log docs/desktop-acceptance-port-conflict.log"
  elif [[ "${EVIDENCE_LOG}" == docs/desktop-acceptance-* ]]; then
    local requested_evidence_log="${EVIDENCE_LOG}"
    EVIDENCE_LOG=""
    emit_error "Closeout evidence logs under docs/desktop-acceptance-* must use one of:"
    emit_error "scripts/verify-desktop-acceptance.sh --evidence-log docs/desktop-acceptance-happy.log"
    emit_error "scripts/verify-desktop-acceptance.sh --skip-build --with-port-conflict --evidence-log docs/desktop-acceptance-port-conflict.log"
    emit_error "Current evidence log: ${requested_evidence_log}"
    exit 1
  fi
  [[ -n "${expected_command}" ]] || return 0

  if [[ "${ORIGINAL_COMMAND}" != "${expected_command}" ]]; then
    local requested_evidence_log="${EVIDENCE_LOG}"
    EVIDENCE_LOG=""
    emit_error "Closeout evidence log ${requested_evidence_log} must be generated with exact command:"
    emit_error "${expected_command}"
    emit_error "Current command: ${ORIGINAL_COMMAND}"
    exit 1
  fi
}

print_manual_checklist() {
  local dynamic_port_result="not run by this command"
  local conflict_port_result="not run by this command"
  if (( WITH_PORT_CONFLICT == 1 )); then
    dynamic_port_result="automated --with-port-conflict verifier passed; fresh core required and endpoint port != ${PORT_CONFLICT_PORT}"
    conflict_port_result="${PORT_CONFLICT_PORT}"
  fi
  local evidence_log_value="${EVIDENCE_LOG:-not requested}"
  local record_date
  record_date="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

  cat <<CHECKLIST | write_output

Automated desktop acceptance checks passed.
Full desktop acceptance is not complete until the manual visual fields below are filled.

Manual visual checks still required in this normal macOS desktop session:
- Finder double-click Ava.app: no Terminal window is required.
- Happy path: Console loads after double-click.
- Setup path: local setup surface appears before Console when nanobot or .venv is missing.
- Cancel path: Cancel stops an active uv sync, and Retry starts a new attempt.
- Logs path: Help -> Open Logs opens ~/Library/Logs/Ava.
- Before running the port-conflict handoff, quit the Ava.app instance opened by the previous handoff and make sure 127.0.0.1:${PORT_CONFLICT_PORT} is free; run scripts/verify-desktop-handoff-ready.sh --port-conflict first.

Acceptance record fields:
- Date: ${record_date}
- Command: ${ORIGINAL_COMMAND}
- App path: ${APP_PATH}
- Evidence log: ${evidence_log_value}
- Conflict port: ${conflict_port_result}
- Console happy path: automated LaunchServices verifier passed
- Dynamic-port path: ${dynamic_port_result}
- Finder double-click, no Terminal:
- Setup surface visible before Console:
- Cancel stops uv sync, Retry starts again:
- Help -> Open Logs opens ~/Library/Logs/Ava:
- Notes / log excerpts:

Paste-ready result record:
\`\`\`text
Date: ${record_date}
Command: ${ORIGINAL_COMMAND}
App path: ${APP_PATH}
Evidence log: ${evidence_log_value}
Conflict port: ${conflict_port_result}
Console happy path: automated LaunchServices verifier passed
Dynamic-port path: ${dynamic_port_result}
Finder double-click, no Terminal:
Setup surface visible before Console:
Cancel stops uv sync, Retry starts again:
Help -> Open Logs opens ~/Library/Logs/Ava:
Notes / log excerpts:
\`\`\`

Record these fields in docs/desktop-launch-acceptance.md and the active Task Spec before closing the goal.
CHECKLIST
}

cd "${REPO_ROOT}"
validate_closeout_handoff_command

if (( WITH_PORT_CONFLICT == 1 )); then
  run_pre_evidence_step scripts/verify-desktop-handoff-ready.sh --port-conflict "${APP_PATH}"
else
  run_pre_evidence_step scripts/verify-desktop-handoff-ready.sh "${APP_PATH}"
fi

if [[ -n "${EVIDENCE_LOG}" ]]; then
  mkdir -p "$(dirname "${EVIDENCE_LOG}")"
  : >"${EVIDENCE_LOG}"
  EVIDENCE_LOG_STARTED=1
  emit "Evidence log: ${EVIDENCE_LOG}"
  emit "Date: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  emit "Command: ${ORIGINAL_COMMAND}"
  emit "App path: ${APP_PATH}"
  emit "Skip build: ${SKIP_BUILD}"
  emit "With port conflict: ${WITH_PORT_CONFLICT}"
  emit "Conflict port: ${PORT_CONFLICT_PORT}"
  emit "Handoff readiness preflight: passed before evidence logging"
fi

if (( SKIP_BUILD == 0 )); then
  require_node_for_build
  run_step pnpm electron:build
fi

run_step codesign --verify --deep --strict --verbose=1 "${APP_PATH}"
run_step scripts/verify-desktop-setup-surface.sh "${APP_PATH}"
run_step node scripts/verify-desktop-setup-dom.mjs
if (( WITH_PORT_CONFLICT == 1 )); then
  fail_if_conflict_port_has_healthy_core
  fail_if_runtime_meta_has_healthy_core
  start_port_conflict_server
  run_step env AVA_DESKTOP_VERIFY_REQUIRE_FRESH_CORE=1 AVA_DESKTOP_VERIFY_FORBID_ENDPOINT_PORT="${PORT_CONFLICT_PORT}" scripts/verify-desktop-launch.sh "${APP_PATH}"
else
  run_step scripts/verify-desktop-launch.sh "${APP_PATH}"
fi

print_manual_checklist
