from __future__ import annotations

from ava.console.services.token_stats_service import TokenStatsCollector
from ava.console.services.trace_context import end_span_sync, start_span_sync
from ava.console.services.trace_spans_service import TraceSpanStore
from ava.storage import Database


def test_record_auto_creates_llm_child_span(tmp_path):
    db = Database(tmp_path / "trace.sqlite3")
    trace_store = TraceSpanStore(db)
    collector = TokenStatsCollector(data_dir=tmp_path, db=db, trace_spans=trace_store)

    root_ctx, root_token = start_span_sync(
        name="invoke_agent",
        operation_name="invoke_agent",
        store=trace_store,
        session_key="s1",
        conversation_id="c1",
        turn_seq=0,
    )
    try:
        row_id = collector.record(
            model="mock",
            provider="mock-provider",
            usage={"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
            session_key="s1",
            conversation_id="c1",
            turn_seq=0,
            finish_reason="stop",
        )
    finally:
        end_span_sync(root_ctx, store=trace_store, ctx_token=root_token)

    token_row = db.fetchone("SELECT trace_id, span_id, parent_span_id FROM token_usage WHERE id = ?", (row_id,))
    assert token_row["trace_id"] == root_ctx.trace_id
    assert token_row["parent_span_id"] == root_ctx.span_id
    assert token_row["span_id"] != root_ctx.span_id

    span_row = db.fetchone(
        "SELECT operation_name, status, end_ns FROM trace_spans WHERE trace_id = ? AND span_id = ?",
        (token_row["trace_id"], token_row["span_id"]),
    )
    assert span_row["operation_name"] == "chat"
    assert span_row["status"] == "ok"
    assert span_row["end_ns"] is not None


def test_record_with_explicit_span_id_does_not_auto_end(tmp_path):
    db = Database(tmp_path / "trace.sqlite3")
    trace_store = TraceSpanStore(db)
    collector = TokenStatsCollector(data_dir=tmp_path, db=db, trace_spans=trace_store)

    root_ctx, root_token = start_span_sync(
        name="invoke_agent",
        operation_name="invoke_agent",
        store=trace_store,
    )
    trace_store.start_span(root_ctx.trace_id, "manual-chat", root_ctx.span_id, "chat mock", "chat")
    try:
        collector.record(
            model="mock",
            provider="mock-provider",
            usage={"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
            trace_id=root_ctx.trace_id,
            span_id="manual-chat",
            parent_span_id=root_ctx.span_id,
        )
    finally:
        end_span_sync(root_ctx, store=trace_store, ctx_token=root_token)

    span_row = db.fetchone(
        "SELECT end_ns FROM trace_spans WHERE trace_id = ? AND span_id = ?",
        (root_ctx.trace_id, "manual-chat"),
    )
    assert span_row["end_ns"] is None
