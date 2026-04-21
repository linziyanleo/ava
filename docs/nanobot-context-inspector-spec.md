# Task Spec — Nanobot WebUI Context Inspector

- **Status**: Draft v2.2 (Codex 三轮评审后修订，待审批)
- **Owner**: 待指派
- **Target repo**: `/Users/fanghu/Documents/Test/nanobot/`
- **Source of truth**: `observed sibling /Users/fanghu/Documents/Test/nanobot HEAD=68466b1c2a6d6d166f8042d6ed82e4925f51f09a`
- **Created**: 2026-04-21  |  **Revised**: 2026-04-21 (v2.2)
- **Related**: webui thread header 抽屉（当前不存在，新建）;webui 采用单 `Shell` 组件结构（`webui/src/App.tsx:150`），不存在多路由/多"页"概念，故全文不使用"Token 页"表述

---

## 0. 背景与问题

用户希望在 nanobot webui 实时看到：
> 除当前输入 prompt 外，本次请求如果发送，实际会拼给 LLM 的完整系统提示词 + 历史消息，以及它们合计会消耗多少 token。并且希望当底层 md 文件（AGENTS.md / SOUL.md 等）被修改后，预览能够**实时**更新。

**范围声明（Idle Baseline + 排除当前 Prompt）**：本功能预览的是——**"在用户_尚未_键入下一条消息的前提下，已锁定下发的上下文组件（system prompt + memory + skills + runtime metadata + 历史 + tools schema）及其 token 花费"**。明确两条边界：

1. **不含当前 prompt**：preview 的 `messages` 字段 = `session.get_history(max_messages=0)` 原样（经同步的过滤/对齐），**不合成 placeholder user message**、**不复刻 `build_messages()` 末尾把 runtime_context 合并到末尾 user 消息/新增 user 消息的步骤**。`totals.request_total_tokens` 不包含用户下次输入的 prompt token——这是本 spec 反复强调的产品目标"除当前输入 prompt 外"。
2. **不含 in-flight 中途注入**：runtime 会通过 `_pending_queues`（`nanobot/agent/loop.py:395-420` `_drain_pending`）在已执行的 turn 中途注入 follow-up 消息，此类中途状态不纳入契约。API 响应需显式返回 `scope: "idle_baseline"` 字段；若目标 session 正在执行，附加 `in_flight: true` 并仍回空闲基线快照（不模拟 mid-turn）。

**关于 `runtime_context` 的语义澄清（v2.2 明确）**：`runtime_context` 段**独立**展示其 content 与 token 数；UI 需向用户说明"下次你发消息时，这段内容将按 `build_messages()` 规则合并到你的消息开头或作为独立 user 消息注入"——这是产品层的说明，**不**在 preview 结构中预合成该步骤。

## 1. 可行性结论

**技术可行，工作量中等（约 4-6 人日）。**

**可直接复用的既有能力**（来自源码核查）：
| 能力 | 位置 | 说明 |
|---|---|---|
| System prompt 拼接 | `nanobot/agent/context.py:30-63` `ContextBuilder.build_system_prompt()` | 6 个分量顺序拼接，每次调用都重读磁盘 |
| Runtime context 注入 | `nanobot/agent/context.py:80-90` `_build_runtime_context()` | 在 `build_messages()` 第 141 行被调用，注入到最末 user 消息 |
| 历史过滤/对齐 | `nanobot/session/manager.py:39-62` `Session.get_history()` | 对齐 user turn 边界、删除孤立 tool_result。**运行时调用点均传 `max_messages=0`（全量）**——见 `loop.py:731` 与 `memory.py:426`；preview 必须沿用此参数而非 500，否则破坏"UI 快照 == 实际发送"契约 |
| 同角色消息合并 | `nanobot/agent/context.py:154-159` | `build_messages()` 末尾逻辑 |
| Token 估算 | `nanobot/utils/helpers.py:288-390` `estimate_prompt_tokens` / `estimate_prompt_tokens_chain` | tiktoken cl100k_base，本地运行。**签名含 `tools` 参数**；runtime 调用（`loop.py:423-425` 把 `tools=self.tools` 传给 runner；`runner.py:576,916` 实际下发时调 `spec.tools.get_definitions()`）会将工具 JSON schema 一并计入 |
| Tool 定义源头 | `nanobot/agent/tools/registry.py:48` `ToolRegistry.get_definitions()` | **唯一真实源**。`AgentLoop.__init__` 持有 `self.tools: ToolRegistry`；`loop.py:237` 把 `self.tools.get_definitions` 作为 callable 传给 `Consolidator`，后者仅在内部命名为 `_get_tool_definitions`。**preview 必须从 `agent_loop.tools.get_definitions()` 取**，不得调用任何 `provider._get_tool_definitions()`（该方法不存在） |
| 预算公式 | `nanobot/utils/helpers.py:423-424` | `ctx_budget = context_window - max_completion_tokens - 1024`（_SAFETY_BUFFER）。utilization% 必须按 `request_total / ctx_budget` 计算，与 `/status` 口径一致，否则面板百分比与真实压缩阈值不符 |
| Consolidation | `nanobot/agent/memory.py:346-510` `Consolidator` | 运行时可能改变 session 历史长度 |
| Pending 中途注入 | `nanobot/agent/loop.py:395-420` `_drain_pending` + `loop.py:480-499` `_pending_queues` | turn 执行期间同 session 的后续消息会被注入，改变实际发送内容。**本期 preview 不覆盖此情景**（见 §3 Scope） |
| REST 扩展点 | `nanobot/channels/websocket.py:432-458` `_dispatch_http` | 现有 `/api/sessions` / `/api/sessions/{k}/messages` / `/api/sessions/{k}/delete` |
| WS 事件广播 | `nanobot/channels/websocket.py` 订阅字典 | 现有事件 `ready / attached / message / delta / stream_end / error` |
| Event bus | `nanobot/bus/` | 仅渠道↔Agent，可扩展内部事件 |

**缺口**：
1. 没有"获取预览上下文"的 API 端点。
2. 没有 md 文件监听，因此虽然每次 `build_system_prompt()` 都会重读磁盘（**事实上已是被动热加载**），但 UI 无法被动得知"该刷新了"。
3. webui 没有 Token 面板，需新建。

## 2. md 实时更新可行性与方案

**结论**：可以做到实时更新，但"实时"有两档：

### 方案 A —「拉取式」（被动热加载 + 轮询/按需刷新）
- 不改 `ContextBuilder`：由于每次调用 `build_system_prompt()` 都直接 `read_text` md 文件，只要前端定时（或用户打开面板、切换 session 时）调一次 preview API，就能拿到最新内容。
- 前端 **不需要** 订阅文件变更；可用 SWR/polling（建议 3-5 s，仅面板可见时）。
- 优点：零新增依赖、零文件系统风险、实现最小。
- 缺点：用户改 md 后要等下一次 tick，不是"改完立刻亮"。

### 方案 B —「推送式」（文件监听 + WebSocket 广播）
- 新增 `watchfiles>=0.21` 依赖，在 `nanobot/watchers/context_sources.py` 中用 `awatch()` 异步监听。
- 监听范围（**按 workspace 逐个注册**，避免跨租户泄漏）：
  - `{workspace}/AGENTS.md`, `SOUL.md`, `USER.md`, `TOOLS.md`
  - `{workspace}/memory/MEMORY.md`
  - `{workspace}/skills/*/SKILL.md`
  - `nanobot/templates/agent/*.md`（包内模板，改动少，可选）
- 变更触发 `ContextSourcesChangedEvent(workspace, paths, at)` 进入 bus，WebSocket fan-out 到订阅该 workspace 的连接（**不是按 chat_id**）。
- 前端收到后 debounce 300 ms 重新调 preview API。
- 优点：改完即亮，所见即所发。
- 缺点：新增依赖 + fan-out routing 要正确（见 §5 风险 6）。

**推荐**：**一期先做方案 A，二期加方案 B。** 方案 A 在用户主动切面板/切 session 时体验已足够"实时"，且零风险；方案 B 是后续增量。本 spec 两段都给出，默认落地 A；B 设为 Open Question。

## 3. 作用域

