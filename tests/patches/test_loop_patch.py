"""Tests for loop_patch — AgentLoop attribute injection + token stats."""

import gc
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from pathlib import Path
import weakref

import pytest

from nanobot.agent.loop import AgentLoop
from nanobot.agent.memory import Consolidator


@pytest.fixture(autouse=True)
def _restore_agent_loop():
    """Save and restore AgentLoop methods to avoid polluting other tests."""
    orig_init = AgentLoop.__init__
    orig_set_tool_context = AgentLoop._set_tool_context
    orig_run_agent_loop = AgentLoop._run_agent_loop
    orig_save_turn = AgentLoop._save_turn
    orig_process = AgentLoop._process_message
    orig_archive = Consolidator.archive
    orig_maybe_consolidate = Consolidator.maybe_consolidate_by_tokens
    yield
    AgentLoop.__init__ = orig_init
    AgentLoop._set_tool_context = orig_set_tool_context
    AgentLoop._run_agent_loop = orig_run_agent_loop
    AgentLoop._save_turn = orig_save_turn
    AgentLoop._process_message = orig_process
    Consolidator.archive = orig_archive
    Consolidator.maybe_consolidate_by_tokens = orig_maybe_consolidate


class TestLoopPatch:
    @pytest.mark.asyncio
    async def test_mutating_tool_guard_blocks_mismatched_summary(self):
        from ava.patches.loop_patch import _wrap_mutating_tool_execute

        loop = SimpleNamespace(
            _pending_tool_guard={
                "declared_tool": "exec",
                "actual_tool_names": ["write_file"],
            }
        )

        async def original_execute(**kwargs):
            return "should not run"

        guarded = _wrap_mutating_tool_execute(loop, "write_file", original_execute)
        result = await guarded(path="/tmp/x.md", content="x")

        assert result.startswith("Error: blocked tool execution")
        assert "Tool: exec" in result

    @pytest.mark.asyncio
    async def test_mutating_tool_guard_allows_matching_summary(self):
        from ava.patches.loop_patch import _wrap_mutating_tool_execute

        loop = SimpleNamespace(
            _pending_tool_guard={
                "declared_tool": "write_file",
                "actual_tool_names": ["write_file"],
            }
        )

        async def original_execute(**kwargs):
            return "ok"

        guarded = _wrap_mutating_tool_execute(loop, "write_file", original_execute)
        result = await guarded(path="/tmp/x.md", content="x")

        assert result == "ok"

    def test_set_shared_db(self):
        """T3.7: set_shared_db stores the db reference."""
        from ava.patches.loop_patch import set_shared_db, _get_or_create_db

        mock_db = MagicMock()
        set_shared_db(mock_db)
        result = _get_or_create_db("/tmp/test")
        assert result is mock_db

        # Cleanup
        set_shared_db(None)

    def test_get_or_create_db_fallback(self, tmp_path):
        """T3.7b: _get_or_create_db creates new db when shared is None."""
        from ava.patches.loop_patch import set_shared_db, _get_or_create_db

        set_shared_db(None)
        result = _get_or_create_db(tmp_path)
        assert result is not None

        # Cleanup
        set_shared_db(None)

    def test_patch_applies_without_error(self):
        """T3.1-3.3: apply_loop_patch runs without error."""
        from ava.patches.a_schema_patch import apply_schema_patch
        apply_schema_patch()
        from ava.patches.loop_patch import apply_loop_patch

        result = apply_loop_patch()
        assert "AgentLoop patched" in result

    def test_process_message_patched(self):
        """T3.5: _process_message is wrapped after patch."""
        original = AgentLoop._process_message

        from ava.patches.a_schema_patch import apply_schema_patch
        apply_schema_patch()
        from ava.patches.loop_patch import apply_loop_patch
        apply_loop_patch()

        assert AgentLoop._process_message is not original

    def test_patch_result_mentions_new_modules(self):
        """New attributes mentioned in patch result string."""
        from ava.patches.a_schema_patch import apply_schema_patch
        apply_schema_patch()
        from ava.patches.loop_patch import apply_loop_patch

        result = apply_loop_patch()
        assert "categorized_memory" in result
        assert "summarizer" in result
        assert "compressor" in result
        assert "guarded" in result

    def test_idempotent(self):
        """T3.6: 连续应用两次不应重复包装。"""
        from ava.patches.a_schema_patch import apply_schema_patch
        apply_schema_patch()
        from ava.patches.loop_patch import apply_loop_patch

        apply_loop_patch()
        result = apply_loop_patch()
        assert "skipped" in result.lower()

    def test_get_agent_loop_uses_weakref(self):
        import ava.patches.loop_patch as loop_patch_module

        class DummyLoop:
            pass

        original_ref = loop_patch_module._agent_loop_ref
        try:
            loop = DummyLoop()
            loop_patch_module._agent_loop_ref = weakref.ref(loop)
            assert loop_patch_module.get_agent_loop() is loop

            loop_ref = weakref.ref(loop)
            del loop
            gc.collect()

            assert loop_ref() is None
            assert loop_patch_module.get_agent_loop() is None
        finally:
            loop_patch_module._agent_loop_ref = original_ref

    @pytest.mark.asyncio
    async def test_patched_maybe_consolidate_accepts_session_summary(self):
        # 回归：上游 nanobot.agent.loop 升级后会以 kwarg 传入 session_summary；
        # patched 版本若未透传，会抛 TypeError 并整条消息处理链中断，
        # 导致 chat 页面出现部分 turn 缺失 model name / token cost 的半成品。
        from ava.patches.a_schema_patch import apply_schema_patch
        from ava.patches.loop_patch import apply_loop_patch

        apply_schema_patch()
        apply_loop_patch()

        consolidator = Consolidator.__new__(Consolidator)
        consolidator.context_window_tokens = 0  # 命中方法内早退分支，无需构造真实依赖

        session = SimpleNamespace(key="telegram:999", messages=[])

        await consolidator.maybe_consolidate_by_tokens(session, session_summary="hi")

        assert getattr(consolidator, "_ava_current_session_key", None) is None

    def test_snapshot_content_limit_reads_config(self, monkeypatch):
        """snapshot_content_max_chars should come from config when available."""
        from ava.patches.loop_patch import _get_snapshot_content_max_chars

        monkeypatch.setattr(
            "nanobot.config.loader.load_config",
            lambda: SimpleNamespace(token_stats=SimpleNamespace(snapshot_content_max_chars=1234)),
        )

        assert _get_snapshot_content_max_chars() == 1234

    def test_snapshot_content_limit_falls_back_on_invalid_config(self, monkeypatch):
        """Invalid config values should not break token snapshot recording."""
        from ava.patches.loop_patch import _get_snapshot_content_max_chars

        monkeypatch.setattr(
            "nanobot.config.loader.load_config",
            lambda: SimpleNamespace(token_stats=SimpleNamespace(snapshot_content_max_chars=0)),
        )
        assert _get_snapshot_content_max_chars() == 3000

        def _raise():
            raise RuntimeError("boom")

        monkeypatch.setattr("nanobot.config.loader.load_config", _raise)
        assert _get_snapshot_content_max_chars() == 3000

    @pytest.mark.asyncio
    async def test_process_message_preserves_upstream_kwargs(self):
        """T3.6b: patched _process_message forwards pending_queue and future kwargs."""
        from ava.patches.loop_patch import apply_loop_patch

        captured: dict[str, object] = {}

        async def original_process_message(self, msg, **kwargs):
            captured["msg"] = msg
            captured["kwargs"] = kwargs
            return SimpleNamespace(content="ok")

        AgentLoop._process_message = original_process_message
        apply_loop_patch()

        pending_queue = object()
        loop = SimpleNamespace(bg_tasks=None, token_stats=None, bus=None)
        msg = SimpleNamespace(content="hello", session_key="")

        result = await AgentLoop._process_message(
            loop,
            msg,
            pending_queue=pending_queue,
            trace_context="future-compatible",
        )

        assert result.content == "ok"
        assert captured["msg"] is msg
        assert captured["kwargs"]["pending_queue"] is pending_queue
        assert captured["kwargs"]["trace_context"] == "future-compatible"


