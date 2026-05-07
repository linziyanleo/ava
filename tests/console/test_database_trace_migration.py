from __future__ import annotations

from ava.storage import Database


def test_trace_schema_is_created_and_idempotent(tmp_path):
    db_path = tmp_path / "trace.sqlite3"

    first = Database(db_path)
    second = Database(db_path)

    columns = {
        row["name"]
        for row in second.fetchall("PRAGMA table_info(token_usage)")
    }
    assert {"trace_id", "span_id", "parent_span_id"} <= columns

    trace_table = second.fetchone(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='trace_spans'"
    )
    assert trace_table is not None

    first.close()
    second.close()
