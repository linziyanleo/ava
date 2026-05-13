# IDEA.md — AVA 多 Agent 协同平面

> 最后更新：2026-05-12
> 状态：Living Concept Spec（已按当前实现对齐）

## 核心愿景

AVA 是**本地优先的 Agent Control Plane**，桌面端是主要客户端。

ava-core 是产品核心——一个可 headless 运行的 Agent 控制平面服务。Electron 只是壳。用户通过 AVA 统一指挥、监控和编排多个异构 Agent，实现复杂工作流的自动化交付。

## 用户场景

### S1 — 直接指挥单 Agent

> "让 Claude Code 去指定目录写一个 REST API，跑完 CI 推到 GitHub。"

### S2 — 多 Agent 串行工作流

> "Nanobot 写 Task Spec → Codex review → 反馈修改 → 双方满意 → Codex 执行。Nanobot 全程汇报。"

### S3 — 跨能力编排

> "Codex 优化图片提示词 → Image Gen 批量生图 → 结果发到 Telegram。"

### S4 — 实时观测与控制

> "查看所有 Agent 的运行状态、模型、token 消耗、配置。重启 Nanobot 线程。停止 Claude Code 的当前任务。"

### S5 — 可扩展 Agent 注册

> "接入 OpenClaw / Hermes / 自定义 MCP agent。"

## 产品形态演进


| 阶段      | 定位                                        | 核心能力                                     |
| ------- | ----------------------------------------- | ---------------------------------------- |
| **P1a** | **Desktop Shell + ava-core 独立化**          | Electron 壳、ava-core sidecar、Nanobot 子进程化 |
| **P1b** | **Agent Control Plane** — 看得见、管得住         | Agent 注册/状态/配置/单任务派发/线程控制、轻量任务链与产物可视化 |
| **P1c** | **产品体验补强** — 让人懂 Ava 在做什么            | 首启动向导、记忆/任务可解释性、任务统一回放、桌面壳启动体验          |
| **P2a** | **Durable Workflow Run + 契约** — 跑得稳       | workflow run 持久化、artifact contract、workspace lease / worktree / branch authority |
| **P2b** | **Fan-out / Fan-in** — 跑得开                | parallel / join、并发上限、子任务聚合显示                                              |
| **P2c** | **可保存 Workflow + 编辑入口** — 编得起来          | workflow definition 存储、版本、模板、导入导出、Workflow Detail UI                      |
| **P3**  | **Multi-Agent Coordination Plane** — 自动协同 | 条件分支、循环、approval、可视化编排                                                     |


P1 的成功标准：用户能启动/停止/重启 Agent，能观察状态，能派发任务，能取消任务，能查看事件和产物。

## 当前实现 Check List（2026-05-08）

本节只标记当前 P1b Agent Control Plane 已落地的最小闭环，不把 P2/P3 workflow/coordination 规划误写成已完成能力。

