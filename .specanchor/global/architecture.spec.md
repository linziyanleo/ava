---
specanchor:
  level: global
  type: architecture
  version: "0.1.0"
  author: "fanghu"
  reviewers: []
  last_synced: "2026-04-13"
  last_change: "收紧架构边界：面向多 Agent 记忆系统适配，nanobot 仅为首个 reference adapter"
  applies_to: "**/*"
---

# 架构约定

## 总体边界
- Ava 是独立仓库，目标是承接跨 agent 的记忆管理与适配能力
- `nanobot` 是首个迁移来源与 reference adapter，不是唯一目标
- 当前阶段优先保持现有 console 与主要行为面不变

## 分层原则
- `ava.core.*`: 记忆管理、历史处理、迁移辅助、通用契约等可复用能力
- `ava.adapters.*`: 面向不同 agent / memory runtime 的适配层
- `console-ui/` 与 `bridge/` 当前继续保留，先服务迁移，不提前抽象成通用产品面

## 当前特殊约束
- 当前不预写实现级 Module Spec，避免在核心抽象未稳定前绑定目录与实现
- `categorized_memory` 一类能力在具体 adapter 中可能只是 projection/tool-facing layer，不能先假定它在所有运行时里都是 authoritative store
- adapter 兼容链包括 config、workspace、bootstrap、skills、commands、console、channel 等，不得在迁移中被隐式舍弃
