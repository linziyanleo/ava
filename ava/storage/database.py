"""SQLite database manager with thread-safe connection pooling and auto-migration."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from loguru import logger


class Database:
    """Thread-safe SQLite database with WAL mode, schema management, and JSONL migration."""

    SCHEMA_VERSION = 1

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._lock = threading.Lock()
        self._create_schema()

    def _get_conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(str(self._db_path), timeout=30)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=5000")
            self._local.conn = conn
        return conn

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        return self._get_conn().execute(sql, params)

    def executemany(self, sql: str, params_list: list[tuple]) -> None:
        self._get_conn().executemany(sql, params_list)

    def commit(self) -> None:
        self._get_conn().commit()

    def fetchone(self, sql: str, params: tuple = ()) -> sqlite3.Row | None:
        return self._get_conn().execute(sql, params).fetchone()

    def fetchall(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        return self._get_conn().execute(sql, params).fetchall()

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn:
            conn.close()
            self._local.conn = None

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _create_schema(self) -> None:
        conn = self._get_conn()
        conn.executescript(_SCHEMA_DDL)
        for col, col_type, default in _SAFE_TOKEN_USAGE_COLUMNS:
            try:
                conn.execute(f"ALTER TABLE token_usage ADD COLUMN {col} {col_type} DEFAULT {default}")
            except sqlite3.OperationalError:
                pass  # column already exists
        try:
            conn.execute("ALTER TABLE session_messages ADD COLUMN conversation_id TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass
        for sql in _SAFE_POST_MIGRATION_SQL:
            try:
                conn.execute(sql)
            except sqlite3.OperationalError as exc:
                logger.warning("Skipped post-migration SQL due to legacy schema mismatch: {}", exc)
        conn.commit()

    # ------------------------------------------------------------------
    # Migration from JSONL / JSON
    # ------------------------------------------------------------------

    def is_migrated(self) -> bool:
        row = self.fetchone("SELECT version FROM schema_version LIMIT 1")
        return row is not None

    def migrate_from_files(
        self,
        *,
        sessions_dir: Path | None = None,
        token_stats_file: Path | None = None,
        audit_file: Path | None = None,
        media_records_file: Path | None = None,
    ) -> dict[str, int]:
        """Import existing JSONL/JSON data into SQLite. Idempotent (skips if already migrated)."""
        if self.is_migrated():
            return {}

        counts: dict[str, int] = {}
        conn = self._get_conn()

        if sessions_dir and sessions_dir.is_dir():
            n = self._migrate_sessions(conn, sessions_dir)
            counts["sessions"] = n

        if token_stats_file and token_stats_file.is_file():
            n = self._migrate_token_stats(conn, token_stats_file)
            counts["token_usage"] = n

        if audit_file and audit_file.is_file():
            n = self._migrate_audit(conn, audit_file)
            counts["audit_entries"] = n

        if media_records_file and media_records_file.is_file():
            n = self._migrate_media(conn, media_records_file)
            counts["media_records"] = n

        conn.execute(
            "INSERT INTO schema_version (version) VALUES (?)",
            (self.SCHEMA_VERSION,),
        )
        conn.commit()
        logger.info("Migration complete: {}", counts)

        backfilled = self.backfill_turn_seq()
        if backfilled:
            logger.info("Backfilled turn_seq for {} token_usage records", backfilled)

        iteration_backfilled = self.backfill_iteration()
        if iteration_backfilled:
            logger.info("Backfilled iteration for {} token_usage records", iteration_backfilled)

        return counts

    def backfill_turn_seq(self, session_key: str | None = None) -> int:
        """Infer turn_seq for token_usage records that have NULL turn_seq.

        Uses session_messages timestamps to determine which user-turn each
        LLM call belongs to.  Turn boundaries are built from user messages
        sorted by timestamp (not seq) and deduplicated so that each seq
        value maps to its earliest timestamp.  The assigned turn_seq uses
        the original ``seq`` value rather than a positional index.
        """
        conn = self._get_conn()

        if session_key:
            null_count = conn.execute(
                "SELECT COUNT(*) FROM token_usage WHERE turn_seq IS NULL AND session_key = ?",
                (session_key,),
            ).fetchone()[0]
        else:
            null_count = conn.execute(
                "SELECT COUNT(*) FROM token_usage WHERE turn_seq IS NULL AND session_key != ''"
            ).fetchone()[0]
        if not null_count:
            return 0

        if session_key:
            sessions = [(session_key,)]
        else:
            sessions = conn.execute(
                "SELECT DISTINCT session_key FROM token_usage WHERE turn_seq IS NULL AND session_key != ''"
            ).fetchall()

        total_updated = 0
        for (session_key,) in sessions:
            session_row = conn.execute(
                "SELECT id FROM sessions WHERE key = ?", (session_key,)
            ).fetchone()
            if not session_row:
                continue

            # Fetch user messages, deduplicate by seq (keep earliest timestamp),
            # then sort by timestamp so boundary scanning works correctly.
            user_msgs = conn.execute(
                "SELECT seq, MIN(timestamp) as timestamp FROM session_messages "
                "WHERE session_id = ? AND role = 'user' "
                "GROUP BY seq ORDER BY MIN(timestamp)",
                (session_row["id"],),
            ).fetchall()
            if not user_msgs:
                continue

            # Build (seq_value, timestamp) boundaries sorted by timestamp
            turn_boundaries: list[tuple[int, str]] = [
                (row["seq"], row["timestamp"] or "")
                for row in user_msgs
                if row["timestamp"]
            ]

            records = conn.execute(
                "SELECT id, timestamp FROM token_usage "
                "WHERE session_key = ? AND turn_seq IS NULL ORDER BY timestamp",
                (session_key,),
            ).fetchall()

            for rec in records:
                rec_ts = rec["timestamp"] or ""
                assigned_turn = turn_boundaries[0][0] if turn_boundaries else 0
                for seq_val, boundary_ts in turn_boundaries:
                    if rec_ts >= boundary_ts:
                        assigned_turn = seq_val
                    else:
                        break

                conn.execute(
                    "UPDATE token_usage SET turn_seq = ? WHERE id = ?",
                    (assigned_turn, rec["id"]),
                )
                total_updated += 1

        conn.commit()
        return total_updated

    def backfill_iteration(self, session_key: str | None = None) -> int:
        """Assign deterministic iteration values to legacy all-zero turn groups.

        Only updates groups with more than one record where every row still has
        the legacy default iteration=0. Ordering is based on timestamp then id
        so repeated runs are idempotent.
        """
        conn = self._get_conn()

        clauses = ["turn_seq IS NOT NULL"]
        params: list[Any] = []
        if session_key:
            clauses.append("session_key = ?")
            params.append(session_key)

        groups = conn.execute(
            f"""
            SELECT session_key, conversation_id, turn_seq
              FROM token_usage
             WHERE {" AND ".join(clauses)}
             GROUP BY session_key, conversation_id, turn_seq
            HAVING COUNT(*) > 1 AND COALESCE(MAX(iteration), 0) = 0
            ORDER BY session_key, conversation_id, turn_seq
            """,
            tuple(params),
        ).fetchall()
        if not groups:
            return 0

        total_updated = 0
        for group in groups:
            rows = conn.execute(
                """
                SELECT id
                  FROM token_usage
                 WHERE session_key = ? AND conversation_id = ? AND turn_seq = ?
                 ORDER BY CASE WHEN timestamp IS NULL OR timestamp = '' THEN 1 ELSE 0 END,
                          timestamp ASC,
                          id ASC
                """,
                (group["session_key"], group["conversation_id"], group["turn_seq"]),
            ).fetchall()
            for iteration, row in enumerate(rows):
                conn.execute(
                    "UPDATE token_usage SET iteration = ? WHERE id = ?",
                    (iteration, row["id"]),
                )
                total_updated += 1

        conn.commit()
        return total_updated

    def _migrate_sessions(self, conn: sqlite3.Connection, sessions_dir: Path) -> int:
        count = 0
        for jsonl_file in sessions_dir.glob("*.jsonl"):
            try:
                self._import_session_file(conn, jsonl_file)
                count += 1
            except Exception as e:
                logger.warning("Failed to migrate session {}: {}", jsonl_file.name, e)
        conn.commit()
        return count

    def _import_session_file(self, conn: sqlite3.Connection, path: Path) -> None:
        lines = path.read_text("utf-8").splitlines()
        if not lines:
            return

        metadata: dict[str, Any] = {}
        messages: list[dict[str, Any]] = []

        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if data.get("_type") == "metadata":
                metadata = data
            else:
                messages.append(data)

        key = metadata.get("key") or path.stem.replace("_", ":", 1)
        created_at = metadata.get("created_at", "")
        updated_at = metadata.get("updated_at", "")
        meta_json = json.dumps(metadata.get("metadata", {}), ensure_ascii=False)
        last_consolidated = metadata.get("last_consolidated", 0)
        last_completed = metadata.get("last_completed")
        token_stats = json.dumps(
            metadata.get("token_stats", {}), ensure_ascii=False
        )

        conn.execute(
            """INSERT OR IGNORE INTO sessions
               (key, created_at, updated_at, metadata, last_consolidated, last_completed, token_stats)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (key, created_at, updated_at, meta_json, last_consolidated, last_completed, token_stats),
        )

        row = conn.execute("SELECT id FROM sessions WHERE key = ?", (key,)).fetchone()
        if not row:
            return
        session_id = row["id"]
        conversation_id = ""
        if isinstance(metadata.get("conversation_id"), str):
            conversation_id = metadata["conversation_id"]
        elif isinstance(metadata.get("metadata"), dict):
            nested_value = metadata["metadata"].get("conversation_id")
            if isinstance(nested_value, str):
                conversation_id = nested_value

        for seq, msg in enumerate(messages):
            tool_calls_json = json.dumps(msg["tool_calls"], ensure_ascii=False) if msg.get("tool_calls") else None
            conn.execute(
                """INSERT INTO session_messages
                   (session_id, seq, conversation_id, role, content, tool_calls, tool_call_id, name, reasoning_content, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    session_id,
                    seq,
                    conversation_id,
                    msg.get("role", ""),
                    msg.get("content") if isinstance(msg.get("content"), str) else json.dumps(msg.get("content"), ensure_ascii=False) if msg.get("content") else None,
                    tool_calls_json,
                    msg.get("tool_call_id"),
                    msg.get("name"),
                    msg.get("reasoning_content"),
                    msg.get("timestamp"),
                ),
            )

    def _migrate_token_stats(self, conn: sqlite3.Connection, path: Path) -> int:
        try:
            raw = json.loads(path.read_text("utf-8"))
        except (json.JSONDecodeError, OSError):
            return 0
        if not isinstance(raw, list):
            return 0

        count = 0
        for item in raw:
            if not isinstance(item, dict):
                continue
            conn.execute(
                """INSERT INTO token_usage
                   (timestamp, model, provider, prompt_tokens, completion_tokens, total_tokens,
                    session_key, user_message, output_content, system_prompt_preview,
                    conversation_history, full_request_payload, finish_reason)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    item.get("timestamp", ""),
                    item.get("model", ""),
                    item.get("provider", ""),
                    item.get("prompt_tokens", 0),
                    item.get("completion_tokens", 0),
                    item.get("total_tokens", 0),
                    item.get("session_key", ""),
                    item.get("user_message", ""),
                    item.get("output_content", ""),
                    item.get("system_prompt_preview", ""),
                    item.get("conversation_history", ""),
                    item.get("full_request_payload", ""),
                    item.get("finish_reason", ""),
                ),
            )
            count += 1
        conn.commit()
        return count

    def _migrate_audit(self, conn: sqlite3.Connection, path: Path) -> int:
        count = 0
        for line in path.read_text("utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            conn.execute(
                """INSERT INTO audit_entries
                   (timestamp, user, role, action, target, detail, ip)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    data.get("ts", ""),
                    data.get("user", ""),
                    data.get("role", ""),
                    data.get("action", ""),
                    data.get("target", ""),
                    json.dumps(data.get("detail"), ensure_ascii=False) if data.get("detail") else None,
                    data.get("ip", ""),
                ),
            )
            count += 1
        conn.commit()
        return count

    def _migrate_media(self, conn: sqlite3.Connection, path: Path) -> int:
        count = 0
        for line in path.read_text("utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            conn.execute(
                """INSERT OR IGNORE INTO media_records
                   (id, timestamp, prompt, reference_image, output_images, output_text, model, status, error)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    data.get("id", ""),
                    data.get("timestamp", ""),
                    data.get("prompt", ""),
                    data.get("reference_image"),
                    json.dumps(data.get("output_images", []), ensure_ascii=False),
                    data.get("output_text", ""),
                    data.get("model", ""),
                    data.get("status", "success"),
                    data.get("error"),
                ),
            )
            count += 1
        conn.commit()
        return count


