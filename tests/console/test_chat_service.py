import json
import asyncio
from types import SimpleNamespace

import pytest
from nanobot.bus.events import OutboundMessage

from ava.console.services.chat_service import ChatService
from ava.storage import Database


def _create_service(tmp_path):
    db = Database(tmp_path / "chat.db")
    service = ChatService(agent_loop=None, workspace=tmp_path, db=db)
    return service, db


class _FakeAgentLoop:
    def __init__(self):
        self.calls: list[dict[str, object]] = []

    async def process_direct(
        self,
        content: str,
        *,
        session_key: str,
        channel: str,
        chat_id: str,
        on_progress=None,
        on_stream=None,
        on_stream_end=None,
        media=None,
    ):
        self.calls.append({
            "content": content,
            "session_key": session_key,
            "channel": channel,
            "chat_id": chat_id,
            "on_progress": on_progress,
            "on_stream": on_stream,
            "on_stream_end": on_stream_end,
            "media": media,
        })
        return "ok"


class _AgentContextLoop(_FakeAgentLoop):
    def __init__(self):
        super().__init__()
        self.contexts: list[dict[str, object]] = []

    async def process_direct(self, **kwargs):
        self.contexts.append(dict(getattr(self, "_current_chat_agent_context", {})))
        return await super().process_direct(**kwargs)


class _AgentSkillContextLoop(_FakeAgentLoop):
    def __init__(self):
        super().__init__()
        self.skill_contexts: list[dict[str, object]] = []

    async def process_direct(self, **kwargs):
        self.skill_contexts.append({
            "skill_names": list(getattr(self, "_ava_forced_skill_names", [])),
            "skill_contents": dict(getattr(self, "_ava_forced_skill_contents", {})),
        })
        return await super().process_direct(**kwargs)


class _CancellableAgentLoop:
    def __init__(self):
        self._active_tasks: dict[str, list[asyncio.Task]] = {}
        self.started = asyncio.Event()
        self.subagents = SimpleNamespace(cancel_by_session=self._cancel_subagents)
        self.bg_tasks = SimpleNamespace(cancel_by_session=self._cancel_bg_tasks)
        self.bg_cancelled: list[str] = []

    async def _cancel_subagents(self, _session_key: str) -> int:
        return 0

    async def _cancel_bg_tasks(self, session_key: str) -> int:
        self.bg_cancelled.append(session_key)
        return 2

    async def _cancel_active_tasks(self, key: str) -> int:
        tasks = self._active_tasks.pop(key, [])
        cancelled = sum(1 for task in tasks if not task.done() and task.cancel())
        for task in tasks:
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        return cancelled

    async def process_direct(self, **_kwargs):
        self.started.set()
        await asyncio.Event().wait()
        return "should not finish"


def _insert_session(db: Database, *, key: str, metadata: dict):
    db.execute(
        """
        INSERT INTO sessions (key, created_at, updated_at, metadata, token_stats)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            key,
            "2026-04-07T00:00:00+00:00",
            "2026-04-07T00:00:00+00:00",
            json.dumps(metadata, ensure_ascii=False),
            json.dumps({}, ensure_ascii=False),
        ),
    )
    db.commit()
    row = db.fetchone("SELECT id FROM sessions WHERE key = ?", (key,))
    assert row is not None
    return row["id"]


def _insert_message(
    db: Database,
    *,
    session_id: int,
    conversation_id: str,
    seq: int,
    role: str,
    content: str,
    timestamp: str,
    trace_id: str = "",
    from_agent_id: str = "",
    mentioned_agent_ids: list[str] | None = None,
):
    db.execute(
        """
        INSERT INTO session_messages
            (session_id, seq, conversation_id, trace_id, from_agent_id, mentioned_agent_ids, role, content, tool_calls, tool_call_id, name, reasoning_content, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            seq,
            conversation_id,
            trace_id,
            from_agent_id,
            json.dumps(mentioned_agent_ids or [], ensure_ascii=False),
            role,
            content,
            None,
            None,
            None,
            None,
            timestamp,
        ),
    )
    db.commit()


