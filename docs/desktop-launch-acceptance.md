# Desktop Launch Acceptance Checklist

Date: 2026-05-13

Use this checklist outside the Codex sandbox to close the Finder double-click acceptance for `Ava.app`.

For a focused human-run checklist with reversible setup-trigger steps, use
[`docs/desktop-manual-visual-checklist.md`](desktop-manual-visual-checklist.md).

## Build

```bash
cd /Users/fanghu/Documents/Test/ava
nvm use 20.19.0
pnpm electron:build
codesign --verify --deep --strict --verbose=1 electron/dist/Ava-darwin-arm64/Ava.app
scripts/verify-desktop-setup-surface.sh
node scripts/verify-desktop-setup-dom.mjs
scripts/verify-desktop-launch.sh
# Or run the full automated sequence:
scripts/verify-desktop-acceptance.sh
# To verify dynamic-port startup while 6688 is occupied by a non-Ava process:
scripts/verify-desktop-acceptance.sh --skip-build --with-port-conflict
# To capture closeout evidence, use the exact two-command handoff below.
```

Use these exact handoff commands before closing the Task Spec. Run them from the repo root after `nvm use 20.19.0`, in this order; the second command intentionally reuses the app bundle built and signed by the first command.
After the first command passes, quit the `Ava.app` instance it opened before running the second command; the port-conflict verifier requires a fresh app process and a free `127.0.0.1:6688`.
When either canonical evidence-log path is used, `scripts/verify-desktop-acceptance.sh` fails fast unless the command line exactly matches the corresponding command below.
Any `docs/desktop-acceptance-*` evidence path that is not one of the two canonical paths below is rejected, because `scripts/verify-desktop-closeout-records.sh` will not accept it.
The optional readiness preflight below is non-canonical and never writes evidence logs. The default mode checks the happy-path handoff blockers only; run `--port-conflict` after quitting the first `Ava.app` instance and before the second command.
If either preflight reports an already-running `Ava.app`, quit that app from Dock/Finder first. If no app UI is available, use normal SIGTERM with the printed PID; avoid `kill -9` unless SIGTERM fails. Then rerun the same preflight before generating evidence.
If `--port-conflict` reports a listener on `127.0.0.1:6688`, use the printed `lsof` row to identify the owning process. If the preflight says it is a healthy Ava core, stop that Ava/core process from its original app or terminal; otherwise stop the owning process shown by `lsof`. If no original app or terminal is available, use normal SIGTERM with `kill <PID>` from the `lsof` row; avoid `kill -9` unless SIGTERM fails. Then rerun `scripts/verify-desktop-handoff-ready.sh --port-conflict` before generating the canonical port-conflict evidence log.

```bash
scripts/verify-desktop-handoff-ready.sh
scripts/verify-desktop-handoff-ready.sh --port-conflict
```

```bash
scripts/verify-desktop-acceptance.sh --evidence-log docs/desktop-acceptance-happy.log
scripts/verify-desktop-acceptance.sh --skip-build --with-port-conflict --evidence-log docs/desktop-acceptance-port-conflict.log
```

After both commands pass and the human visual fields are filled in this document and the active Task Spec, run:

```bash
scripts/verify-desktop-closeout-records.sh
```

Expected:

