# Ava Electron Shell

This is the P1b macOS `.app` shell. It starts the local Ava gateway as an `ava-core` sidecar, waits for `/api/gateway/health`, then loads the Console UI from `http://127.0.0.1:6688/`.

## Local Build

```bash
nvm use
uv sync --extra dev
cd console-ui && npm install
cd ../electron && pnpm install
cd ..
pnpm electron:build
open electron/dist/Ava-darwin-arm64/Ava.app
```

For CI or checklist verification without downloading Electron:

```bash
pnpm electron:dry-run
```

The P1b app is repo-coupled: keep the generated `.app` under this checkout so the shell can find `scripts/start-ava.sh`, `ava/`, and `console-ui/`.
