# Ava Console UI 自查清单

> 用途：给后续 agent 一份「打开浏览器→截图→对照 DESIGN.md→打分」的可操作脚本。
>
> 范围限定：
> - 仅覆盖**匿名 / 普通用户视图**。`admin`/`mock_tester` 专属页面只列入口、不展开内容。
> - 仅做**视觉与交互**自查（DESIGN.md v0.4.3-B「Warm Operations Cockpit」），不审后端契约、不审枚举表。
> - 默认 desktop = 1280×800，mobile = 390×844。除非另注，所有截图都拍这两档。

---

## 0. Agent 自查工作流

### 0.1 启动环境

```bash
cd console-ui
rtk pnpm install                # 第一次运行
rtk pnpm dev                    # 默认 http://localhost:5173
```

后端如果没起来，仅 `/login`、`/lan/pair` 可用；其他路由会卡在 `Loading...`。先确认 `/login` 能进。

### 0.2 登录 / 切角色

- 普通用户：用 `viewer` 或 `editor` 账号。完整自查范围用 `viewer` 即可。
- 不要用 `mock_tester`（会出现 `MOCK SANDBOX` 提示带，污染截图基线）。
- 登录态拿到后，截图工具优先走 **`playwright-cdp` MCP**（extension 模式连日常 Chrome），免重复登录。

### 0.3 截图协议

每个条目至少跑两次：

| 视口 | 尺寸 | 触发的布局 |
|------|------|-----------|
| desktop | 1280×800 | TopBar + 主内容 + TaskFloater |
| mobile | 390×844 | MobileBottomNav + 主内容 + TaskFloater |

主题轮换：先 dark（默认），再 light（`<html class="light">`）。命名建议 `.audit/<route-slug>-<viewport>-<theme>.png`。

### 0.4 对照 DESIGN.md 的硬点位

每张截图按下面 6 条逐项打勾：

1. **背景层级**：canvas（最深）→ surface（卡片）→ raised（hover/popover）。不允许出现纯黑或与 token 不一致的灰。
2. **语义色**：6 种 kind（primary / running / success / queued / warning / danger）只能取 `--ava-*` 变量；任何 `bg-blue-500`、`text-emerald-400`、Tailwind 原生色都判失败。
3. **状态徽章**：状态点/Pill 必须经过 `StatusBadge` 或 `chipClass`，颜色 = `{kind-soft, kind-border, kind}`。出现裸色（`bg-[var(--ava-success)] text-white`）就记一条差异。
4. **边框优先**：分隔依靠 `1px solid var(--ava-border)`；阴影**只**在浮层（drawer/popover/floater）出现，卡片不应带 shadow。
5. **TopBar-first**：桌面主操作沉淀在 TopBar；左侧不能再出现持久竖向导航条。
6. **动效**：过渡走 `--ava-motion-normal` × `--ava-ease-standard`；遵守 `prefers-reduced-motion`。

### 0.5 报告格式

每个条目产出一行：

```
[路由] [视口] [主题] PASS|FAIL  备注
```

`FAIL` 必须附 1) 截图路径 2) 违反的 DESIGN 硬点位编号 3) 文件:行 推断（如 `MediaPage.tsx:301`）。

### 0.6 自动化入口

`console-ui/e2e/ui-audit.mjs`（见本目录同名脚本）会读 §1-§3 的路由表自动遍历截图。手动看 §4 的浮层/弹窗。

---

## 1. 全局外壳（每页都要看）

### 1.1 桌面 TopBar — `components/layout/TopBar.tsx`

- **进入路径**：登录后任意路由。
- **元素清单**：
  - 左：AVA logo + （仅 mock_tester）`MOCK SANDBOX` pill。
  - 中-左：导航链接（Chat `/`、Settings `/settings`）。激活态 `bg-[var(--accent)] text-white`。
  - 中：`TaskPreviewBar`（`density="topbar"`）。无任务时占位透明。
  - 右：`AvatarMenu`（头像下拉）。
- **要看的状态**：
  - 默认 / hover / active 三态 navlink。
  - TaskPreviewBar 有任务（running/queued/success/danger）时，胶囊配色取 `--ava-{kind}-soft/-border/{kind}`。
  - AvatarMenu 展开时是 popover（drawer 阴影 `--ava-shadow-popover`）。

