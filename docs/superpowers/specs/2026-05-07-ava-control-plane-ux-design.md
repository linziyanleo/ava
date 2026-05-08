# AVA 控制平面 UX 重设计 · Design Spec

> 日期：2026-05-07
> 状态：Design (pre-implementation plan)
> 范围：console-ui 前端整体 IA 与 Chat / Settings 两个一级页面的样式建议与实现方向；不含具体实现细节
> 配套愿景：参见 `IDEA.md`（AVA 多 Agent 协同平面）

---

## 0. 设计目标

把当前 console-ui（12 项一级导航 + 网关中心化的 DashboardPage + 多个并列资源页）重设计成符合 AVA "本地优先 Agent Control Plane" 定位的产品形态：

- 唯一的高频入口是 **Chat**——"对话即操作"；
- 所有"非动作"内容（配置、统计、工具、系统能力）收纳进 **Settings**；
- 任务、产物、链结构在对话中显式可见，但不刷屏；
- 桌面优先，移动端用现有响应式自适应，不做专属重设计。

非目标（YAGNI 边界）：
- 不做移动端独立 IA / 手势 / 全屏 sheet；
- 不做 LAN Access P2 增强（HTTPS / QR / PWA / mDNS）；
- 不做用户手动编排 Workflow（由 Nanobot+Skill 隐式覆盖）；
- 不做"Inbox（审批流）"，留给 P3。

---

## 1. 顶层信息架构

### 1.1 一级页面（仅两个）

- **Chat**：重交互 + 部分观测。承担 80%+ 的日常使用时间。
- **Settings**：状态观测 + 状态配置。承担配置、监控、统计、系统管理。

两个页面并列、独立路由。Chat 是默认首屏。

### 1.2 路由建议

- `/` → Chat（默认）
- `/settings/...` → Settings 子目录
- 任务页是 Chat 内部的 **state 切换覆盖层**，不是独立路由；但 URL 支持 `?task_id=` / `?chain_id=` / `?trace_id=` 参数，用来直链跳转到具体任务卡或对话片段。
- 旧路由（`/agents` `/config` `/memory` `/persona` `/skills` `/media` `/chat` `/tasks` `/bg-tasks` `/tokens` `/users` `/browser` `/`-DashboardPage）全部映射或退役（详见 §7 迁移清单）。

### 1.3 Chat 与 Settings 的关系

- Settings 不嵌入 Chat 内部，是平级独立页面；Chat 内提供"前往 Settings"的入口按钮（建议放会话栏底部，与用户头像/退出登录同区）。
- Chat 内出现的 Agent 头像、Skill 名称、Token chip 等，可作为深链跳到对应 Settings 子页（例：点击 HUD 的 Token → Statistics 该会话页；点击对话头像 → Agents Config 对应 Tab）。

---

## 2. Chat 页面设计

### 2.1 总体骨架（桌面 ≥ 768px）

四区块，沿用当前暗色主题与 1px 圆角卡片风格：

- **左：会话栏（窄列）**
  - 默认按更新时间倒序；顶部排序切换按钮可切换为"按 Agent 分组"（多 Agents / Nanobot / Claude Code / Codex / Image Gen…）
  - 每条会话项展示：标题 / 最近消息摘要 / 参与 Agent 头像群（小尺寸） / 时间 / 未读徽标
  - 不再展示 Channel 桥接 session（数据另存，渠道信息内化为会话属性）
  - 底部：Settings 入口、用户头像、角色徽标、主题切换、退出

- **右上：任务状态预览栏 + 对话配置区**
  - **任务预览栏**（最上一行）：水平 chip 流，显示进行中 / 排队任务（每 chip 含 Agent 图标 + 任务标题省略 + 状态色），右端 [⛶ 展开] 按钮 → state 切换为「任务页」全覆盖对话区
  - **对话配置区**（紧贴下方）：当前对话参与的 Agents（可单选/多选）、Context Size（数字 + 进度条）、[压缩] 按钮、[查看压缩后上下文] 链接、当前 channel 标识（如"console / telegram / cli"，只读 chip）

