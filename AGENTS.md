# AGENTS.md

本文件是当前仓库的 **Codex / Claude 工作区入口**。

目标只有一个：让新会话进入这个 repo 后，能直接按真实环境启动、验证和开发，而不是重新猜启动链。

## 先读什么

1. `anchor.yaml`
2. `.specanchor/global/*.spec.md`
3. 如果用户已经点名某个 Task Spec、文件、函数或报错，直接沿现有证据继续，不要重起方案
4. 如果只加载了 `ava/` 子树，再补读 `ava/AGENTS.md`

## 环境前提

- 当前仓库依赖一个外部 `nanobot` checkout
- 默认路径是同级目录 `../nanobot`
- 如果不在默认位置，设置 `AVA_NANOBOT_ROOT=/path/to/nanobot`
- 根目录 `.nvmrc` 固定 Node 为 `20.19.0`
- `console-ui` 使用 Vite 7，要求 `Node 20.19+`
- Python 使用 `3.11+`

## 首次 bootstrap

```bash
nvm use
uv sync --extra dev
cd console-ui && npm install
cd ../bridge && npm install
```

如果是从旧 Node 版本切到 `20.19.0`，需要在 `console-ui/` 下重新执行一次 `npm install`。
否则可能缺少 Rollup optional native 依赖，并报 `@rollup/rollup-darwin-arm64` 找不到。

## 常用命令

```bash
# 最小 smoke，确认 sidecar + 外部 nanobot 解析正常
./scripts/start-ava.sh --help

# 启动网关
./scripts/start-ava.sh gateway

# Python 定向测试
uv run pytest tests/<path> -q

# 前端构建
cd console-ui && npm run build

# bridge 构建
cd bridge && npm run build

# 提交前低成本检查
git diff --check
```

## Trace 速查

- `trace_id` 是单个 agent turn 的端到端链路 ID；`span_id` 是单个操作；`parent_span_id` 表示层级。
- 运行时 span 落在 SQLite `trace_spans`，token 行通过 `token_usage.trace_id/span_id/parent_span_id` join 回 span。
- 查询与 Console 入口见 `docs/observability.md`。

## 当前仓库边界

- `nanobot` 是外部 checkout，不要再把上游源码重新放回本仓库根目录
- `ava/templates/AGENTS.md` 和 `ava/templates/TOOLS.md` 是运行时 workspace overlay 模板，不是当前 repo 的 Codex 指令入口
- 只有在修改 runtime bootstrap / template sync / tool surface 时，才去改 `ava/templates/*`
- `ava/AGENTS.md` 是 `ava/` 子树自举入口；仓库根 `AGENTS.md` 才是完整 repo 的开发入口

## 开发规则

- 优先最小有效改动，不为了“顺手”重构相邻代码
- 优先窄验证；不要把 repo 级环境噪音包装成代码失败
- 涉及 `console-ui/`、`bridge/`、workspace bootstrap、模板同步、旧 patch 热区时，不要只看 `ava/` 子树
- 如果使用新的 git worktree，先确认 `anchor.yaml` 和 `.specanchor/` 是否存在；不要把 local-only context 缺失误判成代码问题
