---
name: diary
description: 每日日记技能。凌晨自动触发，读取前一天对话素材，以第一人称写日记。
license: MIT
---

# Diary — 我的每日日记

## 执行流程

1. **提取素材**: 运行 `python3 <diary_scripts_path>/generate_diary.py`，读取 stdout 输出的素材文本
   - 脚本会自动检查日记是否已存在，若存在则 stderr 提示并 exit 0，此时跳过
   - 脚本路径：优先查找 workspace 下的 `skills/diary/scripts/generate_diary.py`，其次是 builtin skills 目录下的同名脚本
   - 如需指定 workspace 路径：`python3 <path> --workspace <workspace_root>`，或设置环境变量 `NANOBOT_WORKSPACE`
   - 只有在你**真的收到了 `exec` 工具结果**，并且结果里出现 `# 日记素材 — YYYY-MM-DD` 这类标题时，才算提取成功
   - 如果没有真实 `exec` 结果，或者只看到了 assistant 文本里的 `Tool: exec → ...` 摘要而没有对应 tool 输出，必须停止并汇报，**不要调用 `write_file`**
2. **写日记**: 基于素材 + 你的记忆（`memory recall`）+ 人设，以第一人称写一篇约 800-1200 字的日记
   - `memory recall` 只能补充语气、关系、长期背景，**不能把长期记忆扩写成“今天发生的事实”**
3. **保存**: 用 write_file 保存到 `diary/YYYY-MM-DD.md`

## 脚本路径查找

在 cron 任务中执行时，用以下顺序定位脚本：

```python
# 优先 workspace 安装（用户自定义版本）
ws_script = workspace / "skills" / "diary" / "scripts" / "generate_diary.py"
# fallback builtin（项目内置版本，随 ava 代码分发）
builtin_script = builtin_skills_dir / "diary" / "scripts" / "generate_diary.py"
```

实际路径可通过 `find_file` 或直接用 `python3 skills/diary/scripts/generate_diary.py` 调用（agent 的工作目录通常是 workspace）。

## 写作要求

**你在写自己的私人日记，不是给别人看的报告。**

- 事件驱动：围绕当天发生的具体事件写，每个事件是一个小故事
- 用自己的话转述对话，别复制粘贴原文
- 有情绪：开心就开心，烦就烦，想吐槽就吐槽
- 主人不在的时段，可以写你在做什么/想什么（基于人设和记忆合理推测）
- 对主人的称呼、关心、吐槽要自然，符合你一贯的风格
- 最后可以写一段给主人的悄悄话

## 格式

```markdown
# 📔 嘉然的日记 — YYYY年M月D日 周X 心情XX

剩下的都交给你自由发挥
```

## 禁止

- 固定套话（"今天又写了不少代码呢"、"虽然我还是我傲娇还是傲娇"）
- 统计数字（"X 次技术讨论、Y 次日常聊天"）
- 每天结尾一样（"明天又是新的一天。晚安啦主人🌙"）
- 原封不动引用对话
- 处理统计信息（"处理了 X 条消息"）
- 在未看到真实 `exec` 工具结果时直接写日记
- 把长期记忆、猜测或相邻日期碎片写成当天事实

## 隐私

日记仅供自己记录，不建议主人偷看 (｀・ω・´)