- **中：对话区**
  - 群聊式排版：每条消息左侧 Agent 头像（用户消息靠右、Agent 消息靠左）
  - Agent 头像点击 → 浮层菜单：[查看状态] / [@ Ta] / [进入私聊]
  - 用户消息触发的任务以 **ChainBubble** 形式插入对话流（详见 §2.3）
  - AVA 主 Agent（Nanobot）的旁白回复仍是普通气泡

- **下：输入区 + HUD**
  - 输入区一行：左侧两个图标按钮（[⚡ 快速命令] / [📎 文件上传]）+ [📚 快速上下文] 入口、中间多行输入框、右侧 [发送 →]
  - 最下一行：HUD 状态栏（详见 §2.5）

### 2.2 多 Agent 群聊语义

- 一条会话可绑定多个 Agent。对话配置区的"Agents 选择"决定该会话的"默认收件人集合"。
- 默认主回复者是 Nanobot（不是硬编码特权角色，是配置项）。
- 用户消息中 `@codex` / `@claude_code` 显式指名 → 该 Agent 收到上下文并回复，主 Agent 仍获得全局上下文但不重复回复。
- Agent 头像在每条消息旁边出现，方便用户视觉上"知道是谁说的话"。

### 2.3 任务在对话里的呈现 — ChainBubble

- 一次 Skill 触发 = 一个 **ChainBubble**（对话流的原子单元，不可被打散）
- ChainBubble 内部：多张 **TaskCard 竖向连线**，从上到下表示链路顺序，分支由竖线 + 缩进表达
- TaskCard 默认形态（精简）：
  - 一行标题（任务名 / Agent kind）
  - 状态徽章（详见 §2.4）
  - 当前进度文字（如"running 4s" / "等待 codex#A12"）
  - 折叠态的 [展开日志 ›] 链接
- TaskCard 展开形态：
  - 内嵌 stdout 滚动区（最多 N 行 + "查看完整日志"链接跳到任务页详情）
  - artifact 预览（diff / 文件名 / 图片缩略图 / json 摘要）
  - 操作按钮：[取消整链] / [打开产物] / [重试]
- 链结构对用户**完全显式**——这是有意的产品哲学："让用户看清 AVA 怎么编排"。
- 取消语义：单卡上的取消按钮 = **取消整链**（不是只取消该步）；上游已完成的步骤不会回滚，下游未开始的会被标 `cancelled` / `skipped`。

### 2.4 TaskCard 状态枚举

九个状态，对应不同的徽章颜色与可操作动作：

| 状态 | 含义 | 视觉 | 动作 |
|---|---|---|---|
| `pending` | Nanobot 在解析 skill / 注册链 | 灰 spinner | 取消整链 |
| `awaiting_deps` | 等待前置任务（注明依赖谁） | 琥珀 | 取消整链 |
| `queued` | 已分配给 Agent，排队中 | 蓝（淡） | 取消 |
| `running` | Agent 在执行（无可见产出） | 蓝 spinner | 取消 / 展开日志 |
| `streaming` | 在产生 artifact（写文件 / 生图等可见进度） | 蓝（亮） + 进度条 | 取消 / 展开日志 / 看实时产物 |
| `succeeded` | 成功 | 翠绿 | 打开产物 / 看日志 |
| `failed` | 失败（含 error 摘要） | 红 | 重试该步 / 看日志 |
| `cancelled` | 用户主动取消 | 灰 | 重试整链 / 看日志 |
| `skipped` | 因前置失败/取消被跳过 | 灰（虚线） | 重试整链 / 看日志 |

`running` 与 `streaming` 保留区分——前者只是 spinner，后者代表"有可见产出正在生成"，让用户感受到不同。

### 2.5 HUD 状态栏

- 一行横向滚动 chip 流，每个 chip 是**独立可拼接前端组件**（widget），可单独扩展、可单独换实现、可单独 capability 隐藏
- 候选 widget（P1b 起步集合，未来可加）：
  - **Token** chip — 当前对话累计 token；点击 → 跳到 Settings → Statistics 该会话页
  - **Skills** chip — 当前对话已加载 skill 数量；点击 → 展开抽屉（卡片式列出可用 skill，可点选触发）
  - **QuickCtx** chip — 当前生效的快速上下文（数量/名称）；点击 → 展开编辑器
  - **Artifacts** chip — 当前对话产生的产物数量；点击 → 跳到任务页的"产物视图"
  - **Time** chip — 当前时间（本地时区）
  - **Memory** chip — 当前 ava-core 进程内存占用；点击 → System 页 Gateway 子页
