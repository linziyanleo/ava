# Ava Current Feature Inventory

Date: 2026-05-13

This inventory records the current product surface so later interaction design can reason from concrete features instead of roadmap names.

## Desktop and Startup

- Electron macOS shell launches `ava-core` as a sidecar and loads the Console after `/api/gateway/health`.
- Finder launch path now creates a local setup surface before the sidecar is healthy.
- Desktop launch uses a single immutable launch config for port, endpoint, PATH, repo root, and log paths.
- Console port is probed at launch; desktop mode exports `AVA_DESKTOP_CONSOLE_PORT`, which overrides config port inside `console_patch.py`.
- If the preferred Console port or `~/.ava/console.json` points to a healthy Ava core, the desktop shell attaches to that core instead of launching a second sidecar.
- Single-instance lock focuses the existing window instead of spawning another sidecar.
- Logs are written to `~/Library/Logs/Ava/main.log` and `~/Library/Logs/Ava/core.log`; Help -> Open Logs opens that folder.
- Startup failures show a native dialog and the setup surface with stderr tail.
- `~/Library/Application Support/Ava/desktop.json` stores the selected external nanobot checkout.
- Desktop config and nanobot checkout validation are isolated in `electron/lib/desktop-config.mjs`, so path resolution and corrupt-config behavior can be tested without launching Electron.
- Finder PATH merging, `uv` executable discovery, and sidecar desktop env injection are isolated in `electron/lib/launch-env.mjs`, so launch environment behavior can be tested without launching Electron.
- Setup can select nanobot checkout, run `uv sync --extra dev` when `.venv/bin/python` is missing, cancel bootstrap, and retry core startup.
- Settings -> System -> Desktop exposes nanobot checkout selection, retry, logs, and links to Codex / Claude Code config editors after the Console is healthy.
- Non-sandbox Finder/LaunchServices and visual setup/cancel/logs acceptance is still tracked in `docs/desktop-launch-acceptance.md`; current sandbox checks verify code/package/DOM contracts but cannot prove Finder double-click behavior.

## Core Runtime

- Ava runs as a local-first Agent Control Plane; `ava-core` owns agent registry, tasks, events, artifacts, permissions, and API routes.
- External `nanobot` checkout is required and resolved by explicit path, `AVA_NANOBOT_ROOT`, sibling `../nanobot`, or vendor fallback in adapter discovery.
- `scripts/start-ava.sh` launches `python -m ava` with `PYTHONPATH` containing Ava and nanobot.
- Console startup is injected through `ava/patches/console_patch.py` and writes runtime console metadata.

## Console UI

- Primary IA is Chat and Settings.
- Login, refresh, current-user, and logout flows are backed by `/api/auth/*`; protected pages route unauthenticated users to `/login`.
- Settings contains Agents Config, Statistics, Tools, Users, and System.
- System settings subpages are Desktop, LAN Access, Gateway, Browser, Console, and Version.
- Browser system page shows active page-agent sessions with screencast frames, page URL/status, step count, and agent activity events.
- Agent detail pages expose status, version, path, config links, recent events, recent artifacts, direct task launch, task cancellation, and Nanobot restart.
- Legacy top-level routes redirect into the current Settings or task overlay surfaces.
- `/lan/pair` is the mobile device pairing entry outside the main protected shell.
- Desktop uses TopBar and global TaskFloater; mobile keeps responsive bottom/navigation behavior.
- Chat HUD exposes Token, Skills, Artifacts, and Memory widgets; Token opens statistics, Skills opens the skill picker/drawer, Artifacts opens the TaskFloater artifacts panel, and Memory links to Gateway status.
- Chat supports session create/rename/stop/delete/history, context size, compression history, context preview, message queries, uploads, and conversation listing through `/api/chat/*` and `/api/messages`.

## Agent Control

- Agent Registry reports Nanobot, Claude Code, Codex, and Image Gen installation status, runtime status, versions, capabilities, active tasks, recent events, and artifacts.
- Claude Code, Codex, and Image Gen can be launched as direct background tasks from Agents Config or slash-command/direct-task flows.
- Direct task submission is exposed through `/api/console/direct-tasks`, and agent process start/stop/restart/health/cancel operations are exposed through `/api/agents/*`.
- Nanobot is the default long-running agent; CLI/provider agents are detected at startup but only invoked per task.
- Claude Code and Codex config files are editable through Settings -> Agents Config.

