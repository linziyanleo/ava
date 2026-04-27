from __future__ import annotations

import inspect
import json

import pytest

from ava.agent.bg_tasks import BackgroundTaskStore, SubmitResult
from ava.console.services.token_stats_service import TokenStatsCollector
from ava.console.services.trace_context import current_trace_context, end_span_sync, start_span_sync
from ava.console.services.trace_spans_service import TraceSpanStore
from ava.storage import Database


@pytest.mark.asyncio
async def test_bg_task_restores_trace_context_and_record_auto_spans(tmp_path):
    db = Database(tmp_path / "bg-trace.sqlite3")
    trace_store = TraceSpanStore(db)
    token_stats = TokenStatsCollector(data_dir=tmp_path, db=db, trace_spans=trace_store)
    store = BackgroundTaskStore(db=db, trace_spans=trace_store)

    async def _executor(**_kwargs):
        token_stats.record(
            model="mock-bg",
            provider="mock-provider",
            usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            model_role="codex",
        )
        return {"result": "done"}

    root_ctx, root_token = start_span_sync(
        name="invoke_agent",
        operation_name="invoke_agent",
        store=trace_store,
        session_key="console:test",
    )
    try:
        submit = store.submit_task(
            _executor,
            origin_session_key="console:test",
            prompt="run bg trace",
            timeout=5,
            task_type="codex",
        )
        assert isinstance(submit, SubmitResult)
        assert not inspect.isawaitable(submit)
        await store._tasks[submit.task_id]
        assert current_trace_context.get() == root_ctx
    finally:
        end_span_sync(root_ctx, store=trace_store, ctx_token=root_token)

    trace = trace_store.get_trace(root_ctx.trace_id)
    spans = {span["span_id"]: span for span in trace["spans"]}
    operations = {span["operation_name"] for span in trace["spans"]}
    assert "dispatch_bg_task" in operations
    assert "chat" in operations

    token_row = db.fetchone("SELECT trace_id, span_id, parent_span_id FROM token_usage WHERE model = ?", ("mock-bg",))
    assert token_row["trace_id"] == root_ctx.trace_id
    assert token_row["span_id"] != root_ctx.span_id
    assert spans[token_row["span_id"]]["operation_name"] == "chat"
    assert token_row["parent_span_id"] == root_ctx.span_id

    task_row = db.fetchone("SELECT extra FROM bg_tasks WHERE task_id = ?", (submit.task_id,))
    extra = json.loads(task_row["extra"])
    assert extra["trace_id"] == root_ctx.trace_id
    assert extra["parent_span_id"] == root_ctx.span_id
    assert extra["dispatch_span_id"] in spans
    assert "captured_context" not in store.get_status(task_id=submit.task_id)["tasks"][0]
