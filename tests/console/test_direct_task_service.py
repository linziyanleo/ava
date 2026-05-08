from __future__ import annotations

from types import SimpleNamespace

import pytest

from ava.agent.bg_tasks import SubmitResult
from ava.console.services.config_service import ConfigService
from ava.console.services.direct_task_service import DirectTaskService
from ava.console.services.media_service import MediaService


class _FakeBgStore:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def submit_task(self, **kwargs):
        self.calls.append(kwargs)
        return SubmitResult(
            task_id=f"{kwargs['task_type']}_001",
            reused=False,
            replaced_task_id=None,
            workspace_id="",
            active_in_session=[],
        )

    def get_status(self, task_id: str, include_finished: bool = True):
        return {
            "running": 1,
            "total": 1,
            "tasks": [{
                "task_id": task_id,
                "status": "queued",
            }],
        }


@pytest.mark.asyncio
async def test_submit_codex_direct_task_uses_session_context(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "ava.console.services.direct_task_service.shutil.which",
        lambda name: "/usr/local/bin/codex" if name == "codex" else None,
    )
    monkeypatch.setattr(
        "ava.tools.codex.shutil.which",
        lambda name: "/usr/local/bin/codex" if name == "codex" else None,
    )

    bg_store = _FakeBgStore()
    service = DirectTaskService(
        agent_loop=SimpleNamespace(tools=SimpleNamespace(get=lambda _name: None)),
        workspace=tmp_path,
        bg_store=bg_store,
    )

    result = await service.submit(
        task_type="codex",
        prompt="fix auth",
        session_key="console:abc123",
        conversation_id="conv_1",
        turn_seq=4,
        project_path=str(tmp_path),
        params={"mode": "readonly"},
    )

    assert result == {
        "task_id": "codex_001",
        "status": "queued",
        "task_type": "codex",
    }
    assert len(bg_store.calls) == 1
    call = bg_store.calls[0]
    assert call["task_type"] == "codex"
    assert call["origin_session_key"] == "console:abc123"
    assert call["origin_conversation_id"] == "conv_1"
    assert call["origin_turn_seq"] == 4
    assert call["mode"] == "readonly"
    assert call["project"] == str(tmp_path)
    assert call["auto_continue"] is False


@pytest.mark.asyncio
async def test_submit_claude_code_direct_task_defaults_standard_auto_continue(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "ava.console.services.direct_task_service.shutil.which",
        lambda name: "/usr/local/bin/claude" if name == "claude" else None,
    )
    monkeypatch.setattr(
        "ava.tools.claude_code.shutil.which",
        lambda name: "/usr/local/bin/claude" if name == "claude" else None,
    )

    bg_store = _FakeBgStore()
    service = DirectTaskService(
        agent_loop=SimpleNamespace(tools=SimpleNamespace(get=lambda _name: None)),
        workspace=tmp_path,
        bg_store=bg_store,
    )

    result = await service.submit(
        task_type="claude_code",
        prompt="write tests",
        session_key="console:abc123",
        project_path=str(tmp_path),
        params={},
    )

    assert result["task_id"] == "claude_code_001"
    call = bg_store.calls[0]
    assert call["task_type"] == "claude_code"
    assert call["mode"] == "standard"
    assert call["auto_continue"] is True


@pytest.mark.asyncio
async def test_submit_codex_direct_task_uses_agent_specific_config(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "ava.console.services.direct_task_service.shutil.which",
        lambda name: "/usr/local/bin/codex" if name == "codex" else None,
    )
    monkeypatch.setattr(
        "ava.tools.codex.shutil.which",
        lambda name: "/usr/local/bin/codex" if name == "codex" else None,
    )

    config = ConfigService(tmp_path)
    config.update_config(
        "codex-config.toml",
        'model = "gpt-5"\ntimeout = 42\napi_base = "https://gateway.example/v1"\n',
        expected_mtime=0,
    )
    bg_store = _FakeBgStore()
    service = DirectTaskService(
        agent_loop=SimpleNamespace(tools=SimpleNamespace(get=lambda _name: None)),
        workspace=tmp_path,
        bg_store=bg_store,
        config_service=config,
    )

    await service.submit(
        task_type="codex",
        prompt="fix auth",
        session_key="console:abc123",
        project_path=str(tmp_path),
        params={},
    )

    assert bg_store.calls[0]["timeout"] == 42


@pytest.mark.asyncio
async def test_submit_claude_code_direct_task_uses_agent_specific_config(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "ava.console.services.direct_task_service.shutil.which",
        lambda name: "/usr/local/bin/claude" if name == "claude" else None,
    )
    monkeypatch.setattr(
        "ava.tools.claude_code.shutil.which",
        lambda name: "/usr/local/bin/claude" if name == "claude" else None,
    )

    config = ConfigService(tmp_path)
    config.update_config(
        "claude-code-settings.json",
        '{"model":"claude-sonnet-4","timeout":33,"maxTurns":9}',
        expected_mtime=0,
    )
    bg_store = _FakeBgStore()
    service = DirectTaskService(
        agent_loop=SimpleNamespace(tools=SimpleNamespace(get=lambda _name: None)),
        workspace=tmp_path,
        bg_store=bg_store,
        config_service=config,
    )

    await service.submit(
        task_type="claude_code",
        prompt="write tests",
        session_key="console:abc123",
        project_path=str(tmp_path),
        params={},
    )

    assert bg_store.calls[0]["timeout"] == 33