- 实现方向：HUD 行容器只负责"水平滚动 + 渲染传入的 widget 列表"；每个 widget 自治（请求自己的数据 / 处理自己的 click 行为 / 决定自己的可见性）。

### 2.6 上下文管理

- 配置区显示 Context Size：当前 token / 模型上限 / 进度条颜色随占用率变化（绿 → 琥珀 → 红）
- [压缩] 按钮：触发后端压缩当前对话上下文（保留最近若干轮 + 摘要早期消息）
- [查看压缩后上下文] 弹出 modal / 抽屉，展示压缩前后对比（diff 风格）
- 压缩是一次性动作，不是自动；用户决定何时执行。

### 2.7 Skill 触发方式

两个入口（同时启用）：

- **自然语言匹配**：用户在 Chat 里自然描述意图，Nanobot 主 Agent 内部匹配最合适的 skill，生成 ChainBubble；匹配过程对用户半透明（AVA 旁白会说"我会用 skill X 来完成 Y、Z"）
- **`@skill_name` 显式触发**：用户在输入框里以 `@skill_name` 开头，跳过自然语言匹配，直接执行该 skill；输入框自动补全候选 skill 列表
- 辅助入口：HUD 的 Skills chip 展开抽屉，可在抽屉里点选 skill 触发（等价于 `@skill_name`）

### 2.8 任务页（state 切换覆盖）

- 触发点：任务预览栏右端 [⛶展开]
- 实现方向：**同路由 state 切换**（不是独立路由），但通过 URL `?task_id=` / `?chain_id=` 支持从外部直链跳转
- 内容分区：
  - **当前进行中**：所有 running / queued / awaiting_deps 任务列表（完整 TaskCard 形态，含日志和产物预览）
  - **历史**：已完成 / 失败 / 取消的任务，可按 Agent / 时间 / 状态过滤
  - **定时任务**：cron 形式的预设任务编辑器（旧 ScheduledTasksPage 内容迁来）
  - **产物视图**：所有任务输出的 artifact 集合（图片 / 文件 / diff / json），按时间倒序网格化呈现；这里就是旧 MediaPage 的归宿
- 视觉建议：进入任务页用淡入 + 上滑动画；右上角有 [× 关闭] 回到对话区。

---

## 3. Settings 页面设计

### 3.1 总体骨架

- 左侧子目录 sidebar，右侧详情区。视觉与 macOS System Settings / VS Code Settings 风格一致。
- 五大块顶层分组：**Agents Config / Statistics / Tools / Users / System**
- 顶部支持搜索框（搜索所有子项 / 配置项）作为加分项，P1b 可以先不做。

### 3.2 Agents Config（关键解耦点）

进入 Agents Config 默认看到 **Agent 总览**（卡片网格式，每张卡片对应一个 Agent，展示状态/版本/路径/活跃任务/近期事件），复用当前 AgentDashboardPage 的卡片视觉。点击卡片或顶部 Tab 切换进入具体 Agent Tab。

每个 Agent Tab 内承载该 Agent 的全部"自有内容"：

- **Nanobot Tab**
  - `config.json` 可视化编辑（当前 ConfigPage 的 Nanobot 部分迁来）
  - `MEMORY.md` / `HISTORY.md`（当前 MemoryPage 内容迁来）
  - Persona（当前 PersonaPage 迁来）
  - Status / Version / Path
  - 近期事件 / 产物
- **Claude Code Tab**
  - `settings.json` 可视化编辑
  - `CLAUDE.md`
  - Status / Version / Path
- **Codex Tab**
  - `config.toml` 可视化编辑
  - `AGENTS.md`
  - Status / Version / Path
- **Image Gen Tab**
  - 配置 / 模型 / API key
  - Status

**关键技术债**：当前 ava 的 ConfigPage 与 Nanobot 配置高度耦合（实质是一个 Nanobot config 编辑器），但顶层叫"通用配置"。重构时必须**把 Nanobot 专属配置从通用 Console 配置中剥离出来**，让"通用 Console 配置"和"Nanobot 配置"成为各自独立的概念：