### 1.2 移动 BottomNav — `components/layout/Layout.tsx:13-59`

- **进入路径**：viewport ≤ md。
- **要看**：
  - 横向可滚 nav，激活项颜色 `var(--accent)`，文字加粗。
  - `safe-area-inset-bottom` padding 是否生效（iPhone 模型截图带刘海）。
  - 滚动条是否被 `scrollbar-none` 隐藏。

### 1.3 BootstrapBanner

- **进入路径**：全局。后端 bootstrap 异常时出现。
- **要看**：banner 配色应为 warning 或 danger soft 系列；横贯顶部，不应阻塞布局。

### 1.4 TaskFloater — `components/tasks/TaskFloater.tsx`

- **触发**：TopBar TaskPreviewBar 点击任意任务，或 ChatPage 内消息块的「在浮层打开」。
- **要看**：
  - 桌面：右下角浮层，阴影 `--ava-shadow-floater`，圆角 `--ava-radius-xl`。
  - 移动：底部贴边卡片，进入动画 `animate-task-overlay-in`。
  - 顶部状态条颜色严格按 `StatusKind → StatusTone` 对照表。

### 1.5 AvatarMenu

- **触发**：点击右上头像。
- **要看**：菜单项 hover 背景 `--bg-tertiary`；分隔线 1px border；签出按钮 danger 文字色 `var(--ava-danger)`。

---

## 2. 一级路由

### 2.1 `/login` — `pages/LoginPage.tsx`

- **进入路径**：未登录直接打开根域名。
- **功能**：账号密码登录；后端未启动时显示连接错误。
- **关键操作**：
  - 输入用户名/密码 → 提交 → 跳 `/`。
  - 错误密码 → toast/inline error。
- **截图视口**：desktop + mobile，dark + light。
- **语义状态对照**：错误提示走 `--ava-danger-soft` + `--ava-danger-border` + `--ava-danger`。

### 2.2 `/lan/pair` — `pages/MobilePairPage.tsx`

- **进入路径**：移动端二维码扫描配对。`Suspense` 懒加载。
- **范围标记**：移动端单页，仅在专项任务时自查。

### 2.3 `/` — ChatPage（**核心页面，按交互单元拆**）

入口组件 `pages/ChatPage/index.tsx`。它是「聊天 + 任务列表 + 媒体浏览」三合一的容器，由 `?view=` query 切换：

| view query | 实际显示 | 备注 |
|------------|----------|------|
| 缺省 | 聊天会话视图 | 默认 |
| `?view=tasks` | BgTasksPage 列表/详情 | 替代旧 `/bg-tasks` `/tasks` |
| `?view=media&task_id=…` | MediaPage 媒体浏览 | 替代旧 `/media` |

每种 view 都按下面的子条目独立拍。

#### 2.3.a ChatPage 默认聊天视图

- **进入**：登录后默认页 `/`。
- **截图视口**：desktop + mobile，两套主题。

子组件清单（每个都要单独检查）：

##### 2.3.a.1 ChatHeader — `pages/ChatPage/ChatHeader.tsx`

- 元素：会话标题、`AgentsDropdown`、`ConnectionBadge`、搜索按钮（→ SearchModal）、ContextLens 入口、HeaderOverflowSheet（移动端 ⋯）。
- 关键操作：
  - 点 AgentsDropdown → 弹 popover 列出 agents。
  - 点搜索图标 → SearchModal 打开。
  - 点 ContextLens 图标 → ContextLensDrawer 从右侧滑入。
  - 移动端点 ⋯ → HeaderOverflowSheet 底部弹起。
- 语义点：`ConnectionBadge` 颜色（在线 success / 离线 danger / 重连 running）必须用 `--ava-{kind}` token。

##### 2.3.a.2 HudBar — `pages/ChatPage/HudBar.tsx`

- 元素：4 颗 chip（Token / Skills / Artifacts / Memory）。`chipClass()` 决定外观（line 31-33）。
- 关键操作：每颗 chip 点击 → 对应 popover（TokenInfoPopover 等）。
- 语义点：chip 应该是「surface 底色 + border + 文字 muted」，不应有阴影；激活态用 `--ava-primary-soft`。

##### 2.3.a.3 SessionSidebar — `pages/ChatPage/SessionSidebar.tsx`

