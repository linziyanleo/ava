# P2 Mobile Remote Task Checklist Audit

Date: 2026-05-11

Scope: `.specanchor/tasks/_cross-module/2026-05-09_p2-mobile-and-remote-access.spec.md` section 4.3.

Status terms:
- Done: implemented and covered by current automated verification.
- Deviation: implemented with a deliberate shape/name/schema difference from the original checklist.
- Open: not verifiable in this environment.

## Checklist Mapping

| Item | Status | Evidence |
|---|---|---|
| 1 | Deviation | `ava/storage/database.py` sets `SCHEMA_VERSION = 2` and creates `schema_migrations`, `lan_devices`, `lan_device_events`, `lan_pair_throttle`; throttle table uses generalized `(scope, key)` instead of literal `(ip, pin_hash)`. |
| 2 | Done | `ava/storage/lan_devices_store.py`; `tests/console/test_lan_devices_store.py`. |
| 3 | Done | `LanAccessService` owns `LanDevicesStore` and preserves PIN/state JSON. |
| 4 | Done | `pair_device()` writes `expires_at` and default `capabilities=["read"]`; covered in `tests/console/test_lan_access_routes.py`. |
| 5 | Done | `LanAccessService.invalidate_pin()`. |
| 6 | Deviation | `bump_capabilities()` delegates to `update_device_capabilities()` and logs `capability_update`; `actor` is not persisted. |
| 7 | Done | `renew_device()` logs renewal and is covered by `tests/console/test_lan_access_routes.py`. |
| 8 | Done | `cleanup_expired_devices()` is called on service bootstrap and LAN enable. |
| 9 | Deviation | `qr_payload()` returns direct `/lan/pair?pin=...` URL for QR consumption instead of base64 wrapping; documented in plan-execution diff. |
| 10 | Done | `get_lan_urls()` and `allowed_lan_origins()` feed CORS/origin logic. |
| 11 | Done | `ava/console/services/lan_mdns_service.py`; `tests/console/test_lan_mdns_service.py`. |
| 12 | Done | `ava/console/services/tunnel_service.py`; `tests/console/test_tunnel_service.py`. |
| 13 | Deviation | `PairThrottleService` persists scope/key counters and exposes lockout cleanup; route layer logs pair failure/device events and invalidates PIN. |
| 14 | Deviation | `ConsoleNetworkService` is callback-driven (`set_reload_callback`, `reload`) instead of full `build_config()/attach()/supervisor_fallback()` API; same-process reload behavior is covered. |
| 15 | Done | `auth.require_console_role_or_device_capability()`; `tests/console/test_capability_dependency.py`. |
| 16 | Deviation | Origin enforcement is implemented in `ava/console/middleware.py` and reusable helper, rather than only `auth.py`. |
| 17 | Done | Device token expiry validation and effective-scheme cookie handling in `auth.py` / `lan_access_service.py`; covered by route/origin tests. |
| 18 | Done | Custom dynamic CORS middleware in `ava/console/middleware.py`; `tests/console/test_origin_allowlist.py`. |
| 19 | Done | `get_client_ip()` trusts `CF-Connecting-IP` only for loopback tunnel traffic; `tests/console/test_get_client_ip.py`. |
| 20 | Done | Read/operate routes use `require_console_role_or_device_capability()` across agent, bg task, workflow, chat, direct task, and media routes. |
| 20a | Deviation | Admin-only process lifecycle is implemented in `agent_routes.py`; tests live in `test_agent_routes.py` and `test_capability_dependency.py`, not a separate `test_agent_process_admin_only.py`. |
| 21 | Deviation | Mutating API origin enforcement is applied by custom middleware for `/api/*` mutating methods, not by explicitly attaching the dependency to every route. |
| 22 | Done | WebSocket origin/capability checks are centralized through `auth.get_ws_user()` and route guards; workflow/chat WebSocket routes use that entry point. |
| 23 | Done | LAN route endpoints for capability, renew, discovery, and tunnel actions exist in `lan_access_routes.py`. |
| 24 | Done | `/pin` and `/pair` use `PairThrottleService`; lockout and throttle paths are covered. |
| 25 | Done | `/status` response includes `qr_payload`, `tunnel`, `mdns`, and `https`. |
| 26 | Deviation | `console_patch.py` registers `ConsoleNetworkService` reload callback instead of passing service directly through `_build_server()` signature. |
| 27 | Done | LAN config, tunnel, and HTTPS route actions call `svc.network.reload()`. |
| 28 | Done | `pyproject.toml` and `uv.lock` include `zeroconf`. |
| 29 | Done | `scripts/fetch-cloudflared.sh` supports platform selection, SHA256 verification, and `CLOUDFLARED_OFFLINE_PATH`. |
| 30 | Deviation | `electron/scripts/build.mjs` invokes `scripts/fetch-cloudflared.sh` for real packaging; dry-run verifies packaging contract but intentionally skips download. |
| 31 | Done | `docs/third-party-licenses.md` lists cloudflared, qrcode.react, zeroconf, and react-window. |
| 32 | Done | `console-ui/package.json` / lock include `qrcode.react`. |
| 33 | Done | `console-ui/src/api/lan-access.ts` includes capability, renewal, discovery, tunnel, HTTPS, and CA helpers. |
| 34 | Done | `console-ui/src/App.tsx` exposes public `/lan/pair` outside `RequireAuth`. |
| 35 | Done | `console-ui/src/pages/MobilePairPage.tsx`; `console-ui/e2e/p2-mobile-pair.mjs`. |
| 36 | Done | `LanAccessPage.tsx` renders QR and countdown from `/lan/pair` payload; `p2-lan-access.mjs`. |
| 37 | Done | `LanAccessPage.tsx` has Tunnel card and control path. |
| 38 | Done | `LanAccessPage.tsx` devices table includes expiry, renewal, and capability controls. |
| 39 | Deviation | Service behavior tests are in `tests/console/test_lan_access_routes.py`, not a separate `test_lan_access_service.py`. |
| 40 | Done | `tests/console/test_lan_mdns_service.py`. |
| 41 | Done | `tests/console/test_tunnel_service.py`. |
| 42 | Done | `tests/console/test_lan_devices_store.py`. |
| 43 | Done | `tests/console/test_pair_throttle_service.py`. |
| 44 | Done | `tests/console/test_capability_dependency.py` covers OR helper operate/read branches, console viewer/read_only read access, admin-only process lifecycle rejection for editor/device tokens, and absence of a standalone `require_capability` gate. |
| 45 | Done | `tests/console/test_origin_allowlist.py` covers explicit dependency/audit, dynamic exact-origin allowlist changes, LAN/HTTPS/tunnel exact allowlist composition, WebSocket 1008 rejection, effective-scheme Secure cookies, and no wildcard or same-LAN wrong-port reflection. |
| 46 | Done | `tests/console/test_get_client_ip.py`. |
| 47 | Done | `tests/console/test_console_dynamic_bind.py`. |
| 48 | Done | `console-ui/e2e/p2-lan-access.mjs` covers QR modal, Tunnel card/control, capability edit request, and device renewal request; syntax checked by verifier, browser execution blocked by environment. |
| 49 | Done | `console-ui/e2e/p2-mobile-pair.mjs` covers `/lan/pair?pin=...`, PIN prefill, successful pairing redirect, and throttle failure message; syntax checked by verifier, browser execution blocked by environment. |
| 50 | Done | `tests/guardrails/test_ava8_decoupling_boundary.py` covers new service boundary. |
| 51 | Done | `pyproject.toml` and `uv.lock` include direct `cryptography>=44,<46`. |
| 52 | Done | `ava/console/services/lan_https_service.py`; `tests/console/test_lan_https_service.py`. |
| 53 | Done | HTTPS enable/disable calls `svc.network.reload()` through LAN routes. |
| 54 | Done | `GET /cert/ca.crt` and `POST /https/{action}` exist in `lan_access_routes.py`. |
| 55 | Done | `console-ui/public/manifest.webmanifest`, apple touch icons, and 192/512 icons exist. |
| 56 | Done | `console-ui/index.html` includes manifest, theme-color, and Apple mobile meta. |
| 57 | Done | `LanAccessPage.tsx` includes HTTPS card, CA download, and trust doc links. |
| 58 | Done | `tests/console/test_lan_https_service.py` plus `tests/console/test_console_dynamic_bind.py`. |
| 59 | Done | `useResponsiveMode.ts` exposes `isTablet` and `isLandscape`. |
| 60 | Done | `AgentDashboardPage.tsx` contains responsive task modal constraints. |
| 61 | Done | `HudBar.tsx` implements mobile scroll-snap and drawer behavior. |
| 62 | Done | `ChainBubble.tsx` imports `react-window` and renders `<List>` for long chains. |
| 63 | Done | `console-ui/package.json` / lock include `react-window`. |
| 64 | Done | `console-ui/e2e/p2-responsive.mjs` covers viewport mode, Chat HUD Skills, TaskFloater, and AgentDashboard task modal; `p2-chain-bubble.mjs` verifies the ChainBubble `>10` virtualized `<List>` branch and the `<=10` map fallback branch; static checks pass. |
| 65 | Done | `docs/control-plane-manual-acceptance.md` includes P2 mobile/remote access checklist and a structured evidence template for item 66 verification. |
| 66 | Open | Physical iPhone/Pixel/iPad flows were not run; browser automation is blocked by current macOS sandbox permissions and missing in-app Browser / Codex Chrome Extension Node REPL tooling. |

