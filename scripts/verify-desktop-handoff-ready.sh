#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="happy"
APP_PATH=""
CONFLICT_PORT=6688
# Non-canonical preflight only; this script never writes evidence logs.
if [[ "${AVA_DESKTOP_HANDOFF_ALLOW_CONFLICT_PORT_OVERRIDE:-0}" == "1" ]]; then
  CONFLICT_PORT="${AVA_DESKTOP_HANDOFF_CONFLICT_PORT:-6688}"
fi

usage() {
  cat <<'TEXT'
Usage:
  scripts/verify-desktop-handoff-ready.sh [--happy] [app-path]
  scripts/verify-desktop-handoff-ready.sh --port-conflict [app-path]

This non-canonical preflight never writes evidence logs.
Run default/--happy before:
  scripts/verify-desktop-acceptance.sh --evidence-log docs/desktop-acceptance-happy.log

Run --port-conflict after quitting Ava.app and before:
  scripts/verify-desktop-acceptance.sh --skip-build --with-port-conflict --evidence-log docs/desktop-acceptance-port-conflict.log
TEXT
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --help|-h)
      usage
      exit 0
      ;;
    --happy)
      MODE="happy"
      shift
      ;;
    --port-conflict)
      MODE="port-conflict"
      shift
      ;;
    --*)
      echo "unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
    *)
      if [[ -n "${APP_PATH}" ]]; then
        echo "only one app-path may be provided" >&2
        usage >&2
        exit 2
      fi
      APP_PATH="$1"
      shift
      ;;
  esac
done
APP_PATH="${APP_PATH:-${REPO_ROOT}/electron/dist/Ava-darwin-arm64/Ava.app}"

FAILURES=0

blocker() {
  printf 'BLOCKED: %s\n' "$*" >&2
  FAILURES=$((FAILURES + 1))
}

ok() {
  printf 'OK: %s\n' "$*"
}

print_listener_context() {
  local pid="$1"
  local details
  details="$(lsof -nP -p "${pid}" 2>/dev/null || true)"
  local cwd
  cwd="$(awk '$4 == "cwd" { print $NF; exit }' <<<"${details}")"
  local executable
  executable="$(awk '$4 == "txt" { print $NF; exit }' <<<"${details}")"
  if [[ -n "${cwd}" ]]; then
    echo "Listener process cwd: ${cwd}" >&2
  fi
  if [[ -n "${executable}" ]]; then
    echo "Listener process executable: ${executable}" >&2
  fi
}

print_listener_remediation() {
  local owner="$1"
  local listener="$2"
  local pid
  pid="$(awk 'NR == 2 { print $2 }' <<<"${listener}")"
  echo "Use the listener row above to identify the owning process, stop ${owner} from its original app or terminal, then rerun: scripts/verify-desktop-handoff-ready.sh --port-conflict" >&2
  if [[ "${pid}" =~ ^[0-9]+$ ]]; then
    print_listener_context "${pid}"
    echo "If no original app or terminal is available, use normal SIGTERM: kill ${pid}" >&2
  fi
}

