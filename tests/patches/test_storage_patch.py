"""Tests for storage_patch — SQLite storage replacement."""

import json
import sqlite3
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from nanobot.session.manager import SessionManager, Session


@pytest.fixture(autouse=True)
def _restore_session_manager():
    """Save and restore SessionManager methods to avoid polluting other tests."""
    orig_save = SessionManager.save
    orig_load = SessionManager._load
    orig_list = SessionManager.list_sessions
    yield
    SessionManager.save = orig_save
    SessionManager._load = orig_load
    SessionManager.list_sessions = orig_list


@pytest.fixture
def storage_db(tmp_path):
    """Apply storage_patch with a temp data dir and return (db, data_dir, db_path)."""
    from unittest.mock import patch as mock_patch

    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    with mock_patch("nanobot.config.paths.get_data_dir", return_value=data_dir):
        from ava.storage import Database

        db_path = data_dir / "nanobot.db"
        db = Database(db_path)
        return db, data_dir, db_path


@pytest.fixture
def patched_manager(tmp_path):
    """Return a SessionManager after storage_patch is applied."""
    from unittest.mock import patch as mock_patch

    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    with mock_patch("nanobot.config.paths.get_data_dir", return_value=data_dir):
        from ava.patches.storage_patch import apply_storage_patch
        apply_storage_patch()

    mgr = SessionManager.__new__(SessionManager)
    mgr._cache = {}
    mgr._sessions_dir = tmp_path / "sessions"
    mgr._sessions_dir.mkdir(exist_ok=True)
    return mgr


def _make_session(key="test:123", messages=None, metadata=None):
    """Helper to create a Session instance."""
    return Session(
        key=key,
        messages=messages or [
            {"role": "user", "content": "hello", "timestamp": "2026-01-01T00:00:00"},
            {"role": "assistant", "content": "hi there", "timestamp": "2026-01-01T00:00:01"},
        ],
        created_at=datetime(2026, 1, 1),
        metadata=metadata or {"token_stats": {}},
        last_consolidated=0,
    )