- 通用 Console 配置 → Settings → System
- Nanobot 专属配置 → Settings → Agents Config → Nanobot Tab

未来加新 Agent 时，**只需要在 Agents Config 里新增一个 Tab**，不应该污染通用 Console 配置。

### 3.3 Statistics

- Token Usage 统计，按 Agent 适配（每个 Agent 是独立的 chart 组合）
- 维度切换：按时间 / 按会话 / 按 Agent / 按 model
- 单会话维度的统计页可从 Chat HUD Token chip 直接深链跳入
- 旧 TokenStatsPage 内容迁来，但要按 Agent 重新组织（之前是单一统计大杂烩）

### 3.4 Tools

- **Skill 管理**：列表（CRUD） / 详情（YAML/JSON 视图 + 可视化编辑） / 试运行（一段 prompt 触发，结果以 TaskCard 形式弹出 mini 浮层 / 或链接到 Chat 看完整链）
- **内置工具管理**：AVA 自带的工具集合（fs / git / shell / browser-cdp 等）的开关与配置
- **MCP 管理**：MCP server 注册、连接状态、工具列表浏览

### 3.5 Users

- admin only（沿用现有 ProtectedRoute）
- 内容沿用当前 UsersPage：用户列表 / RBAC / 创建 / 重置密码 / 撤销
- 新增（P1b 起步占位）：device session 列表（LAN Access 配对的设备 token），admin 可撤销

### 3.6 System

新增的兜底大类，承载所有"非 Agent 自有、非 Tool / Skill、非 Stats"的系统级能力：

- **LAN Access**（新建）
  - 总开关（默认关）；启用后展示局域网 URL、PIN 配对入口、device token 列表、撤销操作、audit log 摘要
- **Gateway**（旧 DashboardPage 网关部分迁来）
  - 状态（在线 / 离线 / PID / 端口 / uptime / boot generation）
  - 操作：Restart / Force Restart / Rebuild Console
  - 版本信息
- **Browser**（旧 BrowserPage 迁来）
  - 诊断工具，保留原样
- **Console**（新建）
  - 通用 Console 配置（host、port、log level、theme 等），跟 Agents Config 解耦后的"非 Agent 部分"
- **Version**（新建）
  - core version / agent versions / protocol version / build hash 一览

---

## 4. 数据流与状态管理

### 4.1 单一状态源

- **BackgroundTaskStore** 是任务相关的唯一真理：
  - Skill 解析 → 任务链注册到 store
  - Agent 输出（events / artifacts / status）通过 ava-core 同步更新 store
  - 前端通过 WebSocket 订阅 store 变化，响应式重渲染
- **AgentRuntimeStore** 是 Agent 运行时状态的唯一真理（已存在，沿用）
- 前端不应该有独立的 task / agent 状态拷贝；ChainBubble、TaskCard、任务页、顶部任务条、HUD Artifacts、Settings 的 Agent 状态展示——全部从同一个 store 读取。

### 4.2 前端 store 实现方向

- 沿用当前 zustand 风格（`useAuth` / `useTheme` 等）
- 新增 store（实现层级，命名暂定）：
  - `useTaskStore`（订阅后端 BackgroundTaskStore）
  - `useChainStore`（chain 与 task 的关系映射）
  - `useChatStore`（会话 / 消息 / 配置 / context）
  - `useAgentRegistryStore`（订阅 AgentRuntimeStore；当前 AgentDashboardPage 的状态来源）
- 实现细节（schema / API / 字段命名）留给 implementation plan，不在本 spec 内决定。

### 4.3 实时性

- 任务状态变化、stdout 流、artifact 产生 → WebSocket 推送
- 心跳 / Agent 在线 / 系统状态等低频信号 → polling（沿用现有 10s 节拍）

---

## 5. 视觉风格建议

### 5.1 沿用现有暗色主题
- CSS 变量：`var(--bg-primary | --bg-secondary | --bg-tertiary)` / `var(--text-primary | --text-secondary)` / `var(--accent | --accent-hover)` / `var(--success | --warning | --danger)`
- 卡片：`rounded-xl` + 1px border + 适度阴影
- 按钮：高度 36-40px，内边距 12-14px，hover 状态用 `--accent` 边框过渡
- 字号：标题 14-16px / 正文 13px / HUD chip 与状态徽章 11px / 元数据 10px

