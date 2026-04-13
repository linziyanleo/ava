# Execute Checkpoints

## 当前推荐顺序

### Checkpoint 1: 仓库边界

- 明确哪些内容必须留在 `ava/`
- 明确哪些内容暂时留在 `ava/` 外
- 为旧路径准备 shim / alias 策略

完成标准：
- 不再把 `nanobot` 当成唯一目标
- 不再把未来 module 结构写死

### Checkpoint 2: Core 抽象

- 收敛 memory / history / persistence / adapter 最小契约
- 把宿主特定实现与 Ava Core 抽象分开描述

完成标准：
- 能说清 core 负责什么，adapter 负责什么
- 还不需要写实现级 Module Spec

### Checkpoint 3: 首个 Reference Adapter

- 以 `nanobot` 为首个 reference adapter 进行迁移
- 保住当前主要行为链路

完成标准：
- console、commands、skills/bootstrap、onboard、channel/transcription 不发生预期外回退

### Checkpoint 4: 迁移验证闭环

- 引入必要的 `tests/`、`console-ui/`、`bridge/`
- 建立最小集成测试基线

完成标准：
- 不再依赖“感觉应该没坏”

## 当前停顿点

如果下一位 agent 不确定该先做什么，默认从 Checkpoint 1 开始，而不是直接写实现代码。
