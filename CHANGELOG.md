# Changelog

## 0.2.0 - 2026-05-14

- PR-1 / AVA-40: Cleaned up ChatPage static legacy paths, removed the old context inspector file, normalized Context Lens naming, removed duplicate token UI, and marked legacy redirects for removal after 0.3.0.
- PR-2 / AVA-41: Moved layout padding ownership to pages, removed ChatPage and SettingsPage shell offset hacks, and collapsed Settings navigation into a recursive tree.
- PR-3 / AVA-42: Added macOS-style desktop lifecycle behavior and standard App / Edit / View / Window / Help menus with Open Logs and Retry Core.
- PR-4 / AVA-43: Wired Electron bootstrap state replay, desktop bootstrap banner, BG task terminal notifications, notification-to-TaskFloater routing, and desktop Retry Core entry.
- PR-5 / AVA-44: Added `ava://` / `ava-dev://` deep links, Info.plist URL scheme injection, renderer deep-link handling, and allowlisted artifact reveal instead of renderer `openPath`.
- PR-6 / AVA-45: Added Tray menu, global shortcut restore, Dock badge IPC, BG task active-count badge updates, and GitHub Releases update notification checks.
