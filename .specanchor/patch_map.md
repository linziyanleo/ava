# Patch Map

> 后续开发和合并 upstream 代码前，必须先对照本文件。
> 目标不是复述 patch 名称，而是快速判断：当前 patch 是继续保留、收窄、上推还是删除。

## 使用方式

### 开发 / merge 前必做

1. 拉取上游：

```bash
git fetch upstream main
```

1. 找出 upstream 这次改了哪些 `nanobot/` 文件：

```bash
git diff --name-only $(git merge-base HEAD upstream/main)..upstream/main -- nanobot/
```

1. 用下面的 patch map 对照这些改动落在哪些 patch 热区。
2. 对每个命中的 patch，按"取舍规则"判断：
   - 上游已完整覆盖：删除 patch，并同步删测试 / spec
   - 上游部分覆盖：收窄 patch，只保留 sidecar 独有逻辑
   - 上游新增基础能力而 fork 未同步：优先同步 fork / spec，不要先加白名单
   - 完全无关：保留 patch，仅回归测试
3. 变更完成后至少回归：

```bash
uv run pytest tests/patches -q
uv run pytest tests/guardrails -q
```

1. 若本次改动涉及 `nanobot/`，同步更新 `ava/UPSTREAM_VERSION`。

## 取舍规则

### `保留`

- 上游尚未覆盖该能力；
- 或该 patch 明确承载 sidecar 独有能力。

### `收窄`

- 上游已覆盖 patch 中的一部分逻辑；
- 只保留 sidecar 额外修复 / 扩展的最小差异。

### `删除`

- 上游已完整覆盖功能；
- sidecar 不再需要额外行为；
- patch 留着只会增加 merge 成本或行为分叉。

### `上推`

- 该 patch 的逻辑已被证明是通用能力；
- 且 sidecar 继续维护这段代码的成本高于提 upstream PR。

## 当前 Patch 全景

> 上次对照：upstream `c092896` (2026-04-08)

| Patch | 上游触点 | 当前职责 | 热度 | 当前判断 | 最低验证 |
|-------|----------|----------|------|----------|----------|
| `a_schema_patch` | `config/schema.py` | fork 完整替换 schema | **极高** | 保留，必须同步 | `test_schema_patch` + `test_schema_drift` |
| `b_config_patch` | `AgentDefaults` | fork 降级字段注入 | 低 | 倾向删除 | `test_config_patch` |
| `bus_patch` | `MessageBus.publish_outbound` | Console queue listener | 低 | 保留 | `test_bus_patch` |
| `c_onboard_patch` | `cli/commands.py:onboard` | refresh 兼容层 | 中 | 保留，收窄 | `test_onboard_patch` |
| `channel_patch` | `channels/telegram.py` | 消息批处理 + send_delta 剩余修复 + sidecar command handlers | 中 | 保留，stream_id 逻辑已完全回退 upstream | `test_channel_patch` |
| `console_patch` | `cli/commands.py` | gateway 启动注入 Console | **高** | 保留 | `test_console_patch` |
| `context_patch` | `ContextBuilder` + `LLMProvider.chat_*` | 历史压缩 + Personal Memory 注入去重 + 消息清洗 | **高** | 保留，负责三层去重 | `test_context_patch` |
| `loop_patch` | `agent/loop.py` + `agent/memory.py` | db/token/bg_tasks/lifecycle 注入 + Consolidator person bridge | **极高** | 保留，持续热区 | `test_loop_patch` + `test_consolidation_bridge` |
| `provider_prefix_patch` | `providers/openai_compat_provider.py` | 旧版 yunwu/zenmux 前缀兼容垫片 | 低 | 保留，等待配置迁移后删除 | `test_provider_prefix_patch` |
| `skills_patch` | `SkillsLoader` | 三源发现 + disabled filter | 低 | 保留 | `test_skills_patch` |
| `storage_patch` | `SessionManager` | SQLite 持久化 + db 共享 | 低 | 保留 | `test_storage_patch` |
| `tools_patch` | `_register_default_tools` | 8 个自定义工具注入 | **高** | 保留 | `test_tools_patch` |
| `templates_patch` | `sync_workspace_templates` | ava/templates → workspace overlay | 中 | 保留 | — |
| `transcription_patch` | `transcription.py` | Groq proxy 注入 | 低 | 保留 | `test_transcription_patch` |

### 本轮取舍详情

#### `a_schema_patch` — 保留，必须同步

upstream 新增：`DreamConfig`（依赖 `CronSchedule`）、`AgentDefaults.dream`、`WebToolsConfig.enable`、`ToolsConfig.ssrf_whitelist`、`ProvidersConfig.xiaomi_mimo`。`WebSearchConfig.provider` 默认值 `"brave"` → `"duckduckgo"`。

fork 通过 `_UPSTREAM.AgentDefaults` 继承，大部分自动吸收。需显式验证：
- `DreamConfig` 模块级 `from nanobot.cron.types import CronSchedule` 在 fork 加载时是否解析正确
- `ProvidersConfig` fork 覆盖了父类、需确认 `xiaomi_mimo` 不丢失

#### `console_patch` — 合并热点

upstream `gateway()` 参数 `web_search_config`/`web_proxy` → `web_config`。新增 Dream cron 注册和 `restart_notice` 消费。console_patch 若 callback 级包裹（不重构参数），参数透传安全；但 Dream/restart 新逻辑需确认不被包裹遮蔽。