### In Scope
1. 新增后端 `/api/sessions/{key}/context-preview` 端点，返回结构化上下文快照 + token 细分。
2. `ContextBuilder`（`nanobot/agent/context.py`）仅做**非侵入抽取**——把现有 `build_system_prompt` 内部 parts 数组抽成私有 `_build_system_parts() -> list[SystemSection]`，行为不变。
3. **新建** `nanobot/agent/context_preview.py`：承载 preview dataclasses（`ContextPreview / SystemSection / MessagePreview / ToolsPreview / Totals`）与 `build_context_preview()` 主函数。**preview 按分段独立构建（system + runtime_context + history + tools），不调用 `build_messages()`，不注入任何 placeholder user message**（见 §1 范围声明）。
4. **新建** `nanobot/agent/runtime_inspector.py`：轻量 facade `RuntimeInspector`，持有 `AgentLoop` 引用，对 WebSocket/HTTP 层暴露按 `session_key` 反查 runtime 三元组（context_builder / provider / model / tools / context_window / max_completion_tokens / in_flight）的只读接口——解决端点层拿不到 live `AgentLoop` 的 plumbing 缺口。
5. `nanobot/utils/helpers.py` 增加 section 级 token 估算 helper（基于文件 mtime 做简单缓存）。
6. **Runtime wiring**：`nanobot/channels/manager.py` 与 `nanobot/channels/websocket.py` 新增 `runtime_inspector` 可选参数；`nanobot/nanobot.py` 和 `nanobot/cli/commands.py` 的 4 处 `AgentLoop` 实例化点后，新建 `RuntimeInspector` 并注入 `ChannelManager`。
7. webui 新增 `ContextInspector` 抽屉（thread header 入口，非新路由） + `useContextPreview` hook。
8. 单元 + 集成测试（含 parity test，见 §6 阶段 3）。
9. `nanobot/docs/context-inspector.md` 用户文档。

### Out of Scope（明确推迟）
- 方案 B 的文件监听（本期只留接口预留，二期再接）。
- 多 provider 下 token 计数器切换（沿用 `estimate_prompt_tokens_chain` 既有降级链）。
- Consolidation diff 的可视化（Langfuse 风格，留作后续增强）。
- 按 skill/tool 定义的 token 细分（tools 描述注入由 provider adapter 负责，非本期）。

## 4. 目标结构体（API 契约 · v2.2）

`GET /api/sessions/{session_key}/context-preview[?full=0|1][&reveal=0|1]` 响应：

```json
{
  "snapshot_ts": "2026-04-21T12:34:56+08:00",
  "session_key": "channel:chat_id",
  "workspace": "/abs/path/to/workspace",
  "provider": { "name": "anthropic|openai|...", "model": "claude-opus-4-7" },
  "scope": "idle_baseline",
  "streaming": false,

  "system_sections": [
    { "name": "identity",        "source": "template:agent/identity.md",       "content": "...", "tokens": 812 },
    { "name": "bootstrap",       "source": "files:AGENTS.md,SOUL.md,...",      "content": "...", "tokens": 3210, "files": [{"path":".../AGENTS.md","mtime":"..."}] }
  ],

  "runtime_context": { "content": "[Runtime Context...]", "tokens": 28 },

  "messages": [
    {
      "role": "user|assistant|tool",
      "content": "...",
      "content_type": "text",
      "content_blocks": null,
      "tool_calls": null,
      "tool_call_id": null,
      "name": null,
      "tokens": 123,
      "truncated": false
    },
    {
      "role": "user",
      "content": "[multimodal message — see content_blocks]",
      "content_type": "blocks",
      "content_blocks": [
        { "type": "text", "text": "describe this image" },
        { "type": "image_url", "image_url": { "url": "data:image/png;base64,..." } }
      ],
      "tokens": 5210,
      "truncated": false
    }
  ],

  "tools": { "count": 14, "tokens": 2150, "names": ["bash", "read", "..."] },

  "totals": {
    "system_tokens": 6958,
    "runtime_tokens": 28,
    "history_tokens": 12044,
    "tool_tokens": 2150,
    "request_total_tokens": 21180,
    "context_window": 200000,
    "max_completion_tokens": 8192,
    "ctx_budget": 190784,
    "utilization_pct": 11.1
  },

  "flags": {
    "sanitized": true,
    "full": false,
    "reveal": false,
    "streaming": false,
    "in_flight": false
  },

  "notes": [
    "history: session.get_history(max_messages=0) ORIGINAL (no synthetic placeholder user, no build_messages() merge)",
    "totals.request_total_tokens EXCLUDES the user's next prompt by design (see §1 Scope)",
    "tool_tokens: estimate_prompt_tokens_chain(..., tools=agent_loop.tools.get_definitions()) diff (parity with loop.py:237 + registry.py:48)",
    "ctx_budget: context_window - max_completion_tokens - 1024 (parity with helpers.py:423)",
    "scope=idle_baseline: does NOT model _pending_queues mid-turn injections",
    "full: truncation control ONLY; reveal: redaction control ONLY; two orthogonal axes"
  ]
}
```

### 契约硬性要求（v2 修订）

**C1 — History parity**：preview 调用链必须为 `session.get_history(max_messages=0)`，与 `nanobot/agent/loop.py:731` 和 `nanobot/agent/memory.py:426` 完全一致。不使用任何硬编码上限。**preview 的 `messages` 字段是上述调用的原样结果**（再经 C8 定义的序列化）——**不**进一步调用 `build_messages()`、**不**合并 runtime_context、**不**追加任何 placeholder user message。runtime_context 作为独立字段单独返回（见 §1 范围声明与 C9）。

**C2 — Tool token parity**：`tools` 段必须存在；`tool_tokens` 通过 `estimate_prompt_tokens_chain(provider, model, [], tools=tool_defs) - estimate_prompt_tokens_chain(provider, model, [], tools=None)` 方式差分计算，**其中 `tool_defs = agent_loop.tools.get_definitions()`**（见 `nanobot/agent/tools/registry.py:48`；严禁写成 `provider._get_tool_definitions()`，该方法不存在）。**不得**把 `request_total_tokens` 误标为"仅消息 token"，面板标题须明示"包含 tool schema"。

**C3 — Idle baseline scope**：响应必有 `scope: "idle_baseline"` 字段。当目标 session 正在执行（即 `_pending_queues` 中存在该 session）时，**HTTP 状态码一律返回 `200`**，body 保持标准结构并附加 `flags.in_flight: true`（仍是 idle baseline 快照，不模拟 mid-turn）。**不使用 `409`**——"预览"语义本质是只读快照，`4xx` 会让前端误判端点坏了、触发不必要的错误分支。此项在 v2.2 已**锁定**，§6 实施步骤 6、§3 集成测试与 §9 Open Question 7 均按 `200 + flags.in_flight=true` 对齐。

**C4 — Sparse system_sections**：`system_sections` 是**稀疏数组**——`build_system_prompt()` 在 `context.py:30-63` 按条件省略 bootstrap/memory/active_skills/skills_summary/recent_history；preview **不得**伪造空段。UI 必须以 `sections.map(...)` 渲染，不得假设固定 6 段。可能出现的 `name` 取值：`identity` | `bootstrap` | `memory` | `active_skills` | `skills_summary` | `recent_history`（有且仅有 `identity` 一段必然存在）。

**C5 — Full content 契约（仅控截断，二选一敲定为 A）**：
- **(A 采纳)** 整 payload 切换：默认 `?full=0`，`messages[].content`（及 C8 的 block text）截断为前 2KB 且 `truncated: true`；`?full=1` 时返回全量、所有 `truncated: false`。**不提供**单条寻址。
- (B 放弃) 单条寻址 `/context-preview/messages/{idx}?full=1`——本期不做，留作 Open Question 8。
- **关键**：`full` **仅**控制"是否截断"，**不**控制"是否脱敏"。脱敏由 `reveal` 独立控制（见 C10）。

**C6 — Utilization 预算口径**：`utilization_pct = request_total_tokens / ctx_budget * 100`，其中 `ctx_budget = context_window - max_completion_tokens - 1024`（与 `helpers.py:423-424` 及 `/status` 命令一致）。**不得**用裸 `context_window` 做分母。

**C7 — Provider-neutral**：`system_sections[].content` 为原文 string；是否以 OpenAI `role:"system"` 消息形式下发，或 Anthropic `system` 独立字段，在 UI 层不暴露——这部分差异由 provider adapter 在真正下发时处理。

