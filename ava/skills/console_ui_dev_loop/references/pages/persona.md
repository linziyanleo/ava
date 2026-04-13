# 人设（Persona）

**路由**: `/persona`
**页面标题**: 人物设定
**副标题**: 管理 Agent 的核心配置文件
**权限**: 非 viewer（admin / editor / mock_tester）

## 可操作元素

| 元素 | 类型 | 作用 |
|------|------|------|
| 刷新 按钮 | 按钮 | 重新加载所有人设文件 |
| AGENTS.md 按钮 | Tab/导航 | 查看并编辑 AGENTS.md |
| SOUL.md 按钮 | Tab/导航 | 查看并编辑 SOUL.md |
| TOOLS.md 按钮 | Tab/导航 | 查看并编辑 TOOLS.md |
| USER.md 按钮 | Tab/导航 | 查看并编辑 USER.md |
| 文件内容编辑区 | 文本编辑器 | 直接编辑对应的 Markdown 配置文件 |
| 已保存 / 保存 按钮 | 按钮 | 保存编辑后的文件，显示保存状态 |

## 检查项

| check_id | 检查内容 | 断言方式 |
|-----------|---------|---------|
| `persona.route` | URL 为 `/persona` | `page.url` |
| `persona.heading` | 标题"人物设定"可见 | `page_state.headings` |
| `persona.file_tabs` | 文件标签可见（AGENTS / SOUL / TOOLS / USER） | `page_state.buttons` |
| `persona.editor` | 文件内容编辑区可见 | `page_state.forms` |
| `persona.save_btn` | 保存按钮存在 | `page_state.buttons` |
| `persona.no_error` | 无错误提示 | `page_state.alerts` 为空 |

## instruction 示例

"检查页面是否显示'人物设定'标题，AGENTS / SOUL / TOOLS / USER 四个文件标签是否可见，是否有编辑区和保存按钮"