- [x] Agent Registry API：`GET /api/agents` 返回 Nanobot、Claude Code、Codex、Image Gen 的安装状态、运行状态、版本、能力、活跃任务、近期事件和产物摘要
- [x] Version API：`GET /api/core/version` 与 `GET /api/agents/{agent}/version` 暴露 core / agent 版本面
- [x] Runtime projection persistence：新增 `agent_registry` SQLite 表，启动/刷新时持久化检测结果
- [x] Nanobot discovery：Agent Registry 使用全局 discovery，不把 runtime workspace 当 project root，避免错误检查 `/Users/fanghu/nanobot`
- [x] API JSON boundary：未知 `/api/*` 在 SPA fallback 前返回 JSON 404，前端 API client 对 HTML 响应给出明确错误
- [x] Agent Dashboard：Settings → Agents Config 展示 Agent 卡片、状态、路径、版本、能力、活跃任务、近期事件和产物；旧 `/agents` 仅作为 legacy redirect 指向 `/settings/agents-config`
- [x] Dashboard single task dispatch：Dashboard 可对 Codex、Claude Code、Image Gen 发起 direct background task，复用 `/api/console/direct-tasks`
- [x] Task control：Dashboard 可跳转任务页并取消 Codex / Claude Code / Image Gen 的活跃后台任务
- [x] Restart control：Dashboard 可对运行中的 Nanobot 触发 gateway restart
- [x] Role boundary：viewer / mock_tester 可读 Agent Dashboard；direct task submit 只对 admin/editor 开放；restart 只对 admin 开放
- [x] Config separation：`ConsoleConfig` 只承接 console/gateway 通用运行面，`NanobotConfig` 显式承接 agent 专属根配置；`Config` 保持兼容导出
- [x] AVA-8 product surface cleanup：通用 console/storage/slash command 产品面使用 AVA Agent Control Plane / AVA Agent 命名；`tests/guardrails/test_ava8_decoupling_boundary.py` 将剩余 `nanobot` 引用分类为 adapter、兼容配置、legacy home 或上游 runtime 引用
- [x] AgentProcessManager：提供显式 `start/stop/restart/healthcheck` lifecycle，并通过 Agent Registry routes 暴露；`GET /api/agents` 保持 read-only
- [x] WorkflowStore / ArtifactStore P1b：支持 `chain_id`、9 状态节点、线性推进、cancel、retry、artifact 四类索引与旧 BackgroundTask 兼容
- [x] Workflow realtime：`/api/workflows/ws` 推送 chain/artifact snapshot，`useWorkflowStore` 统一订阅并更新共享状态
- [x] ChainBubble：在 Chat 中显式展示 P1b 任务链状态，支持 streaming progress、artifact preview、整链 cancel、失败/取消 retry 与长链滚动约束
- [x] HUD widgets：Chat HUD 以 widget 列表渲染 Token / Skills / Artifacts / Memory，窄屏水平滚动；Skills 可展开卡片抽屉，Memory 读取 ava-core `memory_rss_bytes`，失败数据源对应 chip 自动隐藏
- [x] LAN Access P1b：Settings → System → LAN Access 提供显式开关、LAN URL、5 分钟 PIN 配对、read_only device token、设备撤销和 `lan.device_access` audit 摘要；console 启动绑定由 LAN 状态控制为 `127.0.0.1` / `0.0.0.0`
- [x] Electron shell P1b：`electron/` 提供 macOS `.app` 壳，启动 `ava-core` sidecar、等待 `/api/gateway/health`、加载 Console、退出时清理子进程，并提供 pnpm dry-run 构建验收
- [x] TopBar + Task Floater：桌面端主导航收敛为 TopBar；TaskPreviewBar 迁到全局任务栏，点击 chip 打开不改路由的任务浮窗
- [x] Task Overlay deep link：支持 `?view=tasks`、`?task_view=all/current/history/scheduled/artifacts`、`?task_id=`、`?chain_id=`、`?trace_id=` 与旧 `/tasks` / `/bg-tasks` / `/media` redirect
- [x] Regression tests：补充 Agent Registry service、Agent API route、API JSON fallback、Nanobot discovery regression 的定向测试
- [x] Linear checklist acceptance：`tests/console_ui/test_linear_acceptance_checklists.py` 覆盖当前 Linear checklist，AVA-8/15/27/38 xfail 缺口已转为实测通过，并显式断言 AVA-25/26/28-36 deferred UI/route 不进入当前 P1b 验收

## 剩余 TODO List

### P1b 当前闭环

- [x] Agent Detail：Settings → Agents Config 支持 4 个 Agent kind 的状态、配置、操作、文档与近期事件入口
- [x] AgentProcessManager：支持 start/stop/restart/healthcheck，并接入 Agent Registry routes
- [x] Multi-Agent Chat：支持会话 participants、`@agent` 指名、default responder、消息来源持久化与头像菜单
- [x] AgentAdapter protocol：`ava/agents/*/adapter.py` 提供 4 个现有 Agent kind 的 adapter，AgentRegistryService 通过 adapter 列表投影
- [x] Skill 触发双入口：`@skill_name` 显式触发 + Nanobot 自然语言匹配，并把触发结果注册为 chain
- [x] Context Size：显示 token 占用、手动压缩、压缩前后对比

### P1c 待落地

- [ ] 首启动向导：environment check + Agent Registry 健康检查 + model provider 录入 + 渠道接入（可选）+ 示例任务；每次启动复用 health check，缺关键依赖自动回到对应步骤
- [ ] 记忆条目可解释字段：`source` / `created_by_agent` / `confidence` / `last_used_at` / `last_used_in` / `pinned`；Memory 列表按"用户确认 / Agent 推断 / 不确定"分组
- [ ] 任务条目可解释字段：触发来源、依据 memory id、参考 artifact id、决策日志（模型 output 摘要 + 工具调用参数）
- [ ] 任务统一回放：Task Overlay 任务详情内整合 ChainBubble / BackgroundTask / Trace spans / Browser screencast / Artifact 五源时间线，并补 `GET /api/tasks/{task_id}/replay` 聚合接口
- [ ] 桌面壳启动体验：macOS `.app` 启动无 terminal 闪烁、首次启动衔接首启动向导、Dock/Cmd+Q 行为；快捷键 `Cmd+Shift+D` 以系统浏览器打开同一份 Console（不绕认证，不依赖 LAN Access）

### P2 / P3 后续增强

- [ ] AVA-25 / AVA-26 / AVA-28 / AVA-29 / AVA-30：已在 Linear 标记 `deferred`，不进入当前 P1b 验收。
- [ ] AVA-31 / AVA-32 / AVA-33 / AVA-34 / AVA-35 / AVA-36：已在 Linear 标记 `deferred`，保留为 P3 backlog，不作为当前可见 UI 或 passing acceptance。
- [ ] 设备侧 LAN Access P2 验收：手机扫码、中国大陆 WiFi、iOS/Android 添加主屏、家用路由器 mDNS 实测；人工验收步骤见 `docs/control-plane-manual-acceptance.md`
- [ ] 移动端原生重设计验收：iPhone 13+ / Pixel 4+ 流畅度、关键场景、横竖屏切换；人工验收步骤见 `docs/control-plane-manual-acceptance.md`