def _insert_message_row(
    db: Database,
    *,
    session_id: int,
    conversation_id: str,
    seq: int,
    role: str,
    content: str,
    timestamp: str,
    tool_calls: list[dict] | None = None,
    tool_call_id: str | None = None,
    name: str | None = None,
):
    db.execute(
        """
        INSERT INTO session_messages
            (session_id, seq, conversation_id, role, content, tool_calls, tool_call_id, name, reasoning_content, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            seq,
            conversation_id,
            role,
            content,
            json.dumps(tool_calls, ensure_ascii=False) if tool_calls else None,
            tool_call_id,
            name,
            None,
            timestamp,
        ),
    )
    db.commit()


def _insert_token_usage(
    db: Database,
    *,
    session_key: str,
    conversation_id: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    turn_seq: int,
    iteration: int = 0,
):
    db.execute(
        """
        INSERT INTO token_usage
            (timestamp, model, provider, prompt_tokens, completion_tokens, total_tokens,
             session_key, conversation_id, turn_seq, iteration, finish_reason, model_role)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "2026-04-07T00:00:00+00:00",
            "test-model",
            "test-provider",
            prompt_tokens,
            completion_tokens,
            total_tokens,
            session_key,
            conversation_id,
            turn_seq,
            iteration,
            "stop",
            "chat",
        ),
    )
    db.commit()


def test_get_messages_defaults_to_active_conversation(tmp_path):
    service, db = _create_service(tmp_path)
    session_id = _insert_session(
        db,
        key="telegram:1",
        metadata={"conversation_id": "conv_current"},
    )

    _insert_message(
        db,
        session_id=session_id,
        conversation_id="conv_old",
        seq=0,
        role="user",
        content="old question",
        timestamp="2026-04-07T00:00:00+00:00",
    )
    _insert_message(
        db,
        session_id=session_id,
        conversation_id="conv_current",
        seq=0,
        role="user",
        content="current question",
        timestamp="2026-04-07T01:00:00+00:00",
        trace_id="trace-current",
    )

    active_messages = service.get_messages("telegram:1")
    old_messages = service.get_messages("telegram:1", conversation_id="conv_old")

    assert [msg["content"] for msg in active_messages] == ["current question"]
    assert active_messages[0]["trace_id"] == "trace-current"
    assert active_messages[0]["metadata"]["trace_id"] == "trace-current"
    assert [msg["content"] for msg in old_messages] == ["old question"]


def test_create_session_persists_participants_from_request(tmp_path):
    service, db = _create_service(tmp_path)

    created = service.create_session(
        "tester",
        title="Multi agent",
        participants=["nanobot", "codex", "codex:default"],
    )
    sessions = service.list_sessions()

    assert created["session_id"]
    assert sessions[0]["title"] == "Multi agent"
    assert sessions[0]["participants"] == ["nanobot", "codex"]
    row = db.fetchone("SELECT metadata FROM sessions WHERE key = ?", (f"console:{created['session_id']}",))
    assert row is not None
    assert json.loads(row["metadata"])["participants"] == ["nanobot", "codex"]


def test_context_size_uses_recorded_prompt_tokens_and_breakdown(tmp_path):
    service, db = _create_service(tmp_path)
    created = service.create_session("tester")
    service.record_console_message(
        created["session_id"],
        role="user",
        content="summarize this short thread",
        from_agent_id="user",
    )
    _insert_token_usage(
        db,
        session_key=f"console:{created['session_id']}",
        conversation_id=created["conversation_id"],
        prompt_tokens=123,
        completion_tokens=10,
        total_tokens=133,
        turn_seq=0,
    )

    result = service.get_context_size(created["session_id"])

    assert result["used_tokens"] == 123
    assert result["model_limit"] == 200_000
    assert result["breakdown"]["recorded_prompt"] == 123
    assert "messages" in result["breakdown"]


def test_compress_context_persists_history_and_keeps_recent_messages(tmp_path):
    service, _db = _create_service(tmp_path)
    created = service.create_session("tester")
    for index in range(10):
        content = (
            f"recent message {index}"
            if index >= 8
            else f"old message {index} " + ("important details " * 80)
        )
        service.record_console_message(
            created["session_id"],
            role="user" if index % 2 == 0 else "assistant",
            content=content,
            from_agent_id="user" if index % 2 == 0 else "nanobot",
        )

    result = service.compress_context(created["session_id"], keep_recent=4)

    assert result["after_tokens"] < result["before_tokens"]
    assert "compression_preview" in result
    assert "before_after_diff" in result
    assert [item["content"] for item in result["before_after_diff"]["kept_messages"]][-2:] == [
        "recent message 8",
        "recent message 9",
    ]
    history = service.list_context_compressions(created["session_id"])
    assert len(history) == 1
    assert history[0]["before_tokens"] == result["before_tokens"]


