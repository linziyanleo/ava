---
specanchor:
  level: task
  task_name: "修复 Anthropic tool_result 结构化结果校验失败"
  author: "fanghu"
  created: "2026-04-14"
  status: "active"
  last_change: "新增 Anthropic tool_result 归一化 sidecar patch，兼容结构化 tool 输出并补回归测试"
  related_modules: []
  related_global:
    - ".specanchor/global/coding-standards.spec.md"
    - ".specanchor/global/architecture.spec.md"
  writing_protocol: "bug-fix"
  bugfix_phase: "VERIFY"
  branch: "codex/fix-token-context-snapshot"
---

# Bug Fix: 修复 Anthropic tool_result 结构化结果校验失败

## 0. Bug Report

- **报告来源**: 运行时错误日志
- **严重程度**: High
- **影响范围**: Anthropic provider 下所有带结构化 tool result 的会话续聊

## 1. Reproduce

- **复现步骤**:
  1. 使用 Anthropic provider 处理一条会触发工具调用的消息
  2. 工具返回结构化对象结果，例如 `web_fetch` 返回的 JSON dict
  3. 在同一 session 中继续发送下一条用户消息
  4. 观察模型请求失败，返回 Anthropic 400 参数校验错误
- **环境**: Ava sidecar + 外部 nanobot checkout + Telegram session `telegram:8589721068`
- **预期行为**: 历史里的 tool result 能被 Anthropic provider 转成合法的 `tool_result` block
- **实际行为**: Anthropic 返回 `messages.26.content.0.tool_result.content.0.type: Field required`
- **复现率**: 在含结构化 tool result 的会话中稳定复现

## 2. Diagnose

### 2.1 证据

- `/Users/fanghu/Documents/Test/nanobot/nanobot/providers/base.py:195-198`
  - `_sanitize_empty_content()` 会把 `dict` 内容包装成 `list[dict]`
- `/Users/fanghu/Documents/Test/nanobot/nanobot/providers/anthropic_provider.py:164-174`
  - 旧 `_tool_result_block()` 对 `list` 类型 content 直接透传，不做 Anthropic block 归一化
- `/Users/fanghu/.nanobot/workspace/data/nanobot.db`
  - `telegram:8589721068` 当前会话中存在 `web_fetch` 返回的结构化 dict tool result
- 离线复现
  - 对当前 session 走 `SessionManager._load()` + `AnthropicProvider._convert_messages()`，旧逻辑会生成 `tool_result.content = [<plain dict>]`
  - Anthropic 要求该 list 内每一项都必须显式带 `type`

### 2.2 排除项

- 不是 Token 页面压缩/截断问题
- 不是 backfill placeholder 直接写坏了历史
- 不是 history compressor 产生 orphan `tool_result`

## 3. Root Cause

- **根因**: Anthropic provider 的 `_tool_result_block()` 只把 `tool` message 的 `content` 当作字符串或原始 list 透传，没有把 `dict` / legacy block / OpenAI 风格 block 规范化成 Anthropic Messages API 可接受的 block list。

- **触发链**:
  1. tool 返回 `dict`
  2. `_sanitize_empty_content()` 把它包装成 `list[dict]`
  3. `_tool_result_block()` 直接把这个 list 放进 `tool_result.content`
  4. Anthropic 校验首项缺少 `type`，直接 400

## 4. Fix Plan

### 4.1 Fix Checklist

- [x] 1. 新增 sidecar patch，拦截 `AnthropicProvider._tool_result_block()`
- [x] 2. 将 `tool_result.content` 统一归一化为 Anthropic-safe string 或 block list
- [x] 3. 保留合法 `text` / `image` / `document` block
- [x] 4. 将 `input_text` / `output_text` / 无类型 dict 退化为 `text` block
- [x] 5. 补充覆盖真实调用链的窄测试

### 4.2 File Changes

- `ava/patches/provider_anthropic_tool_result_patch.py`
  - patch `AnthropicProvider._tool_result_block()`
  - 新增 `tool_result` content 归一化逻辑
  - patch 以 sidecar 方式生效，不直接修改外部 nanobot checkout

- `tests/patches/test_provider_anthropic_tool_result_patch.py`
  - 覆盖 patch 幂等性
  - 覆盖 string / scalar / list block 归一化
  - 覆盖真实故障链：`dict tool result -> _sanitize_empty_content() -> _convert_messages()`

### 4.3 Risk Assessment

- **回归风险**: Low
- **影响面**: 仅 Anthropic provider 的 `tool_result` 序列化
- **注意事项**: patch 需要在 Ava launcher 重新启动后才会对运行时生效

## 5. Fix Log

- 2026-04-14：确认当前运行时使用的是外部 `/Users/fanghu/Documents/Test/nanobot` checkout，且其 `AnthropicProvider._tool_result_block()` 仍为旧透传逻辑
- 2026-04-14：新增 `provider_anthropic_tool_result_patch.py`，把结构化 tool result 归一化为 Anthropic-safe blocks
- 2026-04-14：补充回归测试，覆盖直接 block 构造和完整 provider 转换链

## 6. Verify

- [x] Bug 已修复（旧逻辑离线复现，patch 后同链路输出合法 `tool_result` block）
- [x] 无回归（未改动其他 provider 序列化路径）
- [x] 验证：`PYTHONPATH=/Users/fanghu/Documents/Test/ava pytest tests/patches/test_provider_anthropic_tool_result_patch.py -q`
- [x] 验证：`git diff --check -- ava/patches/provider_anthropic_tool_result_patch.py tests/patches/test_provider_anthropic_tool_result_patch.py`
- **Follow-ups**: 如需向上游 nanobot 提 PR，可将本 patch 平移到 provider 本体，而不是长期维持 sidecar monkey patch