# ------------------------------------------------------------------
# DDL
# ------------------------------------------------------------------

_SAFE_TOKEN_USAGE_COLUMNS: list[tuple[str, str, str]] = [
    ("cost_usd", "REAL", "0"),
    ("current_turn_tokens", "INTEGER", "0"),
    ("tool_names", "TEXT", "''"),
    ("conversation_id", "TEXT", "''"),
]

_SAFE_POST_MIGRATION_SQL: list[str] = [
    "CREATE INDEX IF NOT EXISTS idx_tu_conv_turn ON token_usage(session_key, conversation_id, turn_seq)",
    "CREATE INDEX IF NOT EXISTS idx_msg_session_conv_seq ON session_messages(session_id, conversation_id, seq)",
]

_SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT UNIQUE NOT NULL,
    created_at TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT '',
    metadata TEXT DEFAULT '{}',
    last_consolidated INTEGER DEFAULT 0,
    last_completed INTEGER,
    token_stats TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sessions_key ON sessions(key);
CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(updated_at);

CREATE TABLE IF NOT EXISTS session_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    seq INTEGER NOT NULL,
    conversation_id TEXT DEFAULT '',
    role TEXT NOT NULL,
    content TEXT,
    tool_calls TEXT,
    tool_call_id TEXT,
    name TEXT,
    reasoning_content TEXT,
    timestamp TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_msg_session_seq ON session_messages(session_id, seq);

