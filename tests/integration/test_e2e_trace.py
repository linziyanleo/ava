from __future__ import annotations

import pytest

from ava.agent.bg_tasks import BackgroundTaskStore
from ava.console.services.token_stats_service import TokenStatsCollector
from ava.console.services.trace_context import end_span_sync, start_span_sync
from ava.console.services.trace_spans_service import TraceSpanStore
from ava.storage import Database


@pytest.mark.asyncio
async def test_trace_joins_main_chat_and_background_task(tmp_path):
    db = Database(tmp_path / "e2e-trace.sqlite3")
    trace_store = TraceSpanStore(db)
    token_stats = TokenStatsCollector(data_dir=tmp_path, db=db, trace_spans=trace_store)
    bg_tasks = BackgroundTaskStore(db=db, trace_spans=trace_store)

    async def bg_executor(**_kwargs):
        token_stats.record(
            model="bg-model",
            provider="mock",
            usage={"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
            session_key="console:e2e",
            conversation_id="conv-e2e",
            turn_seq=0,
            model_role="codex",
        )
        return {"result": "done"}

    root_ctx, root_token = start_span_sync(
        name="invoke_agent",
        operation_name="invoke_agent",
        store=trace_store,
        session_key="console:e2e",
        conversation_id="conv-e2e",
        turn_seq=0,
    )
    try:
        token_stats.record(
            model="main-model",
            provider="mock",
            usage={"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14},
            session_key="console:e2e",
            conversation_id="conv-e2e",
            turn_seq=0,
            model_role="chat",
        )
        submit = bg_tasks.submit_task(
            bg_executor,
            origin_session_key="console:e2e",
            prompt="run background work",
            timeout=5,
            task_type="codex",
        )
        await bg_tasks._tasks[submit.task_id]
    finally:
        end_span_sync(root_ctx, store=trace_store, ctx_token=root_token)

    trace = trace_store.get_trace(root_ctx.trace_id)
    operations = [span["operation_name"] for span in trace["spans"]]

    assert operations.count("invoke_agent") == 1
    assert operations.count("chat") == 2
    assert operations.count("dispatch_bg_task") == 1
    assert len(trace["token_usage"]) == 2

    chat_span_ids = {span["span_id"] for span in trace["spans"] if span["operation_name"] == "chat"}
    assert {row["span_id"] for row in trace["token_usage"]} == chat_span_ids
