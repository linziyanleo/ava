#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MCP_BIN="${PLAYWRIGHT_MCP_BIN:-/Users/fanghu/.local/share/mcp-runners/node_modules/.bin/playwright-mcp}"
CDP_ENDPOINT="${PLAYWRIGHT_CDP_ENDPOINT:-http://127.0.0.1:${PLAYWRIGHT_CDP_PORT:-9222}}"
NO_DEFAULTS_SHIM="$SCRIPT_DIR/playwright-mcp-cdp-no-defaults.cjs"

export NODE_OPTIONS="${NODE_OPTIONS:-"--require $NO_DEFAULTS_SHIM"}"
export NO_PROXY="${NO_PROXY:-127.0.0.1,localhost,::1}"
export no_proxy="${no_proxy:-127.0.0.1,localhost,::1}"

bash "$SCRIPT_DIR/start-cdp-chrome.sh"

if [[ "$#" -eq 0 ]]; then
  set -- --cdp-endpoint "$CDP_ENDPOINT"
fi

exec "$MCP_BIN" "$@"
