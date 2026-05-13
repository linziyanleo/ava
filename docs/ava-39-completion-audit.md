# AVA-39 Completion Audit

Date: 2026-05-13

Objective: complete AVA-39 through PR-1~PR-6, executed in order as AVA-40 -> AVA-41 -> AVA-42 -> AVA-43 -> AVA-44 -> AVA-45, with each PR implemented, verified, committed separately, and reflected in spec/checklist state.

## Prompt-to-Artifact Checklist

| Requirement | Evidence | Status |
|---|---|---|
| AVA-40 / PR-1 implemented separately | main branch commit `4ad25de feat(console-ui): clean up chat header legacy paths`; Task Spec PR-1 execute log records ChatPage cleanup, Context Lens rename, token UI cleanup, redirect deprecation | Done |
| AVA-40 / PR-1 verified | focused grep, `npm exec -- tsc -b`, `npm run build`, focused eslint, `git diff --check`; Playwright verified desktop/mobile chat, Context Lens open, one HudBar Token widget, and dev `/agents` redirect warning | Done; full `pnpm -C console-ui lint` remains blocked by unrelated existing baseline |
| AVA-41 / PR-2 implemented separately | main branch commit `dd84efa feat(console-ui): normalize layout padding ownership`; Task Spec PR-2 execute log records Layout padding ownership, Chat/Settings margin cleanup, Settings tree | Done |
| AVA-41 / PR-2 verified | targeted grep, `npm exec -- tsc -b`, `npm run build`, `git diff --check`; Playwright verified 20 terminal `/settings/*` routes at desktop/mobile with no outer document scroll/overflow | Done; focused eslint only hit existing unrelated baseline in touched files |
| AVA-42 / PR-3 implemented separately | main branch commit `84ac0c6 feat(electron): add macos shell menu and dock behavior`; Task Spec PR-3 execute log records macOS lifecycle and menu | Done with live Dock visual follow-up |
| AVA-42 / PR-3 verified | `node --check electron/main.mjs`, targeted desktop pytest, `git diff --check`; rebuilt package live System Events check verified `Cmd+W` hides the window without quitting, `Ctrl+Shift+A` restores it, Dock click restores it, and Help -> Open Logs opens `~/Library/Logs/Ava/` | Done |
| AVA-43 / PR-4 implemented separately | main branch commit `6082bf6 feat(electron): wire bootstrap and task notifications`; Task Spec PR-4 execute log records bootstrap replay, banner, BG task notifications, TaskFloater bridge, Retry Core | Done with OS notification visual follow-up |
| AVA-43 / PR-4 verified | Electron targeted pytest, `npm exec -- tsc -b`, focused eslint, `npm run build`, `git diff --check`; mocked Electron runtime test verifies `ava:showNotification` click restores/creates the window and sends `ava:openTaskFloater` with the task id | Done with live OS notification click blocked |
| AVA-44 / PR-5 implemented separately | main branch commit `14f72ed feat(electron): add deep links and artifact reveal`; Task Spec PR-5 execute log records deep-link routing, Info.plist injection, revealArtifact allowlist, `openPath` removal | Done |
| AVA-44 / PR-5 verified | `node --check`, focused eslint, targeted desktop pytest, dry-run build, `npm run build`, `git diff --check`; rebuilt bundle contains `CFBundleURLTypes` with `ava` scheme; mocked Electron runtime test verifies legal `revealArtifact` calls `shell.showItemInFolder` and invalid ids do not update it; live packaged-app UI clicked `Reveal in Finder` for media record `37b70c8f0a75` and Finder selected `/Users/fanghu/.ava/media/generated/37b70c8f0a75_4.png`; `open 'ava://settings/system/version'` routed the packaged app to `/settings/system/version` | Done |
| AVA-45 / PR-6 implemented separately | latest main branch `HEAD` commit `feat(electron): add tray badge and update checks`; includes tray, Ctrl+Shift+A shortcut, Dock badge IPC, BG task badge sync, 5s update check, optional GitHub token support, update notification outcome logging, foreground activation/present flow, desktop runtime port-conflict hardening, packaged runtime mirror, Safe Storage keychain prompt guard, login-item cold startup timeout guard, tray icon resize guard, restore-window setup-abort guard, CHANGELOG, release notes, and this audit | Done |
| AVA-45 / PR-6 verified | `node --check`, focused TS/eslint, targeted desktop pytest, dry-run build, real Node 20.19 `pnpm electron:build`, packaged setup verifier, setup DOM verifier, codesign, fresh LaunchServices startup from empty runtime mirror, LaunchServices restart with existing mirror, `git diff --check`; update-check contract covers newer/equal/missing-version/invalid-repo paths and token header behavior; packaged setup verifier checks foreground activation/present flow, Safe Storage keychain switch, 120s core startup timeout, tray 18x18 resize, restore-window setup-abort guard, badge IPC, invalid badge count, 5s scheduler, update-check strings, GitHub token env strings, packaged runtime mirror, and desktop runtime port env strings in `app.asar`; desktop contract now asserts the macOS `use-mock-keychain` switch runs before single-instance setup; mocked Electron runtime test verifies Tray/menu structure, global shortcut registration, Dock badge values, and update notification click opening the release URL; live System Events check verified Tray menu labels and Tray Open Logs; live Dock screenshot evidence verified active BG-task badge `4` and admin clear; live authenticated `cli/cli` update check returned `v2.92.0`; LaunchServices-started packaged app logged `update notification shown for v2.92.0`; NotificationCenter `AXPress` on the visible update notification opened `https://github.com/cli/cli/releases/tag/v2.92.0` in Chrome | Done |
| CHANGELOG records each PR | `CHANGELOG.md` lists PR-1 through PR-6 | Done |
| 0.2.0 release notes list redirect-matrix 0.3.0 removal plan | `docs/release-notes-0.2.0.md` documents legacy redirect deprecation and planned 0.3.0 cleanup | Done |
| Task Spec updated | `.specanchor/tasks/_cross-module/2026-05-13_legacy-cleanup-and-desktop-shell-uplift.spec.md` has PR-1~PR-6 execute logs, review verdicts, plan-execution diff, and current packaged evidence | Done |
| Module specs updated | `.specanchor/modules/electron.spec.md`, `.specanchor/modules/console-ui-src.spec.md`, ChatPage and SettingsPage module specs reflect the landed changes | Done |
| Checklist state reconciled | Task Spec checklist separates automated/browser contract evidence from real macOS visual checks; completed automation/spec/release/browser items and accepted desktop-session checks are checked, including the live update-notification click check | Done |
| Fresh LaunchServices handoff evidence | Current rebuilt `AVA_DESKTOP_VERIFY_TIMEOUT=240 scripts/verify-desktop-launch.sh` passed from an empty runtime mirror; a second `AVA_DESKTOP_VERIFY_TIMEOUT=120 scripts/verify-desktop-launch.sh` passed with the existing mirror, covering restart recovery. `scripts/verify-desktop-handoff-ready.sh` now fails fast when the frontmost macOS session is `com.apple.loginwindow`, preventing another false-positive visual handoff. | Done |
| Real UI visual acceptance | System Events can drive the packaged Ava foreground session. Live PR-3 is accepted: `Cmd+W` hid the Console window without quitting, `Control+Shift+A` restored it, and Dock click restored it again. Live menu/log checks are accepted: menu bar exposed Apple / Ava / Edit / View / Window / Help, Window menu included Close Window, Tray menu exposed Show Window / Open Logs / Retry Core / Quit, and both Tray Open Logs and Help -> Open Logs opened `~/Library/Logs/Ava/`. PR-5 legal Finder reveal is accepted: Finder selected `/Users/fanghu/.ava/media/generated/37b70c8f0a75_4.png`; LaunchServices `ava://settings/system/version` routed to the Settings Version page. PR-6 Dock badge is accepted: mock_tester active count 4 showed badge `4`, then admin active count 0 cleared it. PR-6 update notification show and click are accepted: a token-backed `cli/cli` update notification was shown, `AXPress` on the NotificationCenter item clicked it, and Chrome opened `https://github.com/cli/cli/releases/tag/v2.92.0`. | Accepted |
| Linear issue state | AVA-39 through AVA-45 are `Done`. AVA-39 blocker comment `10560a7a-1333-4c61-8f2a-be7deb87b7f7` now records final closeout evidence, and AVA-42 through AVA-45 descriptions no longer contain stale visual blockers. | Done |
| Visual closeout handoff | `docs/ava-39-visual-closeout.md` records the PR-3, PR-5, and PR-6 manual checks as accepted in a foregroundable macOS desktop session. | Accepted |