### 5.2 状态色规范
- 成功 → emerald (`--success`)
- 运行 / 进行中 → blue (`--accent` 或独立蓝)
- 等待 / 排队 → amber
- 失败 → red (`--danger`)
- 取消 / 跳过 → gray（`--text-secondary` 调淡）

### 5.3 Agent 视觉编码
- 每个 Agent 类型对应一个 lucide 图标（已存在的：Bot / Terminal / Zap / Image），保持一致
- Agent 头像在对话气泡旁、会话项里、ChainBubble 的 TaskCard 上、Tab 切换等多处出现，必须**视觉统一**（同一颜色、同一尺寸规格库 sm / md / lg）

### 5.4 ChainBubble 视觉

- 整个 ChainBubble 包在一个浅色卡片容器里，外侧有"群聊气泡"的视觉提示（左侧 Agent 头像 + 时间）
- 内部 TaskCard 之间用 1px 实线（已完成）/ 1px 虚线（等待）连接
- 当前活跃步骤的 TaskCard 用 `--accent` 边框高亮
- 整链失败时，ChainBubble 整体加红色边框警示

### 5.5 任务页过渡

- 进入：对话区淡出 + 任务页从右侧滑入（200-300ms）
- 退出：反向
- URL 参数变化（`?task_id=`）时也应该走同一动画路径，从对话区无缝过渡到对应任务卡

---

## 6. RBAC、移动端与可扩展性

### 6.1 RBAC

- 沿用现有 `ProtectedRoute` + `mock_tester` 模式
- read_only / mock_tester 用户在 Chat：输入框 disabled + 顶部 banner 提示"只读模式 · 申请权限"
- 操作按钮（取消任务、重试、压缩、Settings 的写入操作）按 capability 隐藏或 disable
- 设备 token capability 同样按 RBAC 应用（移动端 LAN 设备默认 read_only，可在 Settings → Users → 设备列表里授权升级）

### 6.2 移动端

- 不做专属重设计；沿用 `useResponsiveMode`（768px 断点）和现有 mobile bottom nav
- 底部 nav 收敛到 **Chat / Settings 两项**（删除当前 12 项中的其他）
- 新组件（ChainBubble、TaskCard、HUD chip、对话配置区）在窄屏下应优雅自适应：
  - HUD 横向滚动天然兼容
  - ChainBubble 在窄屏下卡片宽度自适应、连线缩短
  - 对话配置区在窄屏下折叠为单行 chip + [展开] 按钮
  - 任务预览栏 chip 流横向滚动
- 移动端任务页覆盖 → 全屏覆盖（同桌面 state 切换语义，只是 viewport 不同）

### 6.3 可扩展性

- HUD widget 是独立组件——加一个新的 HUD 项不应触动 HUD 容器逻辑
- Settings → Agents Config 加新 Agent Tab 不应触动通用 Console 配置
- ChainBubble 内 TaskCard 类型可扩展（未来加新 Agent / 新状态时只需加图标和颜色映射）
- 路由参数化（`?task_id=` / `?chain_id=` / `?trace_id=`）让任意外部链接（IM / email / Telegram bot）能直链 deep-link 到具体对话片段

---

## 7. 退役 / 迁移清单

