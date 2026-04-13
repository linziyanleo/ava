---
specanchor:
  level: task
  task_name: "Ava 迁移基线——面向多 Agent 记忆系统适配的独立仓库收口"
  author: "@方壶"
  assignee: "@方壶"
  reviewer: "@方壶"
  created: "2026-04-13"
  status: "active"
  last_change: "补充仓库发布基线：新增根 README、MIT LICENSE，并准备在 linziyanleo/ava 下初始化公开仓库"
  related_global:
    - ".specanchor/global/architecture.spec.md"
    - ".specanchor/global/project-setup.spec.md"
    - ".specanchor/global/coding-standards.spec.md"
  flow_type: "standard"
  writing_protocol: "sdd-riper-one"
  sdd_phase: "EXECUTE"
  branch: "feat/ava-monorepo-extraction"
---

# SDD Spec: Ava 迁移基线——面向多 Agent 记忆系统适配的独立仓库收口

## 0. Decisions Locked

- 仓库名统一为 `ava`
- Ava 的目标是适配多类 agent 的记忆管理系统，不绑定单一运行时
- 当前 Execute 以 `nanobot__ava` 为迁移来源，但 `nanobot` 只是首个 reference adapter
- 当前 `console-ui`、`ava.console`、slash commands、skills/bootstrap、onboard、channel/transcription 等用户可见行为默认保持不变
- 当前阶段不预写实现级 Module Spec，待核心抽象和首个 adapter 稳定后再补
- 本阶段不强推具体 adapter 目录或 patch 收敛数字，先把核心边界和迁移顺序锁定

## 1. Requirements (Context)

- **Goal**: 将当前仓库收敛成 Ava 的独立开发真源，为后续适配多类 agent 的记忆管理系统打下统一迁移基线；当前以 `nanobot__ava` 为首个迁移来源，并尽量保持现有 console 和主要功能链路稳定
- **In-Scope**:
  - 重新定义 Ava 的仓库边界、核心抽象边界、适配层边界
  - 将 `nanobot` 重新定位为首个 reference adapter，而不是唯一适配对象
  - 收紧当前迁移期的全局约束，避免过早固化具体 module 设计
  - 保持当前 console、commands、skills/bootstrap、onboard、bus/observe、channel/transcription 行为面不变
  - 规划兼容迁移策略（shim / alias / 兼容入口）
- **Out-of-Scope**:
  - 立即发布完整多 adapter 产品
  - 为所有未来 adapter 提前定义实现级模块图
  - 重写 Console Web UI 或 FastAPI 后端
  - 立即引入完整 `ava.config.json` 体系或 MCP 产品化方案
  - 在本轮任务中直接完成所有代码迁移

- **Schema**: sdd-riper-one（当前项目迁移优先，先锁定可执行边界）

## 1.1 Context Sources

- Requirement Source: 用户本轮新增约束
  - “先做当前项目的迁移”
  - “Ava 成为单独的外挂层”
  - “项目直接叫 ava”
  - “nanobot 不是唯一要适配的对象，需要适配各类 agent 的记忆管理系统”
  - “先不要写具体的 module spec 文件”
- Repo Refs:
  - `ava/launcher.py`
  - `ava/patches/console_patch.py`
  - `ava/patches/context_patch.py`
  - `ava/patches/loop_patch.py`
  - `ava/patches/templates_patch.py`
  - `ava/agent/bg_tasks.py`
  - `ava/agent/commands.py`
  - `.specanchor/patch_map.md`

## 2. Research Findings

### 2.1 这次迁移真正要解决的问题

当前最大的问题不是“包名不够优雅”，而是三件事混在一起：

1. **Ava 的可复用能力**
   - 例如 `categorized_memory`、`history_*`、`Database`、`page_agent`、`bg_tasks` 的部分状态机

2. **reference adapter 与兼容层**
   - 当前首个来源是 `nanobot__ava`
   - 但长期需要适配的是不同 agent 的 memory/session/prompt/tool runtime

3. **当前产品面**
   - 例如 `ava.console`、`console-ui`、mock runtime、gateway 联动

旧版 spec 最大的问题是试图在同一阶段同时完成：
- repo 抽离
- 通用产品抽象
- patch 大收缩
- 新 config 体系

这会让“当前项目迁移”变成“提前承诺最终实现”。

### 2.2 当前应先按三类边界理解

#### A. Ava Core 关心的抽象能力

- 记忆模型与同步语义
- 历史处理与裁剪语义
- 持久化与迁移能力
- 对不同 agent memory runtime 的适配契约
- 背景任务与状态机中可复用的部分

