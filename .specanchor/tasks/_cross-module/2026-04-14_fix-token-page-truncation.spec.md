---
specanchor:
  level: task
  task_name: "修复 Token 页面对话历史显示误导问题"
  author: "fanghu"
  created: "2026-04-14"
  status: "active"
  last_change: "完成请求上下文误导修复并验证通过：snapshot 阈值配置化、前端改名并移除误导性截断统计"
  related_modules: []
  related_global:
    - ".specanchor/global/coding-standards.spec.md"
    - ".specanchor/global/architecture.spec.md"
  writing_protocol: "bug-fix"
  bugfix_phase: "VERIFY"
  branch: "codex/fix-token-context-snapshot"
---

# Bug Fix: 修复 Token 页面对话历史显示误导问题

## 0. Bug Report

- **报告来源**: 自测发现
- **严重程度**: Medium
- **影响范围**: Console UI Token 统计页面（`/tokens`）的对话历史视图

## 1. Reproduce

- **复现步骤**:
  1. 在 Telegram 上发送一条消息给 nanobot（任意长度均可触发）
  2. 打开 `http://localhost:6688/tokens` 页面
  3. 展开最近一个 turn 的调用详情
  4. 观察 iteration=0 默认展开的"对话历史"区域
- **环境**: macOS, Console UI (localhost:6688), nanobot with ava patches
- **预期行为**: 用户能明确理解所看到的内容是"发送给模型的上下文快照"，而非完整聊天记录
- **实际行为**:
  - UI 标题写"对话历史"，暗示展示的是完整对话
  - 实际数据来自 `initial_messages`（经过 summarizer + compressor 处理后的 prompt snapshot）
  - 被压缩器移除的旧 turn 完全不出现，tool 输出、`[auto-backfill]` 占位等内部结构暴露
  - "已压缩 · N 条截断" 的统计混淆了"内容被 [:200] 截断" 和 "turn 被压缩器移除"两种情况
  - iteration>0 的记录 `conversation_history` 为空（硬编码 `""`），只有 iteration=0 有快照
- **复现率**: 必现

## 2. Diagnose

### 2.1 诊断策略

- 已通过代码审查 + DB 查询完成诊断

### 2.2 诊断代码

- 无需添加诊断代码

### 2.3 证据

**后端数据流：**
- `nanobot/agent/loop.py:682` — `self.context.build_messages(history, current_message)` 构建 initial_messages
- `ava/patches/context_patch.py:142-154` — patched_build_messages 在 build 前先执行 summarizer.summarize() + compressor.compress()
- `ava/patches/loop_patch.py:472` — patched_run_agent_loop 接收已压缩的 initial_messages
- `ava/patches/loop_patch.py:497-501` — Phase 0 记录：序列化 initial_messages（过滤 system），每条 content[:200]
- `ava/patches/loop_patch.py:613-624` — iteration>0 记录：conversation_history="" 硬编码空字符串

**前端显示：**
- `console-ui/src/pages/TokenStatsPage.tsx:1627,1916` — 两处标注"对话历史"
- `console-ui/src/pages/TokenStatsPage.tsx:1853` — `record.iteration === 0` 默认展开
- `console-ui/src/components/ConversationHistoryView.tsx:22` — `CONTENT_TRUNCATE_THRESHOLD = 198`
- `console-ui/src/components/ConversationHistoryView.tsx:150` — `content.length >= 198` 判断截断

**Summarizer 的影响：**
- `ava/agent/history_summarizer.py:160` — tool result 也会被截断到 tool_result_max_chars（默认 200 字符）
- 这意味着不需要"用户消息 >200 字符"也能触发前端的"已截断"标记（tool result 被 summarizer 截断到恰好 200 字符 → >=198 → 标记截断）

### 2.4 证据分析

**核心问题：数据契约错位**

`conversation_history` 字段存储的是 **prompt snapshot**（发送给模型的上下文），不是 **authoritative chat history**（完整聊天记录）。Token 页面却把它标为"对话历史"展示给用户。

这个错位导致三个表象问题：
1. 被压缩器移除的旧 turn 消失，用户以为是 bug
2. tool 输出、auto-backfill 占位等内部结构暴露，用户困惑
3. "已压缩 · N 条截断" 文案混淆了两种完全不同的截断机制

## 3. Root Cause

- **根因**: `conversation_history` 字段的语义是 "prompt snapshot"（模型输入快照），但前端把它当 "chat history"（聊天历史）展示和命名。

  具体包含三个层面：

  **A. 数据来源错位**:
  `loop_patch.py:497` 序列化的是 `initial_messages`，这是经过 `HistorySummarizer` + `HistoryCompressor` 处理后、即将发送给模型的消息列表。它不是聊天记录，而是模型输入上下文。

  **B. 显示入口绑定 iteration=0**:
  快照只在首条调用记录（Phase 0, iteration=0）写入。后续 iteration 的 `conversation_history` 为空字符串（`loop_patch.py:624`）。前端 `TurnCallEntry` 默认展开 iteration=0（`TokenStatsPage.tsx:1853`），用户看到的永远是"首轮模型调用前的上下文"。

  **C. 前端标记阈值错位（次要）**:
  后端 `[:200]` 截断 vs 前端 `>=198` 判断，存在 2 字符的假阳性窗口。且 summarizer 本身会把 tool result 截到 200 字符，进一步扩大误报面。

