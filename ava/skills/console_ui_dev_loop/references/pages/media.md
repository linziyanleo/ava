# 生成图片（Media）

**路由**: `/media`
**页面标题**: 生成图片
**副标题**: AI 图片生成记录
**权限**: 任意已登录

## 可操作元素

| 元素 | 类型 | 作用 |
|------|------|------|
| 刷新 按钮 | 按钮 | 重新加载图片记录列表 |
| 搜索输入框 | 输入框 | 按 prompt 关键词搜索图片记录 |
| 图片记录列表项 | 列表 | 展示每张生成图片的时间和 prompt |
| 删除 按钮（每行） | 按钮 | 删除对应图片记录 |
| 首页 / 末页 按钮 | 分页 | 跳转到第一页或最后一页 |
| 页码按钮 | 分页 | 跳转到指定页 |
| 下一页 按钮 | 分页 | 翻到下一页 |
| 跳至 输入框 + 确定 按钮 | 分页 | 跳转到指定页码 |

## 分页规格

每页 18 张（6列x3行）

## 检查项

| check_id | 检查内容 | 断言方式 |
|-----------|---------|---------|
| `media.route` | URL 为 `/media` | `page.url` |
| `media.heading` | 标题"生成图片"可见 | `page_state.headings` |
| `media.search` | 搜索输入框存在 | `page_state.forms` |
| `media.refresh_btn` | 刷新按钮存在 | `page_state.buttons` |
| `media.gallery_or_empty` | 图片 gallery 或空状态可见 | `page_state` 文本 |
| `media.no_error` | 无错误提示 | `page_state.alerts` 为空 |

## instruction 示例

"检查页面是否显示'生成图片'标题和搜索框，是否有图片记录列表或空状态提示，刷新按钮是否存在"
