#!/usr/bin/env bash
set -euo pipefail

PORT="${PLAYWRIGHT_CDP_PORT:-9222}"
LOCAL_PROFILE_DIR="${PLAYWRIGHT_LOCAL_CHROME_PROFILE:-$HOME/Library/Application Support/Google/Chrome}"
PROFILE_DIR="${PLAYWRIGHT_CDP_PROFILE:-$LOCAL_PROFILE_DIR}"
LOG_FILE="${PLAYWRIGHT_CDP_LOG:-/tmp/cdp-chrome.log}"
CHROME_BIN="${CHROME_BIN:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"

is_listening() {
  curl -sS --max-time 1 "http://127.0.0.1:$PORT/json/version" >/dev/null 2>&1
}

listener_pids() {
  lsof -nP -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | sort -u
}

listener_matches_profile() {
  local pid cmd
  while IFS= read -r pid; do
    [[ -n "$pid" ]] || continue
    cmd="$(ps -p "$pid" -o command= 2>/dev/null || true)"
    if [[ "$cmd" == *"--user-data-dir=$PROFILE_DIR"* ]]; then
      return 0
    fi
    if [[ "$PROFILE_DIR" == "$LOCAL_PROFILE_DIR" && "$cmd" == *"--remote-debugging-port=$PORT"* && "$cmd" != *"--user-data-dir="* ]]; then
      return 0
    fi
  done < <(listener_pids)
  return 1
}

profile_lock_pid() {
  local lock target
  lock="$PROFILE_DIR/SingletonLock"
  target="$(readlink "$lock" 2>/dev/null || true)"
  if [[ "$target" =~ -([0-9]+)$ ]]; then
    echo "${BASH_REMATCH[1]}"
  fi
}

is_pid_alive() {
  local pid="$1"
  [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1
}

chrome_major_version() {
  "$CHROME_BIN" --version 2>/dev/null | awk '{split($NF, parts, "."); print parts[1]}'
}

if is_listening; then
  if listener_matches_profile; then
    echo "cdp_port=listening port=$PORT"
    echo "action=none reason=already_listening profile=$PROFILE_DIR"
    exit 0
  fi
  echo "cdp_port=listening port=$PORT"
  echo "action=failed reason=port_in_use_by_different_profile expected_profile=$PROFILE_DIR"
  echo "instruction=close_existing_cdp_chrome_or_choose_another_PLAYWRIGHT_CDP_PORT"
  exit 1
fi

if [[ ! -x "$CHROME_BIN" ]]; then
  echo "cdp_port=closed port=$PORT"
  echo "action=failed reason=chrome_binary_missing path=$CHROME_BIN"
  exit 1
fi

mkdir -p "$PROFILE_DIR"

lock_pid="$(profile_lock_pid)"
if is_pid_alive "$lock_pid"; then
  echo "cdp_port=closed port=$PORT"
  echo "action=failed reason=profile_in_use profile=$PROFILE_DIR pid=$lock_pid"
  echo "instruction=quit_chrome_and_rerun_to_enable_cdp_for_this_profile"
  exit 1
fi

if [[ "$PROFILE_DIR" == "$LOCAL_PROFILE_DIR" ]]; then
  major_version="$(chrome_major_version)"
  if [[ "$major_version" =~ ^[0-9]+$ ]] && (( major_version >= 136 )); then
    echo "cdp_port=closed port=$PORT"
    echo "action=failed reason=default_profile_cdp_blocked profile=$PROFILE_DIR chrome_major_version=$major_version"
    echo "instruction=chrome_136_plus_requires_non_standard_user_data_dir_for_remote_debugging"
    echo "alternative=use_extension_mode_for_daily_profile_or_set_PLAYWRIGHT_CDP_PROFILE_to_an_isolated_profile"
    exit 1
  fi
fi

if [[ "$(uname -s)" == "Darwin" ]] && command -v open >/dev/null 2>&1; then
  /usr/bin/open -na "Google Chrome" --args \
    --remote-debugging-port="$PORT" \
    --remote-debugging-address=127.0.0.1 \
    --user-data-dir="$PROFILE_DIR" \
    --no-first-run \
    --no-default-browser-check \
    about:blank \
    >"$LOG_FILE" 2>&1
else
  nohup "$CHROME_BIN" \
    --remote-debugging-port="$PORT" \
    --remote-debugging-address=127.0.0.1 \
    --user-data-dir="$PROFILE_DIR" \
    --no-first-run \
    --no-default-browser-check \
    about:blank \
    >"$LOG_FILE" 2>&1 &
fi

for _ in {1..16}; do
  if is_listening; then
    echo "cdp_port=listening port=$PORT"
    echo "action=started profile=$PROFILE_DIR log=$LOG_FILE"
    exit 0
  fi
  sleep 0.5
done

echo "cdp_port=closed port=$PORT"
echo "action=failed reason=port_not_ready log=$LOG_FILE"
exit 1