**C8 — Message content 类型（union）**：历史消息的 `content` 在 runtime 真实类型为 **`str | list[dict[str, Any]]`**（证据：`context.py:93-104` `_merge_message_content` 返回 `str | list[dict[str, Any]]`；`loop.py:879, 903` `_save_turn` 分别处理 str 与 list 分支；`helpers.py:302-340` tokenizer 同样有 list 分支）。Preview 契约：
- 响应结构必含 `content_type: "text" | "blocks"`。
- **`content_type="text"`** 时：`content` 为截断（或全量）字符串，`content_blocks=null`。
- **`content_type="blocks"`** 时：`content` 为一段 UI 友好的扁平摘要（例如 `"[multimodal — 2 blocks (text+image)]"` 或前 N 个 text block 的拼接），仅用于渲染降级；**strict parity 断言不跨越此降级**，而是对 `content_blocks` 的 **preview-safe 变换结果** 比较：即对 runtime 原始 block 数组应用与 preview 相同的截断 / 脱敏 / image omission 规则后逐项相等，**不要求** `image_url.url` 或其 base64 payload 字节级回传。`content_blocks` 仍保持 block-aware 结构：`type="text"` 的 text 字段按 `full/reveal` 规则处理；`type="image_url"` 的 `url` 字段**始终**替换为 `data:<mime>;base64,[omitted bytes=N]`，供 UI 显示 MIME + 字节数占位，不渲染真实缩略图；`?full=1` 仅恢复 text / JSON 类字段的全量内容。
- Tool-call / tool-result 的结构化字段（`tool_calls` / `tool_call_id` / `name`）作为 message 顶层可空字段透传，不压入 content。
- `messages[].tokens` 基于**原始** content（含 blocks）用 `estimate_message_tokens` 计算，与 runtime 完全一致。

**C9 — Runtime_context 段独立展示（v2.2 新增）**：
- `runtime_context` 是 preview 响应的**独立字段**，包含 `content`（文本）与 `tokens`。
- **不**在 `messages[]` 内复刻"合并到末尾 user message / 追加新 user message"的 runtime 行为——那是 `ContextBuilder.build_messages()` 在真正下发瞬间才做的动作；preview 仅展示"下次若下发，这段将被如此合并"的说明文案（UI 层 i18n 键 `contextInspector.runtime.hint`）。
- `totals.runtime_tokens` 直接取该段 `tokens`，计入 `request_total_tokens`。

**C10 — 脱敏与截断正交（v2.2 拆清）**：`?full` 与 `?reveal` 是**两个完全独立**的维度，严禁互相兜底。

| `full \ reveal` | `reveal=0`（默认安全） | `reveal=1`（高权限，逃生阀） |
|---|---|---|
| `full=0`（默认） | **截断 + 脱敏**（默认返回） | 截断 + 未脱敏 |
| `full=1` | **全量 + 脱敏** | 全量 + 未脱敏 |

- **`full`**：仅控长度。text 超 2KB 截断；`content_blocks` 内 `type="text"` 的 text 字段按 2KB 截断；`type="image_url"` 的 `url` 字段 **始终**替换为 `data:<mime>;base64,[omitted bytes=N]`（与 full 无关——不暴露图像数据，节省带宽）；`type="tool_use"` / `tool_result` 的 JSON 字段整体按 2KB 截断。
- **`reveal`**：仅控脱敏。默认（`reveal=0`）对所有文本字段（系统段 content / runtime_context / messages text / content_blocks text）应用 §6 阶段 1 步骤 4 定义的正则替换为 `[REDACTED]`；响应 `flags.sanitized=true`。`reveal=1` 时跳过脱敏，`flags.sanitized=false`；本期复用同一 bearer token，不引入分级权限（在 Open Question 2 中标注，未来可引入 scope）。
- **`sanitized` 判定**：`sanitized = (reveal=0 AND 任一正则命中)`；未命中时即使 `reveal=0` 也为 `false`（避免误报"已脱敏"）。

## 5. 风险与缓解（P0 必解，P1 应解，P2 可接受）

| # | 等级 | 风险 | 缓解 |
|---|------|------|------|
| 1 | **P0** | 误把 `runtime_context` 预合成进 `messages` 或直接复用 `build_messages()`，导致 preview 与 v2.2 契约（C1 / C9：history 原样 + runtime_context 独立段）背离，也会让 "UI 快照 == 实际发送" 的 parity 断言失去锚点 | `build_context_preview()` **分段独立调用** `_build_system_parts()`（非合并）、`_build_runtime_context()`（独立段）、`session.get_history(max_messages=0)`（原样），**严禁**调用 `build_messages()` 或合成 `[token-probe]`；parity 由 segment-level 测试守门（§阶段 3 test_context_preview.py），确保 system/runtime_context/history/tools 四段各自与 runtime 字节对齐 |
| 2 | **P0** | AGENTS.md / SOUL.md / USER.md / TOOLS.md / MEMORY.md 可能含 API key、内部策略 | (a) preview 端点复用 `_check_api_token` 鉴权；(b) 响应 `sanitized: bool` 字段；(c) 可选正则脱敏（`sk-[A-Za-z0-9]{20,}`, `AKIA[0-9A-Z]{16}`, `Bearer [A-Za-z0-9\\-_\\.]+`, 自定义正则从 `.preview-redact` 读取） |
| 3 | **P0** | 对大 prompt 反复调用 tiktoken 造成 50-200 ms 卡顿 | (a) 基于每个 md 的 `mtime+size` 缓存 section token 数；(b) 服务端节流每 session ≥ 500 ms；(c) 前端仅在面板**可见**时刷新 |
| 4 | P1 | API 路由放错位置 | 路由**必须**注册在 `nanobot/channels/websocket.py:_dispatch_http`（和 `/api/sessions` 同屋），**不是** `nanobot/api/server.py`（那是 OpenAI 兼容入口） |
| 5 | P1 | "Recent History" 分量名歧义 | 源码中 `Recent History` 来自 `memory.read_unprocessed_history()`（memory log），**不是** `Session.get_history()`；spec 中 `system_sections[5].name = "recent_history"`、`messages[]` 才是会话历史，UI 需分清 |
| 6 | P1 | 方案 B 广播 routing | `ContextSourcesChangedEvent` 按 **workspace**（非 chat_id）fan-out；需要在 WS 订阅侧建立 `workspace → connection_set` 索引 |
| 7 | P1 | Session 切换时 UI 残留 | 面板状态绑定 `session_key`，切换时清空并重新拉 |
| 8 | P1 | 流式中 token 数抖动 | 流式期间返回 `streaming: true` + `frozen_totals`（流式开始瞬间的快照）；UI 显示"⏸ 流式中" |
| 9 | P2 | Provider 差异（Anthropic system 独立字段 vs OpenAI 系列消息） | UI 以"段"形式展示，不暴露 wire format；token 计数走 `estimate_prompt_tokens_chain`，已按 provider 自适应 |
| 10 | P2 | 多 workspace/多 session | preview 端点路径以 `session_key` 为准，由 session manager 反查 workspace |
| 11 | **P0** | **History 上限与 runtime 不一致** | preview 必须调用 `session.get_history(max_messages=0)`，与 `loop.py:731` / `memory.py:426` 完全一致；严禁任何硬编码上限（v1 版本的 `500` 已移除） |
| 12 | **P0** | **Tool schema token 漏算** | runtime 走 `tools=self.tools`（`loop.py:423-425`），estimator 已计入；preview 必须通过 `agent_loop.tools.get_definitions()`（`registry.py:48`）把工具 schema 纳入 `tool_tokens` 与 `request_total_tokens`，UI 标题须明示"含 tools"。**禁止**调用不存在的 `provider._get_tool_definitions()` |
| 13 | P1 | **In-flight turn 不纳入契约** | 本期 `scope="idle_baseline"`；当 `_pending_queues` 中存在目标 session 时，API 返回 `in_flight: true` + 冻结的 idle baseline 快照（而非 mid-turn 实时状态）；UI 显示 "⏳ Turn 执行中（下次 idle 基线）" |
| 14 | P1 | **system_sections 条件省略** | `build_system_prompt()` 按内容条件省略各段（`context.py:30-63`）。API 契约为 **sparse array**；UI 不得假设固定 6 段；验收改为"存在的段与 build_system_prompt 一致，缺段不伪造" |
| 15 | P1 | **utilization% 口径偏差** | 分母必须为 `ctx_budget = context_window - max_completion_tokens - 1024`（`helpers.py:423-424`），与 `/status` 口径一致；裸 `context_window` 会让用户对"何时触发 consolidation"产生错觉 |
| 16 | P1 | **full_content 契约歧义** | 采纳方案 A：`?full=0` 默认截断，`?full=1` 整 payload 全量；**不**提供单条寻址 API（原 v1 的 `full_content_hash` 已删除） |
| 17 | P1 | **Message content 可为 block array** | 历史中存在 multimodal / 结构化 tool_result 时 `content` 为 `list[dict]`；若 spec 仅建模为纯文本，parity test 在含图或含 block 的 session 上会失败。契约 C8 统一用 `content_type + content / content_blocks` union 表示 |
| 18 | **P0** | **Current-prompt 边界歧义** | 产品目标"除当前输入 prompt 外" vs 工程手段"用 `[token-probe]` 占位 + `build_messages()` parity"互斥。v2.2 敲定：preview **真正不含**当前 prompt；`messages` 直出 `session.get_history(max_messages=0)`；runtime_context 独立字段；parity 改为分段 parity（契约 C1 / C9） |
| 19 | P1 | **端点拿不到 live `AgentLoop`** | `WebSocketChannel.__init__` (`websocket.py:301-308`) 仅持 `SessionManager`，无 `AgentLoop`/`ContextBuilder`/`provider`。必须新建 `nanobot/agent/runtime_inspector.py` facade + 改 `ChannelManager` 与 4 处 `AgentLoop` 实例化点 wiring（`nanobot/nanobot.py:69`, `cli/commands.py:576 / 679 / 1055`） |
| 20 | P1 | **`full` 与 `reveal` 语义打架** | v2.1 把 `?full=1` 写成"同时返回完整 block 数据 + 脱敏"，与默认安全边界冲突。v2.2 按契约 C10 拆清：`full` 仅控截断、`reveal` 仅控脱敏，矩阵正交 |