## P1c — 产品体验补强

P1b 已经把"控制面"立住：Agent 状态、任务派发、cancel/retry、artifact 预览、LAN Access、Electron 壳都可用。P1c 不再叠功能，而是把已有数据暴露成用户能看懂的产品表达。四件事互相独立，可分别落地。

### 首启动向导

当前接入门槛：用户按 README 5 步（`nvm use` / 准备 `nanobot` checkout / `uv sync` / `npm install` / `start-ava.sh`），再手工配 `AVA_NANOBOT_ROOT`、模型 provider key、渠道 token。Electron 壳进入 P1b 后，README 驱动的接入流程是非 contributor 的最大障碍。

向导覆盖 5 步：

1. **环境探测**：外部 `nanobot` checkout、`AVA_NANOBOT_ROOT`、`AVA_HOME`、Python venv、Node version
2. **Agent 健康检查**：复用 Agent Registry，列出 4 个内置 Agent kind 的安装状态、版本、缺失项；未安装项给出官网跳转
3. **Model provider 配置**：OpenAI / Anthropic / Gemini key 录入与本地保存（写入 ava-core 配置，不进 git）
4. **渠道接入（可选）**：Telegram / Feishu / 微信 / Discord 等 channel token；用户可全部跳过
5. **示例任务**：生成 3–5 条"你现在可以让 Ava 做什么"的可点击示例，跳到 Chat 并预填 prompt

向导不是一次性页面。每次启动 Ava 都做 environment health check：关键依赖缺失（`nanobot` checkout 不存在 / core 模型 provider 未配置）则回到向导对应步骤；全部就绪则直接进 Chat。

向导只负责"让 Ava 可用"，不引入新的产品概念，不替代 Settings → Agents Config。

### 记忆与任务可解释性

`MemoryPage` / `BgTasksPage` 已存在，但目前主要展示"是什么"（内容、状态、时间），缺"为什么"（来源、依据、最近被使用）。Agent Control Plane 定位下，用户对 AI 的信任来自"我能看懂 Ava 在依据什么做事"。

**记忆条目** — 在已有 Memory 详情上补字段，不新增独立页面：

| 字段                 | 说明                                              |
| ------------------ | ----------------------------------------------- |
| `source`           | 来源：chat / task / manual / channel / file       |
| `created_by_agent` | 是哪个 Agent 写入的                                   |
| `confidence`       | inferred / confirmed / uncertain                |
| `last_used_at`     | 最近一次被读入上下文的时间                                   |
| `last_used_in`     | 最近一次被使用的 task / chain id                        |
| `pinned`           | 用户显式 pin，不参与自动失效                                |

Memory 列表按"用户确认 / Agent 推断 / 不确定"分组；每条支持 approve / edit / delete / pin。

**任务条目** — 在 Task Overlay 任务详情上补：

- 触发来源：chat 消息 id / channel 消息 / cron / 上游 chain / direct task
- 依据：当时使用的 memory 条目 id 列表、参考 artifact id 列表
- 决策日志：Agent 在哪几步做了选择（model output 摘要 + 工具调用参数）

**字段来源差异**：

- **任务条目**字段大多已在 `BackgroundTaskStore` / `WorkflowStore` / `trace_spans` 里有原始数据（trace_id、parent_span_id、dispatch_span_id、tool call、模型 raw output），P1c 主要是 projection 与 UI 层工作
- **记忆条目**的 `source` / `created_by_agent` / `confidence` / `last_used_at` / `last_used_in` / `pinned` 在当前 memory schema 里不存在，需要对现有 memory 表做**最小字段扩展**（safe ALTER，参考 `schema_version` 既有迁移机制），不新增独立 store

P1c 的边界是：不引入新的长期 store / authoritative source，但允许对现有 memory / task schema 做最小字段扩展以暴露 provenance。

### 任务统一回放

当前任务上下文分散在四处：ChainBubble（对话内联）、Task Overlay（任务详情）、BrowserPage（screencast）、TraceTimelineDrawer（trace 时间线）。重看一条任务需要在多个入口跳转。

任务统一回放在 Task Overlay 任务详情页内整合五源：

| 源                  | 提供                              |
| ------------------ | ------------------------------- |
| ChainBubble        | chain 9 状态、节点关系、step 状态         |
| BackgroundTask     | task 执行进度、stdout / stderr       |
| Trace spans        | tool call、token、耗时、错误           |
| Browser screencast | 浏览器步骤截图、DOM 目标、URL              |
| Artifact           | 产物预览与版本                         |

回放视图给出 3 个核心问题的答案：

1. **Ava 当时看到了什么** — 输入 prompt、依据 memory、上游 artifact、浏览器页面
2. **Ava 做了什么** — 每一步 tool call、模型决策、子任务派发
3. **Ava 为什么这么做** — 决策日志、引用的 memory、参考 artifact

P1c 阶段不引入新的存储模型。后端补一个 `GET /api/tasks/{task_id}/replay` 聚合接口，把五源拼成一条时间线返回；前端在 Task Overlay 任务详情内做时间线 UI。

