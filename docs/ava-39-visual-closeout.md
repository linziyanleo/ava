# AVA-39 Visual Closeout

Date: 2026-05-13
Last updated: 2026-05-14

Use this checklist from a normal foregroundable macOS desktop session to close the
remaining AVA-39 visual acceptance gap. Do not run it from a locked screen,
loginwindow-fronted automation session, or a session where apps cannot be made
frontmost.

## Preconditions

```bash
cd /Users/fanghu/Documents/Test/ava
git rev-parse --short HEAD
scripts/verify-desktop-handoff-ready.sh
scripts/verify-desktop-launch.sh
```

Expected PR-6 commit subject at the time this checklist was written:

```text
feat(electron): add tray badge and update checks
```

If `scripts/verify-desktop-launch.sh` passes but the window is not visible, do
not mark visual acceptance complete. The handoff preflight now blocks
`loginwindow`-fronted sessions; if you bypass it, first confirm the desktop
session can make apps frontmost. A previous Codex session was blocked because
`lsappinfo front` reported `loginwindow` and `lsappinfo setfront Ava` returned
`permErr`.

Ava should not show a macOS `@ava/electron-shell Safe Storage` keychain prompt
on launch. If that prompt appears, the app bundle under test does not include
the 2026-05-14 Safe Storage prompt guard and must be rebuilt before visual
acceptance.

Current blocker evidence: on 2026-05-14, `screencapture` still showed the macOS
lock screen and `lsappinfo front` still returned `ASN:0x0-0x2002`; visual
acceptance remains blocked until the Mac is unlocked into a normal desktop
session.

Additional 2026-05-14 probe: packaged Ava reached `/api/gateway/health`
`ready=true` for 63 seconds, but System Events still reported
`frontmost=false`, `visible=true`, and `windows=0` while `lsappinfo front`
remained `ASN:0x0-0x2002`.

## PR-3: Dock And Menu

Record one clear observation for each field:

```text
Cmd+W keeps app alive and Dock click restores: Confirmed 2026-05-14 by System Events on rebuilt package; initial=1, after Cmd+W=0, after Dock click=1 with AVA Agent Control Plane restored.
Menu bar has App/Edit/View/Window/Help: Confirmed 2026-05-14; menu bar labels Apple/Ava/Edit/View/Window/Help and Window menu includes Close Window.
Help -> Open Logs opens ~/Library/Logs/Ava: Confirmed 2026-05-14; Finder target path was /Users/fanghu/Library/Logs/Ava/.
```

Steps:

1. Open `electron/dist/Ava-darwin-arm64/Ava.app` from Finder.
2. Confirm the Console or setup window becomes visible without Terminal.
3. Press `Cmd+W`.
4. Confirm the app remains running and the Dock icon remains present.
5. Click the Dock icon and confirm the Ava window returns.
6. Confirm the macOS menu bar contains App / Edit / View / Window / Help.
7. Use `Help -> Open Logs` and confirm Finder opens `~/Library/Logs/Ava`.

## PR-5: Reveal Artifact

Record:

