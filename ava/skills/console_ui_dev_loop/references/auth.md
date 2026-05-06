# 认证流程

## 测试账号

系统启动时自动创建两个本地账号，密码保存在 console 数据目录下：

| 账号 | 用户名 | 角色 | 默认密码 | 密码文件 |
|------|--------|------|----------|----------|
| 测试员 | `mock_tester` | `mock_tester` | （随机生成） | `<console_dir>/local-secrets/mock_tester_password` |

测试员密码为首次启动时随机生成（`secrets.token_urlsafe(24)`）。后续启动自动校验并同步。

## 登录操作

1. 如果需要本 skill 的 Page State/session 复用能力，使用 `page_agent` 的 `playwright` backend 执行 `page_agent(execute)` 导航到 `/login`
2. 如果当前 `page_agent` 是 `official_mcp` backend，改用 `playwright_daily_browser` 的 navigate/snapshot/type/click 流程完成登录和验收
3. instruction 示例："在用户名输入框填写 `mock_tester`，密码输入框填写 `<password>`，点击 Sign In 按钮"
4. 验证登录成功：URL 跳转到 `/`，Sidebar 显示用户名和角色

## Session 复用

- `page_agent` 的 `playwright` backend：登录成功后记录 `session_id`，后续页面测试复用该 session
- `official_mcp` / `playwright_daily_browser`：复用日常 Chrome profile 和当前 tab 状态，不依赖 `page_agent` local `session_id`
- 如需切换账号（如测试 admin-only 页面），先明确当前后端；local runner 关闭 session，日常 Chrome 则需要手动切换账号或使用独立 profile

## 权限矩阵

- `mock_tester` 角色等同 `editor`，可访问大多数页面
- `users` 页面仅 `admin` 可访问 — mock_tester 测试时应标记 `skipped(AUTH_REQUIRED)`
- `browser` 页面仅 `admin/editor/viewer` 可访问 — mock_tester 无权限，同理 skip
- 详细权限见 `page-registry.md` 的权限列
