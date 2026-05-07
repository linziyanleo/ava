# nanobot Skills

This directory contains built-in skills that extend nanobot's capabilities.

## Skill Format

Each skill is a directory containing a `SKILL.md` file with:
- YAML frontmatter (name, description, metadata)
- Markdown instructions for the agent

## Attribution

These skills are adapted from [OpenClaw](https://github.com/openclaw/openclaw)'s skill system.
The skill format and metadata structure follow OpenClaw's conventions to maintain compatibility.

## Available Skills

| Skill | Description |
|-------|-------------|
| `console_ui_dev_loop` | Console UI 前端开发与回归闭环 |
| `cron` | Schedule reminders and recurring tasks |
| `diary` | 每日日记生成 |
| `memory` | Dream 全局记忆 + person memory 边界说明 |
| `page_agent_test` | 基于 page_agent 的任务级页面探索 / smoke 协议 |
| `playwright_daily_browser` | 使用 Playwright MCP extension mode 对日常 Chrome 做精确操作、截图和验收 |
| `tmux` | Remote-control tmux sessions |