```text
Legal artifact Reveal in Finder locates the file: Confirmed 2026-05-14 through packaged Ava UI; TaskFloater artifacts opened record 37b70c8f0a75, Reveal in Finder selected /Users/fanghu/.ava/media/generated/37b70c8f0a75_4.png in Finder.
LaunchServices `ava://` routes into packaged app: Confirmed 2026-05-14; `open 'ava://settings/system/version'` changed the packaged app renderer URL to http://127.0.0.1:6688/settings/system/version and showed the Settings Version view.
```

Steps:

1. Open Console in the packaged app.
2. Navigate to a view that shows a real generated, screenshot, or chat-upload artifact.
3. Click `Reveal in Finder`.
4. Confirm Finder opens with the expected artifact selected.
5. Do not use arbitrary filesystem paths; this PR only accepts artifact ids.
6. For deep-link routing, use `open 'ava://settings/system/version'` and confirm the packaged app navigates to Settings Version.

## PR-6: Tray, Shortcut, Badge, Update Notification

Record:

```text
Tray icon appears at normal menu-bar size and menu actions work: Confirmed 2026-05-14 after 18x18 tray resize rebuild; status menu labels Show Window/Open Logs/Retry Core/Quit and Open Logs opened /Users/fanghu/Library/Logs/Ava/.
Ctrl+Shift+A restores Ava from another app: Confirmed 2026-05-14; after Cmd+W closed the Console window, System Events sent control+shift+a from Finder and Ava restored AVA Agent Control Plane with one window.
Dock badge reflects active BG-Task count and clears: Confirmed 2026-05-14; admin /api/bg-tasks returned 0 active and Dock had no badge, mock_tester returned 4 active tasks and Dock showed red badge 4, switching back to admin returned 0 active and cleared the badge.
Update notification appears when a newer release is detected: Confirmed 2026-05-14 by main.log; LaunchServices-started packaged Ava with `GITHUB_TOKEN` and `AVA_UPDATE_REPO=cli/cli` logged `update notification shown for v2.92.0: https://github.com/cli/cli/releases/tag/v2.92.0` about 6s after Console load.
Update notification click opens release page: Confirmed 2026-05-14; after a token-backed `cli/cli` update notification appeared, System Events performed `AXPress` on the NotificationCenter item and Chrome opened `https://github.com/cli/cli/releases/tag/v2.92.0`.
```

Steps:

1. Confirm the Ava tray/menu-bar icon appears at normal menu-bar icon size and does not consume abnormal horizontal space.
2. Open its menu and verify Show Window / Open Logs / Retry Core / Quit.
3. Switch to another app, then press `Ctrl+Shift+A`; confirm Ava becomes visible.
4. For update notification, use a run where the configured GitHub release tag is newer than `electron/package.json::version`; confirm the notification appears and click opens the release page.

Update-notification click is now accepted. Earlier unauthenticated GitHub
Releases requests returned `403` API rate limit for the current public IP, so
the accepted live check used `GITHUB_TOKEN` plus `AVA_UPDATE_REPO=cli/cli`.
The notification click was confirmed by Chrome's active tab changing to
`https://github.com/cli/cli/releases/tag/v2.92.0`.

## Closeout

After the fields above are filled:

1. Update `.specanchor/tasks/_cross-module/2026-05-13_legacy-cleanup-and-desktop-shell-uplift.spec.md` by checking the corresponding PR-3, PR-5, and PR-6 visual items.
2. Update `docs/ava-39-completion-audit.md` from blocked to accepted, preserving the command evidence.
3. Only after visual acceptance is recorded, update Linear AVA-39 through AVA-45 from `Backlog` to the correct completed state or add a status comment with the remaining exception.
4. Re-run:

```bash
git diff --check
```

## Linear Comment Draft

Use this after visual acceptance is complete. If any visual item fails, replace
the pass line with the exact failed observation and keep the affected issue open.

```markdown
AVA-39 / PR-1~PR-6 closeout update:

- Commit sequence on `feat/0.1.0`: AVA-40 -> AVA-41 -> AVA-42 -> AVA-43 -> AVA-44 -> AVA-45.
- Latest audited PR-6 commit subject: `feat(electron): add tray badge and update checks`.
- Automated verification passed: desktop contract pytest, Electron build, packaged setup verifier, setup DOM verifier, codesign, LaunchServices health checks, and `git diff --check`.
- Manual visual acceptance passed in a normal macOS desktop session: Dock/menu, legal artifact Reveal in Finder, Tray/menu, global shortcut, Dock badge, and update notification click.
- D6 / desktop auth-token contract remains out of scope and is tracked separately by AVA-46.

Docs:
- `docs/ava-39-completion-audit.md`
- `docs/ava-39-visual-closeout.md`
- `.specanchor/tasks/_cross-module/2026-05-13_legacy-cleanup-and-desktop-shell-uplift.spec.md`
```
