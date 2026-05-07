---
name: page-agent-test
description: 基于 page_agent 的狭义 smoke / exploratory 测试协议。适合用户明确要求“用 Page Agent”检查页面、路径不确定的多步页面探索，或给上层 wrapper 复用；如需精确截图/ref/验收证据，应搭配 playwright_daily_browser。不是 console-ui 开发闭环，也不默认自动修复。
metadata: {"nanobot":{"emoji":"🔍"}}
---

# Page Agent Test

这是一个基础测试协议，不是当前仓库里的主闭环入口。

- 对 `console-ui` 开发任务，优先使用 `console_ui_dev_loop`
- 这个 skill 只负责页面验证与诊断
- 默认不负责自动修复

## 适用场景

- 对一个或少量页面做 smoke / exploratory 检查
- 需要一个可被 wrapper 继承的 page-agent 测试协议
- 用户明确要求用 Page Agent 评估某个网页
- 登录态/内网/SSO 页面中，目标明确但路径需要 PageAgent 自主探索

## 不适用场景

- 当前仓库里的 console-ui 开发闭环
- 想把它当成 Playwright / Cypress 的稳定替代
- 需要多轮 coding -> regression -> retry orchestration
- 需要精确 ref 点击、截图证据、tab 管理或稳定回归验收；这些用 `playwright_daily_browser`

## 默认协议

1. 明确测试目标
   - 页面路径
   - 预期路由
   - 关键 checkpoint

2. 执行 deterministic-first 检查
   - 先 `page_agent(get_status, response_format="json")`，确认 PageAgent backend 可用
   - 用 `page_agent(execute, response_format="json")` 完成任务级探索
   - 如果当前是 `playwright` backend，可继续 `page_agent(get_page_info, response_format="json")` 并读取 Page State / DOM 事实
   - 如果当前是 `official_mcp` backend，不假设有 Page State / screenshot/session preview；需要证据时改用 `playwright_daily_browser`

3. 仅在必要时升级视觉检查
   - `playwright_daily_browser` 的 snapshot / screenshot
   - `vision(...)` 分析截图
   - 只有 `playwright` backend 才能使用 `page_agent(screenshot, response_format="json")`

4. 输出报告
   - 每个 checkpoint 的状态
   - 失败证据
   - 是否建议交给上层 wrapper 继续修复

## 断言原则

- 先 URL / heading / alerts / forms / buttons
- `official_mcp` 结果只作为 PageAgent 任务结果，不等于可复现验收证据
- 需要 refs、截图、最终状态复核时，用 `mcp_playwright_daily_browser_snapshot()` 或 `mcp_playwright_daily_browser_take_screenshot()`
- 只有颜色、布局、图片、Canvas、SVG 等 DOM 难以表达的问题才升级到 `vision`
- 不要把 `vision` 当默认主判据

## 与 Playwright Daily Browser 的搭配

- PageAgent 负责“看懂目标并自主走流程”
- Playwright MCP 负责“精确观察、精确动作、截图留证、失败定位”
- 常用顺序：`page_agent(execute)` 完成探索或操作 -> `mcp_playwright_daily_browser_snapshot()` 验收文本/结构 -> 必要时 `mcp_playwright_daily_browser_take_screenshot()` 留证
- 高风险最终动作（提交、删除、支付、发布、权限变更）必须先停在确认前状态，用 Playwright snapshot/screenshot 向用户展示，不让 PageAgent 直接完成最后一步

## 浏览器持久化

- `official_mcp` backend 通过 Page Agent Chrome Extension 使用用户日常 Chrome 的登录态、SSO、扩展和当前 tab，需要 extension Hub connected
- `playwright` backend 使用 Ava 旧本地 runner 的独立 profile/session；它不是用户日常 Chrome

## 边界

- pass/fail 仍然是 best-effort，不等于 CI 级验收
- 默认不调用 `claude_code`
- 如需修复循环，应由上层 wrapper 明确编排
- 当前官方 PageAgent MCP 只提供 `execute_task/get_status/stop_task`；不要要求它返回 Playwright refs、MediaService screenshot path 或 console `/browser` screencast