## Tasks, Workflows, and Artifacts

- `BackgroundTaskStore` is the current task execution source for direct coding/image tasks.
- Task snapshots include status, phase, timeline, prompt preview, result/error preview, project path, trace id, chain id, CLI run/session ids, workspace metadata, and origin turn binding.
- Chat renders task cards and background task result blocks.
- TaskPreviewBar shows active background tasks in the global shell; TaskFloater tabs cover background tasks, scheduled tasks, and artifacts.
- TaskFloater/Task Overlay can deep-link via `?view=tasks`, `task_view`, `task_id`, `chain_id`, and `trace_id` into all/current/history/scheduled/artifact-oriented task views.
- P1b `WorkflowStore` and `ArtifactStore` support linear chains, 9-state task nodes, cancel/retry, artifact indexing, and ChainBubble rendering.
- Current backend surfaces include `/api/bg-tasks`, `/api/workflows`, `/api/artifacts`, `/api/page-agent`, `/api/media`, `/api/files`, and `/api/audit` for task history, workflow/artifact snapshots, browser/page-agent sessions, generated media/files, and audit queries.
- Full durable Workflow Runner, fan-out/fan-in, saved workflow definitions, and workflow editor remain P2a/P2b/P2c scope.

## Observability

- Trace ids bind a single agent turn end to end; span ids represent operations.
- `trace_spans` and `token_usage` can be joined by trace/span/parent span ids.
- Token statistics pages and trace details expose model, provider, token counts, duration, errors, and session/turn context.
- Background task recent events and artifacts are projected into Agent Registry for operational display.

## Config, Security, and Access

- Console auth and RBAC protect pages and APIs.
- Agent Registry read surface is available to read roles; direct task submit/cancel is editor/admin; gateway restart is admin.
- Config pages manage nanobot, console, Codex, Claude Code, and Image Gen config files with list/read/update/reveal operations and masking/revision protections where applicable.
- Gateway status, health, console rebuild, and restart are exposed under `/api/gateway/*`.
- Unknown `/api/*` returns JSON errors instead of SPA HTML fallback.
- LAN Access supports local network enablement, PIN pairing, read-only device tokens, device revoke, and audit summary.

## Skills, Memory, and Channels

- Skills page manages built-in skills, skill detail/toggle/delete/install flows, MCP status/test/reconnect, and tool registry status.
- Memory and Persona remain under Settings -> Agents Config -> Nanobot.
- Chat supports multi-agent participants, explicit `@agent` mentions, context inspection, context size, and manual compression.
- Channel integrations and scheduled tasks remain available through existing config/runtime surfaces.

## Hook Feasibility for Claude Code and Codex Progress

- Current reliable progress source is Ava-owned: `BackgroundTaskStore` records submitted/started/succeeded/failed/cancelled events, CLI run/session ids, stdout/stderr-derived result previews, trace ids, and artifacts.
- Current display surfaces are Agent Registry active task counts, recent events, recent artifacts, task cancel actions, and TaskFloater background-task views. These surfaces read Ava's normalized task projection, not native CLI hook files directly.
- Claude Code and Codex native hook/status systems should not be read directly by Electron. If used, they should be wrapped by an Ava adapter that writes normalized events into `BackgroundTaskStore` or a future agent-event API.
- Existing `BackgroundTaskStore` post-task hooks are local completion hooks, currently used for console-ui rebuild checks; they are not native Claude Code or Codex progress ingestion.
- The minimum safe event contract is `agent`, `task_id`, `cli_run_id`, `event`, `detail`, `timestamp`, and optional `artifact_ref`.
- Display should continue to read from existing task and registry projections, so hook ingestion does not create a second task truth source.
- Repo code does not yet include a Claude Code/Codex native hook ingestion adapter. That is a separate follow-up after the desktop startup path is stable.

## Explicitly Deferred

- Code signing, notarization, hardened runtime, app icon, DMG, auto-updater.
- Embedded Python / PyInstaller / python-build-standalone packaging.
- Moving `Ava.app` to a different machine without the repo checkout and external nanobot checkout.
- Full workflow runner, visual workflow editor, approval/branch/loop workflow steps.
- Mobile P2 real-device acceptance and external relay/provider push surfaces.
