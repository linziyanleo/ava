# playwright-cdp Troubleshooting

本文件只沉淀诊断与修复路径。不要在未获用户确认时修改 `~/.claude.json` 或删除全局 MCP / skill / plugin。

## 1. npx 慢或缓存损坏

症状：
- `plugin:playwright:playwright` 偶发 `Failed to connect`
- `claude mcp list` 首次检查耗时很长，第二次状态变化

诊断：

```bash
claude mcp list
```

修复：
- 阶段二清理前重新 live check。
- 对 `plugin:playwright:playwright`，优先禁用整个 plugin，而不是手改 plugin cache。

## 2. 装错扩展

症状：
- 日常 Chrome 已打开，但 extension mode 仍报 `Extension not connected`
- MCP 进程正常，页面工具不可用

诊断：
- 在 Chrome 扩展页确认 Playwright MCP Bridge 已启用。
- 确认使用的是 Bridge 扩展，不是普通 CRX 或无关 Playwright 插件。

修复：
- 启用正确的 Bridge 扩展。
- 如果扩展路径持续不稳定，输出切换到 CDP endpoint 的建议命令，由用户确认执行。

## 3. 缺 `PLAYWRIGHT_MCP_EXTENSION_TOKEN`

症状：
- Bridge 扩展存在，但 MCP 无法完成握手
- 日志里出现 token / authorization 相关失败

诊断：

```bash
claude mcp list
```

修复：
- 检查当前 user-scope MCP 注册是否包含 extension mode 所需环境。
- 不在 skill 中打印 token 或完整配置。

## 4. 缺 `--browser` 或 `--user-data-dir`

症状：
- extension mode 启动了隔离浏览器或拿不到日常登录态
- 登录态页面变成未登录页

诊断：

```bash
bash .claude/skills/playwright-cdp-launcher/scripts/check-mcp-state.sh
```

修复：
- extension mode 应使用 Chrome 与用户日常 profile。
- CDP endpoint mode 默认使用本机日常 profile：`~/Library/Application Support/Google/Chrome`，以复用现有登录态。
- 如果日常 Chrome 已经在运行但没有开启 9222，必须先正常退出 Chrome，再用 `start-cdp-chrome.sh` 重新启动；不要并发打开同一个 profile。

## 5. `/cdp/<uuid>` socket hang up

症状：
- extension mode 偶发 `socket hang up`
- 重试仍不能稳定恢复

诊断：
- 先运行 `check-mcp-state.sh`，确认当前 mode。
- 如果 `mode=extension`，不要调用 `start-cdp-chrome.sh`。

修复：
- 只输出 CDP endpoint 切换建议命令，由用户确认后执行。
- 切换后重启 Claude Code / MCP 客户端，再在 CDP profile 登录目标站点。

## 6. macOS Chrome 短暂启动后 9222 消失

症状：
- `start-cdp-chrome.sh` 一度看到 `DevTools listening`，但随后 `lsof` / `curl` 访问不到 9222
- `~/.chrome-cdp-profile` 留下 stale `Singleton*` 文件

诊断：

```bash
curl -sS --max-time 2 http://127.0.0.1:9222/json/version
```

修复：
- 在 macOS 上用 `open -na "Google Chrome" --args ... about:blank` 启动独立实例。
- 如果使用日常 profile，先正常退出日常 Chrome，再启动；脚本不会自动杀日常 Chrome。
- 如需隔离 profile，显式设置 `PLAYWRIGHT_CDP_PROFILE="$HOME/.chrome-cdp-profile"`。

## 6.5. `profile_in_use`

症状：
- `start-cdp-chrome.sh` 输出 `action=failed reason=profile_in_use`
- `profile=~/Library/Application Support/Google/Chrome`

原因：
- 日常 Chrome profile 已经被正在运行的 Chrome 使用。
- Chrome 只有在启动时带上 `--remote-debugging-port` 才能开放 CDP；无法给已经正常启动的 Chrome 追加这个端口。

修复：
- 保存工作，正常退出 Google Chrome。
- 重新运行 `start-cdp-chrome.sh`，确认当前 Chrome 是否允许同一个日常 profile 以 CDP 模式启动。
- 如果后续返回 `default_profile_cdp_blocked`，说明当前 Chrome 已禁止默认 profile CDP；改用 extension mode 或隔离 CDP profile。
- 如果是 nanobot 自动连接 MCP 触发的错误，说明 wrapper 正确保护了日常浏览器；不要让 wrapper 自动杀 Chrome。

