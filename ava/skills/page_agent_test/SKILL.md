---
name: page-agent-test
description: 基于 page_agent 的狭义 smoke / exploratory 测试协议。适合显式页面检查或给上层 wrapper 复用，不是 console-ui 开发闭环，也不默认自动修复。当用户明确要求“用 Page Agent 测一下页面”或需要通用 best-effort 页面检查协议时触发。
metadata: {"nanobot":{"emoji":"🔍"}}
---

# Page Agent Test

这是一个基础测试协议，不是当前仓库里的主闭环入口。

- 对 `console-ui` 开发任务，优先使用 `console_ui_dev_loop`
- 这个 skill 只负责页面验证与诊断
- 默认不负责自动修复

## 适用场景

- 对一个或少量页面做 smoke / exploratory 检查
- 需要一个可被 wrapper 继承的 page-agent 测试协议
- 用户明确要求用 Page Agent 评估某个网页

## 不适用场景

- 当前仓库里的 console-ui 开发闭环
- 想把它当成 Playwright / Cypress 的稳定替代
- 需要多轮 coding -> regression -> retry orchestration

## 默认协议

1. 明确测试目标
   - 页面路径
   - 预期路由
   - 关键 checkpoint

2. 执行 deterministic-first 检查
   - `page_agent(execute, response_format="json")`
   - `page_agent(get_page_info, response_format="json")`
   - 先看 URL / Page State / DOM 事实

3. 仅在必要时升级视觉检查
   - `page_agent(screenshot, response_format="json")`
   - `vision(...)`

4. 输出报告
   - 每个 checkpoint 的状态
   - 失败证据
   - 是否建议交给上层 wrapper 继续修复

## 断言原则

- 先 URL / heading / alerts / forms / buttons
- 只有颜色、布局、图片、Canvas、SVG 等 DOM 难以表达的问题才升级到 `vision`
- 不要把 `vision` 当默认主判据

## 边界

- pass/fail 仍然是 best-effort，不等于 CI 级验收
- 默认不调用 `claude_code`
- 如需修复循环，应由上层 wrapper 明确编排
