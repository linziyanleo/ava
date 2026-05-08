# Agent Control Plane Completion Audit

Date: 2026-05-08
Branch: `feat/control-plane-ux-linear`
Base requirement: branch from `feat/0.1.0`

## Objective

User objective:

- Use Linear AVA tasks at `https://linear.app/avava/team/AVA/all`.
- Complete tasks in priority order.
- Verify final results against `IDEA.md`.
- Verify final results against `docs/superpowers/specs/2026-05-07-ava-control-plane-ux-design.md`.
- Develop on a new branch based on `feat/0.1.0`.

## Current Linear Scope

Linear was updated on 2026-05-08 so these issues are now `Backlog` with the
`deferred` label:

- P2: AVA-25, AVA-26, AVA-28, AVA-29, AVA-30
- P3: AVA-31, AVA-32, AVA-33, AVA-34, AVA-35, AVA-36

Those issues are not part of the current P1b passing acceptance. Deferred code
artifacts must not be mounted, visible, or required by current acceptance.
Inbox, manual Workflow editor, Relay, Notifications, HUD widget marketplace,
LAN P2, mobile native redesign, and external provider/device evidence are
future milestone scope.

## Prompt-To-Artifact Checklist

| Requirement | Artifact / evidence | Status |
| --- | --- | --- |
| New branch from `feat/0.1.0` | `git branch --show-current` -> `feat/control-plane-ux-linear`; prior `git merge-base --is-ancestor feat/0.1.0 HEAD` -> exit 0 | Complete |
| P1b Linear checklist coverage | `tests/console_ui/test_linear_acceptance_checklists.py` covers the active P1b / tech-debt issues and explicitly excludes deferred P2/P3 UI scope | Complete |
| Deferred P2/P3 removal | Current app/test surface no longer contains Inbox, manual Workflow editor, Relay, Notifications, HUD widget marketplace, PWA manifest/service worker, P2/P3 runner, or their acceptance tests | Complete |
| IDEA.md alignment | `IDEA.md` marks P2/P3 issues as Linear-deferred instead of current complete capabilities | Complete |
| Design spec alignment | `docs/superpowers/specs/2026-05-07-ava-control-plane-ux-design.md` already lists Inbox, manual Workflow, LAN P2, HUD marketplace, Relay, collaboration, and push as non-goals / later phases | Complete |
| Visible Settings IA | `console-ui/src/App.tsx` and `console-ui/src/pages/SettingsPage.tsx` no longer expose current routes/nav for Inbox, Workflows, Relay, Notifications, or HUD Widgets | Complete |
| Deferred backend route wiring | `ava/console/app.py` and `ava/console/routes/__init__.py` no longer mount/re-export Inbox, Relay, Notifications, or Collaboration routes in the current app | Complete |
| Chat IA | `console-ui/src/pages/ChatPage/index.tsx` no longer renders top channel tabs and no longer filters the session list by scene | Complete |
| Chat scroll-to-bottom affordance | `console-ui/src/pages/ChatPage/MessageArea.tsx` uses a sticky in-container `ArrowDownToLine` button, rAF-throttled scroll checks, and `ResizeObserver` instead of the old absolute floating button | Complete |
| Conversation task card consistency | `ConversationTaskCard` is the single render surface for standalone, chain, and background-result task cards; `SceneTabs.tsx` has been removed | Complete |
| Conversation task ordering | Direct/background task messages carry `origin_conversation_id` and `origin_turn_seq`; `MessageArea` groups task cards by turn and suppresses duplicate legacy result cards | Complete |
| Natural-language skill chain ordering | `ChatService.next_console_turn_ref` predicts the active conversation turn before registering a natural-language skill chain, so the synthetic skill task is anchored to its trigger turn | Complete |
| Session list readable surface | `SessionSidebar` renders metadata `title`, recent conversation preview, participant Agent badges, and Agent labels instead of using the raw session key as the primary label | Complete |
| Message header readable surface | `MessageArea` renders a product title, Agent badge row, and thread state; the raw session key remains only a copy target and Context Inspector receives the readable label | Complete |
| HUD scope | `console-ui/src/pages/ChatPage/HudBar.tsx` renders the four P1b static widgets directly instead of consuming HUD marketplace preferences | Complete |
| LAN Access P1b scope | `console-ui/src/pages/LanAccessPage.tsx` exposes LAN enablement, LAN URLs, PIN, device tokens, revoke, and audit; HTTPS, mDNS, PWA, and QR UI are deferred | Complete |
| Workflow P1b scope | `ava/console/routes/workflow_routes.py` uses `WorkflowStore.advance_linear_chain/cancel_chain/retry_chain` directly; `ava/workflow/runner.py` has been removed from the current P1b branch | Complete |
| Linear deferred wording | AVA-25/26/28/29/30/31/32/33/34/35/36 descriptions were aligned with the current P1b boundary; AVA-25/30/35/36 also have correction comments for stale fan-out/dependency wording | Complete |

## Verification Commands

Fresh commands run on 2026-05-08:

```bash
cd console-ui && npm run build
```

Result: passed. Vite printed the known Node 20.16.0 warning because this shell
is not using the repo `.nvmrc` Node 20.19.0, then built successfully with the
existing chunk-size warning.

```bash
uv run --extra dev pytest tests/console_ui/test_linear_acceptance_checklists.py -q
```

Result: `24 passed`.

```bash
PYTHONPATH=/Users/fanghu/Documents/Test/nanobot \
AVA_NANOBOT_ROOT=/Users/fanghu/Documents/Test/nanobot \
uv run --extra dev pytest \
  tests/console/test_config_service.py \
  tests/console/test_lan_access_routes.py \
  tests/console/test_workflow_routes.py \
  tests/agent/test_workflow_store.py -q
```

Result: `19 passed`.

```bash
PYTHONPATH=/Users/fanghu/Documents/Test/nanobot \
AVA_NANOBOT_ROOT=/Users/fanghu/Documents/Test/nanobot \
uv run --extra dev pytest \
  tests/console/test_mock_tester_pages.py tests/console/test_gateway_service.py -q
```

Result: `10 passed`.

```bash
PYTHONPATH=/Users/fanghu/Documents/Test/nanobot \
AVA_NANOBOT_ROOT=/Users/fanghu/Documents/Test/nanobot \
uv run --extra dev python - <<'PY'
from pathlib import Path
from ava.console.app import create_console_app_standalone
root = Path('/tmp/ava-app-smoke')
workspace = Path('/tmp/ava-workspace-smoke')
root.mkdir(parents=True, exist_ok=True)
workspace.mkdir(parents=True, exist_ok=True)
app = create_console_app_standalone(root, workspace, gateway_port=18790, console_port=16688)
paths = {route.path for route in app.routes}
for path in ['/api/inbox/count', '/api/relay/status', '/api/notifications/push/status', '/api/collaboration/presence']:
    print(path, path in paths)
print('/api/lan-access/status', '/api/lan-access/status' in paths)
print('/api/gateway/status', '/api/gateway/status' in paths)
PY
```

Result: deferred P3 paths printed `False`; active LAN/Gateway paths printed
`True`.

```bash
uv run --extra dev python -m py_compile \
  ava/console/app.py \
  ava/console/routes/__init__.py \
  ava/console/routes/config_routes.py \
  ava/console/routes/workflow_routes.py \
  ava/console/routes/lan_access_routes.py \
  ava/console/services/config_service.py \
  ava/console/services/lan_access_service.py \
  ava/agent/workflow_store.py
```

Result: passed.

```bash
git diff --check
```

Result: passed.

```bash
PYTHONPATH=/Users/fanghu/Documents/Test/nanobot \
AVA_NANOBOT_ROOT=/Users/fanghu/Documents/Test/nanobot \
uv run --extra dev pytest \
  tests/console_ui/test_linear_acceptance_checklists.py \
  tests/console_ui/test_redirect_matrix.py \
  tests/guardrails/test_ava8_decoupling_boundary.py -q
```

Result: `31 passed`.

```bash
PYTHONPATH=/Users/fanghu/Documents/Test/nanobot \
AVA_NANOBOT_ROOT=/Users/fanghu/Documents/Test/nanobot \
uv run --extra dev pytest \
  tests/console/test_config_service.py \
  tests/console/test_lan_access_routes.py \
  tests/console/test_workflow_routes.py \
  tests/agent/test_workflow_store.py \
  tests/agents/test_skill_matcher.py \
  tests/console/test_mock_tester_pages.py \
  tests/console/test_gateway_service.py \
  tests/console/test_agent_registry_service.py \
  tests/console/test_agent_routes.py \
  tests/console/test_direct_task_service.py \
  tests/agent/test_bg_tasks.py \
  tests/desktop/test_electron_shell_contract.py -q
```

Result: `61 passed`.

Latest chat-task-card refactor checks run on 2026-05-08:

```bash
PYTHONPATH=/Users/fanghu/Documents/Test/nanobot \
AVA_NANOBOT_ROOT=/Users/fanghu/Documents/Test/nanobot \
uv run --extra dev pytest \
  tests/console/test_chat_service.py \
  tests/console/test_chat_routes.py \
  tests/console/test_direct_task_routes.py \
  tests/console_ui/test_linear_acceptance_checklists.py -q
```

Result: `70 passed`.

```bash
PYTHONPATH=/Users/fanghu/Documents/Test/nanobot \
AVA_NANOBOT_ROOT=/Users/fanghu/Documents/Test/nanobot \
uv run --extra dev python -m py_compile \
  ava/console/routes/chat_routes.py \
  ava/console/services/chat_service.py \
  ava/console/routes/direct_task_routes.py
```

Result: passed.

```bash
cd console-ui && npm run build
```

Result: passed with the known local Node 20.16.0 / Vite 20.19+ warning and
existing chunk-size warning.

```bash
cd console-ui
npm run preview -- --host 127.0.0.1 --port 4173
BASE_URL=http://127.0.0.1:4173 node e2e/control-plane-smoke.mjs
```