- `pnpm electron:build` installs Electron shell dependencies automatically.
- `scripts/verify-desktop-acceptance.sh` fails fast before build if the active shell is not on Node.js `20.19.0` or newer; run `nvm use 20.19.0` and retry.
- Console UI build passes.
- cloudflared fetch passes.
- electron-packager writes `electron/dist/Ava-darwin-arm64/Ava.app`.
- local ad-hoc signing completes.
- `codesign --verify` reports the app is valid on disk.
- The build script verifies `Info.plist` `CFBundleExecutable`, the matching main app executable, and Electron helper executables before signing.
- `scripts/verify-desktop-setup-surface.sh` confirms the local setup surface, desktop IPC wiring, setup load timeout, Cancel kill guard, startup stderr-tail dialog, and Help -> Open Logs menu wiring are present in source and packaged `app.asar`.
- `node scripts/verify-desktop-setup-dom.mjs` confirms the setup page script renders bootstrap/canceled state and that Select Nanobot, Retry, Cancel, and Open Logs buttons call the expected desktop IPC methods.
- `scripts/verify-desktop-launch.sh` verifies the `CFBundleExecutable` target is executable and reports as a Mach-O binary, then opens the app through LaunchServices and waits for strict Ava `/api/gateway/health` (`ready=true`, `shutting_down=false`, `boot_generation` present).
- `scripts/verify-desktop-launch.sh` samples `main.log` / `core.log` identity and byte size before launch, then only accepts a health endpoint from the new launch log segment; if Electron rotates/recreates logs during startup, it reads the recreated file from the beginning. If the new core log contains a gateway crash or traceback, it fails instead of passing against an older healthy core. Optional channel/MCP startup errors do not replace the strict `coreEndpoint` + health check.
- `scripts/verify-desktop-launch.sh` fails early if the same `Ava.app` executable is already running, because the single-instance path does not prove a fresh Finder launch. It detects the running bundle executable with `lsof` before falling back to `pgrep`, because some sandboxed shells cannot read the process list with `pgrep`.
- `scripts/verify-desktop-handoff-ready.sh` reports local blockers before canonical evidence generation. Default mode checks Node.js `20.19.0+` and the target `Ava.app` process for the happy-path command; it detects a running app from the bundle executable path with `lsof` before falling back to `pgrep`, because some sandboxed shells cannot read the process list with `pgrep`. If the app is running, it prints the PID and an advisory normal SIGTERM fallback for cases where Dock/Finder is unavailable. `--port-conflict` additionally requires `127.0.0.1:6688` to be free and runtime metadata not to point at a healthy Ava core. It does not replace either exact evidence command.
- `scripts/verify-desktop-acceptance.sh` runs the matching handoff readiness preflight before evidence log creation/truncation and before build/codesign, so local blockers cannot overwrite a previous closeout log. After the preflight passes, it runs build, codesign, packaged setup, setup DOM, and LaunchServices checks, and finally prints the visual checks that still need human confirmation. It pre-fills the acceptance record fields it can prove from the current run. With `--with-port-conflict`, it always occupies `127.0.0.1:6688` with a controlled non-Ava server and marker file before the LaunchServices check, then requires a fresh Ava core instead of passing through existing-core attach. If `127.0.0.1:6688` already hosts a healthy Ava core, or `~/.ava/console.json` already points to a healthy Ava core, this mode fails before launch; stop that core or clear stale runtime metadata first. With `--evidence-log <path>`, it tees post-preflight output to a local evidence log and records date, command, app path, skip-build, port-conflict setting, conflict port, and that the preflight passed before logging. Failed automated runs after evidence logging starts append a failure marker telling you not to paste that log into Result Records as a successful acceptance run.

## Finder Double-Click

`scripts/verify-desktop-launch.sh` closes the happy path where Ava should load an already healthy Console after a LaunchServices open.
It does not prove the local setup surface is visible. The setup/failure cases below still require visual confirmation in a normal macOS desktop session.

1. Open Finder at `electron/dist/Ava-darwin-arm64/`.
2. Double-click `Ava.app`.
3. Confirm no Terminal window is required.
4. If the external nanobot checkout is configured and `.venv/bin/python` exists, Ava should load Console.
5. If nanobot or `.venv` is missing, Ava should show the local setup surface before Console is healthy.

Logs:

- Main log: `~/Library/Logs/Ava/main.log`
- Sidecar log: `~/Library/Logs/Ava/core.log`
- Desktop config: `~/Library/Application Support/Ava/desktop.json`

## Failure Cases

- Delete or move `~/Library/Application Support/Ava/desktop.json`, then relaunch. Expected: setup asks for nanobot checkout.
- Point nanobot selection at a non-checkout directory. Expected: validation error; config is not saved.
- Temporarily rename `.venv`, then relaunch. Expected: setup runs `uv sync --extra dev`; Cancel stops the bootstrap child; Retry can run again.
- Occupy port `6688`, then relaunch. Expected: Electron chooses another port and Console still loads.
- If port `6688` or `~/.ava/console.json` points to an existing healthy Ava Console, relaunch. Expected: Electron attaches to that core instead of starting a second sidecar.