class TestStoragePatch:
    def test_database_upgrades_legacy_token_usage_before_creating_conversation_index(self, tmp_path):
        """Legacy DB without conversation_id should still migrate cleanly."""
        db_path = tmp_path / "legacy.db"
        conn = sqlite3.connect(str(db_path))
        conn.executescript(
            """
            CREATE TABLE token_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                model TEXT NOT NULL,
                provider TEXT NOT NULL,
                prompt_tokens INTEGER DEFAULT 0,
                completion_tokens INTEGER DEFAULT 0,
                total_tokens INTEGER DEFAULT 0,
                session_key TEXT,
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
            """
        )
        conn.commit()
        conn.close()

        from ava.storage import Database

        db = Database(db_path)
        columns = {row["name"] for row in db.fetchall("PRAGMA table_info(token_usage)")}
        indexes = {row["name"] for row in db.fetchall("PRAGMA index_list(token_usage)")}

        assert "conversation_id" in columns
        assert "idx_tu_conv_turn" in indexes

    def test_database_adds_session_message_conversation_column_and_index(self, tmp_path):
        db_path = tmp_path / "legacy_messages.db"
        conn = sqlite3.connect(str(db_path))
        conn.executescript(
            """
            CREATE TABLE session_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                seq INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT,
                tool_calls TEXT,
                tool_call_id TEXT,
                name TEXT,
                reasoning_content TEXT,
                timestamp TEXT
            );
            """
        )
        conn.commit()
        conn.close()

        from ava.storage import Database

        db = Database(db_path)
        columns = {row["name"] for row in db.fetchall("PRAGMA table_info(session_messages)")}
        indexes = {row["name"] for row in db.fetchall("PRAGMA index_list(session_messages)")}

        assert "conversation_id" in columns
        assert "idx_msg_session_conv_seq" in indexes

    def test_patch_applies_without_error(self, tmp_path):
        """T5.0: apply_storage_patch runs without error."""
        from unittest.mock import patch as mock_patch

        data_dir = tmp_path / "data"
        data_dir.mkdir(exist_ok=True)
        with mock_patch("nanobot.config.paths.get_data_dir", return_value=data_dir):
            from ava.patches.storage_patch import apply_storage_patch

            result = apply_storage_patch()
            assert "sqlite" in result.lower()

    def test_save_and_load(self, patched_manager):
        """T5.1+T5.2: save then load returns equivalent session."""
        session = _make_session()
        patched_manager.save(session)

        loaded = patched_manager._load("test:123")
        assert loaded is not None
        assert loaded.key == "test:123"
        assert len(loaded.messages) == 2
        assert loaded.messages[0]["role"] == "user"
        assert loaded.messages[0]["content"] == "hello"

    def test_load_nonexistent(self, patched_manager):
        """T5.5: loading nonexistent key returns None."""
        result = patched_manager._load("nonexistent:key")
        assert result is None

    def test_message_serialization_with_tool_calls(self, patched_manager):
        """T5.3: messages with tool_calls serialize/deserialize correctly."""
        session = _make_session(messages=[
            {
                "role": "assistant",
                "content": "calling tool",
                "tool_calls": [{"id": "tc1", "function": {"name": "test"}}],
                "timestamp": "2026-01-01T00:00:00",
            },
            {
                "role": "tool",
                "content": "result",
                "tool_call_id": "tc1",
                "name": "test",
                "timestamp": "2026-01-01T00:00:01",
            },
        ])
        patched_manager.save(session)
        loaded = patched_manager._load("test:123")

        assert loaded.messages[0]["tool_calls"][0]["id"] == "tc1"
        assert loaded.messages[1]["tool_call_id"] == "tc1"
        assert loaded.messages[1]["name"] == "test"

    def test_save_skips_duplicate_message_signature(self, patched_manager):
        session = _make_session(messages=[
            {
                "role": "assistant",
                "content": "calling tool",
                "tool_calls": [{"id": "tc1", "function": {"name": "write_file"}}],
                "timestamp": "2026-01-01T00:00:00",
            },
            {
                "role": "tool",
                "content": "Successfully wrote file",
                "tool_call_id": "tc1",
                "name": "write_file",
                "timestamp": "2026-01-01T00:00:01",
            },
            {
                "role": "assistant",
                "content": "done",
                "timestamp": "2026-01-01T00:00:02",
            },
        ])
        patched_manager.save(session)

        session.messages.extend([
            {
                "role": "tool",
                "content": "Successfully wrote file",
                "tool_call_id": "tc1",
                "name": "write_file",
                "timestamp": "2026-01-01T00:00:01",
            },
            {
                "role": "assistant",
                "content": "done",
                "timestamp": "2026-01-01T00:00:02",
            },
        ])
        patched_manager.save(session)

        loaded = patched_manager._load("test:123")
        assert loaded is not None
        assert [(msg["role"], msg["content"]) for msg in loaded.messages] == [
            ("assistant", "calling tool"),
            ("tool", "Successfully wrote file"),
            ("assistant", "done"),
        ]

    def test_list_sessions(self, patched_manager):
        """T5.4: list_sessions returns saved sessions."""
        patched_manager.save(_make_session("sess:1"))
        patched_manager.save(_make_session("sess:2"))

        sessions = patched_manager.list_sessions()
        keys = [s["key"] for s in sessions]
        assert "sess:1" in keys
        assert "sess:2" in keys

    def test_upsert(self, patched_manager):
        """T5.6: saving same key twice — incremental append keeps old + adds new."""
        s = _make_session(messages=[{"role": "user", "content": "v1", "timestamp": "t1"}])
        patched_manager.save(s)

        # Append a new message (simulates real usage: append-only)
        s.messages.append({"role": "assistant", "content": "v2", "timestamp": "t2"})
        patched_manager.save(s)

        loaded = patched_manager._load("test:123")
        assert len(loaded.messages) == 2
        assert loaded.messages[0]["content"] == "v1"
        assert loaded.messages[1]["content"] == "v2"

    def test_clear_then_save(self, patched_manager):
        """T5.6b: clearing session via .clear() and re-adding messages replaces DB."""
        s = _make_session(messages=[
            {"role": "user", "content": "old", "timestamp": "t1"},
            {"role": "assistant", "content": "old reply", "timestamp": "t2"},
        ])
        patched_manager.save(s)

        # Simulate session.clear() + new messages
        s.clear()
        s.add_message("user", "new")
        s.add_message("assistant", "new reply")
        patched_manager.save(s)

        loaded = patched_manager._load("test:123")
        assert loaded.messages[0]["content"] == "new"
        assert loaded.messages[1]["content"] == "new reply"

    def test_new_conversation_keeps_old_history_and_loads_only_active_conversation(self, patched_manager):
        session = _make_session(
            messages=[
                {"role": "user", "content": "old", "timestamp": "t1"},
                {"role": "assistant", "content": "old reply", "timestamp": "t2"},
            ],
            metadata={"token_stats": {}, "conversation_id": "conv_old"},
        )
        patched_manager.save(session)

        session.metadata["conversation_id"] = "conv_new"
        session.clear()
        patched_manager.save(session)

        session.add_message("user", "fresh")
        session.add_message("assistant", "fresh reply")
        patched_manager.save(session)

        loaded = patched_manager._load("test:123")
        assert loaded is not None
        assert loaded.metadata["conversation_id"] == "conv_new"
        assert [msg["content"] for msg in loaded.messages] == ["fresh", "fresh reply"]

        conn = patched_manager._cache["test:123"]  # confirm cache still points at live session
        assert conn.metadata["conversation_id"] == "conv_new"

        db_rows = patched_manager.list_sessions()
        assert any(row["key"] == "test:123" for row in db_rows)

        from ava.storage import get_db
        db = get_db()
        rows = db.fetchall(
            """
            SELECT conversation_id, seq, content
              FROM session_messages sm
              JOIN sessions s ON s.id = sm.session_id
             WHERE s.key = ?
             ORDER BY conversation_id, seq
            """,
            ("test:123",),
        )
        assert [(row["conversation_id"], row["content"]) for row in rows] == [
            ("conv_new", "fresh"),
            ("conv_new", "fresh reply"),
            ("conv_old", "old"),
            ("conv_old", "old reply"),
        ]

    def test_cache_updated(self, patched_manager):
        """T5.7: save updates _cache."""
        session = _make_session()
        patched_manager.save(session)
        assert "test:123" in patched_manager._cache

    def test_backfill_integrated(self, patched_manager):
        """T5.8: backfill runs after SQLite load (P0 fix)."""
        # Save a session — backfill should run on load
        # Even if messages are "clean", the backfill code path should execute without error
        session = _make_session()
        patched_manager.save(session)
        loaded = patched_manager._load("test:123")
        assert loaded is not None
        assert len(loaded.messages) >= 2

    def test_shared_db_with_loop_patch(self, tmp_path):
        """T5.9: storage_patch calls loop_patch.set_shared_db."""
        from unittest.mock import patch as mock_patch

        data_dir = tmp_path / "data"
        data_dir.mkdir(exist_ok=True)
        with mock_patch("nanobot.config.paths.get_data_dir", return_value=data_dir):
            # Verify that after apply, loop_patch._shared_db is set
            from ava.patches.loop_patch import set_shared_db
            set_shared_db(None)  # reset

            from ava.patches.storage_patch import apply_storage_patch
            apply_storage_patch()

            from ava.patches import loop_patch
            assert loop_patch._shared_db is not None