## Current Commit Evidence

Primary implementation commits are now on the main checkout branch `feat/0.1.0`.

Current PR sequence:

```text
HEAD feat(electron): add tray badge and update checks
14f72ed feat(electron): add deep links and artifact reveal
6082bf6 feat(electron): wire bootstrap and task notifications
84ac0c6 feat(electron): add macos shell menu and dock behavior
dd84efa feat(console-ui): normalize layout padding ownership
4ad25de feat(console-ui): clean up chat header legacy paths
```

The previous temp worktree remains at `/private/tmp/ava-worktree-audit-1778665851`, but the current branch ref has been advanced to the same PR sequence and the final PR-6 verifier hardening has been amended into the latest main checkout commit.

## Current Status

Fresh LaunchServices startup is no longer blocked. The current implementation packages a filtered `ava-runtime` into `Contents/Resources`, mirrors it to `~/Library/Application Support/@ava/electron-shell/runtime-mirror/current`, and starts Python from that App Support runtime root. Startup still gates Console on `/api/gateway/health` strict readiness and `/api/auth/me` returning `200` or `401`. Electron also disables Chromium Safe Storage login-keychain access before single-instance/window initialization so a macOS keychain prompt cannot block the visual handoff. Login-item cold startup now gets a 120s sidecar readiness window and reports `core_startup_timeout` instead of surfacing raw `curl exit 7`.