Result: `control-plane-smoke: passed`. The smoke now includes a `task_id`
deep-link with `origin_turn_seq=0` and asserts the unified task card renders
once after its trigger turn.

Claude Code review follow-up checks run on 2026-05-08:

```bash
PYTHONPATH=/Users/fanghu/Documents/Test/nanobot \
AVA_NANOBOT_ROOT=/Users/fanghu/Documents/Test/nanobot \
uv run --extra dev pytest \
  tests/console/test_chat_service.py \
  tests/console_ui/test_linear_acceptance_checklists.py -q
```

Result: `48 passed`.

```bash
cd console-ui && npm run build
```

Result: passed with the known local Node 20.16.0 / Vite 20.19+ warning and
existing chunk-size warning.

```bash
cd console-ui
npm run preview -- --host 127.0.0.1 --port 4173
BASE_URL=http://127.0.0.1:4173 node e2e/control-plane-smoke.mjs
```

Result: `control-plane-smoke: passed`. The smoke now checks the readable
session title, Agent label row, and absence of raw `console:smoke` text from
the normal Chat surface.

```bash
git diff --check
```

Result: passed.

Additional final audit commands run on 2026-05-08:

```bash
uv run --extra dev pytest \
  tests/console_ui/test_linear_acceptance_checklists.py \
  tests/console_ui/test_redirect_matrix.py \
  tests/guardrails/test_ava8_decoupling_boundary.py -q
```

Result: `31 passed`.

```bash
PYTHONPATH=/Users/fanghu/Documents/Test/nanobot \
AVA_NANOBOT_ROOT=/Users/fanghu/Documents/Test/nanobot \
uv run --extra dev pytest \
  tests/console/test_config_service.py \
  tests/console/test_lan_access_routes.py \
  tests/console/test_workflow_routes.py \
  tests/agent/test_workflow_store.py \
  tests/agents/test_skill_matcher.py -q
```

Result: `22 passed`.

```bash
PYTHONPATH=/Users/fanghu/Documents/Test/nanobot \
AVA_NANOBOT_ROOT=/Users/fanghu/Documents/Test/nanobot \
uv run --extra dev pytest \
  tests/console/test_mock_tester_pages.py \
  tests/console/test_gateway_service.py \
  tests/console/test_agent_registry_service.py \
  tests/console/test_agent_routes.py \
  tests/console/test_direct_task_service.py \
  tests/console/test_chat_service.py \
  tests/console/test_chat_routes.py \
  tests/agent/test_bg_tasks.py \
  tests/desktop/test_electron_shell_contract.py -q
```

Result: `80 passed`.

```bash
cd console-ui
npm run preview -- --host 127.0.0.1 --port 4173
BASE_URL=http://127.0.0.1:4173 node e2e/control-plane-smoke.mjs
```

Result: `control-plane-smoke: passed`. The smoke now checks the current P1b
surface and no longer expects deferred presence/conflict, manual Workflow,
Relay, Notifications, or LAN P2 UI.

Final post-Linear sync checks run on 2026-05-08:

```bash
PYTHONPATH=/Users/fanghu/Documents/Test/nanobot \
AVA_NANOBOT_ROOT=/Users/fanghu/Documents/Test/nanobot \
uv run --extra dev pytest \
  tests/console/test_chat_service.py \
  tests/console_ui/test_linear_acceptance_checklists.py -q
```

Result: `48 passed`.

```bash
cd console-ui && npm run build
```

Result: passed with the known local Node 20.16.0 / Vite 20.19+ warning and
existing chunk-size warning.

```bash
cd console-ui
npm run preview -- --host 127.0.0.1 --port 4173
BASE_URL=http://127.0.0.1:4173 node e2e/control-plane-smoke.mjs
```

Result: `control-plane-smoke: passed`.

Note: `uv run pytest ...` without `--extra dev` used the wrong pytest/runtime
surface and failed before collection with `ModuleNotFoundError: ava.adapters`.
`uv run --extra dev pytest ...` is the valid repo command because pytest is a
dev extra.

## Remaining Audit Notes

The current P1b acceptance is aligned with updated Linear scope.

Final live audit on 2026-05-08 confirmed:

- active P1b / tech-debt Linear issues are `Done`:
  AVA-5/6/7/8/9/10/12/13/14/15/16/17/18/19/20/21/22/23/24/27/37/38;
- `P1b` + `In Review` query returned zero issues;
- AVA-11 is `Canceled` and merged into AVA-23;
- P2/P3 Linear issues AVA-25/26/28/29/30/31/32/33/34/35/36 are
  `Backlog` with `deferred`;
- browser smoke was run against this worktree preview on
  `http://127.0.0.1:4173`, not the separate local `feat/0.1.0` console on
  port 6688.

No further Linear status transition is pending for current P1b acceptance.

Do not use old AVA-28/30/34/35 external manual evidence as a blocker for P1b
completion while those issues remain Linear-deferred.
