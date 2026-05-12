# Chat Header 统一改造 + Context Lens 设计

- 状态：Draft for implementation review
- 日期：2026-05-11
- 作者：Brainstorming 结果（与用户共识）
- 影响范围：`console-ui/src/pages/ChatPage/`、`ava/console/routes/chat_routes.py`、`ava/console/services/chat_service.py`、`ava/console/services/context_preview_service.py`、`tests/console/*`、`tests/console_ui/*`

## 1. 背景与问题

当前 ChatPage 顶部存在两条横栏，语义重叠且部分控件**与真实后端行为不一致**：

1. **`ConversationConfigBar`**（`index.tsx:1195`，横跨 sidebar + MessageArea）
   - Agents 多选 pill
   - Context Size 进度条
   - 「压缩」按钮 + 「查看压缩后上下文」Modal
   - Scene chip

2. **`MessageArea` 内部的 Session header**（`MessageArea.tsx:310-410`）
   - 会话标题 / key 复制
   - 参与者头像 + 文本（**与 ConfigBar 的 agents pill 重复**）
   - Scene chip（**与 ConfigBar 重复**）
   - Conversation thread 状态
   - Token 统计跳转链接（⚡）
   - ConnectionBadge / Read-only badge
   - Refresh / Search / Context Inspector 按钮

### 1.1 信息层面的问题

- 参与者信息、Scene chip 在两条栏里重复出现。
- "Context 相关操作"被拆到两处：进度条 + 压缩按钮在 ConfigBar；Context Inspector 按钮在 Session header 右侧。
- ConfigBar 横跨 sidebar + MessageArea，sidebar 收起 / 移动端抽屉时视觉上脱离主内容。

### 1.2 概念层面的问题（更关键）

经核对 `ava/console/services/chat_service.py`、`ava/console/services/context_preview_service.py` 与外部 nanobot checkout 的 prompt 组装路径：

- **「压缩」是假动作**。`compress_context()` 拼一段 `"已压缩早期上下文：…"` 文本写入 `session_compressions` 表，**从不写回 history，也不被下一次推理读取**。`loop.context` 每次仍按滑窗自行组装 prompt。
- **`/context-size` 的数字不真实**。它用 DB 中 user/assistant 文本估算的 token，与真正发给 LLM 的 prompt 口径不同；上限硬编码 200K。
- **`/context-preview` 与真实 prompt 也不等价，但更接近**。当前 `context_preview_service.py:374` 直接 `session.get_history(max_messages=0)`；与之相对，nanobot 生产路径（`nanobot/agent/loop.py:529, 568`、`nanobot/agent/memory.py:404`、`nanobot/command/builtin.py:84`）写的也都是 `session.get_history(max_messages=0)`，**所以 preview 的 history 取数与生产 history replay 在调用层是一致的**——但生产路径还会再走 `ContextBuilder.build_messages()` 的 `_sanitize_history` 与 runner 的 `_snip_history()`（`nanobot/agent/runner.py:640`，按 `context_window_tokens - max_output - safety_buffer` 二次裁剪），preview 这两层都没走。
- **`session.get_history(max_messages=0)` 的真实语义**：`nanobot/session/manager.py:38-41` 的实现是 `unconsolidated = self.messages[self.last_consolidated:]`，再 `unconsolidated[-max_messages:]`；当 `max_messages=0` 时因为 Python `[-0:]` 等价 `[0:]`，结果是**整段 unconsolidated 历史**——既不是直觉中的"0 条"，也**不**包含 `last_consolidated` 之前已被合并的早期消息。它**不是稳定的 full-history API**；不能据此承诺"完整历史快照"。
- **现 ContextInspector** 已经读 `/context-preview`，所以它展示的也是上述"replay window 但未经 runner trim"的快照，不等同于"下一次请求实际发送的最终 messages"。
- 模型实际行为是**多层裁剪/治理后的滑窗**：history replay 取整段 unconsolidated，runner 再按上下文预算 snip。当前用户**没有可调旋钮**。

