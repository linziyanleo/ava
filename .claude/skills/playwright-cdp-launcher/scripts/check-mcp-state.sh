#!/usr/bin/env bash
set -u

CONFIG_FILE="${CLAUDE_CONFIG_FILE:-$HOME/.claude.json}"
MCP_NAME="${PLAYWRIGHT_CDP_MCP_NAME:-playwright-cdp}"
PORT="${PLAYWRIGHT_CDP_PORT:-9222}"

if pgrep -x "Google Chrome" >/dev/null 2>&1 || pgrep -f "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" >/dev/null 2>&1; then
  echo "chrome_process=running"
else
  echo "chrome_process=missing"
fi

if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "cdp_port=listening port=$PORT"
else
  echo "cdp_port=closed port=$PORT"
fi

if [[ ! -f "$CONFIG_FILE" ]]; then
  echo "mode=unknown config=missing"
elif ! command -v node >/dev/null 2>&1; then
  echo "mode=unknown config_probe=node_missing"
else
  node - "$CONFIG_FILE" "$MCP_NAME" <<'NODE'
const fs = require("fs");

const configPath = process.argv[2];
const mcpName = process.argv[3];

function findServer(config, name) {
  if (config && config.mcpServers && config.mcpServers[name]) {
    return config.mcpServers[name];
  }

  const projects = config && config.projects;
  if (projects && typeof projects === "object") {
    for (const project of Object.values(projects)) {
      if (project && project.mcpServers && project.mcpServers[name]) {
        return project.mcpServers[name];
      }
    }
  }

  return null;
}

try {
  const config = JSON.parse(fs.readFileSync(configPath, "utf8"));
  const server = findServer(config, mcpName);

  if (!server) {
    console.log("mode=unknown config=missing_mcp");
    process.exit(0);
  }

  const args = Array.isArray(server.args) ? server.args.map(String) : [];
  const hasExtension = args.includes("--extension");
  const hasCdpEndpoint = args.includes("--cdp-endpoint") || args.some((arg) => arg.startsWith("--cdp-endpoint="));

  if (hasCdpEndpoint) {
    console.log("mode=cdp-endpoint config=present");
  } else if (hasExtension) {
    console.log("mode=extension config=present");
  } else {
    console.log("mode=unknown config=present");
  }
} catch (_) {
  console.log("mode=unknown config=unreadable");
}
NODE
fi

mcp_line="$(claude mcp list 2>&1 | grep -E "(^|[[:space:]])${MCP_NAME}:" || true)"
if [[ -z "$mcp_line" ]]; then
  echo "playwright_cdp_mcp=missing"
elif [[ "$mcp_line" == *"✓ Connected"* ]]; then
  echo "playwright_cdp_mcp=connected"
elif [[ "$mcp_line" == *"✗ Failed"* ]]; then
  echo "playwright_cdp_mcp=failed"
else
  echo "playwright_cdp_mcp=unknown"
fi