## 6. 实施计划（分阶段）

### 阶段 1 · 后端契约（约 1.5 日）
1. **`nanobot/agent/context.py`（仅抽取，零行为变更）**：
   - 将 `build_system_prompt` 内部的 parts 构造抽成私有 `_build_system_parts(skill_names, channel) -> list[SystemSection]`，每个 SystemSection 是 `(name, source, content)`；`build_system_prompt` 改为 `return "\n\n---\n\n".join(sec.content for sec in sections)` —— **对现有行为零侵入**。
   - 不在此文件添加任何 preview 逻辑。
2. **`nanobot/agent/context_preview.py`（新建，承载 preview 主逻辑与 dataclasses）**：
   - 新增 dataclasses：`ContextPreview / SystemSection / RuntimeContext / MessagePreview / ContentBlockPreview / ToolsPreview / Totals / Flags`。
   - **新增** `build_context_preview(context_builder, session, channel, chat_id, session_summary=None, *, tool_defs: list[dict] | None = None, full: bool = False, reveal: bool = False) -> ContextPreview`：
     - 调 `context_builder._build_system_parts(...)` 拿 sparse 系统段（**契约 C4**）。
     - 调 `context_builder._build_runtime_context(channel, chat_id, context_builder.timezone, session_summary=session_summary)` 得到**独立**的 runtime_context 段（**契约 C9**）。
     - 调 `session.get_history(max_messages=0)` 拿 history（**契约 C1**）。**此 history 就是 preview 的 `messages` 原始数据，不做任何合并/追加**（**契约 C1 + C9**）；**禁止**构造 `[token-probe]` 占位或调用 `build_messages()`。
     - 序列化 messages（**契约 C8**）：对每条 history message 判断 `isinstance(content, list)`：
       - 是 → `content_type="blocks"`，`content_blocks=preview_safe_transform(content, full=full, reveal=reveal)`（按 C5/C8/C10 规则处理），`content="[multimodal — N blocks]"` UI 降级摘要。
       - 否 → `content_type="text"`，`content=str_content`，`content_blocks=None`。
     - **截断（C5 + C10 `full` 维度）**：`full=False` 时对 text 字段（含 block 内的 text）做 2KB 截断并置 `truncated=true`；image base64 **始终**替换为 `[omitted bytes=N]`（与 full 无关）；tool_use/tool_result JSON 超 2KB 时同样截断。
     - **脱敏（C10 `reveal` 维度）**：`reveal=False` 时走 `nanobot/utils/redact.py` 对所有文本字段应用正则替换，返回 `sanitized=true if any_hit else false`；`reveal=True` 时跳过脱敏，`sanitized=false`。
     - `tool_calls` / `tool_call_id` / `name` 作为 message 顶层字段透传。
   - **`ToolsPreview`** 由 `build_context_preview` 根据传入的 `tool_defs` 产出：`count = len(tool_defs)`、`names = [d["function"]["name"] or d.get("name") for d in tool_defs]`、`tokens` 由 endpoint 侧差分计算后回填（见步骤 6）。
3. **`nanobot/utils/helpers.py`**：
   - 新增 `estimate_section_tokens(text: str | list[dict], cache_key: tuple | None = None) -> int`；`cache_key=(path, mtime_ns, size)` 时走进程内 dict 缓存（LRU 512）；纯字符串/block 无 key 直接走 `estimate_message_tokens` 既有分支（已支持 `isinstance(content, list)`，见 `helpers.py:337-340`）。
   - **不改**现有 `estimate_prompt_tokens*` 行为；preview 通过 `estimate_prompt_tokens_chain(provider, model, messages=[], tools=tool_defs) - estimate_prompt_tokens_chain(provider, model, messages=[], tools=None)` 差分得到 `tool_tokens`（**契约 C2**）；**`tool_defs` 在 preview 端点层获取：`agent_loop.tools.get_definitions()`**（`registry.py:48`）。如差分为负则归零并打 warning。

4. **`nanobot/agent/runtime_inspector.py`（新建，解决 runtime plumbing）**：
   ```python
   @dataclass(frozen=True)
   class RuntimeRef:
       agent_loop: "AgentLoop"
       context_builder: "ContextBuilder"
       provider: Any
       model: str
       context_window_tokens: int
       max_completion_tokens: int
       tools: "ToolRegistry"

   class RuntimeInspector:
       def __init__(self, agent_loop: "AgentLoop") -> None:
           self._loop = agent_loop
       def get(self, session_key: str) -> RuntimeRef | None: ...
       def is_in_flight(self, session_key: str) -> bool:
           return session_key in self._loop._pending_queues  # noqa: SLF001
   ```
   - `get()` 返回 session 绑定的 runtime 三元组；若 session_key 未知返回 None（endpoint 回 404）。
   - 单一 facade，避免 `WebSocketChannel` 反射 `_pending_queues` 等私有字段；也便于单测 mock。

5. **`nanobot/session/manager.py`**：
   - 新增公开只读 lookup：`get(key: str) -> Session | None`，语义为"若 session 已存在则返回，否则返回 None"；内部允许复用 `_cache` / `_load()`，但**不**创建新 session。
   - `get_or_create()` 保持现有行为不变；context-preview 端点**必须**走 `get()`，以满足"非法 `session_key` → 404" 契约，避免在 HTTP 层直接依赖私有 `_load()`。

6. **`nanobot/channels/websocket.py:_dispatch_http` 与构造函数**：
   - `WebSocketChannel.__init__` 新增 kwarg `runtime_inspector: RuntimeInspector | None = None`，保存为 `self._runtime_inspector`。
   - 注册 `GET /api/sessions/{key}/context-preview`（**注意：不是 `nanobot/api/server.py`**），鉴权复用 `_check_api_token`。
   - 查询参数：`?full=0|1`（默认 0，控截断）；`?reveal=0|1`（默认 0，控脱敏）（**契约 C10**）。
   - 处理流程：
     1. `ref = self._runtime_inspector.get(session_key)`；`None` → 404。
     2. 若 `self._runtime_inspector.is_in_flight(session_key)` → 响应 `flags.in_flight=true`（仍回空闲基线，**契约 C3**）。
     3. `tool_defs = ref.tools.get_definitions()`（**契约 C2**）。
     4. `session = session_manager.get(session_key)`；`None` → 404；随后调 `build_context_preview(ref.context_builder, session, channel, chat_id, session_summary=..., tool_defs=tool_defs, full=full, reveal=reveal)`。
     5. 端点侧计算 `tool_tokens` 差分后回填到 `preview.tools.tokens` 与 `preview.totals.tool_tokens`。
     6. `utilization_pct = request_total / (ref.context_window_tokens - ref.max_completion_tokens - 1024) * 100`（**契约 C6**）。
     7. 序列化 `ContextPreview` 为 JSON 返回。

