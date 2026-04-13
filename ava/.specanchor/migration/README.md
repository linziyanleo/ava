# Ava Migration Bootstrap

这组文档服务于一个特殊场景：

- 后续在新对话中只带入 `ava/` 子树内容
- agent 需要在缺少仓库根级 `.specanchor/` 上下文的情况下继续迁移工作

## 阅读顺序

1. `HANDOFF.md`
   - 先读不可变决策、项目目标、非目标
2. `ADAPTER_CONTRACT.md`
   - 再读 core / adapter 的抽象边界
3. `MIGRATION_MANIFEST.md`
   - 最后读哪些 `ava/` 外内容需要在什么条件下迁入
4. `EXECUTE_CHECKPOINTS.md`
   - 看当前推荐的实现顺序与停顿点

## 当前定位

- `ava` 是独立开发真源
- 当前迁移来源是 `nanobot__ava`
- `nanobot` 只是首个 reference adapter，不是唯一目标
- 当前要优先保住 console 与主要行为链路，不提前写死未来 module 结构

## 使用方式

如果新对话只带 `ava/` 内容，优先依据本目录文档做判断；
不要假定仓库根级 `.specanchor/`、`console-ui/`、`bridge/`、`tests/`
一定已经被同时带入。
