---
name: playwright_daily_browser
description: 使用 Playwright MCP extension mode 操作本机日常 Chrome profile。适合登录态、内网、SSO/2FA、需要浏览器扩展或已有 tab 的页面；按 Playwright MCP 快照/ref 优先流程执行。
metadata: {"nanobot":{"emoji":"🌐"}}
---

# Playwright Daily Browser

当前 Ava 使用 `playwright_daily` MCP server 连接本机日常 Chrome。它通过 Playwright MCP extension mode 复用用户已登录的 session、cookies、SSO/2FA 状态、浏览器扩展和当前 tabs。

## 何时使用

- 登录态、内网、SSO、2FA 页面
- 用户明确要求操作当前日常 Chrome 或已有 tab
- 页面依赖本机 Chrome 扩展
- `web_fetch` 拿不到 JS 渲染后的正文或登录后内容

普通公网静态页面仍优先 `web_fetch`。不依赖日常 Chrome profile 的自然语言探索可用 `page_agent`。

## 可用工具

工具名前缀是 `mcp_playwright_daily_`：

- `browser_navigate`
- `browser_snapshot`
- `browser_click`
- `browser_fill_form`
- `browser_type`
- `browser_press_key`
- `browser_select_option`
- `browser_tabs`
- `browser_wait_for`
- `browser_take_screenshot`

不要调用未注册的高权限工具，例如 `browser_evaluate`、`browser_run_code`、`browser_file_upload`，除非配置里明确放开。

## 标准流程

1. 需要打开新页面时先 `mcp_playwright_daily_browser_navigate(url)`。
2. 交互前调用 `mcp_playwright_daily_browser_snapshot()`，读取当前可访问性树和元素 `ref`。
3. 点击、输入、选择下拉项时使用 snapshot 里的 `ref`，不要猜 CSS selector、坐标或 DOM 路径。
4. 每次导航、弹窗、提交表单、切 tab、页面大幅变化后重新 snapshot；旧 refs 可能失效。
5. 需要等页面加载、提示出现或异步请求完成时，用 `browser_wait_for`，不要盲目连续点击。
6. 视觉布局、Canvas、图表、图片内容或 bug 证据才用 `browser_take_screenshot`；读取文本和定位元素优先 snapshot。

## 常见动作

登录态页面读取：

```text
mcp_playwright_daily_browser_navigate(url)
mcp_playwright_daily_browser_snapshot()
```

表单：

```text
mcp_playwright_daily_browser_snapshot()
mcp_playwright_daily_browser_type(ref, text)
mcp_playwright_daily_browser_select_option(ref, values)
mcp_playwright_daily_browser_click(ref)
mcp_playwright_daily_browser_snapshot()
```

已有 tab：

```text
mcp_playwright_daily_browser_tabs(action="list")
mcp_playwright_daily_browser_tabs(action="select", index=N)
mcp_playwright_daily_browser_snapshot()
```

## 错误处理

- 如果工具提示 extension 未连接，先让用户确认 Chrome 里的 Playwright MCP extension 已启用并连接；不要切换到会丢失日常登录态的其他浏览器连接模式。
- 如果提示 target/page/context closed，这通常是 Playwright MCP 持有的页面 target 失效，不等于 extension 已断连；runtime 会尝试用 fresh MCP session 重试。若仍返回 `Error:`，显式重新 `browser_navigate` 或用 `browser_tabs` 选择可用 tab 后 snapshot。
- 如果 ref 不存在，立刻重新 snapshot，再根据新的 ref 操作。
- 如果 60s 超时，不要只凭 timeout 判定失败；先 snapshot 或查看当前 URL/标题确认页面状态。
