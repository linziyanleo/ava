"""Chat session management for console conversations."""

from __future__ import annotations

from difflib import SequenceMatcher
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Awaitable


class ChatService:
    def __init__(self, agent_loop, workspace: Path, db: Any | None = None):
        self._agent = agent_loop
        self._sessions_dir = workspace / "sessions"
        self._sessions_dir.mkdir(parents=True, exist_ok=True)
        self._db = db

    @property
    def _use_db(self) -> bool:
        return self._db is not None

    @staticmethod
    def _derive_scene(key: str) -> str:
        if key.startswith("telegram:"):
            return "telegram"
        if key.startswith("console:"):
            return "console"
        if key.startswith("cli:"):
            return "cli"
        if key.startswith("cron:"):
            return "cron"
        if key == "heartbeat":
            return "heartbeat"
        if key.startswith("feishu:"):
            return "feishu"
        if key.startswith("discord:"):
            return "discord"
        return "other"

    @staticmethod
    def _extract_conversation_id(meta: dict[str, Any] | None) -> str:
        if not isinstance(meta, dict):
            return ""
        value = meta.get("conversation_id")
        return value if isinstance(value, str) else ""

    @staticmethod
    def _decode_message_content(raw_content: Any) -> Any:
        if raw_content is None or not isinstance(raw_content, str):
            return raw_content
        try:
            parsed = json.loads(raw_content)
        except (json.JSONDecodeError, TypeError):
            return raw_content
        if isinstance(parsed, (dict, list)):
            return parsed
        return raw_content

    @staticmethod
    def _message_text(raw_content: Any) -> str:
        decoded = ChatService._decode_message_content(raw_content)
        if isinstance(decoded, str):
            return decoded.strip()
        if isinstance(decoded, list):
            return "\n".join(
                item.get("text", "").strip()
                for item in decoded
                if isinstance(item, dict) and isinstance(item.get("text"), str)
            ).strip()
        return ""

    @staticmethod
    def _texts_equivalent(left: str, right: str) -> bool:
        if not left or not right:
            return False
        if left == right:
            return True
        return SequenceMatcher(a=left, b=right).ratio() >= 0.995

    def _repair_conversation_artifacts(
        self,
        session_id: int,
        conversation_id: str,
        msg_rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not self._use_db or not msg_rows:
            return msg_rows

        working = [dict(row) for row in msg_rows]
        delete_ids: list[int] = []
        blank_assistant_ids: list[int] = []

        idx = 0
        while idx + 1 < len(working):
            current = working[idx]
            following = working[idx + 1]
            if current["role"] == "user" and following["role"] == "user":
                current_text = self._message_text(current["content"])
                following_text = self._message_text(following["content"])
                has_followup = any(row["role"] != "user" for row in working[idx + 2:])
                if current_text and current_text == following_text and has_followup:
                    delete_ids.append(following["id"])
                    del working[idx + 1]
                    continue
            idx += 1

        idx = 0
        while idx < len(working):
            current = working[idx]
            current_text = self._message_text(current["content"])
            if current["role"] == "assistant" and current.get("tool_calls") and current_text:
                next_idx = idx + 1
                saw_tool = False
                while next_idx < len(working) and working[next_idx]["role"] == "tool":
                    saw_tool = True
                    next_idx += 1
                if saw_tool and next_idx < len(working):
                    final_row = working[next_idx]
                    final_text = self._message_text(final_row["content"])
                    if (
                        final_row["role"] == "assistant"
                        and not final_row.get("tool_calls")
                        and self._texts_equivalent(current_text, final_text)
                    ):
                        blank_assistant_ids.append(current["id"])
                        current["content"] = ""
            idx += 1

        if not delete_ids and not blank_assistant_ids:
            return msg_rows

        for row_id in delete_ids:
            self._db.execute(
                "DELETE FROM session_messages WHERE id = ?",
                (row_id,),
            )
        for row_id in blank_assistant_ids:
            self._db.execute(
                "UPDATE session_messages SET content = '' WHERE id = ?",
                (row_id,),
            )
        self._db.commit()

        return self._db.fetchall(
            """
            SELECT id, seq, role, content, tool_calls, tool_call_id, name,
                   reasoning_content, timestamp, conversation_id
              FROM session_messages
             WHERE session_id = ? AND conversation_id = ?
             ORDER BY seq
            """,
            (session_id, conversation_id),
        )

    def _resolve_active_conversation_id(
        self,
        session_id: int,
        meta: dict[str, Any] | None,
    ) -> str:
        active_conversation_id = self._extract_conversation_id(meta)
        if active_conversation_id:
            return active_conversation_id
        if not self._use_db:
            return ""
        latest = self._db.fetchone(
            """
            SELECT conversation_id
              FROM session_messages
             WHERE session_id = ?
             ORDER BY CASE WHEN timestamp IS NULL OR timestamp = '' THEN 1 ELSE 0 END,
                      timestamp DESC,
                      seq DESC
             LIMIT 1
            """,
            (session_id,),
        )
        if not latest:
            return ""
        value = latest["conversation_id"]
        return value if isinstance(value, str) else ""

    def list_sessions(self, user_id: str | None = None) -> list[dict]:
        if self._use_db:
            rows = self._db.fetchall(
                """SELECT s.id, s.key, s.created_at, s.updated_at, s.metadata, s.token_stats,
                          (SELECT COUNT(*) FROM session_messages WHERE session_id = s.id) as msg_count
                   FROM sessions s
                   ORDER BY s.updated_at DESC"""
            )
            sessions = []
            for r in rows:
                key = r["key"]
                meta: dict[str, Any] = {}
                ts: dict = {}
                if r["metadata"]:
                    try:
                        meta = json.loads(r["metadata"])
                    except json.JSONDecodeError:
                        pass
                if r["token_stats"]:
                    try:
                        ts = json.loads(r["token_stats"])
                    except json.JSONDecodeError:
                        pass
                sessions.append({
                    "key": key,
                    "scene": self._derive_scene(key),
                    "created_at": r["created_at"] or "",
                    "updated_at": r["updated_at"] or "",
                    "conversation_id": self._resolve_active_conversation_id(r["id"], meta),
                    "token_stats": {
                        "total_prompt_tokens": ts.get("total_prompt_tokens", 0),
                        "total_completion_tokens": ts.get("total_completion_tokens", 0),
                        "total_tokens": ts.get("total_tokens", 0),
                        "llm_calls": ts.get("llm_calls", 0),
                    },
                    "message_count": r["msg_count"],
                })
            return sessions

        sessions = []
        for f in self._sessions_dir.glob("*.jsonl"):
            if f.name.startswith("_"):
                continue
            first_line = ""
            lines = f.read_text("utf-8").splitlines()
            if lines:
                first_line = lines[0]
            key = f.stem.replace("_", ":", 1)
            created_at = ""
            updated_at = ""
            token_stats = {
                "total_prompt_tokens": 0, "total_completion_tokens": 0,
                "total_tokens": 0, "llm_calls": 0,
            }
            conversation_id = ""
            msg_count = max(0, len(lines) - 1)
            if first_line:
                try:
                    parsed = json.loads(first_line)
                    if parsed.get("_type") == "metadata":
                        key = parsed.get("key", key)
                        created_at = parsed.get("created_at", "")
                        updated_at = parsed.get("updated_at", "")
                        token_stats = parsed.get("token_stats", token_stats)
                        conversation_id = parsed.get("conversation_id") or self._extract_conversation_id(parsed.get("metadata"))
                except json.JSONDecodeError:
                    pass
            sessions.append({
                "key": key,
                "scene": self._derive_scene(key),
                "created_at": created_at,
                "updated_at": updated_at,
                "conversation_id": conversation_id,
                "token_stats": token_stats,
                "message_count": msg_count,
            })
        sessions.sort(key=lambda s: s.get("updated_at", ""), reverse=True)
        return sessions

    def list_conversations(self, session_key: str) -> list[dict[str, Any]]:
        if self._use_db:
            row = self._db.fetchone(
                "SELECT id, metadata FROM sessions WHERE key = ?",
                (session_key,),
            )
            if not row:
                return []

            meta: dict[str, Any] = {}
            if row["metadata"]:
                try:
                    meta = json.loads(row["metadata"])
                except json.JSONDecodeError:
                    meta = {}
            active_conversation_id = self._resolve_active_conversation_id(row["id"], meta)

            message_rows = self._db.fetchall(
                """
                SELECT conversation_id, seq, role, content, timestamp
                  FROM session_messages
                 WHERE session_id = ?
                 ORDER BY CASE WHEN timestamp IS NULL OR timestamp = '' THEN 1 ELSE 0 END,
                          timestamp ASC,
                          seq ASC
                """,
                (row["id"],),
            )

            groups: dict[str, dict[str, Any]] = {}
            for message_row in message_rows:
                conversation_id = message_row["conversation_id"]
                if not isinstance(conversation_id, str):
                    conversation_id = ""
                group = groups.setdefault(
                    conversation_id,
                    {
                        "conversation_id": conversation_id,
                        "first_message_preview": "",
                        "message_count": 0,
                        "created_at": "",
                        "updated_at": "",
                        "is_active": False,
                        "is_legacy": conversation_id == "",
                    },
                )
                group["message_count"] += 1
                timestamp = message_row["timestamp"] or ""
                if timestamp and not group["created_at"]:
                    group["created_at"] = timestamp
                if timestamp:
                    group["updated_at"] = timestamp
                if not group["first_message_preview"]:
                    preview = self._decode_message_content(message_row["content"])
                    if isinstance(preview, str):
                        preview_text = preview.strip()
                    elif isinstance(preview, list):
                        preview_text = " ".join(
                            item.get("text", "")
                            for item in preview
                            if isinstance(item, dict) and isinstance(item.get("text"), str)
                        ).strip()
                    else:
                        preview_text = ""
                    if preview_text:
                        group["first_message_preview"] = preview_text[:60]

            if active_conversation_id not in groups:
                groups[active_conversation_id] = {
                    "conversation_id": active_conversation_id,
                    "first_message_preview": "",
                    "message_count": 0,
                    "created_at": "",
                    "updated_at": "",
                    "is_active": True,
                    "is_legacy": active_conversation_id == "",
                }

            conversations = list(groups.values())
            for item in conversations:
                item["is_active"] = item["conversation_id"] == active_conversation_id
            conversations.sort(
                key=lambda item: item["updated_at"] or item["created_at"] or "",
                reverse=True,
            )
            conversations.sort(key=lambda item: not item["is_active"])
            return conversations

        messages = self.get_messages(session_key)
        if not messages:
            return []
        first_timestamp = messages[0].get("timestamp", "")
        last_timestamp = messages[-1].get("timestamp", "")
        preview = ""
        for message in messages:
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                preview = content.strip()[:60]
                break
        return [{
            "conversation_id": "",
            "first_message_preview": preview,
            "message_count": len(messages),
            "created_at": first_timestamp,
            "updated_at": last_timestamp,
            "is_active": True,
            "is_legacy": True,
        }]

    def get_messages(self, session_key: str, conversation_id: str | None = None) -> list[dict]:
        """Return full message details for one conversation from DB or JSONL."""
        if self._use_db:
            row = self._db.fetchone(
                "SELECT id, metadata FROM sessions WHERE key = ?",
                (session_key,),
            )
            if not row:
                return []
            meta: dict[str, Any] = {}
            if row["metadata"]:
                try:
                    meta = json.loads(row["metadata"])
                except json.JSONDecodeError:
                    meta = {}
            resolved_conversation_id = (
                self._resolve_active_conversation_id(row["id"], meta)
                if conversation_id is None
                else conversation_id
            )
            msg_rows = self._db.fetchall(
                """SELECT id, seq, role, content, tool_calls, tool_call_id, name,
                          reasoning_content, timestamp, conversation_id
                   FROM session_messages
                   WHERE session_id = ? AND conversation_id = ?
                   ORDER BY seq""",
                (row["id"], resolved_conversation_id),
            )
            msg_rows = self._repair_conversation_artifacts(
                row["id"],
                resolved_conversation_id,
                msg_rows,
            )
            messages: list[dict] = []
            for mr in msg_rows:
                msg: dict[str, Any] = {"role": mr["role"]}
                msg["content"] = self._decode_message_content(mr["content"])
                if mr["tool_calls"]:
                    try:
                        msg["tool_calls"] = json.loads(mr["tool_calls"])
                    except json.JSONDecodeError:
                        pass
                if mr["tool_call_id"]:
                    msg["tool_call_id"] = mr["tool_call_id"]
                if mr["name"]:
                    msg["name"] = mr["name"]
                if mr["reasoning_content"]:
                    msg["reasoning_content"] = mr["reasoning_content"]
                if mr["timestamp"]:
                    msg["timestamp"] = mr["timestamp"]
                msg["metadata"] = {"conversation_id": mr["conversation_id"] or ""}
                messages.append(msg)
            return messages

        safe_key = session_key.replace(":", "_")
        session_file = self._sessions_dir / f"{safe_key}.jsonl"
        if not session_file.exists():
            return []
        messages = []
        for line in session_file.read_text("utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if entry.get("_type") == "metadata":
                    continue
                if entry.get("role"):
                    messages.append(entry)
            except json.JSONDecodeError:
                continue
        return messages

    def create_session(self, user_id: str, title: str = "") -> dict[str, str]:
        sid = uuid.uuid4().hex[:8]
        conversation_id = f"conv_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        session_title = title or f"Session {sid}"
        session_key = f"console:{sid}"

        if self._use_db:
            meta = json.dumps(
                {
                    "title": session_title,
                    "user": user_id,
                    "conversation_id": conversation_id,
                },
                ensure_ascii=False,
            )
            ts_json = json.dumps({
                "total_prompt_tokens": 0, "total_completion_tokens": 0,
                "total_tokens": 0, "llm_calls": 0,
            })
            self._db.execute(
                """INSERT INTO sessions (key, created_at, updated_at, metadata, token_stats)
                   VALUES (?, ?, ?, ?, ?)""",
                (session_key, now, now, meta, ts_json),
            )
            self._db.commit()
        else:
            session_file = self._sessions_dir / f"console_{sid}.jsonl"
            metadata_line = json.dumps({
                "_type": "metadata",
                "key": session_key,
                "created_at": now,
                "updated_at": now,
                "title": session_title,
                "user": user_id,
                "conversation_id": conversation_id,
                "token_stats": {
                    "total_prompt_tokens": 0,
                    "total_completion_tokens": 0,
                    "total_tokens": 0,
                    "llm_calls": 0,
                },
            }, ensure_ascii=False)
            session_file.write_text(metadata_line + "\n", "utf-8")
        return {"session_id": sid, "conversation_id": conversation_id}

    async def send_message(
        self,
        session_id: str,
        message: str,
        user_id: str,
        on_progress: Callable[..., Awaitable[None]] | None = None,
    ) -> str:
        session_key = f"console:{session_id}"
        response = await self._agent.process_direct(
            content=message,
            session_key=session_key,
            channel="console",
            chat_id=user_id,
            on_progress=on_progress,
        )
        return response or ""

    def get_history(self, session_id: str) -> list[dict]:
        if self._use_db:
            session_key = f"console:{session_id}"
            row = self._db.fetchone(
                "SELECT id, metadata FROM sessions WHERE key = ?",
                (session_key,),
            )
            if not row:
                return []
            meta: dict[str, Any] = {}
            if row["metadata"]:
                try:
                    meta = json.loads(row["metadata"])
                except json.JSONDecodeError:
                    meta = {}
            active_conversation_id = self._resolve_active_conversation_id(row["id"], meta)
            msg_rows = self._db.fetchall(
                """SELECT role, content, timestamp FROM session_messages
                   WHERE session_id = ? AND conversation_id = ? AND role IN ('user', 'assistant') AND content IS NOT NULL AND content != ''
                   ORDER BY seq""",
                (row["id"], active_conversation_id),
            )
            return [
                {"role": r["role"], "content": r["content"], "timestamp": r["timestamp"] or ""}
                for r in msg_rows
            ]

        session_file = self._sessions_dir / f"console_{session_id}.jsonl"
        if not session_file.exists():
            return []

        messages = []
        for line in session_file.read_text("utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                role = entry.get("role", "")
                content = entry.get("content", "")
                if role in ("user", "assistant") and content:
                    messages.append({
                        "role": role,
                        "content": content,
                        "timestamp": entry.get("timestamp", ""),
                    })
            except json.JSONDecodeError:
                continue
        return messages

    def delete_session(self, session_id: str) -> bool:
        if self._use_db:
            session_key = f"console:{session_id}"
            self._db.execute("DELETE FROM sessions WHERE key = ?", (session_key,))
            self._db.commit()
            if self._agent and hasattr(self._agent, "sessions"):
                self._agent.sessions.invalidate(session_key)
            return True

        session_file = self._sessions_dir / f"console_{session_id}.jsonl"
        if not session_file.exists():
            return False
        session_file.unlink()
        return True