#### B. reference adapter 负责的能力

- 对宿主 runtime 的 memory/session/prompt/tool 生命周期接入
- config / workspace / bootstrap / skills / commands / channel / console 兼容链
- 与宿主特定运行时相关的 patch、shim、bridge 与 fallback

#### C. 当前产品面，Phase 1 默认不重构

- `ava.console/*`
- `console-ui/*`
- `bridge/*`
- mock runtime / 本地 console 用户体系

### 2.3 Phase 1 的关键约束

1. **保持行为稳定优先于抢先抽象**
   - 当前 console 和主要功能面必须先保住

2. **先收敛 core / adapter 边界，再决定 module 结构**
   - 否则所有“模块规范”都会被后续实现反复打回

3. **当前以首个 reference adapter 的迁移闭环为准**
   - 不是先为未来所有 adapter 画完整最终结构

4. **config / workspace / bootstrap 不能先重做**
   - 否则 `onboard`、workspace 文件、skills、console、旧用户环境都会一起炸

5. **暂不写实现级 Module Spec**
   - 先用 Global + Task 驱动，等核心边界稳定再补

## 3. Innovate (Options & Decision)

### Option A: 现在就写死最终 module/map

**结论**: 不选。  
理由：未来要适配多类 agent 记忆系统，当前没有足够稳定的实现边界支撑具体 module spec。

### Option B: 先收紧 Ava 的 global/task 规范，按 reference adapter 迁移

- Ava 成为独立维护的 repo
- `nanobot__ava` 是首个迁移来源
- `nanobot` 降为首个 reference adapter
- 先定义 core vs adapter 的抽象边界，不预写 module spec

**结论**: 选这个。  
理由：
1. 最符合当前迁移目标
2. 能避免未来 adapter 扩张时反复改规范
3. 让 Spec 先治理方向与边界，而不是提前绑定实现目录

## 4. Plan (Contract)

### 4.0 目标架构：独立 Ava Repo + Core / Adapters 分层

> 这里描述的是方向，不是实现级 module 承诺。

```text
ava-repo/
├── pyproject.toml
├── README.md
├── ava/
│   ├── core/                         ← 未来可复用的记忆管理与迁移能力
│   ├── adapters/                     ← 各类 agent / memory runtime 的适配层
│   ├── console/                      ← 迁移期保留
│   └── ...
│
├── console-ui/                       ← 迁移期保留
├── bridge/                           ← 迁移期保留
└── tests/
```

### 4.1 Repo 边界与 reference adapter 策略

#### 4.1.1 Ava 是真仓库

- `ava` 是新的开发真源
- 当前迁移来源是 `nanobot__ava`
- 后续可以陆续补充更多 reference adapter

#### 4.1.2 `nanobot` 的定位

- `nanobot` 是首个 reference adapter
- 当前迁移阶段仍要保留对 `nanobot` 行为面的兼容
- 但 Spec 不再围绕“nanobot 是唯一宿主”来写

### 4.2 当前阶段只锁定抽象边界，不锁定 module 设计

#### 4.2.1 Ava Core 需要锁定的抽象

- 记忆对象模型
- memory projection / sync / recall 语义
- 历史处理与裁剪
- 持久化与迁移语义
- 与 adapter 交互的最小契约

#### 4.2.2 Adapter 需要锁定的抽象

- 如何接入宿主 memory runtime
- 如何接入 prompt / session / tool / console 生命周期
- 哪些兼容链必须保行为稳定

#### 4.2.3 当前明确不锁定的内容

- 具体 package / module 命名
- 具体文件归属
- 不同 adapter 是否共享同一实现
- 哪些 helper 最终落在 core，哪些落在 adapter

### 4.3 Console 与产品面的处理

本阶段明确：

- `ava.console` 保持现有结构与行为
- `console-ui` 保持现有目录与联调方式
- `bridge/` 保持现状
- Console 当前是迁移期要保住的产品面
- 它不定义 Ava 的长期核心抽象
- 当前也不提前承诺它最终属于哪一类 adapter 共享能力

### 4.4 Config / Workspace / Bootstrap 策略

#### 4.4.1 Config

- 当前迁移阶段继续兼容现有配置与 bootstrap 行为
- 不急于定义最终统一 config 体系
- config 规范要服务多 adapter 目标，不能先写成 nanobot 专用 schema

#### 4.4.2 Workspace / Bootstrap

- 继续沿用当前 workspace bootstrap 约定
- `TOOLS.md` 仍是允许强制同步的运行时事实面
- `AGENTS.md / SOUL.md / USER.md` 继续默认补缺，不做全量覆盖
- 这条 contract 属于 adapter 行为，不能从 checklist 中遗漏

