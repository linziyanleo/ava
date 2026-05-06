---
name: playwright-daily-browser
description: 使用 Playwright MCP extension mode 操作本机日常 Chrome profile。适合登录态、内网、SSO/2FA、需要浏览器扩展或已有 tab 的页面；按 snapshot/ref 优先流程执行。
---

# playwright-daily-browser

Ava/nanobot 当前通过 `playwright_daily` MCP server 连接本机日常 Chrome。它使用 Playwright MCP extension mode，直接复用日常 profile 的登录态和扩展。

## 当前配置

```json
{
  "mcpServers": {
    "playwright_daily": {
      "command": "/Users/fanghu/.local/share/mcp-runners/node_modules/.bin/playwright-mcp",
      "args": ["--extension", "--browser", "chrome", "--user-data-dir", "/Users/fanghu/Library/Application Support/Google/Chrome"],
      "toolTimeout": 60,
      "enabledTools": [
        "browser_navigate",
        "browser_snapshot",
        "browser_click",
        "browser_fill_form",
        "browser_type",
        "browser_press_key",
        "browser_select_option",
        "browser_tabs",
        "browser_wait_for",
        "browser_take_screenshot"
      ]
    }
  }
}
```

## 使用边界

- 登录态、内网、SSO、2FA、需要本机 Chrome 扩展或已有 tab 时，优先使用 `mcp_playwright_daily_*`。
- 普通公网静态页面仍优先 `web_fetch`。
- 不依赖日常 Chrome profile 的自然语言多步探索可用 `page_agent`。
- 不要启动调试端口连接，不要复制或杀掉日常 Chrome profile。

## Playwright MCP 流程

1. `mcp_playwright_daily_browser_navigate(url)` 打开目标页。
2. `mcp_playwright_daily_browser_snapshot()` 获取 accessibility snapshot。
3. 用 snapshot 中的 `ref` 调用 click/type/fill/select/press；不要猜 selector 或坐标。
4. 导航、提交、弹窗、切 tab、页面刷新或 DOM 大幅变化后重新 snapshot。
5. 需要等待页面文本或状态时用 `browser_wait_for`。
6. 只有视觉布局、Canvas、图表、图片内容或 bug 证据需要截图时才用 `browser_take_screenshot`。

## 排障

更多排障见 `references/troubleshooting.md`。