#### `context_patch` — 变得更关键

upstream 删除 `_sanitize_history()` → `build_messages` 不再内置 trailing assistant 清理。我们的 provider 级 `sanitize_messages()` 成为唯一清理点。当前还承担 `USER.md` + `memory/MEMORY.md` + Personal Memory 的三层去重，已不是单纯的注入补丁。

#### `loop_patch` — 合并热点

upstream `__init__` 参数 `web_search_config`/`web_proxy` → `web_config`；`self.memory_consolidator` → `self.consolidator`；新增 `self.dream`；新注册 `GlobTool`/`GrepTool`。sidecar 现在还会 wrap `Consolidator.maybe_consolidate_by_tokens()` / `archive()`，把 `session.key` 保留下来并桥接到 `categorized_memory.on_consolidate()`。

`patched_init` 用 `original_init(self, *args, **kwargs)` 透传安全。ava 代码中无 `memory_consolidator` 引用。

#### `provider_prefix_patch` — 迁移垫片

仅在 sidecar OpenAI-compatible provider 缺少 ProviderSpec 时剥离 `yunwu/` / `zenmux/` 前缀。它是旧配置兼容层，不是长期 provider 规范；配置全部迁移后应直接删除。

#### `tools_patch` — 已补 TOOLS.md，但仍需继续防漂移

upstream 在 `_register_default_tools` 新增 `GlobTool`/`GrepTool`、Web 工具条件化（`if self.web_config.enable`）。`original_register(self)` 前缀调用安全。本轮已把 `glob` / `grep` 同步进 `ava/templates/TOOLS.md`，并把 `gateway_control` 注册描述与实际工具面重新对齐；后续仍需持续同步 overlay，避免再次回漂。

## 当前热区提醒

### 热区 1: `nanobot/agent/loop.py` — 极高

- 关联 patch：`loop_patch`、`tools_patch`、间接影响 `context_patch`
- 本轮变更：`MemoryConsolidator` → `Consolidator` + `Dream`；参数合并 `web_config`；新增 `GlobTool`/`GrepTool`；Web 条件化
- 策略：参数透传无冲突；持续判断能否迁到 AgentHook 层

### 热区 2: `nanobot/cli/commands.py` — 高

- 关联 patch：`console_patch`、`c_onboard_patch`
- 本轮变更：gateway 参数重构 `web_config`；Dream cron 注册；`restart_notice` 消费
- 策略：确认 console_patch 包裹不遮蔽 Dream/restart 逻辑

### 热区 3: `nanobot/config/schema.py` — 极高

- 关联 patch：`a_schema_patch`、`b_config_patch`
- 本轮变更：`DreamConfig`、`dream` 字段、`ssrf_whitelist`、`xiaomi_mimo`、`WebToolsConfig.enable`
- 策略：fork 继承验证新类；`ProvidersConfig` 覆盖确认新 provider 不丢失

### 热区 4: `nanobot/channels/telegram.py` — 中

- 关联 patch：`channel_patch`
- 本轮变更：Dream 命令注册、`_normalize_telegram_command`、polling error 缩短、stream edit interval
- 策略：batch 逻辑与新命令不冲突

### 热区 5: `nanobot/agent/context.py` + `nanobot/providers/base.py` — 高

- 关联 patch：`context_patch`
- 本轮变更：`_sanitize_history` 删除；`_build_identity` Jinja2 化；`build_messages` 简化
- 策略：provider 级 `sanitize_messages()` 现为唯一清理点，需保留

### 热区 6: `nanobot/agent/tools/base.py` — 新增

- 关联：所有 `ava/tools/*.py`
- 本轮变更：新增 `Schema` 抽象类、`tool_parameters` 装饰器、`_validate` → `Schema.validate_json_schema_value`
- 策略：自定义工具只用公开 API，不调 `_validate`，无冲突

### 热区 7: `nanobot/agent/memory.py` — 新增

- 关联：`context_patch`（通过 `self.context.memory` 引用）、`loop_patch`（Consolidator bridge）
- 本轮变更：`MemoryConsolidator` → `Consolidator` + `Dream`；`MemoryStore` 完全重写（GitStore、history.jsonl）
- 策略：`context_patch` 只读 system prompt / memory context；`loop_patch` 只在归档出口桥接 `session.key` 与新写入的 history entry，不改 upstream memory 数据结构

## 上游新增能力概览

| 新模块 / 文件 | 说明 | 对 sidecar 的影响 |
|---------------|------|-------------------|
| `agent/tools/search.py` | GrepTool + GlobTool | Agent 原生搜索，需在 `TOOLS.md` 中记录 |
| `agent/tools/schema.py` | Schema 类型系统 | `tool_parameters` 装饰器可简化自定义工具定义 |
| `utils/prompt_templates.py` | Jinja2 `render_template()` | 可复用于 sidecar 模板 |
| `utils/gitstore.py` | Git 版本控制 for memory | Dream 基础设施 |
| `utils/restart.py` | 环境变量 restart notice | 与 `LifecycleManager` 文件方案互补 |
| `templates/agent/*.md` | 11 个 Jinja2 prompt 模板 | 减少硬编码 |
| `providers/` | GPT-5 支持 + Codex provider 改动 | 自动可用 |