### 桌面壳启动体验

P1b 已经提供 macOS `.app` 壳（见 Checklist Electron shell P1b），双击启动 → 拉起 sidecar → 加载 Console 全链路已通。但当前 `.app` 仍依赖本机 git checkout、external `nanobot` checkout 与本地 venv —— **真·"拷到另一台机器双击就能用"依赖 Python sidecar 打包，属于 P2 范围，不在 P1c 承诺**。

P1c 只补两件让现有 `.app` 用起来更接近"日常桌面应用"的事：

**Finder 双击启动体验打磨**

- macOS 下确保启动时不闪 terminal 窗口，stderr 不出现在用户视线
- 首次启动检测到环境不完整时直接进首启动向导，不抛 stderr 让用户去看 Console.app
- Dock icon、应用菜单、`Cmd+Q` 行为按 macOS 习惯走，不依赖 terminal 终止进程
- 双击 `.app` → 启动 sidecar → 加载 Console → 退出时清理子进程，全链路无 terminal 介入

**快捷键进入 web 模式**

- Electron 注册全局快捷键（默认 `Cmd+Shift+D`），按下时用系统默认浏览器打开同一份 Console（`http://127.0.0.1:<core_port>/`）
- **不依赖 LAN Access 开启** —— 本机 `127.0.0.1` 始终可用；LAN Access 控制的是是否绑 `0.0.0.0` 给其他设备
- **不绕过认证** —— 浏览器走完整登录流程，token 不从 Electron renderer 复用
- 用途：用 Chrome / Safari DevTools 调试网络 / WebSocket / 性能；与 Electron 窗口并行操作同一后端，验证 WS 推送的多端一致性
- production build 与 dev build 都启用，不在生产隐藏

这两件事都不引入新的产品概念，只是把 Electron 模块和 ava-core 已经具备的能力暴露给用户。

## P2a / P2b / P2c — Multi-Agent Workflow Runner 详解

P1b 的 `WorkflowStore` 只支持线性 chain（9 状态、`parent_task_ids` 一对一）。P2 把它扩展成完整的 Workflow Runner，承接 S2 / S3 跨 Agent 串行与并行场景，但**拆成三个可独立验收的子阶段**，避免一次性交付一个无法验证的大 runner：

- **P2a**：durable workflow run + artifact contract + workspace 写入冲突契约
- **P2b**：fan-out / fan-in、并发与 join 策略、子任务聚合显示
- **P2c**：可保存 workflow definition、模板、导入导出、Workflow Detail UI

P2 任何子阶段的 step kind 都**只支持** `agent_task / parallel / join`；`approval / branch / loop` 与嵌套 workflow / 可视化编排为 **P3 reserved**，不在 P2 引入。

### P2a — Durable Workflow Run + 契约

#### Workflow 模型（P2a 范围）

```
Workflow
├─ id, name, version, owner
├─ definition (DSL or graph JSON)
├─ inputs schema / outputs schema
├─ shared workspace ref
└─ steps[]
    ├─ id, name, kind (agent_task / parallel / join)
    ├─ agent (claude_code / codex / nanobot / image_gen / ...)
    ├─ inputs (artifact refs / literal values / upstream step outputs)
    ├─ outputs (artifact contract)
    ├─ retry policy (max_attempts / backoff / on_error)
    └─ depends_on[]
```

Workflow 定义存 `agent_workflows` 表；每次执行实例化为 `workflow_runs`，run 持有当前 step 状态、artifact 引用、workspace lease。P2a 允许 workflow 通过 API / 内置模板触发，但还没有编辑 UI（编辑入口在 P2c）。

#### Workspace 写入冲突契约（P2a 第一硬约束）

fan-out 一旦上线，并发写同一个 repo 会立刻出事。这条契约必须在 P2a 立住，才能让 P2b 安全引入并行：

- **Workspace lease**：每个 step 启动前显式 acquire workspace lease（粒度按 workspace path）。未持有 lease 不能写入。lease 在 step settle（success / fail / cancel）时释放，超时由 Runner GC
- **Worktree 策略**：默认每个 agent step 在独立 git worktree 内运行，避免与 main worktree 的脏树污染。多个并发 step 拿到独立 worktree 路径
- **Branch authority**：fan-out 子任务在独立分支（`workflow/<run_id>/<step_id>`）；join step 决定合并策略（fast-forward / squash / 选择其一 / 丢弃），合并策略由 step 定义声明
- **Dirty tree 处理**：step 启动前若 workspace 有未提交变更，按 step 定义 `on_dirty: fail | stash | require_clean` 处理；默认 `fail`，强制让用户感知
- **跨 step artifact 仍走显式传递**：worktree / branch 是隔离手段，artifact 是契约手段；两者不互相替代，不允许通过 worktree 文件路径偷传上下文

#### step 间 artifact 传递

