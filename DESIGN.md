# DESIGN.md — Ava Visual & Interaction Guidelines

> Version: 0.4.3-B (summary tier)
> Last updated: 2026-05-14
> Purpose: Single-page summary of Ava's visual direction and interaction standards.
> Companion: See [DESIGN_DETAILS.md](./DESIGN_DETAILS.md) for page-by-page guidelines, shared UI patterns, mobile/LAN rules, motion, accessibility, anti-patterns, and the design review checklist.
> Non-goal: This is **not** a Tailwind migration plan, component API spec, backend state contract, or token implementation document.

---

## 1. What Ava is

Ava is an **Agent Control Plane** — a calm, reliable, high-density operating cockpit for coordinating multiple agents, tasks, workflows, artifacts, and system state.

It should look like a focused desktop productivity tool, a warm operational control surface, a state-first multi-agent command center, a technical workspace that remains readable during long sessions.

It should **not** look like a generic SaaS dashboard, a marketing AI landing page, a decorative chat app, a raw developer console, or a random collection of Tailwind utilities.

Visual direction:

> **Warm operations cockpit** — dark-first, state-led, compact, readable, precise, slightly warm rather than cold slate-blue.

---

## 2. Five core judgments

These five anchor every visual and interaction decision. When a decision is unclear, return to them.

1. **Dark-first warm operations cockpit.** Not slate-blue SaaS, not marketing AI, not raw devtool. Warm charcoal/green canvas, deep teal/green primary, restrained accents.
2. **Six semantic status colors.** Brand-green, blue (running), green (healthy/done), purple (queued), amber (waiting/retrying), red (failed/blocked), neutral (idle). Used identically everywhere.
3. **TopBar-first global shell.** Desktop navigation lives in the top bar. Sidebars are only allowed as section-level secondary navigation (Settings tree, workflow step navigator, artifact tree).
4. **Border-first separation, restrained shadow.** Cards, panels, rows separate by border + subtle surface change. Shadows are reserved for drawers, popovers, dialogs, floaters.
5. **ChainBubble is an embedded workflow card inside chat.** Not another chat bubble, not a toolcall block. Visually distinct, status-led, links to workflow detail.

---

## 3. Core principles

- **State is the primary UI.** A user should scan a screen and quickly answer: what is running, waiting, failed, needs attention, can I do next. Do not hide state inside logs, raw JSON, or hover-only UI.
- **Clarity before beauty.** Visual polish is useful only when it improves comprehension. Avoid decorative gradients, noisy animation, excessive shadows, "AI sparkle".
- **Dense, but not cramped.** Density is welcome — but metadata stays compact, status stays obvious, actions stay grouped, long content stays contained, detail is progressively disclosed.
- **One prominent action per region.** A region may expose multiple actions; only one is visually dominant — the most relevant for the current state.
- **Chat is important, but not the whole product.** Chat coexists with chain state, tool calls, artifacts, memory, background tasks, workflow progress, system events, runtime/connectivity. Chat is an operational command surface, not a messaging screen.

---

## 4. Theme

Ava is **dark-first** because it is a long-session control-plane app. Light mode remains a first-class supported appearance for demos, daylight usage, screenshots, documentation, and users who prefer light UI.

The redesign should not preserve the old generic slate-blue look by default.

### Dark mood

Warm charcoal / green-black canvas, slightly raised dark green-gray surfaces, subtle warm borders, deep teal/green brand accents, blue only for live/running state, restrained amber/gold for attention, red only for failure. Avoid pure black, generic slate panels, neon blue overload, AI gradients, glowing borders.

| Role | Suggested |
|---|---|
| Canvas | `#0F1512` |
| Muted canvas | `#121C18` |
| Surface | `#17211D` |
| Raised surface | `#1E2A25` |
| Border | `#2B3A33` |
| Strong border | `#3F554A` |
| Primary / brand | `#2AA982` |
| Primary hover | `#34C596` |
| Text | `#ECF4EF` |
| Muted text | `#AAB8AF` |

### Light mood

Cream canvas, white/near-white cards, warm gray borders, deep green primary, restrained gold/caramel accents, high readability, low shadow.

| Role | Suggested |
|---|---|
| Canvas | `#FFFDF7` |
| Muted canvas | `#F8F3EA` |
| Surface | `#FFFFFF` |
| Raised surface | `#FFFCF5` |
| Border | `#E7DED0` |
| Strong border | `#D6C7B7` |
| Primary / brand | `#145A48` |
| Primary hover | `#0F4638` |
| Text | `#24342C` |
| Muted text | `#69756E` |

---

## 5. Color semantics (single source of truth)

Color carries consistent meaning across the entire app. Other documents and components reference back here.

| Meaning | Color | Use for |
|---|---|---|
| Brand / primary action | Deep green / teal | Main CTA, selected high-level navigation, Ava identity |
| Running / live / streaming | Blue | Active workflow, active task, streaming agent output |
| Healthy / available / completed | Green | Available agent, completed step, successful task |
| Queued | Purple | Queued work that has not started |
| Waiting / retrying / warning / slow | Amber | Waiting on input, retrying, delayed, attention needed |
| Failed / blocked / disconnected | Red | Failure, offline, blocked, destructive actions |
| Idle / paused / cancelled | Neutral | Quiet inactive state |

