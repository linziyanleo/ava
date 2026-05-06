# playwright-daily-browser Troubleshooting

## Extension 未连接

症状：
- MCP server 能启动，但浏览器工具报 extension disconnected 或 authorization/token 相关错误。

处理：
- 确认 Chrome 中已安装并启用 Playwright MCP extension。
- 确认 extension 连接的是当前 MCP server。
- 确认 `PLAYWRIGHT_MCP_EXTENSION_TOKEN` 仍与 extension 配对。
- 不要改用会丢失日常登录态的其他连接模式作为默认修复；当前目标是复用日常 Chrome profile。

## ref 失效

症状：
- click/type/select 提示 ref 不存在或元素不可操作。

处理：
- 重新调用 `mcp_playwright_daily_browser_snapshot()`。
- 使用新 snapshot 中的 ref 继续操作。
- 页面导航、提交表单、打开弹窗、切 tab 后都应重新 snapshot。

## 页面或 target 已关闭

症状：
- 返回 `Target page, context or browser has been closed`。

处理：
- 这通常是 Playwright MCP 持有的页面 target 失效，不等于 extension 已断连。
- 当前 nanobot wrapper 会尝试用 fresh MCP session 重试。
- 用 `mcp_playwright_daily_browser_tabs(action="list")` 查看可用 tab。
- 如果目标 tab 已关闭，重新 `mcp_playwright_daily_browser_navigate(url)`。
- 如果只是当前 tab 切错，select 对应 tab 后重新 snapshot。

## 超时

症状：
- `browser_navigate` 或交互工具接近 60s timeout。

处理：
- 不要只凭 timeout 判定失败。
- 先 `browser_snapshot()` 查看当前 URL、标题和页面正文。
- 对异步加载使用 `browser_wait_for` 等待目标文本或状态。

## 什么时候截图

- 读取正文、定位按钮、填表：优先 snapshot。
- 视觉布局、Canvas、图表、图片内容、bug 证据：使用 screenshot。