- 触发：桌面常驻左侧（如启用），移动端走 drawer。
- 关键操作：切换会话、新建会话、删除会话（确认弹窗）。
- 语义点：当前会话项背景 `--bg-tertiary`，未读小红点 `--ava-danger`。

##### 2.3.a.4 MessageArea + TurnGroup + MessageBubble + ChainBubble

- 元素：用户气泡、Assistant 气泡、ToolCallBlock、SubagentResultBlock、BackgroundTaskResultBlock、InFlightTurnBlock、ConversationTaskCard、ImageCarousel、ContextChip。
- 关键操作：
  - hover 气泡 → 操作条出现（复制、重发、查看 trace）。
  - 点 ToolCallBlock 折叠/展开。
  - 点附在消息上的 BackgroundTaskResultBlock → TaskFloater 打开。
- 语义点：
  - Tool 状态 pill（running/success/error）只允许走 StatusBadge。
  - InFlightTurnBlock 的「思考中」动画应该是 idle / running 色。
  - 不允许 `bg-blue-*` 或 `text-emerald-*` 出现在气泡内。

##### 2.3.a.5 ChatInput + InputActionMenu — `pages/ChatPage/ChatInput.tsx`

- 元素：多行 textarea、发送按钮、附件入口、`InputActionMenu`（语音/工具切换/Agent 切换）。
- 关键操作：
  - Enter / Shift+Enter 行为正确。
  - 附件拖拽进入。
  - InputActionMenu 弹起 → 项目 hover 背景 `--bg-tertiary`。
- 语义点：发送按钮 = primary（`--ava-primary` / hover `--ava-primary-hover`）；禁用态置灰，不要变红。

##### 2.3.a.6 SearchModal — `pages/ChatPage/SearchModal.tsx`

- 触发：ChatHeader 搜索图标 / Cmd+K。
- 关键操作：键入 → 实时筛选会话/消息；上下方向键选中；Enter 跳转。
- 截图：modal 居中浮层，背景 `--ava-bg-surface`，阴影 `--ava-shadow-floater`。

##### 2.3.a.7 ContextLensDrawer — `pages/ChatPage/ContextLensDrawer.tsx`

- 触发：ChatHeader 上下文图标。
- 元素：右侧抽屉，列出当前 turn 的引用 / artifact / 工作目录 / 可见上下文。
- 截图：drawer 1/3 屏宽，左边 1px border，无遮罩或者半透明黑遮罩 `bg-black/45`。
- 语义点：内部状态 chip 同样走 `--ava-{kind}-soft`。

##### 2.3.a.8 HeaderOverflowSheet — `pages/ChatPage/HeaderOverflowSheet.tsx`

- 触发：移动端 ChatHeader ⋯。
- 截图：底部弹起，圆角顶部，进入动画 `animate-slide-in-bottom`。

#### 2.3.b ChatPage `?view=tasks`（旧 BgTasksPage） — `pages/BgTasksPage.tsx`

- **进入**：TopBar TaskPreviewBar「查看全部」/ ChatPage 任务消息「在列表打开」/ URL 带 `?view=tasks`。
- **元素**：
  - `FilterBar`（按 workspace/状态/时间筛选）。
  - workspace 分组（`groupByWorkspace`）。
  - 每行 `TaskStatusBadge`（line 230，已用 StatusBadge 包装）。
  - 详情面板（点行后右侧滑出）。
- **关键操作**：
  - 切换筛选 → 列表实时刷新。
  - 点行 → 详情面板出，URL 带 `task_id`。
  - 详情面板内「在浮层打开」→ TaskFloater。
  - 重试 / 取消 / 删除（仅 admin 可见）。
- **语义状态对照**：
  - 12 种 StatusKind 必须落到 6 种 StatusTone 配色，不允许出现裸色。
  - 列表行 hover 背景 `--bg-tertiary`/30。

#### 2.3.c ChatPage `?view=media&task_id=…`（旧 MediaPage） — `pages/MediaPage.tsx`

- **进入**：BgTasks 详情中点击媒体附件 / URL 直达。
- **元素**：左侧文件树、右侧预览（图/视频/文本/PDF）、底部状态栏。
- **关键操作**：上下键切换文件、空格预览、点缩略图切大图、关闭返回。
- **已知差异**（DESIGN review 已记录）：
  - `bg-[var(--success)]/10`（line 301）—— 应改 `--ava-success-soft`。
  - 状态 span（line 449-451）裸色，应替换为 StatusBadge。
