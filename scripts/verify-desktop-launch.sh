#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_PATH="${1:-${REPO_ROOT}/electron/dist/Ava-darwin-arm64/Ava.app}"
MAIN_LOG="${HOME}/Library/Logs/Ava/main.log"
CORE_LOG="${HOME}/Library/Logs/Ava/core.log"
TIMEOUT_SECONDS="${AVA_DESKTOP_VERIFY_TIMEOUT:-45}"
REQUIRE_FRESH_CORE="${AVA_DESKTOP_VERIFY_REQUIRE_FRESH_CORE:-0}"
FORBID_ENDPOINT_PORT="${AVA_DESKTOP_VERIFY_FORBID_ENDPOINT_PORT:-}"

fail() {
  echo "verify-desktop-launch: $*" >&2
  exit 1
}

require_executable() {
  local executable="$1"
  [[ -x "${executable}" ]] || fail "missing executable: ${executable}"
}

require_mach_o_executable() {
  local executable="$1"
  require_executable "${executable}"
  local file_output
  file_output="$(file "${executable}")" || fail "cannot inspect executable type: ${executable}"
  [[ "${file_output}" == *"Mach-O 64-bit executable"* ]] || fail "main executable is not a Mach-O binary: ${file_output}"
  echo "Main executable: ${executable}"
  echo "Main executable type: ${file_output}"
}

absolute_app_path() {
  local app_path="$1"
  local app_dir
  app_dir="$(cd "$(dirname "${app_path}")" && pwd)" || return 1
  printf '%s/%s\n' "${app_dir}" "$(basename "${app_path}")"
}

read_plist_value() {
  local plist="$1"
  local key="$2"
  plutil -extract "${key}" raw -o - "${plist}" 2>/dev/null || return 1
}

running_app_pids() {
  local main_executable="$1"
  local bundle_executable="$2"

  local lsof_pids
  lsof_pids="$(
    lsof -nP -c "${bundle_executable}" 2>/dev/null \
      | awk -v target="${main_executable}" '$4 == "txt" && index($0, target) { print $2 }' \
      | sort -u
  )"
  if [[ -n "${lsof_pids}" ]]; then
    printf '%s\n' "${lsof_pids}"
    return 0
  fi

  local pgrep_output
  local pgrep_status
  set +e
  pgrep_output="$(pgrep -f "${main_executable}" 2>&1)"
  pgrep_status="$?"
  set -e
  if (( pgrep_status == 0 )); then
    printf '%s\n' "${pgrep_output}"
    return 0
  fi
  if (( pgrep_status > 1 )); then
    printf '%s\n' "${pgrep_output}" >&2
    return 2
  fi
  return 1
}

health_ready() {
  local endpoint="$1"
  local body
  body="$(curl -fsS --max-time 1 "${endpoint}/api/gateway/health" 2>/dev/null)" || return 1
  python3 -c '
import json
import sys

try:
    payload = json.loads(sys.stdin.read())
except json.JSONDecodeError:
    sys.exit(1)

ready = payload.get("ready") is True
not_shutting_down = payload.get("shutting_down") is False
has_boot_generation = isinstance(payload.get("boot_generation"), (int, float))
sys.exit(0 if ready and not_shutting_down and has_boot_generation else 1)
' <<<"${body}"
}

log_size() {
  local file="$1"
  [[ -f "${file}" ]] || {
    echo 0
    return
  }
  wc -c <"${file}" | tr -d ' '
}

log_identity() {
  local file="$1"
  [[ -f "${file}" ]] || return 0
  stat -f '%i' "${file}" 2>/dev/null || stat -c '%i' "${file}" 2>/dev/null || true
}

log_since() {
  local file="$1"
  local offset="$2"
  local previous_id="${3:-}"
  [[ -f "${file}" ]] || return 0
  local current_id
  local current_size
  current_id="$(log_identity "${file}")"
  current_size="$(log_size "${file}")"
  if [[ -n "${previous_id}" && -n "${current_id}" && "${current_id}" != "${previous_id}" ]]; then
    cat "${file}"
    return
  fi
  if (( current_size < offset )); then
    cat "${file}"
    return
  fi
  tail -c "+$((offset + 1))" "${file}" 2>/dev/null || true
}

latest_endpoint_from_new_log() {
  log_since "${MAIN_LOG}" "${MAIN_LOG_SIZE}" "${MAIN_LOG_ID}" | grep -Eo 'coreEndpoint=http://[^[:space:]]+' | tail -n 1 | cut -d= -f2-
}

latest_launch_config_from_new_log() {
  log_since "${MAIN_LOG}" "${MAIN_LOG_SIZE}" "${MAIN_LOG_ID}" | grep 'launch config ' | tail -n 1
}

