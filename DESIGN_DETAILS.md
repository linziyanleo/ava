# DESIGN_DETAILS.md — Ava Visual & Interaction Details

> Version: 0.4.3-B (details tier)
> Last updated: 2026-05-14
> Companion: [DESIGN.md](./DESIGN.md) is the summary tier — five core judgments, color semantics, theme moods, global shell rule. This file expands those into page-level guidelines, shared UI patterns, motion, mobile/LAN, accessibility, anti-patterns, and the review checklist.
> Non-goal: This is **not** a Tailwind migration plan, component API spec, backend state contract, or token implementation document.

---

## 1. How this document relates to DESIGN.md

DESIGN.md owns the foundational decisions:

- visual direction (warm cockpit),
- five core judgments,
- five core principles,
- theme palettes (dark + light),
- color semantics + soft layer rules,
- global shell rule (TopBar-first),
- shape & depth orientation,
- density orientation,
- motion orientation.

This file owns the **expansion** — the per-page rules, component behavior, full tables, accessibility specifics, anti-patterns, and the review checklist. When a hard rule appears in both files, DESIGN.md wins; this file should not contradict it.

---

## 2. Soft color layer

(Summary in DESIGN.md §5. Full table here.)

| Meaning | Dark soft feel | Light soft feel |
|---|---|---|
| Primary / selected | Deep teal tint | Pale green tint |
| Running | Dark blue tint | Pale blue tint |
| Success / healthy | Dark green tint | Pale green tint |
| Queued | Dark purple tint | Pale purple tint |
| Warning / retrying | Dark amber tint | Pale amber tint |
| Danger / failed | Dark red tint | Pale red tint |
| Idle / neutral | Muted gray tint | Warm gray tint |

Use cases: badge backgrounds, selected row/card tint, subtle banner fills, timeline step background, low-emphasis status surfaces.

Rules:

- Soft colors are not new semantic meanings.
- Soft colors are background/tint, never primary text.
- Selected items typically combine stronger border + soft tint, not heavy shadow.

---

## 3. Chart colors

Charts need their own categorical palette. Reusing status colors for generic categories causes accidental meaning ("the green line must mean healthy").

| Slot | Suggested |
|---|---|
| Chart 1 | `#8FB6FF` |
| Chart 2 | `#D7B5FF` |
| Chart 3 | `#E3B15F` |
| Chart 4 | `#7DD3B0` |
| Chart 5 | `#C9885C` |
| Chart 6 | `#A6B0A8` |

Rules:

- Use chart colors for categories, series, comparison data.
- Use status colors only when the chart explicitly visualizes status.
- Chart legends use text labels, not color alone.
- Avoid more than six colors per chart unless grouped or interactive.

---

## 4. Layout

### 4.1 Page structure

Most pages follow:

```txt
Page
├─ Header
│  ├─ Title
│  ├─ Current scope / workspace / filter summary
│  └─ Primary page action
├─ Control row
│  ├─ Search / filters / grouping
│  └─ View options
├─ Main content
│  ├─ List / table / grid / timeline / chat
│  └─ Empty / loading / error state
└─ Optional detail panel / drawer / floater
```

Rules:

- Header explains the page's operational purpose.
- Filters stay close to the data they affect.
- Detail panels preserve the user's context; the selected entity should be visually connected to its detail panel.
- Long logs and JSON should not take over the primary layout.

### 4.2 Sidebars

(Rule lives in DESIGN.md §7.) Sidebars are allowed only as section-level secondary navigation. Specific allowed cases:

- Settings tree.
- Workflow step navigator.
- Artifact file tree.
- Optional detail navigation inside complex pages.

---

## 5. Density defaults

| Element | Desired feel | Avoid |
|---|---|---|
| Page padding | Medium operational padding | Marketing page padding |
| Card padding | Compact control-plane card | Spacious document page |
| Table rows | Dense scanning list | Tall marketing table |
| Page gaps | Medium operational spacing | Hero-section whitespace |
| Buttons | Comfortable but not oversized | App-store CTA size |
| Badges | Small, legible, aligned with metadata | Large standalone tags |
| Logs/code | Compact monospace surface | Loose paragraph spacing |
| Drawers | Wide enough for technical detail | Narrow modal-like sliver |
| Metadata | Compact and aligned | Paragraph-like metadata |
| Chat stream | Readable but state-rich | Bubble-only messenger layout |

