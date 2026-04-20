from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ava.agent.bg_tasks import BackgroundTaskStore, TaskSnapshot
from nanobot.session.manager import Session


class _FakeSessions:
    def __init__(self) -> None:
        self.session = Session(key="telegram:1")
        self.save_calls = 0

    def get_or_create(self, key: str) -> Session:
        assert key == "telegram:1"
        return self.session

    def save(self, session: Session) -> None:
        assert session is self.session
        self.save_calls += 1


class _FakeBus:
    def __init__(self) -> None:
        self.messages = []

    async def publish_outbound(self, message) -> None:
        self.messages.append(message)


@pytest.mark.asyncio
async def test_on_complete_is_idempotent_for_same_task():
    sessions = _FakeSessions()
    bus = _FakeBus()
    loop = SimpleNamespace(sessions=sessions, bus=bus)
    store = BackgroundTaskStore(db=None)
    store.set_agent_loop(loop)
    store._run_post_task_hooks = AsyncMock(return_value="")
    store._trigger_continuation = AsyncMock()

    snapshot = TaskSnapshot(
        task_id="abc123",
        task_type="codex",
        origin_session_key="telegram:1",
        status="succeeded",
        prompt_preview="fix the bug",
        elapsed_ms=100,
        auto_continue=True,
    )
    result = {"result": "ok"}

    await store._on_complete(snapshot, result)
    await store._on_complete(snapshot, result)

    assert len(sessions.session.messages) == 1
    assert sessions.session.messages[0]["content"] == (
        "[Background Task abc123 SUCCESS]\n"
        "Type: codex | Duration: 100ms\n\n"
        "ok"
    )
    assert sessions.save_calls == 1
    assert len(bus.messages) == 1
    assert store._run_post_task_hooks.await_count == 1
    store._trigger_continuation.assert_awaited_once_with(snapshot, "", result=result)
