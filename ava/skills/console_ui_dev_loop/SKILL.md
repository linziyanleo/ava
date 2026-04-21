---
name: console_ui_dev_loop
description: Console-UI 前端开发与回归测试。支持 regression（只测不修，输出报告）和 dev_loop（coding→regression→retry 闭环）两种模式。当用户说"测/回归 console-ui"或"修这个页面并回归直到通过"时触发。
metadata: {"nanobot":{"emoji":"🔁"}}
---

# Console UI Dev Loop

当前仓库中处理 `console-ui` 前端任务的唯一 user-facing skill。

- 通用页面探索（非 console-ui）请用 `page_agent_test`
- 不要把本 skill 扩展成任意前端项目的通用框架

## 模式选择

| 模式 | 触发词 | 行为 |
|------|--------|------|
| `regression` | "测一下 console-ui" / "做 smoke 测试" / "回归检查" | 只测不修，输出结构化报告 |
| `dev_loop` | "修这个页面并回归" / "做完后继续测直到通过" | coding → regression → retry 闭环 |

## 先读（两种模式共享）

每次执行前按需加载：

1. `references/page-registry.md` — 确认页面路由、权限、文件映射
2. `references/auth.md` — 认证流程和测试账号
3. `references/pages/_sidebar.md` — Sidebar 共享检查项
4. `references/pages/{target_page}.md` — 目标页面的元素、检查项、instruction 示例
5. `references/verifier-policy.md` — deterministic-first 断言梯度

### dev_loop 模式额外读

6. `references/loop-contract.md` — round lifecycle、stop policy、coder feedback
7. `references/testing-task.md` — Round 0 意图理解、checklist 生命周期

> 关键原则：只加载当前测试涉及的页面 reference，不要一次全部读入。

## 页面 reference 结构

每个页面的详细知识存放在 `references/pages/{page_key}.md`，包含：

- 路由、标题、权限
- 可操作元素表
- check_id 检查项表
- page_agent instruction 示例

可用页面列表见 `references/page-registry.md`。

---

## Regression 模式

### 1. 确定范围

按 `references/page-registry.md` 的优先级选择：

1. `explicit_pages` — 用户直接指定
2. `changed_files` 映射 — 根据文件映射表推导
3. `baseline_smoke` — `login` → `dashboard` → `config` → `chat` → `tokens`
4. `full_regression` — 全部页面

### 2. 执行认证

按 `references/auth.md` 登录，复用 `session_id`。

### 3. 按页面验证

对每个待测页面：

1. 读取 `references/pages/{page}.md` 获取检查项
2. 读取 `references/pages/_sidebar.md` 获取 Sidebar 共享检查项
3. 使用 `page_agent(execute, response_format="json")` 执行验证
4. 按 `references/verifier-policy.md` 的 deterministic-first 原则判定

### 4. 输出报告

```yaml
regression_report:
  scope: "baseline_smoke | explicit_pages | full_regression"
  total_checks: N
  passed: N
  failed: N
  skipped: N
  verdict: "pass | fail | partial"
  failed_checks:
    - check_id: "..."
      failure_taxonomy: "..."
      coder_hint: "..."
  skipped_checks:
    - check_id: "..."
      reason: "..."
```

---

## Dev Loop 模式

### 异步 Coding 衔接模型

`claude_code(mode="standard")` 或 `codex(mode="standard")` 都是异步调用——提交后立即返回 `task_id`，coding 任务在后台运行。任务完成后系统会自动注入一条 `[Background Task Completed]` 消息并触发 continuation。

这意味着 dev_loop 的每个 coding round 会跨越**两个 turn**：

```
Turn A: 提交 coding → 收到 task_id → 当前 turn 结束，告知用户 coding 已提交
Turn B: 收到 [Background Task Completed] → 解析 coder 结果 → 立即进入 regression
```

#### Turn A（提交 coding）的行为

1. 构造 coder prompt（含 `goal`、`failed_checks`、`failure_taxonomy`、目录范围）
2. 调用 `claude_code(mode="standard")` 或 `codex(mode="standard")`
3. 收到 task_id 后，输出当前 round 的**阶段小结**：

```yaml
round_status:
  round: N
  phase: coding
  action: submitted
  task_id: "xxx"
  coding_goal: "简述本轮 coding 目标"
  pending_regression: "impacted_subset | full_checklist"
```

> 这段小结是给自己下一个 turn 的状态锚点——continuation 到达时，你需要靠它恢复上下文。

#### Turn B（收到 coding 结果）的行为

收到 `[Background Task Completed]` 消息时：

1. **识别来源**：从消息中提取 task_id，与上一轮 `round_status.task_id` 匹配
2. **解析结果**：提取 coder 的变更摘要（`coding_summary`）
3. **立即进入 Regression Round**——不要重复提交 coding，不要重新规划
4. 如果结果是 ERROR，按失败升级规则处理

### 1. Round 0：生成测试任务

按 `references/testing-task.md` 规则：

- 压缩需求意图（`target_outcomes` / `primary_risks` / `excluded_scope`）
- 从 `references/pages/{page}.md` 提取检查项，生成 `master_checklist`
- 为每个 checkpoint 分配稳定 `check_id`
- 如果用户已给了明确验收点，优先纳入

### 2. Coding Round

使用 `claude_code(mode="standard")` 或 `codex(mode="standard")` 异步提交实现或修复。

给 coder 的输入至少包含：`goal`、`changed_files`、`failed_checks`、`failure_taxonomy`、只允许修改的目录范围。

提交后按上述 Turn A 行为输出阶段小结，等待 continuation。

### 3. Regression Round

收到 coding 结果后立即执行：

- 中间轮次：`impacted_subset + baseline_smoke`
- 准备宣告 PASS 前：强制 `full_checklist`

每个 checkpoint 按 `references/verifier-policy.md` 执行。

### 4. Checklist Reverse Sync

执行中允许更新 checklist，但必须带理由：

- `checklist_delta.added` — 新增 checkpoint
- `checklist_delta.deprecated` — 废弃 checkpoint
- `checklist_delta.unchanged` — 未变化项

不要重命名既有 `check_id`。

### 5. 每轮输出

按 `references/loop-contract.md` 的 `round_output` 格式返回：

- `checklist_snapshot`（completed / pending / failed / deprecated）
- `checklist_delta`
- `regression_report`
- `verdict`（pass / retry / escalate）

只有执行过 `full_checklist` 的轮次，才允许返回 `verdict=pass`。

如果 verdict 为 `retry`，直接进入下一轮 Coding Round（Turn A）。

---

## 默认约束

- v1 默认 `coding_tool=claude_code`，调用方式 `claude_code(mode="standard")`（异步）
- `page_agent` 统一使用 `response_format="json"`
- `vision` 只用于 `assertion_mode=visual|hybrid`
- 默认 `rerun_policy=full_before_pass`

## 失败升级

遇到以下情况直接 `escalate`：

- 同一 `check_id + failure_taxonomy` 连续两轮失败
- 登录态 / 权限要求无法自动满足
- 问题属于 tooling/runtime，而不是当前页面实现

## 禁止事项

- 不要把 `vision` 当默认主判据
- 不要每轮默认跑完整 checklist（除非用户要求 `full_each_round`）
- 不要把 console 的 WS 推送事件当成 `page_agent` tool 返回
- 结果优先输出结构化报告，再补简短中文结论