Avoid full-page whitespace unless it is an onboarding or empty state.

---

## 6. Typography

| Role | Style |
|---|---|
| Page title | 22–24px, semibold |
| Section title | 16–18px, semibold |
| Card title | 14–16px, semibold |
| Body text | 14px |
| Metadata | 12–13px |
| Badge text | 12px, medium |
| Logs/code | 12–13px monospace |

Rules:

- Use sentence case.
- Avoid all-caps labels except tiny technical tags when necessary.
- Use monospace only for IDs, paths, commands, logs, JSON, diffs, code.
- Keep labels literal: `Running`, `Queued`, `Retrying`, `Disconnected`, `View logs`.

---

## 7. Shared UI Patterns

### 7.1 Status Badge

```txt
[icon or dot] Label [optional detail]
```

Examples:

```txt
● Running · 12m
✓ Completed
! Retrying · 2nd attempt
× Failed · 3m ago
○ Idle
```

Rules:

- Badge must include text.
- Running badges may use subtle motion, not constant noise.
- Failed/blocked/disconnected badges should be easy to notice; neutral badges stay quiet.
- Do not create page-specific badge colors.

### 7.2 Buttons and actions

| Variant | Use |
|---|---|
| Primary | One prominent action in a region |
| Secondary | Normal safe action |
| Ghost | Toolbars, row actions, low-priority actions |
| Danger | Destructive or interrupting action |
| Icon | Compact actions with label/tooltip |

Rules:

- One primary per region.
- Destructive actions are explicit: `Stop agent`, `Cancel task`, `Delete artifact`.
- Destructive actions should not sit visually next to safe primary actions without separation.
- Disabled actions must explain why when the reason is not obvious.

### 7.3 Cards

Cards summarize operational entities. Good content: title, status, 3–5 metadata points, current activity, last updated/heartbeat, one prominent action, secondary actions.

Cards rely on borders and subtle surface changes more than heavy shadows. Do not stuff full logs, raw JSON, or decorative graphics into cards.

### 7.4 Tables and lists

Use tables/lists when items are comparable.

- Status comes early in the row, time/duration near status.
- Row actions stay aligned and predictable.
- Long text truncates with access to detail.
- Selected row connects clearly to its detail panel.
- Failed/running rows must be visually scannable.

### 7.5 Detail panels and drawers

For logs, step details, task history, artifact metadata, retry/error context, raw output.

- Top of panel shows entity name and status.
- Primary action stays visible.
- Logs are scroll-contained; raw error is expandable.
- Detail panels tied to a selection should not feel like detached modals.

### 7.6 Code and log panels

Code/log panels may use a dark surface in both dark and light themes — Ava is a developer/control-plane tool, and dark code/log panels preserve terminal readability convention.

This applies to **dedicated** log/code viewer panels and artifact code previews. Inline code inside chat messages, metadata, or compact summaries should follow the surrounding surface theme and should not force a dedicated dark panel.

Rules:

- Use monospace, preserve whitespace.
- Provide copy action when useful.
- Contain long content in a scroll area.
- Logs stay visually secondary to state and summary.
- Errors show human summary before raw logs.

### 7.7 Banners and connectivity strips

For app-level or page-level system state: Ava core not ready, WebSocket disconnected, mobile read-only, workspace unavailable, model provider degraded, bootstrap required.

- Banners are short and actionable.
- Amber for warning/bootstrap; red for disconnected/blocking failure.
- Green only for successful restoration, briefly.
- Do not stack more than two banners; consolidate if necessary.

### 7.8 Chips and HUD widgets

Compact contextual info: token usage, model, skills, memory, artifacts, workspace, agent kind, cost, duration.

- Chips are metadata, not primary actions.
- HUD widgets stay quiet unless they need attention.
- Use status color only when the chip represents status — no rainbow chip groups.

### 7.9 Floaters

Allowed for persistent operational overlays — TaskFloater, active workflow floater, upload/progress floater, global failure indicator.

- Must not block primary work; dismissible/collapsible when safe.
- Summarize state first, detail second.
- On mobile, must avoid BottomNav and safe-area collisions.
- A floater must not become a second dashboard.