def test_create_session_defaults_to_console_default_responder(tmp_path):
    (tmp_path / "console").mkdir()
    (tmp_path / "console" / "console-config.json").write_text(
        json.dumps({"gateway": {"console": {"defaultResponderAgentId": "codex"}}}),
        encoding="utf-8",
    )
    service, _db = _create_service(tmp_path)

    service.create_session("tester")
    sessions = service.list_sessions()

    assert sessions[0]["default_responder_agent_id"] == "codex"
    assert sessions[0]["participants"] == ["codex"]
    assert service.get_session_default_responder_agent_id(sessions[0]["key"].split(":", 1)[1]) == "codex"


def test_get_messages_returns_agent_metadata_and_legacy_defaults(tmp_path):
    service, db = _create_service(tmp_path)
    session_id = _insert_session(
        db,
        key="console:abc123",
        metadata={"conversation_id": "conv_agents", "participants": ["nanobot", "codex"]},
    )
    _insert_message(
        db,
        session_id=session_id,
        conversation_id="conv_agents",
        seq=0,
        role="user",
        content="@codex write code",
        timestamp="2026-04-07T01:00:00+00:00",
        from_agent_id="user",
        mentioned_agent_ids=["codex"],
    )
    _insert_message(
        db,
        session_id=session_id,
        conversation_id="conv_agents",
        seq=1,
        role="assistant",
        content="done",
        timestamp="2026-04-07T01:00:10+00:00",
    )

    messages = service.get_messages("console:abc123")

    assert messages[0]["from_agent_id"] == "user"
    assert messages[0]["mentioned_agent_ids"] == ["codex"]
    assert messages[0]["metadata"]["mentioned_agent_ids"] == ["codex"]
    assert messages[1]["from_agent_id"] == "nanobot"
    assert messages[1]["mentioned_agent_ids"] == []


def test_record_console_message_persists_agent_metadata(tmp_path):
    service, db = _create_service(tmp_path)
    created = service.create_session("tester", participants=["nanobot", "codex"])

    record = service.record_console_message(
        created["session_id"],
        role="user",
        content="@codex write code",
        from_agent_id="user",
        mentioned_agent_ids=["codex"],
    )
    service.record_console_message(
        created["session_id"],
        role="assistant",
        content="[Background Task task_1 QUEUED]\nType: codex | Duration: 0ms",
        from_agent_id="codex",
    )

    messages = service.get_messages(f"console:{created['session_id']}")

    assert record["conversation_id"] == created["conversation_id"]
    assert record["turn_seq"] == 0
    assert [message["from_agent_id"] for message in messages] == ["user", "codex"]
    assert messages[0]["mentioned_agent_ids"] == ["codex"]
    rows = db.fetchall("SELECT seq, from_agent_id FROM session_messages ORDER BY seq")
    assert [(row["seq"], row["from_agent_id"]) for row in rows] == [(0, "user"), (1, "codex")]


def test_next_console_turn_ref_predicts_active_conversation_turn(tmp_path):
    service, _db = _create_service(tmp_path)
    created = service.create_session("tester", participants=["nanobot"])

    first = service.next_console_turn_ref(created["session_id"])

    assert first == {
        "session_key": f"console:{created['session_id']}",
        "conversation_id": created["conversation_id"],
        "turn_seq": 0,
    }

    service.record_console_message(
        created["session_id"],
        role="user",
        content="first task",
        from_agent_id="user",
    )

    second = service.next_console_turn_ref(created["session_id"])
    assert second["conversation_id"] == created["conversation_id"]
    assert second["turn_seq"] == 1


