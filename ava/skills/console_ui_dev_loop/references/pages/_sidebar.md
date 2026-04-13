# Sidebar（全局导航栏）

所有页面共享同一左侧 Sidebar。

## 导航项

| 导航项 | 路由 | 说明 |
|--------|------|------|
| 控制台 | `/` | Dashboard 首页 |
| 配置 | `/config` | 配置管理 |
| 定时任务 | `/tasks` | Cron 任务列表 |
| 后台任务 | `/bg-tasks` | Claude Code 后台任务 |
| 记忆 | `/memory` | 记忆管理 |
| 生成图片 | `/media` | 图片 Gallery |
| 人设 | `/persona` | Agent 人设配置文件 |
| 技能和工具 | `/skills` | 技能 & 工具管理 |
| 聊天 | `/chat` | 会话记录浏览 |
| Token 统计 | `/tokens` | Token 用量统计 |

## Footer 元素

- 当前用户名 + 角色
- 主题切换按钮（深色/浅色）
- 退出登录按钮

## 通用检查项

| check_id 模式 | 检查内容 | 断言方式 |
|---------------|---------|---------|
| `{page}.sidebar.nav` | Sidebar 导航项完整可见 | `page_state.buttons` |
| `{page}.sidebar.user` | 用户名和角色显示正确 | `page_state` 文本 |
| `{page}.sidebar.logout` | 退出登录按钮存在 | `page_state.buttons` |