## 6.55. `default_profile_cdp_blocked`

症状：
- `start-cdp-chrome.sh` 输出 `action=failed reason=default_profile_cdp_blocked`
- 命令行里能看到 Chrome 带了 `--remote-debugging-port=9222`，但 `curl http://127.0.0.1:9222/json/version` 仍失败

原因：
- Chrome 136+ 不再接受默认 Chrome data directory 的 `--remote-debugging-port` / `--remote-debugging-pipe`。
- 这是 Chrome 的安全边界，用来避免 CDP 直接读取默认 profile 中的 cookies 和登录数据。

修复：
- 如果必须使用日常 profile 登录态，走 extension mode / Bridge 路径，而不是 CDP endpoint。
- 如果必须使用 CDP endpoint，设置非默认 profile，例如 `PLAYWRIGHT_CDP_PROFILE="$HOME/.chrome-cdp-profile"`，并在该 profile 内登录一次。
- 不要复制正在使用的日常 profile，也不要把默认 profile 当作可长期 CDP endpoint。

## 6.6. `port_in_use_by_different_profile`

症状：
- `start-cdp-chrome.sh` 输出 `action=failed reason=port_in_use_by_different_profile`

原因：
- 9222 已经被另一个 Chrome profile 监听，例如旧的 `~/.chrome-cdp-profile`。

修复：
- 关闭旧的 CDP Chrome 窗口，或改用另一个 `PLAYWRIGHT_CDP_PORT` 并同步更新 MCP endpoint。

## 7. Node 被 Proxifier 拦截导致 CDP 超时

症状：
- `curl http://127.0.0.1:9222/json/version` 成功
- Node `http.get` / Playwright MCP 访问同一地址超时或 `socket hang up`
- Proxifier active profile 里有应用规则把 `node` / `bun` 代理到 SOCKS

诊断：

```bash
node -e "require('net').createConnection({host:'127.0.0.1',port:9222},()=>console.log('connected')).setTimeout(2000,()=>console.log('timeout'))"
```

修复：
- 给 Proxifier active profile 增加排在前面的 `Localhost Direct` 规则：`127.0.0.1;localhost;::1`。
- 修改前备份 `.ppx` profile；修改后用 Proxifier 打开该 profile 让规则生效。

## 8. `Browser.setDownloadBehavior` 不支持

症状：
- Playwright MCP 已连上 CDP WebSocket
- `browser_navigate` 返回 `Protocol error (Browser.setDownloadBehavior): Browser context management is not supported`

诊断：
- 用 Playwright 直接调用 `chromium.connectOverCDP(endpoint, { noDefaults: true })`；如果成功，说明是 Playwright MCP CDP attach 默认参数问题。

修复：
- 对 Playwright MCP stdio server 增加 `NODE_OPTIONS=--require .../playwright-mcp-cdp-no-defaults.cjs`。
- 这个 shim 只在加载 `playwright-core/lib/coreBundle.js` 时给 MCP 的 CDP attach 补 `noDefaults: true`，不手改 `node_modules`。

## 9. nanobot 自动启动 MCP

目标：
- nanobot 连接 MCP 时自动调起带 CDP 的日常 Chrome profile。
- 不影响已经普通启动的 Chrome。

配置：
- MCP `command` 指向 `run-playwright-mcp-with-daily-chrome.sh`。
- MCP `args` 为空；wrapper 默认使用 `--cdp-endpoint http://127.0.0.1:9222`。

预期失败：
- 日常 Chrome 已运行但未带 CDP：wrapper 返回 `profile_in_use`，不启动 MCP。
- 9222 被其他 profile 占用：wrapper 返回 `port_in_use_by_different_profile`。

## 10. 从 Applications 启动

入口：
- `/Users/fanghu/Applications/Chrome CDP - Daily Profile.app`

行为：
- App 包装 `start-cdp-chrome.sh`。
- 成功时用通知提示 CDP 已监听。
- `profile_in_use` 时弹窗提示先退出 Chrome。
- `default_profile_cdp_blocked` 时弹窗提示 Chrome 136+ 默认 profile 不能作为 CDP endpoint。
- 不自动关闭或重启用户的日常 Chrome。

诊断：

```bash
CHROME_CDP_APP_NO_UI=1 "/Users/fanghu/Applications/Chrome CDP - Daily Profile.app/Contents/MacOS/ChromeCDPDailyProfile"
```
