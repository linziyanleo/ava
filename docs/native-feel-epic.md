# Ava Native-Feel Epic

> 范围：把 Ava Console（Electron 桌面壳 + console-ui）从「跑在 Electron 里的网页」往「macOS / Windows 原生应用观感」推一档。
>
> 原则：
> - 视觉/交互层级，不动后端契约、不改路由、不动 RBAC。
> - 桌面观感优先（macOS/Windows），mobile/Web 不退化。
> - DESIGN.md「Warm Operations Cockpit」token 保持权威，原生感通过 token 表达，不引入新的硬编码颜色。

## 节奏

| 批次 | 条目 | 风险 | 观感 |
|------|------|------|------|
| 第一波（即刻落） | NF-1 / NF-2 | 低 | 高 |
| 第二波（与 UI audit 联合） | NF-3 / NF-5 / NF-6 / NF-7 | 中 | 中-高 |
| 单独评估 | NF-4 | 中 | 中 |

UI audit 见 `docs/UI_AUDIT.md`。第二波改动应该一次性把 §6「已知差异」一并清掉。

---

## NF-1 · 无边窗 + 拖拽区 + traffic light 让位

**目标**：macOS 上把窗口边框收掉，只留沉浸式 TopBar；TopBar 任意空白可拖；红黄绿不压 logo。Windows 保留默认 frame，不强求自绘。

**落点**：
- `electron/main.mjs` BrowserWindow：darwin 增加 `titleBarStyle: 'hiddenInset'`、`trafficLightPosition: { x, y }`、`backgroundColor: '#0f1512'`（dark canvas，避免白闪）。
- `electron/preload.cjs`：`avaDesktop` 暴露 `platform`（`darwin` / `win32` / `linux`），让渲染端按平台调左 padding。
- `console-ui/src/App.tsx`：启动时把 `process.platform` 写到 `<html data-platform="darwin">`，CSS 据此处理 traffic light 让位。
- `console-ui/src/components/layout/TopBar.tsx`：header 整体 `-webkit-app-region: drag`，所有可点元素（NavLink / TaskPreviewBar / AvatarMenu）加 `-webkit-app-region: no-drag`。darwin 时左侧 padding ≥ 78px 给 traffic lights。

**验收**：
- macOS：双击 .app，TopBar 空白处可拖窗；红黄绿位于 TopBar 左上，垂直居中，不重叠 AVA logo；窗口启动无白闪。
- Windows：保留系统 frame，TopBar 拖拽不干扰系统按钮。
- Linux：保留默认行为。
- Web（dev server `pnpm dev`）：drag region CSS 不破坏 hover/click。

## NF-2 · 系统字体栈

**目标**：默认字体跟随操作系统（macOS = SF Pro / PingFang SC，Windows ≥ 11 = Segoe UI Variable，Linux = system-ui），CJK 自动落到系统中文字体；代码块用 `ui-monospace`。

**落点**：
- `console-ui/src/index.css`：
  - 新 token：`--ava-font-sans`、`--ava-font-mono`、`--ava-font-cjk-extra`（细分调控点）。
  - `body { font-family: var(--ava-font-sans); }`。
  - `code, pre, .markdown-body code { font-family: var(--ava-font-mono); }`。
- 不再依赖 Inter；如未来要回 Inter，也只改 token。

**验收**：
- macOS DevTools 选 body：computed font-family 第一项命中 `system-ui` / `-apple-system`；中文字段命中 PingFang SC。
- Windows 11：computed font-family 命中 `Segoe UI Variable`。
- 代码块 computed font-family 命中 `ui-monospace` / `SFMono-Regular` / `Cascadia Code`。
- DESIGN.md CJK line-height 1.8 不变（依然由 `--cjk-line-height` 控制）。

## NF-3 · macOS vibrancy / 半透明背板

**目标**：macOS 主窗体背景使用 `vibrancy: 'sidebar'`（或 `under-window`），让 Dock / 桌面壁纸隐隐透出，但不破坏 dark/light token 对比度。

**落点**：
- `electron/main.mjs` BrowserWindow（darwin）：`vibrancy: 'sidebar'`、`visualEffectState: 'active'`、`transparent: true`（仅 darwin）。
- `console-ui/src/index.css`：`html[data-platform="darwin"] body { background: transparent; }`，但 surface/raised 卡片保留实色。
- light theme 同样适配。

