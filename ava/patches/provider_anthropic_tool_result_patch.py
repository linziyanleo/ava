"""Monkey patch AnthropicProvider tool_result serialization for Anthropic-safe blocks.

拦截点: ``AnthropicProvider._tool_result_block``
原始行为: 直接透传 ``tool`` message 的 list content，导致 list 中的 string /
OpenAI 风格 block / 无 ``type`` 的 dict 进入 Anthropic Messages API 后报
``tool_result.content[0].type: Field required``。
修改后行为: 将 tool_result content 归一化为 Anthropic 可接受的 string 或
block list，仅保留 ``text`` / ``image`` / ``document`` 等安全 block，其他
形态退化为 text block。
"""

from __future__ import annotations

import json
from functools import wraps
from typing import Any

from loguru import logger

from ava.launcher import register_patch

_PASSTHROUGH_TOOL_RESULT_BLOCK_TYPES = {"text", "image", "document"}


def _text_block(text: Any) -> dict[str, str]:
    return {"type": "text", "text": "" if text is None else str(text)}


def _normalize_tool_result_item(item: Any, provider_cls) -> dict[str, Any] | None:
    """Normalize one tool_result content item into an Anthropic-safe block."""
    if isinstance(item, str):
        return _text_block(item)

    if not isinstance(item, dict):
        return _text_block(item)

    item_type = item.get("type")

    if item_type in _PASSTHROUGH_TOOL_RESULT_BLOCK_TYPES:
        if item_type == "text":
            return _text_block(item.get("text", ""))
        return item

    if item_type in {"input_text", "output_text"}:
        return _text_block(
            item.get("text")
            or item.get("input_text")
            or item.get("output_text")
            or ""
        )

    if item_type == "image_url":
        converted = provider_cls._convert_image_block(item)
        if converted:
            return converted

    return _text_block(json.dumps(item, ensure_ascii=False))


def _normalize_tool_result_content(content: Any, provider_cls) -> str | list[dict[str, Any]]:
    """Return string content or a normalized list of Anthropic content blocks."""
    if isinstance(content, str):
        return content

    if content is None:
        return ""

    if not isinstance(content, list):
        return str(content)

    blocks: list[dict[str, Any]] = []
    for item in content:
        normalized = _normalize_tool_result_item(item, provider_cls)
        if normalized:
            blocks.append(normalized)
    return blocks or ""


def apply_anthropic_tool_result_patch() -> str:
    """Normalize tool_result blocks before Anthropic Messages API serialization."""
    from nanobot.providers.anthropic_provider import AnthropicProvider

    original_tool_result_block = getattr(AnthropicProvider, "_tool_result_block", None)
    if original_tool_result_block is None:
        logger.warning(
            "anthropic_tool_result_patch skipped: AnthropicProvider._tool_result_block not found"
        )
        return "anthropic tool_result patch skipped (target method not found)"

    if getattr(original_tool_result_block, "_ava_anthropic_tool_result_patch", False):
        return "AnthropicProvider tool_result normalization already patched (skipped)"

    if not hasattr(AnthropicProvider, "_ava_original_tool_result_block"):
        AnthropicProvider._ava_original_tool_result_block = original_tool_result_block

    @wraps(original_tool_result_block)
    def patched_tool_result_block(msg: dict[str, Any]) -> dict[str, Any]:
        content = msg.get("content")
        block: dict[str, Any] = {
            "type": "tool_result",
            "tool_use_id": msg.get("tool_call_id", ""),
            "content": _normalize_tool_result_content(content, AnthropicProvider),
        }
        return block

    patched_tool_result_block._ava_anthropic_tool_result_patch = True
    AnthropicProvider._tool_result_block = staticmethod(patched_tool_result_block)
    return "AnthropicProvider normalizes tool_result content blocks for Anthropic Messages API"


register_patch("provider_anthropic_tool_result", apply_anthropic_tool_result_patch)