### 7.10 Empty, loading, and error states

```txt
Empty  → Title / Description / Action
Error  → Title / Summary / Detail (expandable raw) / Time / Action
```

Loading: skeletons for structured content, spinners for short isolated actions, preserve layout stability, avoid full-page loading unless the page is unavailable.

---

## 8. Page Guidelines

Each page lists only the **Ava-specific judgments**. Generic best practices already in §7 are not repeated.

### 8.1 Chat

Chat must distinguish: user messages, agent messages, system events, tool calls, chain/workflow updates, artifacts, memory/context updates, background tasks.

Ava-specific:

- User and agent messages can look conversational, but **system events look like operational timeline entries**, not chat bubbles.
- Tool calls are collapsible; long agent output shows summary first.
- HUD widgets (Token, Skills, Artifacts, Memory) use chip/widget styling.
- TaskFloater stays visible but does not dominate.
- BootstrapBanner clearly communicates: Ava core unavailable / initializing / degraded.
- If a chat message is tied to a workflow, workflow state is visible near the message or thread.

#### ChainBubble

(Core rule lives in DESIGN.md §2 judgment 5.)

ChainBubble is a compact workflow-timeline visual **inside** the chat stream. It shows status markers, step progression, active/failed/completed state, linked artifacts, retry/error summary.

ChainBubble must be visually distinct from conversational message bubbles, system timeline entries, and collapsible tool-call blocks. It feels like an **embedded workflow card**, not another chat message.

Chat must not become a wall of bubbles with hidden system state, a log viewer, or a decorative assistant UI detached from task execution.

### 8.2 Agent Dashboard

Each agent card shows: name, kind, status, model/runtime, current task or last event, token/cost/duration when useful, heartbeat/last seen, one prominent action, secondary actions.

Action hierarchy by state:

| Agent state | Prominent | Secondary |
|---|---|---|
| Available / idle | Dispatch or Start task | Restart, settings, logs |
| Running | View run | Stop, logs, restart |
| Failed | View error or Retry | Logs, restart |
| Disconnected | Reconnect | Logs, settings |
| Paused | Resume | Stop, settings |

Ava-specific:

- Running agents are easy to scan but not visually noisy.
- Failed/disconnected agents rise in priority.
- Idle agents look calm, not broken.

### 8.3 Tasks / Background Tasks

Visual order of attention:

1. Running
2. Failed / blocked
3. Queued / waiting
4. Recently completed
5. Historical

Required info: task title or prompt summary, target agent/tool, status, start time, duration, workspace/project, next action.

Ava-specific:

- Failed task rows must show reason or a path to reason.
- Running tasks show progress or current phase when available.
- **Queued (purple) is clearly different from waiting/retrying (amber).**
- Do not bury active tasks below historical content.

### 8.4 Workflow Detail

The clearest expression of state progression.

```txt
Workflow Header   → status, duration, started, coordinator, primary action
Timeline          → step status, agent, input summary, output/artifact, error/retry
Detail Panel      → selected step detail, logs, artifacts, retry/error info
```

Ava-specific:

- Timeline markers use semantic status colors (DESIGN.md §5).
- Each step shows state, agent, output.
- Failed steps show reason and next action.
- Retried steps show retry count/history.
- Completed steps stay visually quiet but readable.
- Current running step is visually active (subtle pulse OK, not constant noise).

### 8.5 Artifact Preview

Header: artifact type, source agent, linked task/workflow, created time, status if generation incomplete.

Body adapts by type: text, code, image, diff, JSON, logs, file tree, generated output.

Ava-specific:

- Raw content does not overpower metadata.
- Diffs/code/logs use code panel conventions (§7.6).
- Actions are predictable: open, copy, export/download, reveal in workspace.
- Artifact errors show summary before raw output.

### 8.6 Settings

Calmer and simpler than operational pages. Group by domain: Agents, Models, Workspaces, Runtime, Integrations, Appearance, Mobile/LAN access.

Ava-specific:

- Destructive actions stay separated.
- Validation appears near the relevant field.
- Appearance settings expose dark/light/system choices.
- Settings can use **section-level** navigation, not global sidebar (DESIGN.md §7).

---

## 9. Motion

(Summary in DESIGN.md §6.)

Allowed:

- hover/press feedback,
- drawer/panel open/close,
- timeline expansion,
- running indicator pulse,
- subtle skeleton loading,
- status transition feedback.

Avoid:

- page entrance animation,
- bouncy spring effects,
- decorative particles,
- persistent AI glow,
- slow cinematic transitions,
- animation that distracts from state.

Speed feel:

- fast for hover/press,
- moderate for drawers/panels,
- subtle for running indicators.

If reduced motion is enabled, preserve state changes with static visual indicators instead of animation.

---

## 10. Mobile / LAN Device

Mobile/LAN access is a first-class mode, not a broken desktop shrink.

### 10.1 Navigation

Use bottom navigation for primary mobile destinations.

- BottomNav must not collide with floaters.
- Active destination is obvious.
- Keep labels short; no more than five primary destinations.

### 10.2 Touch targets

- ≥44px hit area where practical.
- Avoid tiny icon-only controls without enough hit area.
- Crowded row actions become sheets or menus.
- Dense desktop tables become lists/cards on mobile.

### 10.3 Safe areas and keyboard

- Respect safe-area insets.
- Chat input must remain usable above mobile keyboard.
- Floaters and banners must not cover the composer.
- Bottom sheets account for device safe areas.

### 10.4 Read-only mode

LAN/mobile devices may be read-only.

- Write actions are hidden or clearly disabled.
- Disabled write actions should not look like failures.
- The UI explains read-only mode when relevant.
- Read-only still allows inspection of state, logs, artifacts, progress.

### 10.5 PIN pairing / device access

Show device identity, connection status, permission level, expiration/validity, error state, clear next action. Security UI is plain and explicit — no cute copy.

---

## 11. Accessibility

### 11.1 Status accessibility

Color alone is never sufficient (DESIGN.md §5). Critical state changes must be visible without hover. Error states should be copyable or inspectable.

### 11.2 Focus

Keyboard focus must remain visible. Selected ≠ focused:

- selected = current item or opened detail,
- focus = current keyboard target.

When an element is both, both states remain understandable.

### 11.3 Reduced motion

Respect reduced-motion preferences:

- remove pulsing animation,
- remove shimmer,
- reduce drawer transitions,
- preserve state changes with static indicators.

### 11.4 Icon-only controls

Must have accessible label, tooltip or visible label when helpful, enough hit area, clear disabled state.

---

## 12. Visual Anti-patterns

Avoid:

- Global desktop sidebar as default navigation.
- Generic slate-blue SaaS appearance.
- Neon AI gradients.
- Random colorful tags for status.
- Multiple equal-weight primary buttons.
- Heavy shadows on dense operational cards.
- Hiding failure reason inside logs only.
- Using green for running.
- Using blue as both brand and running.
- Making Chat look detached from workflows/tasks.
- Making mobile a squeezed desktop layout.
- Decorative animation that does not express state.
- Code/log panels that dominate page hierarchy.
- Disabled controls with no explanation.
- Redundant toast notifications for state already visible through badges, banners, floaters, or timeline updates.

Use toast only for transient events not already visible in the current UI, or for confirmations that would otherwise be missed.

---

## 13. Design Review Checklist

Use this checklist when reviewing Ava UI changes. These are **Ava-specific hard rules** — generic checks (focus visible, touch targets large enough, etc.) are covered in §10/§11 and not repeated here.

- [ ] **Warm cockpit, not slate-blue.** Does the screen feel like Ava's warm operations cockpit, not a generic slate-blue SaaS dashboard?
- [ ] **Status colors match DESIGN.md §5.** Running is blue (not green), brand is green/teal (not running blue), queued is purple (not amber), no one-off semantic colors.
- [ ] **TopBar-first.** No global desktop sidebar; sidebars only as section-level navigation.
- [ ] **Border-first separation.** Cards/panels separate by border + subtle surface, not heavy shadow. Shadow reserved for drawers, popovers, floaters, dialogs.
- [ ] **ChainBubble is not a chat bubble.** ChainBubble visually reads as an embedded workflow card with timeline state, not as another conversational message or tool-call block.
- [ ] **Toast restraint.** Toast is not used for state already visible elsewhere (badge, banner, floater, timeline).
- [ ] **Motion is functional.** No decorative animation; reduced-motion preserves state via static indicators.