7. **Runtime wiring（把 `RuntimeInspector` 注入到 `WebSocketChannel`）**：
   - **`nanobot/channels/manager.py:40-90` `ChannelManager.__init__`**：新增 `runtime_inspector: RuntimeInspector | None = None` 参数，保存为 `self._runtime_inspector`；`_init_channels` 条件注入块中（`if cls.name == "websocket"`）一并注入 `kwargs["runtime_inspector"] = self._runtime_inspector`。
   - **`nanobot/nanobot.py:69` 附近**：在 `AgentLoop(...)` 实例化**之后**新建 `RuntimeInspector(agent_loop)`，传入 `ChannelManager(config, bus, session_manager=..., runtime_inspector=...)`。
   - **`nanobot/cli/commands.py`**：同样在三处 `AgentLoop` 实例化点（`:576 / :679 / :1055`）之后创建 `RuntimeInspector` 并传给 `ChannelManager`（`:768` 附近）。**注意：`commands.py:576` 与 `:679` 可能在 CLI 交互/批处理路径上不启动 ChannelManager**——实施时需按真实调用链逐一确认，未使用 ChannelManager 的路径可跳过 wiring。

8. **`nanobot/utils/redact.py`（新建）**：
   - 正则脱敏：`sk-[A-Za-z0-9]{20,}` / `AKIA[0-9A-Z]{16}` / `Bearer [A-Za-z0-9\-_.]+` / `ghp_[A-Za-z0-9]{36}` 等。
   - 接受用户自定义规则：`{workspace}/.preview-redact`（每行一条正则）。
   - 输出 `(redacted_text, was_redacted: bool)`；`build_context_preview` 汇总为顶层 `flags.sanitized: bool`。

**阶段 1 验收**：
- `curl -H "Authorization: Bearer $TOKEN" .../context-preview` 返回 §4 结构，包含 `scope: "idle_baseline"`、`tools.tokens > 0`、`totals.request_total_tokens ≈ system + runtime + history + tools`（允许 ±2% 误差，因 tiktoken 对分隔符处理）。
- 修改 workspace 中 `AGENTS.md` 后再次 curl，`bootstrap.content` 与 `tokens` 发生对应变化。
- 构造一个"全量禁用 skills + MEMORY.md 为模板默认 + 没有 bootstrap 文件"的 workspace，`system_sections` 应**仅含 `identity`**（**契约 C4** 验证）。

### 阶段 2 · 前端面板（约 1.5 日）
1. **`webui/src/lib/api.ts`**：新增 `fetchContextPreview(sessionKey, { full, reveal })`；沿用现有 `baseUrl + token` 注入规则。
2. **`webui/src/hooks/useContextPreview.ts`**：
   - 首次打开抽屉时拉取（`full=false`）。
   - 抽屉可见期间每 5 s stale-while-revalidate（仅当 session 非 streaming 时；streaming 期间间隔拉长到 15 s，UI 显示 "⏸ 流式中（冻结预览）"）。
   - 抽屉隐藏立刻停表；session 切换时清空旧快照并重拉（**风险 7** 缓解）。
3. **`webui/src/components/context-inspector/ContextInspector.tsx`**：
   - 顶部：`totals` 概览 —— 四个 TokenBadge（system / history / tools / runtime）+ 一条 `Progress` 进度条显示 `utilization_pct`（基于 `ctx_budget`，tooltip 注明公式）；`sanitized` 时显示 ⚠ "已脱敏" badge；`in_flight` 时显示 ⏳ "Turn 执行中（下次 idle 基线）"。
   - 上半区：**按 `system_sections.map` 动态渲染**（**契约 C4**），严禁硬编码 6 段；每段一个 `Collapsible`，标题行含 `name` + `source` + `TokenBadge`；下挂 `runtime_context` 段。
   - 下半区：`messages` 卡片列表，每卡 role / tokens / content（**按 `content_type` 分支渲染**）：
     - `content_type="text"`：`MarkdownText` 渲染；若 `truncated` 标灰显示 `+N 字未展示`。
     - `content_type="blocks"`：按 `content_blocks[]` 遍历，`type="text"` 走 Markdown、`type="image_url"` 显示图像占位 + MIME + 字节数（**不渲染真实缩略图**）、`type="tool_use"` / 其他类型按 code 块降级；顶部显示 "🧩 multimodal (N blocks)" badge。
     - 含 `tool_calls` 时显示 "🔧 N tool calls" 折叠区；含 `tool_call_id` 的 tool-result message 标"🔁 tool result for {name}"。
   - 右上角一个全局"显示完整内容"开关 → 切换为 `full=1` 整 payload 拉取（**契约 C5**），**不做**逐条寻址。
   - `tools` 折叠区域显示 `count / names / tokens`（只读）。
   - 复用：`MarkdownText`, `CodeBlock`, ShadCN `Collapsible` / `Progress` / `Sheet` / `Separator` / `Tooltip`。
4. **`webui/src/lib/types.ts`**：扩展 `ContextPreview` / `SystemSection` / `MessagePreview` 类型；`InboundEvent` 联合本期**不新增事件类型**（方案 B 的 `context_sources_changed` 在阶段 4 再加）。
5. **`webui/src/components/thread/ThreadShell.tsx`**：header 新增 🧾 按钮（非抽屉路由），点击打开 `<Sheet>` 右侧抽屉（宽度 ≥ 640px）。**不引入新路由**——保持现有单 `Shell` 架构（`App.tsx:150`）。
6. **i18n**：所有新文案走 `useTranslation()`。**实际路径为 `webui/src/i18n/locales/<locale>/common.json`**（非 `src/locales/*.json`）；webui 当前支持 9 个 locale：`en, es, fr, id, ja, ko, vi, zh-CN, zh-TW`。新增命名空间 `contextInspector.*`（button / drawer.title / totals.system / totals.tools / totals.history / totals.runtime / totals.utilization / sections.identity / sections.bootstrap / sections.memory / sections.activeSkills / sections.skillsSummary / sections.recentHistory / flags.sanitized / flags.inFlight / flags.streaming / actions.showFull / actions.collapse / empty.noSections 等键）：
   - **en + zh-CN 必须完整翻译**（主力用户语言）。
   - **其余 7 个 locale（es / fr / id / ja / ko / vi / zh-TW）**：首期可先 fallback 到 en（与 `webui/src/i18n/config.ts` 既有 `fallbackLng` 行为一致），但**必须**在 JSON 中插入 `contextInspector` 命名空间的占位键值（内容直接拷贝 en），避免 `i18next` missing key 警告；后续由社区/维护者补译。
   - **不得**在组件里写死任何中/英文串（含 emoji 后的描述文字）。

**阶段 2 验收**：
- 启动 nanobot + webui → 点击 header 🧾 → 抽屉打开，顶部 totals 显示四项 token + utilization 进度。
- 打开的工作区若无自定义 bootstrap/memory/skills → 上半区仅显示 `identity` 段（sparse 渲染正确，**契约 C4**）。
- 修改 `SOUL.md` → ≤ 5 s 后抽屉刷新，相应段内容与 token 数变化（方案 A 被动轮询生效）。
- 切换 session → 抽屉数据替换，无上一个 session 的残留。
- 切换 UI 语言（中 / 英）→ 抽屉所有文案跟随切换，无硬编码字符串遗漏。
- 流式响应期间打开抽屉 → 显示 "⏸ 流式中（冻结预览）"，数据为流式开始瞬间的快照。

