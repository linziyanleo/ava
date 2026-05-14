# Ava

Ava 现在是一个独立仓库，承接从既有 sidecar 代码抽取出来的外挂层实现。

Ava 当前的产品定位是**本地优先 Agent Control Plane**：`ava-core` 负责 agent 注册、状态、任务、事件、产物与权限控制；桌面壳只负责生命周期与 native 能力。Console 一级 IA 是 `Chat` + `Settings`，Agent 控制面位于 `Settings → Agents Config`（旧 `/agents` 仅作为 legacy redirect）。`nanobot` 仍是默认主 Agent，但不作为架构特权角色；Console 也可以通过显式 slash command 直接启动其他 agent 后台任务（例如 `/codex`、`/claude-code`、`/image-gen`），这条直连路径绕开 nanobot agent loop，任务仍复用 Ava 的 BackgroundTaskStore、状态查询、timeline 和结果回流机制。

这个仓库不再内嵌 `nanobot/` 源码；运行时通过外部 checkout 接入上游 `nanobot`，默认指向同级目录 `../nanobot`，也支持用 `AVA_NANOBOT_ROOT` 覆盖。

## 目录

- `ava/`: Python 插件层，包含 patches、console、storage、tools、runtime 和 adapter bootstrap
- `console-ui/`: 当前迁移期保留的 Console 前端
- `electron/`: macOS `.app` 壳，负责 Finder/LaunchServices 启动、本地 setup surface、ava-core sidecar 生命周期并加载 Console；当前产物会内嵌本机 repo root manifest，可复制到 `/Applications` 从 Launchpad 启动，但仍依赖本机 checkout，不是可跨机器分发的安装包
- `bridge/`: 当前迁移期保留的 Node bridge
- `tests/`: 以外挂层为中心的单元测试
- `scripts/start-ava.sh`: 用当前仓库代码 + 外部 nanobot checkout 启动 Ava

## 多 Agent 直连任务

Console 聊天输入框支持以下直连命令：

- `/codex <prompt>`: 直接创建 Codex CLI 后台任务
- `/claude-code <prompt>`: 直接创建 Claude Code CLI 后台任务
- `/image-gen`: 打开图片生成参数面板后创建 image generation 后台任务

这些命令是用户显式选择 agent 的入口，区别于 nanobot tool call 的自动决策路径。首期任务上下文与当前 nanobot 对话隔离；任务完成后，BackgroundTaskStore 会把结果摘要写回当前 session conversation，后续 nanobot turn 可以看到这条结果。

## 启动

1. 切到项目要求的 Node 版本

```bash
nvm use
```

当前 `console-ui` 使用 Vite 7，要求 `Node 20.19+`。仓库根目录的 `.nvmrc` 已固定为 `20.19.0`。

2. 准备外部 `nanobot` checkout
   建议放在当前仓库同级目录，或通过环境变量显式指定
3. 安装当前仓库依赖

```bash
uv sync --extra dev
```

4. 安装前端依赖

```bash
cd console-ui && npm install
cd ../bridge && npm install
```

如果你是把已有 checkout 从旧 Node 版本切到 `20.19.0`，建议在 `console-ui/` 下重新执行一次 `npm install`。否则 Rollup 的 optional native 依赖可能缺失，并报 `@rollup/rollup-darwin-arm64` 找不到。

5. 启动 Ava

```bash
./scripts/start-ava.sh gateway
```

如果 `nanobot` 不在默认同级目录，先指定：

```bash
AVA_NANOBOT_ROOT=/path/to/nanobot ./scripts/start-ava.sh gateway
```

## Electron Shell

macOS `.app` 壳位于 `electron/`。它会先显示本地 setup surface，处理 nanobot checkout、`.venv` bootstrap、日志与错误状态；`ava-core` healthy 后再加载 Console。当前 `.app` 仍依赖本仓库 checkout 和外部 `nanobot` checkout。

```bash
pnpm electron:dry-run
pnpm electron:build
pnpm electron:install
```

根 `pnpm electron:build` 会自动按 `electron/pnpm-lock.yaml` 安装 Electron shell 依赖，不需要单独进入 `electron/` 执行 `pnpm install`。
根 `pnpm electron:install` 会先执行 Electron 打包，再用 `ditto` 替换 `/Applications/Ava.app` 并做安装后 codesign 校验；如只想安装已有 bundle，可运行 `scripts/install-desktop-app.sh --skip-build`。

Finder/LaunchServices 验收请按 `docs/desktop-launch-acceptance.md` 执行并记录结果；生成 evidence 前可用 `scripts/verify-desktop-handoff-ready.sh` 与 `scripts/verify-desktop-handoff-ready.sh --port-conflict` 分别检查两条 handoff 的本地 blocker。填完视觉确认字段后再运行 `scripts/verify-desktop-closeout-records.sh`；当前 Codex sandbox 无法关闭该验收，因为 `open -n` 对 Ava 和系统 Calculator 都返回 `kLSNoExecutableErr`。脱离 repo checkout 的独立分发、正式签名、公证、图标和 DMG 仍不在当前阶段范围内。

## 说明

- `python -m ava ...` 现在会先解析外部 `nanobot` checkout，再加载 patches。
- `./scripts/start-ava.sh` 会优先使用当前仓库 `.venv`，其次才回退到外部 `nanobot` 的 `.venv`。
- 当前本地开发建议使用 Python `3.11+`、`uv` 和 Node `20.19.0`。
- 当前 repo guardrail 明确禁止再次把 `nanobot` 源码直接放回本仓库根目录。