结论：不能把"假按钮包装得更漂亮"。要换一套诚实的心智模型，并且**分阶段交付**以避免一次性把多个不稳定假设压成单个 PR。

## 2. 目标

1. 合并两条横栏为单一 `ChatHeader`，定位在原 Session header 位置，**仅占 MessageArea 宽度**。
2. 把 CHAT_AGENTS 多选改为「选择+显示一体」的 dropdown。
3. **删除假压缩 UI**，UI 上对滑窗行为保持诚实。
4. ContextChip 数字源于 `/context-preview`；**弃用 `/context-size` 接口**。
5. 把"上下文相关操作"在 UI 上收成一个入口；Phase 1 复用现有 `ContextInspector` 抽屉，Phase 2 再上 `ContextLensDrawer` 三 tab。

## 3. 非目标（本期不做）

- **不**实现"用户可调滑窗形状"。
- **不**实现真摘要（auto-summarization）。
- **不**改变 nanobot `loop.context` 算法或 `_snip_history()` 行为。
- **不**改变默认 responder / routing 语义；Agents dropdown 只管 session participants 元数据。
- **不**把 `session.get_history(max_messages=0)` 当全量历史或真实 provider request 来源。
- **不**承诺 preview 等价于 provider request；preview 显式标注 `estimate_scope`，让前端知道这是 replay-window 前裁剪态。

## 4. Phase 划分（关键）

把原始 spec 拆成两阶段，避免一次性同时改后端 dry-run 等价逻辑与前端整套抽屉。

### Phase 1 —— 视觉收敛 + 诚实标签（本 spec 的实施范围）

只做"前端结构对齐 + 后端 preview 字段诚实化"，**不**引入 runner-equivalent dry-run、**不**新建 `ContextLensDrawer`。

前端：
- 新增 `ChatHeader.tsx`，合并原 `ConversationConfigBar` + `MessageArea` Session header。
- 新增 `AgentsDropdown.tsx`（选择+显示一体）。
- 新增 `ContextChip.tsx`：进度条 + 百分比 + hover 浮层；**点击直接挂载现有 `ContextInspector`**（行为不变，仅入口移位）。
- 删除 `ConversationConfigBar.tsx`、`MessageArea.tsx` 中旧 Session header 段、`CompressionDiffModal`（如已抽出）。
- 删除 `MessageArea.tsx` 中 Context Inspector 按钮入口（迁到 ContextChip 点击）。
- 同步重写 `tests/console_ui/test_linear_acceptance_checklists.py:253/877/895` 中关于 ConfigBar 的静态断言。

后端：
- `/context-preview`：保持当前 `session.get_history(max_messages=0)` 调用，**新增**少量字段诚实标注现状（见 §7.1）。
- `/context-size`：标注 deprecated，返回值切到基于 `/context-preview` 的 totals 子集；前端不再调用。
- `/compress`、`/compressions`：**完全不动**，保留兼容性。

### Phase 2 —— Context Lens 抽屉 + 后端 dry-run（不在本 spec 实施范围）

仅在本 spec 中做接口预留与字段保留，**不**写实施代码。Phase 2 拟做的工作：
- 新建 `ContextLensDrawer.tsx`，三 tab（Now Sending / Window / History）替代 `ContextInspector`。
- 评估能否在 Ava 侧实现 runner-equivalent 只读 helper（含 `_sanitize_history` + 等价 `_snip_history`），把 `/context-preview` 升级为更接近 provider request 的 dry-run。
- 引入 `dropped_messages` 精确列表（依赖稳定的全量历史 helper）。
- 处理 consolidated history 的展示与 token 计入策略。

Phase 2 触发条件、技术评估、字段最终形态在另一份 spec 中产出，不与 Phase 1 耦合。

## 5. 信息架构

