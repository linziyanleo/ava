# Deferred P2/P3 Manual Acceptance

This file records future manual checks for Linear issues that are currently
`Backlog` + `deferred`. These checks are not part of current P1b acceptance
unless the corresponding Linear issue is moved back into the active milestone.

The current prompt-to-artifact audit is in
`docs/control-plane-completion-audit.md`.

## Current Automated Baseline

Run these for the active P1b scope:

```bash
uv run --extra dev pytest tests/console_ui/test_linear_acceptance_checklists.py -q
cd console-ui && npm run build
git diff --check
```

Expected current result: P1b acceptance passes, frontend build passes, and
`git diff --check` is clean.

## AVA-28 LAN Access P2 Manual Pass

Deferred until AVA-28 leaves Backlog.

Checklist:

- HTTP LAN URL redirects to HTTPS when HTTPS is enforced.
- Self-signed certificate status and install guidance are visible in Settings.
- QR pairing URL opens from a phone camera scan in the mainland China Wi-Fi environment.
- PIN exchange creates a `read_only` device token.
- Revoked device token loses access immediately.
- iOS Safari and Android Chrome can add the PWA to the home screen.
- PWA reload does not serve cached `/api/*` responses.
- `ava.local` resolves through mDNS on the router; if it does not, the UI shows the IP fallback.
- `lan.device_access` audit entries include device id, endpoint, method, status code, and IP.

## AVA-30 Mobile Native Manual Pass

Deferred until AVA-30 leaves Backlog.

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
