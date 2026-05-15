"""Tests for RetentionManager — SQLite data pruning."""

import sqlite3
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from ava.storage.retention import RetentionManager, FINISHED_STATUSES


class FakeDB:
    """Minimal DB wrapper around sqlite3 for testing."""

    def __init__(self, path: str = ":memory:"):
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._setup()

    def _setup(self):
        self._conn.executescript("""
            CREATE TABLE token_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                model TEXT DEFAULT '',
                provider TEXT DEFAULT ''
            );
            CREATE TABLE trace_spans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trace_id TEXT NOT NULL,
                span_id TEXT NOT NULL,
                parent_span_id TEXT DEFAULT '',
                name TEXT DEFAULT '',
                operation_name TEXT DEFAULT '',
                kind TEXT DEFAULT 'internal',
                status TEXT DEFAULT 'running',
                start_ns INTEGER NOT NULL,
                end_ns INTEGER,
                events_json TEXT DEFAULT '[]'
            );
            CREATE TABLE bg_tasks (
                task_id TEXT PRIMARY KEY,
                task_type TEXT DEFAULT '',
                origin_session_key TEXT DEFAULT '',
                status TEXT DEFAULT 'queued',
                started_at REAL,
                finished_at REAL
            );
            CREATE TABLE bg_task_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                event TEXT NOT NULL,
                detail TEXT,
                timestamp REAL NOT NULL
            );
            CREATE TABLE audit_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                user TEXT DEFAULT '',
                role TEXT DEFAULT '',
                action TEXT DEFAULT '',
                target TEXT DEFAULT ''
            );
        """)

    def execute(self, sql, params=()):
        return self._conn.execute(sql, params)

    def commit(self):
        self._conn.commit()

    def fetchone(self, sql, params=()):
        return self._conn.execute(sql, params).fetchone()

    def count(self, table: str) -> int:
        row = self._conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        return row[0]


@pytest.fixture
def db():
    return FakeDB()


@pytest.fixture
def manager(db):
    return RetentionManager(
        db,
        token_usage_days=30,
        trace_spans_days=14,
        bg_tasks_days=30,
        audit_days=90,
        vacuum_threshold=100000,
    )


def _iso_ago(days: int) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=days)
    return dt.isoformat()


def _ns_ago(days: int) -> int:
    return int((time.time() - days * 86400) * 1_000_000_000)


class TestTokenUsageRetention:
    def test_old_rows_deleted(self, db, manager):
        db.execute("INSERT INTO token_usage (timestamp, model) VALUES (?, 'm')", (_iso_ago(60),))
        db.execute("INSERT INTO token_usage (timestamp, model) VALUES (?, 'm')", (_iso_ago(31),))
        db.execute("INSERT INTO token_usage (timestamp, model) VALUES (?, 'm')", (_iso_ago(1),))
        db.commit()
        result = manager.run_cleanup()
        assert result["token_usage"] == 2
        assert db.count("token_usage") == 1

    def test_recent_rows_kept(self, db, manager):
        db.execute("INSERT INTO token_usage (timestamp, model) VALUES (?, 'm')", (_iso_ago(5),))
        db.commit()
        result = manager.run_cleanup()
        assert result["token_usage"] == 0
        assert db.count("token_usage") == 1


class TestTraceSpansRetention:
    def test_closed_old_spans_deleted(self, db, manager):
        db.execute(
            "INSERT INTO trace_spans (trace_id, span_id, name, operation_name, start_ns, end_ns) VALUES (?,?,?,?,?,?)",
            ("t1", "s1", "n", "op", _ns_ago(20), _ns_ago(20)),
        )
        db.commit()
        result = manager.run_cleanup()
        assert result["trace_spans"] == 1

    def test_open_spans_not_deleted(self, db, manager):
        db.execute(
            "INSERT INTO trace_spans (trace_id, span_id, name, operation_name, start_ns) VALUES (?,?,?,?,?)",
            ("t2", "s2", "n", "op", _ns_ago(20)),
        )
        db.commit()
        result = manager.run_cleanup()
        assert result["trace_spans"] == 0
        assert db.count("trace_spans") == 1

    def test_recent_closed_spans_kept(self, db, manager):
        db.execute(
            "INSERT INTO trace_spans (trace_id, span_id, name, operation_name, start_ns, end_ns) VALUES (?,?,?,?,?,?)",
            ("t3", "s3", "n", "op", _ns_ago(1), _ns_ago(1)),
        )
        db.commit()
        result = manager.run_cleanup()
        assert result["trace_spans"] == 0


