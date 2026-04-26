"""Context preview helpers for Ava console chat sessions."""

from __future__ import annotations

import base64
import copy
import json
import re
from datetime import datetime
from typing import Any

from loguru import logger

from ava.patches.context_patch import _deduplicate_memory
from nanobot.utils.helpers import estimate_message_tokens, estimate_prompt_tokens_chain
from nanobot.utils.prompt_templates import render_template

_TRUNCATE_CHARS = 2048
_REDACTED = "[REDACTED]"
_REDACT_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"Bearer [A-Za-z0-9\\-_.]+"),
    re.compile(r"ghp_[A-Za-z0-9]{36,}"),
)


def _content_tokens(content: Any) -> int:
    return max(0, estimate_message_tokens({"content": content}) - 4)


def _parse_session_key(session_key: str) -> tuple[str | None, str | None]:
    if ":" not in session_key:
        return None, None
    return session_key.split(":", 1)


def _session_summary(loop: Any, session: Any, session_key: str) -> str | None:
    auto_compact = getattr(loop, "auto_compact", None)
    if auto_compact is None:
        return None

    summaries = getattr(auto_compact, "_summaries", None)
    if isinstance(summaries, dict):
        entry = summaries.get(session_key)
        if isinstance(entry, tuple) and len(entry) == 2:
            try:
                return auto_compact._format_summary(entry[0], entry[1])
            except Exception:
                logger.debug("Failed to format in-memory auto-compact summary for {}", session_key)

    metadata = getattr(session, "metadata", None)
    if not isinstance(metadata, dict):
        return None
    last_summary = metadata.get("_last_summary")
    if not isinstance(last_summary, dict):
        return None
    try:
        return auto_compact._format_summary(
            str(last_summary.get("text", "")),
            datetime.fromisoformat(str(last_summary.get("last_active", ""))),
        )
    except Exception:
        logger.debug("Failed to format persisted auto-compact summary for {}", session_key)
        return None


def _apply_text_presentation(
    text: str,
    *,
    full: bool,
    reveal: bool,
) -> tuple[str, bool, bool]:
    rendered = text
    sanitized = False
    if not reveal:
        for pattern in _REDACT_PATTERNS:
            rendered, replaced = pattern.subn(_REDACTED, rendered)
            sanitized = sanitized or replaced > 0

    truncated = False
    if not full and len(rendered) > _TRUNCATE_CHARS:
        rendered = rendered[:_TRUNCATE_CHARS] + "\n… (truncated)"
        truncated = True
    return rendered, sanitized, truncated