- 每个 step 输出按 artifact contract 写入 `ArtifactStore`，run 持有 artifact id 引用
- 下游 step 通过 `inputs.upstream_step_id.output_name` 显式拿到 artifact，不依赖隐式上下文
- 序列化策略沿用 P1b：text 入 DB、file / image / log 存本地 artifact directory、workspace 存引用
- 引用过期 artifact（已被 GC / workspace 已重置）必须立即报错；Runner 不做"找不到就跳过"的回退
- Artifact contract 在 step 定义里声明类型与必要字段，运行时不匹配立即 fail，不静默喂垃圾数据下游

#### 失败重试

- **Step 级 retry policy**：`max_attempts` / `backoff (exponential / fixed)` / `retry_on (error_types)`；超过 max_attempts 进入 `failed`
- **Workflow 级失败策略**：`fail_fast`（默认，首个 step 失败立刻取消未启动 step、保留运行中 step 直到 settle）/ `continue_on_error`（标记 step 失败但继续后续不依赖它的 step）
- **手动 retry**：从任意 failed step 继续；Runner 复用上游成功 artifact，不重跑已成功 step
- **修复重试**：重试时 inputs 可被用户修改（修复 prompt、补 artifact），形成新的 attempt；attempt 历史保留可对比
- **诊断信息**：失败 step 的 last error / stack / tool call args / 模型 raw output 作为 step 详情字段（编辑 UI 在 P2c 暴露）

#### 数据库扩展（P2a 范围）

- `agent_workflows`：workflow 定义（id / name / version / definition_json / owner / created_at）
- `workflow_runs`：执行实例（id / workflow_id / version / status / started_at / ended_at / trigger）
- `workflow_steps`：step 状态（id / run_id / step_name / status / attempt / started_at / ended_at / artifact_outputs / error）
- `workflow_artifacts`：run 内 step 输出引用，复用 P1b `artifacts` 表 + run/step 索引
- `workspace_leases`：workspace lease 持有记录（path / holder_run_id / holder_step_id / acquired_at / expires_at / released_at）

### P2b — Fan-out / Fan-in

P2a 已经能跑单 step 串行 workflow。P2b 加并行：

- **fan-out**：一个 step 输出 N 个 artifact，下游 step 声明 `for_each: artifact_collection`，Runner 为每个 artifact 派发独立子任务；子任务获得独立 AgentInstance（或排队复用 instance），取决于 `AgentCapabilities.max_concurrent_tasks`
- **fan-in**：N 个并行子任务全部 settle 后触发 join step；join 策略由 step 定义声明：`all_success` / `at_least_n` / `best_effort` / `first_success`
- 并发上限 = AgentInstance 数量 × `max_concurrent_tasks`；超出排队
- 每个 fan-out 子任务在独立 worktree / branch 内运行（依赖 P2a workspace 契约）
- Runner 维护 `barrier` 状态：未达到 fan-in 条件的 join step 阻塞，直到上游全部 settle（success / fail / cancel）
- fan-out 子任务在 Chat 的 ChainBubble 内聚合显示一个折叠组，点击展开看每个子任务，不让对话流被批量任务淹没

### P2c — 可保存 Workflow + 编辑入口

P2a / P2b 已经能跑 workflow，但定义还只能通过 API / 模板进入。P2c 把定义面做完整：

- **持久化与版本**：定义文件存 `agent_workflows` 表；同一 workflow 多版本通过 `version` 号管理；run 始终指向具体 version，已开始的 run 不被新版本影响
- **编辑入口**：Settings → Tools → Workflows（新增）；P2c 以表单 + JSON 编辑为主，可视化编排留给 P3
- **触发入口**：Skill / Chat slash / cron / API；触发参数遵循 workflow inputs schema
- **内置模板**：常用 workflow（codex_review → nanobot_apply、image_gen_batch → telegram_publish）作为复制起点，用户基于模板改写
- **导入/导出**：workflow 定义可作为 JSON 文件导出 / 导入，便于团队内复用与 git 版本管理
- **Workflow Detail UI**：Timeline / Steps / Artifacts / Coordinator Report / Logs（已在 P1b 信息架构中预留路由）
- **Chat 集成**：Workflow 触发的 ChainBubble 升级为多分支显示，fan-out 子任务在 bubble 内合并展示，点击进入 Workflow Detail
- **Task Overlay ↔ Workflow Detail 互跳**：单 step 详情仍走 Task Overlay 的任务统一回放视图（P1c 已交付）

### P3 reserved

明确以下能力**不属于 P2 任何子阶段**，在 P3 Multi-Agent Coordination Plane 引入：

- **`approval` step kind**：人工 approve / reject + 走分支
- **`branch` step kind**：基于 step output 的条件分支
- **`loop` step kind**：循环执行直到条件满足
- **嵌套 workflow**：workflow 调用另一个 workflow
- **可视化编排**：拖拽节点图编辑器

### 与 P1b 的边界