```text
zsh -lc 'source ~/.nvm/nvm.sh && nvm use >/dev/null && CI=true pnpm electron:build'
  passed; app packaged and codesign verification passed

scripts/verify-desktop-setup-surface.sh
  passed against rebuilt packaged app.asar

node scripts/verify-desktop-setup-dom.mjs
  passed

codesign --verify --deep --strict --verbose=1 electron/dist/Ava-darwin-arm64/Ava.app
  passed

  AVA_DESKTOP_VERIFY_TIMEOUT=240 scripts/verify-desktop-launch.sh
  passed from empty App Support runtime mirror; Console startup interfaces healthy at http://127.0.0.1:6688

  AVA_DESKTOP_VERIFY_TIMEOUT=120 scripts/verify-desktop-launch.sh
  passed after stopping the first app instance without clearing the runtime mirror; Console startup interfaces healthy at http://127.0.0.1:6688

runtime mirror evidence
  packaged Contents/Resources/ava-runtime size: 365M
  App Support runtime mirror size after fresh launch: 366M
  main.log shows packaged runtime resource -> App Support runtime mirror -> python -m ava gateway -> health watcher Console load
```

Desktop visual evidence and remaining manual acceptance:

```text
Computer Use get_app_state("Ava") -> Apple event error -10005: cgWindowNotFound
Computer Use get_app_state("com.electron.ava") -> Apple event error -10005: cgWindowNotFound
CoreGraphics CGWindowList -> Ava window exists with title "AVA Agent Control Plane", alpha=1, bounds={X=320,Y=130,W=1280,H=820}, but onscreen=0
lsappinfo front -> loginwindow; lsappinfo setfront Ava -> ERROR #-54 permErr
2026-05-13 retry: Ava process and sidecar were healthy, /api/gateway/health returned ready=true, /api/auth/me returned 401, but Computer Use still returned cgWindowNotFound and screencapture showed the macOS lock screen instead of a foreground desktop
2026-05-14 retry: no Ava/sidecar process was left running; screencapture still showed the macOS lock screen, and lsappinfo front still reported ASN:0x0-0x2002 instead of a normal foreground app
2026-05-14 low-level launch probe: packaged Ava reached /api/gateway/health ready=true for 63s, but System Events kept reporting frontmost=false, visible=true, windows=0 while lsappinfo front stayed ASN:0x0-0x2002
2026-05-14 handoff preflight hardening: scripts/verify-desktop-handoff-ready.sh now inspects lsappinfo info "$(lsappinfo front)" and blocks com.apple.loginwindow before visual evidence generation; desktop contract pytest and live preflight failure verified this session blocker
2026-05-14 Safe Storage prompt guard: user-observed @ava/electron-shell Safe Storage keychain prompt is now blocked by Darwin-only app.commandLine.appendSwitch('use-mock-keychain') before app.requestSingleInstanceLock(); targeted desktop contract pytest covers the ordering
2026-05-14 rebuilt package after Safe Storage guard: CI=true pnpm electron:build passed, packaged setup verifier passed against app.asar, codesign verify passed, and AVA_DESKTOP_VERIFY_TIMEOUT=120 scripts/verify-desktop-launch.sh passed with Console startup interfaces healthy at http://127.0.0.1:6688
2026-05-14 login-item startup guard: user-observed startup error showed 6688 was not reachable inside the prior 45s window; same-env sidecar repro later reached health successfully, so Electron now waits 120s and emits core_startup_timeout if readiness still fails
2026-05-14 rebuilt package after login-item startup guard: CI=true pnpm electron:build passed, packaged setup verifier passed against app.asar, codesign verify passed, and AVA_DESKTOP_VERIFY_TIMEOUT=150 scripts/verify-desktop-launch.sh passed with Console startup interfaces healthy at http://127.0.0.1:6688
2026-05-14 tray icon size guard: user screenshot showed abnormal menu-bar icon width; Electron now resizes the 192x192 template asset to 18x18 before new Tray(...). node --check, targeted desktop contract pytest, packaged setup verifier, codesign, and AVA_DESKTOP_VERIFY_TIMEOUT=150 scripts/verify-desktop-launch.sh passed after rebuild.
2026-05-14 shortcut restore guard: live visual probe found closing the Console window then invoking the global shortcut could create a new window, start setup.html, then abort it with loadURL(coreEndpoint), showing ERR_ABORTED. The shortcut is now Control+Shift+A, and Console-loaded restore creates the window without setup.html so restore cannot surface the false setup failure.
2026-05-14 shortcut restore verification: after rebuild, AVA_DESKTOP_VERIFY_TIMEOUT=150 scripts/verify-desktop-launch.sh passed, System Events closed the Console window (before=1, after_close=0), sent control+shift+a from another frontmost app, and observed front=Electron/Ava with one AVA Agent Control Plane window; main.log recorded console reloaded and no setup failure dialog appeared.
2026-05-14 Window close role verification: after rebuilding the package, System Events observed initial=1 AVA Agent Control Plane window, after Cmd+W window count=0, after Control+Shift+A window count=1, before Dock click window count=0, and after Dock click window count=1 with AVA Agent Control Plane restored.
2026-05-14 Tray/Menu/Open Logs verification: System Events observed menu bar labels Apple/Ava/Edit/View/Window/Help, Window menu labels Close Window/Close All/Minimize/Zoom/Bring All to Front, Tray labels Show Window/Open Logs/Retry Core/Quit, Tray Open Logs path=/Users/fanghu/Library/Logs/Ava/, and Help Open Logs path=/Users/fanghu/Library/Logs/Ava/.
2026-05-14 Artifact Reveal verification: packaged Ava was launched with CDP on http://127.0.0.1:9225; Playwright logged in as admin, opened /?view=tasks&task_view=artifacts, selected media record 37b70c8f0a75, clicked Reveal in Finder, and AppleScript confirmed Finder front path /Users/fanghu/.ava/media/generated/ with selection /Users/fanghu/.ava/media/generated/37b70c8f0a75_4.png.
2026-05-14 Dock badge verification: Playwright switched the packaged app from admin to mock_tester; /api/bg-tasks?include_finished=true returned 4 active tasks (mock-task-queue-1:queued, mock-task-img-run-1:running, mock-task-run-2:running, mock-task-run-1:running), and screenshot evidence showed Dock badge 4. Switching back to admin returned 0 active tasks and screenshot evidence showed the Dock badge cleared.
2026-05-14 Update notification blocker: AVA_UPDATE_REPO=cli/cli and direct curl probes to GitHub Releases returned 403 API rate limit for the current public IP. A direct window.avaDesktop.showNotification(...) probe returned {ok:true} but produced no visible notification banner in the current macOS notification surface. Live update notification click remains open.
2026-05-14 LaunchServices deep-link verification: packaged Ava was launched with CDP on http://127.0.0.1:9225, logged in as admin, then `open 'ava://settings/system/version'` was invoked through macOS LaunchServices. The renderer URL changed to http://127.0.0.1:6688/settings/system/version, and the page body showed the Settings Version view.
2026-05-14 Update notification hardening and probe: initial update check delay changed from 60s to 5s; update checker supports GITHUB_TOKEN/GH_TOKEN Authorization headers; main.log now records notification shown/no-update/unsupported outcomes. Direct GITHUB_TOKEN="$(gh auth token)" update check against cli/cli returned available=true, version=v2.92.0, url=https://github.com/cli/cli/releases/tag/v2.92.0. LaunchServices-started packaged Ava with the same token logged update notification shown for v2.92.0 at 2026-05-14T04:19:54Z, about 6s after Console load. Screenshot and NotificationCenter inspection still found no visible notification banner or clickable NotificationCenter item.
2026-05-14 Update notification click verification: packaged Ava was relaunched with `GITHUB_TOKEN`, `AVA_UPDATE_REPO=cli/cli`, and `AVA_DESKTOP_REMOTE_DEBUGGING_PORT=9225`. After the new `update notification shown for v2.92.0` log entry, `perform action "AXPress"` on `group 1 of scroll area 1 of group 1 of group 1 of window "Notification Center"` succeeded, and Chrome's active tab changed to `https://github.com/cli/cli/releases/tag/v2.92.0`. Screenshots: `/tmp/ava-update-notification-click-attempt3-before.png` and `/tmp/ava-update-notification-click-attempt3-after.png`.
lsof confirms Ava runs from this bundle's Contents/MacOS/Ava
bundle executable/codesign checks still pass
```

Linear checklist state is closed:

```text
AVA-39 status: Done
AVA-40 status: Done
AVA-41 status: Done
AVA-42 status: Done
AVA-43 status: Done
AVA-44 status: Done
AVA-45 status: Done
Issue descriptions now record completed automation-backed checklist items and live visual checks, including update notification click.
AVA-39 blocker comment updated: 10560a7a-1333-4c61-8f2a-be7deb87b7f7
```

Manual closeout document:

```text
docs/ava-39-visual-closeout.md
```

Additional Web Console walkthrough evidence:

```text
Playwright against http://127.0.0.1:6688 and dev server http://127.0.0.1:5173:
  [PASS] chat desktop: Context Lens opens, one HudBar token widget, no document overflow
  [PASS] chat mobile: Context Lens opens, one HudBar token widget, no document overflow
  [PASS] dev redirect /agents: navigates to /settings/agents-config and emits 0.3.0 deprecation warning
  [PASS] settings desktop: 20 routes, no outer document scroll/overflow
  [PASS] settings mobile: 20 routes, no outer document scroll/overflow