### 阶段 3 · 测试（约 1 日）
1. **`tests/test_context_preview.py`**（单元 + 对比）：
   - **Segment-level parity（核心，契约 C1/C2/C8/C9 守门）**：**不调用 `build_messages()`**。构造多个 session fixture，逐段独立断言 preview 与 runtime 来源一致：
     - **System parity**：`"\n\n---\n\n".join(sec.content for sec in preview.system_sections)` 与 `context_builder.build_system_prompt(skill_names, channel)` 在同一 workspace 下**字节相等**。
     - **Runtime_context parity**：`preview.runtime_context.content` 与 `context_builder._build_runtime_context(channel, chat_id, tz, session_summary=...)` 字节相等；`preview.runtime_context.tokens == estimate_section_tokens(...)`（契约 **C9**）。
     - **History parity**：`preview.messages` 的条目数、role、`tool_calls / tool_call_id / name` 等顶层字段与 `session.get_history(max_messages=0)` 原样相等；`content_type="text"` 条目的 content 与原值字节相等；对 `content_type="blocks"` 条目，`content_blocks` 与对 runtime 原 list 应用同一 preview-safe transform（截断 / 脱敏 / image omission）后的结果逐项相等（契约 **C8**）；**`preview.messages` 末尾不得出现合成的 `[token-probe]`** 或 runtime_context 合并后的 user message（契约 **C1**）。
     - **Tools parity**：`preview.tools.names == [d["function"]["name"] for d in agent_loop.tools.get_definitions()]` 顺序敏感相等；`preview.tools.count == len(tool_defs)`。
   - Fixture 必须覆盖：
     - 纯文本 session（`content: str`）。
     - 含图像的 multimodal session（`content: list` 包含 `image_url` block）。
     - 含 tool_use / tool_result 的 session（验证 `tool_calls / tool_call_id / name` 透传）。
     - Empty-history session（只有 system，`preview.messages == []`，`runtime_context.content` 仍独立返回）。
   - **Tool-tokens diff（契约 C2）**：断言 `totals.tool_tokens` 与 `estimate_prompt_tokens_chain(provider, model, [], tools=agent_loop.tools.get_definitions()) - estimate_prompt_tokens_chain(provider, model, [], tools=None)` 的差分相等；`request_total_tokens ≈ system_tokens + runtime_tokens + history_tokens + tool_tokens` 误差 ≤ 2%（tiktoken 分隔符偏差）。
   - **Sparse sections（契约 C4）**：至少 4 个 fixture —— (a) 空 workspace 仅 identity；(b) 仅有 AGENTS.md；(c) MEMORY.md 为默认模板（应省略）；(d) 全套齐全 6 段；每 fixture 对 `system_sections[*].name` 做精确序列匹配。
   - **Consolidation 后**：`messages` 不含 `last_consolidated` 之前的条目；`recent_history` 系统段（memory log，**非** session history）反映 memory 最新状态。
   - **No-merge 边界（契约 C9）**：无论末尾 history 的 role 是 user 还是 assistant，`preview.runtime_context` 始终独立返回；`preview.messages[-1].content` 与原始 `get_history(0)[-1].content` 逐字节相等——断言 preview 不 mutate、不合并、不追加（与 runtime `build_messages()` 的"同角色合并 / 新建 user"行为**解耦**，那是下发瞬间才发生的）。
   - **Truncation（契约 C5 + C10 `full` 维度）**：`full=False` 时 text 字段 ≤ 2KB 且 `truncated=true`、`content_blocks` 内 `type="text"` 的 text 同样 ≤ 2KB；`type="image_url"` 的 `url` **始终**形如 `data:<mime>;base64,[omitted bytes=N]`（与 full 无关）；`full=True` 时所有 text 字段 `truncated=false` 且 `content_blocks[*].type="text"` 的 text 还原为原值（image_url 仍 omitted）。
   - **Redaction（契约 C10 `reveal` 维度）**：预置含 `sk-abcdefghij0123456789012345` 的 bootstrap，断言 `reveal=0`（默认）响应已替换为 `[REDACTED]` 且 `flags.sanitized=true`；`reveal=1` 时返回原串、`flags.sanitized=false`。
   - **Full × Reveal 2×2 矩阵（契约 C10）**：针对同一 fixture 依次发 `(full=0,reveal=0)` / `(full=0,reveal=1)` / `(full=1,reveal=0)` / `(full=1,reveal=1)` 四组请求，断言四个维度独立变化：`full` 只影响 `truncated` 与 text 长度；`reveal` 只影响 `sanitized` 与脱敏字段内容；两者不互相渗透。
   - **Utilization（契约 C6）**：断言 `utilization_pct = round(request_total / (context_window - max_completion - 1024) * 100, 1)`，与 `/status` 命令手算一致。
2. **`tests/test_context_preview_api.py`**（集成）：
   - 鉴权缺失 → 401；错误 token → 401；合法 token → 200。
   - `?full=0` vs `?full=1` payload 字节差显著（≥10×，取决于 history 规模）。
   - 非法 session_key → 404。
   - Session 正在执行时 → 响应含 `in_flight=true` 且 `scope="idle_baseline"`（契约 C3）。
   - Provider 切换（OpenAI ↔ Anthropic）→ `totals.tool_tokens` 非负；两侧 `request_total_tokens` 都在合理量级。
3. **手工 E2E**：
   - 阶段 1 被动刷新：`touch AGENTS.md && 追加内容` → 在前端抽屉内 5 s 内看到变化。
   - 阶段 4（如落地）：同操作 → 1 s 内前端收到 `context_sources_changed` 并刷新。
   - i18n：切换语言包，所有新文案切换；对抽屉做一次 ARIA / a11y 快速检查。

### 阶段 4 · 方案 B（可选，约 1 日）
1. `pyproject.toml` 加 `watchfiles>=0.21`。
2. `nanobot/watchers/context_sources.py`：`awatch` 按 workspace 启动独立 task。
3. `nanobot/bus/events.py`：`ContextSourcesChangedEvent`。
4. `websocket.py` 加 `workspace → {connection}` 索引 + fan-out。
5. 前端增加对 `context_sources_changed` 事件的监听，debounce 300 ms 刷新。
6. 测试：触摸 md → 1 s 内前端拿到刷新。

### 阶段 5 · 文档（约 0.5 日）
- `nanobot/docs/context-inspector.md`：功能说明 + 截图 + 敏感信息策略 + FAQ。

## 7. 文件改动清单

| # | 文件 | 改动 |
|---|------|------|
| 1 | `nanobot/agent/context.py` | 抽 `_build_system_parts() -> list[SystemSection]`；`build_system_prompt` 改为调用它 + join，**现有行为保持不变**；不在此文件加 preview 逻辑（便于独立测试） |
| 2 | `nanobot/agent/context_preview.py` | **新建** `build_context_preview()` + dataclasses `ContextPreview / SystemSection / RuntimeContext / MessagePreview / ContentBlockPreview / ToolsPreview / Totals / Flags` |
| 3 | `nanobot/agent/runtime_inspector.py` | **新建** `RuntimeInspector` facade + `RuntimeRef` dataclass；`get(session_key)` / `is_in_flight(session_key)` 两个只读接口，供 WebSocket 层按 `session_key` 反查 runtime 三元组 |
| 3a | `nanobot/session/manager.py` | +公开只读 `get(key) -> Session \| None` lookup（不创建 session，供 context-preview 端点保留 `404` 语义） |
| 4 | `nanobot/utils/helpers.py` | +`estimate_section_tokens(text, cache_key)`，内部 mtime 缓存；**不改**既有 `estimate_prompt_tokens*` 行为 |
| 5 | `nanobot/utils/redact.py` | **新建** 正则脱敏工具（读 `.preview-redact` 支持自定义） |
| 6 | `nanobot/channels/websocket.py` | `__init__` 新增 kwarg `runtime_inspector: RuntimeInspector \| None = None`；`_dispatch_http` 注册 `GET /api/sessions/{key}/context-preview`；参数 `?full / ?reveal`；`in_flight` 检测；通过 `session_manager.get()` 保持未知 session → `404` |
| 7 | `nanobot/channels/manager.py` | `ChannelManager.__init__` 新增 `runtime_inspector: RuntimeInspector \| None = None`；`_init_channels` 的 `cls.name == "websocket"` 条件块内把 `self._runtime_inspector` 注入 `kwargs`（与 `session_manager`/`static_dist_path` 同处） |
| 8 | `nanobot/nanobot.py` | 在 `AgentLoop(...)` 实例化后新建 `RuntimeInspector(agent_loop)`，传给 `ChannelManager(..., runtime_inspector=...)`（`:69` 附近） |
| 9 | `nanobot/cli/commands.py` | 三处 `AgentLoop` 实例化点（`:576 / :679 / :1055`）之后创建 `RuntimeInspector`，在启动 `ChannelManager` 的路径（如 `:768` 附近）传入；**未启动 `ChannelManager` 的 CLI 子命令路径可跳过**（实施时按真实调用链确认） |
| 10 | `tests/test_context_preview.py` | **新建**（见 §阶段 3 单元清单：含 segment-level parity + Full × Reveal 2×2 矩阵 + empty-history 边界 + block preview-safe parity） |
| 11 | `tests/test_context_preview_api.py` | **新建**（见 §阶段 3 集成清单：含 `in_flight` 冒烟、RuntimeInspector 注入回归） |
| 12 | `webui/src/lib/api.ts` | +`fetchContextPreview(sessionKey, { full, reveal })` |
| 13 | `webui/src/lib/types.ts` | 扩展 `ContextPreview / SystemSection / RuntimeContext / MessagePreview / ContentBlockPreview / ToolsPreview / Totals / Flags` 类型 |
| 14 | `webui/src/hooks/useContextPreview.ts` | **新建**（SWR 节流 + streaming/in_flight 感知） |
| 15 | `webui/src/components/context-inspector/ContextInspector.tsx` | **新建**（sparse sections 渲染 + runtime_context 独立段 + totals + tools + messages；image block 仅占位展示） |
| 16 | `webui/src/components/context-inspector/TokenBadge.tsx` | **新建**（可内联） |
| 17 | `webui/src/components/thread/ThreadShell.tsx` | +header 🧾 按钮 +`<Sheet>` 抽屉容器 |
| 18 | `webui/src/i18n/locales/en/common.json` | +`contextInspector.*` 命名空间（完整翻译） |
| 19 | `webui/src/i18n/locales/zh-CN/common.json` | +`contextInspector.*` 命名空间（完整翻译） |
| 19a | `webui/src/i18n/locales/{es,fr,id,ja,ko,vi,zh-TW}/common.json` | +`contextInspector.*` 命名空间（先拷 en 占位，避免 i18next 告警；待社区补译） |
| 20 | `nanobot/docs/context-inspector.md` | **新建** 用户文档 + 截图 + 敏感信息策略 + FAQ |
| 21 | *(阶段 4)* `pyproject.toml` | +`watchfiles>=0.21` |
| 22 | *(阶段 4)* `nanobot/watchers/context_sources.py` | **新建** |
| 23 | *(阶段 4)* `nanobot/bus/events.py` | +`ContextSourcesChangedEvent` |

