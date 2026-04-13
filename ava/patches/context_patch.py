"""Patch ContextBuilder.build_messages to apply history processing and memory injection.
Also patches LLMProvider.chat_with_retry / chat_stream_with_retry to sanitize messages
before sending to non-Claude providers (removes trailing assistant messages, merges
consecutive same-role messages that violate strict user/assistant alternation).

Intercept: ContextBuilder.build_messages
Behavior:
  1. Apply HistorySummarizer to compress old turns into condensed pairs
  2. Apply HistoryCompressor to trim history within character budget
  3. Call original build_messages
  4. Inject CategorizedMemoryStore context into system prompt

Intercept: LLMProvider.chat_with_retry / chat_stream_with_retry
Behavior:
  Sanitize messages for non-Claude providers:
  - Remove trailing assistant messages (causes HTTP 400 prefill error)
  - Merge consecutive same-role messages into one

Depends on loop_patch having set self.context._agent_loop on the ContextBuilder.
"""

from __future__ import annotations

import re

from loguru import logger

from ava.launcher import register_patch


def _is_claude_provider(provider) -> bool:
    """Return True if the provider is Anthropic/Claude-based."""
    return type(provider).__name__ == "AnthropicProvider"


_LIST_ITEM_RE = re.compile(r"^([-*+]|\d+\.)\s+")


def _normalize_memory_text(text: str) -> str:
    """Normalize markdown-ish text for lightweight duplicate detection."""
    return " ".join((text or "").replace("\r", "\n").split())


def _deduplicate_memory(system_prompt: str, personal_memory: str) -> str:
    """Drop personal-memory blocks that already exist in the system prompt."""
    normalized_system = _normalize_memory_text(system_prompt)
    blocks = re.split(r"\n\s*\n+", (personal_memory or "").strip())
    kept_blocks: list[str] = []

    for block in blocks:
        raw_lines = [line.rstrip() for line in block.splitlines()]
        meaningful_lines = [line for line in raw_lines if line.strip()]
        if not meaningful_lines:
            continue

        heading_lines: list[str] = []
        content_lines = list(meaningful_lines)
        while content_lines and content_lines[0].lstrip().startswith("#"):
            heading_lines.append(content_lines.pop(0))

        if content_lines and all(_LIST_ITEM_RE.match(line.lstrip()) for line in content_lines):
            unique_lines = [
                line for line in content_lines
                if _normalize_memory_text(line) not in normalized_system
            ]
            if unique_lines:
                kept_blocks.append("\n".join([*heading_lines, *unique_lines]).strip())
            continue

        compare_text = "\n".join(content_lines).strip() or "\n".join(meaningful_lines).strip()
        if compare_text and _normalize_memory_text(compare_text) in normalized_system:
            continue

        kept_blocks.append("\n".join(meaningful_lines).strip())

    return "\n\n".join(block for block in kept_blocks if block).strip()


def sanitize_messages(messages: list[dict]) -> list[dict]:
    """Remove trailing assistant messages and merge consecutive same-role messages.

    Some providers (e.g. OpenAI-compatible) reject requests where:
    - The last message role is 'assistant' (prefill not supported)
    - Two consecutive messages share the same role

    System messages are always kept at position 0 and not merged.
    """
    if not messages:
        return messages

    # Step 1: merge consecutive same-role non-system messages
    merged: list[dict] = []
    for msg in messages:
        role = msg.get("role")
        if (
            merged
            and role != "system"
            and merged[-1].get("role") == role
            and role in ("user", "assistant")
        ):
            prev = merged[-1]
            prev_content = prev.get("content") or ""
            curr_content = msg.get("content") or ""
            if isinstance(prev_content, str) and isinstance(curr_content, str):
                prev["content"] = (prev_content + "\n\n" + curr_content).strip()
            else:
                # Non-string content (list of blocks): just keep the latest
                merged[-1] = msg
        else:
            merged.append(dict(msg))

    # Step 2: drop trailing assistant messages (only non-system messages)
    while merged and merged[-1].get("role") == "assistant":
        dropped = merged.pop()
        logger.debug(
            "sanitize_messages: dropped trailing assistant message (content={!r:.80})",
            (dropped.get("content") or "")[:80],
        )

    return merged