Hard rules:

- **Running is blue, not green.** Green means healthy/available/completed.
- **Brand green ≠ running blue.** Brand is CTA color; running is state.
- **Color alone is never sufficient.** Always pair with label, icon, dot, timestamp, or metadata.
- **No one-off semantic colors.** Page-specific status palettes are not allowed.

### Soft layer

Every semantic color has a soft variant for badge backgrounds, selected row/card tint, subtle banner fills, timeline step background. Soft colors should be visible but quiet — they support existing semantics, do not introduce new meaning, and are never used for primary text. Selected items typically combine **stronger border + soft tint**, not heavy shadow.

### Charts

Charts use their own categorical palette (see [DESIGN_DETAILS.md §3](./DESIGN_DETAILS.md#3-chart-colors)). Do not reuse status colors for generic chart categories — a green line should not accidentally imply "healthy".

---

## 6. Visual feel

### Shape & depth

- **Border-first.** Cards, panels, rows, drawers separate by border + subtle surface change.
- **Shadows are restrained.** Reserved for drawers, popovers, floaters, dialogs.
- **Moderate radius.** Buttons and inputs softly rounded; cards and panels moderate; badges/chips may be pill-shaped; code/log panels slightly squarer. Do not pill-shape everything.

### Density

Operational, not marketing. Compact card padding, dense scanning rows, comfortable but not oversized buttons, small legible badges aligned with metadata. Avoid hero-section whitespace, spacious document padding, app-store CTA buttons. (Full table in [DESIGN_DETAILS.md §5](./DESIGN_DETAILS.md#5-density-defaults).)

### Typography

Practical and quiet. Sentence case. Monospace only for IDs, paths, commands, logs, JSON, diffs, code. Labels stay literal: `Running`, `Queued`, `Retrying`, `View logs`. (Full hierarchy in [DESIGN_DETAILS.md §6](./DESIGN_DETAILS.md#6-typography).)

### Motion

Functional, fast, restrained. Allowed: hover/press feedback, drawer/panel open-close, timeline expansion, running indicator pulse, subtle skeleton, status transition. Avoid: page entrance animation, bouncy spring, decorative particles, persistent AI glow, slow cinematic transitions. Reduced motion preserves state via static indicators. (Detail in [DESIGN_DETAILS.md §9](./DESIGN_DETAILS.md#9-motion).)

---

## 7. Global shell

Ava desktop navigation is **TopBar-first**. Do not introduce a global desktop sidebar as the default navigation model.

| Pattern | Allowed? |
|---|---:|
| Global desktop sidebar for all navigation | No |
| TopBar global navigation | Yes |
| Section sidebar (Settings tree, workflow steps, artifact tree) | Yes |
| Right detail panel (selected task/agent/artifact) | Yes |

Global shell contains workspace/project context, global navigation, connection/bootstrap state, running task indicator, theme/settings entry.

Page structure, banners, floaters, and drawers are detailed in [DESIGN_DETAILS.md §7](./DESIGN_DETAILS.md#7-shared-ui-patterns).

---

## 8. Where the rest lives

| Topic | Location |
|---|---|
| Chart palette | [DESIGN_DETAILS.md §3](./DESIGN_DETAILS.md#3-chart-colors) |
| Soft color tints (per-theme) | [DESIGN_DETAILS.md §2](./DESIGN_DETAILS.md#2-soft-color-layer) |
| Page structure & density table | [DESIGN_DETAILS.md §4](./DESIGN_DETAILS.md#4-layout) |
| Density defaults | [DESIGN_DETAILS.md §5](./DESIGN_DETAILS.md#5-density-defaults) |
| Typography scale | [DESIGN_DETAILS.md §6](./DESIGN_DETAILS.md#6-typography) |
| StatusBadge / Buttons / Cards / Tables / Drawers / Code panels / Banners / Chips / Floaters / Empty-Loading-Error | [DESIGN_DETAILS.md §7](./DESIGN_DETAILS.md#7-shared-ui-patterns) |
| Per-page guidelines (Chat / Agents / Tasks / Workflow Detail / Artifact / Settings) | [DESIGN_DETAILS.md §8](./DESIGN_DETAILS.md#8-page-guidelines) |
| Motion specifics | [DESIGN_DETAILS.md §9](./DESIGN_DETAILS.md#9-motion) |
| Mobile / LAN device | [DESIGN_DETAILS.md §10](./DESIGN_DETAILS.md#10-mobile--lan-device) |
| Accessibility | [DESIGN_DETAILS.md §11](./DESIGN_DETAILS.md#11-accessibility) |
| Anti-patterns | [DESIGN_DETAILS.md §12](./DESIGN_DETAILS.md#12-visual-anti-patterns) |
| Design review checklist | [DESIGN_DETAILS.md §13](./DESIGN_DETAILS.md#13-design-review-checklist) |

---

## 9. Final direction

Ava should be redesigned as a **dark-first warm operations cockpit**.

The redesign should improve scan speed, confidence, state visibility, action clarity, long-session comfort, mobile/LAN usability, and visual consistency.

The goal is not to preserve the old look. The goal is to make Ava feel like a mature, coherent Agent Control Plane.