## 8. 验收标准（合并自各阶段）

### 契约层
- [ ] **C1**：preview 内部统一走 `session.get_history(max_messages=0)`，grep 实现代码无任何 `500` 硬编码；**更关键**：grep `context_preview.py` 无 `build_messages(` 调用、无 `[token-probe]` 字符串、无 runtime_context 合并到 messages 尾的逻辑。
- [ ] **C2**：`totals.tool_tokens > 0`（当 runtime 注册了工具时），`request_total_tokens ≈ system + runtime + history + tool` 误差 ≤ 2%；UI 标题明示"含 tools"。实现侧 tool_defs 来源于 `ref.tools.get_definitions()`（`ToolRegistry`），grep 无 `provider._get_tool_definitions`。
- [ ] **C3**：目标 session 在 `_pending_queues` 中时，响应 `in_flight: true` + `scope: "idle_baseline"`；UI 显示 ⏳ "Turn 执行中（下次 idle 基线）"。
- [ ] **C4**：`system_sections` 稀疏返回；空 workspace fixture 只含 `identity` 一段；UI 渲染 `sections.map(...)`，无硬编码 6 段。
- [ ] **C5**：`?full=0` 截断且 `truncated=true`，`?full=1` 全量 `truncated=false`；**未**引入逐条寻址 API。
- [ ] **C6**：`utilization_pct` 分母为 `context_window - max_completion_tokens - 1024`，口径与 `/status` 命令一致。
- [ ] **C7**：同一 session 切换 provider，`tool_tokens` 非负、`request_total` 处于合理量级；UI 不因 provider 差异改变布局。
- [ ] **C8**：对包含 multimodal / tool-use / tool-result 的 session，`content_type` 正确区分 `"text" / "blocks"`，`content_blocks` 在 `full=True` 下与运行时原值逐项相等；UI 对三种 block 类型（text / image_url / tool_use）均有对应渲染分支。
- [ ] **C9**：响应结构包含**独立的** `runtime_context: { content, tokens }` 段；`preview.messages[-1].content` 与 `session.get_history(0)[-1].content` 字节相等（证明 preview 未合并 runtime_context 到尾部消息）；`totals.runtime_tokens == runtime_context.tokens` 且计入 `request_total_tokens`。UI 侧 runtime_context 以独立 Collapsible 呈现，配 i18n 文案 `contextInspector.runtime.hint`。
- [ ] **C10**：Full × Reveal 正交矩阵（4 组请求 `(full,reveal) ∈ {0,1}²`）对同一 fixture 返回四种不同 payload，逐维度独立可验证：`full` 只影响 `truncated` / text 长度 / `content_blocks[*].text` 长度（image_url url 与 full 无关，恒 omitted）；`reveal` 只影响 `flags.sanitized` 与脱敏字段内容；两维度不互相渗透。

### Parity（"UI 快照 == 实际发送"——按分段）
- [ ] **System parity**：`"\n\n---\n\n".join(preview.system_sections[*].content)` 与 `context_builder.build_system_prompt(skill_names, channel)` 逐字节相等。
- [ ] **Runtime_context parity**：`preview.runtime_context.content` 与 `context_builder._build_runtime_context(channel, chat_id, tz, session_summary=...)` 逐字节相等。
- [ ] **History parity**：`preview.messages` 的条目数、role 序列与 `session.get_history(max_messages=0)` 原样相等；`content_type="text"` 条目的 content 与原值字节相等，`content_type="blocks"` 条目的 `content_blocks` 与对 runtime 原 blocks 应用同一 preview-safe transform（截断 / 脱敏 / image omission）后的结果相等；**不得**出现合成的 user message、`[token-probe]` 占位或 runtime_context 合并尾部的 artifact。
- [ ] **Tools parity**：`preview.tools.names` 顺序与 `ref.tools.get_definitions()` 的 function name 序列一致；`preview.tools.tokens` 等于差分结果。
- [ ] **Totals parity**：`totals.request_total_tokens == system_tokens + runtime_tokens + history_tokens + tool_tokens`（tiktoken 分隔符误差 ≤ 2%）。

### 功能层
- [ ] `/api/sessions/{k}/context-preview` 鉴权生效（401 / 404 用例正确）。
- [ ] 修改 AGENTS.md / SOUL.md / MEMORY.md / SKILL.md 后 5 秒内 UI 反映新内容与新 token（方案 A）。
- [ ] 面板关闭后后端 CPU 占用无明显增加（节流生效）。
- [ ] 敏感字符串（`sk-*`, `AKIA*`, `Bearer *`, `ghp_*`）默认被 `[REDACTED]`，响应 `sanitized=true`；`.preview-redact` 的用户规则生效。
- [ ] 流式中打开面板显示 `⏸ 流式中（冻结预览）`，数据不抖动。
- [ ] Session 切换后面板数据跟随切换，无残留。
- [ ] `webui/src/i18n/locales/en/common.json` 与 `zh-CN/common.json` 完整翻译 `contextInspector.*` 键；切换中英文无硬编码字符串遗留。
- [ ] 其余 7 个 locale（`es / fr / id / ja / ko / vi / zh-TW`）均已插入 `contextInspector` 命名空间占位键（至少拷 en 文本），切换到任一 locale 控制台无 `i18next::translator: missingKey` 警告。

### 阶段 4（可选）
- [ ] 修改 md 后 1 秒内前端收到 `context_sources_changed` WS 事件并刷新。

## 9. Open Questions（需用户/团队确认）

1. **是否落地方案 B**（文件监听 + WS 推送）？推荐：一期先 A，二期 B。
2. **脱敏默认开关**：默认 ON（生产更安全）还是 OFF（开发更直白）？推荐 ON + `?reveal=1` 逃生阀（需更高权限 token，复用现有 bearer，暂不引入分级权限）。
3. **截断阈值**：默认 2KB / 条是否合适？若多数消息 < 2KB 会变成"等同全量"，若常含 10KB+ tool result 则截断感明显。建议：默认 4KB，用户点"显示完整内容"切到 `?full=1`。
4. **Token 估算策略**：是否引入 provider 专用 tokenizer（例如 Anthropic `count_tokens` API 做对账 badge）？本期仅复用 `estimate_prompt_tokens_chain` 既有降级链，对账能力设为 Open。
5. **入口位置**（已敲定）：ThreadShell header 🧾 按钮 → `<Sheet>` 右侧抽屉；**不**引入新路由，不复活"Token 页"称呼（与 `webui/src/App.tsx:150` 单 `Shell` 架构一致）。
6. **Workspace 路径展示**：抽屉头部显示 workspace 绝对路径（便于用户定位在改哪个 md）？还是仅在 tooltip？推荐 tooltip，避免泄露运行环境细节。
7. **`in_flight` HTTP 语义**（已敲定）：**`200 + flags.in_flight=true`**，body 仍为标准 idle baseline 快照；**不使用 `409 Conflict`**。"预览"本质是只读快照，`4xx` 会让前端误判端点坏了、触发错误分支；契约 C3 已锁定此决策，本 OQ 仅作历史记录，无需再讨论。
8. **逐条 message 寻址**（契约 C5 的 B 选项）：本期不做，若后续数据量变大可再上 `GET /api/sessions/{k}/context-preview/messages/{idx}`。暂留作 Q8。

## 10. 决策/变更记录

