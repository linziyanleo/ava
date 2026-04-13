# Adapter Contract

## Core 要负责什么

当前只锁定抽象，不锁定实现文件。

Core 负责的方向：

- 记忆对象模型
- memory projection / sync / recall 语义
- 历史处理与裁剪语义
- 持久化与迁移语义
- 适配不同宿主 runtime 的最小契约
- 背景任务 / 状态机里可复用的部分

## Adapter 要负责什么

Adapter 负责把宿主运行时接上 Ava Core。

Adapter 典型职责：

- memory / session / prompt / tool 生命周期接入
- config / workspace / bootstrap / skills / commands 兼容链
- console、channel、bus、observe 等产品面 wiring
- patch、shim、bridge、fallback

## 不能先假定的事情

- 不能先假定某个宿主的 memory store 就是 Ava 的全局真源
- 不能先假定 `categorized_memory` 这类能力在所有宿主里都扮演同一角色
- 不能先假定所有 adapter 都共享同一套文件布局
- 不能先假定 console 一定属于 core

## 当前 reference adapter 规则

以 `nanobot` 为首个 reference adapter 时：

- 要优先保持当前 console 与主要行为链路稳定
- 适配层需要承接 config / workspace / bootstrap / commands / skills / channel / transcription 等兼容面
- 任何 adapter-specific 行为，只要当前用户可见能力依赖它，就不能在迁移期被隐式舍弃

## 什么时候可以开始补 Module Spec

满足以下条件后，再考虑补实现级 Module Spec：

1. Core 与 adapter 的抽象边界稳定
2. 至少一个 reference adapter 已经跑通
3. 关键目录和契约不再高频变动
4. 新增 Module Spec 不会在短期内因为目录重组被整体推翻
