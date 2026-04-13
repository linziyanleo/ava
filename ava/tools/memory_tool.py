"""Memory tool for agent-driven categorized memory operations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from nanobot.agent.tools.base import Tool

if TYPE_CHECKING:
    from nanobot.agent.categorized_memory import CategorizedMemoryStore

class MemoryTool(Tool):
    """Tool for the agent to recall, remember, and manage categorized memory."""

    def __init__(self, store: CategorizedMemoryStore, db: Any | None = None) -> None:
        self._store = store
        self._channel: str = ""
        self._chat_id: str = ""
        self._db = db

    def set_context(self, channel: str, chat_id: str) -> None:
        """Set the current conversation context for identity resolution."""
        self._channel = channel
        self._chat_id = chat_id

    @property
    def name(self) -> str:
        return "memory"

    @property
    def description(self) -> str:
        return (
            "Manage categorized memory. Actions:\n"
            "- recall: Retrieve memory for a person or the current user\n"
            "- remember: Store a memory note for the current person\n"
            "- list_persons: List all known persons and their IDs\n"
            "- map_identity: Link the current channel:id to a person name\n"
            "- search_history: Search history logs by keyword and/or time range (since/until)"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["recall", "remember", "list_persons", "map_identity", "search_history"],
                    "description": "The memory action to perform",
                },
                "content": {
                    "type": "string",
                    "description": "Content to store (for 'remember') or search keyword (for 'search_history', optional when since/until is set)",
                },
                "person": {
                    "type": "string",
                    "description": "Person name to target (optional, defaults to current user)",
                },
                "scope": {
                    "type": "string",
                    "enum": ["person", "source"],
                    "description": "Memory scope: 'person' (cross-channel) or 'source' (channel-specific). Default: person",
                },
                "display_name": {
                    "type": "string",
                    "description": "Display name for the person (for 'map_identity')",
                },
                "since": {
                    "type": "string",
                    "description": "Start date/datetime filter in ISO format, e.g. '2026-02-25' (only for search_history)",
                },
                "until": {
                    "type": "string",
                    "description": "End date/datetime filter in ISO format, e.g. '2026-02-26' (only for search_history)",
                },
                "channel": {
                    "type": "string",
                    "description": "Filter by channel, e.g. 'telegram', 'cli', 'dingtalk' (only for search_history, default: all)",
                },
            },
            "required": ["action"],
        }

    async def execute(self, action: str, **kwargs: Any) -> str:
        if action == "recall":
            return self._recall(**kwargs)
        elif action == "remember":
            return self._remember(**kwargs)
        elif action == "list_persons":
            return self._list_persons()
        elif action == "map_identity":
            return self._map_identity(**kwargs)
        elif action == "search_history":
            return self._search_history(**kwargs)
        else:
            return f"Unknown action: {action}. Use: recall, remember, list_persons, map_identity, search_history"

    def _recall(self, person: str | None = None, scope: str = "person", **_: Any) -> str:
        """Retrieve memory for a person or the current user."""
        if person:
            target = person
        else:
            target = self._store.resolve_person(self._channel, self._chat_id)

        if not target:
            return "No person identity mapped for the current session. Use map_identity first, or specify a person name."

        if scope == "source":
            mem = self._store.get_source_memory(self._channel, self._chat_id)
            label = f"Source memory ({self._channel}:{self._chat_id})"
        else:
            mem = self._store.get_person_memory(target)
            label = f"Person memory ({target})"

        if not mem:
            return f"{label}: (empty)"
        return f"{label}:\n{mem}"

    def _remember(self, content: str | None = None, scope: str = "person", person: str | None = None, **_: Any) -> str:
        """Store a memory note."""
        if not content:
            return "Error: 'content' is required for remember action."

        if person:
            target = person
        else:
            target = self._store.resolve_person(self._channel, self._chat_id)

        if not target:
            return "No person identity mapped for the current session. Use map_identity first, or specify a person name."

        if scope == "source":
            existing = self._store.get_source_memory(self._channel, self._chat_id)
            updated = f"{existing}\n{content}".strip() if existing else content
            self._store.write_source_note(self._channel, self._chat_id, updated)
            return f"Source memory updated for {target} ({self._channel}:{self._chat_id})"
        else:
            existing = self._store.get_person_memory(target)
            updated = f"{existing}\n{content}".strip() if existing else content
            self._store.write_person_memory(target, updated)
            return f"Person memory updated for {target}"

    def _list_persons(self, **_: Any) -> str:
        """List all known persons."""
        persons = self._store.list_persons()
        if not persons:
            return "No persons mapped yet. Use map_identity to add the first one."

        lines = []
        for p in persons:
            ids = ", ".join(f"{e['channel']}:{e['id']}" for e in p["ids"])
            lines.append(f"- {p['display_name']} ({p['name']}): {ids}")
        return "Known persons:\n" + "\n".join(lines)

    def _map_identity(self, person: str | None = None, display_name: str | None = None, **_: Any) -> str:
        """Map the current channel:id to a person."""
        if not person:
            return "Error: 'person' (person name key) is required for map_identity."
        if not self._channel or not self._chat_id:
            return "Error: No channel/chat_id context available."

        self._store.add_identity(person, self._channel, self._chat_id, display_name)
        label = display_name or person
        return f"Mapped {self._channel}:{self._chat_id} -> {label} ({person})"

    def _search_history(
        self,
        content: str | None = None,
        person: str | None = None,
        since: str | None = None,
        until: str | None = None,
        channel: str | None = None,
        **_: Any,
    ) -> str:
        """Search history logs, with automatic fallback to raw session files."""
        has_time_filter = bool(since or until)
        has_advanced_filter = has_time_filter or bool(channel)

        if not content and not has_advanced_filter:
            return "Error: 'content' (search query) or time range (since/until) is required for search_history."

        if person:
            target = person
        else:
            target = self._store.resolve_person(self._channel, self._chat_id)

        if not has_advanced_filter and content:
            memory_dir = self._store._workspace / "memory"
            matches: list[str] = []

            global_history = memory_dir / "history.jsonl"
            if global_history.exists():
                matches.extend(self._search_history_jsonl(global_history, content.lower()))

            if target:
                person_history = memory_dir / "persons" / target / "history.jsonl"
                if person_history.exists():
                    matches.extend(self._search_history_jsonl(person_history, content.lower()))

            if matches:
                if len(matches) > 50:
                    matches = matches[:50]
                    matches.append("... (truncated, 50+ matches)")
                return f"Search results for '{content}':\n" + "\n".join(matches)

        session_results = self._search_sessions(content, target, since, until, channel)
        if session_results:
            label_parts = []
            if content:
                label_parts.append(f"'{content}'")
            meta_parts = []
            if since:
                meta_parts.append(f"since={since}")
            if until:
                meta_parts.append(f"until={until}")
            if channel:
                meta_parts.append(f"channel={channel}")
            if meta_parts:
                label_parts.append(", ".join(meta_parts))
            label = f"Search results ({', '.join(label_parts)}):" if label_parts else "Search results:"
            return f"{label}\n{session_results}"

        query_desc = f"'{content}'" if content else "given filters"
        return f"No matches found for {query_desc} in history."

    @staticmethod
    def _search_history_jsonl(jsonl_path: Path, query_lower: str) -> list[str]:
        """Search a JSONL history file, return matching formatted lines."""
        results: list[str] = []
        try:
            with open(jsonl_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    content = record.get("content", "")
                    if not isinstance(content, str):
                        continue
                    if query_lower not in content.lower():
                        continue
                    ts = record.get("timestamp", "")
                    results.append(f"[{ts}] {content}")
        except OSError:
            pass
        return results

    _SESSIONS_MAX_RESULTS = 20
    _SESSIONS_MAX_CHARS = 500

    @staticmethod
    def _normalize_datetime(value: str) -> str:
        """Normalize an ISO date or datetime string for comparison.

        '2026-02-25' → '2026-02-25T00:00:00'
        '2026-02-25T10:00:00' → '2026-02-25T10:00:00' (unchanged)
        """
        if "T" not in value:
            return value + "T00:00:00"
        return value

    def _search_sessions(
        self,
        query: str | None,
        person: str | None,
        since: str | None = None,
        until: str | None = None,
        channel: str | None = None,
    ) -> str:
        """Search session messages with current-session-first priority.

        Uses SQLite when available, falls back to JSONL file scanning.
        """
        if self._db is not None:
            return self._search_sessions_db(query, person, since, until, channel)

        sessions_dir = self._store._workspace / "sessions"
        if not sessions_dir.exists():
            return ""

        since_norm = self._normalize_datetime(since) if since else None
        until_norm = self._normalize_datetime(until) if until else None
        query_lower = query.lower() if query else None

        if person:
            session_files = self._get_session_files_for_person(person)
            if channel:
                prefix = f"{channel}_"
                session_files = [p for p in session_files if p.name.startswith(prefix)]
            return self._search_session_files(session_files, query_lower, since_norm, until_norm)

        has_advanced = bool(since or until or channel)
        current_session_file = None
        if self._channel and self._chat_id and not has_advanced:
            current = sessions_dir / f"{self._channel}_{self._chat_id}.jsonl"
            if current.exists():
                current_session_file = current

        if current_session_file:
            result = self._search_session_files([current_session_file], query_lower, since_norm, until_norm)
            if result:
                return result

        all_files = sorted(sessions_dir.glob("*.jsonl"))
        if channel:
            prefix = f"{channel}_"
            all_files = [p for p in all_files if p.name.startswith(prefix)]
        if current_session_file:
            all_files = [p for p in all_files if p != current_session_file]

        if not all_files:
            return ""

        return self._search_session_files(all_files, query_lower, since_norm, until_norm)

    def _search_sessions_db(
        self,
        query: str | None,
        person: str | None,
        since: str | None = None,
        until: str | None = None,
        channel: str | None = None,
    ) -> str:
        """Search session messages via SQLite."""
        conditions: list[str] = []
        params: list[Any] = []

        if query:
            conditions.append("sm.content LIKE ?")
            params.append(f"%{query}%")
        if since:
            conditions.append("sm.timestamp >= ?")
            params.append(self._normalize_datetime(since))
        if until:
            conditions.append("sm.timestamp < ?")
            params.append(self._normalize_datetime(until))
        if channel:
            conditions.append("s.key LIKE ?")
            params.append(f"{channel}:%")

        if person:
            session_keys = self._get_session_keys_for_person(person)
            if not session_keys:
                return ""
            placeholders = ",".join("?" for _ in session_keys)
            conditions.append(f"s.key IN ({placeholders})")
            params.extend(session_keys)
        elif self._channel and self._chat_id and not (since or until or channel):
            current_key = f"{self._channel}:{self._chat_id}"
            rows = self._db.fetchall(
                f"""SELECT sm.role, sm.content, sm.timestamp
                    FROM session_messages sm
                    JOIN sessions s ON s.id = sm.session_id
                    WHERE s.key = ? AND sm.content IS NOT NULL
                    {"AND sm.content LIKE ?" if query else ""}
                    ORDER BY sm.timestamp DESC LIMIT ?""",
                tuple([current_key] + ([f"%{query}%"] if query else []) + [self._SESSIONS_MAX_RESULTS]),
            )
            if rows:
                return self._format_db_matches(rows)

        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(self._SESSIONS_MAX_RESULTS)

        rows = self._db.fetchall(
            f"""SELECT sm.role, sm.content, sm.timestamp
                FROM session_messages sm
                JOIN sessions s ON s.id = sm.session_id
                {where}
                AND sm.content IS NOT NULL
                ORDER BY sm.timestamp DESC LIMIT ?""",
            tuple(params),
        )
        return self._format_db_matches(rows)

    def _format_db_matches(self, rows: list) -> str:
        if not rows:
            return ""
        matches = []
        for r in rows:
            content = r["content"] or ""
            if not isinstance(content, str):
                continue
            snippet = content[:self._SESSIONS_MAX_CHARS]
            if len(content) > self._SESSIONS_MAX_CHARS:
                snippet += "..."
            matches.append(f"[{r['timestamp'] or ''}] {r['role']}: {snippet}")
        if not matches:
            return ""
        result = "\n".join(matches)
        if len(matches) >= self._SESSIONS_MAX_RESULTS:
            result += f"\n... (showing first {self._SESSIONS_MAX_RESULTS} matches)"
        return result

    def _get_session_keys_for_person(self, person_name: str) -> list[str]:
        """Get session keys for a person from identity_map."""
        persons = self._store.resolver.list_persons()
        info = persons.get(person_name)
        if not info:
            return []
        keys: list[str] = []
        for entry in info.get("ids", []):
            ch = entry.get("channel", "")
            ids = entry.get("id", [])
            if isinstance(ids, str):
                ids = [ids]
            for cid in ids:
                keys.append(f"{ch}:{cid}")
        return keys

    def _search_session_files(
        self,
        session_files: list[Path],
        query_lower: str | None,
        since_norm: str | None,
        until_norm: str | None,
    ) -> str:
        """Search a list of session files and return formatted results."""
        if not session_files:
            return ""

        matches: list[str] = []
        for path in session_files:
            try:
                with open(path, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if data.get("_type") == "metadata":
                            continue

                        ts = data.get("timestamp", "")
                        if since_norm and ts < since_norm:
                            continue
                        if until_norm and ts >= until_norm:
                            continue

                        msg_content = data.get("content", "")
                        if not isinstance(msg_content, str):
                            continue
                        if query_lower and query_lower not in msg_content.lower():
                            continue

                        role = data.get("role", "?")
                        snippet = msg_content[:self._SESSIONS_MAX_CHARS]
                        if len(msg_content) > self._SESSIONS_MAX_CHARS:
                            snippet += "..."
                        matches.append(f"[{ts}] {role}: {snippet}")
                        if len(matches) >= self._SESSIONS_MAX_RESULTS:
                            break
            except OSError:
                continue
            if len(matches) >= self._SESSIONS_MAX_RESULTS:
                break

        if not matches:
            return ""

        result = "\n".join(matches)
        if len(matches) >= self._SESSIONS_MAX_RESULTS:
            result += f"\n... (showing first {self._SESSIONS_MAX_RESULTS} matches)"
        return result

    def _get_session_files_for_person(self, person_name: str) -> list[Path]:
        """Get all session files associated with a person via identity_map."""
        sessions_dir = self._store._workspace / "sessions"
        if not sessions_dir.exists():
            return []

        persons = self._store.resolver.list_persons()
        info = persons.get(person_name)
        if not info:
            return []

        paths: list[Path] = []
        for entry in info.get("ids", []):
            channel = entry.get("channel", "")
            ids = entry.get("id", [])
            if isinstance(ids, str):
                ids = [ids]
            for chat_id in ids:
                p = sessions_dir / f"{channel}_{chat_id}.jsonl"
                if p.exists():
                    paths.append(p)
        return paths
