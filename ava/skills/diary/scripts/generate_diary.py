#!/usr/bin/env python3
"""
日记素材提取器
从 session 文件中提取前一天的对话素材，输出结构化文本到 stdout。
Agent 读取 stdout 后，以第一人称用 LLM 写作日记。

路径解析优先级：
  1. 环境变量 NANOBOT_WORKSPACE
  2. 命令行参数 --workspace <path>
  3. 自动推断：假设脚本位于 <workspace>/skills/diary/scripts/（workspace 安装位置）
"""

import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path


def _resolve_workspace() -> Path:
    """解析 workspace 根目录。"""
    # 1. 环境变量
    env_ws = os.environ.get("NANOBOT_WORKSPACE")
    if env_ws:
        return Path(env_ws).resolve()

    # 2. 命令行 --workspace 参数（在 main() 解析前用，这里做快速扫描）
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--workspace" and i + 1 < len(args):
            return Path(args[i + 1]).resolve()

    # 3. 自动推断：脚本在 <workspace>/skills/diary/scripts/
    #    或 <ava_dir>/skills/diary/scripts/（项目内置位置）
    #    两种情况都尝试，取存在 sessions/ 或 nanobot.db 的那个
    script_dir = Path(__file__).resolve().parent  # scripts/
    candidates = [
        script_dir.parent.parent.parent.parent,  # workspace 安装: workspace/skills/diary/scripts
        script_dir.parent.parent.parent,          # ava 安装: ava/skills/diary/scripts -> ava/ (不对，但留着)
    ]
    for c in candidates:
        if (c / "sessions").exists() or (c.parent / "nanobot.db").exists() or (c / "nanobot.db").exists():
            return c

    # 最终 fallback：脚本所在位置向上 4 级
    return script_dir.parent.parent.parent.parent


WORKSPACE_ROOT = _resolve_workspace()
SESSIONS_DIR = WORKSPACE_ROOT / "sessions"
DIARY_DIR = WORKSPACE_ROOT / "diary"
# DB 可能在 workspace 同级（<nanobot_dir>/nanobot.db）或 workspace 内
_db_candidates = [WORKSPACE_ROOT.parent / "nanobot.db", WORKSPACE_ROOT / "nanobot.db"]
DB_PATH = next((p for p in _db_candidates if p.exists()), _db_candidates[0])

MAX_CONTENT_LENGTH = 500
MAX_TOTAL_MESSAGES = 200

WEEKDAY_CN = {
    'Monday': '周一', 'Tuesday': '周二', 'Wednesday': '周三',
    'Thursday': '周四', 'Friday': '周五', 'Saturday': '周六', 'Sunday': '周日'
}

SKIP_PATTERNS = [
    'tool_calls', 'function_call', '✅ AIWay 心跳检查',
    'heartbeat', '[Scheduled Task]', 'Timer finished'
]


def get_yesterday_date():
    yesterday = datetime.now() - timedelta(days=1)
    return yesterday.strftime("%Y-%m-%d")


def truncate_content(content, max_length=MAX_CONTENT_LENGTH):
    if not content or len(content) <= max_length:
        return content
    if content.startswith('{') or content.startswith('['):
        try:
            json.loads(content)
            return f"[结构化数据，{len(content)} 字]"
        except Exception:
            pass
    head_len = max_length * 2 // 3
    tail_len = max_length // 3
    return f"{content[:head_len]}...[省略]...{content[-tail_len:]}"


def estimate_tokens(text):
    chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    other_chars = len(text) - chinese_chars
    return chinese_chars // 2 + other_chars // 4


def should_skip(content):
    content_lower = content.lower()
    return any(p.lower() in content_lower for p in SKIP_PATTERNS)


def _extract_text_from_content(content_raw):
    """从 content 字段提取纯文本。content 可能是字符串或 JSON 列表（multimodal）。"""
    if not content_raw:
        return None
    if isinstance(content_raw, str):
        if content_raw.startswith('['):
            try:
                parts = json.loads(content_raw)
                if isinstance(parts, list):
                    texts = []
                    for part in parts:
                        if isinstance(part, dict) and part.get('type') == 'text':
                            texts.append(part.get('text', ''))
                        elif isinstance(part, str):
                            texts.append(part)
                    return '\n'.join(texts) if texts else None
            except (json.JSONDecodeError, Exception):
                pass
        return content_raw
    return None


