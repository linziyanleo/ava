"""Tests for channel_patch TelegramChannel extensions."""

import pytest
from pydantic import BaseModel, Field

from nanobot.bus.queue import MessageBus
from nanobot.channels.telegram import TelegramChannel, TelegramConfig


@pytest.fixture(autouse=True)
def _restore_telegram_methods():
    """Save and restore patched TelegramChannel methods to avoid test pollution."""
    original_init = TelegramChannel.__init__
    original_send = TelegramChannel.send
    original_send_delta = TelegramChannel.send_delta
    original_start = TelegramChannel.start
    yield
    TelegramChannel.__init__ = original_init
    TelegramChannel.send = original_send
    TelegramChannel.send_delta = original_send_delta
    TelegramChannel.start = original_start


class TestChannelPatch:
    def test_patch_applies_without_error(self):
        """T6.0: apply_channel_patch runs without error."""
        from ava.patches.channel_patch import apply_channel_patch

        result = apply_channel_patch()
        assert "config normalization" in result.lower()

    def test_send_method_replaced(self):
        """T6.1: TelegramChannel.send is replaced."""
        original_send = TelegramChannel.send

        from ava.patches.channel_patch import apply_channel_patch

        apply_channel_patch()

        assert TelegramChannel.send is not original_send

    def test_no_session_load_patch(self):
        """T6.2: channel_patch should not patch SessionManager._load."""
        import inspect
        from ava.patches.channel_patch import apply_channel_patch

        source = inspect.getsource(apply_channel_patch)
        assert "SessionManager._load" not in source
        assert "patched_load" not in source

    def test_batcher_in_source(self):
        """T6.3: MessageBatcher is used in the patch."""
        import inspect
        from ava.patches.channel_patch import apply_channel_patch

        source = inspect.getsource(apply_channel_patch)
        assert "MessageBatcher" in source
        assert "batcher" in source

    def test_init_normalizes_foreign_pydantic_config(self):
        """T6.4: foreign Pydantic config should be normalized into TelegramConfig."""
        from ava.patches.channel_patch import apply_channel_patch

        class ForeignTelegramConfig(BaseModel):
            enabled: bool = True
            token: str = "123:abc"
            allow_from: list[str] = Field(default_factory=lambda: ["*"])
            stream_edit_interval: float = 1.25

        apply_channel_patch()

        channel = TelegramChannel(ForeignTelegramConfig(), MessageBus())

        assert isinstance(channel.config, TelegramConfig)
        assert not isinstance(channel.config, ForeignTelegramConfig)
        assert channel.config.token == "123:abc"