print_running_app_remediation() {
  local running_pids="$1"
  local pid
  pid="$(awk 'NF { print $1; exit }' <<<"${running_pids}")"
  echo "Quit the running Ava.app from Dock/Finder, then rerun the matching handoff preflight before generating evidence." >&2
  if [[ "${pid}" =~ ^[0-9]+$ ]]; then
    echo "If no app UI is available, use normal SIGTERM: kill ${pid}" >&2
  fi
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

check_node_version() {
  local version
  if ! version="$(node -p "process.versions.node" 2>/dev/null)"; then
    blocker "Node.js 20.19.0 or newer is required; run nvm use 20.19.0 before the handoff."
    return
  fi
  if node -e "const [major, minor] = process.versions.node.split('.').map(Number); process.exit(major > 20 || (major === 20 && minor >= 19) ? 0 : 1)" >/dev/null 2>&1; then
    ok "Node.js ${version} satisfies the handoff build requirement"
  else
    blocker "Node.js 20.19.0 or newer is required; current Node is ${version}. Run nvm use 20.19.0 before the handoff."
  fi
}

check_app_process() {
  if [[ ! -d "${APP_PATH}" ]]; then
    if [[ "${MODE}" == "port-conflict" ]]; then
      blocker "app bundle is missing: ${APP_PATH}; run the happy-path evidence command first because the port-conflict command uses --skip-build."
    else
      ok "app bundle is not present yet; the happy-path evidence command will build it"
    fi
    return
  fi

  local app_abs_path
  app_abs_path="$(absolute_app_path "${APP_PATH}")" || {
    blocker "cannot resolve app bundle path: ${APP_PATH}"
    return
  }
  local info_plist="${app_abs_path}/Contents/Info.plist"
  if [[ ! -f "${info_plist}" ]]; then
    blocker "app bundle is missing Info.plist: ${info_plist}"
    return
  fi
  local bundle_executable
  bundle_executable="$(read_plist_value "${info_plist}" "CFBundleExecutable")" || {
    blocker "app bundle is missing CFBundleExecutable: ${info_plist}"
    return
  }
  local main_executable="${app_abs_path}/Contents/MacOS/${bundle_executable}"
  local running_pids
  local running_status
  set +e
  running_pids="$(running_app_pids "${main_executable}" "${bundle_executable}")"
  running_status="$?"
  set -e
  if (( running_status == 0 )); then
    blocker "Ava.app is already running from ${app_abs_path} (pid(s): ${running_pids//$'\n'/, }); quit it before running an acceptance handoff command."
    print_running_app_remediation "${running_pids}"
    return
  fi
  if (( running_status == 2 )); then
    blocker "could not determine whether Ava.app is already running from ${app_abs_path}; pgrep failed and lsof found no matching executable."
    return
  fi
  ok "no running Ava.app process found for ${app_abs_path}"
}

check_frontable_desktop_session() {
  if [[ "$(uname -s)" != "Darwin" ]]; then
    ok "frontable desktop session check skipped outside macOS"
    return
  fi
  if ! command -v lsappinfo >/dev/null 2>&1; then
    blocker "lsappinfo is unavailable; cannot confirm this macOS session can make apps frontmost before visual evidence."
    return
  fi

  local front_asn
  if ! front_asn="$(lsappinfo front 2>/dev/null)" || [[ -z "${front_asn}" ]]; then
    blocker "cannot read the frontmost macOS app; run the handoff from an unlocked desktop session."
    return
  fi

  local front_info
  if ! front_info="$(lsappinfo info "${front_asn}" 2>/dev/null)" || [[ -z "${front_info}" ]]; then
    blocker "cannot inspect the frontmost macOS app (${front_asn}); run the handoff from an unlocked desktop session."
    return
  fi

  if grep -q 'bundleID="com.apple.loginwindow"' <<<"${front_info}"; then
    blocker "frontmost macOS session is loginwindow; unlock the Mac into a normal desktop session before visual evidence."
    printf '%s\n' "${front_info}" >&2
    return
  fi

  ok "frontmost macOS session is not loginwindow"
}

healthy_core_at_port() {
  local port="$1"
  python3 - "${port}" <<'PY'
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
}

healthy_core_from_runtime_meta() {
  local ava_home="${AVA_HOME:-${HOME}/.ava}"
  local meta_path="${ava_home}/console.json"
  [[ -f "${meta_path}" ]] || return 1

  python3 - "${meta_path}" <<'PY'
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
}

check_conflict_port_ready() {
  local existing_core
  if existing_core="$(healthy_core_at_port "${CONFLICT_PORT}" 2>/dev/null)"; then
    local listener
    listener="$(lsof -nP -iTCP:"${CONFLICT_PORT}" -sTCP:LISTEN 2>/dev/null || true)"
    if [[ -n "${listener}" ]]; then
      echo "Current listener on 127.0.0.1:${CONFLICT_PORT}:" >&2
      printf '%s\n' "${listener}" >&2
      print_listener_remediation "that Ava/core process" "${listener}"
    fi
    blocker "${existing_core} already hosts a healthy Ava core; stop that core before running the --with-port-conflict handoff."
    return
  fi

  local listener
  listener="$(lsof -nP -iTCP:"${CONFLICT_PORT}" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -n "${listener}" ]]; then
    printf '%s\n' "${listener}" >&2
    print_listener_remediation "that process" "${listener}"
    blocker "127.0.0.1:${CONFLICT_PORT} is already occupied; the port-conflict handoff must let the verifier start its controlled marker server."
    return
  fi
  ok "127.0.0.1:${CONFLICT_PORT} is free for the controlled port-conflict marker server"
}

check_runtime_meta_ready() {
  local existing_core
  if existing_core="$(healthy_core_from_runtime_meta 2>/dev/null)"; then
    blocker "runtime metadata points to a healthy Ava core at ${existing_core}; stop that core or clear stale runtime metadata before the --with-port-conflict handoff."
    return
  fi
  ok "runtime metadata does not point to a healthy Ava core"
}

cd "${REPO_ROOT}"
check_node_version
check_app_process
check_frontable_desktop_session
if [[ "${MODE}" == "port-conflict" ]]; then
  check_conflict_port_ready
  check_runtime_meta_ready
else
  ok "port-conflict-only checks skipped for happy-path handoff"
fi

if (( FAILURES > 0 )); then
  printf '\nDesktop handoff preflight found %s blocker(s). Fix them before generating canonical evidence logs.\n' "${FAILURES}" >&2
  if [[ "${MODE}" == "port-conflict" ]]; then
    echo "After fixing blockers, rerun: scripts/verify-desktop-handoff-ready.sh --port-conflict" >&2
  else
    echo "After fixing blockers, rerun: scripts/verify-desktop-handoff-ready.sh" >&2
  fi
  exit 1
fi

cat <<'TEXT'

Desktop handoff preflight passed.
TEXT
if [[ "${MODE}" == "port-conflict" ]]; then
  echo "Run the exact port-conflict evidence command from the repo root:"
  echo
  echo "scripts/verify-desktop-acceptance.sh --skip-build --with-port-conflict --evidence-log docs/desktop-acceptance-port-conflict.log"
else
  echo "Run the exact happy-path evidence command from the repo root:"
  echo
  echo "scripts/verify-desktop-acceptance.sh --evidence-log docs/desktop-acceptance-happy.log"
  echo
  echo "After it passes, quit Ava.app and rerun:"
  echo "scripts/verify-desktop-handoff-ready.sh --port-conflict"
fi
