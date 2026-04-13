# AGENTS.md

本文件服务于一个特定场景：

- 后续可能在新对话中只带入 `ava/` 子树内容
- agent 无法天然看到仓库根级 `.specanchor/`
- 因此需要在 `ava/` 内部保留一套最小但可自举的规范入口

## 先理解 `ava/.specanchor/` 的整体架构

当前 `ava/.specanchor/` 不是完整的项目级 SpecAnchor 体系，而是一个**子树自举层**。

它的作用不是替代仓库根级 `.specanchor/`，而是为只带 `ava/` 内容的新对话提供：

- 项目目标与非目标
- core / adapter 抽象边界
- `ava/` 外候选迁移面的触发条件
- 当前 Execute 阶段的推荐顺序

换句话说：

- **仓库根级 `.specanchor/`**：完整治理层，面向整个 repo
- **`ava/.specanchor/`**：子树自举层，面向只带 `ava/` 内容的后续开发对话

## 当前目录结构

当前 `ava/.specanchor/` 下只有一个子目录：

- `migration/`

这是有意为之，不是缺失。

原因：

- 当前阶段还没有稳定到可以写实现级 Module Spec
- Ava 的长期目标是适配多类 agent 的记忆管理系统
- 如果现在就把具体 module/file 结构写死，后续很容易整体返工

因此当前策略是：

- 先用 migration 文档锁定方向和边界
- 等 core / adapter 抽象稳定后，再补实现级 Module Spec

## 阅读顺序

进入 `ava/` 子树开发时，默认按下面顺序读取：

1. `ava/.specanchor/migration/README.md`
   - 了解这套子树自举文档是干什么的
2. `ava/.specanchor/migration/HANDOFF.md`
   - 读取不可变决策、当前阶段要做什么和不要做什么
3. `ava/.specanchor/migration/ADAPTER_CONTRACT.md`
   - 理解 core / adapter 抽象边界
4. `ava/.specanchor/migration/MIGRATION_MANIFEST.md`
   - 判断什么时候必须把 `ava/` 外的内容一起迁入
5. `ava/.specanchor/migration/EXECUTE_CHECKPOINTS.md`
   - 确认当前推荐的执行顺序和停顿点

## 当前工作的默认规则

- 不要把 `nanobot` 当成 Ava 的唯一宿主
- 不要提前写死实现级 Module Spec
- 不要为了结构好看而提前重写 console
- 遇到需要判断“要不要迁 `ava/` 外内容”时，先看 `MIGRATION_MANIFEST.md`
- 遇到需要判断“这个能力属于 core 还是 adapter”时，先看 `ADAPTER_CONTRACT.md`
- 如果不知道下一步该做什么，先看 `EXECUTE_CHECKPOINTS.md`

## 什么时候需要跳出 `ava/` 子树

如果任务涉及以下任一类内容，就不要假定只看 `ava/` 足够：

- `console-ui/` 的页面行为或构建链
- `bridge/` 的 Node 桥接或 runner
- 集成测试 / 回归测试基线
- 旧 patch 热区回溯
- workspace bootstrap / 模板同步的真实行为验证

这些场景下，按 `ava/.specanchor/migration/MIGRATION_MANIFEST.md` 的说明决定需要把哪些外部目录一起迁入。

## 当前边界说明

当前 `ava/AGENTS.md` 只做**导航与边界说明**，不承载实现级规范。

后续如果出现以下条件，才考虑继续扩展 `ava/.specanchor/`：

- Core 与 adapter 的抽象边界已经稳定
- 至少一个 reference adapter 已经跑通
- 新增规范不会因为目录重组而立即失效
