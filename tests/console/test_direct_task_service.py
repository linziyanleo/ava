from __future__ import annotations

from types import SimpleNamespace

import pytest

from ava.agent.bg_tasks import SubmitResult
from ava.console.services.direct_task_service import DirectTaskService


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