### 5.1 `ChatHeader` 两行布局（桌面，Phase 1）

```
┌────────────────────────────────────────────────────────────────────────────┐
│  ☰  Session Title  📋    · Console  · Active thread       ●Live  RO  ⟳  🔍  │ Row 1
│  ──────────────────────────────────────────────────────────────────────── │
│  [🤖 Nanobot · Codex  (2) ▾]   [▰▰▰▰▱▱▱▱  38%  12.1K/32.0K  ▾]   ⚡ 128K · 4 calls ↗  │ Row 2
└────────────────────────────────────────────────────────────────────────────┘
```

- **Row 1** 高 ~28px：身份 + 全局工具。
  - 左：（移动端）汉堡 → 会话标题 → 复制 key → Scene chip → Thread 状态 chip
  - 右：`ConnectionBadge` → Read-only badge（条件显示）→ Refresh → Search
  - **删除原右侧的 Context Inspector 按钮**（移到 Row 2 的 ContextChip 点击行为）
- **Row 2** 高 ~36px：会话级控制带。
  - 左：Agents dropdown
  - 中：Context chip（Phase 1 点击挂载现有 `ContextInspector`；Phase 2 改为打开 Lens drawer）
  - 右：⚡ token 统计跳转链接（保留原 `buildTokenStatsNavUrl` 行为）

### 5.2 移动端紧凑形态（< md，Phase 1）

```
☰  Session Title  📋   …   [🤖 2 ▾]  [38% ▾]   ⋯
```

- Agents chip 仅显示数量徽标；点击展开 popover（与桌面同一组件，自适应宽度）。
- Context chip 仅显示百分比（颜色仍跟阈值）；**点击直接全屏挂载现有 `ContextInspector`**（Phase 2 再换成全屏 Lens sheet）。
- 删除现 ConfigBar 的"展开/收起"按钮（不再需要）。
- 右侧 `⋯` 改为**移动端 bottom sheet**（不是 dropdown 菜单），项目固定为：
  1. Refresh
  2. Search
  3. Token stats（跳转 `buildTokenStatsNavUrl`）
  4. Connection status（只读展示 `activeTransport` / `transportStatus`）
  5. Read-only state（只读展示 `isReadOnly` 来源）
- ContextChip **不进 `⋯`**——因为它的点击行为是打开 Inspector / Lens 全屏 sheet，自带二级界面，不应再被嵌进 overflow。

## 6. 组件拆分

### 6.1 Phase 1 新建 / 改动

```
ChatHeader.tsx                       新建（聚合 Row 1 + Row 2 + mobile bottom sheet）
  ├─ AgentsDropdown.tsx              新建（选择 + 显示一体）
  ├─ ContextChip.tsx                 新建（trigger，点击挂载现有 ContextInspector）
  └─ HeaderOverflowSheet.tsx         新建（仅移动端，bottom sheet，菜单项固定）
```

- `ContextInspector.tsx`（28K）**Phase 1 不拆分、不重写**——只是从 `MessageArea` 中按钮触发，改为从 `ContextChip` 点击触发。挂载位置允许从 `MessageArea` 提升到 `ChatHeader`，但 props / fetch / render / sanitize 行为保持不变。
- `ConversationConfigBar.tsx`：**整文件删除**；`index.tsx:1195` 引用同步移除。
- `MessageArea.tsx`：移除原 Session header 段（`MessageArea.tsx:310-410`），改为顶部挂载 `<ChatHeader />`；移除 Context Inspector 按钮与相关 state（`showInspector` 由 `ChatHeader` 接管）。
- 旧 `CompressionDiffModal`（内嵌在 `ConversationConfigBar.tsx:224-268`）随 ConfigBar 一起删除。

### 6.2 Phase 2 预留位置（不实施）

```
ContextLensDrawer.tsx                Phase 2 新建（替换 ContextInspector）
```