#### 4.4.3 Onboard / Refresh

- `c_onboard_patch` 对旧用户配置的兼容行为仍属于 Phase 1 必保功能
- 只有在明确放弃 legacy config 兼容时，才允许把它降级成一次性 migration script

### 4.5 当前迁移策略

- 以“迁移来源可持续收口”为优先，不以 patch 数量或 module 数量为 KPI
- 先把全局规则和任务边界收紧，再在实现期决定哪些逻辑真正沉到 core
- 任何 adapter-specific 兼容行为，只要当前用户可见行为依赖它，就不能先从规范里删掉

### 4.6 兼容迁移策略

为降低当前项目迁移风险，本阶段允许使用 compatibility shim：

- 旧路径可通过 shim 维持兼容
- 先保证：
  - import 不炸
  - console 不炸
  - tests 能逐步迁移

而不是一开始就追求“结构一次性定死”。

### 4.7 测试与验收

本阶段验收重点不是“包设计优雅”，而是：

1. `python -m ava` 仍能启动当前 Ava 能力
2. console 可正常联动 gateway
3. commands / skills / bootstrap / onboard / channel / transcription 行为不回退
4. 首个 reference adapter 的集成测试能快速暴露断点

建议验证分层：

- `tests/core/`
- `tests/integration_reference_adapter/`

### 4.8 Implementation Checklist

- [ ] 1. 把任务目标改写为“当前项目迁移优先”，停止把本阶段绑定到跨框架产品化
- [ ] 2. 明确 Ava 是独立开发真源，`nanobot__ava` 是当前迁移来源而不是最终边界定义者
- [ ] 3. 将 `nanobot` 重写为首个 reference adapter 的定位，而不是 Ava 的唯一宿主
- [ ] 4. 维持当前入口与行为兼容，避免 console 与主要使用链路回退
- [ ] 5. 收紧 `ava.core` 与 `ava.adapters` 的抽象边界，但不提前落地实现级 Module Spec
- [ ] 6. 把记忆管理语义与具体宿主 runtime 分离，避免把某一运行时的 memory store 当成全局真源
- [ ] 7. 将 `commands / skills / bootstrap / TOOLS.md / onboard` 明确列为迁移期兼容链，不得遗漏
- [ ] 8. 将 `bus observe / console listener / channel / transcription` 明确列为首个 reference adapter 的兼容 contract
- [ ] 9. 保留当前 console backend + console-ui 的主要行为，不做重构，只做迁移期承接
- [ ] 10. 当前阶段继续兼容现有 config / workspace / bootstrap 约定，推迟统一 config 设计
- [ ] 11. 为现有路径设计 shim / alias，避免一次性搬目录导致入口与测试同时破裂
- [ ] 12. 建立首个 reference adapter 的集成测试基线
- [ ] 13. 删除当前过早写死的实现级 Module Spec，待核心抽象稳定后再补
- [ ] 14. 同步更新 `.specanchor` 文档，使其服务多 Agent 记忆系统适配方向

## 5. Execute Log

- 2026-04-13：已在 `/Users/fanghu/Documents/Test/ava` 初始化独立 Git 仓库，并切到 `feat/ava-monorepo-extraction`
- 2026-04-13：已完成 SpecAnchor full 模式初始化，创建 `anchor.yaml`、`.specanchor/` 目录、最小 Global Spec 与扫描脚本
- 2026-04-13：已统一仓库命名为 `ava`
- 2026-04-13：已根据未来方向收紧 Spec：`nanobot` 降为首个 reference adapter，暂停实现级 Module Spec
- 2026-04-13：已补充 `ava/.specanchor/migration/` 自举文档，供后续只带 `ava/` 子树内容的新对话继续迁移工作
- 2026-04-13：已新增 `ava/AGENTS.md`，说明 `ava/.specanchor/` 的子树自举架构、阅读顺序与何时必须拉入 `ava/` 外内容
- 2026-04-13：已新增根目录 `README.md`，使用简短介绍说明 Ava 当前是面向多 Agent 的记忆管理与适配仓库
- 2026-04-13：已新增根目录 `LICENSE`，当前采用 MIT 许可证，为公开初始化仓库做准备
- 2026-04-13：已在 GitHub 创建公开仓库 `linziyanleo/ava`，后续以 `main` 作为默认公开基线分支

## 6. Review Verdict

（待 Execute 完成后填写）

## 7. Plan-Execution Diff

（待 Execute 完成后填写）