def test_get_history_includes_trace_id(tmp_path):
    service, db = _create_service(tmp_path)
    session_id = _insert_session(
        db,
        key="console:abc123",
        metadata={"conversation_id": "conv_history"},
    )
    _insert_message(
        db,
        session_id=session_id,
        conversation_id="conv_history",
        seq=0,
        role="user",
        content="question",
        timestamp="2026-04-07T01:00:00+00:00",
        trace_id="trace-history",
    )

    messages = service.get_history("abc123")

    assert messages == [
        {
            "role": "user",
            "content": "question",
            "timestamp": "2026-04-07T01:00:00+00:00",
            "trace_id": "trace-history",
        }
    ]


def test_get_messages_by_trace_id_returns_session_metadata(tmp_path):
    service, db = _create_service(tmp_path)
    session_id = _insert_session(
        db,
        key="console:abc123",
        metadata={"conversation_id": "conv_trace"},
    )
    _insert_message(
        db,
        session_id=session_id,
        conversation_id="conv_trace",
        seq=0,
        role="user",
        content="trace question",
        timestamp="2026-04-07T01:00:00+00:00",
        trace_id="trace-deeplink",
    )
    _insert_message(
        db,
        session_id=session_id,
        conversation_id="conv_other",
        seq=0,
        role="user",
        content="other question",
        timestamp="2026-04-07T02:00:00+00:00",
        trace_id="trace-other",
    )

    messages = service.get_messages_by_trace_id("trace-deeplink")

    assert [msg["content"] for msg in messages] == ["trace question"]
    assert messages[0]["trace_id"] == "trace-deeplink"
    assert messages[0]["metadata"] == {
        "session_key": "console:abc123",
        "conversation_id": "conv_trace",
        "trace_id": "trace-deeplink",
        "from_agent_id": "user",
        "mentioned_agent_ids": [],
    }


@pytest.mark.asyncio
async def test_send_message_passes_media_paths_to_agent_loop(tmp_path):
    agent_loop = _FakeAgentLoop()
    service = ChatService(agent_loop=agent_loop, workspace=tmp_path, db=None)

    result = await service.send_message(
        session_id="abc123",
        message="describe this",
        user_id="tester",
        media=["/tmp/example.png"],
    )

    assert result == "ok"
    assert agent_loop.calls == [{
        "content": "describe this",
        "session_key": "console:abc123",
        "channel": "console",
        "chat_id": "tester",
        "on_progress": None,
        "on_stream": None,
        "on_stream_end": None,
        "media": ["/tmp/example.png"],
    }]


@pytest.mark.asyncio
async def test_send_message_sets_agent_context_and_merges_mentions(tmp_path):
    agent_loop = _AgentContextLoop()
    db = Database(tmp_path / "chat.db")
    service = ChatService(agent_loop=agent_loop, workspace=tmp_path, db=db)
    created = service.create_session("tester", participants=["nanobot"])

    result = await service.send_message(
        session_id=created["session_id"],
        message="@codex write tests",
        user_id="tester",
    )

    assert result == "ok"
    assert agent_loop.contexts == [{
        "from_agent_id": "user",
        "mentioned_agent_ids": ["codex"],
        "default_responder_agent_id": "nanobot",
    }]
    assert not hasattr(agent_loop, "_current_chat_agent_context")
    session = service.list_sessions()[0]
    assert session["participants"] == ["nanobot", "codex"]


@pytest.mark.asyncio
async def test_send_message_sets_forced_skill_context(tmp_path):
    agent_loop = _AgentSkillContextLoop()
    service = ChatService(agent_loop=agent_loop, workspace=tmp_path, db=None)

    result = await service.send_message(
        session_id="abc123",
        message="write summary",
        user_id="tester",
        skill_names=["my-skill"],
        skill_contents={"my-skill": "# My Skill\n\nUse this skill."},
    )

    assert result == "ok"
    assert agent_loop.skill_contexts == [{
        "skill_names": ["my-skill"],
        "skill_contents": {"my-skill": "# My Skill\n\nUse this skill."},
    }]
    assert not hasattr(agent_loop, "_ava_forced_skill_names")
    assert not hasattr(agent_loop, "_ava_forced_skill_contents")


