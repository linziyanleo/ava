# Module Index

当前阶段暂不创建实现级 Module Spec。

原因：

- Ava 的未来目标不是只适配 `nanobot`，而是适配多种 agent 的记忆管理系统
- 目前核心边界还在收敛期，过早写死 module spec，后续会频繁返工
- 现阶段以 Global Spec + Task Spec 驱动迁移，待核心抽象和首批 adapter 稳定后，再补模块规范

后续触发条件：

- `ava.core` 的核心抽象已经稳定
- 至少一个 reference adapter 完成落地
- 关键目录和契约不再高频变动
