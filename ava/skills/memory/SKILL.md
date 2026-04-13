---
name: memory
description: Dream-managed global memory plus sidecar person memory with identity resolution.
always: true
---

# Memory

## Architecture

当前仓库的记忆分成两条链路：Dream 管全局文件，`memory` 工具管 person memory。

```
SOUL.md                    # Dream 管理
USER.md                    # Dream 管理
memory/
├── MEMORY.md              # Dream 管理的全局长期记忆
├── history.jsonl          # append-only 全局历史
├── identity_map.yaml      # channel:chat_id -> person
└── persons/
    └── <person>/
        ├── MEMORY.md      # 个人长期记忆
        ├── history.jsonl   # 个人时间线（JSONL 格式，与全局 history.jsonl 结构一致）
        └── sources/       # 渠道级笔记 (<channel>_<id>.md)
```

## Ownership Boundary

- Dream 会读取 `history.jsonl`，并维护 `SOUL.md`、`USER.md`、`memory/MEMORY.md`
- `memory` 工具负责 person 维度的 `MEMORY.md` / `history.jsonl` / `sources/*`
- `CategorizedMemoryStore.on_consolidate()` 会在会话压缩后把归档摘要同步到 person history
- Dream **不会**回写 person memory；person sync 只走 sidecar bridge

加载到 prompt 的边界：

- 全局：`SOUL.md`、`USER.md`、`memory/MEMORY.md`
- 个人：身份解析成功后，附加 `memory/persons/<person>/MEMORY.md`
- 历史：全局 `history.jsonl` 和各 person `history.jsonl` 默认不直接注入，通过检索或 consolidate 使用

## Identity Resolution

`identity_map.yaml` 将 `channel:chat_id` 映射到自然人：

```yaml
persons:
  leo:
    display_name: "Leo / 主人"
    ids:
      - channel: telegram
        id: ["12345678", "87654321"]
      - channel: cli
        id: ["direct"]
```

同一 person 可挂载多渠道、多账号，记忆自动聚合。

## memory Tool

优先使用 `memory` 工具操作 person memory，不要手工改全局 Dream 文件。

| action | 说明 |
|--------|------|
| `recall` | 查看当前或指定 person 的记忆 |
| `remember` | 写入稳定事实，支持 `person` / `source` 作用域 |
| `search_history` | 搜索 `history.jsonl` 或 person history，支持时间和渠道过滤 |
| `map_identity` | 建立 channel:chat_id → person 映射 |

如果要修改 `SOUL.md`、`USER.md`、`memory/MEMORY.md`，应交给 Dream 处理，而不是直接改。

## MEMORY vs HISTORY

**MEMORY.md** — 只写稳定、可复用、影响未来决策的事实：

- 用户偏好（"不喜欢频繁汇报"）
- 身份信息（"位置: 杭州"）
- 长期目标、重要约定

**history.jsonl** — 时间线事件与归档摘要：

- 对话摘要、关键决策
- 一次性事件记录

## Consolidation

会话增长到阈值时，Consolidator 会归档旧消息到 `history.jsonl`。

如果当前会话能解析到 `channel:chat_id -> person`，sidecar bridge 会额外执行：

1. 读取本次新写入的 `history.jsonl` 归档条目
2. 调用 `CategorizedMemoryStore.on_consolidate(...)`
3. 只同步 person history / person facts，不改 Dream 的全局文件

## Search Past Events

`memory/history.jsonl` 是 JSONL，每行包含 `cursor`、`timestamp`、`content`。

- 优先用 `memory(search_history, ...)` 或 repo 内置搜索工具检索
- 需要精确时间点时，按时间戳或关键词查 `history.jsonl`
- person 相关历史优先查 `memory/persons/<person>/history.jsonl`

## Writing Guidelines

写入前问自己：

1. 下周/下个月还会用得上吗？
2. 会影响未来的决策吗？
3. 是稳定事实还是临时状态？

三个都是"是"→ person `MEMORY.md`；否则 → 历史或不记。
