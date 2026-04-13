"""Tests for transcription_patch — Groq transcription proxy injection."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest


@pytest.fixture(autouse=True)
def _restore_transcription_targets(monkeypatch):
    """每个测试后恢复被 patch 的类方法，避免跨用例污染。"""
    from nanobot.channels.base import BaseChannel
    from nanobot.channels.manager import ChannelManager
    from nanobot.providers.transcription import GroqTranscriptionProvider

    original_base = BaseChannel.transcribe_audio
    original_resolve = ChannelManager._resolve_transcription_key
    original_groq = GroqTranscriptionProvider.transcribe
    yield
    monkeypatch.setattr(BaseChannel, "transcribe_audio", original_base, raising=False)
    monkeypatch.setattr(ChannelManager, "_resolve_transcription_key", original_resolve, raising=False)
    monkeypatch.setattr(GroqTranscriptionProvider, "transcribe", original_groq, raising=False)


class TestTranscriptionPatch:
    def test_skip_when_no_proxy_configured(self, monkeypatch, tmp_path):
        """T11.1: patch skips when config contains no proxy."""
        fake_home = tmp_path / "home"
        nanobot_dir = fake_home / ".nanobot"
        nanobot_dir.mkdir(parents=True)
        (nanobot_dir / "config.json").write_text(json.dumps({"tools": {"web": {}}}), encoding="utf-8")
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

        from ava.patches.transcription_patch import apply_transcription_patch

        result = apply_transcription_patch()
        assert "skip" in result.lower()

    def test_patch_applies_with_proxy(self, monkeypatch, tmp_path):
        """T11.2: patch applies when proxy config exists."""
        fake_home = tmp_path / "home"
        nanobot_dir = fake_home / ".nanobot"
        nanobot_dir.mkdir(parents=True)
        (nanobot_dir / "config.json").write_text(
            json.dumps({"tools": {"web": {"proxy": "socks5://127.0.0.1:1080"}}}),
            encoding="utf-8",
        )
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

        from nanobot.providers.transcription import GroqTranscriptionProvider
        from ava.patches.transcription_patch import apply_transcription_patch

        result = apply_transcription_patch()
        assert "proxy=socks5://127.0.0.1:1080" in result
        assert getattr(GroqTranscriptionProvider.transcribe, "_ava_transcription_patched", False) is True

    def test_idempotent(self, monkeypatch, tmp_path):
        """T11.3: repeated apply returns skipped once patched."""
        fake_home = tmp_path / "home"
        nanobot_dir = fake_home / ".nanobot"
        nanobot_dir.mkdir(parents=True)
        (nanobot_dir / "config.json").write_text(
            json.dumps({"tools": {"web": {"proxy": "socks5://127.0.0.1:1080"}}}),
            encoding="utf-8",
        )
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

        from ava.patches.transcription_patch import apply_transcription_patch

        apply_transcription_patch()
        result = apply_transcription_patch()
        assert "skipped" in result.lower()

    def test_channel_manager_routes_gemini_and_zenmux_keys(self, monkeypatch, tmp_path):
        """T11.4: gemini/zenmux transcription provider 应路由到对应 key。"""
        fake_home = tmp_path / "home"
        nanobot_dir = fake_home / ".nanobot"
        nanobot_dir.mkdir(parents=True)
        (nanobot_dir / "config.json").write_text(json.dumps({"tools": {"web": {}}}), encoding="utf-8")
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

        from ava.patches.transcription_patch import apply_transcription_patch
        from nanobot.channels.manager import ChannelManager

        apply_transcription_patch()
        manager = ChannelManager.__new__(ChannelManager)
        manager.config = SimpleNamespace(
            providers=SimpleNamespace(
                gemini=SimpleNamespace(api_key="gemini-key"),
                zenmux=SimpleNamespace(api_key="zenmux-key"),
                groq=SimpleNamespace(api_key="groq-key"),
                openai=SimpleNamespace(api_key="openai-key"),
            )
        )

        assert manager._resolve_transcription_key("gemini") == "gemini-key"
        assert manager._resolve_transcription_key("zenmux") == "zenmux-key"
        assert manager._resolve_transcription_key("groq") == "groq-key"

    @pytest.mark.asyncio
    async def test_base_channel_transcribes_with_gemini_vertex(self, monkeypatch, tmp_path):
        """T11.5: gemini transcription provider 应走 ZenMux Vertex generateContent。"""
        fake_home = tmp_path / "home"
        nanobot_dir = fake_home / ".nanobot"
        nanobot_dir.mkdir(parents=True)
        (nanobot_dir / "config.json").write_text(
            json.dumps(
                {
                    "channels": {"transcriptionProvider": "gemini"},
                    "providers": {
                        "gemini": {
                            "apiKey": "gemini-key",
                            "apiBase": "https://zenmux.ai/api/vertex-ai/v1",
                        }
                    },
                    "tools": {"web": {}},
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

        captured: dict[str, object] = {}

        class _FakeResponse:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict[str, object]:
                return {
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {"text": "hello from zenmux transcript"},
                                ]
                            }
                        }
                    ]
                }

        class _FakeAsyncClient:
            def __init__(self, **kwargs):
                captured["client_kwargs"] = kwargs

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def post(self, url: str, *, headers=None, json=None):
                captured["url"] = url
                captured["headers"] = headers or {}
                captured["json"] = json or {}
                return _FakeResponse()

        monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)

        from ava.patches.transcription_patch import apply_transcription_patch
        from nanobot.channels.base import BaseChannel

        class _DummyChannel(BaseChannel):
            async def start(self) -> None:
                return None

            async def stop(self) -> None:
                return None

            async def send(self, msg) -> None:
                return None

        apply_transcription_patch()
        audio_file = tmp_path / "sample.wav"
        audio_file.write_bytes(b"wav-bytes")

        channel = _DummyChannel({"enabled": True}, MagicMock())
        channel.transcription_provider = "gemini"
        channel.transcription_api_key = "gemini-key"

        result = await channel.transcribe_audio(audio_file)

        assert result == "hello from zenmux transcript"
        assert captured["url"] == (
            "https://zenmux.ai/api/vertex-ai/v1/publishers/google/models/"
            "gemini-2.5-flash-lite:generateContent"
        )
        assert captured["headers"] == {
            "Authorization": "Bearer gemini-key",
            "Content-Type": "application/json",
        }
        assert captured["json"]["contents"][0]["parts"][1]["inlineData"]["mimeType"] == "audio/wav"
