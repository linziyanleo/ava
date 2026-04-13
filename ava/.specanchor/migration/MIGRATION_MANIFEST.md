# Migration Manifest

这份清单回答两个问题：

1. 只带 `ava/` 子树时，哪些东西暂时可以不迁？
2. 什么条件下，必须把 `ava/` 外的内容一起拉进来？

## 候选迁移面

| 路径/对象 | 当前状态 | 什么时候必须迁入 | 不迁入的代价 |
| --- | --- | --- | --- |
| `console-ui/` | 暂留在 `ava/` 外 | 需要改 Console 页面行为、接口契约、构建链 | 只能做后端/抽象层迁移，不能闭环验证 UI |
| `bridge/` | 暂留在 `ava/` 外 | 需要改 Node 桥接、浏览器 runner、前后端协同 | Page-agent / bridge 相关行为无法完整验证 |
| `tests/` | 暂留在 `ava/` 外 | 需要建立迁移回归、适配层验收、CI 基线 | 只能靠局部推断，风险高 |
| 根级 `.specanchor/patch_map.md` | 当前仍是参考材料 | 需要对照旧 patch 热区或回溯 nanobot 来源行为 | 容易误删兼容行为或低估迁移成本 |
| workspace bootstrap 模板与相关约定 | 部分行为依赖它们 | 需要改 `TOOLS.md` / bootstrap contract / skills 发现 | 容易出现“核心迁了，但启动行为变了” |
| `console` 相关 mock/runtime 数据 | 当前未迁入 `ava/` 子树 | 需要验证本地 console 用户体系、mock 流程 | Console 行为只能做不完全验证 |

## 默认规则

- 先尽量只在 `ava/` 子树内收敛 core / adapter 抽象
- 只要当前工作还不需要动 UI / bridge / 集成验证，就不强制迁 `console-ui/`、`bridge/`、`tests/`
- 一旦任务涉及行为回归判断，就优先迁测试，而不是继续靠口头推断

## 迁移顺序建议

1. 先迁抽象与兼容文档
2. 再迁 `ava/` 内的可复用实现
3. 再迁首个 reference adapter 的必要 glue
4. 最后按需要补 `console-ui/`、`bridge/`、`tests/`
