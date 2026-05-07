from __future__ import annotations

from types import SimpleNamespace

import pytest

from nanobot.agent.loop import AgentLoop, _LoopHook
from nanobot.agent.memory import Consolidator


@pytest.fixture(autouse=True)
def _restore_agent_loop():
    orig_init = AgentLoop.__init__
    orig_loop_hook_init = _LoopHook.__init__
    orig_loop_hook_on_stream = _LoopHook.on_stream
    orig_loop_hook_on_stream_end = _LoopHook.on_stream_end
    orig_set_tool_context = AgentLoop._set_tool_context
    orig_run_agent_loop = AgentLoop._run_agent_loop
    orig_save_turn = AgentLoop._save_turn
    orig_process = AgentLoop._process_message
    orig_archive = Consolidator.archive
    orig_maybe_consolidate = Consolidator.maybe_consolidate_by_tokens
    yield
    AgentLoop.__init__ = orig_init
    _LoopHook.__init__ = orig_loop_hook_init
    _LoopHook.on_stream = orig_loop_hook_on_stream
    _LoopHook.on_stream_end = orig_loop_hook_on_stream_end
    AgentLoop._set_tool_context = orig_set_tool_context
    AgentLoop._run_agent_loop = orig_run_agent_loop
    AgentLoop._save_turn = orig_save_turn
    AgentLoop._process_message = orig_process
    Consolidator.archive = orig_archive
    Consolidator.maybe_consolidate_by_tokens = orig_maybe_consolidate


@pytest.mark.asyncio
async def test_loop_patch_creates_root_build_context_and_chat_span(tmp_path):
    from ava.console.services.token_stats_service import TokenStatsCollector
    from ava.console.services.trace_spans_service import TraceSpanStore
    from ava.patches.a_schema_patch import apply_schema_patch
    from ava.patches.loop_patch import apply_loop_patch
    from ava.storage import Database

    class DummyProvider:
        async def chat_with_retry(self, *args, **kwargs):
            return SimpleNamespace(
                usage={"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
                finish_reason="stop",
                content="hello",
                tool_calls=[],
            )

    async def original_run_agent_loop(self, initial_messages, **kwargs):
        return await self.provider.chat_with_retry(messages=initial_messages)

    AgentLoop._run_agent_loop = original_run_agent_loop
    apply_schema_patch()
    apply_loop_patch()

    db = Database(tmp_path / "loop-trace.sqlite3")
    trace_store = TraceSpanStore(db)
    collector = TokenStatsCollector(data_dir=tmp_path, db=db, trace_spans=trace_store)
    loop = SimpleNamespace(
        provider=DummyProvider(),
        model="mock-model",
        token_stats=collector,
        trace_spans=trace_store,
        bus=None,
        _current_session_key="console:trace",
        _current_conversation_id="conv-trace",
        _current_user_message="hello",
        _current_turn_seq=0,
    )

    from ava.patches.loop_patch import _token_record_context

    trace_id = "fedcba9876543210fedcba9876543210"
    token = _token_record_context.set({
        "session_key": "console:trace",
        "conversation_id": "conv-trace",
        "user_message": "hello",
        "turn_seq": 0,
        "trace_id": trace_id,
        "record_ids": [],
        "turn_iteration": 0,
        "phase0_record_id": None,
    })
    try:
        result = await AgentLoop._run_agent_loop(
            loop,
            [{"role": "user", "content": "hello"}],
        )
    finally:
        _token_record_context.reset(token)

    assert result.content == "hello"
    rows = db.fetchall("SELECT trace_id, span_id, parent_span_id, prompt_tokens FROM token_usage")
    assert len(rows) == 1
    assert rows[0]["trace_id"] == trace_id
    assert rows[0]["prompt_tokens"] == 3

    spans = db.fetchall(
        "SELECT trace_id, span_id, parent_span_id, operation_name, status, end_ns FROM trace_spans ORDER BY start_ns, id"
    )
    assert {row["trace_id"] for row in spans} == {trace_id}
    operations = [row["operation_name"] for row in spans]
    assert operations == ["invoke_agent", "build_context", "chat"]
    assert rows[0]["span_id"] == spans[2]["span_id"]
    assert rows[0]["parent_span_id"] == spans[0]["span_id"]
    assert all(row["status"] == "ok" for row in spans)
    assert all(row["end_ns"] is not None for row in spans)
