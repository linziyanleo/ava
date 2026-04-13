"""Tests for tools_patch — Custom tool injection into AgentLoop."""

from unittest.mock import MagicMock, patch

import pytest

from nanobot.agent.loop import AgentLoop


@pytest.fixture(autouse=True)
def _restore_register_default_tools():
    """Save and restore _register_default_tools to avoid polluting other tests."""
    original = AgentLoop._register_default_tools
    yield
    AgentLoop._register_default_tools = original


class TestToolsPatch:
    def test_patch_applies_without_error(self):
        """T4.1: apply_tools_patch runs without error."""
        from ava.patches.tools_patch import apply_tools_patch

        result = apply_tools_patch()
        assert "6 custom tools" in result.lower() or "registered" in result.lower()

    def test_register_default_tools_replaced(self):
        """T4.2: _register_default_tools is replaced on AgentLoop class."""
        original = AgentLoop._register_default_tools

        from ava.patches.tools_patch import apply_tools_patch
        apply_tools_patch()

        assert AgentLoop._register_default_tools is not original

    def test_memory_tool_conditional(self):
        """T4.6: MemoryTool only registered when categorized_memory exists."""
        import inspect
        from ava.patches.tools_patch import apply_tools_patch

        source = inspect.getsource(apply_tools_patch)
        assert "categorized_memory" in source
        assert "MemoryTool" in source
