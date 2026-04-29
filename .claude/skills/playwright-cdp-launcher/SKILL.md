---
name: playwright-cdp-launcher
description: 在需要访问登录态、内网、JS 渲染页面，或准备调用 mcp__playwright-cdp__* 工具前，检查 playwright-cdp 的 Chrome/CDP 状态并按模式给出最小修复路径。
---

# playwright-cdp-launcher

这个 skill 只负责项目级环境拉起与诊断，不改用户全局配置，不清理全局 MCP / skill / plugin。

> 2026-04-29 状态：Ava/nanobot 默认已改为 direct extension mode，见 `~/.ava/config.json.tools.mcpServers.playwright_cdp` 与 `.specanchor/tasks/_cross-module/2026-04-28_nanobot-playwright-cdp-mcp-smoke.spec.md`。CDP wrapper / `--cdp-endpoint http://127.0.0.1:9222` 是历史 fallback，只在 extension Bridge 完全不可用且用户确认切换时使用。

## 适用场景

- 需要访问 WebFetch 抓不到的登录态、内网或 JS 渲染页面
- 准备调用 `mcp__playwright-cdp__*` 工具前做状态检查
- `playwright-cdp` 报 `Failed to connect`、`Extension not connected`、`socket hang up`

## 不适用场景

- 普通公网静态页面抓取
- 不需要用户 Chrome 登录态的 Playwright 自动化
- 全局 MCP / skill / plugin 清理

## 默认流程

先运行只读检查脚本：

```bash
bash .claude/skills/playwright-cdp-launcher/scripts/check-mcp-state.sh
```

脚本输出四类状态：

- `chrome_process=running|missing`
- `cdp_port=listening|closed`
- `mode=extension|cdp-endpoint|unknown`
- `playwright_cdp_mcp=connected|failed|missing|unknown`

按 `mode` 分叉处理。

### mode=extension

这是当前默认路径，依赖用户日常 Chrome profile 与 Playwright MCP Bridge 扩展。

- 如果 `playwright_cdp_mcp=connected`，直接调用目标 `mcp__playwright-cdp__*` 工具。
- 如果 Bridge / extension 失败，只输出切换到 CDP endpoint 的建议命令，不调用 `start-cdp-chrome.sh`。
- 不要尝试通过启动 9222 Chrome 修复 extension mode；extension mode 不会因此自动切到 `--cdp-endpoint`。

建议命令必须标明需要用户确认后执行：

```bash
claude mcp remove -s user playwright-cdp
claude mcp add -s user playwright-cdp -- /Users/fanghu/.local/share/mcp-runners/node_modules/.bin/playwright-mcp --cdp-endpoint http://127.0.0.1:9222
```

切换后需要重启 Claude Code / MCP 客户端。

### mode=cdp-endpoint

只有在当前配置已经是 CDP endpoint 时，才允许启动本机 Chrome CDP：

```bash
bash .claude/skills/playwright-cdp-launcher/scripts/start-cdp-chrome.sh
```

- 如果 `cdp_port=listening`，不要重复启动。
- 默认 profile 仍指向本机日常 Chrome profile：`~/Library/Application Support/Google/Chrome`，但 Chrome 136+ 不再允许默认数据目录开启 CDP remote debugging；脚本会返回 `default_profile_cdp_blocked`，不会盲目启动。
- 如果 `cdp_port=closed` 且日常 Chrome 已经在运行，脚本只输出 `profile_in_use`，要求用户先正常退出 Chrome 后重跑；脚本不会自动杀日常 Chrome。
- 如果 9222 已被其他 profile 占用，脚本输出 `port_in_use_by_different_profile`，要求先关闭已有 CDP Chrome 或换端口。
- 在 macOS 上脚本使用 `open -na "Google Chrome"` 拉起带 `--remote-debugging-port` 的 Chrome。
- 启动成功后再重试目标 `mcp__playwright-cdp__*` 工具。

如果需要可用的 CDP endpoint，应显式使用非默认隔离 profile，并在该 profile 内登录一次：

```bash
PLAYWRIGHT_CDP_PROFILE="$HOME/.chrome-cdp-profile" bash .claude/skills/playwright-cdp-launcher/scripts/start-cdp-chrome.sh
```

## nanobot MCP wrapper

Ava/nanobot 当前默认直接使用 Playwright MCP extension mode：

```json
{
  "command": "/Users/fanghu/.local/share/mcp-runners/node_modules/.bin/playwright-mcp",
  "args": ["--extension", "--browser", "chrome", "--user-data-dir", "/Users/fanghu/Library/Application Support/Google/Chrome"],
  "toolTimeout": 60,
  "enabledTools": ["browser_navigate", "browser_snapshot"]
}
```

不要把 nanobot 配置回 CDP wrapper，除非 extension Bridge 已确认不可用，且用户明确同意切到 CDP endpoint fallback。

历史 wrapper 路径保留如下：

```bash
.claude/skills/playwright-cdp-launcher/scripts/run-playwright-mcp-with-daily-chrome.sh
```

fallback wrapper 行为：

- 先调用 `start-cdp-chrome.sh`，检查目标 profile 是否能以 CDP 模式启动。
- 如果日常 Chrome 已普通启动且未开放 9222，返回 `profile_in_use`，不启动 MCP server。
- 如果当前 Chrome 版本禁止默认日常 profile 开启 CDP，返回 `default_profile_cdp_blocked`，不启动 MCP server。
- 如果 9222 被其他 profile 占用，返回 `port_in_use_by_different_profile`。
- 只有 CDP 可用后才 `exec playwright-mcp --cdp-endpoint http://127.0.0.1:9222`。
- wrapper 会设置 Playwright MCP 的 `NODE_OPTIONS` shim 与 localhost `NO_PROXY`。

## macOS App launcher

也可以从用户 Applications 检查或尝试启动日常 profile CDP：

```text
/Users/fanghu/Applications/Chrome CDP - Daily Profile.app
```

这个 App 只包装 `start-cdp-chrome.sh`：

- 日常 Chrome 未运行时，尝试启动同一个日常 profile 并开启 `127.0.0.1:9222`。
- 日常 Chrome 已普通启动时，弹窗提示先正常退出 Chrome，不会自动杀进程。
- Chrome 136+ 禁止默认日常 profile 开启 CDP 时，弹窗提示改用 extension mode 或隔离 CDP profile。
- 9222 被其他 profile 占用时，弹窗提示先关闭旧 CDP Chrome。
- 运行日志写到 `/tmp/chrome-cdp-daily-profile-app.log`。

### mode=unknown

只输出诊断结果与切换/修复建议，不调用 `start-cdp-chrome.sh`。

`mode=unknown` 表示无法确认 `playwright-cdp` 当前到底是否使用 CDP endpoint。不能假定启动 9222 会修复问题。

## 边界

- 不自动写 `~/.claude.json`
- 不复制用户日常 Chrome profile；Chrome 136+ 下默认日常 profile 不能作为 CDP endpoint
- 不杀日常 Chrome；profile 正在使用时只提示用户退出后重跑
- `check-mcp-state.sh` 只读，不调用任何 MCP 工具
- `start-cdp-chrome.sh` 只在 `mode=cdp-endpoint` 路径使用

## 排障资料

遇到失败时读取：

```bash
sed -n '1,220p' .claude/skills/playwright-cdp-launcher/references/troubleshooting.md
```