- P1b 的 `WorkflowStore`（线性 chain、9 状态、cancel / retry）不被废弃，作为 P2 Workflow Runner 在"单 step / 无 fan-out"场景下的 fast path 保留
- 新 `workflow_runs` 与旧 chain 并存：旧 chain 继续承接 Skill 触发的简单任务链；新 workflow 处理多 step / 并行场景
- P2a 期间，Skill 触发仍走旧 chain；P2c 期间可考虑把部分 Skill 迁到 workflow definition，但不强制

## 架构思路

### 进程模型

```
Electron Main Process
├─ 启动 / 停止 ava-core sidecar
├─ app lifecycle、workspace 选择、系统通知、托盘
└─ 健康检查（不持有核心业务状态）

React Renderer (复用当前 console-ui)
├─ TopBar（桌面主导航 + 全局 TaskPreviewBar + Avatar menu）
├─ Chat
├─ Settings (Agents Config / Statistics / Tools / Users / System)
├─ Task Overlay (P1b)
└─ Workflow Detail (P2c，当前未路由)

ava-core Python Sidecar (FastAPI + WebSocket)
├─ AgentRegistry
├─ AgentAdapter(s)
├─ AgentProcessManager
├─ BackgroundTaskStore
├─ AgentRuntimeStore
├─ ArtifactStore (P1b light)
├─ WorkflowStore (P1b light)
└─ IPC → Managed Agents

Managed Agents
├─ Nanobot (默认主 Agent，自动带起)
├─ Claude Code CLI
├─ Codex CLI
├─ Image Gen
└─ (未来) OpenClaw / Hermes / MCP Agent
```

核心原则：**Electron 管桌面生命周期，Python 管 Agent 控制平面。** 当前 headless 入口是 `ava` / `ava gateway`（Electron wrapper 启动同一 sidecar）；`ava-core serve --port 0 --workspace ...` 是后续产品化命名契约，不按当前实现声明为已完成。

### 通信拓扑

```
Renderer ↔ ava-core：HTTP + WebSocket（核心 API）
Renderer ↔ Electron main：Electron IPC（仅 native 能力）
Electron main ↔ ava-core：启动/停止/healthcheck
ava-core ↔ Agents：stdio JSON-RPC / local HTTP / adapter-specific
```

ava-core 上层只依赖 AgentAdapter 统一接口；底层协议按 Agent 类型选择。P1 优先支持 stdio JSON-RPC 和 local HTTP，暂不引入 gRPC。

### 桌面客户端

P1 采用 Electron，以最大化复用现有 Vite + React 前端并降低迁移成本。Tauri 保留为长期可选替代方案。桌面壳技术不影响核心抽象。

### 核心抽象

**AgentAdapter** — 统一的 Agent 交互接口（任务派发、取消、状态查询、配置读取、事件流）。新增 Adapter 以 wrapper 模式包裹现有 Tool，不重构已有工具代码。

**AgentInstance** — Agent 类型用 name 标识（`claude_code`、`codex`、`nanobot`），运行实例用 instance_id 标识。Registry 管理的是 AgentInstance。

**AgentCapabilities** — 每个 Agent 声明能力（supports_chat / supports_task / supports_cancel / supports_restart / supports_streaming / supports_artifacts / max_concurrent_tasks / supported_artifact_types），前端据此决定可用操作。

**AgentProcessManager** — 管理 Agent 子进程生命周期：启动、停止、重启、健康检查。

**Artifact** — Agent 间上下文传递的最小单元（text / file / diff / image / log / json / workspace）。Agent 的输入输出围绕 Artifact 结构化。存储策略：小文本存 DB，大文件/图片存本地 artifact directory，workspace 只存引用。

**AgentEvent** — 标准化事件（log / status / artifact / error / token_usage），上层不感知具体 CLI 输出格式。

**Store 分层**：

- `BackgroundTaskStore`：底层任务生命周期（执行单元）
- `AgentRuntimeStore`：Agent 当前状态和配置
- `WorkflowStore`（P1b light）：一次 skill / task 触发产生的 chain、节点关系、9 状态聚合与线性推进
- `ArtifactStore`（P1b light）：任务产物引用，先覆盖 text / file / diff / image / log / json
- `ChatStore`：用户与 Agent 的对话

P1b 的 WorkflowStore 只服务"看得见、管得住"的体验闭环：ChainBubble、TaskCard、任务 overlay、HUD Artifacts。P2a/P2b/P2c 才扩展为完整 Workflow Runner；条件 / 循环 / 嵌套 / approval / 可视化编排是 P3 reserved，不在 P2 任何子阶段引入。

逻辑分离，物理上可共用存储。不让 BackgroundTaskStore 继续膨胀成万能状态容器。

### 并发与 Workspace

- 默认每个 AgentInstance 同时只执行一个 task。并发能力通过 `AgentCapabilities.max_concurrent_tasks` 声明
- 需要并发就启动多个 AgentInstance，而不是在一个 instance 内部多线程
- Workflow 拥有共享 workspace；Agent 可拥有私有 scratch workspace；跨 Agent 传递必须通过 Artifact 显式表达
- P2a 引入 workspace 写入冲突契约（lease / worktree / branch authority / dirty tree 处理），fan-out 在 P2b 才被允许引入，详见 "P2a — Durable Workflow Run + 契约" 一节