CREATE TABLE IF NOT EXISTS token_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    model TEXT NOT NULL,
    provider TEXT NOT NULL,
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    session_key TEXT,
    conversation_id TEXT DEFAULT '',
    turn_seq INTEGER,
    iteration INTEGER DEFAULT 0,
    user_message TEXT DEFAULT '',
    output_content TEXT DEFAULT '',
    system_prompt_preview TEXT DEFAULT '',
    conversation_history TEXT DEFAULT '',
    full_request_payload TEXT DEFAULT '',
    finish_reason TEXT DEFAULT '',
    model_role TEXT DEFAULT 'default',
    cached_tokens INTEGER DEFAULT 0,
    cache_creation_tokens INTEGER DEFAULT 0,
    cost_usd REAL DEFAULT 0,
    current_turn_tokens INTEGER DEFAULT 0,
    tool_names TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_tu_timestamp ON token_usage(timestamp);
CREATE INDEX IF NOT EXISTS idx_tu_model ON token_usage(model);
CREATE INDEX IF NOT EXISTS idx_tu_session ON token_usage(session_key);
CREATE INDEX IF NOT EXISTS idx_tu_turn ON token_usage(session_key, turn_seq);

CREATE TABLE IF NOT EXISTS audit_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    user TEXT NOT NULL,
    role TEXT NOT NULL,
    action TEXT NOT NULL,
    target TEXT NOT NULL,
    detail TEXT,
    ip TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_entries(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_entries(user);

CREATE TABLE IF NOT EXISTS media_records (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    prompt TEXT NOT NULL,
    reference_image TEXT,
    output_images TEXT DEFAULT '[]',
    output_text TEXT DEFAULT '',
    model TEXT DEFAULT '',
    status TEXT DEFAULT 'success',
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_media_ts ON media_records(timestamp);

CREATE TABLE IF NOT EXISTS skill_config (
    name TEXT PRIMARY KEY,
    source TEXT NOT NULL DEFAULT 'ava',
    enabled INTEGER NOT NULL DEFAULT 1,
    installed_at TEXT,
    install_method TEXT,
    git_url TEXT,
    updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_skill_source ON skill_config(source);
"""