## Evidence Checklist

- Console happy path: `scripts/verify-desktop-launch.sh` exits 0 outside the Codex sandbox.
- Optional readiness preflight: `scripts/verify-desktop-handoff-ready.sh` exits 0 before the happy-path evidence command, and `scripts/verify-desktop-handoff-ready.sh --port-conflict` exits 0 immediately before the dynamic-port evidence command; if either reports blockers, fix them before generating evidence logs. For `127.0.0.1:6688` blockers, stop the listener shown by the preflight and rerun the preflight before the evidence command.
- Full automated evidence run: `scripts/verify-desktop-acceptance.sh --evidence-log docs/desktop-acceptance-happy.log` exits 0 outside the Codex sandbox.
- Dynamic-port evidence run: `scripts/verify-desktop-acceptance.sh --skip-build --with-port-conflict --evidence-log docs/desktop-acceptance-port-conflict.log` exits 0 outside the Codex sandbox; this mode preflights `127.0.0.1:6688` and `~/.ava/console.json`, sets `AVA_DESKTOP_VERIFY_REQUIRE_FRESH_CORE=1`, and forbids the launched endpoint from using the occupied conflict port, so it fails if Ava would reuse an existing healthy core or bind to `6688` instead of starting against a dynamic port.
- Fresh app process path: the verifier starts from no running `Ava.app` process for the target bundle.
- Existing-core attach path: with an already healthy Ava core, the verifier should pass only if the newly opened app writes a fresh `coreEndpoint=...` launch log and does not append port-conflict errors to the new `core.log` segment.
- Setup packaged contract: `scripts/verify-desktop-setup-surface.sh` exits 0.
- Setup DOM contract: `node scripts/verify-desktop-setup-dom.mjs` exits 0.
- Same-machine Applications launch contract: packaged `Contents/Resources/ava-runtime-manifest.json` contains the current repo root, so a copy under `/Applications` can still locate `scripts/start-ava.sh`; this does not make the app portable to another machine.
- Setup path: a human confirms the local setup surface appears before Console when nanobot or `.venv` is missing.
- Cancel path: a human confirms Cancel stops the active `uv sync`, and Retry starts it again.
- Logs path: a human confirms Help -> Open Logs opens `~/Library/Logs/Ava`.

## Result Record Template

```text
Date:
Command:
App path:
Evidence log:
Conflict port:
Console happy path:
Dynamic-port path:
Finder double-click, no Terminal:
Setup surface visible before Console:
Cancel stops uv sync, Retry starts again:
Help -> Open Logs opens ~/Library/Logs/Ava:
Notes / log excerpts:
```

## Result Records

Canonical automated evidence logs and human visual confirmations have been recorded. Keep the two records below mirrored with the active Task Spec.
Each successful acceptance run prints a `Paste-ready result record` block at the end of its evidence log; use that block as the base record, then fill the human visual confirmation fields.
The `Command` field must exactly match the corresponding handoff command, including the `--evidence-log ...` path.
The human visual confirmation fields must match exactly between this document and the active Task Spec.
Do not use any evidence log containing `Automated desktop acceptance checks failed` as a successful Result Record.
Do not treat `Automated desktop acceptance checks passed` alone as full acceptance; the Finder, setup, Cancel/Retry, and Help -> Open Logs fields must be filled before closing the Task Spec.
For the happy-path evidence run, `Conflict port` should remain `not run by this command`; only the `--with-port-conflict` run should record the occupied port.
After future evidence reruns, update this section and the active Task Spec together, then run `scripts/verify-desktop-closeout-records.sh`; it must pass before the Task Spec can be closed.

