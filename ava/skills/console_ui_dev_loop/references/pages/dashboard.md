# Dashboard（控制台首页）

**路由**: `/`
**页面标题**: 控制台
**权限**: 任意已登录

## 可操作元素

| 元素 | 类型 | 作用 |
|------|------|------|
| Config 快捷卡片 | 按钮/链接 | 跳转到配置管理页面 |
| Memory 快捷卡片 | 按钮/链接 | 跳转到记忆管理页面 |
| Persona 快捷卡片 | 按钮/链接 | 跳转到人设配置页面 |
| Chat 快捷卡片 | 按钮/链接 | 跳转到聊天会话页面 |

## 状态显示

- Gateway online 状态指示
- Quick Info 信息摘要区域

## 检查项

| check_id | 检查内容 | 断言方式 |
|-----------|---------|---------|
| `dashboard.route` | URL 为 `/` | `page.url` |
| `dashboard.heading` | 标题"控制台"可见 | `page_state.headings` |
| `dashboard.quick_cards` | 4 个快捷卡片存在（Config / Memory / Persona / Chat） | `page_state.buttons` |
| `dashboard.gateway_status` | Gateway 状态指示可见 | `page_state` 文本 |
| `dashboard.no_error` | 无错误提示 | `page_state.alerts` 为空 |

## instruction 示例

"检查页面是否显示'控制台'标题，是否有 Config、Memory、Persona、Chat 四个快捷卡片，以及 Gateway 在线状态指示"
