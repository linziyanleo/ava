"""Chat session management for console conversations."""

from __future__ import annotations

import asyncio
from difflib import SequenceMatcher
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Awaitable

from nanobot.bus.events import OutboundMessage

from ava.console.services.context_preview_service import build_context_preview

_LOCAL_TIMEZONE = datetime.now().astimezone().tzinfo or timezone.utc
_IMAGE_PLACEHOLDER_RE = re.compile(r"\[image:\s*([^\]]+?)\]", re.IGNORECASE)
_BG_TASK_ASSISTANT_RE = re.compile(
    r"^\[Background Task ([A-Za-z0-9_-]+) ([A-Z_]+)\]\nType: ([^|\n]+?) \| Duration: (\d+)ms(?:\n\n([\s\S]*))?$"
)
_BG_TASK_CONTINUATION_RE = re.compile(
    r"^\[Background Task Completed — ([A-Z_]+)\]\nTask: ([^:\n]+):([A-Za-z0-9_-]+)\nDuration: (\d+)ms(?:\n\n([\s\S]*))?$"
)
_AGENT_MENTION_RE = re.compile(r"(?<!\w)@([A-Za-z][A-Za-z0-9_-]*)(?![\w-])")
_AGENT_ALIASES = {
    "nanobot": "nanobot",
    "nanobot_default": "nanobot",
    "codex": "codex",
    "codex_default": "codex",
    "claude": "claude_code",
    "claude_code": "claude_code",
    "claude-code": "claude_code",
    "claude_code_default": "claude_code",
    "image": "image_gen",
    "image_gen": "image_gen",
    "image-gen": "image_gen",
    "image_gen_default": "image_gen",
    "user": "user",
}
_DEFAULT_CONTEXT_MODEL_LIMIT = 200_000