@pytest.mark.asyncio
async def test_stop_session_cancels_tracked_console_turn_and_bg_tasks(tmp_path):
    agent_loop = _CancellableAgentLoop()
    service = ChatService(agent_loop=agent_loop, workspace=tmp_path, db=None)

    send_task = asyncio.create_task(
        service.send_message(
            session_id="abc123",
            message="long task",
            user_id="tester",
        )
    )
    await agent_loop.started.wait()

    active_tasks = agent_loop._active_tasks["console:abc123"]
    assert len(active_tasks) == 1
    assert active_tasks[0] is not send_task

    result = await service.stop_session("abc123")

    assert result == {
        "ok": True,
        "stopped": 3,
        "message": "Stopped 3 task(s).",
    }
    assert agent_loop.bg_cancelled == ["console:abc123"]
    with pytest.raises(asyncio.CancelledError):
        await send_task


@pytest.mark.asyncio
async def test_send_message_passes_on_stream_to_agent_loop(tmp_path):
    agent_loop = _FakeAgentLoop()
    service = ChatService(agent_loop=agent_loop, workspace=tmp_path, db=None)

    async def on_stream(_chunk: str):
        return None

    result = await service.send_message(
        session_id="abc123",
        message="stream this",
        user_id="tester",
        on_stream=on_stream,
    )

    assert result == "ok"
    assert agent_loop.calls == [{
        "content": "stream this",
        "session_key": "console:abc123",
        "channel": "console",
        "chat_id": "tester",
        "on_progress": None,
        "on_stream": on_stream,
        "on_stream_end": None,
        "media": None,
    }]


@pytest.mark.asyncio
async def test_send_message_returns_text_from_outbound_message(tmp_path):
    class _OutboundAgentLoop(_FakeAgentLoop):
        async def process_direct(
            self,
            content: str,
            *,
            session_key: str,
            channel: str,
            chat_id: str,
            on_progress=None,
            on_stream=None,
            on_stream_end=None,
            media=None,
        ):
            self.calls.append({
                "content": content,
                "session_key": session_key,
                "channel": channel,
                "chat_id": chat_id,
                "on_progress": on_progress,
                "on_stream": on_stream,
                "on_stream_end": on_stream_end,
                "media": media,
            })
            return OutboundMessage(
                channel="console",
                chat_id=chat_id,
                content="done",
                metadata={"session_key": session_key},
            )

    agent_loop = _OutboundAgentLoop()
    service = ChatService(agent_loop=agent_loop, workspace=tmp_path, db=None)

    result = await service.send_message(
        session_id="abc123",
        message="finish this",
        user_id="tester",
    )

    assert result == "done"


@pytest.mark.asyncio
async def test_send_message_passes_on_stream_end_to_agent_loop(tmp_path):
    agent_loop = _FakeAgentLoop()
    service = ChatService(agent_loop=agent_loop, workspace=tmp_path, db=None)

    async def on_stream_end(*, resuming: bool):
        return None

    result = await service.send_message(
        session_id="abc123",
        message="stream this",
        user_id="tester",
        on_stream_end=on_stream_end,
    )

    assert result == "ok"
    assert agent_loop.calls == [{
        "content": "stream this",
        "session_key": "console:abc123",
        "channel": "console",
        "chat_id": "tester",
        "on_progress": None,
        "on_stream": None,
        "on_stream_end": on_stream_end,
        "media": None,
    }]


def test_list_conversations_returns_active_and_synthetic_empty_active(tmp_path):
    service, db = _create_service(tmp_path)
    session_id = _insert_session(
        db,
        key="telegram:2",
        metadata={"conversation_id": "conv_active"},
    )

    _insert_message(
        db,
        session_id=session_id,
        conversation_id="conv_old",
        seq=0,
        role="user",
        content="older branch",
        timestamp="2026-04-07T00:00:00+00:00",
    )

    conversations = service.list_conversations("telegram:2")

    assert [item["conversation_id"] for item in conversations] == ["conv_active", "conv_old"]
    assert conversations[0]["is_active"] is True
    assert conversations[0]["message_count"] == 0
    assert conversations[1]["first_message_preview"] == "older branch"