class TestBgTasksRetention:
    def test_succeeded_old_tasks_deleted(self, db, manager):
        old_ts = time.time() - 35 * 86400
        db.execute(
            "INSERT INTO bg_tasks (task_id, task_type, origin_session_key, status, finished_at) VALUES (?,?,?,?,?)",
            ("t1", "type", "sk", "succeeded", old_ts),
        )
        db.execute(
            "INSERT INTO bg_task_events (task_id, event, timestamp) VALUES (?,?,?)",
            ("t1", "started", old_ts),
        )
        db.commit()
        result = manager.run_cleanup()
        assert result["bg_tasks"] == 1
        assert result["bg_task_events"] == 1
        assert db.count("bg_tasks") == 0
        assert db.count("bg_task_events") == 0

    def test_all_finished_statuses_cleaned(self, db, manager):
        old_ts = time.time() - 35 * 86400
        for status in FINISHED_STATUSES:
            db.execute(
                "INSERT INTO bg_tasks (task_id, task_type, origin_session_key, status, finished_at) VALUES (?,?,?,?,?)",
                (f"t_{status}", "type", "sk", status, old_ts),
            )
        db.commit()
        result = manager.run_cleanup()
        assert result["bg_tasks"] == len(FINISHED_STATUSES)

    def test_active_tasks_not_deleted(self, db, manager):
        old_ts = time.time() - 35 * 86400
        db.execute(
            "INSERT INTO bg_tasks (task_id, task_type, origin_session_key, status, started_at) VALUES (?,?,?,?,?)",
            ("t_active", "type", "sk", "running", old_ts),
        )
        db.commit()
        result = manager.run_cleanup()
        assert result["bg_tasks"] == 0
        assert db.count("bg_tasks") == 1

    def test_recent_finished_tasks_kept(self, db, manager):
        recent_ts = time.time() - 5 * 86400
        db.execute(
            "INSERT INTO bg_tasks (task_id, task_type, origin_session_key, status, finished_at) VALUES (?,?,?,?,?)",
            ("t_recent", "type", "sk", "succeeded", recent_ts),
        )
        db.commit()
        result = manager.run_cleanup()
        assert result["bg_tasks"] == 0


class TestAuditRetention:
    def test_old_audit_deleted(self, db, manager):
        db.execute(
            "INSERT INTO audit_entries (timestamp, user, role, action, target) VALUES (?,?,?,?,?)",
            (_iso_ago(100), "u", "r", "a", "t"),
        )
        db.execute(
            "INSERT INTO audit_entries (timestamp, user, role, action, target) VALUES (?,?,?,?,?)",
            (_iso_ago(10), "u", "r", "a", "t"),
        )
        db.commit()
        result = manager.run_cleanup()
        assert result["audit_entries"] == 1
        assert db.count("audit_entries") == 1


class TestVacuumThreshold:
    def test_vacuum_not_triggered_below_threshold(self, db):
        mgr = RetentionManager(db, token_usage_days=1, vacuum_threshold=100)
        db.execute("INSERT INTO token_usage (timestamp, model) VALUES (?, 'm')", (_iso_ago(5),))
        db.commit()
        result = mgr.run_cleanup()
        assert result["token_usage"] == 1

    def test_vacuum_triggered_above_threshold(self, db):
        mgr = RetentionManager(db, token_usage_days=1, vacuum_threshold=5)
        for i in range(10):
            db.execute("INSERT INTO token_usage (timestamp, model) VALUES (?, 'm')", (_iso_ago(5),))
        db.commit()
        result = mgr.run_cleanup()
        assert result["token_usage"] == 10
