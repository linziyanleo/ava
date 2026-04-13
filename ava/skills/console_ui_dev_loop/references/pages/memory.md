# 记忆管理（Memory）

**路由**: `/memory`
**页面标题**: 记忆管理
**权限**: 任意已登录

## 可操作元素

| 元素 | 类型 | 作用 |
|------|------|------|
| 记忆 Tab | Tab | 切换到记忆文件视图 |
| 日记 Tab | Tab | 切换到日记视图 |
| 全局记忆 按钮 | 筛选/导航 | 查看全局记忆文件 |
| 用户记忆按钮（如 Leo / 主人） | 筛选/导航 | 查看特定用户的个人记忆 |
| Memory 按钮 | 子 Tab | 查看 MEMORY.md 文件 |
| History(N) 按钮 | 子 Tab | 查看 history.jsonl 文件（含条目数，只读） |
| 刷新 按钮 | 按钮 | 重新加载记忆文件 |
| 文件内容编辑区 | 文本编辑器 | 直接编辑记忆 Markdown 文件 |
| 保存 按钮 | 按钮 | 保存编辑后的记忆文件 |

## 检查项

| check_id | 检查内容 | 断言方式 |
|-----------|---------|---------|
| `memory.route` | URL 为 `/memory` | `page.url` |
| `memory.heading` | 标题"记忆管理"可见 | `page_state.headings` |
| `memory.tabs` | 记忆 / 日记 Tab 可见 | `page_state.buttons` |
| `memory.editor` | 文件内容编辑区可见 | `page_state.forms` |
| `memory.save_btn` | 保存按钮存在 | `page_state.buttons` |
| `memory.no_error` | 无错误提示 | `page_state.alerts` 为空 |

## instruction 示例

"检查页面是否显示'记忆管理'标题，记忆和日记两个 Tab 是否可见，是否有文件编辑区和保存按钮"
