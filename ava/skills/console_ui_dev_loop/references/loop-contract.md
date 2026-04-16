# Loop Contract

## Phase Model

`console_ui_dev_loop` 的单次运行按以下阶段推进：

1. `round0_planning`
2. `coding` — 异步提交，输出 `round_status`（Turn A 结束）
3. `coding_result` — 收到 `[Background Task Completed]`，解析结果（Turn B 开始）
4. `regression` — 紧接 coding_result 执行，不拆 turn
5. `final_verification`

`round0_planning` 必须先于任何 coding 行为发生。

`coding` 和 `coding_result` 分属不同 turn，通过 `round_status.task_id` 关联。

## Round Output

### coding 阶段（Turn A）使用精简格式

```yaml
round_status:
  round: 1
  phase: coding
  action: submitted
  task_id: "abc123"
  coding_goal: "修复 config 页面标题缺失"
  pending_regression: "impacted_subset"
```

这段输出是 Turn B 的**状态锚点**——continuation 到达时靠它恢复上下文。

### regression / final_verification 阶段使用完整骨架

```yaml
round_output:
  round: 1
  phase: "coding_result | regression | final_verification"
  coding_summary: ""
  regression_scope:
    check_ids: []
    pages: []
    source: "impacted_subset | baseline_smoke | full_checklist"
  checklist_snapshot:
    version: 1
    completed_checks: []
    pending_checks: []
    failed_checks: []
    deprecated_checks: []
  checklist_delta:
    added: []
    deprecated: []
    unchanged: []
  regression_report: ""
  verdict: "pass | retry | escalate"
  feedback_for_coder:
    failed_pages: []
    failed_checks: []
    failure_taxonomy: []
    evidence_paths: []
    next_hint: ""
```

## Stop Policy

默认停止条件：

- `same_failure_twice`
- `non_retryable_failure`
- `manual_auth_required`
- `max_rounds_reached`

其中 `same_failure_twice` 必须按 `check_id + failure_taxonomy` 判定，不要只比较自然语言描述。

## Retry Policy

默认：`rerun_policy=full_before_pass`

- 中间轮次：只跑 `impacted_subset + baseline_smoke`
- 最终放行前：强制 `full_checklist`

严格模式：`full_each_round`

- 每轮都执行 `full_checklist`
- 只有用户明确要求高成本严格回归时才启用

## Verdict Rules

- `pass`
  - 当前轮已经执行 `full_checklist`
  - 无 `failed_checks`
- `retry`
  - 仍有可重试失败
- `escalate`
  - 失败不可重试
  - 或问题超出当前页面/console-ui 范围

## Coder Feedback Contract

回灌给 coder 的内容必须压缩，不要原样粘贴大段日志：

- `failed_checks`
- `failure_taxonomy`
- 证据路径
- 最小下一步提示

目标是让 coder 能直接进入下一轮修复，而不是重新分析整个页面。
