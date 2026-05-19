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

    SCHEMA_VERSION = 2

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
        try:
            conn.execute("ALTER TABLE session_messages ADD COLUMN trace_id TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE session_messages ADD COLUMN from_agent_id TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE session_messages ADD COLUMN mentioned_agent_ids TEXT DEFAULT '[]'")
        except sqlite3.OperationalError:
            pass
        for sql in _SAFE_POST_MIGRATION_SQL:
            try:
                conn.execute(sql)
            except sqlite3.OperationalError as exc:
                logger.warning("Skipped post-migration SQL due to legacy schema mismatch: {}", exc)
        # AVA-47 P2a: stamp per-table migration markers so future migrations
        # can branch on whether v1 was applied.
        from datetime import datetime, timezone
        applied_at = datetime.now(timezone.utc).isoformat()
        for marker in (
            "agent_workflows_v1",
            "workflow_versions_v1",
            "workflow_runs_v1",
            "workflow_steps_v1",
            "workflow_artifacts_v1",
            "workspace_leases_v1",
        ):
            conn.execute(
                "INSERT OR IGNORE INTO schema_migrations (name, applied_at) VALUES (?, ?)",
                (marker, applied_at),
            )
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
                   (session_id, seq, conversation_id, trace_id, from_agent_id, mentioned_agent_ids, role, content, tool_calls, tool_call_id, name, reasoning_content, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    session_id,
                    seq,
                    conversation_id,
                    msg.get("trace_id", ""),
                    msg.get("from_agent_id", ""),
                    json.dumps(msg.get("mentioned_agent_ids", []), ensure_ascii=False),
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
    ("trace_id", "TEXT", "''"),
    ("span_id", "TEXT", "''"),
    ("parent_span_id", "TEXT", "''"),
]

_SAFE_POST_MIGRATION_SQL: list[str] = [
    "CREATE INDEX IF NOT EXISTS idx_tu_conv_turn ON token_usage(session_key, conversation_id, turn_seq)",
    "CREATE INDEX IF NOT EXISTS idx_msg_session_conv_seq ON session_messages(session_id, conversation_id, seq)",
    "CREATE INDEX IF NOT EXISTS idx_msg_trace ON session_messages(trace_id)",
    "CREATE INDEX IF NOT EXISTS idx_tu_trace ON token_usage(trace_id)",
    "CREATE INDEX IF NOT EXISTS idx_tu_span ON token_usage(trace_id, span_id)",
    "CREATE INDEX IF NOT EXISTS idx_agent_registry_status ON agent_registry(status)",
    """CREATE TABLE IF NOT EXISTS session_compressions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER NOT NULL,
        compressed_at TEXT NOT NULL,
        before_tokens INTEGER NOT NULL,
        after_tokens INTEGER NOT NULL,
        summary_text TEXT NOT NULL,
        before_after_diff TEXT DEFAULT '{}',
        FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
    )""",
    "CREATE INDEX IF NOT EXISTS idx_session_compressions_session ON session_compressions(session_id, compressed_at)",
]

_SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS schema_migrations (
    name TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
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
    trace_id TEXT DEFAULT '',
    role TEXT NOT NULL,
    content TEXT,
    tool_calls TEXT,
    tool_call_id TEXT,
    name TEXT,
    reasoning_content TEXT,
    from_agent_id TEXT DEFAULT '',
    mentioned_agent_ids TEXT DEFAULT '[]',
    timestamp TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_msg_session_seq ON session_messages(session_id, seq);

CREATE TABLE IF NOT EXISTS session_compressions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    compressed_at TEXT NOT NULL,
    before_tokens INTEGER NOT NULL,
    after_tokens INTEGER NOT NULL,
    summary_text TEXT NOT NULL,
    before_after_diff TEXT DEFAULT '{}',
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_session_compressions_session ON session_compressions(session_id, compressed_at);

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
    tool_names TEXT DEFAULT '',
    trace_id TEXT DEFAULT '',
    span_id TEXT DEFAULT '',
    parent_span_id TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_tu_timestamp ON token_usage(timestamp);
CREATE INDEX IF NOT EXISTS idx_tu_model ON token_usage(model);
CREATE INDEX IF NOT EXISTS idx_tu_session ON token_usage(session_key);
CREATE INDEX IF NOT EXISTS idx_tu_turn ON token_usage(session_key, turn_seq);

CREATE TABLE IF NOT EXISTS trace_spans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id TEXT NOT NULL,
    span_id TEXT NOT NULL,
    parent_span_id TEXT DEFAULT '',
    name TEXT NOT NULL,
    operation_name TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'internal',
    status TEXT NOT NULL DEFAULT 'running',
    status_message TEXT DEFAULT '',
    start_ns INTEGER NOT NULL,
    end_ns INTEGER,
    duration_ms REAL,
    attributes_json TEXT DEFAULT '{}',
    events_json TEXT DEFAULT '[]',
    session_key TEXT DEFAULT '',
    conversation_id TEXT DEFAULT '',
    turn_seq INTEGER,
    UNIQUE(trace_id, span_id)
);
CREATE INDEX IF NOT EXISTS idx_trace_spans_trace ON trace_spans(trace_id, start_ns);
CREATE INDEX IF NOT EXISTS idx_trace_spans_parent ON trace_spans(trace_id, parent_span_id);
CREATE INDEX IF NOT EXISTS idx_trace_spans_session ON trace_spans(session_key, conversation_id, turn_seq);
CREATE INDEX IF NOT EXISTS idx_trace_spans_open ON trace_spans(end_ns, start_ns);

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