def _process_message(role, content_raw, timestamp, stats):
    """处理单条消息，返回 conversation dict 或 None。"""
    content = _extract_text_from_content(content_raw)
    if not content:
        return None
    if isinstance(content, dict):
        content = str(content.get('text', content.get('content', '')))
    if not isinstance(content, str) or len(content) < 15:
        return None
    if should_skip(content):
        stats['skipped'] += 1
        return None

    return {
        'role': role,
        'content': truncate_content(content),
        'timestamp': timestamp or '',
        'time': timestamp[11:16] if timestamp and len(timestamp) >= 16 else '',
    }


def collect_from_db(date_str):
    """从 SQLite 数据库读取对话。"""
    all_convs = []
    stats = {
        'total_messages': 0, 'truncated': False, 'skipped': 0,
        'errors': 0, 'files_processed': 0
    }

    conn = sqlite3.connect(str(DB_PATH))
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, key FROM sessions "
            "WHERE key NOT LIKE 'cron:%' AND key != 'heartbeat'"
        )
        sessions = cur.fetchall()

        for session_id, session_key in sessions:
            cur.execute(
                "SELECT role, content, timestamp FROM session_messages "
                "WHERE session_id = ? AND role IN ('user', 'assistant') "
                "AND timestamp LIKE ? "
                "ORDER BY seq",
                (session_id, f"{date_str}%")
            )
            rows = cur.fetchall()
            stats['files_processed'] += 1

            for role, content_raw, timestamp in rows:
                if stats['total_messages'] >= MAX_TOTAL_MESSAGES:
                    stats['truncated'] = True
                    break
                try:
                    conv = _process_message(role, content_raw, timestamp, stats)
                    if conv:
                        all_convs.append(conv)
                        stats['total_messages'] += 1
                except Exception:
                    stats['errors'] += 1

            if stats['truncated']:
                break
    finally:
        conn.close()

    all_convs.sort(key=lambda x: x.get('timestamp', ''))
    return all_convs, stats


def read_session_file(session_path, target_date, stats):
    """从 JSONL 文件读取对话（fallback）。"""
    conversations = []
    if not session_path.exists():
        return conversations

    with open(session_path, 'r', encoding='utf-8') as f:
        for line in f:
            if stats['total_messages'] >= MAX_TOTAL_MESSAGES:
                stats['truncated'] = True
                break
            try:
                msg = json.loads(line.strip())
                timestamp = msg.get('timestamp', '')
                if target_date not in timestamp:
                    continue

                conv = _process_message(
                    msg.get('role', ''), msg.get('content', ''), timestamp, stats
                )
                if conv:
                    conversations.append(conv)
                    stats['total_messages'] += 1

            except (json.JSONDecodeError, Exception):
                stats['errors'] += 1
    return conversations


def collect_from_jsonl(date_str):
    """从 JSONL 文件读取对话（fallback）。"""
    all_convs = []
    stats = {
        'total_messages': 0, 'truncated': False, 'skipped': 0,
        'errors': 0, 'files_processed': 0
    }

    if not SESSIONS_DIR.exists():
        return all_convs, stats

    for sf in SESSIONS_DIR.glob('*.jsonl'):
        convs = read_session_file(sf, date_str, stats)
        all_convs.extend(convs)
        stats['files_processed'] += 1
        if stats['truncated']:
            break

    all_convs.sort(key=lambda x: x.get('timestamp', ''))
    return all_convs, stats


def collect_all_conversations(date_str):
    """优先从数据库读取，数据库不存在则 fallback 到 JSONL。"""
    if DB_PATH.exists():
        return collect_from_db(date_str)
    return collect_from_jsonl(date_str)


def build_timeline(conversations):
    """按时间段分组对话，每个时段形成一个事件块。"""
    if not conversations:
        return []

    segments = []
    current_segment = {'start': '', 'end': '', 'conversations': []}

    for conv in conversations:
        t = conv.get('time', '')
        if not current_segment['conversations']:
            current_segment['start'] = t
            current_segment['end'] = t
            current_segment['conversations'].append(conv)
        else:
            last_t = current_segment['end']
            gap_minutes = _time_diff_minutes(last_t, t)
            if gap_minutes > 30:
                segments.append(current_segment)
                current_segment = {'start': t, 'end': t, 'conversations': [conv]}
            else:
                current_segment['end'] = t
                current_segment['conversations'].append(conv)

    if current_segment['conversations']:
        segments.append(current_segment)

    return segments


