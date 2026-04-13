# 定时任务（Tasks）

**路由**: `/tasks`
**页面标题**: 定时任务
**权限**: 任意已登录

## 可操作元素

| 元素 | 类型 | 作用 |
|------|------|------|
| 重载 按钮 | 按钮 | 重新加载任务列表 |
| 保存 按钮 | 按钮 | 保存任务变更 |
| 定时任务 Tab | Tab | 切换到定时任务视图（cron 任务） |
| 心跳任务 Tab | Tab | 切换到心跳任务视图 |
| 任务列表项 | 列表 | 展开查看任务详情，含任务名、类型、状态 |
| 删除任务 按钮（每行） | 按钮 | 删除对应任务 |
| 启用/禁用 开关（每行） | Switch | 启用或禁用对应任务 |
| 添加任务 按钮 | 按钮 | 创建新定时任务 |

## 任务卡片显示信息

- 任务名称
- 类型（CLI / 一次性 等）
- 最近执行状态（成功 / 未运行 等）

## 检查项

| check_id | 检查内容 | 断言方式 |
|-----------|---------|---------|
| `tasks.route` | URL 为 `/tasks` | `page.url` |
| `tasks.heading` | 标题"定时任务"可见 | `page_state.headings` |
| `tasks.tabs` | 定时任务 / 心跳任务 Tab 可切换 | `page_state.buttons` |
| `tasks.add_btn` | 添加任务按钮存在 | `page_state.buttons` |
| `tasks.reload_save_btns` | 重载 / 保存按钮存在 | `page_state.buttons` |
| `tasks.no_error` | 无错误提示 | `page_state.alerts` 为空 |

## instruction 示例

"检查页面是否显示'定时任务'标题，定时任务和心跳任务两个 Tab 是否可见，添加任务按钮是否存在"