def apply_context_patch() -> str:
    from nanobot.agent.context import ContextBuilder

    if not hasattr(ContextBuilder, "build_messages"):
        logger.warning("context_patch skipped: ContextBuilder.build_messages not found")
        return "context_patch skipped (build_messages not found)"

    if getattr(ContextBuilder.build_messages, "_ava_patched", False):
        return "context_patch already applied (skipped)"

    original_build = ContextBuilder.build_messages

    def patched_build_messages(self, history, current_message, **kwargs):
        """Wrap build_messages: summarize → compress → build → inject memory."""
        channel = kwargs.get("channel")
        chat_id = kwargs.get("chat_id")

        loop = getattr(self, "_agent_loop", None)

        # 1. 历史摘要（旧轮次压缩为精简 user/assistant 对）
        summarizer = getattr(loop, "history_summarizer", None) if loop else None
        if summarizer:
            try:
                history = summarizer.summarize(history)
            except Exception as exc:
                logger.warning("HistorySummarizer failed, using raw history: {}", exc)

        # 2. 历史压缩（基于字符预算 + 相关性裁剪）
        compressor = getattr(loop, "history_compressor", None) if loop else None
        if compressor:
            try:
                history = compressor.compress(history, current_message)
            except Exception as exc:
                logger.warning("HistoryCompressor failed, using summarized history: {}", exc)

        # 3. 调用原始 build_messages
        messages = original_build(self, history, current_message, **kwargs)

        # 4. 注入分类记忆到系统提示词
        cat_mem = getattr(loop, "categorized_memory", None) if loop else None
        if cat_mem and channel and chat_id:
            try:
                memory_ctx = cat_mem.get_combined_context(channel, chat_id)
                if memory_ctx and messages and messages[0]["role"] == "system":
                    deduped_memory = _deduplicate_memory(messages[0]["content"], memory_ctx)
                    if deduped_memory:
                        messages[0]["content"] += f"\n\n{deduped_memory}"
            except Exception as exc:
                logger.warning("CategorizedMemory injection failed: {}", exc)

        # 5. 注入后台任务 digest 到系统提示词
        bg_store = getattr(loop, "bg_tasks", None) if loop else None
        if bg_store and messages and messages[0]["role"] == "system":
            try:
                sk = getattr(loop, "_current_session_key", None)
                digest = bg_store.get_active_digest(sk)
                if digest:
                    messages[0]["content"] += f"\n\n{digest}"
            except Exception as exc:
                logger.warning("BackgroundTaskStore digest injection failed: {}", exc)

        # 6. 保存 system prompt 到 loop，供 token_stats 记录（完整保存，不截断）
        if loop and messages and messages[0].get("role") == "system":
            try:
                loop._last_system_prompt = messages[0]["content"] or ""
            except Exception:
                pass

        # 7. 记录压缩后的历史消息数（不含 system 和当前 user），供 _save_turn 计算正确的 skip。
        #    HistorySummarizer/Compressor 会减少历史长度，导致上游 skip = 1 + len(原始history)
        #    大于 all_msgs 实际长度，使新消息无法被保存。
        #    build_messages 返回 [system, history..., user_msg]，历史数 = len - 2。
        if loop:
            loop._last_build_msg_count = len(messages) - 2  # 不含 system 和当前 user

        return messages

    patched_build_messages._ava_patched = True
    ContextBuilder.build_messages = patched_build_messages

    # ------------------------------------------------------------------
    # Patch LLMProvider.chat_with_retry and chat_stream_with_retry
    # to sanitize messages before sending to non-Claude providers.
    # ------------------------------------------------------------------
    try:
        from nanobot.providers.base import LLMProvider
    except ImportError:
        logger.warning("context_patch: LLMProvider not found, skipping message sanitize patch")
        return "ContextBuilder.build_messages patched (LLMProvider sanitize skipped)"

    if not hasattr(LLMProvider, "chat_with_retry") or not hasattr(LLMProvider, "chat_stream_with_retry"):
        logger.warning("context_patch: LLMProvider chat methods not found, skipping sanitize patch")
        return "ContextBuilder.build_messages patched (LLMProvider sanitize skipped)"

    if getattr(LLMProvider.chat_with_retry, "_ava_sanitize_patched", False):
        return "ContextBuilder.build_messages patched: history summarize+compress, categorized memory injection"

    original_chat_with_retry = LLMProvider.chat_with_retry
    original_chat_stream_with_retry = LLMProvider.chat_stream_with_retry

    async def patched_chat_with_retry(self, messages, **kwargs):
        """Wrap chat_with_retry: sanitize messages for non-Claude providers."""
        if not _is_claude_provider(self):
            messages = sanitize_messages(messages)
        return await original_chat_with_retry(self, messages, **kwargs)

    async def patched_chat_stream_with_retry(self, messages, **kwargs):
        """Wrap chat_stream_with_retry: sanitize messages for non-Claude providers."""
        if not _is_claude_provider(self):
            messages = sanitize_messages(messages)
        return await original_chat_stream_with_retry(self, messages, **kwargs)

    patched_chat_with_retry._ava_sanitize_patched = True
    patched_chat_stream_with_retry._ava_sanitize_patched = True
    LLMProvider.chat_with_retry = patched_chat_with_retry
    LLMProvider.chat_stream_with_retry = patched_chat_stream_with_retry

    return (
        "ContextBuilder.build_messages patched: history summarize+compress, categorized memory injection; "
        "LLMProvider.chat_with_retry/chat_stream_with_retry patched: sanitize trailing assistant messages"
    )


register_patch("context_builder", apply_context_patch)
