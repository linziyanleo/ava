"""Tests for Anthropic tool_result normalization patch."""

from __future__ import annotations

import json

import pytest


@pytest.fixture(autouse=True)
def _restore_tool_result_block():
    """Restore AnthropicProvider._tool_result_block after each test."""
    from nanobot.providers.anthropic_provider import AnthropicProvider

    original = getattr(
        AnthropicProvider,
        "_ava_original_tool_result_block",
        AnthropicProvider._tool_result_block,
    )
    yield
    AnthropicProvider._tool_result_block = staticmethod(original)
    if hasattr(AnthropicProvider, "_ava_original_tool_result_block"):
        delattr(AnthropicProvider, "_ava_original_tool_result_block")


class TestAnthropicToolResultPatch:
    def test_apply_is_idempotent(self):
        from ava.patches.provider_anthropic_tool_result_patch import apply_anthropic_tool_result_patch

        first = apply_anthropic_tool_result_patch()
        second = apply_anthropic_tool_result_patch()

        assert "normalizes" in first
        assert "already patched" in second

    def test_string_content_passthrough(self):
        from ava.patches.provider_anthropic_tool_result_patch import apply_anthropic_tool_result_patch
        from nanobot.providers.anthropic_provider import AnthropicProvider

        apply_anthropic_tool_result_patch()
        block = AnthropicProvider._tool_result_block(
            {"tool_call_id": "toolu_123", "content": "plain text"}
        )

        assert block == {
            "type": "tool_result",
            "tool_use_id": "toolu_123",
            "content": "plain text",
        }

    def test_non_list_scalar_stringified(self):
        from ava.patches.provider_anthropic_tool_result_patch import apply_anthropic_tool_result_patch
        from nanobot.providers.anthropic_provider import AnthropicProvider

        apply_anthropic_tool_result_patch()
        block = AnthropicProvider._tool_result_block(
            {"tool_call_id": "toolu_123", "content": 42}
        )

        assert block["content"] == "42"

    def test_list_content_is_normalized_to_safe_blocks(self):
        from ava.patches.provider_anthropic_tool_result_patch import apply_anthropic_tool_result_patch
        from nanobot.providers.anthropic_provider import AnthropicProvider

        apply_anthropic_tool_result_patch()
        block = AnthropicProvider._tool_result_block(
            {
                "tool_call_id": "toolu_123",
                "content": [
                    "hello",
                    {"type": "input_text", "text": "in"},
                    {"type": "output_text", "text": "out"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "data:image/png;base64,AAA="},
                    },
                    {"foo": "bar"},
                ],
            }
        )

        assert block["content"] == [
            {"type": "text", "text": "hello"},
            {"type": "text", "text": "in"},
            {"type": "text", "text": "out"},
            {
                "type": "image",
                "source": {"type": "base64", "media_type": "image/png", "data": "AAA="},
            },
            {"type": "text", "text": json.dumps({"foo": "bar"}, ensure_ascii=False)},
        ]

    def test_valid_text_blocks_are_preserved(self):
        from ava.patches.provider_anthropic_tool_result_patch import apply_anthropic_tool_result_patch
        from nanobot.providers.anthropic_provider import AnthropicProvider

        apply_anthropic_tool_result_patch()
        block = AnthropicProvider._tool_result_block(
            {
                "tool_call_id": "toolu_123",
                "content": [{"type": "text", "text": "already valid"}],
            }
        )

        assert block["content"] == [{"type": "text", "text": "already valid"}]

    def test_convert_messages_normalizes_sanitized_tool_dict_content(self):
        from ava.patches.provider_anthropic_tool_result_patch import apply_anthropic_tool_result_patch
        from nanobot.providers.anthropic_provider import AnthropicProvider

        apply_anthropic_tool_result_patch()

        provider = AnthropicProvider()
        messages = provider._sanitize_empty_content(
            [
                {"role": "user", "content": "最近AI圈都在讨论什么呀"},
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "toolu_123",
                            "type": "function",
                            "function": {
                                "name": "web_fetch",
                                "arguments": "{\"url\": \"https://example.com\"}",
                            },
                        }
                    ],
                },
                {
                    "role": "tool",
                    "tool_call_id": "toolu_123",
                    "name": "web_fetch",
                    "content": {
                        "url": "https://example.com",
                        "status": 200,
                        "text": "ok",
                    },
                },
            ]
        )

        _system, anthropic_messages = provider._convert_messages(messages)
        tool_result = anthropic_messages[2]["content"][0]

        assert tool_result["type"] == "tool_result"
        assert tool_result["tool_use_id"] == "toolu_123"
        assert tool_result["content"] == [
            {
                "type": "text",
                "text": json.dumps(
                    {"url": "https://example.com", "status": 200, "text": "ok"},
                    ensure_ascii=False,
                ),
            }
        ]
