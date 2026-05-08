# IDEA.md — AVA 多 Agent 协同平面

> 最后更新：2026-05-08
> 状态：Concept Spec

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
| **P2**  | **Multi-Agent Workflow Runner** — 编得起来    | fan-out/fan-in、可保存 workflow、step 间 artifact 传递、失败重试 |
| **P3**  | **Multi-Agent Coordination Plane** — 自动协同 | 条件分支、循环审批、并行执行、可视化编排                     |


P1 的成功标准：用户能启动/停止/重启 Agent，能观察状态，能派发任务，能取消任务，能查看事件和产物。

## 当前实现 Check List（2026-05-08）

本节只标记当前 P1b Agent Control Plane 已落地的最小闭环，不把 P2/P3 workflow/coordination 规划误写成已完成能力。

- [x] Agent Registry API：`GET /api/agents` 返回 Nanobot、Claude Code、Codex、Image Gen 的安装状态、运行状态、版本、能力、活跃任务、近期事件和产物摘要
- [x] Version API：`GET /api/core/version` 与 `GET /api/agents/{agent}/version` 暴露 core / agent 版本面
- [x] Runtime projection persistence：新增 `agent_registry` SQLite 表，启动/刷新时持久化检测结果
- [x] Nanobot discovery：Agent Registry 使用全局 discovery，不把 runtime workspace 当 project root，避免错误检查 `/Users/fanghu/nanobot`
- [x] API JSON boundary：未知 `/api/*` 在 SPA fallback 前返回 JSON 404，前端 API client 对 HTML 响应给出明确错误
- [x] Agent Dashboard：新增 `/agents` 页面和一级导航，展示 Agent 卡片、状态、路径、版本、能力、活跃任务、近期事件和产物
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
- [x] Task Overlay deep link：支持 `?view=tasks`、`?task_id=`、`?chain_id=`、`?trace_id=` 与旧 `/tasks` / `/bg-tasks` / `/media` redirect
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

### P2 / P3 后续增强

- [ ] AVA-25 / AVA-26 / AVA-28 / AVA-29 / AVA-30：已在 Linear 标记 `deferred`，不进入当前 P1b 验收。
- [ ] AVA-31 / AVA-32 / AVA-33 / AVA-34 / AVA-35 / AVA-36：已在 Linear 标记 `deferred`，保留为 P3 backlog，不作为当前可见 UI 或 passing acceptance。
- [ ] 设备侧 LAN Access P2 验收：手机扫码、中国大陆 WiFi、iOS/Android 添加主屏、家用路由器 mDNS 实测；人工验收步骤见 `docs/control-plane-manual-acceptance.md`
- [ ] 移动端原生重设计验收：iPhone 13+ / Pixel 4+ 流畅度、关键场景、横竖屏切换；人工验收步骤见 `docs/control-plane-manual-acceptance.md`

## 架构思路

### 进程模型

```
Electron Main Process
├─ 启动 / 停止 ava-core sidecar
├─ app lifecycle、workspace 选择、系统通知、托盘
└─ 健康检查（不持有核心业务状态）

React Renderer (复用当前 console-ui)
├─ Chat
├─ Settings (Agents Config / Statistics / Tools / Users / System)
├─ Task Overlay (P1b)
└─ Workflow Detail (P2)

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

核心原则：**Electron 管桌面生命周期，Python 管 Agent 控制平面。** ava-core 必须支持 `ava-core serve --port 0 --workspace ...` 独立启动，Electron 只是启动方式之一。

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

P1b 的 WorkflowStore 只服务“看得见、管得住”的体验闭环：ChainBubble、TaskCard、任务 overlay、HUD Artifacts。P2 再扩展为完整 Workflow Runner，不把条件、循环、嵌套、复杂 fan-in 策略提前塞进 P1b。

逻辑分离，物理上可共用存储。不让 BackgroundTaskStore 继续膨胀成万能状态容器。

### 并发与 Workspace

- 默认每个 AgentInstance 同时只执行一个 task。并发能力通过 `AgentCapabilities.max_concurrent_tasks` 声明
- 需要并发就启动多个 AgentInstance，而不是在一个 instance 内部多线程
- Workflow 拥有共享 workspace；Agent 可拥有私有 scratch workspace；跨 Agent 传递必须通过 Artifact 显式表达

### Agent 自动检测与启动

AVA 启动时自动检测本地已安装的 Agent（Claude Code CLI、Codex CLI、Nanobot），已安装的自动带起，未安装的在 Settings → Agents Config 显示；未安装的 Agent 在对应卡片上显示下载按钮跳转到官网。

检测方式：PATH 查找（`claude` / `codex`）、版本命令验证、Nanobot 使用现有 discovery 机制。检测结果持久化到 `AgentRuntimeStore`，启动时刷新。

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
├─ 当前进行中
├─ 历史
├─ 定时任务
└─ 产物视图

Workflow Detail (P2)：
├─ Timeline
├─ Steps
├─ Artifacts
├─ Coordinator Report
└─ Logs
```

