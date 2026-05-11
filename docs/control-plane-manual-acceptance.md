# Deferred P2/P3 Manual Acceptance

This file records future manual checks for Linear issues that are currently
`Backlog` + `deferred`. These checks are not part of current P1b acceptance
unless the corresponding Linear issue is moved back into the active milestone.

The current prompt-to-artifact audit is in
`docs/control-plane-completion-audit.md`.

The P2 LAN/mobile/remote-access audit is in
`docs/p2-mobile-remote-completion-audit.md`. The remaining open P2 acceptance
item is tracked in `docs/p2-mobile-remote-task-checklist-audit.md`.

## Current Automated Baseline

Run these for the active P1b scope:

```bash
uv run --extra dev pytest tests/console_ui/test_linear_acceptance_checklists.py -q
cd console-ui && npm run build
git diff --check
```

Expected current result: P1b acceptance passes, frontend build passes, and
`git diff --check` is clean.

For the P2 LAN/mobile static and preview smoke checks, run:

```bash
RUN_PREVIEW_SMOKE=1 ./scripts/verify-p2-mobile-remote.sh
```

For browser automation on a verifier machine that can launch Playwright, run:

```bash
RUN_BROWSER_E2E=1 ./scripts/verify-p2-mobile-remote.sh
```

Browser automation output is mirrored to `${P2_BROWSER_LOG_DIR:-${TMPDIR:-/tmp}/ava-p2-browser-e2e}`.
Set `P2_BROWSER_LOG_DIR=/path/to/logs` when collecting evidence for review.

If bundled Chromium cannot launch on the verifier machine, the browser scripts
also accept `PW_BROWSER=webkit` or `PW_BROWSER=firefox` after installing the
matching Playwright browser.

In the current Codex sandbox, Playwright browsers, Safari WebDriver, Codex
in-app Browser, Codex Chrome Extension, and Chrome Computer Use are all blocked.
Treat `docs/p2-mobile-remote-task-checklist-audit.md` as the current blocked
evidence and run this browser step on a machine that can actually launch or
control a browser.

To close the P2 open item, attach the browser command result and the AVA-28
manual evidence template below to `docs/p2-mobile-remote-task-checklist-audit.md`,
then update item 66 in the Task Spec execute log.

## AVA-28 LAN Access P2 Manual Pass

Evidence template:

```text
Date:
Verifier:
Build/commit:
Console URL:
Devices:
- iPhone model / iOS / browser:
- Android model / version / browser:
- iPad model / iPadOS / browser:
Browser automation:
- Command:
- Browser engine:
- Result:
LAN:
- QR scan result:
- Pairing result:
- mDNS result:
- IP fallback result:
Tunnel:
- public URL:
- Secure cookie observed:
- audit event observed:
HTTPS:
- CA install result:
- HTTPS URL result:
- local http://127.0.0.1 cookie still usable:
Mobile UI:
- ChatPage:
- AgentDashboard:
- TaskOverlay:
- LanAccessPage:
- /lan/pair:
Open issues:
```

Checklist:

- iPhone 13+ scans the LAN QR code and opens `/lan/pair?pin=...`.
- Pixel 4+ scans the LAN QR code and opens `/lan/pair?pin=...`.
- iPad opens the same pairing URL in portrait and landscape.
- PIN exchange creates a `read_only` device token with `capabilities=["read"]` and `expires_at`.
- Capability preset `reviewer` writes `["read","review"]`.
- Capability preset `operator` writes `["read","review","operate"]`.
- Device token with `["read"]` can read dashboard/chat state but cannot send or stop chat.
- Device token with `["read","operate"]` can submit the covered mutating routes.
- `cloudflared` tunnel start shows the exact `https://*.trycloudflare.com` URL and audit event.
- Stopping LAN kills tunnel state and removes the tunnel origin from CORS.
- HTTP LAN URL remains usable when HTTPS is disabled.
- HTTPS toggle generates the CA certificate and keeps local `http://127.0.0.1` cookies usable.
- Tunnel pairing over HTTPS sets a Secure device-token cookie.
- QR pairing URL opens from a phone camera scan in the mainland China Wi-Fi environment.
- Revoked device token loses access immediately.
- iOS Safari and Android Chrome can add the PWA to the home screen.
- PWA reload does not serve cached `/api/*` responses.
- `ava.local` resolves through mDNS on the router; if it does not, the UI shows the IP fallback.
- `lan.device_access` audit entries include device id, endpoint, method, status code, and IP.

## AVA-30 Mobile Native Manual Pass

Checklist:

- Sending a message works on mobile.
- Opening task overlay works and remains full screen.
- Switching session with swipe works.
- Changing the active Agent from the collapsed mobile config bar works.
- Input remains visible when the keyboard is open.
- Safe area is correct on notch/full-screen devices.
- Long-press TaskCard opens the action menu.
- Portrait and landscape layouts do not break.
- No major jank in the key flows above.
- Chat HUD widgets scroll horizontally with snap on mobile.
- Skills widget opens as a bottom drawer on mobile.
- Agent task dialog fits within the viewport and keeps form fields single-column on mobile.
- ChainBubble with more than 10 nodes scrolls smoothly without rendering all rows at once.

## AVA-34 Relay Remote Access Manual Pass

Deferred until AVA-34 leaves Backlog.

Checklist:

- Remote phone can access local AVA Chat through the relay path.
- Device token is required; unauthenticated requests are rejected.
- RBAC applies without introducing a new role.
- Kill switch takes effect immediately.
- IP allowlist rejects a disallowed remote IP.
- Relay network drop degrades gracefully and does not block local LAN access.
- Relay audit entries include user/device identity and target endpoint.

## AVA-35 Formal HTTPS And Push Manual Pass

Deferred until AVA-35 leaves Backlog.

Checklist:

- Let's Encrypt DNS-01 issuance succeeds.
- Renewal dry run or forced renewal succeeds.
- Caddy serves the renewed certificate.
- APNs notification is delivered for a task-chain failure.
- FCM notification is delivered for a long task completion.
- Web Push notification is delivered for an approval-pending event.
- Per-scene disable prevents notification delivery for that scene.
- Push payload does not include user message text, prompt contents, or secret values.