**风险**：透明 + transition 容易产生重绘卡顿；要确认 `prefers-reduced-transparency`。

**验收**：
- macOS：拖窗时背后 wallpaper 可见但不晃；切 dark/light，对比度仍 > AAA。
- 关闭 macOS 系统「减少透明度」时（reduce transparency）回退到实色 `--ava-bg-canvas`。

## NF-4 · 系统 accent color follow（独立评估，非本批落地）

**目标**：可选项。让按钮/链接的 accent 颜色跟随 macOS「强调色」系统设置。

**风险**：会破坏 DESIGN.md 中 `--ava-primary` 的 brand 一致性。**默认不开启**，仅放出 `prefers-accent-color` opt-in。本 epic 仅做调研和占位，不动代码。

## NF-5 · 原生 contextMenu

**目标**：渲染端任意位置右键，弹原生 Electron contextMenu，至少包含「拷贝 / 粘贴 / 检查元素（dev 时）」。文本字段额外加「全选 / 拼写检查」。

**落点**：
- `electron/main.mjs`：在 BrowserWindow webContents `'context-menu'` 事件监听，按 `params.editFlags` 组装 `Menu.buildFromTemplate`。
- 渲染端：消息气泡的「复制 / 重发」自定义菜单保持不变，但浏览器默认右键事件不再被拦。

**验收**：右键 ChatInput textarea：剪切 / 复制 / 粘贴 / 全选 / 拼写。右键消息气泡：拷贝命中所选文本。dev mode 多一条「Inspect Element」。

## NF-6 · 原生滚动条行为

**目标**：macOS 走系统 overlay scrollbar（手势滚动时才出现，停止后淡出）；Windows 11 用更贴系统的细条；移动 Safari 不被 6px 强制条遮住。

**落点**：
- `console-ui/src/index.css`：把现有 `::-webkit-scrollbar` 6px 规则收到 `html[data-platform="win32"], html[data-platform="linux"]` 下；macOS 不写自定义条，让浏览器内核走系统 overlay。
- `scrollbar-gutter: stable both-edges` 给固定列表，避免内容跳动。

**验收**：macOS 闲置 1.5s 后滚动条消失；滚动时浮现，不挤压内容。Windows 滚动条贴系统主题色。移动端不变。

## NF-7 · spring / native 过渡曲线 token 收敛

**目标**：把所有过渡曲线收敛到三档 motion token：`fast / normal / slow`，曲线加 macOS 风的 `cubic-bezier(0.32, 0.72, 0, 1)`（接近 SwiftUI default spring）。`prefers-reduced-motion` 全局生效不变。

**落点**：
- `console-ui/src/index.css`：新 `--ava-ease-spring: cubic-bezier(0.32, 0.72, 0, 1)`；现有 `--ava-ease-standard` 保持兼容。
- 关键浮层组件（TaskFloater、HeaderOverflowSheet、ContextLensDrawer、SearchModal、AvatarMenu popover）切到 `--ava-ease-spring`。
- 普通 UI 状态过渡（hover / theme switch）仍走 `--ava-ease-standard`。
- 全文搜索 `cubic-bezier(`、`transition:.*ms` 字面量，统一收敛到 token。

**验收**：UI audit §0.4 第 6 条「动效：过渡走 token」不再出现裸值。

---

## 联合改造：第二波 + UI audit §6 已知差异

执行 NF-3/5/6/7 时一并修：
- `components/TraceTimelineDrawer.tsx` 13-25, 202-204：status pill 改 StatusBadge / soft+border 三段。
- `pages/MediaPage.tsx:301`：`bg-[var(--success)]/10` → `bg-[var(--ava-success-soft)]`。
- `pages/MediaPage.tsx:449-451`：状态 span → StatusBadge。

每改一处，按 UI_AUDIT.md §0.5 报告格式补一行。

## 不在本 epic 内（明确划掉）

- 整体重新定义 DESIGN.md 视觉系统（保持 v0.4.3-B）。
- 移动端原生重设计（属 AVA-30，独立 epic）。
- 自绘 Windows 标题栏（成本太高，收益边际）。
- 替换 React/构建工具链。