pnpm -C console-ui lint:
  failed on unrelated existing repo baseline; not marked as passed
```

Additional PR-6 mocked runtime evidence:

```text
UV_CACHE_DIR=/private/tmp/ava-uv-cache uv run pytest tests/desktop/test_electron_shell_contract.py::test_desktop_integrations_runtime_contract_with_mocked_electron -q
  1 passed

UV_CACHE_DIR=/private/tmp/ava-uv-cache uv run pytest tests/desktop/test_electron_shell_contract.py -q
  35 passed

This test imports a transformed temporary copy of electron/main.mjs with fake Electron and fake update-check modules, then verifies:
- `ava:showNotification` click routes to `ava:openTaskFloater` with the task id
- `ava:revealArtifact` resolves a legal artifact under `AVA_HOME/media/generated` to `shell.showItemInFolder`; invalid path-like ids fail and do not change the revealed path
- Tray is idempotently installed with an 18x18 template image, tooltip, click handler, and Show Window / Open Logs / Retry Core / Quit menu
- Control+Shift+A global shortcut is registered with a callable callback
- setDockBadgeCount rejects invalid counts and sets Dock badge to "2" then clears it with 0 on macOS
- available update creates a notification, and clicking it opens the GitHub release URL
- equal/not-newer update does not create another notification
```

Additional foreground activation hardening:

```text
Electron Main now uses ensureForegroundActivation() + presentMainWindow() for startup, setup-loaded, console-loaded, second-instance, and show-window flows.
The setup-surface verifier checks these strings in source and packaged app.asar: app.setActivationPolicy('regular'), app.dock?.show?.(), setSkipTaskbar(false), moveTop(), app.focus({ steal: true }), show:false, focusable:true, and await showMainWindow().

