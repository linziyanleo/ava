# Observability Trace Spans

Ava records a W3C-style trace for each agent turn. The trace is stored in SQLite
so the console can join runtime spans with token usage rows.

## IDs

- `trace_id`: 32 hex chars, shared by one turn and any background tasks it starts.
- `span_id`: 16 hex chars, one runtime operation.
- `parent_span_id`: parent operation inside the same trace.

New `token_usage` rows store all three fields. A normal LLM record maps to one
`trace_spans` row with `operation_name = "chat"`.

## Span Types

- `invoke_agent`: root turn span.
- `build_context`: context assembly snapshot.
- `chat`: one LLM call.
- `execute_tool`: tool execution window.
- `dispatch_bg_task`: synchronous background task dispatch.

Sidecar coding tools such as `codex`, `claude_code`, and `page_agent` currently
write token rows in the parent Python process after parsing child process
results. P0 therefore propagates trace context through `BackgroundTaskStore`
with `contextvars.copy_context()` and lets `TokenStatsCollector.record()` create
the LLM child span. External CLI/Node `TRACEPARENT` injection is intentionally
left for a later child-process telemetry pass.

## API

- `GET /api/stats/tokens/records?trace_id=...&span_id=...`
- `GET /api/stats/traces/{trace_id}`
- `GET /api/stats/traces?session_key=...&turn_seq=...`

The console Token Stats page shows trace/span fields in each expanded record.
Use `View Trace` to open the waterfall drawer and inspect span attributes,
events, status, and joined token usage.

## Recovery

On console startup, the real trace store marks stale open spans older than
30 minutes as `interrupted`. Mock services do not run recovery.
