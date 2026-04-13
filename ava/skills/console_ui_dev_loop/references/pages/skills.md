# 技能 & 工具（Skills）

**路由**: `/skills`
**页面标题**: 技能 & 工具
**权限**: 非 viewer（admin / editor / mock_tester）

## 可操作元素

| 元素 | 类型 | 作用 |
|------|------|------|
| 保存 按钮 | 按钮 | 保存技能启用/禁用状态 |
| 添加技能 按钮 | 按钮 | 添加新技能 |
| 内置工具 区块 | 展示区 | 显示内置工具列表 |
| 自定义技能(N) 区块 | 展示区 | 显示本地自定义技能 |
| .agents 技能(N) 区块 | 展示区 | 显示 .agents 目录技能 |
| 技能卡片 "点击启用"/"点击禁用" | 切换按钮 | 启用或禁用单个技能 |

## 技能卡片包含信息

- 技能名称
- 来源标签（如 via git）
- 详细描述
- 启用/禁用切换按钮

## 检查项

| check_id | 检查内容 | 断言方式 |
|-----------|---------|---------|
| `skills.route` | URL 为 `/skills` | `page.url` |
| `skills.heading` | 标题"技能 & 工具"可见 | `page_state.headings` |
| `skills.save_btn` | 保存按钮存在 | `page_state.buttons` |
| `skills.add_btn` | 添加技能按钮存在 | `page_state.buttons` |
| `skills.sections` | 至少一个技能区块可见（自定义技能 / .agents 技能） | `page_state.headings` |
| `skills.no_error` | 无错误提示 | `page_state.alerts` 为空 |

## instruction 示例

"检查页面是否显示'技能 & 工具'标题，保存和添加技能按钮是否存在，是否有技能卡片列表"
