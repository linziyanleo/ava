from __future__ import annotations

from ava.console.services.token_stats_service import TokenStatsCollector
from ava.storage import Database


def test_token_by_session_responses_include_trace_fields(tmp_path):
    db = Database(tmp_path / "tokens.sqlite3")
    collector = TokenStatsCollector(data_dir=tmp_path, db=db)

    collector.record(
        model="mock-model",
        provider="mock",
        usage={"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
        session_key="console:trace",
        conversation_id="conv-token",
        turn_seq=0,
        iteration=0,
        trace_id="trace-token",
        span_id="span-token",
        parent_span_id="parent-token",
        finish_reason="stop",
    )

    turns = collector.get_by_session("console:trace", conversation_id="conv-token")
    detailed = collector.get_by_session_detailed("console:trace", conversation_id="conv-token")

    assert turns[0]["trace_id"] == "trace-token"
    assert turns[0]["span_id"] == "span-token"
    assert detailed[0]["trace_id"] == "trace-token"
    assert detailed[0]["span_id"] == "span-token"
    assert detailed[0]["parent_span_id"] == "parent-token"
