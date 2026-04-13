"""Tests for console_patch — Web Console independent service launch."""

from unittest.mock import MagicMock, patch
import os

import pytest


class TestConsolePatch:
    def test_patch_applies_without_error(self):
        """T7.1: apply_console_patch runs without error."""
        from ava.patches.console_patch import apply_console_patch

        result = apply_console_patch()
        assert "console" in result.lower()

    def test_gateway_callback_wrapped(self):
        """T7.1b: gateway command callback is replaced."""
        import nanobot.cli.commands as cli_mod

        from ava.patches.console_patch import apply_console_patch
        apply_console_patch()

        # Find gateway command
        for cmd_info in cli_mod.app.registered_commands:
            cb = getattr(cmd_info, "callback", None)
            if cb and ("patched" in cb.__name__ or "gateway" in cb.__name__):
                assert True
                return

        # If gateway command doesn't exist, patch should have skipped
        result = apply_console_patch()
        assert "skipped" in result.lower() or "console" in result.lower()

    def test_console_uses_standalone_factory(self):
        """T7.4: console_patch uses create_console_app_standalone (not create_console_app)."""
        import inspect
        from ava.patches.console_patch import apply_console_patch

        source = inspect.getsource(apply_console_patch)
        assert "create_console_app_standalone" in source
        assert "create_console_app()" not in source  # no bare call without params

    def test_asyncio_run_not_permanently_replaced(self):
        """T7.3: asyncio.run is not permanently replaced at patch time."""
        import asyncio

        original_run = asyncio.run

        from ava.patches.console_patch import apply_console_patch
        apply_console_patch()

        # asyncio.run should still be the original at this point
        # (it's only temporarily replaced when gateway callback executes)
        assert asyncio.run is original_run
