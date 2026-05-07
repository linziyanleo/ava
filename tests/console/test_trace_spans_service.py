from __future__ import annotations

import time

from ava.console.services.trace_spans_service import TraceSpanStore
from ava.storage import Database


def test_trace_store_start_end_and_get_trace(tmp_path):
    db = Database(tmp_path / "trace.sqlite3")
    store = TraceSpanStore(db)

    store.start_span(
        "t1",
        "root",
        "",
        "invoke_agent",
        "invoke_agent",
        attributes_json={"session": "s1"},
        start_ns=100,
        session_key="s1",
        conversation_id="c1",
        turn_seq=0,
    )
    store.start_span(
        "t1",
        "chat",
        "root",
        "chat mock",
        "chat",
        attributes_json={"model": "mock"},
        start_ns=200,
        session_key="s1",
        conversation_id="c1",
        turn_seq=0,
    )
    store.append_event("t1", "chat", {"name": "gen_ai.first_token", "ts": 250})
    store.end_span("t1", "chat", status="ok", end_ns=400, attributes_merge={"tokens": 3})
    store.end_span("t1", "root", status="ok", end_ns=500)

    trace = store.get_trace("t1")

    assert [span["span_id"] for span in trace["spans"]] == ["root", "chat"]
    chat = trace["spans"][1]
    assert chat["depth"] == 1
    assert chat["duration_ms"] == 0.0002
    assert chat["attributes"]["tokens"] == 3
    assert chat["events"][0]["name"] == "gen_ai.first_token"


def test_mark_interrupted_closes_stale_open_spans(tmp_path):
    db = Database(tmp_path / "trace.sqlite3")
    store = TraceSpanStore(db)

    stale_start = time.time_ns() - 3_600 * 1_000_000_000
    store.start_span("t2", "open", "", "chat mock", "chat", start_ns=stale_start)

    assert store.mark_interrupted(stale_threshold_ns=30 * 60 * 1_000_000_000) == 1
    row = db.fetchone("SELECT status, end_ns FROM trace_spans WHERE trace_id = ? AND span_id = ?", ("t2", "open"))
    assert row["status"] == "interrupted"
    assert row["end_ns"] is not None


def test_list_traces_filters_by_conversation_id(tmp_path):
    db = Database(tmp_path / "trace.sqlite3")
    store = TraceSpanStore(db)

    store.start_span("trace-a", "root", "", "invoke_agent", "invoke_agent", conversation_id="conv-a")
    store.end_span("trace-a", "root")
    store.start_span("trace-b", "root", "", "invoke_agent", "invoke_agent", conversation_id="conv-b")
    store.end_span("trace-b", "root")

    traces = store.list_traces(conversation_id="conv-a")

    assert [item["trace_id"] for item in traces] == ["trace-a"]