### 数据库演进

现有 ava.db schema（sessions / session_messages / token_usage / trace_spans / bg_tasks / media_records / audit_entries）需要扩展以支持多 Agent 模型。方向：

- **agent_registry 表**：持久化已检测的 Agent 信息（name / instance_id / kind / path / version / capabilities / status / last_seen）
- **session_messages 扩展**：增加 `target_agent`（@谁回复）、`source_agent`（谁回复的）、`mention_agents`（@了哪些 Agent）、`context_message_ids`（带入了哪些消息作为上下文）字段
- **bg_tasks 扩展 / workflow_chains 表（P1b light）**：支持 `chain_id`、`parent_task_ids`、9 状态、trace 归属与线性 chain 推进
- **artifacts 表（P1b light）**：产物记录（id / type / uri / metadata / chain_id / task_id），供 Chat 任务 overlay 与 HUD Artifacts 读取
- **agent_workflows 表**（P2）：存储用户自定义的 Agent 流程定义

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

- ava-core 提供 LAN Access 模式（`--lan` 或 Settings 页面开关），启用后监听 `0.0.0.0`，桌面端显示可访问的局域网 URL
- LAN Access 模式是显式开启、可见、可关闭、可审计的状态——不只是 host 切换
- 关闭 LAN Access 后立即停止接受局域网连接，可选择撤销移动端 session
- 可选支持 mDNS/Bonjour 广播（依赖 zeroconf 库，跨平台稳定性有限，作为体验增强而非核心依赖）

**静态资源托管**：

- LAN 模式下 ava-core 需托管 console-ui 静态资源（手机浏览器无法访问 Electron 的 `file://` 页面）
- 桌面 Electron 继续加载本地 bundle 或 dev server；手机访问 `http://<lan-ip>:<port>/`，加载同一份 console-ui
- 不新增独立 mobile app 或独立 mobile routes，复用同一个 bundle、路由、API client、WebSocket client 和状态管理

**安全层**：

- LAN Access 默认关闭
- 通过 PIN（P1b 最低要求）或 QR 完成设备配对；pairing code 短期有效，使用后失效
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

**权限差异**（四级模型）：

- **read_only**（移动端默认）：查看 Agent 状态、任务、workflow、日志摘要、artifact preview
- **reviewer**：read_only + approve/reject workflow、comment
- **operator**：reviewer + cancel/retry task、send_message、submit template task
- **admin**：完整能力，高风险操作（workspace 选择、shell 执行、secret 读取、配置修改、git push、文件写入、重启 ava-core）仍需二次确认

**分期**：

- **P1b**：LAN Access 开关、host 切换、console-ui 托管、PIN 配对（QR 可选）、device token、HTTP/WebSocket 鉴权、响应式 UI 复用、默认 read_only、设备撤销、基础 audit log
- **P2**：QR 配对完善、mDNS/Bonjour、HTTPS/证书策略、PWA manifest、移动端通知、更细粒度权限配置
- **P3**：Relay safety gate、正式 HTTPS contract、远程 inbox、移动推送 contract

### 安全边界

P1 就定下来：

**Electron 侧**：nodeIntegration=false、contextIsolation=true、sandbox=true、preload 只暴露最小白名单（selectDirectory / openPath / getAppConfig / getCoreEndpoint / getAuthToken / showNotification）

**ava-core 侧**：默认只绑定 127.0.0.1；LAN Access 模式下绑定 0.0.0.0 + PIN/QR 设备配对 + device token 鉴权（P1b 先 HTTP，P2 加 HTTPS）；随机端口；启动时生成一次性 session token；所有 HTTP/WebSocket 请求带 token；CORS 白名单；危险操作显式授权；移动端操作记入 audit log

### 版本管理

桌面端有多个版本对象需要追踪：Electron app version / ava-core version / AgentAdapter protocol version / Nanobot version / CLI agent versions / Workflow schema version。P1 就暴露 `/core/version` 和 `/agents/{id}/version` 接口。

## 关键约束

- Nanobot 是默认主 Agent 但不是架构特权角色——coordinator 是 workflow 配置项，不是硬编码系统角色
- 新 Agent 的接入成本尽量低：实现 AgentAdapter + 注册即可
- 前端页面各司其职，互相跳转但不合并
- Electron main process 绝不持有核心业务状态
- ava-core 必须 headless 可运行，Electron 只是启动方式之一
- Python sidecar 打包需要早期验证（依赖管理、PATH/shell 环境、升级机制）
