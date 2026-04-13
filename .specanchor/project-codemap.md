# Project Codemap

## 当前阶段

仓库刚初始化，目标是承接 Ava 从现有 `nanobot__ava` 项目中的迁移，并把 Ava 收敛成一个可面向多类 agent 记忆系统适配的独立仓库。

## 预期目录

- `ava/`: Ava 核心代码
- `ava/core/`: 未来可复用的记忆管理与迁移基础能力
- `ava/adapters/`: 各类 agent / memory runtime 的适配层
- `console-ui/`: 当前迁移期保留的 Console 前端
- `bridge/`: 当前迁移期保留的桥接进程
- `tests/`: 核心能力与适配层验证

## 当前治理重点

- 先收紧全局边界，不预写具体 module spec
- 将 nanobot 降为首个 reference adapter，而不是唯一目标
- 保留当前 console 与主要行为面，避免迁移期功能回退