def _parse_data_image_url(url: str) -> tuple[str, int]:
    if not url.startswith("data:") or ";base64," not in url:
        return "application/octet-stream", 0
    mime, b64 = url[5:].split(";base64,", 1)
    try:
        size = len(base64.b64decode(b64, validate=False))
    except Exception:
        size = max(0, len(b64) * 3 // 4)
    return mime or "application/octet-stream", size


def _transform_json_like(
    value: Any,
    *,
    full: bool,
    reveal: bool,
) -> tuple[Any, bool, bool]:
    if isinstance(value, str):
        rendered, sanitized, truncated = _apply_text_presentation(value, full=full, reveal=reveal)
        return rendered, sanitized, truncated

    if isinstance(value, list):
        items: list[Any] = []
        any_sanitized = False
        any_truncated = False
        for item in value:
            transformed, sanitized, truncated = _transform_json_like(item, full=full, reveal=reveal)
            items.append(transformed)
            any_sanitized = any_sanitized or sanitized
            any_truncated = any_truncated or truncated
        return items, any_sanitized, any_truncated

    if isinstance(value, dict):
        data: dict[str, Any] = {}
        any_sanitized = False
        any_truncated = False
        for key, item in value.items():
            if key == "_meta":
                continue
            transformed, sanitized, truncated = _transform_json_like(item, full=full, reveal=reveal)
            data[key] = transformed
            any_sanitized = any_sanitized or sanitized
            any_truncated = any_truncated or truncated
        return data, any_sanitized, any_truncated

    return value, False, False


def _build_system_sections(
    context_builder: Any,
    loop: Any,
    *,
    channel: str | None,
    chat_id: str | None,
    session_key: str,
) -> tuple[list[dict[str, Any]], str]:
    sections: list[dict[str, Any]] = []

    identity = context_builder._get_identity(channel=channel)
    sections.append({
        "name": "identity",
        "source": "context_builder._get_identity",
        "raw_content": identity,
        "tokens": _content_tokens(identity),
    })

    bootstrap = context_builder._load_bootstrap_files()
    if bootstrap:
        sections.append({
            "name": "bootstrap",
            "source": "workspace bootstrap files",
            "raw_content": bootstrap,
            "tokens": _content_tokens(bootstrap),
        })

    memory_text = context_builder.memory.get_memory_context()
    if memory_text and not context_builder._is_template_content(
        context_builder.memory.read_memory(),
        "memory/MEMORY.md",
    ):
        payload = f"# Memory\n\n{memory_text}"
        sections.append({
            "name": "memory",
            "source": "memory/MEMORY.md",
            "raw_content": payload,
            "tokens": _content_tokens(payload),
        })

    always_skills = context_builder.skills.get_always_skills()
    if always_skills:
        always_content = context_builder.skills.load_skills_for_context(always_skills)
        if always_content:
            payload = f"# Active Skills\n\n{always_content}"
            sections.append({
                "name": "active_skills",
                "source": "skills loader",
                "raw_content": payload,
                "tokens": _content_tokens(payload),
            })

    skills_summary = context_builder.skills.build_skills_summary(exclude=set(always_skills))
    if skills_summary:
        payload = render_template("agent/skills_section.md", skills_summary=skills_summary)
        sections.append({
            "name": "skills_summary",
            "source": "skills summary",
            "raw_content": payload,
            "tokens": _content_tokens(payload),
        })

    entries = context_builder.memory.read_unprocessed_history(
        since_cursor=context_builder.memory.get_last_dream_cursor()
    )
    if entries:
        capped = entries[-context_builder._MAX_RECENT_HISTORY :]
        payload = "# Recent History\n\n" + "\n".join(
            f"- [{entry['timestamp']}] {entry['content']}" for entry in capped
        )
        sections.append({
            "name": "recent_history",
            "source": "memory/history.jsonl",
            "raw_content": payload,
            "tokens": _content_tokens(payload),
        })

    system_prompt = "\n\n---\n\n".join(section["raw_content"] for section in sections)

    categorized_memory = getattr(loop, "categorized_memory", None)
    if categorized_memory and channel and chat_id:
        try:
            memory_ctx = categorized_memory.get_combined_context(channel, chat_id)
        except Exception:
            logger.exception("Failed to load categorized memory for {}", session_key)
        else:
            deduped = _deduplicate_memory(system_prompt, memory_ctx)
            if deduped:
                sections.append({
                    "name": "categorized_memory",
                    "source": "ava.categorized_memory",
                    "raw_content": deduped,
                    "tokens": _content_tokens(deduped),
                })
                system_prompt += f"\n\n{deduped}"

    bg_store = getattr(loop, "bg_tasks", None)
    if bg_store:
        try:
            digest = bg_store.get_active_digest(session_key)
        except Exception:
            logger.exception("Failed to load background task digest for {}", session_key)
        else:
            if digest:
                sections.append({
                    "name": "background_tasks",
                    "source": "ava.bg_tasks",
                    "raw_content": digest,
                    "tokens": _content_tokens(digest),
                })
                system_prompt += f"\n\n{digest}"

    return sections, system_prompt


def _serialize_message(
    message: dict[str, Any],
    *,
    full: bool,
    reveal: bool,
) -> tuple[dict[str, Any], bool]:
    raw_content = message.get("content")
    tokens = estimate_message_tokens(message)
    payload: dict[str, Any] = {
        "role": message.get("role", ""),
        "tool_calls": copy.deepcopy(message.get("tool_calls")),
        "tool_call_id": message.get("tool_call_id"),
        "name": message.get("name"),
        "tokens": tokens,
        "truncated": False,
    }

    any_sanitized = False
    any_truncated = False

    if isinstance(raw_content, list):
        blocks: list[dict[str, Any]] = []
        block_types: list[str] = []
        for block in raw_content:
            if not isinstance(block, dict):
                transformed, sanitized, truncated = _transform_json_like(
                    block,
                    full=full,
                    reveal=reveal,
                )
                blocks.append({"type": "unknown", "value": transformed})
                any_sanitized = any_sanitized or sanitized
                any_truncated = any_truncated or truncated
                block_types.append("unknown")
                continue

            block_type = str(block.get("type") or "unknown")
            block_types.append(block_type)
            if block_type == "text":
                rendered, sanitized, truncated = _apply_text_presentation(
                    str(block.get("text") or ""),
                    full=full,
                    reveal=reveal,
                )
                blocks.append({"type": "text", "text": rendered})
                any_sanitized = any_sanitized or sanitized
                any_truncated = any_truncated or truncated
                continue

            if block_type == "image_url":
                image_url = block.get("image_url")
                url = image_url.get("url") if isinstance(image_url, dict) else ""
                mime, size = _parse_data_image_url(url) if isinstance(url, str) else ("application/octet-stream", 0)
                blocks.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,[omitted bytes={size}]"},
                })
                continue

            transformed, sanitized, truncated = _transform_json_like(
                block,
                full=full,
                reveal=reveal,
            )
            blocks.append(transformed if isinstance(transformed, dict) else {"type": block_type, "value": transformed})
            any_sanitized = any_sanitized or sanitized
            any_truncated = any_truncated or truncated

        payload["content_type"] = "blocks"
        payload["content"] = f"[multimodal — {len(blocks)} blocks ({', '.join(dict.fromkeys(block_types))})]"
        payload["content_blocks"] = blocks
    else:
        if isinstance(raw_content, str):
            text = raw_content
        elif raw_content is None:
            text = ""
        else:
            text = json.dumps(raw_content, ensure_ascii=False)
        rendered, sanitized, truncated = _apply_text_presentation(text, full=full, reveal=reveal)
        payload["content_type"] = "text"
        payload["content"] = rendered
        payload["content_blocks"] = None
        any_sanitized = sanitized
        any_truncated = truncated

    payload["truncated"] = any_truncated
    return payload, any_sanitized