def _time_diff_minutes(t1, t2):
    """计算两个 HH:MM 格式时间的分钟差。"""
    try:
        h1, m1 = map(int, t1.split(':'))
        h2, m2 = map(int, t2.split(':'))
        return (h2 * 60 + m2) - (h1 * 60 + m1)
    except Exception:
        return 0


def _find_silent_periods(segments):
    """找出时间线中的沉默时段（间隔 > 60 分钟）。"""
    silents = []
    for i in range(len(segments) - 1):
        end_t = segments[i]['end']
        start_t = segments[i + 1]['start']
        gap = _time_diff_minutes(end_t, start_t)
        if gap > 60:
            silents.append(f"{end_t} - {start_t}（沉默 {gap} 分钟）")
    return silents


def extract_material(date_str):
    """提取结构化素材，返回文本。"""
    conversations, stats = collect_all_conversations(date_str)

    if not conversations:
        return f"# 日记素材 — {date_str}\n\n今天没有对话记录。"

    dt = datetime.strptime(date_str, "%Y-%m-%d")
    weekday_cn = WEEKDAY_CN.get(dt.strftime("%A"), '')

    segments = build_timeline(conversations)
    silents = _find_silent_periods(segments)

    lines = [f"# 日记素材 — {date_str} {weekday_cn}\n"]

    lines.append("## 统计")
    lines.append(f"- 总消息数: {stats['total_messages']}")
    if segments:
        lines.append(f"- 活跃时段: {segments[0]['start']} - {segments[-1]['end']}")
    if silents:
        lines.append(f"- 沉默时段: {'; '.join(silents)}")
    lines.append("")

    lines.append("## 时间线")
    for seg in segments:
        n = len(seg['conversations'])
        lines.append(f"\n### {seg['start']} - {seg['end']}（{n} 条消息）")
        for conv in seg['conversations']:
            role_label = "主人" if conv['role'] == 'user' else "我"
            content = conv['content'].replace('\n', ' ').strip()
            if len(content) > 200:
                content = content[:200] + "..."
            lines.append(f"- [{role_label} {conv['time']}] {content}")

    lines.append("\n## 关键对话片段")
    key_convs = _select_key_conversations(conversations)
    for conv in key_convs:
        role_label = "主人" if conv['role'] == 'user' else "我"
        lines.append(f"\n**[{conv['time']}] {role_label}:**")
        lines.append(conv['content'])

    return '\n'.join(lines)


def _select_key_conversations(conversations, max_count=8):
    """挑选最有价值的对话片段：较长的、有情感的、非技术汇报的。"""
    scored = []
    for conv in conversations:
        content = conv['content']
        score = 0
        length = len(content)
        if 50 < length < 400:
            score += 2
        elif length >= 400:
            score += 1

        emotional_words = ['哈哈', '笑死', '😂', '🤣', '开心', '难过', '生气',
                           '想', '喜欢', '讨厌', '无聊', '好吃', '馋', '可爱',
                           '晚安', '早安', '加油', '辛苦', '害', '呜', '啊',
                           '！！', '？？', '...', '～', '嘿嘿', '哼', '呢']
        score += sum(1 for w in emotional_words if w in content)

        if conv['role'] == 'user':
            score += 1

        scored.append((score, conv))

    scored.sort(key=lambda x: x[0], reverse=True)
    selected = [conv for _, conv in scored[:max_count]]
    selected.sort(key=lambda x: x.get('timestamp', ''))
    return selected


def main():
    date_str = get_yesterday_date()

    args = sys.argv[1:]
    # 解析位置参数（日期）和 --workspace（已在 _resolve_workspace 处理）
    positional = [a for a in args if not a.startswith('--') and args.index(a) == 0 or
                  (a not in ('--workspace',) and (args.index(a) == 0 or args[args.index(a)-1] != '--workspace'))]
    # 更简单的解析
    clean_args = []
    skip_next = False
    for a in args:
        if skip_next:
            skip_next = False
            continue
        if a == '--workspace':
            skip_next = True
            continue
        clean_args.append(a)

    if clean_args:
        date_str = clean_args[0]

    existing = DIARY_DIR / f"{date_str}.md"
    if existing.exists():
        print(f"[SKIP] 日记已存在: {existing}", file=sys.stderr)
        sys.exit(0)

    material = extract_material(date_str)
    print(material)


if __name__ == "__main__":
    main()