Phase 1 的 `ChatHeader` / `ContextChip` 设计要为 Phase 2 留一处单一切换点：把 ContextChip `onOpen` 从 "挂载 ContextInspector" 切换到 "打开 ContextLensDrawer"，**不需要重写 ChatHeader 本身**。

## 7. 关键交互

### 7.1 AgentsDropdown（Phase 1）

**Trigger（chip）**

| 选中状态 | 显示 |
| --- | --- |
| 0 个（fallback default） | `未指定（默认 Nanobot）` muted |
| 1 个 | 该 agent label，例：`Nanobot` |
| 2 个 | 完整列出，例：`Nanobot · Codex (2)` |
| ≥3 个 | 前两个 + `+N`，例：`Nanobot · Codex +1 (3)` |

**Popover 内容**

- 多选 checkbox 列表，按 `CHAT_AGENTS` 顺序。
- `session.default_responder_agent_id` 对应项加 `Default` 角标。
- 当尝试取消最后一个时禁用并提示 `至少保留 1 个参与者`。
- `isReadOnly` 时可打开查看，所有 checkbox disabled。
- 键盘：`↑↓` 切换焦点，`Space` 切换勾选，`Esc` 关闭。

**与现有 props 对接**：复用 `onParticipantsChange`（语义不变）。

**语义边界**

- Effective participants = `session.participants.length > 0 ? session.participants : [session.default_responder_agent_id || "nanobot"]`。
- 前端 `PATCH /chat/sessions/{consoleSessionId}` 只发送 `participants`，且不得发送空数组（沿用 `ConversationConfigBar.tsx:157` 的 `if (next.length > 0)` 守卫）。
- 后端继续用 `default_responder_agent_id` 决定普通消息路由；dropdown 只能**标注**默认项，不能改变默认 responder。
- 若后续要把 dropdown 变成 responder 选择器，必须另加后端字段和路由契约，不在本期实现。

### 7.2 ContextChip（Phase 1）

**显示**：`[ ▰▰▰▰▱▱▱▱  {percent}%  {used}/{budget}  ▾ ]`

**数据源**：`GET /chat/sessions/{sessionKey}/context-preview`（沿用现 endpoint，新增字段见 §8.1）。映射：

- `percent` = `totals.utilization_pct`
- `used` = `totals.request_total_tokens`
- `budget` = `totals.ctx_budget`

`sessionKey` 使用完整 key，例如 `console:abc123`；前端调用时继续 `encodeURIComponent(session.key)`。**不要**把 preview 的 key 规则和 legacy `/compressions` 的 `{consoleSessionId}` 混用——参见 §9.1 Key/ID 对照表。

**颜色阈值**（保留现配色语义）：

- `< 60%`：中性 `var(--success)`
- `60–85%`：`var(--warning)`，提示「窗口将开始裁剪历史」
- `> 85%`：`var(--danger)`，提示「prompt 已逼近 budget，runner 可能频繁裁剪」

**Hover 浮层**（mini breakdown，Phase 1）：

```
System        2.4K
Runtime       0.8K
Tools         3.1K
History       5.8K
─────────────────
Total        12.1K / 32.0K budget

ℹ Scope: replay window (pre-runner-trim). 不等价于 provider request。
```

最后一行 `Scope:` 文案直接来自 preview payload 的 `totals.estimate_scope`，避免前端硬编码而误导用户。如果 Phase 2 升级了 dry-run，scope 文案自动跟随后端字段变化。

**点击行为（Phase 1）**：打开当前 `ContextInspector` 全屏抽屉（桌面与移动端都是抽屉而非 drawer——保持现行为）。Phase 2 切到 Lens drawer 时只需替换 `onOpen` 实现。

**错误态**：preview 拿不到时显示 loading / error 占位，**不**回退到 `/context-size` 或 session token stats，避免再造数字漂移。

### 7.3 Context Lens drawer（Phase 2，仅占位）