zsh -lc 'source ~/.nvm/nvm.sh && nvm use >/dev/null && CI=true pnpm electron:build'
  passed; app packaged and codesign verification passed
scripts/verify-desktop-setup-surface.sh
  passed against rebuilt packaged app.asar
node scripts/verify-desktop-setup-dom.mjs
  passed
codesign --verify --deep --strict --verbose=1 electron/dist/Ava-darwin-arm64/Ava.app
  passed
```

Additional login/port-conflict hardening:

```text
Observed failure:
  packaged Ava loaded Console, then ava-core exited; login POST surfaced as browser-level Failed to fetch.
  core.log showed OSError EADDRINUSE for gateway 18790 and WebSocket 8765.

Fix:
  Electron now picks distinct Console / gateway / WebSocket runtime ports.
  buildCoreEnv injects AVA_DESKTOP_CONSOLE_PORT / AVA_DESKTOP_GATEWAY_PORT / AVA_DESKTOP_WEBSOCKET_PORT.
  buildCoreEnv also injects VIRTUAL_ENV and PYTHONPATH including runtime-mirror site-packages; Electron starts `python -m ava gateway` from the App Support runtime mirror and uses the resolved Python binary only as the interpreter.
  Electron startup checks /api/gateway/health and /api/auth/me before loading Console; auth must be 200 or login-required 401.
  Startup failure cleanup now stops and forgets the current sidecar before Retry / Pick nanobot / Quit actions; the SIGKILL fallback checks actual process exit instead of child.killed.
  Python config overlay applies gateway/WebSocket overrides only during desktop config load and does not persist them to user config.

Verification:
  python3 -m py_compile ava/runtime/config_overlay.py ava/patches/bb_config_overlay_patch.py
    passed
  UV_CACHE_DIR=/private/tmp/ava-uv-cache uv run pytest tests/patches/test_config_overlay_patch.py \
    tests/desktop/test_electron_shell_contract.py::test_launch_env_module_merges_shell_path_and_builds_desktop_env \
    tests/desktop/test_electron_shell_contract.py::test_desktop_env_overrides_python_configured_console_port \
    tests/desktop/test_electron_shell_contract.py::test_desktop_port_and_nanobot_error_contracts_are_present \
    tests/desktop/test_electron_shell_contract.py::test_desktop_setup_surface_verifier_script_contract -q
    7 passed
  Live sidecar proof with existing 18790/8765 listeners still present:
    /api/gateway/health returned ready=true on the chosen Console port
    /api/auth/me returned JSON 401 Authentication required instead of connection failure
```