### Agent 自动检测与启动

AVA 启动时**自动检测**全部本地 Agent，但**只自动启动 long-running 主体**（Nanobot / sidecar），不对 CLI 类 Agent 在启动时拉起进程。

- **自动启动**：Nanobot 是默认主回复者且自身是 long-running server，启动 ava-core 时一并拉起；未来形态相同的 sidecar agent 同理
- **按任务触发**：Claude Code CLI、Codex CLI、Image Gen 是 per-invocation 形态，启动 = 调用模型 API = 触达外部网络与消费 quota，仅在 direct task / workflow step 触发时启动子进程
- **检测但不启动**：未安装的 Agent 在 Settings → Agents Config 显示下载按钮跳到官网；已安装但未触发的 Agent 显示"可用，未运行"，不消耗任何外部资源

检测方式：PATH 查找（`claude` / `codex`）、版本命令验证、Nanobot 使用现有 discovery 机制。检测结果持久化到 `agent_registry` projection 表，启动时刷新。`AgentProcessManager` 的自动 start 行为按 Agent kind 区分；显式 `start/stop/restart/healthcheck` 入口对所有 Agent kind 保留。

### 聊天界面

Chat 是默认首屏，也是日常操作主入口。旧 gateway channel（Telegram / Console / CLI / Feishu 等）不再作为一级视觉入口，而是作为会话属性保留；会话栏可按时间或 Agent 分组排序。

一条会话可以绑定多个 Agent。Chat 配置区的 Agent 选择决定默认收件人集合，默认主回复者由配置项决定（例如 Nanobot），不是硬编码特权角色。

- 不指名时，当前默认主回复者响应
- 用户消息中 `@codex` / `@claude_code` 等显式指名时，被指名 Agent 收到上下文并回复
- 主 Agent 获得全局上下文，但不重复回复被其他 Agent 明确接管的消息
- Agent 头像在消息、会话项、ChainBubble、Settings Agent Tab 中保持统一视觉编码
- Skill 触发生成 ChainBubble，在对话流内展示任务链、状态、日志与产物入口
- 任务详情通过 Chat 内 state overlay 展示，不新增独立一级 Tasks 页面

### 前端信息架构

```
一级页面：
├─ Chat（默认首屏）
└─ Settings

Settings：
├─ Agents Config
│  ├─ Agent 总览（状态/模型/token/启停按钮）
│  └─ Agent Detail（Config / History / Logs）
├─ Statistics
├─ Tools
├─ Users
└─ System

Task Overlay (P1b)：
├─ 全部
├─ 当前进行中
├─ 历史
├─ 定时任务
└─ 产物视图

Workflow Detail (P2c)：
├─ Timeline
├─ Steps
├─ Artifacts
├─ Coordinator Report
└─ Logs
```

### 数据库演进

现有 ava.db schema（sessions / session_messages / token_usage / trace_spans / bg_tasks / media_records / audit_entries）需要扩展以支持多 Agent 模型。方向：

- **agent_registry 表**：持久化已检测的 Agent 信息（name / instance_id / kind / path / version / capabilities / status / last_seen）
- **session_messages 扩展**：当前多 Agent 会话通过 participants、default responder 与消息 metadata 支撑；`target_agent` / `source_agent` / `mention_agents` / `context_message_ids` 拆成独立字段仍是后续 schema hardening
- **bg_tasks 扩展 / workflow_chains 表（P1b light）**：支持 `chain_id`、`parent_task_ids`、9 状态、trace 归属与线性 chain 推进
- **artifacts 表（P1b light）**：产物记录（id / type / uri / metadata / chain_id / task_id），供 Chat 任务 overlay 与 HUD Artifacts 读取
- **agent_workflows / workflow_runs / workflow_steps / workflow_artifacts / workspace_leases 表**（P2a）：workflow 定义、执行实例、step 状态、artifact 引用与 workspace lease；编辑入口与版本化在 P2c 引入

迁移策略：使用现有的 `schema_version` 机制做增量迁移，不破坏现有数据。

### Nanobot patch 迁移路径

渐进式迁移，不一步废弃 patch：

1. ava-core 启动 Nanobot 子进程，NanobotAdapter 对外暴露标准接口
2. 现有 patch 链继续在 Nanobot 内部工作（compatibility shim）
3. 把 console 相关状态从 patch 中剥离到 ava-core store
4. Nanobot 只输出标准 AgentEvent / Artifact
5. 删除 patch 模式

ava-core 不应该依赖 Nanobot 内部 AgentLoop——它只知道 Nanobot 是一个 Agent，有状态、能接任务、会发事件、会产出 Artifact。

### 局域网移动端访问

ava-core 默认只监听 `127.0.0.1`。用户显式开启 LAN Access 后，才允许局域网设备访问同一份 console-ui。LAN 访问必须经过配对、token 鉴权和权限限制；移动端默认只读，写操作按 capability 单独授权。