Phase 1 不实施。详细 tab 结构、字段、数据来源在 Phase 2 spec 中产出。占位约束：

- Lens drawer 桌面态宽 ~520px、移动态全屏 sheet。
- ContextChip `onOpen` 是 Phase 1 → Phase 2 唯一切换点。
- 旧 `session_compressions` 表保留作为 Phase 2 History tab 的只读数据源。

### 7.4 删除路径（Phase 1）

- 删除 `console-ui/src/pages/ChatPage/ConversationConfigBar.tsx`。
- 删除 `index.tsx:1195` 的 `<ConversationConfigBar />` 引用与 import。
- 删除 `MessageArea.tsx:310-410` 的 Session header 段；`showInspector` state 与 `<ContextInspector />` 挂载点上移到 `ChatHeader`。
- 删除 `MessageArea.tsx` 顶部 Inspector 按钮（`MessageArea.tsx:401-408`）。
- 删除 `ConversationConfigBar.tsx:224-268` 的 `CompressionDiffModal` inline 实现。
- `POST /chat/sessions/{id}/compress` 路由保留 + 标注 deprecated；现有 `tests/console/test_chat_routes.py:373-392` 不动。

## 8. 后端改动

### 8.1 Phase 1 必做（小步）

1. **`/context-preview` 字段诚实化**（同 endpoint，向后兼容增量；**不**改 history 取数路径）：
   - **新增** `totals.estimate_scope: "replay_window_pre_trim"`（string 字面量；Phase 2 升级 dry-run 后会变更为 `"runner_equivalent"`）。
   - **新增** `window: { strategy: "auto", kept_count, dropped_count, kept_tokens, estimate_scope }`（必做字段仅四个数据点 + 一个 scope 标注）。
     - `kept_count` = 当前 preview history 的长度（即 `len(session.get_history(max_messages=0))`）。
     - `dropped_count` = `len(session.messages) - session.last_consolidated - kept_count`，**估算量**；如果该差值为负则置 0 并写日志。
     - `kept_tokens` = preview history 估算 tokens 合计（已存在的 `history_tokens` 同值，复用即可）。
     - `estimate_scope` 与 `totals.estimate_scope` 同值。
   - **可选字段**（Phase 1 后端如能廉价取到就返回；前端必须容忍缺失，不得依赖）：
     - `window.replay_max_messages`（当前生产 call site 写死 0，本期返回 `0` 或 `null` 均可）
     - `window.replay_max_tokens`（生产 call site 无此参数，应返回 `null`）
     - `window.runner_snipped`（Phase 1 不复现 runner trim，返回 `false` 或 `null`）
     - `window.consolidated_count`（仅当能稳定读 `session.last_consolidated` 时返回；否则省略）
     - `window.summary_present`（依赖 nanobot 内部 consolidation 状态，Phase 1 不保证；省略）
     - `window.oldest_kept_msg_id` / `oldest_dropped_msg_id`（依赖 message 有稳定 ID，Phase 1 不保证；省略）
   - **不**改 `totals.history_tokens` / `totals.request_total_tokens` 当前计算逻辑——Phase 1 它们仍是 preview history 的估算值，不声称等价 provider request；`estimate_scope` 字段就是用来标注这点。
   - **不**新增 `dropped_messages: [...]` 精确列表（依赖稳定全量历史 helper，Phase 2 做）。
   - **副作用约束**（即使 Phase 1 不改 history 取数）：preview 不能调用 provider、不能保存 session、不能触发 consolidate / auto-compact / background task、不能改 tool context 或 runtime checkpoint。这是 endpoint 的现状要求，Phase 1 加测试断言它依然成立。

2. **`/context-size` 弃用**：
   - 路由保留，返回 HTTP header `Deprecation: true` 与 `Sunset: <Phase 2 期内>`。
   - 实现切换到调用 `/context-preview` 拿 `totals` 子集（兼容旧字段名 `used_tokens / model_limit / breakdown`）；**不再**走原 DB 估算路径，避免两套数字漂移。
   - 前端不再调用（acceptance 9.2 卡这一条）。