class ChatService:
    def __init__(self, agent_loop, workspace: Path, db: Any | None = None):
        self._agent = agent_loop
        self._sessions_dir = workspace / "sessions"
        self._sessions_dir.mkdir(parents=True, exist_ok=True)
        self._db = db

    @property
    def _use_db(self) -> bool:
        return self._db is not None

    def _session_exists(self, session_key: str) -> bool:
        if self._use_db:
            row = self._db.fetchone(
                "SELECT 1 AS ok FROM sessions WHERE key = ?",
                (session_key,),
            )
            return row is not None

        safe_key = session_key.replace(":", "_")
        return (self._sessions_dir / f"{safe_key}.jsonl").exists()

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
    def _normalize_agent_id(value: Any) -> str:
        if not isinstance(value, str):
            return ""
        cleaned = value.strip().lstrip("@")
        if not cleaned:
            return ""
        alias_key = cleaned.replace(":", "_").lower()
        return _AGENT_ALIASES.get(alias_key, _AGENT_ALIASES.get(cleaned.lower(), cleaned))

    @classmethod
    def _normalize_agent_ids(cls, values: Any, *, fallback: list[str] | None = None) -> list[str]:
        if isinstance(values, str):
            candidates: list[Any] = [values]
        elif isinstance(values, list):
            candidates = values
        else:
            candidates = []
        normalized: list[str] = []
        for value in candidates:
            agent_id = cls._normalize_agent_id(value)
            if agent_id and agent_id != "user" and agent_id not in normalized:
                normalized.append(agent_id)
        if normalized:
            return normalized
        return list(fallback or [])

    @classmethod
    def _parse_agent_mentions(cls, content: str) -> list[str]:
        if not content:
            return []
        return cls._normalize_agent_ids([match.group(1) for match in _AGENT_MENTION_RE.finditer(content)])

    @classmethod
    def _decode_agent_list(cls, raw_value: Any) -> list[str]:
        if isinstance(raw_value, list):
            return cls._normalize_agent_ids(raw_value)
        if not isinstance(raw_value, str) or not raw_value:
            return []
        try:
            decoded = json.loads(raw_value)
        except json.JSONDecodeError:
            return []
        return cls._normalize_agent_ids(decoded)

    @staticmethod
    def _normalize_direct_response_content(response: Any) -> str:
        if response is None:
            return ""
        if isinstance(response, OutboundMessage):
            return response.content or ""
        if isinstance(response, str):
            return response
        return str(response)

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
    def _preview_text(raw_content: Any) -> str:
        text = ChatService._message_text(raw_content)
        if not text:
            return ""
        text = _IMAGE_PLACEHOLDER_RE.sub("[image]", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def _texts_equivalent(left: str, right: str) -> bool:
        if not left or not right:
            return False
        if left == right:
            return True
        return SequenceMatcher(a=left, b=right).ratio() >= 0.995

    @staticmethod
    def _background_task_signature(content: Any) -> tuple[str, str, str, str] | None:
        if not isinstance(content, str):
            return None
        assistant_match = _BG_TASK_ASSISTANT_RE.match(content)
        if assistant_match:
            return (
                "assistant",
                assistant_match[1],
                assistant_match[2],
                (assistant_match[5] or "").strip(),
            )
        continuation_match = _BG_TASK_CONTINUATION_RE.match(content)
        if continuation_match:
            body = (continuation_match[5] or "").strip()
            tail = "请基于以上结果继续处理后续步骤。如果所有工作已完成，请总结。"
            if body.endswith(tail):
                body = body[: -len(tail)].rstrip()
            return (
                "continuation",
                continuation_match[3],
                continuation_match[1],
                body,
            )
        return None

    @staticmethod
    def _timestamp_sort_key(raw_timestamp: Any) -> tuple[int, float, str]:
        if raw_timestamp is None:
            return (1, 0.0, "")
        if isinstance(raw_timestamp, (int, float)):
            numeric = float(raw_timestamp)
            return (0, numeric / 1000 if abs(numeric) >= 1e12 else numeric, "")
        if not isinstance(raw_timestamp, str):
            return (1, 0.0, "")

        trimmed = raw_timestamp.strip()
        if not trimmed:
            return (1, 0.0, "")

        if re.fullmatch(r"\d+(?:\.\d+)?", trimmed):
            numeric = float(trimmed)
            return (0, numeric / 1000 if abs(numeric) >= 1e12 else numeric, "")

        try:
            parsed = datetime.fromisoformat(trimmed.replace("Z", "+00:00"))
        except ValueError:
            return (1, 0.0, trimmed)

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=_LOCAL_TIMEZONE)
        else:
            parsed = parsed.astimezone(timezone.utc)
        return (0, parsed.timestamp(), "")

    def _canonicalize_conversation_rows(
        self,
        msg_rows: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], bool]:
        if not msg_rows:
            return msg_rows, False

        canonical = sorted(
            (dict(row) for row in msg_rows),
            key=lambda row: (
                *self._timestamp_sort_key(row.get("timestamp")),
                row["seq"],
                row["id"],
            ),
        )
        has_duplicate_seq = len({row["seq"] for row in canonical}) != len(canonical)
        order_changed = [row["id"] for row in canonical] != [row["id"] for row in msg_rows]
        needs_resequence = has_duplicate_seq or order_changed
        if not needs_resequence:
            return [dict(row) for row in msg_rows], False

        for seq, row in enumerate(canonical):
            row["seq"] = seq
        return canonical, True

    def _load_conversation_rows(self, session_id: int, conversation_id: str) -> list[dict[str, Any]]:
        return self._db.fetchall(
            """
            SELECT id, seq, role, content, tool_calls, tool_call_id, name,
                   reasoning_content, timestamp, conversation_id, trace_id,
                   from_agent_id, mentioned_agent_ids
              FROM session_messages
             WHERE session_id = ? AND conversation_id = ?
             ORDER BY seq, id
            """,
            (session_id, conversation_id),
        )

    def _message_row_to_payload(self, row: Any, *, session_key: str = "") -> dict[str, Any]:
        msg: dict[str, Any] = {"role": row["role"]}
        msg["content"] = self._decode_message_content(row["content"])
        if row["tool_calls"]:
            try:
                msg["tool_calls"] = json.loads(row["tool_calls"])
            except json.JSONDecodeError:
                pass
        if row["tool_call_id"]:
            msg["tool_call_id"] = row["tool_call_id"]
        if row["name"]:
            msg["name"] = row["name"]
        if row["reasoning_content"]:
            msg["reasoning_content"] = row["reasoning_content"]
        if row["timestamp"]:
            msg["timestamp"] = row["timestamp"]
        trace_id = row["trace_id"] or ""
        conversation_id = row["conversation_id"] or ""
        from_agent_id = self._normalize_agent_id(row["from_agent_id"]) if "from_agent_id" in row.keys() else ""
        if not from_agent_id:
            if row["role"] == "user":
                from_agent_id = "user"
            elif row["role"] == "assistant":
                from_agent_id = self._default_responder_agent_id()
        mentioned_agent_ids = (
            self._decode_agent_list(row["mentioned_agent_ids"])
            if "mentioned_agent_ids" in row.keys()
            else []
        )
        if from_agent_id:
            msg["from_agent_id"] = from_agent_id
        msg["mentioned_agent_ids"] = mentioned_agent_ids
        msg["trace_id"] = trace_id
        metadata: dict[str, Any] = {
            "conversation_id": conversation_id,
            "trace_id": trace_id,
            "from_agent_id": from_agent_id,
            "mentioned_agent_ids": mentioned_agent_ids,
        }
        if session_key:
            metadata["session_key"] = session_key
        msg["metadata"] = metadata
        return msg

    def _repair_conversation_artifacts(
        self,
        session_id: int,
        conversation_id: str,
        msg_rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not self._use_db or not msg_rows:
            return msg_rows

        working, needs_resequence = self._canonicalize_conversation_rows(msg_rows)
        delete_ids: list[int] = []
        blank_assistant_ids: list[int] = []

        seen_tool_call_assistants: set[tuple[str, str, str, str]] = set()
        seen_tool_results: set[tuple[str, str, str, str]] = set()
        seen_bg_messages: set[tuple[str, str, str, str]] = set()

        idx = 0
        while idx < len(working):
            current = working[idx]
            bg_signature = self._background_task_signature(current["content"])
            if bg_signature:
                if bg_signature in seen_bg_messages:
                    delete_ids.append(current["id"])
                    del working[idx]
                    continue
                seen_bg_messages.add(bg_signature)
            if current["role"] == "assistant" and current.get("tool_calls"):
                signature = (
                    current["tool_calls"] or "",
                    current["content"] or "",
                    current.get("reasoning_content") or "",
                    current["timestamp"] or "",
                )
                if signature in seen_tool_call_assistants:
                    delete_ids.append(current["id"])
                    del working[idx]
                    continue
                seen_tool_call_assistants.add(signature)
            elif current["role"] == "tool" and current.get("tool_call_id"):
                signature = (
                    current["tool_call_id"] or "",
                    current.get("name") or "",
                    current["content"] or "",
                    current["timestamp"] or "",
                )
                if signature in seen_tool_results:
                    delete_ids.append(current["id"])
                    del working[idx]
                    continue
                seen_tool_results.add(signature)
            idx += 1

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

        if not delete_ids and not blank_assistant_ids and not needs_resequence:
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
        if delete_ids or blank_assistant_ids:
            self._db.commit()

        refreshed = self._load_conversation_rows(session_id, conversation_id)
        canonical, needs_resequence = self._canonicalize_conversation_rows(refreshed)
        if not needs_resequence:
            return refreshed

        for row in canonical:
            self._db.execute(
                "UPDATE session_messages SET seq = ? WHERE id = ?",
                (row["seq"], row["id"]),
            )
        self._db.commit()
        return self._load_conversation_rows(session_id, conversation_id)

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

    @staticmethod
    def _normalize_token_stats(stats: dict[str, Any] | None) -> dict[str, int]:
        data = stats or {}
        return {
            "total_prompt_tokens": int(data.get("total_prompt_tokens", 0) or 0),
            "total_completion_tokens": int(data.get("total_completion_tokens", 0) or 0),
            "total_tokens": int(data.get("total_tokens", 0) or 0),
            "llm_calls": int(data.get("llm_calls", 0) or 0),
        }

    def _resolve_session_token_stats(
        self,
        session_key: str,
        conversation_id: str,
        fallback: dict[str, Any] | None,
    ) -> dict[str, int]:
        fallback_stats = self._normalize_token_stats(fallback)
        if not self._use_db:
            return fallback_stats

        try:
            row = self._db.fetchone(
                """
                SELECT COALESCE(SUM(prompt_tokens), 0) AS total_prompt_tokens,
                       COALESCE(SUM(completion_tokens), 0) AS total_completion_tokens,
                       COALESCE(SUM(total_tokens), 0) AS total_tokens,
                       COUNT(*) AS llm_calls
                  FROM token_usage
                 WHERE session_key = ? AND conversation_id = ?
                """,
                (session_key, conversation_id),
            )
        except Exception:
            return fallback_stats

        live_stats = self._normalize_token_stats(dict(row) if row else None)
        if live_stats["llm_calls"] == 0 and fallback_stats["llm_calls"] > 0:
            return fallback_stats
        return live_stats

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
                default_responder_agent_id = self._default_responder_agent_id(meta)
                participants = self._normalize_agent_ids(
                    meta.get("participants"),
                    fallback=[default_responder_agent_id],
                )
                active_conversation_id = self._resolve_active_conversation_id(r["id"], meta)
                sessions.append({
                    "key": key,
                    "title": meta.get("title") or "",
                    "scene": self._derive_scene(key),
                    "created_at": r["created_at"] or "",
                    "updated_at": r["updated_at"] or "",
                    "conversation_id": active_conversation_id,
                    "participants": participants,
                    "default_responder_agent_id": default_responder_agent_id,
                    "token_stats": self._resolve_session_token_stats(key, active_conversation_id, ts),
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
            title = ""
            default_responder_agent_id = self._default_responder_agent_id()
            participants = [default_responder_agent_id]
            msg_count = max(0, len(lines) - 1)
            if first_line:
                try:
                    parsed = json.loads(first_line)
                    if parsed.get("_type") == "metadata":
                        key = parsed.get("key", key)
                        title = parsed.get("title") or ""
                        created_at = parsed.get("created_at", "")
                        updated_at = parsed.get("updated_at", "")
                        token_stats = parsed.get("token_stats", token_stats)
                        conversation_id = parsed.get("conversation_id") or self._extract_conversation_id(parsed.get("metadata"))
                        default_responder_agent_id = self._default_responder_agent_id(parsed.get("metadata"))
                        participants = self._normalize_agent_ids(
                            parsed.get("participants") or (parsed.get("metadata") or {}).get("participants"),
                            fallback=[default_responder_agent_id],
                        )
                except json.JSONDecodeError:
                    pass
            sessions.append({
                "key": key,
                "title": title,
                "scene": self._derive_scene(key),
                "created_at": created_at,
                "updated_at": updated_at,
                "conversation_id": conversation_id,
                "participants": participants,
                "default_responder_agent_id": default_responder_agent_id,
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
                    preview_text = self._preview_text(message_row["content"])
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
            preview_text = self._preview_text(message.get("content"))
            if preview_text:
                preview = preview_text[:60]
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
                """
                SELECT id, seq, role, content, tool_calls, tool_call_id, name,
                       reasoning_content, timestamp, conversation_id, trace_id,
                       from_agent_id, mentioned_agent_ids
                  FROM session_messages
                 WHERE session_id = ? AND conversation_id = ?
                 ORDER BY seq, id
                """,
                (row["id"], resolved_conversation_id),
            )
            msg_rows = self._repair_conversation_artifacts(
                row["id"],
                resolved_conversation_id,
                msg_rows,
            )
            return [self._message_row_to_payload(mr) for mr in msg_rows]

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

    def get_messages_by_trace_id(self, trace_id: str) -> list[dict]:
        """Return all persisted messages bound to one trace_id across sessions."""
        if not trace_id:
            return []
        if not self._use_db:
            return []

        rows = self._db.fetchall(
            """
            SELECT s.key AS session_key, m.id, m.seq, m.role, m.content,
                   m.tool_calls, m.tool_call_id, m.name, m.reasoning_content,
                   m.timestamp, m.conversation_id, m.trace_id,
                   m.from_agent_id, m.mentioned_agent_ids
              FROM session_messages m
              JOIN sessions s ON s.id = m.session_id
             WHERE m.trace_id = ?
             ORDER BY CASE WHEN m.timestamp IS NULL OR m.timestamp = '' THEN 1 ELSE 0 END,
                      m.timestamp ASC,
                      m.seq ASC,
                      m.id ASC
            """,
            (trace_id,),
        )
        return [
            self._message_row_to_payload(row, session_key=row["session_key"] or "")
            for row in rows
        ]

    def get_context_preview(
        self,
        session_key: str,
        *,
        full: bool = False,
        reveal: bool = False,
    ) -> dict[str, Any]:
        if not self._agent:
            raise RuntimeError("Context preview is unavailable while the gateway is offline")
        if not self._session_exists(session_key):
            raise KeyError(session_key)

        sessions = getattr(self._agent, "sessions", None)
        if sessions is None or not hasattr(sessions, "get_or_create"):
            raise RuntimeError("Agent session manager is unavailable")

        session = sessions.get_or_create(session_key)
        return build_context_preview(
            loop=self._agent,
            session=session,
            session_key=session_key,
            full=full,
            reveal=reveal,
        )

    def create_session(
        self,
        user_id: str,
        title: str = "",
        participants: list[str] | None = None,
    ) -> dict[str, Any]:
        sid = uuid.uuid4().hex[:8]
        conversation_id = f"conv_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        session_title = title or f"Session {sid}"
        session_key = f"console:{sid}"
        default_responder_agent_id = self._default_responder_agent_id()
        normalized_participants = self._normalize_agent_ids(
            participants,
            fallback=[default_responder_agent_id],
        )

        if self._use_db:
            meta = json.dumps(
                {
                    "title": session_title,
                    "user": user_id,
                    "conversation_id": conversation_id,
                    "participants": normalized_participants,
                    "default_responder_agent_id": default_responder_agent_id,
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
                "participants": normalized_participants,
                "default_responder_agent_id": default_responder_agent_id,
                "token_stats": {
                    "total_prompt_tokens": 0,
                    "total_completion_tokens": 0,
                    "total_tokens": 0,
                    "llm_calls": 0,
                },
            }, ensure_ascii=False)
            session_file.write_text(metadata_line + "\n", "utf-8")
        return {
            "session_id": sid,
            "title": session_title,
            "conversation_id": conversation_id,
            "participants": normalized_participants,
            "default_responder_agent_id": default_responder_agent_id,
        }

    def update_session(
        self,
        session_id: str,
        *,
        participants: list[str] | None = None,
    ) -> dict[str, Any]:
        session_key = f"console:{session_id}"
        default_responder_agent_id = self._default_responder_agent_id()
        normalized_participants = self._normalize_agent_ids(
            participants,
            fallback=[default_responder_agent_id],
        )
        if not self._use_db:
            raise KeyError(session_id)

        row = self._db.fetchone(
            "SELECT metadata FROM sessions WHERE key = ?",
            (session_key,),
        )
        if not row:
            raise KeyError(session_id)
        meta: dict[str, Any] = {}
        if row["metadata"]:
            try:
                meta = json.loads(row["metadata"])
            except json.JSONDecodeError:
                meta = {}
        meta["participants"] = normalized_participants
        meta["default_responder_agent_id"] = default_responder_agent_id
        self._db.execute(
            "UPDATE sessions SET metadata = ?, updated_at = ? WHERE key = ?",
            (
                json.dumps(meta, ensure_ascii=False),
                datetime.now(timezone.utc).isoformat(),
                session_key,
            ),
        )
        self._db.commit()
        return {
            "ok": True,
            "session_id": session_id,
            "participants": normalized_participants,
            "default_responder_agent_id": default_responder_agent_id,
        }

    def record_console_message(
        self,
        session_id: str,
        *,
        role: str,
        content: str,
        from_agent_id: str = "",
        mentioned_agent_ids: list[str] | None = None,
        trace_id: str = "",
    ) -> dict[str, Any]:
        if not self._use_db:
            raise RuntimeError("Console message recording requires SQLite storage")
        session_key = f"console:{session_id}"
        row = self._db.fetchone(
            "SELECT id, metadata FROM sessions WHERE key = ?",
            (session_key,),
        )
        if not row:
            raise KeyError(session_id)

        meta: dict[str, Any] = {}
        if row["metadata"]:
            try:
                meta = json.loads(row["metadata"])
            except json.JSONDecodeError:
                meta = {}
        conversation_id = self._resolve_active_conversation_id(row["id"], meta)
        seq_row = self._db.fetchone(
            "SELECT COALESCE(MAX(seq), -1) + 1 AS seq FROM session_messages WHERE session_id = ? AND conversation_id = ?",
            (row["id"], conversation_id),
        )
        seq = int(seq_row["seq"] if seq_row else 0)
        turn_row = self._db.fetchone(
            "SELECT COUNT(*) AS count FROM session_messages WHERE session_id = ? AND conversation_id = ? AND role = 'user'",
            (row["id"], conversation_id),
        )
        turn_seq = int(turn_row["count"] if turn_row else 0)
        now = datetime.now(timezone.utc).isoformat()
        normalized_from_agent_id = self._normalize_agent_id(from_agent_id)
        if not normalized_from_agent_id:
            normalized_from_agent_id = "user" if role == "user" else self._default_responder_agent_id(meta)
        normalized_mentions = self._normalize_agent_ids(mentioned_agent_ids)
        self._db.execute(
            """
            INSERT INTO session_messages
                (session_id, seq, conversation_id, trace_id, from_agent_id, mentioned_agent_ids,
                 role, content, tool_calls, tool_call_id, name, reasoning_content, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["id"],
                seq,
                conversation_id,
                trace_id,
                normalized_from_agent_id,
                json.dumps(normalized_mentions, ensure_ascii=False),
                role,
                content,
                None,
                None,
                None,
                None,
                now,
            ),
        )
        self._db.execute(
            "UPDATE sessions SET updated_at = ? WHERE key = ?",
            (now, session_key),
        )
        self._db.commit()
        return {
            "session_key": session_key,
            "conversation_id": conversation_id,
            "seq": seq,
            "turn_seq": turn_seq if role == "user" else None,
            "timestamp": now,
        }

    def next_console_turn_ref(self, session_id: str) -> dict[str, Any]:
        session_key = f"console:{session_id}"
        if not self._use_db:
            return {
                "session_key": session_key,
                "conversation_id": "",
                "turn_seq": None,
            }

        row = self._db.fetchone(
            "SELECT id, metadata FROM sessions WHERE key = ?",
            (session_key,),
        )
        if not row:
            raise KeyError(session_id)

        meta: dict[str, Any] = {}
        if row["metadata"]:
            try:
                meta = json.loads(row["metadata"])
            except json.JSONDecodeError:
                meta = {}
        conversation_id = self._resolve_active_conversation_id(row["id"], meta)
        turn_row = self._db.fetchone(
            """
            SELECT COUNT(*) AS count
              FROM session_messages
             WHERE session_id = ? AND conversation_id = ? AND role = 'user'
            """,
            (row["id"], conversation_id),
        )
        return {
            "session_key": session_key,
            "conversation_id": conversation_id,
            "turn_seq": int(turn_row["count"] if turn_row else 0),
        }

    def get_session_default_responder_agent_id(self, session_id: str) -> str:
        session_key = f"console:{session_id}"
        if self._use_db:
            row = self._db.fetchone(
                "SELECT metadata FROM sessions WHERE key = ?",
                (session_key,),
            )
            if row and row["metadata"]:
                try:
                    meta = json.loads(row["metadata"])
                except json.JSONDecodeError:
                    meta = {}
                return self._default_responder_agent_id(meta)
        return self._default_responder_agent_id()

    async def send_message(
        self,
        session_id: str,
        message: str,
        user_id: str,
        media: list[str] | None = None,
        on_progress: Callable[..., Awaitable[None]] | None = None,
        on_stream: Callable[..., Awaitable[None]] | None = None,
        on_stream_end: Callable[..., Awaitable[None]] | None = None,
        skill_names: list[str] | None = None,
        skill_contents: dict[str, str] | None = None,
    ) -> str:
        session_key = f"console:{session_id}"
        mentioned_agent_ids = self._parse_agent_mentions(message)
        if mentioned_agent_ids:
            self._merge_session_participants(session_key, mentioned_agent_ids)
        missing = object()
        previous_agent_context = getattr(self._agent, "_current_chat_agent_context", missing)
        previous_skill_names = getattr(self._agent, "_ava_forced_skill_names", missing)
        previous_skill_contents = getattr(self._agent, "_ava_forced_skill_contents", missing)
        if self._agent is not None:
            setattr(
                self._agent,
                "_current_chat_agent_context",
                {
                    "from_agent_id": "user",
                    "mentioned_agent_ids": mentioned_agent_ids,
                    "default_responder_agent_id": self._default_responder_agent_id(),
                },
            )
            if skill_names is not None:
                setattr(self._agent, "_ava_forced_skill_names", list(skill_names))
            if skill_contents is not None:
                setattr(self._agent, "_ava_forced_skill_contents", dict(skill_contents))
        process_task = asyncio.create_task(
            self._agent.process_direct(
                content=message,
                session_key=session_key,
                channel="console",
                chat_id=user_id,
                on_progress=on_progress,
                on_stream=on_stream,
                on_stream_end=on_stream_end,
                media=media,
            )
        )
        active_tasks = getattr(self._agent, "_active_tasks", None)
        tracked = False
        if isinstance(active_tasks, dict):
            active_tasks.setdefault(session_key, []).append(process_task)
            tracked = True
        try:
            response = await process_task
        finally:
            if self._agent is not None:
                if previous_agent_context is missing:
                    try:
                        delattr(self._agent, "_current_chat_agent_context")
                    except AttributeError:
                        pass
                else:
                    setattr(self._agent, "_current_chat_agent_context", previous_agent_context)
                if previous_skill_names is missing:
                    try:
                        delattr(self._agent, "_ava_forced_skill_names")
                    except AttributeError:
                        pass
                else:
                    setattr(self._agent, "_ava_forced_skill_names", previous_skill_names)
                if previous_skill_contents is missing:
                    try:
                        delattr(self._agent, "_ava_forced_skill_contents")
                    except AttributeError:
                        pass
                else:
                    setattr(self._agent, "_ava_forced_skill_contents", previous_skill_contents)
            if tracked and isinstance(active_tasks, dict):
                tasks = active_tasks.get(session_key, [])
                if process_task in tasks:
                    tasks.remove(process_task)
                if not tasks:
                    active_tasks.pop(session_key, None)
        return self._normalize_direct_response_content(response)

    def _merge_session_participants(self, session_key: str, agent_ids: list[str]) -> None:
        if not self._use_db or not agent_ids:
            return
        row = self._db.fetchone(
            "SELECT metadata FROM sessions WHERE key = ?",
            (session_key,),
        )
        if not row:
            return
        meta: dict[str, Any] = {}
        if row["metadata"]:
            try:
                meta = json.loads(row["metadata"])
            except json.JSONDecodeError:
                meta = {}
        default_responder_agent_id = self._default_responder_agent_id(meta)
        participants = self._normalize_agent_ids(
            meta.get("participants"),
            fallback=[default_responder_agent_id],
        )
        changed = False
        for agent_id in agent_ids:
            if agent_id not in participants:
                participants.append(agent_id)
                changed = True
        if not changed:
            return
        meta["participants"] = participants
        meta["default_responder_agent_id"] = default_responder_agent_id
        self._db.execute(
            "UPDATE sessions SET metadata = ?, updated_at = ? WHERE key = ?",
            (
                json.dumps(meta, ensure_ascii=False),
                datetime.now(timezone.utc).isoformat(),
                session_key,
            ),
        )
        self._db.commit()

    def _default_responder_agent_id(self, metadata: dict[str, Any] | None = None) -> str:
        if isinstance(metadata, dict):
            value = metadata.get("default_responder_agent_id") or metadata.get("defaultResponderAgentId")
            normalized = self._normalize_agent_id(value)
            if normalized and normalized != "user":
                return normalized

        for path in (
            self._sessions_dir.parent / "console" / "console-config.json",
            self._sessions_dir.parent / "config.json",
        ):
            if not path.exists():
                continue
            try:
                parsed = json.loads(path.read_text("utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(parsed, dict):
                continue
            gateway = parsed.get("gateway") if isinstance(parsed.get("gateway"), dict) else {}
            console = gateway.get("console") if isinstance(gateway.get("console"), dict) else {}
            value = console.get("default_responder_agent_id") or console.get("defaultResponderAgentId")
            normalized = self._normalize_agent_id(value)
            if normalized and normalized != "user":
                return normalized
        return "nanobot"

    async def stop_session(self, session_id: str) -> dict[str, Any]:
        session_key = f"console:{session_id}"
        total = 0
        cancel_active = getattr(self._agent, "_cancel_active_tasks", None)
        if callable(cancel_active):
            total += int(await cancel_active(session_key))
        else:
            active_tasks = getattr(self._agent, "_active_tasks", None)
            if isinstance(active_tasks, dict):
                tasks = active_tasks.pop(session_key, [])
                for task in tasks:
                    if not task.done():
                        task.cancel()
                        total += 1
                    try:
                        await task
                    except (asyncio.CancelledError, Exception):
                        pass

        bg_store = getattr(self._agent, "bg_tasks", None)
        cancel_bg = getattr(bg_store, "cancel_by_session", None)
        if callable(cancel_bg):
            total += int(await cancel_bg(session_key))

        return {
            "ok": True,
            "stopped": total,
            "message": f"Stopped {total} task(s)." if total else "No active task to stop.",
        }

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
                """SELECT role, content, timestamp, trace_id FROM session_messages
                   WHERE session_id = ? AND conversation_id = ? AND role IN ('user', 'assistant') AND content IS NOT NULL AND content != ''
                   ORDER BY seq""",
                (row["id"], active_conversation_id),
            )
            return [
                {
                    "role": r["role"],
                    "content": r["content"],
                    "timestamp": r["timestamp"] or "",
                    "trace_id": r["trace_id"] or "",
                }
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

    @staticmethod
    def _estimate_context_tokens(value: Any) -> int:
        text = ChatService._message_text(value) if not isinstance(value, str) else value
        if not text:
            return 0
        return max(1, (len(text) + 3) // 4)

    def _context_model_limit(self) -> int:
        config = getattr(self._agent, "config", None)
        for name in ("model_context_limit", "context_limit", "max_context_tokens"):
            value = getattr(config, name, None) if config is not None else None
            if isinstance(value, int) and value > 0:
                return value
        return _DEFAULT_CONTEXT_MODEL_LIMIT

    def _active_console_context_rows(self, session_id: str) -> tuple[str, int | None, str, list[dict[str, Any]]]:
        session_key = f"console:{session_id}"
        if not self._use_db:
            rows = [
                {
                    "role": item.get("role", ""),
                    "content": item.get("content", ""),
                    "timestamp": item.get("timestamp", ""),
                    "conversation_id": "",
                }
                for item in self.get_history(session_id)
            ]
            return session_key, None, "", rows

        row = self._db.fetchone(
            "SELECT id, metadata FROM sessions WHERE key = ?",
            (session_key,),
        )
        if not row:
            raise KeyError(session_id)
        meta: dict[str, Any] = {}
        if row["metadata"]:
            try:
                meta = json.loads(row["metadata"])
            except json.JSONDecodeError:
                meta = {}
        conversation_id = self._resolve_active_conversation_id(row["id"], meta)
        rows = self._db.fetchall(
            """SELECT role, content, timestamp, conversation_id
                 FROM session_messages
                WHERE session_id = ? AND conversation_id = ? AND role IN ('user', 'assistant') AND content IS NOT NULL AND content != ''
                ORDER BY seq, id""",
            (row["id"], conversation_id),
        )
        return session_key, int(row["id"]), conversation_id, [dict(item) for item in rows]

    def get_context_size(self, session_id: str) -> dict[str, Any]:
        """Deprecated: prefers context-preview totals, falls back to DB estimation."""
        session_key = f"console:{session_id}"
        try:
            preview = self.get_context_preview(session_key)
            totals = preview.get("totals", {})
            return {
                "used_tokens": totals.get("request_total_tokens", 0),
                "model_limit": totals.get("ctx_budget", _DEFAULT_CONTEXT_MODEL_LIMIT),
                "breakdown": {
                    "messages": totals.get("history_tokens", 0),
                    "system": totals.get("system_tokens", 0),
                    "runtime": totals.get("runtime_tokens", 0),
                    "tools": totals.get("tool_tokens", 0),
                },
                "compression_preview": "",
                "before_after_diff": None,
            }
        except (KeyError, RuntimeError):
            return self._get_context_size_legacy(session_id)

    def _get_context_size_legacy(self, session_id: str) -> dict[str, Any]:
        """Original DB-based estimation, kept as fallback for compress_context."""
        session_key, _numeric_session_id, conversation_id, rows = self._active_console_context_rows(session_id)
        messages_tokens = sum(self._estimate_context_tokens(row.get("content")) for row in rows)
        system_tokens = 0
        recorded_prompt_tokens = 0
        if self._use_db:
            token_row = self._db.fetchone(
                """SELECT COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
                          COALESCE(MAX(system_prompt_preview), '') AS system_prompt_preview
                     FROM token_usage
                    WHERE session_key = ? AND conversation_id = ?""",
                (session_key, conversation_id),
            )
            if token_row:
                recorded_prompt_tokens = int(token_row["prompt_tokens"] or 0)
                system_tokens = self._estimate_context_tokens(token_row["system_prompt_preview"] or "")

        breakdown = {
            "messages": messages_tokens,
            "system": system_tokens,
            "persona": 0,
            "recorded_prompt": recorded_prompt_tokens,
        }
        used_tokens = max(recorded_prompt_tokens, messages_tokens + system_tokens)
        return {
            "used_tokens": used_tokens,
            "model_limit": self._context_model_limit(),
            "breakdown": breakdown,
            "conversation_id": conversation_id,
            "compression_preview": "",
            "before_after_diff": None,
        }

    def compress_context(self, session_id: str, *, keep_recent: int = 6) -> dict[str, Any]:
        session_key, numeric_session_id, conversation_id, rows = self._active_console_context_rows(session_id)
        before = self.get_context_size(session_id)["used_tokens"]
        keep_recent = max(2, keep_recent)
        older = rows[:-keep_recent] if len(rows) > keep_recent else []
        recent = rows[-keep_recent:] if older else rows
        summary_lines = []
        for row in older:
            text = self._preview_text(row.get("content"))[:120]
            if text:
                summary_lines.append(f"- {row.get('role', 'message')}: {text}")
        summary_text = "已压缩早期上下文：" + ("\n" + "\n".join(summary_lines) if summary_lines else "无早期消息需要压缩。")
        after_messages = [{"role": "system", "content": summary_text}, *recent]
        after_tokens = sum(self._estimate_context_tokens(item.get("content")) for item in after_messages)
        before_after_diff = {
            "before": rows,
            "after": after_messages,
            "summary_text": summary_text,
            "kept_messages": recent,
        }

        if self._use_db and numeric_session_id is not None:
            compressed_at = datetime.now(timezone.utc).isoformat()
            self._db.execute(
                """INSERT INTO session_compressions
                   (session_id, compressed_at, before_tokens, after_tokens, summary_text, before_after_diff)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    numeric_session_id,
                    compressed_at,
                    before,
                    after_tokens,
                    summary_text,
                    json.dumps(before_after_diff, ensure_ascii=False),
                ),
            )
            self._db.commit()

        return {
            "ok": True,
            "session_key": session_key,
            "conversation_id": conversation_id,
            "before_tokens": before,
            "after_tokens": after_tokens,
            "used_tokens": after_tokens,
            "model_limit": self._context_model_limit(),
            "breakdown": {
                "messages": after_tokens,
                "system": self._estimate_context_tokens(summary_text),
                "persona": 0,
                "recorded_prompt": 0,
            },
            "compression_preview": summary_text,
            "before_after_diff": before_after_diff,
            "history": self.list_context_compressions(session_id),
        }

    def list_context_compressions(self, session_id: str) -> list[dict[str, Any]]:
        if not self._use_db:
            return []
        session_key = f"console:{session_id}"
        row = self._db.fetchone("SELECT id FROM sessions WHERE key = ?", (session_key,))
        if not row:
            return []
        rows = self._db.fetchall(
            """SELECT compressed_at, before_tokens, after_tokens, summary_text, before_after_diff
                 FROM session_compressions
                WHERE session_id = ?
                ORDER BY compressed_at DESC""",
            (row["id"],),
        )
        result = []
        for item in rows:
            try:
                diff = json.loads(item["before_after_diff"] or "{}")
            except json.JSONDecodeError:
                diff = {}
            result.append({
                "compressed_at": item["compressed_at"],
                "before_tokens": item["before_tokens"],
                "after_tokens": item["after_tokens"],
                "summary_text": item["summary_text"],
                "before_after_diff": diff,
            })
        return result

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
