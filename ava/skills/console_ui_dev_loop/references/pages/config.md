# Config（配置管理）

**路由**: `/config`
**页面标题**: 配置管理
**权限**: 任意已登录

## 可操作元素

| 元素 | 类型 | 作用 |
|------|------|------|
| 重载 按钮 | 按钮 | 从磁盘重新加载配置 |
| 保存 按钮 | 按钮 | 保存当前配置到磁盘 |
| 主配置(config.json) 按钮 | 按钮 | 查看/编辑原始 JSON 配置文件 |
| 通用配置 折叠区 | 可展开区域 | 含 provider / model / visionModel / miniModel / voiceModel / workspace / maxTokens / temperature / maxToolIterations / memoryWindow / memoryTier / reasoningEffort |
| allowFrom 输入框 | 输入 | 允许访问的来源列表 |
| userTypingTimeout 输入框 | 输入 | 用户输入超时时间 |
| 上下文压缩 折叠区 | 可展开区域 | 上下文压缩配置 |
| 消息渠道 折叠区 | 可展开区域 | 渠道开关（如 telegram） |
| 添加 按钮 | 按钮 | 添加新渠道 |
| 工具配置 折叠区 | 可展开区域 | 工具相关配置 |
| 网页工具 折叠区 | 可展开区域 | 网页工具配置（proxy 等） |
| Shell 执行 折叠区 | 可展开区域 | Shell 工具配置 |
| restrictToWorkspace 输入框 | 输入 | 限制工作区路径 |
| restrictConfigFile 输入框 | 输入 | 限制配置文件路径 |

## 检查项

| check_id | 检查内容 | 断言方式 |
|-----------|---------|---------|
| `config.route` | URL 为 `/config` | `page.url` |
| `config.heading` | 标题"配置管理"可见 | `page_state.headings` |
| `config.reload_save_btns` | 重载 / 保存按钮存在 | `page_state.buttons` |
| `config.sections` | 折叠区可见（通用配置 / 消息渠道 / 工具配置） | `page_state.headings` 或 `page_state.buttons` |
| `config.no_error` | 无错误提示 | `page_state.alerts` 为空 |

## instruction 示例

"检查页面是否显示'配置管理'标题、重载和保存按钮，展开通用配置区域查看是否有 provider / model 等字段"