def test_get_messages_supports_explicit_legacy_conversation_id(tmp_path):
    service, db = _create_service(tmp_path)
    session_id = _insert_session(
        db,
        key="telegram:3",
        metadata={"conversation_id": "conv_current"},
    )

    _insert_message(
        db,
        session_id=session_id,
        conversation_id="",
        seq=0,
        role="user",
        content="legacy question",
        timestamp="2026-04-07T00:00:00+00:00",
    )
    _insert_message(
        db,
        session_id=session_id,
        conversation_id="conv_current",
        seq=0,
        role="user",
        content="current question",
        timestamp="2026-04-07T01:00:00+00:00",
    )

    conversations = service.list_conversations("telegram:3")
    assert [item["conversation_id"] for item in conversations] == ["conv_current", ""]

    legacy_messages = service.get_messages("telegram:3", conversation_id="")
    assert [msg["content"] for msg in legacy_messages] == ["legacy question"]


def test_list_sessions_uses_live_token_usage_for_active_conversation_when_cached_stats_are_stale(tmp_path):
    service, db = _create_service(tmp_path)
    session_key = "console:1"
    _insert_session(
        db,
        key=session_key,
        metadata={
            "conversation_id": "conv_live",
            "token_stats": {
                "total_prompt_tokens": 0,
                "total_completion_tokens": 0,
                "total_tokens": 0,
                "llm_calls": 0,
            },
        },
    )
    db.execute(
        "UPDATE sessions SET token_stats = ? WHERE key = ?",
        (
            json.dumps(
                {
                    "total_prompt_tokens": 0,
                    "total_completion_tokens": 0,
                    "total_tokens": 0,
                    "llm_calls": 0,
                },
                ensure_ascii=False,
            ),
            session_key,
        ),
    )
    db.commit()

    _insert_token_usage(
        db,
        session_key=session_key,
        conversation_id="conv_live",
        prompt_tokens=10,
        completion_tokens=2,
        total_tokens=12,
        turn_seq=0,
        iteration=0,
    )
    _insert_token_usage(
        db,
        session_key=session_key,
        conversation_id="conv_live",
        prompt_tokens=5,
        completion_tokens=3,
        total_tokens=8,
        turn_seq=1,
        iteration=0,
    )
    _insert_token_usage(
        db,
        session_key=session_key,
        conversation_id="conv_old",
        prompt_tokens=100,
        completion_tokens=20,
        total_tokens=120,
        turn_seq=0,
        iteration=0,
    )

    sessions = service.list_sessions()

    assert len(sessions) == 1
    assert sessions[0]["conversation_id"] == "conv_live"
    assert sessions[0]["token_stats"] == {
        "total_prompt_tokens": 15,
        "total_completion_tokens": 5,
        "total_tokens": 20,
        "llm_calls": 2,
    }


def test_get_messages_repairs_retry_duplicate_and_toolcall_text_duplication(tmp_path):
    service, db = _create_service(tmp_path)
    session_id = _insert_session(
        db,
        key="telegram:4",
        metadata={"conversation_id": "conv_live"},
    )

    _insert_message_row(
        db,
        session_id=session_id,
        conversation_id="conv_live",
        seq=0,
        role="user",
        content="same prompt",
        timestamp="2026-04-16T16:24:46.173563",
    )
    _insert_message_row(
        db,
        session_id=session_id,
        conversation_id="conv_live",
        seq=1,
        role="user",
        content="same prompt",
        timestamp="2026-04-16T16:27:17.598893",
    )
    _insert_message_row(
        db,
        session_id=session_id,
        conversation_id="conv_live",
        seq=2,
        role="assistant",
        content="duplicate answer",
        tool_calls=[{
            "id": "call_1",
            "type": "function",
            "function": {"name": "send_sticker", "arguments": "{\"sticker_id\": 1}"},
        }],
        timestamp="2026-04-16T16:27:17.598909",
    )
    _insert_message_row(
        db,
        session_id=session_id,
        conversation_id="conv_live",
        seq=3,
        role="tool",
        content="send_sticker, 👍",
        tool_call_id="call_1",
        name="send_sticker",
        timestamp="2026-04-16T16:27:17.598911",
    )
    _insert_message_row(
        db,
        session_id=session_id,
        conversation_id="conv_live",
        seq=4,
        role="assistant",
        content="duplicate answer",
        timestamp="2026-04-16T16:27:17.598916",
    )

    messages = service.get_messages("telegram:4")

    assert [(msg["role"], msg["content"]) for msg in messages] == [
        ("user", "same prompt"),
        ("assistant", ""),
        ("tool", "send_sticker, 👍"),
        ("assistant", "duplicate answer"),
    ]

    rows = db.fetchall(
        """
        SELECT seq, role, content
          FROM session_messages
         WHERE session_id = ? AND conversation_id = ?
         ORDER BY seq
        """,
        (session_id, "conv_live"),
    )
    assert [(row["seq"], row["role"], row["content"]) for row in rows] == [
        (0, "user", "same prompt"),
        (2, "assistant", ""),
        (3, "tool", "send_sticker, 👍"),
        (4, "assistant", "duplicate answer"),
    ]