## Verification Used

- Main checkout: `./scripts/verify-p2-mobile-remote.sh` and `RUN_PREVIEW_SMOKE=1 ./scripts/verify-p2-mobile-remote.sh` passed.
- Linked worktree: `AVA_NANOBOT_ROOT=/Users/fanghu/Documents/Test/nanobot ./scripts/verify-p2-mobile-remote.sh` and `RUN_PREVIEW_SMOKE=1 AVA_NANOBOT_ROOT=/Users/fanghu/Documents/Test/nanobot ./scripts/verify-p2-mobile-remote.sh` passed in `.worktrees/p2-mobile-remote-linked`.
- Linked worktree preview smoke: `/lan/pair?pin=123456` returned HTTP 200 from Vite preview on port 4174 under Node 20.19.
- `git diff --check` passed in the main checkout, `.worktrees/p2-mobile-remote-linked`, and `.worktrees/p2-mobile-remote-impl`.

## Remaining Open Acceptance

The implementation is present and verified in a linked worktree. The remaining open item is runtime browser/real-device acceptance for item 66. Current blocked paths:

- `RUN_BROWSER_E2E=1 ./scripts/verify-p2-mobile-remote.sh` is the supported verifier command; browser logs are mirrored to `P2_BROWSER_LOG_DIR` or `${TMPDIR:-/tmp}/ava-p2-browser-e2e`.
- In this sandbox, `RUN_BROWSER_E2E=1 BASE_URL=http://127.0.0.1:4173 PW_BROWSER=chromium P2_BROWSER_LOG_DIR=/private/tmp/ava-p2-browser-e2e-fail ./scripts/verify-p2-mobile-remote.sh` failed at `p2-lan-access` and wrote `/private/tmp/ava-p2-browser-e2e-fail/p2-lan-access.log`.
- Bundled Chromium: Mach/crashpad permission failure.
- Bundled Chromium with explicit `--disable-crashpad` / `--disable-crash-reporter` launch args: still fails at `MachPortRendezvousServer bootstrap_check_in`.
- System Chrome: launch closes or exits with crashpad `bootstrap_check_in` permission failure.
- WebKit: `Abort trap: 6`.
- Firefox: `SIGABRT`.
- Safari WebDriver: `safaridriver` is installed, but `safaridriver -p 4444` exits immediately without listening on port 4444 and writes no log.
- Chrome DevTools remote debugging: common ports `9222`, `9223`, `9224`, and `9333` do not respond; process-list inspection is blocked by sandbox permissions.
- Playwright CLI: cache paths can be redirected to `/private/tmp`, but browser launch still fails on Chrome crashpad permissions.
- Codex in-app Browser: required Node REPL `js` tool is not exposed in this session.
- Codex Chrome Extension plugin: required Node REPL `js` / browser-client tool is not exposed after tool discovery searches for `node_repl js`, `mcp__node_repl__js`, `js`, and browser tab/openTabs capabilities.
- Chrome Computer Use: MCP approval denied.
- Safari Computer Use: MCP approval denied.

## Closure Procedure For Item 66

Run this on a verifier machine that can launch a real browser:

```bash
RUN_BROWSER_E2E=1 AVA_NANOBOT_ROOT=/Users/fanghu/Documents/Test/nanobot \
  ./scripts/verify-p2-mobile-remote.sh
```

Then complete the AVA-28 evidence template in
`docs/control-plane-manual-acceptance.md` on iPhone, Android, and iPad. Item 66
can be marked done only after both the browser command and the physical-device
flows pass, or after any remaining failures are recorded as explicit follow-up
bugs outside this P2 implementation task.