fresh_core_required_but_reused_existing() {
  local launch_config
  launch_config="$(latest_launch_config_from_new_log || true)"
  [[ "${REQUIRE_FRESH_CORE}" == "1" && "${launch_config}" == *"externalCore=true"* ]]
}

endpoint_port() {
  local endpoint="$1"
  local host_port="${endpoint#http://}"
  host_port="${host_port%%/*}"
  printf '%s\n' "${host_port##*:}"
}

forbidden_endpoint_port_selected() {
  local endpoint="$1"
  [[ -n "${FORBID_ENDPOINT_PORT}" && "$(endpoint_port "${endpoint}")" == "${FORBID_ENDPOINT_PORT}" ]]
}

fail_on_new_core_errors() {
  local new_core
  new_core="$(log_since "${CORE_LOG}" "${CORE_LOG_SIZE}" "${CORE_LOG_ID}")"
  if grep -Eiq 'Gateway crashed unexpectedly|Traceback' <<<"${new_core}"; then
    echo "Ava opened but the new core log contains startup errors" >&2
    echo "--- new core.log ---" >&2
    printf '%s\n' "${new_core}" >&2
    exit 1
  fi
}

[[ -d "${APP_PATH}" ]] || fail "missing app bundle: ${APP_PATH}"
APP_ABS_PATH="$(absolute_app_path "${APP_PATH}")" || fail "cannot resolve app bundle path: ${APP_PATH}"
INFO_PLIST="${APP_ABS_PATH}/Contents/Info.plist"
[[ -f "${INFO_PLIST}" ]] || fail "missing Info.plist: ${INFO_PLIST}"
BUNDLE_EXECUTABLE="$(read_plist_value "${INFO_PLIST}" "CFBundleExecutable")" || fail "missing CFBundleExecutable in ${INFO_PLIST}"
[[ -n "${BUNDLE_EXECUTABLE}" ]] || fail "empty CFBundleExecutable in ${INFO_PLIST}"
MAIN_EXECUTABLE="${APP_ABS_PATH}/Contents/MacOS/${BUNDLE_EXECUTABLE}"
require_mach_o_executable "${MAIN_EXECUTABLE}"
set +e
RUNNING_APP_PIDS="$(running_app_pids "${MAIN_EXECUTABLE}" "${BUNDLE_EXECUTABLE}")"
RUNNING_APP_STATUS="$?"
set -e
if (( RUNNING_APP_STATUS == 0 )); then
  fail "Ava.app is already running from ${APP_ABS_PATH} (pid(s): ${RUNNING_APP_PIDS//$'\n'/, }); quit it before running this verifier."
fi
if (( RUNNING_APP_STATUS == 2 )); then
  fail "could not determine whether Ava.app is already running from ${APP_ABS_PATH}; pgrep failed and lsof found no matching executable."
fi
codesign --verify --deep --strict --verbose=1 "${APP_ABS_PATH}" >/dev/null

MAIN_LOG_SIZE="$(log_size "${MAIN_LOG}")"
CORE_LOG_SIZE="$(log_size "${CORE_LOG}")"
MAIN_LOG_ID="$(log_identity "${MAIN_LOG}")"
CORE_LOG_ID="$(log_identity "${CORE_LOG}")"

echo "Opening ${APP_ABS_PATH}"
if ! open -n "${APP_ABS_PATH}"; then
  fail "LaunchServices open failed. In the Codex sandbox this is expected; rerun from a normal macOS session."
fi

deadline=$((SECONDS + TIMEOUT_SECONDS))
while (( SECONDS < deadline )); do
  fail_on_new_core_errors
  endpoint="$(latest_endpoint_from_new_log || true)"
  if fresh_core_required_but_reused_existing; then
    fail "fresh core was required, but Ava reused an existing core. Stop the current Ava core or clear stale runtime metadata before rerunning this verifier."
  fi
  if [[ -n "${endpoint}" ]] && forbidden_endpoint_port_selected "${endpoint}"; then
    fail "Ava selected forbidden endpoint port ${FORBID_ENDPOINT_PORT}; expected a dynamic port while that port is occupied by the acceptance probe."
  fi
  if [[ -n "${endpoint}" ]] && health_ready "${endpoint}"; then
    echo "Ava Console is healthy at ${endpoint}"
    exit 0
  fi
  sleep 1
done

echo "Ava did not become healthy within ${TIMEOUT_SECONDS}s" >&2
echo "--- new main.log ---" >&2
log_since "${MAIN_LOG}" "${MAIN_LOG_SIZE}" "${MAIN_LOG_ID}" >&2 || true
echo "--- new core.log ---" >&2
log_since "${CORE_LOG}" "${CORE_LOG_SIZE}" "${CORE_LOG_ID}" >&2 || true
exit 1