- 自查时需重点确认这两处是否仍存在。

### 2.4 `/settings/*` — Settings 双栏布局

- **进入**：TopBar → Settings 链接。
- **桌面布局**：左纵向树（`SettingsPage.tsx` `settingsTree`），右内容区。
- **移动布局**：单列，二级抽屉。

#### 2.4.1 settingsTree 路由（普通用户可见的部分）

| 路由 | 子项 | 组件 | 普通用户可见？ |
|------|------|------|----------------|
| `/settings/agents-config` | Overview | AgentDashboardPage | ✅ |
| `/settings/agents-config/nanobot` | Config / Memory / Persona | ConfigPage / MemoryPage / PersonaPage | ✅ |
| `/settings/agents-config/codex/config` | – | ConfigPage(codex) | ✅ |
| `/settings/agents-config/claude-code/config` | – | ConfigPage(claude_code) | ✅ |
| `/settings/agents-config/image-gen/config` | – | ConfigPage(image_gen) | ✅ |
| `/settings/statistics` | – | TokenStatsPage | ✅ |
| `/settings/tools/skills` | – | SkillsPage | ✅ |
| `/settings/users` | – | UsersPage | ❌（admin） |
| `/settings/system/gateway` | – | DashboardPage | ✅ |
| `/settings/system/desktop` | – | DesktopSettingsPage | ❌（admin） |
| `/settings/system/lan-access` | – | LanAccessPage | ❌（admin） |
| `/settings/system/browser` | – | BrowserPage | ✅（editor/viewer 可看） |
| `/settings/system/console` | – | ConfigPage(console) | ✅ |
| `/settings/system/version` | – | SettingsVersionPage | ✅ |

后续条目按这张表逐项拍。

#### 2.4.2 SettingsPage 自身外壳

- **要看**：左树激活态背景 `--bg-tertiary`、字体加粗；树折叠/展开动画；移动端二级抽屉滑入。
- **截图**：desktop 默认进入 `agents-config`；mobile 默认看根 settings 列表。

#### 2.4.3 AgentDashboardPage — `/settings/agents-config[/agentKind]`

- 元素：agent 卡片网格、每张卡显示状态（idle/running/error）、版本、路径、配置入口。
- 关键操作：点卡片 → 跳子配置；点状态徽章 → tooltip。
- 语义点：状态徽章必须 StatusBadge；卡片之间用 border 不用 shadow。

#### 2.4.4 ConfigPage — Nanobot/Codex/Claude Code/Image Gen/Console

- 元素：表单、字段分组、保存按钮、reset 按钮。
- 关键操作：
  - 改字段 → 显示「未保存」提示。
  - 保存 → success toast 或 inline 成功状态。
  - 失败 → danger inline。
- 语义点：保存按钮 = primary；"未保存"提示 = warning soft。

#### 2.4.5 MemoryPage — `/settings/agents-config/nanobot/memory`

- 元素：记忆条目列表、新增/编辑模态。
- 关键操作：CRUD 记忆条目；过滤搜索。
- 语义点：条目卡片 surface 底色 + border；删除按钮 danger 文字。

#### 2.4.6 PersonaPage

- 元素：人格 markdown 编辑器；预览。
- 关键操作：切换编辑/预览；保存。

#### 2.4.7 TokenStatsPage — `/settings/statistics`

- 元素：折线图、按模型分组的柱状图、表格、时间筛选。
- 关键操作：切时间范围；切模型筛选；点行 → trace drawer（TraceTimelineDrawer）。
- 语义点：图表配色严格按 6 色 token，**不允许 d3/recharts 默认色**；TraceTimelineDrawer 内部 status pill（line 202-204）当前是 inline，仍属差异。

#### 2.4.8 SkillsPage — `/settings/tools/skills`

- 元素：skill 列表、搜索、详情侧栏。
- 关键操作：启用/禁用 skill；查看详情；权限级别徽章。
- 语义点：徽章颜色按 kind 落 token。

#### 2.4.9 BrowserPage — `/settings/system/browser`

- 元素：浏览器实例列表、连接状态、操作按钮（拍快照、关闭、重启）。
- 语义点：连接状态徽章；操作按钮组对齐。

#### 2.4.10 DashboardPage — `/settings/system/gateway`