class TestTokenStatsRecordId:
    """token_stats_service.record() 返回 record_id 和 update_record() 测试。"""

    def test_record_returns_id(self, tmp_path):
        from ava.storage import Database
        db = Database(tmp_path / "test.db")
        from ava.console.services.token_stats_service import TokenStatsCollector
        collector = TokenStatsCollector(data_dir=tmp_path, db=db)

        rid = collector.record(
            model="test-model", provider="test",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            session_key="test:1", finish_reason="stop",
        )
        assert rid is not None
        assert isinstance(rid, int)

    def test_update_record(self, tmp_path):
        from ava.storage import Database
        db = Database(tmp_path / "test.db")
        from ava.console.services.token_stats_service import TokenStatsCollector
        collector = TokenStatsCollector(data_dir=tmp_path, db=db)

        rid = collector.record(
            model="test-model", provider="test",
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            session_key="test:1", finish_reason="pending", model_role="pending",
        )
        collector.update_record(rid, prompt_tokens=100, finish_reason="stop", model_role="chat")

        records = collector.get_records(limit=1)
        assert len(records) == 1
        assert records[0]["prompt_tokens"] == 100
        assert records[0]["finish_reason"] == "stop"
        assert records[0]["model_role"] == "chat"

    def test_update_record_rejects_unknown_fields(self, tmp_path):
        from ava.storage import Database
        db = Database(tmp_path / "test.db")
        from ava.console.services.token_stats_service import TokenStatsCollector
        collector = TokenStatsCollector(data_dir=tmp_path, db=db)

        rid = collector.record(
            model="m", provider="p",
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        )
        collector.update_record(rid, unknown_field="bad", prompt_tokens=50)
        records = collector.get_records(limit=1)
        assert records[0]["prompt_tokens"] == 50

    def test_session_query_backfills_turn_seq_before_filtering(self, tmp_path):
        from ava.storage import Database
        db = Database(tmp_path / "test.db")
        from ava.console.services.token_stats_service import TokenStatsCollector
        collector = TokenStatsCollector(data_dir=tmp_path, db=db)

        conn = db._get_conn()
        conn.execute(
            """INSERT INTO sessions (key, created_at, updated_at, metadata, token_stats)
               VALUES (?, ?, ?, ?, ?)""",
            (
                "telegram:1",
                "2026-04-05T20:00:00",
                "2026-04-05T20:02:00",
                "{}",
                "{}",
            ),
        )
        session_row = conn.execute("SELECT id FROM sessions WHERE key = ?", ("telegram:1",)).fetchone()
        assert session_row is not None

        conn.execute(
            """INSERT INTO session_messages
               (session_id, seq, role, content, tool_calls, tool_call_id, name, reasoning_content, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (session_row["id"], 0, "user", "first", None, None, None, None, "2026-04-05T20:00:00"),
        )
        conn.execute(
            """INSERT INTO session_messages
               (session_id, seq, role, content, tool_calls, tool_call_id, name, reasoning_content, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (session_row["id"], 1, "assistant", "reply-1", None, None, None, None, "2026-04-05T20:00:10"),
        )
        conn.execute(
            """INSERT INTO session_messages
               (session_id, seq, role, content, tool_calls, tool_call_id, name, reasoning_content, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (session_row["id"], 2, "user", "second", None, None, None, None, "2026-04-05T20:01:00"),
        )
        conn.execute(
            """INSERT INTO token_usage
               (timestamp, model, provider, prompt_tokens, completion_tokens, total_tokens,
                session_key, turn_seq, iteration, user_message, output_content,
                system_prompt_preview, conversation_history, full_request_payload, finish_reason,
                model_role, cached_tokens, cache_creation_tokens, cost_usd, current_turn_tokens,
                tool_names)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "2026-04-05T20:00:05",
                "model-a",
                "provider-a",
                10,
                5,
                15,
                "telegram:1",
                None,
                0,
                "",
                "",
                "",
                "",
                "",
                "stop",
                "chat",
                0,
                0,
                0.0,
                0,
                "",
            ),
        )
        conn.execute(
            """INSERT INTO token_usage
               (timestamp, model, provider, prompt_tokens, completion_tokens, total_tokens,
                session_key, turn_seq, iteration, user_message, output_content,
                system_prompt_preview, conversation_history, full_request_payload, finish_reason,
                model_role, cached_tokens, cache_creation_tokens, cost_usd, current_turn_tokens,
                tool_names)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "2026-04-05T20:01:05",
                "model-b",
                "provider-b",
                20,
                7,
                27,
                "telegram:1",
                None,
                0,
                "",
                "",
                "",
                "",
                "",
                "stop",
                "chat",
                0,
                0,
                0.0,
                0,
                "",
            ),
        )
        conn.commit()

        per_turn = collector.get_by_session("telegram:1")
        assert [row["turn_seq"] for row in per_turn] == [0, 2]

        filtered = collector.get_records(limit=10, session_key="telegram:1", turn_seq=2)
        assert len(filtered) == 1
        assert filtered[0]["model"] == "model-b"

    def test_legacy_records_without_conversation_id_stay_visible_in_global_audit(self, tmp_path):
        from ava.storage import Database
        db = Database(tmp_path / "test.db")
        from ava.console.services.token_stats_service import TokenStatsCollector
        collector = TokenStatsCollector(data_dir=tmp_path, db=db)

        collector.record(
            model="legacy-model",
            provider="provider",
            usage={"prompt_tokens": 8, "completion_tokens": 4, "total_tokens": 12},
            session_key="telegram:1",
            conversation_id="",
            turn_seq=0,
            finish_reason="stop",
            model_role="chat",
        )
        collector.record(
            model="current-model",
            provider="provider",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            session_key="telegram:1",
            conversation_id="conv_current",
            turn_seq=0,
            finish_reason="stop",
            model_role="chat",
        )

        all_records = collector.get_records(limit=10, session_key="telegram:1")
        assert {row["model"] for row in all_records} == {"legacy-model", "current-model"}

        filtered = collector.get_records(
            limit=10,
            session_key="telegram:1",
            conversation_id="conv_current",
        )
        assert len(filtered) == 1
        assert filtered[0]["model"] == "current-model"

    def test_explicit_empty_conversation_id_filters_legacy_records(self, tmp_path):
        from ava.storage import Database
        db = Database(tmp_path / "test.db")
        from ava.console.services.token_stats_service import TokenStatsCollector
        collector = TokenStatsCollector(data_dir=tmp_path, db=db)

        collector.record(
            model="legacy-model",
            provider="provider",
            usage={"prompt_tokens": 8, "completion_tokens": 4, "total_tokens": 12},
            session_key="telegram:1",
            conversation_id="",
            turn_seq=0,
            finish_reason="stop",
            model_role="chat",
        )
        collector.record(
            model="current-model",
            provider="provider",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            session_key="telegram:1",
            conversation_id="conv_current",
            turn_seq=0,
            finish_reason="stop",
            model_role="chat",
        )

        legacy_records = collector.get_records(
            limit=10,
            session_key="telegram:1",
            conversation_id="",
        )
        assert len(legacy_records) == 1
        assert legacy_records[0]["model"] == "legacy-model"

        legacy_turns = collector.get_by_session("telegram:1", conversation_id="")
        assert len(legacy_turns) == 1
        assert legacy_turns[0]["conversation_id"] == ""

    def test_session_query_backfills_legacy_iteration_and_is_idempotent(self, tmp_path):
        from ava.storage import Database
        db = Database(tmp_path / "test.db")
        from ava.console.services.token_stats_service import TokenStatsCollector
        collector = TokenStatsCollector(data_dir=tmp_path, db=db)

        conn = db._get_conn()
        rows = [
            ("2026-04-05T20:00:01", "telegram:1", "", 0, 0, "legacy-a"),
            ("2026-04-05T20:00:02", "telegram:1", "", 0, 0, "legacy-b"),
            ("2026-04-05T20:00:03", "telegram:1", "", 0, 0, "legacy-c"),
            ("2026-04-05T20:01:01", "telegram:1", "conv_keep", 1, 0, "keep-a"),
            ("2026-04-05T20:01:02", "telegram:1", "conv_keep", 1, 1, "keep-b"),
        ]
        for timestamp, session_key, conversation_id, turn_seq, iteration, model in rows:
            conn.execute(
                """INSERT INTO token_usage
                   (timestamp, model, provider, prompt_tokens, completion_tokens, total_tokens,
                    session_key, conversation_id, turn_seq, iteration, user_message, output_content,
                    system_prompt_preview, conversation_history, full_request_payload, finish_reason,
                    model_role, cached_tokens, cache_creation_tokens, cost_usd, current_turn_tokens,
                    tool_names)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    timestamp,
                    model,
                    "provider",
                    10,
                    5,
                    15,
                    session_key,
                    conversation_id,
                    turn_seq,
                    iteration,
                    "",
                    "",
                    "",
                    "",
                    "",
                    "stop",
                    "chat",
                    0,
                    0,
                    0.0,
                    0,
                    "",
                ),
            )
        conn.commit()

        legacy_details = collector.get_by_session_detailed("telegram:1", conversation_id="")
        assert [row["iteration"] for row in legacy_details] == [0, 1, 2]

        preserved = conn.execute(
            """SELECT iteration
                 FROM token_usage
                WHERE session_key = ? AND conversation_id = ? AND turn_seq = ?
                ORDER BY timestamp, id""",
            ("telegram:1", "conv_keep", 1),
        ).fetchall()
        assert [row["iteration"] for row in preserved] == [0, 1]

        assert db.backfill_iteration(session_key="telegram:1") == 0

    @pytest.mark.asyncio
    async def test_new_rotates_conversation_id_and_keeps_turn_zero_separate(self, tmp_path):
        from ava.patches.loop_patch import apply_loop_patch
        from ava.storage import Database
        from ava.console.services.token_stats_service import TokenStatsCollector

        class DummySession:
            def __init__(self):
                self.key = "telegram:1"
                self.metadata = {"conversation_id": "conv_old"}
                self.messages = [
                    {"role": "user", "content": "old question"},
                    {"role": "assistant", "content": "old answer"},
                ]

            def clear(self):
                self.messages = []

        class DummySessions:
            def __init__(self, session):
                self._session = session
                self.saved_metadata: list[dict[str, str]] = []

            def get_or_create(self, key):
                assert key == self._session.key
                return self._session

            def save(self, session):
                self.saved_metadata.append(dict(session.metadata))

        session = DummySession()
        sessions = DummySessions(session)
        db = Database(tmp_path / "test.db")
        collector = TokenStatsCollector(data_dir=tmp_path, db=db)
        observe_events: list[dict] = []

        class DummyBus:
            def dispatch_observe_event(self, session_key, event):
                observe_events.append({"session_key": session_key, **event})

        collector.record(
            model="model-old",
            provider="provider",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            session_key=session.key,
            conversation_id="conv_old",
            turn_seq=0,
            finish_reason="stop",
            model_role="chat",
        )

        captured: list[tuple[str, str, int | None]] = []

        async def original_process_message(self, msg, **kwargs):
            captured.append((msg.content, self._current_conversation_id, self._current_turn_seq))
            live_session = self.sessions.get_or_create(kwargs.get("session_key") or msg.session_key)
            if msg.content == "/new":
                live_session.clear()
                self.sessions.save(live_session)
                return SimpleNamespace(content="")

            live_session.messages.append({"role": "user", "content": msg.content})
            collector.record(
                model="model-new",
                provider="provider",
                usage={"prompt_tokens": 12, "completion_tokens": 6, "total_tokens": 18},
                session_key=live_session.key,
                conversation_id=self._current_conversation_id,
                turn_seq=self._current_turn_seq,
                finish_reason="stop",
                model_role="chat",
            )
            live_session.messages.append({"role": "assistant", "content": "reply"})
            self.sessions.save(live_session)
            return SimpleNamespace(content="reply")

        AgentLoop._process_message = original_process_message
        apply_loop_patch()

        loop = SimpleNamespace(
            sessions=sessions,
            bg_tasks=None,
            token_stats=collector,
            bus=DummyBus(),
        )

        await AgentLoop._process_message(loop, SimpleNamespace(content="/new", session_key=session.key))
        rotated_conversation_id = session.metadata["conversation_id"]

        assert rotated_conversation_id != "conv_old"
        assert captured[0] == ("/new", rotated_conversation_id, 1)
        assert any(
            event["type"] == "conversation_rotated"
            and event["session_key"] == session.key
            and event["old_conversation_id"] == "conv_old"
            and event["new_conversation_id"] == rotated_conversation_id
            for event in observe_events
        )

        await AgentLoop._process_message(loop, SimpleNamespace(content="fresh question", session_key=session.key))

        assert captured[1] == ("fresh question", rotated_conversation_id, 0)

        per_turn = collector.get_by_session(session.key)
        assert {(row["conversation_id"], row["turn_seq"]) for row in per_turn} == {
            ("conv_old", 0),
            (rotated_conversation_id, 0),
        }

        filtered = collector.get_records(
            limit=10,
            session_key=session.key,
            conversation_id=rotated_conversation_id,
            turn_seq=0,
        )
        assert len(filtered) == 1
        assert filtered[0]["model"] == "model-new"

    @pytest.mark.asyncio
    async def test_turn_completed_event_includes_conversation_and_turn_identity(self):
        from ava.patches.loop_patch import apply_loop_patch

        class DummySession:
            def __init__(self):
                self.key = "telegram:1"
                self.metadata = {"conversation_id": "conv_live"}
                self.messages = []

            def clear(self):
                self.messages = []

        class DummySessions:
            def __init__(self, session):
                self._session = session

            def get_or_create(self, key):
                assert key == self._session.key
                return self._session

            def save(self, session):
                self._session = session

        observe_events: list[dict] = []

        class DummyBus:
            def dispatch_observe_event(self, session_key, event):
                observe_events.append({"session_key": session_key, **event})

        async def original_process_message(self, msg, **kwargs):
            live_session = self.sessions.get_or_create(kwargs.get("session_key") or msg.session_key)
            live_session.messages.append({"role": "user", "content": msg.content})
            live_session.messages.append({"role": "assistant", "content": "reply"})
            self.sessions.save(live_session)
            return SimpleNamespace(content="reply")

        AgentLoop._process_message = original_process_message
        apply_loop_patch()

        session = DummySession()
        loop = SimpleNamespace(
            sessions=DummySessions(session),
            bg_tasks=None,
            token_stats=None,
            bus=DummyBus(),
        )

        await AgentLoop._process_message(loop, SimpleNamespace(content="fresh question", session_key=session.key))

        completed = next(event for event in observe_events if event["type"] == "turn_completed")

        assert completed["session_key"] == session.key
        assert completed["conversation_id"] == "conv_live"
        assert completed["turn_seq"] == 0

    @pytest.mark.asyncio
    async def test_run_agent_loop_observe_events_include_conversation_and_turn_identity(self):
        from ava.patches.loop_patch import apply_loop_patch

        observe_events: list[dict] = []

        class DummyBus:
            def dispatch_observe_event(self, session_key, event):
                observe_events.append({"session_key": session_key, **event})

        class DummyProvider:
            async def chat_with_retry(self, *args, **kwargs):
                return SimpleNamespace(content="reply", usage={}, finish_reason="stop")

            async def chat_stream_with_retry(self, *args, **kwargs):
                return SimpleNamespace(content="reply", usage={}, finish_reason="stop")

        async def original_run_agent_loop(self, initial_messages, **kwargs):
            return SimpleNamespace(content="reply")

        AgentLoop._run_agent_loop = original_run_agent_loop
        apply_loop_patch()

        loop = SimpleNamespace(
            bus=DummyBus(),
            token_stats=None,
            provider=DummyProvider(),
            model="test-model",
            _current_session_key="telegram:1",
            _current_conversation_id="conv_live",
            _current_user_message="fresh question",
            _current_turn_seq=0,
        )

        await AgentLoop._run_agent_loop(loop, initial_messages=[])

        arrived = next(event for event in observe_events if event["type"] == "message_arrived")
        started = next(event for event in observe_events if event["type"] == "processing_started")

        for event in (arrived, started):
            assert event["session_key"] == "telegram:1"
            assert event["conversation_id"] == "conv_live"
            assert event["turn_seq"] == 0
