# Testing Task

## Round 0 目标

在任何 coding 前先把需求转成一个可执行的测试任务：

```yaml
testing_task:
  summary: ""
  intent_understanding:
    target_outcomes: []
    primary_risks: []
    excluded_scope: []
  master_checklist:
    version: 1
    items: []
```

## Checklist 设计规则

### 1. 覆盖来源

`master_checklist` 至少覆盖三类内容：

- 用户显式目标
- `changed_files` 影响到的页面或关键交互
- 最小基础 smoke

### 2. 单个 checkpoint 的最小字段

```yaml
- check_id: "config.route.heading"
  title: "配置页路由与主标题可见"
  page: "/config"
  source: "explicit | file_map | inferred"
  assertion_mode: "deterministic | visual | hybrid"
  priority: "p0 | p1 | p2"
  status: "pending | passed | failed | skipped | deprecated"
  rationale: "为何需要这个检查"
  evidence_required:
    - "url"
    - "page_state.headings"
```

### 3. `check_id` 规则

- 使用稳定、可读、可比较的点号命名
- 推荐格式：`<page>.<subject>.<assertion>`
- 一旦创建，不允许在后续轮次重命名

### 4. `assertion_mode`

- `deterministic`
  - 只依赖 URL / Page State / DOM 事实
- `visual`
  - 必须依赖截图 + `vision`
- `hybrid`
  - 先跑 deterministic，再用视觉补强

不要把 `vision` 单独建成另一份 checklist。

## Checklist 生命周期

允许在后续轮次做 Reverse Sync：

- `added`
  - 发现新的风险边界
  - 某个失败需要拆成更细的 follow-up checkpoint
- `deprecated`
  - 用户明确排除
  - 验证发现该项不再适用
- `unchanged`
  - 其他未变化项

任何增删都必须在 `checklist_delta` 写清理由。

## 基础 Smoke 建议

除非用户明确排除，通常都应有这些 baseline checkpoint：

- 入口路由可达
- 主标题或页面识别元素可见
- 关键按钮 / 空状态 / 错误提示正常
- 导航结构未整体损坏

## Final Pass 规则

中间轮次可以只跑受影响项。

但准备返回最终 `pass` 前，必须：

- 执行完整 `master_checklist`
- 确认没有 `failed_checks`
- 确认没有未解释的 `deprecated_checks`
