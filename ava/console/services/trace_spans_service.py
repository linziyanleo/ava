"""SQLite-backed trace span store."""

from __future__ import annotations

import json
import time
from typing import Any

from loguru import logger


def _loads(raw: str | None, fallback: Any) -> Any:
    try:
        return json.loads(raw or "")
    except Exception:
        return fallback


def _dumps(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


class TraceSpanStore:
    """Persist and query hierarchical spans for a single SQLite database."""

    def __init__(self, db: Any) -> None:
        self._db = db

    def start_span(
        self,
        trace_id: str,
        span_id: str,
        parent_span_id: str,
        name: str,
        operation_name: str,
        kind: str = "internal",
        attributes_json: str | dict[str, Any] | None = None,
        *,
        start_ns: int | None = None,
        session_key: str = "",
        conversation_id: str = "",
        turn_seq: int | None = None,
    ) -> int | None:
        started = start_ns or time.time_ns()
        try:
            self._db.execute(
                """INSERT INTO trace_spans
                   (trace_id, span_id, parent_span_id, name, operation_name, kind,
                    status, start_ns, attributes_json, events_json,
                    session_key, conversation_id, turn_seq)
                   VALUES (?, ?, ?, ?, ?, ?, 'running', ?, ?, '[]', ?, ?, ?)
                   ON CONFLICT(trace_id, span_id) DO UPDATE SET
                    parent_span_id=excluded.parent_span_id,
                    name=excluded.name,
                    operation_name=excluded.operation_name,
                    kind=excluded.kind,
                    status='running',
                    start_ns=excluded.start_ns,
                    end_ns=NULL,
                    duration_ms=NULL,
                    attributes_json=excluded.attributes_json,
                    session_key=excluded.session_key,
                    conversation_id=excluded.conversation_id,
                    turn_seq=excluded.turn_seq""",
                (
                    trace_id,
                    span_id,
                    parent_span_id,
                    name,
                    operation_name,
                    kind,
                    started,
                    _dumps(attributes_json or {}),
                    session_key,
                    conversation_id,
                    turn_seq,
                ),
            )
            self._db.commit()
            row = self._db.fetchone("SELECT last_insert_rowid() as id")
            return row["id"] if row else None
        except Exception as exc:
            logger.warning("TraceSpanStore.start_span failed: {}", exc)
            return None

    def end_span(
        self,
        trace_id: str,
        span_id: str,
        *,
        status: str = "ok",
        end_ns: int | None = None,
        status_message: str = "",
        attributes_merge: dict[str, Any] | None = None,
    ) -> None:
        ended = end_ns or time.time_ns()
        try:
            row = self._db.fetchone(
                "SELECT start_ns, attributes_json FROM trace_spans WHERE trace_id = ? AND span_id = ?",
                (trace_id, span_id),
            )
            if not row:
                return
            attrs = _loads(row["attributes_json"], {})
            if isinstance(attrs, dict) and attributes_merge:
                attrs.update(attributes_merge)
            duration_ms = max(0.0, (ended - int(row["start_ns"])) / 1_000_000)
            self._db.execute(
                """UPDATE trace_spans
                      SET status = ?, status_message = ?, end_ns = ?,
                          duration_ms = ?, attributes_json = ?
                    WHERE trace_id = ? AND span_id = ?""",
                (
                    status,
                    status_message,
                    ended,
                    duration_ms,
                    _dumps(attrs),
                    trace_id,
                    span_id,
                ),
            )
            self._db.commit()
        except Exception as exc:
            logger.warning("TraceSpanStore.end_span failed: {}", exc)

    def append_event(self, trace_id: str, span_id: str, event: dict[str, Any]) -> None:
        try:
            row = self._db.fetchone(
                "SELECT events_json FROM trace_spans WHERE trace_id = ? AND span_id = ?",
                (trace_id, span_id),
            )
            if not row:
                return
            events = _loads(row["events_json"], [])
            if not isinstance(events, list):
                events = []
            events.append(event)
            self._db.execute(
                "UPDATE trace_spans SET events_json = ? WHERE trace_id = ? AND span_id = ?",
                (_dumps(events), trace_id, span_id),
            )
            self._db.commit()
        except Exception as exc:
            logger.warning("TraceSpanStore.append_event failed: {}", exc)

    def get_trace(self, trace_id: str) -> dict[str, Any]:
        span_rows = self._db.fetchall(
            "SELECT * FROM trace_spans WHERE trace_id = ? ORDER BY start_ns ASC, id ASC",
            (trace_id,),
        )
        token_rows = self._db.fetchall(
            "SELECT * FROM token_usage WHERE trace_id = ? ORDER BY timestamp ASC, id ASC",
            (trace_id,),
        )
        tokens_by_span: dict[str, list[dict[str, Any]]] = {}
        token_usage = [dict(row) for row in token_rows]
        for row in token_usage:
            tokens_by_span.setdefault(row.get("span_id") or "", []).append(row)

        spans: list[dict[str, Any]] = []
        by_id: dict[str, dict[str, Any]] = {}
        for row in span_rows:
            item = dict(row)
            item["attributes"] = _loads(item.pop("attributes_json", "{}"), {})
            item["events"] = _loads(item.pop("events_json", "[]"), [])
            item["token_usage"] = tokens_by_span.get(item["span_id"], [])
            item["children"] = []
            item["depth"] = 0
            by_id[item["span_id"]] = item
            spans.append(item)

        roots: list[dict[str, Any]] = []
        for item in spans:
            parent = by_id.get(item.get("parent_span_id") or "")
            if parent:
                item["depth"] = int(parent.get("depth", 0)) + 1
                parent["children"].append(item)
            else:
                roots.append(item)

        return {
            "trace_id": trace_id,
            "spans": spans,
            "tree": roots,
            "token_usage": token_usage,
        }

    def list_traces(
        self,
        *,
        session_key: str | None = None,
        conversation_id: str | None = None,
        turn_seq: int | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if session_key:
            clauses.append("session_key = ?")
            params.append(session_key)
        if conversation_id is not None:
            clauses.append("conversation_id = ?")
            params.append(conversation_id)
        if turn_seq is not None:
            clauses.append("turn_seq = ?")
            params.append(turn_seq)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._db.fetchall(
            f"""SELECT trace_id,
                       MIN(start_ns) AS start_ns,
                       MAX(COALESCE(end_ns, start_ns)) AS end_ns,
                       COUNT(*) AS span_count,
                       SUM(CASE WHEN end_ns IS NULL THEN 1 ELSE 0 END) AS open_spans,
                       MAX(status = 'error') AS has_error,
                       MAX(status = 'interrupted') AS has_interrupted
                  FROM trace_spans
                  {where}
                 GROUP BY trace_id
                 ORDER BY start_ns DESC
                 LIMIT ?""",
            (*params, limit),
        )
        return [dict(row) for row in rows]

    def mark_interrupted(self, stale_threshold_ns: int) -> int:
        cutoff = time.time_ns() - stale_threshold_ns
        try:
            rows = self._db.fetchall(
                "SELECT trace_id, span_id FROM trace_spans WHERE end_ns IS NULL AND start_ns < ?",
                (cutoff,),
            )
            for row in rows:
                self.end_span(
                    row["trace_id"],
                    row["span_id"],
                    status="interrupted",
                    status_message="Recovered after process restart",
                    end_ns=time.time_ns(),
                )
            return len(rows)
        except Exception as exc:
            logger.warning("TraceSpanStore.mark_interrupted failed: {}", exc)
            return 0
