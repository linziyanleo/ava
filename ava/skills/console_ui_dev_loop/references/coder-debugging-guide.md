# Coder Debugging Guide

将本节作为每个 console-ui coding prompt 的调试顺序。它是排查路径，不是扩大修改范围的许可。

## 1. 路由与页面身份

先读：

- `console-ui/src/App.tsx`
- `console-ui/src/components/layout/navItems.ts`
- `ava/skills/console_ui_dev_loop/references/page-registry.md`
- 目标页面 reference

确认目标 path、ProtectedRoute 权限、redirect/alias、页面入口组件。若 reference 与 live code 冲突，先在结果中指出冲突，不要静默按旧文档改代码。

## 2. 组件定位

使用 `rg` 搜索失败 check 对应的可见文案、组件名、状态字段或 API 名称。

对目录型页面：
- `ChatPage` 从 `console-ui/src/pages/ChatPage/index.tsx` 开始
- `ConfigPage` 从 `console-ui/src/pages/ConfigPage/index.tsx` 开始

只沿直接 imports 追一到两层，避免无关重构。

## 3. Props / State / API 追踪

定位失败 UI 的 props、state、hooks 和 store 来源。

API 问题从 `console-ui/src/api/client.ts` 和目标页面 fetch/update 调用开始。检查 loading、empty、error、permission、localStorage 持久化状态，再决定是否改渲染逻辑。

## 4. 断言与证据对齐

把 failed check 映射到具体用户动作或 DOM/page_state 事实。默认优先 deterministic 证据；只有 `VISUAL_LAYOUT_REGRESSION` 或 DOM 无法表达的问题才进入截图/视觉判断。

## 5. 样式与布局

样式问题先看受影响组件附近的 `className`、CSS、父容器约束、overflow、responsive layout、text wrapping。避免跨页面 restyle 或重写共享 layout。

## 6. 修改与验证

做能解释证据的最小修改。不要改无关页面、不要顺手重构。验证优先使用本轮 failed checks；最终 pass 前仍按 loop contract 跑 full checklist。