| 现有路由 / 页面 | 处理 | 去向 |
|---|---|---|
| `/`（DashboardPage 网关中心首页） | **退役** | 网关状态/重启/构建 → Settings → System → Gateway；其余卡片快捷入口取消 |
| `/agents`（AgentDashboardPage） | **重组** | 卡片浏览功能并入 Settings → Agents Config 总览（详见 §3.2）；direct task / restart / cancel 操作合入对话流（通过 Chat 中 Agent 头像点击的浮层菜单触发） |
| `/config`（ConfigPage） | **解耦+迁移** | 通用 Console 配置 → Settings → System → Console；Nanobot 配置 → Settings → Agents Config → Nanobot |
| `/memory`（MemoryPage） | **迁移** | Settings → Agents Config → Nanobot Tab 内"Memory"section |
| `/persona`（PersonaPage） | **迁移** | Settings → Agents Config → Nanobot Tab 内"Persona"section |
| `/skills`（SkillsPage） | **迁移** | Settings → Tools → Skill 管理 |
| `/media`（MediaPage） | **重组** | 媒体产物全部进 Chat 任务页的"产物视图"；Image Gen 配置进 Settings → Agents Config → Image Gen Tab |
| `/chat`（旧 ChatPage） | **重写** | 新 Chat 一级页面；旧 ChatPage 中 Channel / Telegram / CLI 桥接 session 数据并入新会话流，渠道作为会话属性 |
| `/tasks`（ScheduledTasksPage） | **迁移** | Chat 任务页的"定时任务"分区 |
| `/bg-tasks`（BgTasksPage） | **迁移** | Chat 任务页的"当前进行中" + "历史"分区 |
| `/tokens`（TokenStatsPage） | **迁移** | Settings → Statistics |
| `/users`（UsersPage） | **迁移** | Settings → Users |
| `/browser`（BrowserPage） | **迁移** | Settings → System → Browser |

---

## 8. 上线节奏与 P2/P3 边界

### P1b 必须落地
- 新 IA（Chat / Settings 平级两页）
- Chat 完整骨架（左会话栏 / 右上任务栏+配置区 / 中对话区 / 输入+HUD）
- ChainBubble + 9 状态 TaskCard
- 任务页 state 切换 + URL 直链（`?task_id=` / `?chain_id=` / `?trace_id=`）
- Settings 五大块基本可用：Agents Config（含解耦）、Statistics、Tools、Users、System
- Skill 触发的两个入口（自然语言 + `@skill_name`）
- 旧路由全部退役 / 重定向，无残留入口
- HUD 至少 4 个 widget：Token / Skills / Artifacts / Memory

### P2 留白
- Workflow Detail 页（如果未来用户主动手动编排，再做）
- Inbox（审批流）
- LAN Access 安全增强：HTTPS / QR 配对完善 / mDNS / PWA
- 移动端真机打磨与设备侧验收
- HUD widget marketplace（第三方 widget 上传与分发）

### P3 留白
- Relay / 远程访问
- 多用户协作（多人同时操作同一会话）
- 移动推送

---

## 9. 实现方向（不含细节）

按"先骨架后内嵌"的顺序：

1. **路由与 Layout 重写** — 确立 `/` Chat 与 `/settings` 两个独立 page，Layout 拆分；旧路由先全部 redirect。
2. **会话 store + 对话区 shell** — 建立 `useChatStore`，渲染基本群聊式气泡。
3. **任务 store + ChainBubble** — 建立 `useTaskStore` + `useChainStore`，渲染 TaskCard / 链 / 9 状态 / 取消语义。
4. **任务预览栏 + 任务页 state 切换** — 上方 chip 流 + 全屏覆盖任务页 + URL 参数。
5. **HUD 容器与 widget 抽象** — 先做容器和 4 个核心 widget。
6. **Settings 五大块骨架 + 旧页迁移** — 先把所有旧内容迁过去，再做 Agents Config 解耦。
7. **Skill 触发链路** — 自然语言匹配（Nanobot 侧）+ `@skill_name` 输入框补全 + Skills 抽屉触发。
8. **响应式自适应 + RBAC 收口** — 检查所有新组件在 < 768px 下行为；按 capability 收口操作按钮。

详细 task 拆分、文件清单、组件 API、store 字段 schema、WebSocket 协议变更等，留给后续 implementation plan 决定。

---

## 10. 开放问题（待 implementation 阶段决议，非阻塞 spec）

- HUD widget 的注册机制：静态枚举 vs 动态发现？P1b 用静态枚举即可。
- 会话与 Channel 的 schema 合并：是否需要 DB 迁移把旧 Channel session 重命名为统一 session？建议在 implementation 阶段评估数据量决定 in-place migration vs 双轨过渡。
- Skill 试运行的 UX：弹 mini 浮层 vs 跳到 Chat 用临时会话？P1b 推荐 mini 浮层（轻量）。
- ChainBubble 内 TaskCard 的折叠行为：链很长（>5 步）时是否默认折叠中段？建议 P1b 不折叠，等真实数据再调。