### v2.1 → v2.2（2026-04-21，Codex 三轮评审后）
| 修订点 | v2.1 | v2.2 | 证据 |
|---|---|---|---|
| **Current-prompt 边界**（P0） | 用 `build_messages(history, current_message="[token-probe]", ...)` 做 parity，声称"除当前 prompt"但工程上仍然合成了一条 user message、还把 runtime_context 合并到尾部 —— 与产品目标直接冲突 | **preview 真不含当前 prompt**：`messages` 直出 `session.get_history(max_messages=0)`；runtime_context 为独立字段（契约 **C9**）；parity 由 `build_messages()` 整体对比改为 **segment-level parity**（system / runtime_context / history / tools 各自独立断言） | `context.py:30-63` `build_system_prompt` 与 `context.py:80-90` `_build_runtime_context` 两个入口本就独立可调；`loop.py:731` 与 `memory.py:426` 的真实运行时调用即以 `get_history(0)` 为基准 |
| **RuntimeInspector facade**（P1） | 阶段 1 直接说"在 `_dispatch_http` 注册路由"，但 `WebSocketChannel.__init__(config, bus, *, session_manager=None, static_dist_path=None)` **并不持有** `AgentLoop` / `ContextBuilder` / `provider` / `tools`，端点写出来也拿不到 runtime 依赖 | **新建 `nanobot/agent/runtime_inspector.py`**（单一 facade，封装 `agent_loop` 引用 + `_pending_queues` 查询）；`ChannelManager` 新增 `runtime_inspector` kwarg，在 `_init_channels` 的 `cls.name == "websocket"` 条件块内注入；`nanobot.py:69` 和 `cli/commands.py:576/679/1055` 四处 `AgentLoop` 实例化点新建 inspector 并传递 | `channels/websocket.py:301-308` 构造签名；`channels/manager.py:59-95` `_init_channels` 条件注入骨架；`agent/loop.py:395-420` `_drain_pending` 与 `loop.py:480-499` `_pending_queues` 为 `is_in_flight()` 的唯一真实源 |
| **Full vs Reveal 语义**（P1） | 契约 C5 "`?full=1` 时返回完整 + 脱敏"，与默认安全默认冲突；脱敏和截断互相兜底导致矩阵不闭合 | **契约 C10 正交 2×2 矩阵**：`full` 仅控截断（含 block text 长度，不含 image_url url——后者恒 omitted）；`reveal` 仅控脱敏（默认 `reveal=0` 应用正则，`reveal=1` 跳过）；`sanitized = reveal=0 AND 任一正则命中` | 产品安全原则：文本长度控制与敏感信息屏蔽是正交关注点；与业界 inspector（LangSmith / Langfuse）的 `?redact=…` + `?full=…` 解耦保持一致 |
| *(minor)* §3 In-Scope | "`ContextBuilder` 新增 `build_context_preview()`" | 明确 `ContextBuilder` 仅做非侵入抽取；`build_context_preview` 归属 `nanobot/agent/context_preview.py`（新建）；与 §6 实施 + §7 文件清单自洽 | 内部一致性修正 |
| *(v2.2 收尾)* §5 风险 #1 | 缓解写成"复刻 `build_messages` 合并逻辑"—— 与 v2.2 C1/C9 主契约直接打架 | 改写为"误把 runtime_context 预合成进 messages"风险；缓解改为"分段独立调用 + segment-level parity 测试守门"，与契约 C1/C9、§6 阶段 1 步骤、§3 测试策略完全自洽 | 文档内部一致性 |
| *(v2.2 收尾)* §4 契约 C3 + §9 OQ 7 | `200 + in_flight=true` vs `409`"由实施者二选一 / 推荐 200" | **锁定 `200 + flags.in_flight=true`**；C3 正文即终决，OQ 7 降级为历史记录 | 与 §6 实施步骤 6、§3 集成测试、§8 验收文案一致（后文早已全部按 `200` 在写） |
| *(v2.2 收尾)* Session lookup 语义 | 阶段 1 路由流程直接写 `session_manager.get(session_key)`，但 live `SessionManager` 并无该公开 lookup API；若改用 `get_or_create()` 又会破坏未知 session → `404` 契约 | 明确在 `nanobot/session/manager.py` 新增公开只读 `get(key) -> Session \| None`；端点与文件清单统一改为使用该 lookup，避免 HTTP 层依赖私有 `_load()` | `session/manager.py:123-143` 当前仅有 `get_or_create()` / `_load()`；context-preview API 集成测试已要求非法 `session_key` 返回 `404` |
| *(v2.2 收尾)* Block parity × image omission | C8 / 阶段 3 把 `content_blocks` 写成"与 runtime 原始 list 原样相等"，同时 C10 又规定 `image_url.url` 永远 omitted，前端还要求显示缩略图，三者互相冲突 | 将 `content_blocks` 定义为 **preview-safe transformed blocks**：strict parity 对齐的是"runtime 原 blocks 经相同截断 / 脱敏 / image omission 变换后的结果"；前端 image block 降级为 MIME + 字节数占位，不渲染真实缩略图 | 与 C10 的安全边界一致；同时让 §6 实施、§7 文件清单、§3 block 测试口径闭环 |

### v2 → v2.1（2026-04-21，Codex 二轮评审后）
| 修订点 | v2 | v2.1 | 证据 |
|---|---|---|---|
| Tool schema 来源 | `provider._get_tool_definitions()`（方法不存在，会让实施者追一个鬼方法） | **`agent_loop.tools.get_definitions()`**（`ToolRegistry.get_definitions`） | `registry.py:48`, `loop.py:237` 把它作为 callable 传给 Consolidator；`runner.py:576,916` 下发时同样调用 |
| i18n 路径 | `webui/src/locales/{zh,en}.json`（路径不存在，会生成永远不被加载的死文件） | **`webui/src/i18n/locales/<locale>/common.json`**；en + zh-CN 完整翻译，其余 7 个 locale（es / fr / id / ja / ko / vi / zh-TW）先拷 en 占位 | `ls webui/src/i18n/locales/` 实测 9 个目录 |
| Message content 类型 | 建模为纯 string，含图像/tool_result 时 parity 不可达 | **契约 C8**：`content_type: "text" \| "blocks"` + `content_blocks` 原值透传；parity test 按 content_type 分支断言 | `context.py:93-104` `_merge_message_content` 返回 `str \| list[dict]`；`loop.py:879,903` `_save_turn` 含 list 分支；`helpers.py:302-340` tokenizer 含 list 分支 |

### v1 → v2（2026-04-21，Codex 一轮评审后）
| 修订点 | 原 v1 | 新 v2 | 证据 |
|---|---|---|---|
| History 上限 | `Session.get_history(500)` | `max_messages=0`（全量 sentinel） | `loop.py:731`, `memory.py:426` |
| Totals 计算 | `grand_total = system + history + runtime` | 新增 `tool_tokens`，`request_total_tokens` 含工具 schema；UI 明示"含 tools" | `loop.py:423-425` 传 `tools=self.tools`，`helpers.py:324` 已计入 |
| Idle vs in-flight | 未区分 | 引入 `scope: "idle_baseline"`，`_pending_queues` 存在时附 `in_flight: true`；明确不覆盖 mid-turn 状态 | `loop.py:395-420`, `loop.py:480-499` |
| system_sections 形状 | "6 段全部可见" | **Sparse array**，可能仅 `identity`；UI `sections.map` 渲染 | `context.py:36-61` 条件省略 |
| Full content 契约 | `full_content_hash` + `?full=1` 混用 | **仅** `?full=0/1` 整 payload 切换；**不**做逐条寻址 | 简化闭环，避免 v1 契约歧义 |
| Utilization 分母 | 裸 `context_window` | `ctx_budget = context_window - max_completion - 1024` | `helpers.py:423-424` + `/status` 口径 |
| 入口 | "Token 页" | thread header 🧾 抽屉，无新路由 | `webui/src/App.tsx:150` 单 Shell |
| i18n | 未提 | 所有新文案走 `useTranslation()` + `zh.json/en.json` 新命名空间 | 现有 webui 多语言规范 |
| Source attribution | 无 | 头部 `observed sibling .../nanobot HEAD=68466b1c...` | `.specanchor/global/coding-standards.spec.md:25` |

### v1（2026-04-21 初稿）
- 基于 5 个研究 Agent + 1 个评审 Agent 的共识形成。
- 首轮修正：API 路由改落 `channels/websocket.py`；明确 `_build_runtime_context` 必须纳入预览；明确 "Recent History" ≠ session history；明确 workspace 级事件 fan-out；补充 provider 差异与流式场景处理。
