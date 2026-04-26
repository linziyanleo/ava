"""Tests for Consolidator -> categorized_memory bridge in loop_patch."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import weakref

import pytest

from nanobot.agent.loop import AgentLoop
from nanobot.agent.memory import Consolidator, MemoryStore


@pytest.fixture(autouse=True)
def _restore_consolidator_methods():
    """Restore patched Consolidator methods after each test."""
    orig_init = AgentLoop.__init__
    orig_set_tool_context = AgentLoop._set_tool_context
    orig_run_agent_loop = AgentLoop._run_agent_loop
    orig_save_turn = AgentLoop._save_turn
    orig_process = AgentLoop._process_message
    orig_archive = Consolidator.archive
    orig_maybe_consolidate = Consolidator.maybe_consolidate_by_tokens
    yield
    AgentLoop.__init__ = orig_init
    AgentLoop._set_tool_context = orig_set_tool_context
    AgentLoop._run_agent_loop = orig_run_agent_loop
    AgentLoop._save_turn = orig_save_turn
    AgentLoop._process_message = orig_process
    Consolidator.archive = orig_archive
    Consolidator.maybe_consolidate_by_tokens = orig_maybe_consolidate


class TestConsolidationBridge:
    async def test_consolidation_syncs_categorized_memory(self, tmp_path):
        from ava.patches.a_schema_patch import apply_schema_patch
        from ava.patches.loop_patch import apply_loop_patch

        apply_schema_patch()
        apply_loop_patch()

        store = MemoryStore(tmp_path)
        provider = MagicMock()
        provider.chat_with_retry = AsyncMock(return_value=SimpleNamespace(content="保留了用户喜欢乌龙茶"))
        sessions = MagicMock()
        consolidator = Consolidator(
            store=store,
            provider=provider,
            model="test-model",
            sessions=sessions,
            context_window_tokens=4096,
            build_messages=MagicMock(return_value=[]),
            get_tool_definitions=MagicMock(return_value=[]),
            max_completion_tokens=512,
        )

        categorized_memory = MagicMock()

        class DummyLoop:
            def __init__(self, memory):
                self.categorized_memory = memory

        loop = DummyLoop(categorized_memory)
        consolidator._ava_agent_loop_ref = weakref.ref(loop)
        consolidator.estimate_session_prompt_tokens = MagicMock(
            side_effect=[(5000, "stub"), (100, "stub")]
        )

        session = SimpleNamespace(
            key="telegram:12345",
            last_consolidated=0,
            messages=[
                {"role": "user", "content": "我喜欢乌龙茶"},
                {"role": "assistant", "content": "记住了"},
                {"role": "user", "content": "继续聊别的"},
            ],
            get_history=lambda max_messages=0: [],
        )

        await consolidator.maybe_consolidate_by_tokens(session)

        categorized_memory.on_consolidate.assert_called_once()
        args = categorized_memory.on_consolidate.call_args.args
        assert args[0] == "telegram"
        assert args[1] == "12345"
        assert "乌龙茶" in args[2]
        assert args[3] == ""
        assert session.last_consolidated == 2
        sessions.save.assert_called_once_with(session)

    async def test_raw_fallback_not_synced(self, tmp_path):
        from ava.patches.a_schema_patch import apply_schema_patch
        from ava.patches.loop_patch import apply_loop_patch

        apply_schema_patch()
        apply_loop_patch()

        store = MemoryStore(tmp_path)
        provider = MagicMock()
        provider.chat_with_retry = AsyncMock(side_effect=Exception("llm failed"))
        consolidator = Consolidator(
            store=store,
            provider=provider,
            model="test-model",
            sessions=MagicMock(),
            context_window_tokens=4096,
            build_messages=MagicMock(return_value=[]),
            get_tool_definitions=MagicMock(return_value=[]),
            max_completion_tokens=512,
        )

        categorized_memory = MagicMock()

        class DummyLoop:
            def __init__(self, memory):
                self.categorized_memory = memory

        consolidator._ava_agent_loop_ref = weakref.ref(DummyLoop(categorized_memory))
        consolidator._ava_current_session_key = "telegram:12345"

        result = await consolidator.archive(
            [
                {"role": "user", "content": "我喜欢乌龙茶"},
                {"role": "assistant", "content": "记住了"},
            ]
        )

        assert result is None
        categorized_memory.on_consolidate.assert_not_called()
        last_entry = store._read_last_entry()
        assert last_entry is not None
        assert last_entry["content"].startswith("[RAW] ")

    async def test_empty_messages_no_sync(self, tmp_path):
        from ava.patches.a_schema_patch import apply_schema_patch
        from ava.patches.loop_patch import apply_loop_patch

        apply_schema_patch()
        apply_loop_patch()

        store = MemoryStore(tmp_path)
        provider = MagicMock()
        provider.chat_with_retry = AsyncMock()
        consolidator = Consolidator(
            store=store,
            provider=provider,
            model="test-model",
            sessions=MagicMock(),
            context_window_tokens=4096,
            build_messages=MagicMock(return_value=[]),
            get_tool_definitions=MagicMock(return_value=[]),
            max_completion_tokens=512,
        )

        categorized_memory = MagicMock()

        class DummyLoop:
            def __init__(self, memory):
                self.categorized_memory = memory

        consolidator._ava_agent_loop_ref = weakref.ref(DummyLoop(categorized_memory))
        consolidator._ava_current_session_key = "telegram:12345"

        result = await consolidator.archive([])

        assert result is None
        provider.chat_with_retry.assert_not_called()
        categorized_memory.on_consolidate.assert_not_called()
        assert store._read_last_entry() is None