```text
Date: 2026-05-13T02:49:35Z
Command: scripts/verify-desktop-acceptance.sh --evidence-log docs/desktop-acceptance-happy.log
App path: /Users/fanghu/Documents/Test/ava/electron/dist/Ava-darwin-arm64/Ava.app
Evidence log: docs/desktop-acceptance-happy.log
Conflict port: not run by this command
Console happy path: automated LaunchServices verifier passed
Dynamic-port path: not run by this command
Finder double-click, no Terminal: Confirmed in normal macOS desktop session: Finder double-click opened Ava.app without requiring Terminal, and Console loaded.
Setup surface visible before Console: Confirmed: with .venv temporarily moved aside, Ava Setup appeared before Console and showed bootstrap state plus log tail.
Cancel stops uv sync, Retry starts again: Confirmed: Cancel stopped the active bootstrap and showed canceled state; Retry started a new bootstrap attempt.
Help -> Open Logs opens ~/Library/Logs/Ava: Confirmed: Help -> Open Logs opened Finder at /Users/fanghu/Library/Logs/Ava.
Notes / log excerpts:
```

```text
Date: 2026-05-13T02:50:35Z
Command: scripts/verify-desktop-acceptance.sh --skip-build --with-port-conflict --evidence-log docs/desktop-acceptance-port-conflict.log
App path: /Users/fanghu/Documents/Test/ava/electron/dist/Ava-darwin-arm64/Ava.app
Evidence log: docs/desktop-acceptance-port-conflict.log
Conflict port: 6688
Console happy path: automated LaunchServices verifier passed
Dynamic-port path: automated --with-port-conflict verifier passed; fresh core required and endpoint port != 6688
Finder double-click, no Terminal: Confirmed in normal macOS desktop session: Finder double-click opened Ava.app without requiring Terminal, and Console loaded.
Setup surface visible before Console: Confirmed: with .venv temporarily moved aside, Ava Setup appeared before Console and showed bootstrap state plus log tail.
Cancel stops uv sync, Retry starts again: Confirmed: Cancel stopped the active bootstrap and showed canceled state; Retry started a new bootstrap attempt.
Help -> Open Logs opens ~/Library/Logs/Ava: Confirmed: Help -> Open Logs opened Finder at /Users/fanghu/Library/Logs/Ava.
Notes / log excerpts:
```

## Ad-Hoc Port Conflict Probe

The full dynamic-port acceptance evidence must use `scripts/verify-desktop-acceptance.sh --skip-build --with-port-conflict --evidence-log docs/desktop-acceptance-port-conflict.log`.
The manual helper below is only for ad-hoc debugging; it does not replace the runner because it lacks the controlled marker file, fresh-core guard, and evidence log.

```bash
python3 -m http.server 6688 --bind 127.0.0.1
```

## Current Sandbox Limitation

Inside the current Codex sandbox, `open -n <app>` returns `NSOSStatusErrorDomain Code=-10827 kLSNoExecutableErr` even for `/System/Applications/Calculator.app`. Treat that as environment-blocked, not as Ava-specific proof.

The full acceptance wrapper has also been run inside the sandbox with Node.js `20.19.0`: build, codesign, packaged setup verifier, and setup DOM verifier pass, then the same LaunchServices `kLSNoExecutableErr` stops `scripts/verify-desktop-launch.sh`.

After the previous live app/core blockers exited, the same sandbox still cannot generate canonical evidence because process enumeration is denied: `pgrep` returns `sysmond service not found` / `Cannot get process list`, and `ps` returns `operation not permitted`. The handoff preflight intentionally fails closed in that state if `lsof` has no matching target app executable; rerun the handoff and evidence commands from a normal macOS session.

Finder automation is also blocked from this session: Computer Use returns an approval denial for `com.apple.finder`, and `osascript -e 'tell application "Finder" to open ...'` fails with a HiServices/Finder access error for both Ava and Calculator. Computer Use can list `Ava — com.electron.ava [running]`, but `get_app_state` for `com.electron.ava` is also approval-denied, so this session cannot inspect the Ava window or substitute for the human visual fields.

Running `Ava.app/Contents/MacOS/Ava` directly is not a replacement for Finder acceptance. In the current sandbox it aborts before creating Ava logs, while LaunchServices also fails for Calculator; close this checklist from a normal macOS desktop session with `scripts/verify-desktop-launch.sh` plus the visual setup checks above.