def test_get_messages_repairs_duplicate_tool_call_rows(tmp_path):
    service, db = _create_service(tmp_path)
    session_id = _insert_session(
        db,
        key="telegram:5",
        metadata={"conversation_id": "conv_live"},
    )

    tool_calls = [{
        "id": "call_dup",
        "type": "function",
        "function": {"name": "send_sticker", "arguments": "{\"sticker_id\": 8}"},
    }]

    _insert_message_row(
        db,
        session_id=session_id,
        conversation_id="conv_live",
        seq=0,
        role="user",
        content="老板说okr周五之前交上来，你有什么想法吗",
        timestamp="2026-04-20T20:19:51.444936",
    )
    for seq in (1, 1, 1):
        _insert_message_row(
            db,
            session_id=session_id,
            conversation_id="conv_live",
            seq=seq,
            role="assistant",
            content="",
            tool_calls=tool_calls,
            timestamp="2026-04-20T20:20:17.659672",
        )
    _insert_message_row(
        db,
        session_id=session_id,
        conversation_id="conv_live",
        seq=2,
        role="tool",
        content="send_sticker, 💡",
        tool_call_id="call_dup",
        name="send_sticker",
        timestamp="2026-04-20T20:20:17.659675",
    )
    _insert_message_row(
        db,
        session_id=session_id,
        conversation_id="conv_live",
        seq=3,
        role="assistant",
        content="哦这个，聊到工作了。",
        timestamp="2026-04-20T20:20:17.659677",
    )

    messages = service.get_messages("telegram:5")

    assert [(msg["role"], msg["content"]) for msg in messages] == [
        ("user", "老板说okr周五之前交上来，你有什么想法吗"),
        ("assistant", ""),
        ("tool", "send_sticker, 💡"),
        ("assistant", "哦这个，聊到工作了。"),
    ]
    assert len([msg for msg in messages if msg.get("tool_calls")]) == 1

    rows = db.fetchall(
        """
        SELECT seq, role, content, tool_calls
          FROM session_messages
         WHERE session_id = ? AND conversation_id = ?
         ORDER BY seq, id
        """,
        (session_id, "conv_live"),
    )
    assert [(row["seq"], row["role"], row["content"]) for row in rows] == [
        (0, "user", "老板说okr周五之前交上来，你有什么想法吗"),
        (1, "assistant", ""),
        (2, "tool", "send_sticker, 💡"),
        (3, "assistant", "哦这个，聊到工作了。"),
    ]