@pytest.mark.asyncio
async def test_submit_image_gen_direct_task_passes_reference_image(tmp_path, monkeypatch):
    instances = []

    class FakeImageGenTool:
        def __init__(self, **_kwargs):
            self.calls: list[dict] = []
            instances.append(self)

        async def execute(
            self,
            *,
            prompt: str,
            reference_image: str | None = None,
            continue_after_completion: bool | None = None,
        ) -> str:
            self.calls.append({
                "prompt": prompt,
                "reference_image": reference_image,
                "continue_after_completion": continue_after_completion,
            })
            return "Image generation task started (id: image_gen_001). Use /task or /bg-tasks to check progress."

    monkeypatch.setattr("ava.console.services.direct_task_service.ImageGenTool", FakeImageGenTool)

    media = MediaService(media_dir=tmp_path / "generated", chat_upload_dir=tmp_path / "chat-uploads")
    upload = media.save_chat_upload(filename="reference.png", mime_type="image/png", data=b"png")
    service = DirectTaskService(
        agent_loop=SimpleNamespace(tools=SimpleNamespace(get=lambda _name: None)),
        workspace=tmp_path,
        bg_store=_FakeBgStore(),
        media_service=media,
    )

    result = await service.submit(
        task_type="image_gen",
        prompt="make it warmer",
        session_key="console:abc123",
        params={"reference_image": upload["path"]},
    )

    assert result == {
        "task_id": "image_gen_001",
        "status": "queued",
        "task_type": "image_gen",
    }
    assert instances[0].calls == [{
        "prompt": "make it warmer",
        "reference_image": upload["media_path"],
        "continue_after_completion": None,
    }]


@pytest.mark.asyncio
async def test_submit_image_gen_rejects_arbitrary_reference_path(tmp_path, monkeypatch):
    constructed = False

    class FakeImageGenTool:
        def __init__(self, **_kwargs):
            nonlocal constructed
            constructed = True

    monkeypatch.setattr("ava.console.services.direct_task_service.ImageGenTool", FakeImageGenTool)

    secret = tmp_path / "secret.png"
    secret.write_bytes(b"png")
    service = DirectTaskService(
        agent_loop=SimpleNamespace(tools=SimpleNamespace(get=lambda _name: None)),
        workspace=tmp_path,
        bg_store=_FakeBgStore(),
        media_service=MediaService(media_dir=tmp_path / "generated", chat_upload_dir=tmp_path / "chat-uploads"),
    )

    with pytest.raises(ValueError, match="previously uploaded image"):
        await service.submit(
            task_type="image_gen",
            prompt="use this",
            session_key="console:abc123",
            params={"reference_image": str(secret)},
        )
    assert constructed is False


@pytest.mark.asyncio
async def test_submit_image_gen_rejects_non_image_reference(tmp_path, monkeypatch):
    class FakeImageGenTool:
        def __init__(self, **_kwargs):
            pass

    monkeypatch.setattr("ava.console.services.direct_task_service.ImageGenTool", FakeImageGenTool)

    media = MediaService(media_dir=tmp_path / "generated", chat_upload_dir=tmp_path / "chat-uploads")
    upload = media.save_chat_upload(filename="notes.txt", mime_type="text/plain", data=b"notes")
    service = DirectTaskService(
        agent_loop=SimpleNamespace(tools=SimpleNamespace(get=lambda _name: None)),
        workspace=tmp_path,
        bg_store=_FakeBgStore(),
        media_service=media,
    )

    with pytest.raises(ValueError, match="image file"):
        await service.submit(
            task_type="image_gen",
            prompt="use this",
            session_key="console:abc123",
            params={"reference_image": upload["path"]},
        )


@pytest.mark.asyncio
async def test_submit_image_gen_parses_continue_after_completion_string(tmp_path, monkeypatch):
    instances = []

    class FakeImageGenTool:
        def __init__(self, **_kwargs):
            self.calls: list[dict] = []
            instances.append(self)

        async def execute(
            self,
            *,
            prompt: str,
            reference_image: str | None = None,
            continue_after_completion: bool | None = None,
        ) -> str:
            self.calls.append({
                "prompt": prompt,
                "reference_image": reference_image,
                "continue_after_completion": continue_after_completion,
            })
            return "Image generation task started (id: image_gen_001). Use /task or /bg-tasks to check progress."

    monkeypatch.setattr("ava.console.services.direct_task_service.ImageGenTool", FakeImageGenTool)

    service = DirectTaskService(
        agent_loop=SimpleNamespace(tools=SimpleNamespace(get=lambda _name: None)),
        workspace=tmp_path,
        bg_store=_FakeBgStore(),
        media_service=MediaService(media_dir=tmp_path / "generated", chat_upload_dir=tmp_path / "chat-uploads"),
    )

    await service.submit(
        task_type="image_gen",
        prompt="make an icon",
        session_key="console:abc123",
        params={"continue_after_completion": "false"},
    )

    assert instances[0].calls[0]["continue_after_completion"] is False


@pytest.mark.asyncio
async def test_submit_rejects_empty_prompt(tmp_path):
    service = DirectTaskService(
        agent_loop=SimpleNamespace(tools=SimpleNamespace(get=lambda _name: None)),
        workspace=tmp_path,
        bg_store=_FakeBgStore(),
    )

    with pytest.raises(ValueError, match="prompt is required"):
        await service.submit(
            task_type="codex",
            prompt=" ",
            session_key="console:abc123",
        )
