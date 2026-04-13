# Loop Contract

## Phase Model

`console_ui_dev_loop` 的单次运行按以下阶段推进：

1. `round0_planning`
2. `coding`
3. `regression`
4. `final_verification`

`round0_planning` 必须先于任何 coding 行为发生。

## Round Output

每轮输出统一使用以下骨架：

```yaml
round_output:
  round: 1
  phase: "round0_planning | coding | regression | final_verification"
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
