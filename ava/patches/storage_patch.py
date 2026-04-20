"""SQLite storage patch for nanobot SessionManager."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from typing import Any

from loguru import logger

from ava.launcher import register_patch
from ava.storage import Database

_FLOAT_TIMESTAMP_RE = re.compile(r"^\d+(?:\.\d+)?$")
_BG_TASK_ASSISTANT_RE = re.compile(
    r"^\[Background Task ([A-Za-z0-9_-]+) ([A-Z_]+)\]\nType: ([^|\n]+?) \| Duration: (\d+)ms(?:\n\n([\s\S]*))?$"
)
_BG_TASK_CONTINUATION_RE = re.compile(
    r"^\[Background Task Completed — ([A-Z_]+)\]\nTask: ([^:\n]+):([A-Za-z0-9_-]+)\nDuration: (\d+)ms(?:\n\n([\s\S]*))?$"
)
_BG_TASK_CONTINUATION_TAIL = "请基于以上结果继续处理后续步骤。如果所有工作已完成，请总结。"


def apply_storage_patch() -> str:
    """
    Patch SessionManager to use SQLite instead of JSONL for session storage.

    Returns:
        Description of what was patched.
    """
    from nanobot.config.paths import get_data_dir
    from nanobot.session.manager import SessionManager, Session

    missing = [
        method_name
        for method_name in ("save", "_load", "list_sessions")
        if not hasattr(SessionManager, method_name)
    ]
    if missing:
        logger.warning(
            "storage_patch skipped: SessionManager missing methods {}",
            ", ".join(missing),
        )
        return f"storage_patch skipped (missing methods: {', '.join(missing)})"

    if getattr(SessionManager.save, "_ava_storage_patched", False):
        return "storage_patch already applied (skipped)"

    db_path = get_data_dir() / "nanobot.db"
    db = Database(db_path)

    # Register global singleton so other patches (skills_patch) can access it
    from ava.storage import set_db
    set_db(db)

    original_save = SessionManager.save
    original_load = SessionManager._load
    original_list = SessionManager.list_sessions

    def _get_session_conversation_id(session: Session) -> str:
        metadata = getattr(session, "metadata", None)
        if not isinstance(metadata, dict):
            return ""
        value = metadata.get("conversation_id")
        return value if isinstance(value, str) else ""

    def _resolve_active_conversation_id(conn, session_row) -> tuple[dict[str, Any], str]:
        metadata_raw = session_row["metadata"] or "{}"
        try:
            metadata = json.loads(metadata_raw)
        except json.JSONDecodeError:
            metadata = {}

        active_conversation_id = metadata.get("conversation_id")
        if isinstance(active_conversation_id, str) and active_conversation_id:
            return metadata, active_conversation_id

        latest_row = conn.execute(
            """
            SELECT conversation_id
              FROM session_messages
             WHERE session_id = ?
             ORDER BY CASE WHEN timestamp IS NULL OR timestamp = '' THEN 1 ELSE 0 END,
                      timestamp DESC,
                      seq DESC
             LIMIT 1
            """,
            (session_row["id"],),
        ).fetchone()
        if latest_row:
            value = latest_row["conversation_id"]
            active_conversation_id = value if isinstance(value, str) else ""
        else:
            active_conversation_id = ""

        metadata["conversation_id"] = active_conversation_id
        return metadata, active_conversation_id

    def _decode_content(raw_content: Any) -> Any:
        if raw_content is None:
            return None
        if not isinstance(raw_content, str):
            return raw_content
        try:
            parsed = json.loads(raw_content)
        except (json.JSONDecodeError, TypeError):
            return raw_content
        if isinstance(parsed, (dict, list)):
            return parsed
        return raw_content

    def _message_signature(
        *,
        role: str,
        content: str | None,
        tool_calls_json: str | None,
        tool_call_id: str | None,
        name: str | None,
        reasoning_content: str | None,
        timestamp: str | None,
    ) -> tuple[str, str | None, str | None, str | None, str | None, str | None, str | None]:
        return (
            role,
            content,
            tool_calls_json,
            tool_call_id,
            name,
            reasoning_content,
            timestamp,
        )

    def _message_logical_signature(
        *,
        role: str,
        content: str | None,
        tool_calls_json: str | None,
        tool_call_id: str | None,
        name: str | None,
        reasoning_content: str | None,
    ) -> tuple[str, ...] | None:
        if role == "assistant" and tool_calls_json:
            return (
                "assistant_tool_call",
                tool_calls_json,
                content or "",
                reasoning_content or "",
            )

        if role == "tool" and tool_call_id:
            return (
                "tool_result",
                tool_call_id,
                name or "",
                content or "",
            )

        if not isinstance(content, str):
            return None

        assistant_match = _BG_TASK_ASSISTANT_RE.match(content)
        if assistant_match:
            return (
                "bg_task_assistant",
                assistant_match[1],
                assistant_match[2],
                (assistant_match[5] or "").strip(),
            )

        continuation_match = _BG_TASK_CONTINUATION_RE.match(content)
        if continuation_match:
            body = (continuation_match[5] or "").strip()
            if body.endswith(_BG_TASK_CONTINUATION_TAIL):
                body = body[: -len(_BG_TASK_CONTINUATION_TAIL)].rstrip()
            return (
                "bg_task_continuation",
                continuation_match[3],
                continuation_match[1],
                body,
            )

        return None

    def _stringify_timestamp_for_insert(timestamp: Any) -> str | None:
        if timestamp is None:
            return None
        return timestamp if isinstance(timestamp, str) else str(timestamp)

    def _normalize_loaded_timestamp(timestamp: Any) -> Any:
        if isinstance(timestamp, (int, float)):
            try:
                return datetime.fromtimestamp(float(timestamp)).isoformat()
            except (OverflowError, OSError, ValueError):
                return str(timestamp)

        if not isinstance(timestamp, str):
            return timestamp

        raw = timestamp.strip()
        if not raw or not _FLOAT_TIMESTAMP_RE.fullmatch(raw):
            return timestamp

        try:
            return datetime.fromtimestamp(float(raw)).isoformat()
        except (OverflowError, OSError, ValueError):
            return timestamp

    def patched_save(self: SessionManager, session: Session) -> None:
        """Save only the active conversation slice for a session."""
        conn = db._get_conn()
        active_conversation_id = _get_session_conversation_id(session)

        metadata_json = json.dumps(session.metadata, ensure_ascii=False)
        token_stats_json = json.dumps(
            session.metadata.get("token_stats", {}), ensure_ascii=False
        )

        conn.execute(
            """INSERT INTO sessions
               (key, created_at, updated_at, metadata, last_consolidated, last_completed, token_stats)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET
                   updated_at = excluded.updated_at,
                   metadata = excluded.metadata,
                   last_consolidated = excluded.last_consolidated,
                   last_completed = excluded.last_completed,
                   token_stats = excluded.token_stats""",
            (
                session.key,
                session.created_at.isoformat(),
                session.updated_at.isoformat(),
                metadata_json,
                session.last_consolidated,
                session.metadata.get("last_completed"),
                token_stats_json,
            ),
        )

        session_row = conn.execute(
            "SELECT id FROM sessions WHERE key = ?", (session.key,)
        ).fetchone()

        if session_row:
            session_id = session_row["id"]

            row = conn.execute(
                """
                SELECT COUNT(*) as cnt
                  FROM session_messages
                 WHERE session_id = ? AND conversation_id = ?
                """,
                (session_id, active_conversation_id),
            ).fetchone()
            db_count = row["cnt"] if row else 0

            mem_count = len(session.messages)
            needs_rewrite = mem_count < db_count
            if not needs_rewrite and db_count > 0 and mem_count > 0:
                first_db = conn.execute(
                    """
                    SELECT timestamp
                      FROM session_messages
                     WHERE session_id = ? AND conversation_id = ? AND seq = 0
                    """,
                    (session_id, active_conversation_id),
                ).fetchone()
                if first_db:
                    mem_ts = session.messages[0].get("timestamp", "")
                    if first_db["timestamp"] != mem_ts:
                        needs_rewrite = True

            if needs_rewrite:
                conn.execute(
                    "DELETE FROM session_messages WHERE session_id = ? AND conversation_id = ?",
                    (session_id, active_conversation_id),
                )
                start_seq = 0
                existing_signatures: set[tuple[str, str | None, str | None, str | None, str | None, str | None, str | None]] = set()
                existing_logical_signatures: set[tuple[str, ...]] = set()
            else:
                start_seq = db_count
                existing_rows = conn.execute(
                    """
                    SELECT role, content, tool_calls, tool_call_id, name, reasoning_content, timestamp
                      FROM session_messages
                     WHERE session_id = ? AND conversation_id = ?
                    """,
                    (session_id, active_conversation_id),
                ).fetchall()
                existing_signatures = {
                    _message_signature(
                        role=row["role"],
                        content=row["content"],
                        tool_calls_json=row["tool_calls"],
                        tool_call_id=row["tool_call_id"],
                        name=row["name"],
                        reasoning_content=row["reasoning_content"],
                        timestamp=row["timestamp"],
                    )
                    for row in existing_rows
                }
                existing_logical_signatures = {
                    logical_signature
                    for row in existing_rows
                    if (logical_signature := _message_logical_signature(
                        role=row["role"],
                        content=row["content"],
                        tool_calls_json=row["tool_calls"],
                        tool_call_id=row["tool_call_id"],
                        name=row["name"],
                        reasoning_content=row["reasoning_content"],
                    )) is not None
                }

            for seq in range(start_seq, mem_count):
                msg = session.messages[seq]
                tool_calls_json = (
                    json.dumps(msg.get("tool_calls", []), ensure_ascii=False)
                    if msg.get("tool_calls") else None
                )
                content = msg.get("content")
                if content is not None and not isinstance(content, str):
                    content = json.dumps(content, ensure_ascii=False)
                signature = _message_signature(
                    role=msg.get("role", ""),
                    content=content,
                    tool_calls_json=tool_calls_json,
                    tool_call_id=msg.get("tool_call_id"),
                    name=msg.get("name"),
                    reasoning_content=msg.get("reasoning_content"),
                    timestamp=_stringify_timestamp_for_insert(msg.get("timestamp")),
                )
                logical_signature = _message_logical_signature(
                    role=msg.get("role", ""),
                    content=content,
                    tool_calls_json=tool_calls_json,
                    tool_call_id=msg.get("tool_call_id"),
                    name=msg.get("name"),
                    reasoning_content=msg.get("reasoning_content"),
                )
                if signature in existing_signatures:
                    continue
                if logical_signature is not None and logical_signature in existing_logical_signatures:
                    continue

                conn.execute(
                    """INSERT INTO session_messages
                       (session_id, seq, conversation_id, role, content, tool_calls, tool_call_id, name, reasoning_content, timestamp)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        session_id,
                        seq,
                        active_conversation_id,
                        msg.get("role", ""),
                        content,
                        tool_calls_json,
                        msg.get("tool_call_id"),
                        msg.get("name"),
                        msg.get("reasoning_content"),
                        _stringify_timestamp_for_insert(msg.get("timestamp")),
                    ),
                )
                existing_signatures.add(signature)
                if logical_signature is not None:
                    existing_logical_signatures.add(logical_signature)

        conn.commit()
        self._cache[session.key] = session

    def patched_load(self: SessionManager, key: str) -> Session | None:
        """Load only the active conversation from SQLite, then apply backfill."""
        conn = db._get_conn()

        session_row = conn.execute(
            "SELECT * FROM sessions WHERE key = ?", (key,)
        ).fetchone()

        if not session_row:
            return None

        metadata, active_conversation_id = _resolve_active_conversation_id(conn, session_row)
        messages = []
        msg_rows = conn.execute(
            """
            SELECT *
              FROM session_messages
             WHERE session_id = ? AND conversation_id = ?
             ORDER BY seq
            """,
            (session_row["id"], active_conversation_id),
        ).fetchall()

        for msg_row in msg_rows:
            msg = {
                "role": msg_row["role"],
                "content": _decode_content(msg_row["content"]),
                "timestamp": _normalize_loaded_timestamp(msg_row["timestamp"]),
            }
            if msg_row["tool_calls"]:
                msg["tool_calls"] = json.loads(msg_row["tool_calls"])
            if msg_row["tool_call_id"]:
                msg["tool_call_id"] = msg_row["tool_call_id"]
            if msg_row["name"]:
                msg["name"] = msg_row["name"]
            if msg_row["reasoning_content"]:
                msg["reasoning_content"] = msg_row["reasoning_content"]
            messages.append(msg)

        try:
            metadata["token_stats"] = json.loads(session_row["token_stats"] or "{}")
        except json.JSONDecodeError:
            metadata["token_stats"] = {}
        if session_row["last_completed"]:
            metadata["last_completed"] = session_row["last_completed"]

        session = Session(
            key=key,
            messages=messages,
            created_at=datetime.fromisoformat(session_row["created_at"]),
            metadata=metadata,
            last_consolidated=session_row["last_consolidated"],
        )

        # Apply backfill after SQLite load (replaces channel_patch's _load wrapper)
        try:
            from ava.session.backfill_turns import _backfill_messages
            fixed_messages, inserted, normalized = _backfill_messages(session.messages)
            if inserted > 0 or normalized > 0:
                session.messages = fixed_messages
                logger.info(
                    "Backfilled session {}: {} placeholders added, {} normalized",
                    key, inserted, normalized,
                )
        except Exception as exc:
            logger.warning("Backfill failed for session {}: {}", key, exc)

        return session

    def patched_list(self: SessionManager) -> list[dict[str, Any]]:
        """List all sessions from SQLite database."""
        conn = db._get_conn()
        rows = conn.execute(
            "SELECT key, created_at, updated_at FROM sessions ORDER BY updated_at DESC"
        ).fetchall()
        
        return [
            {
                "key": row["key"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "path": str(db_path),
            }
            for row in rows
        ]

    patched_save._ava_storage_patched = True
    patched_load._ava_storage_patched = True
    patched_list._ava_storage_patched = True
    SessionManager.save = patched_save
    SessionManager._load = patched_load
    SessionManager.list_sessions = patched_list

    # Share db with loop_patch so AgentLoop gets the same instance
    try:
        from ava.patches.loop_patch import set_shared_db
        set_shared_db(db)
    except Exception as exc:
        logger.warning("Could not share db with loop_patch: {}", exc)

    return "SessionManager patched to use SQLite storage"


register_patch("sqlite_storage", apply_storage_patch)
