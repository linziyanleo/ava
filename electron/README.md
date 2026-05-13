# Ava Electron Shell

This is the P1b macOS `.app` shell. It starts the local Ava gateway as an `ava-core` sidecar, waits for `/api/gateway/health`, then loads the Console UI from the selected local core endpoint. Port `6688` is only the preferred starting point; the shell can choose a dynamic port when it is occupied.

## Local Build

```bash
nvm use
uv sync --extra dev
pnpm electron:build
```

Root `pnpm electron:build` installs the Electron shell dependencies from `electron/pnpm-lock.yaml`, builds Console UI, fetches pinned cloudflared artifacts, packages the app, ad-hoc signs it, and runs bundle verification.

For CI or checklist verification without downloading Electron:

```bash
pnpm electron:dry-run
```

The P1b app is still same-machine repo-coupled, but the build embeds an `ava-runtime-manifest.json` resource with this checkout's repo root. You may copy the generated `.app` to `/Applications` for Launchpad/App Drawer startup on this machine; it will still run code from this checkout and is not a copy-to-another-machine distribution package.

Finder/LaunchServices acceptance is closed through `../docs/desktop-launch-acceptance.md`, not by a bare `open` command. Before generating evidence, use `scripts/verify-desktop-handoff-ready.sh` for the happy-path command and `scripts/verify-desktop-handoff-ready.sh --port-conflict` before the dynamic-port command. Run the exact two-command handoff from the repo root, fill the visual result records, then run `scripts/verify-desktop-closeout-records.sh` before closing the desktop launch task.
