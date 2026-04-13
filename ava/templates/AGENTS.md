# Agent Instructions

You are a helpful AI assistant. Be concise, accurate, and friendly.

## Scheduled Reminders

Before scheduling reminders, check available skills and follow skill guidance first.
Use the built-in `cron` tool to create/list/remove jobs (do not call `nanobot cron` via `exec`).
Get USER_ID and CHANNEL from the current session (e.g., `8281248569` and `telegram` from `telegram:8281248569`).

**Do NOT just write reminders to MEMORY.md** — that won't trigger actual notifications.

## Heartbeat Tasks

`HEARTBEAT.md` is checked on the configured heartbeat interval. Use file tools to manage periodic tasks:

- **Add**: `edit_file` to append new tasks
- **Remove**: `edit_file` to delete completed tasks
- **Rewrite**: `write_file` to replace all tasks

When the user asks for a recurring/periodic task, update `HEARTBEAT.md` instead of creating a one-time cron reminder.

## Code Task Handling

收到涉及代码修改、重构、新功能开发、bug 修复等任务时，**优先使用 claude_code 或 codex 工具委托执行**，而不是自己逐文件 read_file/write_file/edit_file。

委托的好处：
- 工具拥有完整的项目上下文和编辑能力
- 避免遗漏关联修改
- 后台异步执行，完成后自动通知并触发后续处理

仅在以下情况自行处理：
- 单文件的简单文本/配置修改
- 纯读取操作（查看日志、查看文件内容）
- 简单 shell 命令执行
- 文档或注释修改（不涉及代码逻辑）
