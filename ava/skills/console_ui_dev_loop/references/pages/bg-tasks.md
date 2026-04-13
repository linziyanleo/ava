# 后台任务（Background Tasks）

**路由**: `/bg-tasks`
**页面标题**: 后台任务
**权限**: 非 viewer（admin / editor / mock_tester）

## 可操作元素

| 元素 | 类型 | 作用 |
|------|------|------|
| Live 状态指示器 | 状态标签 | 显示实时连接状态 |
| 刷新 按钮 | 按钮 | 手动刷新任务列表 |
| 查看历史任务 按钮 | 按钮 | 切换到历史任务视图 |
| 历史任务 按钮 | 按钮 | 同上（另一入口） |
| 任务卡片（有任务时） | 卡片 | 展示任务状态、输入、输出 |

## 空状态显示

- "暂无活跃任务"提示
- 说明文字："通过 Claude Code 工具提交的异步编程任务将显示在这里"

## 检查项

| check_id | 检查内容 | 断言方式 |
|-----------|---------|---------|
| `bg-tasks.route` | URL 为 `/bg-tasks` | `page.url` |
| `bg-tasks.heading` | 标题"后台任务"可见 | `page_state.headings` |
| `bg-tasks.refresh_btn` | 刷新按钮存在 | `page_state.buttons` |
| `bg-tasks.empty_or_list` | 显示空状态提示或任务卡片列表 | `page_state` 文本 |
| `bg-tasks.no_error` | 无错误提示 | `page_state.alerts` 为空 |

## instruction 示例

"检查页面是否显示'后台任务'标题，刷新按钮是否存在，是否显示'暂无活跃任务'空状态或任务卡片"
