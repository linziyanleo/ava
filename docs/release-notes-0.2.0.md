# Ava 0.2.0 Release Notes

## Desktop Shell

- Electron now behaves more like a native macOS app: closing the last window keeps the app alive, dock activation restores the window, and the app exposes standard menu groups.
- Desktop bootstrap state is visible in the Console through a banner with retry support.
- BG task terminal states can trigger desktop notifications, and notification clicks reopen the Console task floater.
- `ava://` packaged deep links and `ava-dev://` dev links route to sessions, tasks, traces, chains, and settings.
- Artifact reveal now uses a dedicated `revealArtifact(artifactId)` bridge with Main-process allowlist checks.
- Tray menu, global shortcut restore, Dock badge updates, and GitHub Releases update notifications are wired.

## Console UI

- Chat header legacy context-inspector naming and duplicate token-entry UI were removed in favor of Context Lens and the existing HUD token entry.
- Layout padding is page-owned; Chat and Settings no longer depend on negative margin shell compensation.
- Settings navigation is backed by a single recursive tree instead of parallel link arrays.

## Redirect Deprecation

The legacy Console redirect matrix remains in 0.2.0 for compatibility, but each legacy redirect now carries `deprecatedAfter: "0.3.0"` and emits a development warning. The planned 0.3.0 cleanup is to remove the legacy top-level routes such as `/agents`, `/bg-tasks`, and `/tokens` once callers have moved to the canonical `/` and `/settings/*` entry points.

## Known Verification Gaps

- Real macOS tray/menu clicks, cross-app global shortcut, Dock badge visuals, LaunchServices deep-link routing, legal artifact Finder reveal, and live update-notification clicks still require non-sandbox manual acceptance.