3. **legacy compression 路由保持兼容**：
   - `POST /chat/sessions/{consoleSessionId}/compress`：保留现实现，前端不再调用。
   - `GET /chat/sessions/{consoleSessionId}/compressions`：保留，Phase 1 前端不读（Phase 2 History tab 用）。
   - 既有 `tests/console/test_chat_routes.py:373-392` 测试保留并通过；不能因为前端删除入口顺手删兼容测试。

### 8.2 Phase 2 后端工作（占位，不在本 spec 实施）

- 评估 runner-equivalent 只读 helper 的可行性（在 Ava 侧实现，避免改 upstream nanobot）。
- 若可行：升级 `/context-preview` 让 `totals` 反映 dry-run 后 provider request；`estimate_scope` 切到 `"runner_equivalent"`；引入精确 `dropped_messages` 列表。
- 若不可行：保留 Phase 1 命名，记录 ADR 说明为何不升级。

### 8.3 不做（本期）

- 不新增 `PUT /chat/sessions/{id}/window`。
- 不修改 nanobot `loop.context` / `_snip_history()`。
- 不动 `compress_context` 与 `session_compressions` 表（保留为 Phase 2 History tab 的数据源）。
- 不修改 `default_responder_agent_id` 更新协议。

## 9. 与现有 props / 接口的对接

| 现有 | Phase 1 处理 |
| --- | --- |
| `onParticipantsChange` | `AgentsDropdown` 直接复用 |
| `buildTokenStatsNavUrl` 跳转 | Row 2 ⚡ 链接保留；移动端进 bottom sheet |
| `ConnectionBadge` | Row 1 右侧保留；移动端进 bottom sheet 仅作只读状态展示 |
| `onToggleSessionPanel` | Row 1 移动端汉堡保留 |
| `onRefresh` / Search modal | Row 1 右侧保留；移动端进 bottom sheet |
| `isReadOnly` | Agents disabled；移动端 bottom sheet 展示 state |
| `isMobile` | 切到 §5.2 紧凑形态 |
| `ContextInspector` 旧入口 | 删除 `MessageArea` 中按钮；改由 `ChatHeader` 中 `ContextChip` 点击触发挂载 |

### 9.1 Key / ID 对照

| 用途 | 输入 |
| --- | --- |
| `/context-preview` | 完整 `session.key`，例如 `console:abc123` |
| `/context-size` deprecated | `consoleSessionId`，例如 `abc123` |
| `/compress` deprecated（前端不调） | `consoleSessionId` |
| `/compressions` (Phase 2 使用) | `consoleSessionId`，仅 `console:` session |
| `PATCH /sessions/{id}` participants | `consoleSessionId` |

## 10. 验收

### 10.1 Phase 1 验收（本期）

**视觉与交互**

- [ ] ChatHeader 两行布局在 ≥ md 宽度正常显示，元素不换行 / 不重叠。
- [ ] Agents dropdown 多选 + 显示规则正确（0/1/2/≥3 四种态）；readonly 时可打开但 disabled。
- [ ] Agents dropdown 不会发送空 `participants` 数组（守卫存在）。
- [ ] ContextChip 数字来源于 `/context-preview` 的 `totals`，颜色阈值正确（< 60% / 60-85% / > 85%）。
- [ ] ContextChip hover 浮层展示 mini breakdown + `Scope:` 文案（来自后端 `totals.estimate_scope`，非前端硬编码）。
- [ ] ContextChip 点击挂载现有 `ContextInspector` 抽屉，**行为与之前 Inspector 按钮触发等价**（同样的 fetch / render / sanitize / reveal / 折叠 / 分段复制能力）。
- [ ] 移动端 ChatHeader 单行紧凑形态显示正确。
- [ ] 移动端 `⋯` 触发 bottom sheet，菜单项顺序与文案符合 §5.2（Refresh / Search / Token stats / Connection status / Read-only state）。
- [ ] 移动端 ContextChip 不在 bottom sheet 中。