def test_get_messages_repairs_duplicate_background_task_rows(tmp_path):
    service, db = _create_service(tmp_path)
    session_id = _insert_session(
        db,
        key="telegram:6",
        metadata={"conversation_id": "conv_live"},
    )

    summary = (
        "[Background Task c9031eb1e76d SUCCESS]\n"
        "Type: codex | Duration: 554444ms\n\n"
        "只读结论"
    )
    continuation = (
        "[Background Task Completed — SUCCESS]\n"
        "Task: codex:c9031eb1e76d\n"
        "Duration: 554444ms\n\n"
        "只读结论\n\n"
        "请基于以上结果继续处理后续步骤。如果所有工作已完成，请总结。"
    )

    _insert_message_row(
        db,
        session_id=session_id,
        conversation_id="conv_live",
        seq=0,
        role="user",
        content="你让codex哥研究一下ava仓库",
        timestamp="2026-04-20T20:22:49.463318",
    )
    for _ in range(4):
        _insert_message_row(
            db,
            session_id=session_id,
            conversation_id="conv_live",
            seq=1,
            role="assistant",
            content=summary,
            timestamp="1776688335.40905",
        )
    _insert_message_row(
        db,
        session_id=session_id,
        conversation_id="conv_live",
        seq=2,
        role="user",
        content=continuation,
        timestamp="2026-04-20T20:32:15.650320",
    )

    messages = service.get_messages("telegram:6")

    assert [(msg["role"], msg["content"]) for msg in messages] == [
        ("user", "你让codex哥研究一下ava仓库"),
        ("assistant", summary),
        ("user", continuation),
    ]

    rows = db.fetchall(
        """
        SELECT seq, role, content
          FROM session_messages
         WHERE session_id = ? AND conversation_id = ?
         ORDER BY seq, id
        """,
        (session_id, "conv_live"),
    )
    assert [(row["seq"], row["role"], row["content"]) for row in rows] == [
        (0, "user", "你让codex哥研究一下ava仓库"),
        (1, "assistant", summary),
        (2, "user", continuation),
    ]


def test_get_messages_resequences_colliding_seq_rows_by_timestamp(tmp_path):
    service, db = _create_service(tmp_path)
    session_id = _insert_session(
        db,
        key="telegram:7",
        metadata={"conversation_id": "conv_live"},
    )

    tool_calls = [{
        "id": "call_old",
        "type": "function",
        "function": {"name": "send_sticker", "arguments": "{\"sticker_id\": 8}"},
    }]

    _insert_message_row(
        db,
        session_id=session_id,
        conversation_id="conv_live",
        seq=260,
        role="user",
        content="老板说okr周五之前交上来，你有什么想法吗",
        timestamp="2026-04-20T20:19:51.444936",
    )
    _insert_message_row(
        db,
        session_id=session_id,
        conversation_id="conv_live",
        seq=261,
        role="assistant",
        content="",
        tool_calls=tool_calls,
        timestamp="2026-04-20T20:20:17.659672",
    )
    _insert_message_row(
        db,
        session_id=session_id,
        conversation_id="conv_live",
        seq=264,
        role="tool",
        content="send_sticker, 💡",
        tool_call_id="call_old",
        name="send_sticker",
        timestamp="2026-04-20T20:20:17.659675",
    )
    _insert_message_row(
        db,
        session_id=session_id,
        conversation_id="conv_live",
        seq=265,
        role="assistant",
        content="哦这个，聊到工作了。",
        timestamp="2026-04-20T20:20:17.659677",
    )
    _insert_message_row(
        db,
        session_id=session_id,
        conversation_id="conv_live",
        seq=260,
        role="user",
        content="前端果然在2026年死了。",
        timestamp="2026-04-20T20:51:48.842226",
    )
    _insert_message_row(
        db,
        session_id=session_id,
        conversation_id="conv_live",
        seq=261,
        role="assistant",
        content="就这一个瞬间，我突然理解了为什么程序员也需要心理疏导。",
        timestamp="2026-04-20T20:52:07.651410",
    )

    messages = service.get_messages("telegram:7")

    assert [(msg["role"], msg["content"]) for msg in messages] == [
        ("user", "老板说okr周五之前交上来，你有什么想法吗"),
        ("assistant", ""),
        ("tool", "send_sticker, 💡"),
        ("assistant", "哦这个，聊到工作了。"),
        ("user", "前端果然在2026年死了。"),
        ("assistant", "就这一个瞬间，我突然理解了为什么程序员也需要心理疏导。"),
    ]

    rows = db.fetchall(
        """
        SELECT seq, role, content
          FROM session_messages
         WHERE session_id = ? AND conversation_id = ?
         ORDER BY seq, id
        """,
        (session_id, "conv_live"),
    )
    assert [(row["seq"], row["role"], row["content"]) for row in rows] == [
        (0, "user", "老板说okr周五之前交上来，你有什么想法吗"),
        (1, "assistant", ""),
        (2, "tool", "send_sticker, 💡"),
        (3, "assistant", "哦这个，聊到工作了。"),
        (4, "user", "前端果然在2026年死了。"),
        (5, "assistant", "就这一个瞬间，我突然理解了为什么程序员也需要心理疏导。"),
    ]
