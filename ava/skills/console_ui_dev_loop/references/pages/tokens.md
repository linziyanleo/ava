# Token 统计（Tokens）

**路由**: `/tokens`
**页面标题**: Token 统计
**权限**: 任意已登录

## 可操作元素

| 元素 | 类型 | 作用 |
|------|------|------|
| 明细 Tab | Tab | 切换到逐条调用明细视图 |
| 聚合 Tab | Tab | 切换到聚合统计视图 |
| 刷新 按钮 | 按钮 | 刷新统计数据 |
| 全部 按钮 | 过滤器 | 显示全部类型调用 |
| 终端/代码 按钮 | 过滤器 | 过滤终端/代码类调用 |
| AI 按钮 | 过滤器 | 过滤 AI 调用 |
| 网络 按钮 | 过滤器 | 过滤网络请求 |
| 高消耗 按钮 | 过滤器 | 过滤 token 高消耗 |
| 语音 按钮 | 过滤器 | 过滤语音调用 |
| 视觉 按钮 | 过滤器 | 过滤视觉调用 |
| 调用记录表格 | 数据表格 | 逐条展示 LLM 调用记录（时间/模型/tokens/费用等） |

## 汇总指标（页面顶部）

- 总 Token 数
- LLM 调用次数
- Prompt Tokens
- Completion Tokens

## 检查项

| check_id | 检查内容 | 断言方式 |
|-----------|---------|---------|
| `tokens.route` | URL 为 `/tokens` | `page.url` |
| `tokens.heading` | 标题"Token 统计"可见 | `page_state.headings` |
| `tokens.tabs` | 明细 / 聚合 Tab 可切换 | `page_state.buttons` |
| `tokens.summary` | 汇总指标可见（总 Token 数 / LLM 调用次数） | `page_state` 文本 |
| `tokens.filter_btns` | 过滤按钮存在（全部 + 至少 2 个分类按钮） | `page_state.buttons` |
| `tokens.no_error` | 无错误提示 | `page_state.alerts` 为空 |

## instruction 示例

"检查页面是否显示'Token 统计'标题，明细和聚合两个 Tab 是否可见，汇总指标区域是否显示总 Token 数和 LLM 调用次数，过滤按钮是否存在"