**功能**

- [ ] `ConversationConfigBar.tsx` 已删除，无任何 import 残留。
- [ ] `MessageArea.tsx` 中原 Session header 段已移除；`<ChatHeader />` 由 `MessageArea` 顶部挂载。
- [ ] `MessageArea.tsx` 中 Inspector 按钮已删除；`showInspector` state 改由 `ChatHeader` 管理。
- [ ] `CompressionDiffModal` inline 实现已随 ConfigBar 一同删除。
- [ ] 前端无任何 `/context-size` 调用。
- [ ] `/context-preview` 响应中 `totals.estimate_scope` 与 `window.{kept_count, dropped_count, kept_tokens, estimate_scope}` 必做字段齐全；可选字段缺失时前端不崩。
- [ ] Agents dropdown 仅 `PATCH participants`，不修改 `default_responder_agent_id`。
- [ ] `tests/console_ui/test_linear_acceptance_checklists.py:253/877/895` 已改写：不再读取 `ConversationConfigBar.tsx`，新增对 `ChatHeader.tsx` / `AgentsDropdown.tsx` / `ContextChip.tsx` 的静态断言。

**回归**

- [ ] 现有 `ContextInspector` 抽屉的能力（分段复制 / 展开完整内容 / 脱敏 reveal / 折叠 / 全屏）从 ContextChip 入口完全可达。
- [ ] Token 统计 ⚡ 跳转、ConnectionBadge 状态、Refresh、Search 功能行为不变。
- [ ] `tests/console/test_chat_routes.py:373-392` 的 `/compress` 测试仍然通过。
- [ ] `/context-size` 后端响应仍可被旧客户端解析（旧字段名兼容）；附 `Deprecation` header。
- [ ] 新增 `tests/console/test_context_preview.py` 用例：preview 调用不写 session、不触发 consolidate、不改 runtime checkpoint。
- [ ] 新增前端测试：ContextChip 在 preview 返回 error 时不回退到 `/context-size` 或 session token stats。

### 10.2 Phase 2 验收（占位，不在本 spec）

- [ ] `ContextLensDrawer` 三 tab 完整实施（Now Sending / Window / History）。
- [ ] `/context-preview` 是否升级到 runner-equivalent dry-run；如升级，`estimate_scope` 切到 `"runner_equivalent"`。
- [ ] `dropped_messages` 精确列表与 consolidated 历史的展示策略。
- [ ] ContextChip `onOpen` 从挂载 Inspector 切换到打开 Lens drawer。
- [ ] `/context-size` 路由从 deprecated 进入 sunset。

## 11. 开放问题

1. Phase 1 `window.dropped_count` 是估算值（基于 `len(session.messages) - last_consolidated - kept_count`）；如果该值在 nanobot 不同实现下不稳定，是否退到只返回 `kept_count` 而不报 dropped？— 建议先返回，前端只用作"是否提示"的开关；不展示精确数字。
2. Phase 2 runner-equivalent dry-run 是否需要把 `_snip_history` 复制到 Ava 侧（接受漂移风险），还是争取在 nanobot 暴露稳定的 public helper？— Phase 2 spec 决策。
3. 移动端 bottom sheet 的实现复用哪个组件库 / pattern？— 可选 Headless UI、自写、或继承现有 `SearchModal` 全屏样式；属于实施细节，不影响本 spec。

## 12. 后续（非本 spec）

- Phase 2 `ContextLensDrawer` + 后端 dry-run 升级（独立 spec）。
- 可调滑窗（`PUT /chat/sessions/{id}/window`、`loop.context` plumbing）。
- Auto-summarization 与 `session_compressions` 联动。
- `/context-size` 从 deprecated 进入彻底删除。
