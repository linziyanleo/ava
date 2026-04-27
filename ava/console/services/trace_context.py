"""Trace context helpers for Ava console/runtime telemetry."""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from secrets import token_hex
from typing import TYPE_CHECKING, Any, AsyncIterator

if TYPE_CHECKING:
    from ava.console.services.trace_spans_service import TraceSpanStore


@dataclass(frozen=True)
class TraceContext:
    trace_id: str
    span_id: str
    parent_span_id: str = ""


current_trace_context: ContextVar[TraceContext | None] = ContextVar(
    "ava_current_trace_context",
    default=None,
)


def new_trace_id() -> str:
    return token_hex(16)


def new_span_id() -> str:
    return token_hex(8)


def start_span_sync(
    *,
    name: str,
    operation_name: str,
    kind: str = "internal",
    attributes: dict[str, Any] | None = None,
    store: "TraceSpanStore | None" = None,
    parent: TraceContext | None = None,
    trace_id: str = "",
    span_id: str = "",
    parent_span_id: str = "",
    session_key: str = "",
    conversation_id: str = "",
    turn_seq: int | None = None,
) -> tuple[TraceContext, Token[TraceContext | None]]:
    parent_ctx = parent if parent is not None else current_trace_context.get()
    resolved_trace_id = trace_id or (parent_ctx.trace_id if parent_ctx else new_trace_id())
    resolved_parent_span_id = parent_span_id or (parent_ctx.span_id if parent_ctx else "")
    ctx = TraceContext(
        trace_id=resolved_trace_id,
        span_id=span_id or new_span_id(),
        parent_span_id=resolved_parent_span_id,
    )
    if store is not None:
        store.start_span(
            trace_id=ctx.trace_id,
            span_id=ctx.span_id,
            parent_span_id=ctx.parent_span_id,
            name=name,
            operation_name=operation_name,
            kind=kind,
            attributes_json=attributes or {},
            start_ns=time.time_ns(),
            session_key=session_key,
            conversation_id=conversation_id,
            turn_seq=turn_seq,
        )
    token = current_trace_context.set(ctx)
    return ctx, token


def end_span_sync(
    ctx: TraceContext | None,
    *,
    store: "TraceSpanStore | None" = None,
    status: str = "ok",
    status_message: str = "",
    attributes_merge: dict[str, Any] | None = None,
    ctx_token: Token[TraceContext | None] | None = None,
    end_ns: int | None = None,
) -> None:
    if ctx is not None and store is not None:
        store.end_span(
            trace_id=ctx.trace_id,
            span_id=ctx.span_id,
            status=status,
            status_message=status_message,
            attributes_merge=attributes_merge,
            end_ns=end_ns or time.time_ns(),
        )
    if ctx_token is not None:
        current_trace_context.reset(ctx_token)


@asynccontextmanager
async def start_span(
    *,
    name: str,
    operation_name: str,
    kind: str = "internal",
    attributes: dict[str, Any] | None = None,
    store: "TraceSpanStore | None" = None,
    parent: TraceContext | None = None,
    session_key: str = "",
    conversation_id: str = "",
    turn_seq: int | None = None,
) -> AsyncIterator[TraceContext]:
    ctx, token = start_span_sync(
        name=name,
        operation_name=operation_name,
        kind=kind,
        attributes=attributes,
        store=store,
        parent=parent,
        session_key=session_key,
        conversation_id=conversation_id,
        turn_seq=turn_seq,
    )
    try:
        yield ctx
    except BaseException as exc:
        end_span_sync(
            ctx,
            store=store,
            status="error",
            status_message=str(exc)[:500],
            ctx_token=token,
        )
        raise
    else:
        end_span_sync(ctx, store=store, status="ok", ctx_token=token)


def inject_traceparent(env: dict[str, str], ctx: TraceContext) -> dict[str, str]:
    updated = dict(env)
    updated["TRACEPARENT"] = f"00-{ctx.trace_id}-{ctx.span_id}-01"
    return updated


def extract_traceparent(env: dict[str, str]) -> TraceContext | None:
    raw = env.get("TRACEPARENT", "")
    parts = raw.split("-")
    if len(parts) != 4 or parts[0] != "00":
        return None
    _, trace_id, parent_span_id, _flags = parts
    if len(trace_id) != 32 or len(parent_span_id) != 16:
        return None
    return TraceContext(trace_id=trace_id, span_id=new_span_id(), parent_span_id=parent_span_id)