**现有基础**：前端已有响应式设计（`useResponsiveMode` hook，768px 断点，ChatPage / DashboardPage / MemoryPage 等已适配）；console 后端已支持配置 `host`；核心 API 通过 HTTP + WebSocket 暴露，Electron IPC 仅用于 native capability，因此手机浏览器可作为 ava-core 的另一个客户端。

**网络层**：

- ava-core 提供 LAN Access 模式（当前入口是 Settings 页面开关），启用后监听 `0.0.0.0`，桌面端显示可访问的局域网 URL
- LAN Access 模式是显式开启、可见、可关闭、可审计的状态——不只是 host 切换
- 关闭 LAN Access 后立即停止接受局域网连接，可选择撤销移动端 session
- mDNS/Bonjour 广播仍是 P2 体验增强；当前 P1b 只展示 IP fallback URL

**静态资源托管**：

- LAN 模式下 ava-core 需托管 console-ui 静态资源（手机浏览器无法访问 Electron 的 `file://` 页面）
- 桌面 Electron 继续加载本地 bundle 或 dev server；手机访问 `http://<lan-ip>:<port>/`，加载同一份 console-ui
- 不新增独立 mobile app 或独立 mobile routes，复用同一个 bundle、路由、API client、WebSocket client 和状态管理

**安全层**：

- LAN Access 默认关闭
- 当前通过 PIN 完成设备配对；pairing code 短期有效，使用后失效。QR 配对仍是 P2 增强。
- 配对成功后颁发 device token，绑定 device_id、scope、创建时间、最后活跃时间，可过期、可在 Settings 中撤销
- HTTP API 和 WebSocket 均需 token 鉴权
- 移动端操作进入 audit log（device_id / ip / action / target / result / timestamp）
- HTTPS / 自签证书 / trust-on-first-use 作为 P2 安全增强——手机浏览器对自签证书体验差，不阻塞 P1b MVP
- 注意同源策略：生产环境 console-ui 与 API 同源；开发环境允许配置 dev origin，不使用 `*` + credentials

**前端适配**：

- 复用现有 console-ui 响应式布局
- 新增页面（Settings → Agents Config、Task Overlay 等）同步做移动端适配
- 前端根据 session capability 隐藏不可用操作；后端对所有敏感 API 强制做 capability 校验
- 仅新增：LAN pairing 页面/modal、device token session 逻辑、permission-based action hiding

**权限差异**：

当前实现角色为 `admin / editor / viewer / read_only / mock_tester`：

- **admin**：完整 console 能力，包含用户管理、restart、LAN Access 配置等高权限操作
- **editor**：可提交 direct task、发送消息、取消任务等编辑操作
- **viewer**：可读控制面，不能提交任务或取消任务
- **read_only**：只读访问，作为移动端 device token 默认角色
- **mock_tester**：读取 mock runtime，不触达真实 workspace

后续四级 workflow 协作模型：

- **read_only**（移动端默认）：查看 Agent 状态、任务、workflow、日志摘要、artifact preview
- **reviewer**：read_only + approve/reject workflow、comment
- **operator**：reviewer + cancel/retry task、send_message、submit template task
- **admin**：完整能力，高风险操作（workspace 选择、shell 执行、secret 读取、配置修改、git push、文件写入、重启 ava-core）仍需二次确认

**分期**：

- **P1b**：LAN Access 开关、host 切换、console-ui 托管、PIN 配对、device token、HTTP/WebSocket 鉴权、响应式 UI 复用、默认 read_only、设备撤销、基础 audit log
- **P2**：QR 配对完善、mDNS/Bonjour、HTTPS/证书策略、PWA manifest、移动端通知、更细粒度权限配置
- **P3**：Relay safety gate、正式 HTTPS contract、远程 inbox、移动推送 contract

### 安全边界

P1 就定下来：

**Electron 侧**：nodeIntegration=false、contextIsolation=true、sandbox=true、preload 只暴露最小白名单（selectDirectory / openPath / getAppConfig / getCoreEndpoint / getAuthToken / showNotification）

**ava-core 侧**：默认只绑定 127.0.0.1；LAN Access 模式下绑定 0.0.0.0 + PIN 设备配对 + device token 鉴权（P1b 先 HTTP，P2 加 QR/HTTPS）；所有 HTTP/WebSocket 请求带 token；CORS 白名单；危险操作显式授权；移动端操作记入 audit log

### 版本管理

桌面端有多个版本对象需要追踪：Electron app version / ava-core version / AgentAdapter protocol version / Nanobot version / CLI agent versions / Workflow schema version。P1 就暴露 `/core/version` 和 `/agents/{id}/version` 接口。

## 关键约束

- Nanobot 是默认主 Agent 但不是架构特权角色——coordinator 是 workflow 配置项，不是硬编码系统角色
- 新 Agent 的接入成本尽量低：实现 AgentAdapter + 注册即可
- 前端页面各司其职，互相跳转但不合并
- Electron main process 绝不持有核心业务状态
- ava-core 必须 headless 可运行，Electron 只是启动方式之一
- Python sidecar 打包需要早期验证（依赖管理、PATH/shell 环境、升级机制）
