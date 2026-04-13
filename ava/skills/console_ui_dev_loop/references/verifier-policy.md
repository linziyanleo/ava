# Verifier Policy

## 总原则

默认 `deterministic-first`。

优先用 `page_agent(response_format="json")` 的结构化结果做判断：

- `page.url`
- `page.title`
- `result.data`
- `page_state.headings`
- `page_state.alerts`
- `page_state.forms`
- `page_state.buttons`

只有这些事实不够时，才升级到 `screenshot + vision`。

## 断言梯度

### 1. 路由与页面身份

优先检查：

- URL 是否进入目标路径
- 标题 / heading 是否符合预期

### 2. 表单与错误提示

优先检查：

- `page_state.forms`
- `page_state.alerts`
- 按钮文本是否存在

### 3. 视觉升级

以下场景才需要 `vision`：

- 颜色、样式、布局错乱
- DOM 无法表达的图片、Canvas、SVG 内容
- OCR 识别截图里的文字

## Failure Taxonomy

建议统一用以下分类：

- `ROUTE_MISMATCH`
- `HEADING_MISSING`
- `ALERT_VISIBLE`
- `PRIMARY_ACTION_MISSING`
- `EMPTY_STATE_UNEXPECTED`
- `VISUAL_LAYOUT_REGRESSION`
- `AUTH_REQUIRED`
- `TOOLING_FAILURE`

## Checkpoint 动作

每个 `verifier_result` 都要附带 checklist 动作：

```yaml
checklist_action:
  action: "keep | add_followup | deprecate"
  reason: ""
  new_checks: []
```

规则：

- `keep`
  - 原 checkpoint 仍然有效
- `add_followup`
  - 当前失败需要更细粒度拆分
- `deprecate`
  - 当前 checkpoint 已不再适用

## 证据最小集

除纯视觉问题外，尽量不要只给截图。

优先返回：

- `session_id`
- `page.url`
- `page_state`
- 截图路径（如有）
- 简短 `coder_hint`
