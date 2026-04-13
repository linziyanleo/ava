"""Tests for context_patch — history processing + memory injection."""

from unittest.mock import MagicMock, patch

import pytest

from nanobot.agent.context import ContextBuilder


@pytest.fixture(autouse=True)
def _restore_build_messages():
    """Save and restore ContextBuilder.build_messages."""
    original = ContextBuilder.build_messages
    yield
    ContextBuilder.build_messages = original


def _make_mock_ctx(**overrides):
    """Create a minimal mock ContextBuilder for testing."""
    ctx = ContextBuilder.__new__(ContextBuilder)
    ctx.workspace = MagicMock()
    ctx.memory = MagicMock()
    ctx.memory.get_memory_context.return_value = ""
    ctx.skills = MagicMock()
    ctx.skills.get_always_skills.return_value = []
    ctx.skills.build_skills_summary.return_value = ""
    ctx.timezone = None  # added by upstream 33abe915
    for k, v in overrides.items():
        setattr(ctx, k, v)
    return ctx


class TestContextPatch:
    def test_patch_applies_without_error(self):
        from ava.patches.context_patch import apply_context_patch
        result = apply_context_patch()
        assert "contextbuilder" in result.lower() or "patched" in result.lower()

    def test_build_messages_replaced(self):
        from ava.patches.context_patch import apply_context_patch
        apply_context_patch()
        assert getattr(ContextBuilder.build_messages, "_ava_patched", False) is True

    def test_idempotent(self):
        from ava.patches.context_patch import apply_context_patch
        r1 = apply_context_patch()
        r2 = apply_context_patch()
        assert "skipped" in r2.lower()

    def test_summarizer_called_when_available(self):
        from ava.patches.context_patch import apply_context_patch
        apply_context_patch()

        mock_summarizer = MagicMock()
        mock_summarizer.summarize.return_value = [{"role": "user", "content": "hi"}]
        mock_loop = MagicMock()
        mock_loop.history_summarizer = mock_summarizer
        mock_loop.history_compressor = None
        mock_loop.categorized_memory = None
        mock_loop.bg_tasks = None

        ctx = _make_mock_ctx(_agent_loop=mock_loop)
        history = [{"role": "user", "content": "old"}, {"role": "assistant", "content": "reply"}]
        ctx.build_messages(history, "new msg", channel="tg", chat_id="123")
        mock_summarizer.summarize.assert_called_once_with(history)

    def test_compressor_called_when_available(self):
        from ava.patches.context_patch import apply_context_patch
        apply_context_patch()

        mock_compressor = MagicMock()
        mock_compressor.compress.return_value = [{"role": "user", "content": "hi"}]
        mock_loop = MagicMock()
        mock_loop.history_summarizer = None
        mock_loop.history_compressor = mock_compressor
        mock_loop.categorized_memory = None
        mock_loop.bg_tasks = None

        ctx = _make_mock_ctx(_agent_loop=mock_loop)
        ctx.build_messages([{"role": "user", "content": "old"}], "new", channel="tg", chat_id="123")
        mock_compressor.compress.assert_called_once()

    def test_memory_injected_into_system_prompt(self):
        from ava.patches.context_patch import apply_context_patch
        apply_context_patch()

        mock_cat_mem = MagicMock()
        mock_cat_mem.get_combined_context.return_value = "## Personal Memory (Alice)\n- 用户偏好：喜欢猫咪"
        mock_loop = MagicMock()
        mock_loop.history_summarizer = None
        mock_loop.history_compressor = None
        mock_loop.categorized_memory = mock_cat_mem
        mock_loop.bg_tasks = None

        ctx = _make_mock_ctx(_agent_loop=mock_loop)
        messages = ctx.build_messages([], "hi", channel="tg", chat_id="123")
        assert messages[0]["role"] == "system"
        assert "Personal Memory" in messages[0]["content"]
        assert "猫咪" in messages[0]["content"]

    def test_memory_deduplicated_against_existing_system_prompt(self):
        from ava.patches.context_patch import _deduplicate_memory

        system_prompt = """
## USER.md

- 喜欢猫咪
- 偏好中文

## Memory

- 当前在做 Dream 合并
""".strip()
        personal_memory = """
## Personal Memory (Alice)
- 喜欢猫咪
- 当前在做 Dream 合并
- 喜欢乌龙茶
""".strip()

        deduped = _deduplicate_memory(system_prompt, personal_memory)
        assert "喜欢乌龙茶" in deduped
        assert "喜欢猫咪" not in deduped
        assert "当前在做 Dream 合并" not in deduped
        assert "Personal Memory" in deduped

    def test_no_loop_ref_passthrough(self):
        from ava.patches.context_patch import apply_context_patch
        apply_context_patch()

        ctx = _make_mock_ctx()  # no _agent_loop
        messages = ctx.build_messages([], "hello")
        assert messages[0]["role"] == "system"
        assert len(messages) >= 2