def build_context_preview(
    *,
    loop: Any,
    session: Any,
    session_key: str,
    full: bool = False,
    reveal: bool = False,
) -> dict[str, Any]:
    channel, chat_id = _parse_session_key(session_key)
    context_builder = getattr(loop, "context", None)
    if context_builder is None:
        raise RuntimeError("Agent loop context is unavailable")

    system_sections, actual_system_prompt = _build_system_sections(
        context_builder,
        loop,
        channel=channel,
        chat_id=chat_id,
        session_key=session_key,
    )

    session_summary = _session_summary(loop, session, session_key)
    runtime_context_text = context_builder._build_runtime_context(
        channel,
        chat_id,
        context_builder.timezone,
        session_summary=session_summary,
    )
    runtime_context_rendered, runtime_sanitized, runtime_truncated = _apply_text_presentation(
        runtime_context_text,
        full=full,
        reveal=reveal,
    )

    history = session.get_history(max_messages=0)
    serialized_messages: list[dict[str, Any]] = []
    any_sanitized = runtime_sanitized
    for section in system_sections:
        rendered, sanitized, truncated = _apply_text_presentation(
            section["raw_content"],
            full=full,
            reveal=reveal,
        )
        section["content"] = rendered
        section["truncated"] = truncated
        any_sanitized = any_sanitized or sanitized

    for message in history:
        serialized, sanitized = _serialize_message(message, full=full, reveal=reveal)
        serialized_messages.append(serialized)
        any_sanitized = any_sanitized or sanitized

    provider = getattr(loop, "provider", None)
    model = getattr(loop, "model", None)
    tool_registry = getattr(loop, "tools", None)
    tool_defs = tool_registry.get_definitions() if tool_registry and hasattr(tool_registry, "get_definitions") else []
    with_tools, _ = estimate_prompt_tokens_chain(provider, model, [], tools=tool_defs)
    without_tools, _ = estimate_prompt_tokens_chain(provider, model, [], tools=None)
    tool_tokens = max(0, with_tools - without_tools)

    system_tokens = estimate_message_tokens({"role": "system", "content": actual_system_prompt})
    runtime_tokens = estimate_message_tokens({"role": "user", "content": runtime_context_text})
    history_tokens = sum(estimate_message_tokens(message) for message in history)

    context_window = int(getattr(loop, "context_window_tokens", 0) or 0)
    max_completion_tokens = int(
        getattr(getattr(provider, "generation", None), "max_tokens", 8192) or 8192
    )
    ctx_budget = max(context_window - max_completion_tokens - 1024, 1)
    request_total_tokens = system_tokens + runtime_tokens + history_tokens + tool_tokens
    utilization_pct = round((request_total_tokens / ctx_budget) * 100, 1)
    in_flight = session_key in getattr(loop, "_pending_queues", {})

    return {
        "snapshot_ts": datetime.now().astimezone().isoformat(),
        "session_key": session_key,
        "workspace": str(getattr(loop, "workspace", "")),
        "provider": {
            "name": type(provider).__name__.removesuffix("Provider").lower() if provider else "",
            "model": model or "",
        },
        "scope": "idle_baseline",
        "system_sections": [
            {
                "name": section["name"],
                "source": section["source"],
                "content": section["content"],
                "tokens": section["tokens"],
                "truncated": section["truncated"],
            }
            for section in system_sections
        ],
        "runtime_context": {
            "content": runtime_context_rendered,
            "tokens": runtime_tokens,
            "truncated": runtime_truncated,
        },
        "messages": serialized_messages,
        "tools": {
            "count": len(tool_defs),
            "tokens": tool_tokens,
            "names": [
                (item.get("function") or {}).get("name") or item.get("name") or ""
                for item in tool_defs
                if isinstance(item, dict)
            ],
        },
        "totals": {
            "system_tokens": system_tokens,
            "runtime_tokens": runtime_tokens,
            "history_tokens": history_tokens,
            "tool_tokens": tool_tokens,
            "request_total_tokens": request_total_tokens,
            "context_window": context_window,
            "max_completion_tokens": max_completion_tokens,
            "ctx_budget": ctx_budget,
            "utilization_pct": utilization_pct,
        },
        "flags": {
            "sanitized": any_sanitized,
            "full": full,
            "reveal": reveal,
            "streaming": False,
            "in_flight": in_flight,
        },
        "notes": [
            "history = session.get_history(max_messages=0)",
            "request_total_tokens excludes the user's next prompt",
            "tool tokens include registered tool schema",
        ],
    }