- 元素：Gateway 总览、连通性、流量统计。
- 语义点：状态卡片用 surface + border；指标数字字号一致。

#### 2.4.11 SettingsVersionPage — `/settings/system/version`

- 元素：当前版本、检查更新、changelog 链接。

---

## 3. 全局浮层 / 弹窗（不是路由，但要单独列）

### 3.1 TraceTimelineDrawer — `components/TraceTimelineDrawer.tsx`

- **触发**：TokenStatsPage 行点击 / 任务详情「查看 trace」。
- **要看**：
  - 整屏右侧抽屉，宽 max-w-5xl；遮罩 `bg-black/45`。
  - 时间瀑布图：colour bar 走 `--ava-{kind}` token。
  - **已知差异**：右上 status pill 是 inline `bg-[var(--ava-{kind})] text-white`（line 202-204），未走 StatusBadge。

### 3.2 TaskFloater 详情视图

- 同 §1.4，但要拍「展开内嵌的工具调用列表」「错误堆栈」状态。

### 3.3 SearchModal / ContextLensDrawer / HeaderOverflowSheet

- 同 §2.3.a 的子条目，单独拍 modal/drawer 自身的居中、阴影、遮罩。

### 3.4 Toast / Inline alert

- 触发：保存失败、网络断连、权限不足。
- 语义点：
  - success toast `--ava-success-soft` 底 + `--ava-success-border` + `--ava-success` 文字。
  - danger 同形态。
  - **不允许** `bg-green-500` `text-red-500`。

---

## 4. Legacy 路由重定向

`router/redirect-matrix.ts` 列了 0.3.0 之后会移除的路由：

| from | to | 备注 |
|------|----|------|
| `/agents` | `/settings/agents-config` | |
| `/config` | `/settings/system/console` | |
| `/memory` | `/settings/agents-config/nanobot/memory` | |
| `/persona` | `/settings/agents-config/nanobot/persona` | |
| `/skills` | `/settings/tools/skills` | |
| `/media` | `/?view=media&task_id=…` | |
| `/chat` | `/`（renameParams: session_key→session_id） | |
| `/tasks` | `/?view=tasks` | |
| `/bg-tasks` | `/?view=tasks` | |

自查项：直接访问每个旧路由，应**立刻 replace** 到新路由，URL 在地址栏完成替换；不应短暂闪现旧页面再跳转。

---

## 5. 跨页面通用回归点

| 编号 | 回归点 | 检查方式 |
|------|--------|----------|
| R-1 | 主题切换不重渲整页 | 切换 `<html class="light">` → 看 body transition 平滑 |
| R-2 | CJK line-height 1.8 | 设 `<html lang="zh">`，看消息气泡内行距比 en 文本宽 |
| R-3 | reduced-motion | DevTools 模拟 → 所有动画时长 = 1ms |
| R-4 | scrollbar 自定义样式 | 任意长列表，滚动条 6px、`--bg-tertiary` 颜色 |
| R-5 | safe-area inset | iPhone 模拟器，BottomNav 与 ChatInput 不被 home indicator 遮 |
| R-6 | Tailwind 残留色搜索 | `rtk grep -nE "bg-(blue|red|green|emerald|sky|amber|rose|indigo)-[0-9]" console-ui/src` 应只命中已知差异点 |

---

## 6. 已知差异（DESIGN review 留档，自查时确认是否仍在）

| 文件 | 行 | 问题 | 建议改法 |
|------|----|------|---------|
| `components/TraceTimelineDrawer.tsx` | ~13-25, 202-204 | status pill 走 `bg-[var(--ava-{kind})] text-white`，未走 StatusBadge / 未用 soft+border 三段 | 替换为 `StatusBadge` 或手写 `bg-[var(--ava-{kind}-soft)] border-[var(--ava-{kind}-border)] text-[var(--ava-{kind})]` |
| `pages/MediaPage.tsx` | 301 | `bg-[var(--success)]/10` —— 走的是 alias 不是 soft token | 改 `bg-[var(--ava-success-soft)]` |
| `pages/MediaPage.tsx` | 449-451 | 状态 span 裸色 | 包 StatusBadge |
| `pages/UsersPage.tsx` | （admin 专属，匿名自查跳过） | 角色徽章未走 StatusBadge | 后续单独审 admin 视图 |

每轮自查若发现新差异，按上表追加一行（含截图路径）。
