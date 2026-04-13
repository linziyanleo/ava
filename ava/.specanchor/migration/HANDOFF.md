# Handoff

## 不可变决策

- 项目名称就是 `ava`
- Ava 的长期目标是适配多类 agent 的记忆管理系统
- 当前迁移来源是 `nanobot__ava`
- `nanobot` 只是首个 reference adapter
- 当前阶段不预写实现级 Module Spec
- 当前阶段优先保住现有 console、commands、skills/bootstrap、onboard、channel/transcription 等行为面

## 当前阶段真正要做的事

- 把 Ava 从现有 `nanobot__ava` 项目中收敛为独立开发真源
- 提炼可复用的 memory / history / persistence / adapter contract 抽象
- 在不破坏当前主要行为的前提下，为后续多 adapter 演进打基础

## 当前阶段不要做的事

- 不要把 `nanobot` 当成 Ava 的唯一宿主
- 不要先画完整最终目录图，再逼实现去适配
- 不要为了“看起来更通用”而提前重写 console
- 不要先把 patch 数量、module 数量、包数量当作 KPI
- 不要先补实现级 Module Spec

## 当前判断原则

遇到设计取舍时优先按这个顺序判断：

1. 是否破坏当前用户可见行为
2. 是否把 `nanobot` 的局部现实误写成全局真理
3. 是否会让未来第二个 adapter 更难落地
4. 是否只是结构好看，但没有真实迁移价值

## 当前已知风险

- 如果只带 `ava/` 子树，新对话天然缺少根级 SpecAnchor 上下文
- 当前很多行为链仍依赖 `ava/` 外的 `console-ui/`、`bridge/`、测试与迁移参考材料
- 若没有迁移触发表，agent 很容易在“先迁什么、什么时候拉外部目录”上漂移