CREATE TABLE IF NOT EXISTS agent_registry (
    instance_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    display_name TEXT NOT NULL,
    status TEXT NOT NULL,
    installed INTEGER NOT NULL DEFAULT 0,
    path TEXT DEFAULT '',
    version TEXT DEFAULT '',
    capabilities TEXT DEFAULT '{}',
    active_tasks INTEGER NOT NULL DEFAULT 0,
    install_url TEXT DEFAULT '',
    detail TEXT DEFAULT '',
    last_seen TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_agent_registry_name ON agent_registry(name);

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

CREATE TABLE IF NOT EXISTS lan_devices (
    device_id TEXT PRIMARY KEY,
    token_id TEXT NOT NULL,
    name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'read_only',
    capabilities TEXT NOT NULL DEFAULT '["read"]',
    created_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    last_ip TEXT DEFAULT '',
    user_agent TEXT DEFAULT '',
    expires_at TEXT NOT NULL,
    revoked_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_lan_devices_token ON lan_devices(device_id, token_id);
CREATE INDEX IF NOT EXISTS idx_lan_devices_revoked ON lan_devices(revoked_at);

CREATE TABLE IF NOT EXISTS lan_device_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    device_id TEXT DEFAULT '',
    event TEXT NOT NULL,
    ip TEXT DEFAULT '',
    user_agent TEXT DEFAULT '',
    detail TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_lan_device_events_device ON lan_device_events(device_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_lan_device_events_event ON lan_device_events(event, timestamp);

CREATE TABLE IF NOT EXISTS lan_pair_throttle (
    scope TEXT NOT NULL,
    key TEXT NOT NULL,
    first_failed_at TEXT NOT NULL,
    last_failed_at TEXT NOT NULL,
    failure_count INTEGER NOT NULL,
    locked_until TEXT,
    PRIMARY KEY (scope, key)
);
CREATE INDEX IF NOT EXISTS idx_lan_pair_throttle_locked ON lan_pair_throttle(locked_until);

-- AVA-47 P2a: workflow definition + run baseline (6 tables, see spec
-- .specanchor/tasks/_cross-module/2026-05-13_p2a-p2c-workflow-baseline.spec.md §1 F2).
-- Distinct from P1b workflow_chains/workflow_nodes/task_artifacts owned by
-- ava/agent/workflow_store.py — those keep operating unchanged.
CREATE TABLE IF NOT EXISTS agent_workflows (
    workflow_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    current_version INTEGER NOT NULL DEFAULT 1,
    created_by_agent TEXT DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    deleted_at REAL
);
CREATE INDEX IF NOT EXISTS idx_agent_workflows_name ON agent_workflows(name);
CREATE INDEX IF NOT EXISTS idx_agent_workflows_updated ON agent_workflows(updated_at);

CREATE TABLE IF NOT EXISTS workflow_versions (
    workflow_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    definition_json TEXT NOT NULL,
    change_summary TEXT DEFAULT '',
    base_version INTEGER,
    created_by_agent TEXT DEFAULT '',
    created_at REAL NOT NULL,
    is_current INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (workflow_id, version),
    FOREIGN KEY (workflow_id) REFERENCES agent_workflows(workflow_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_workflow_versions_current ON workflow_versions(workflow_id, is_current);

CREATE TABLE IF NOT EXISTS workflow_runs (
    run_id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    triggered_by TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    started_at REAL,
    completed_at REAL,
    final_outputs_json TEXT DEFAULT '{}',
    FOREIGN KEY (workflow_id) REFERENCES agent_workflows(workflow_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_workflow ON workflow_runs(workflow_id, started_at);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_status ON workflow_runs(status);

CREATE TABLE IF NOT EXISTS workflow_steps (
    step_run_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    step_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    agent TEXT DEFAULT '',
    bg_task_id TEXT DEFAULT '',
    started_at REAL,
    completed_at REAL,
    outputs_json TEXT DEFAULT '{}',
    error_json TEXT DEFAULT '{}',
    FOREIGN KEY (run_id) REFERENCES workflow_runs(run_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_workflow_steps_run ON workflow_steps(run_id);
CREATE INDEX IF NOT EXISTS idx_workflow_steps_bg_task ON workflow_steps(bg_task_id);

CREATE TABLE IF NOT EXISTS workflow_artifacts (
    artifact_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    step_run_id TEXT DEFAULT '',
    kind TEXT NOT NULL,
    payload_ref TEXT NOT NULL,
    created_at REAL NOT NULL,
    FOREIGN KEY (run_id) REFERENCES workflow_runs(run_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_workflow_artifacts_run ON workflow_artifacts(run_id);
CREATE INDEX IF NOT EXISTS idx_workflow_artifacts_step ON workflow_artifacts(step_run_id);

CREATE TABLE IF NOT EXISTS workspace_leases (
    lease_id TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    holder_run_id TEXT DEFAULT '',
    holder_step_id TEXT DEFAULT '',
    acquired_at REAL NOT NULL,
    expires_at REAL,
    released_at REAL
);
CREATE INDEX IF NOT EXISTS idx_workspace_leases_path ON workspace_leases(path);
CREATE INDEX IF NOT EXISTS idx_workspace_leases_holder ON workspace_leases(holder_run_id);
"""