- **证据链**: 见 §2.3
- **为什么之前正常**: 不是回归，是功能设计时的语义定义不够明确

## 4. Fix Plan

**核心决策：先止血（改名 + 对齐阈值），不做大重构**

目标是"别再误导用户"，而非"在 Tokens 页看到真实聊天历史"。后者需要改成按 `session_key + conversation_id + turn_seq` 读 `session_messages`，是另一个更大的任务。

### 4.1 Fix Checklist

- [x] 1. 后端 config：在 `TokenStatsConfig` 中新增 `snapshot_content_max_chars: int = 3000` 字段
- [x] 2. 后端 loop_patch：读取 config 中的阈值替换硬编码 `[:200]`
- [x] 3. 前端改名：将"对话历史"改为"请求上下文（发送给模型前的快照）"
- [x] 4. 前端文案：移除"已压缩 · N 条截断"这类误导性统计
- [x] 5. 前端逻辑：统一 user/assistant 折叠阈值为同一套判定，消除 198/200/300 三套阈值并存

### 4.2 File Changes

- `ava/forks/config/schema.py` — `TokenStatsConfig`:
  - 新增字段 `snapshot_content_max_chars: int = 3000`
  - 含义：Phase 0 记录 conversation_history 时，每条消息 content 的最大保留字符数
  - 默认 3000，支持 `token_stats.snapshot_content_max_chars` / `token_stats.snapshotContentMaxChars` 覆盖

- `ava/patches/loop_patch.py`:
  - L497-501 区域：从 ava config 读取 `token_stats.snapshot_content_max_chars` 替换硬编码 `[:200]`
  - 读取方式：新增 helper 安全读取 `nanobot.config.loader.load_config()`，失败时 fallback 到 3000
  - fallback：读取失败时 fallback 到 3000

- `console-ui/src/pages/TokenStatsPage.tsx`:
  - L1629: `对话历史:` → `请求上下文（发送给模型前的快照）:`
  - L1918: `对话历史` → `请求上下文（发送给模型前的快照）`

- `console-ui/src/components/ConversationHistoryView.tsx`:
  - 删除 `CONTENT_TRUNCATE_THRESHOLD = 198` 常量
  - `UserBubble` / `AssistantBubble`: 统一使用 500 字符阈值判断是否折叠显示
  - badge 文案：`已截断` → `已折叠`
  - `stats.truncatedCount`: 直接移除，避免把 prompt 压缩与 UI 折叠混为一谈
  - `StatsBar`: 改为展示用户消息数 / 助手消息数 / 工具调用数，不再展示“已压缩”状态

### 4.3 Risk Assessment

- **回归风险**: Low — 仅 UI 文案/显示阈值变更 + config 新增默认值字段，不影响 LLM 对话逻辑和 token 计量
- **影响的其他功能**:
  - conversation_history 字段的 JSON 结构不变，只是每条 content 更长（3000 vs 200）
  - DB 存储空间会略增（每条记录的 conversation_history 字段变大），但 token_usage 表的增长在可接受范围
- **需要额外测试的场景**:
  - Token 页面 turn 展开后标题显示"请求上下文"
  - 长消息的折叠/展开功能正常
  - config.json 中 `token_stats.snapshot_content_max_chars` 自定义值生效
  - 无 config 时 fallback 到默认值 3000

### 4.4 Future Work（不在本次范围）

- 在 Tokens 页增加"查看完整聊天历史"入口，从 `session_messages` 表按 `session_key + conversation_id + turn_seq` 读取真实历史
- 在 prompt snapshot 中嵌入压缩元信息（原始消息数、被移除的 turn 数）

## 5. Fix Log

- 2026-04-14：在 `TokenStatsConfig` 中新增 `snapshot_content_max_chars`，并接入 `loop_patch.py` 的 Phase 0 snapshot 序列化逻辑，去掉 `[:200]` 硬编码
- 2026-04-14：将 Tokens 页两处标题统一改为“请求上下文（发送给模型前的快照）”，显式说明该区域不是完整聊天历史
- 2026-04-14：重写 `ConversationHistoryView` 的折叠逻辑，统一 user/assistant 预览阈值为 500，并移除误导性的“已压缩 · N 条截断”统计
- 2026-04-14：补充 schema / onboard / loop_patch 窄测试，覆盖默认值、旧配置保留、config 读取与 fallback

## 6. Verify

- [x] Bug 已修复（Token 页面不再误导用户把 prompt snapshot 当聊天历史）
- [x] 无回归（Token 页面其他功能正常）
- [x] 诊断代码已清理（本次无诊断代码）
- [x] Module Spec 是否需更新: No（当前阶段无 Module Spec）
- [x] 验证：`PYTHONPATH=/Users/fanghu/Documents/Test/ava pytest tests/patches/test_schema_patch.py tests/patches/test_onboard_patch.py tests/patches/test_loop_patch.py -q`
- [x] 验证：`cd console-ui && npm exec -- tsc -b`
- [x] 验证：`git diff --check`
- **Follow-ups**: 评估是否需要在 Tokens 页增加真实聊天历史查看能力（需读 session_messages 表）
