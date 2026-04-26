from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ava.agent.bg_tasks import BackgroundTaskStore, SubmitResult, TaskSnapshot
from ava.storage import Database
from ava.tools.codex import CodexTool
from nanobot.session.manager import Session


class _SessionBackedSessions:
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


class _FakeSessions:
    def __init__(self) -> None:
        self._session = SimpleNamespace(messages=[])
        self.saved_session = None

    def get_or_create(self, _session_key: str):
        return self._session

    def save(self, session) -> None:
        self.saved_session = session


class _FakeLoop:
    def __init__(self) -> None:
        self.sessions = _FakeSessions()
        self.processed: list[dict[str, str]] = []
        self.bus = None

    async def process_direct(
        self,
        content: str,
        *,
        session_key: str,
        channel: str,
        chat_id: str,
    ):
        self.processed.append({
            "content": content,
            "session_key": session_key,
            "channel": channel,
            "chat_id": chat_id,
        })
        return None


class _CapturingTaskStore:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def submit_coding_task(self, **kwargs):
        self.calls.append(kwargs)
        return SubmitResult(
            task_id="task_codex_001",
            reused=False,
            replaced_task_id=None,
            workspace_id="",
            active_in_session=[],
        )


@pytest.mark.asyncio
async def test_on_complete_is_idempotent_for_same_task():
    sessions = _SessionBackedSessions()
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


@pytest.mark.asyncio
async def test_codex_readonly_does_not_auto_continue(tmp_path, monkeypatch):
    monkeypatch.setattr("ava.tools.codex.shutil.which", lambda name: "/usr/bin/codex")

    task_store = _CapturingTaskStore()
    tool = CodexTool(workspace=tmp_path, task_store=task_store)

    result = await tool.execute(
        prompt="Inspect the current project without editing files.",
        mode="readonly",
    )

    assert "task_codex_001" in result
    assert task_store.calls[0]["auto_continue"] is False


@pytest.mark.asyncio
async def test_failed_task_continues_even_without_auto_continue():
    loop = _FakeLoop()
    store = BackgroundTaskStore(db=None)
    store.set_agent_loop(loop)
    store._run_post_task_hooks = AsyncMock(return_value="")
    store._trigger_continuation = AsyncMock()

    snapshot = TaskSnapshot(
        task_id="fail123",
        task_type="codex",
        origin_session_key="console:mock-session-2",
        status="failed",
        prompt_preview="readonly review",
        elapsed_ms=120,
        error_message="Codex failed to start",
        auto_continue=False,
    )

    await store._on_complete(snapshot, None)

    assert loop.sessions.saved_session is loop.sessions._session
    store._trigger_continuation.assert_awaited_once_with(snapshot, "", result=None)


@pytest.mark.asyncio
async def test_bg_tasks_persist_codex_thread_id_as_general_run_id(tmp_path: Path):
    db = Database(tmp_path / "bg-tasks.sqlite3")
    store = BackgroundTaskStore(db=db)
    loop = _FakeLoop()
    store.set_agent_loop(loop)

    async def _executor(**_kwargs):
        return {
            "result": "Codex finished reviewing the workspace.",
            "thread_id": "thread_codex_123",
        }

    submit = store.submit_coding_task(
        executor=_executor,
        origin_session_key="console:mock-session-9",
        prompt="Review the workspace with Codex.",
        project_path=str(tmp_path),
        timeout=5,
        auto_continue=True,
        task_type="codex",
    )
    assert isinstance(submit, SubmitResult)
    task_id = submit.task_id

    await store._tasks[task_id]

    status = store.get_status(task_id=task_id)
    task = status["tasks"][0]

    assert task["cli_run_id"] == "thread_codex_123"
    assert task["cli_session_id"] == "thread_codex_123"

    row = db.fetchone("SELECT extra FROM bg_tasks WHERE task_id = ?", (task_id,))
    assert row is not None
    extra = json.loads(row["extra"] or "{}")
    assert extra["cli_run_id"] == "thread_codex_123"
    assert extra["cli_session_id"] == "thread_codex_123"

    assert loop.processed
    assert loop.processed[0]["content"].startswith("[Background Task Completed — SUCCESS]")


@pytest.mark.asyncio
async def test_workspace_aware_submit_and_query(tmp_path: Path):
    from ava.agent.worktree_manager import ProjectTarget, make_inplace_workspace

    db = Database(tmp_path / "bg-tasks.sqlite3")
    store = BackgroundTaskStore(db=db)
    loop = _FakeLoop()
    store.set_agent_loop(loop)

    target = ProjectTarget(
        repo_root=str(tmp_path),
        workdir_relpath=".",
        requested_path=str(tmp_path),
        workspace_key=f"{tmp_path}:.",
    )
    ws = make_inplace_workspace(target, workspace_id="ws-test-1")

    async def _executor(**_kw):
        return {"result": "done", "session_id": "s1"}

    submit = store.submit_coding_task(
        executor=_executor,
        origin_session_key="test:sess-1",
        prompt="Test workspace-aware submit",
        timeout=5,
        target=target,
        workspace=ws,
    )

    assert isinstance(submit, SubmitResult)
    assert submit.workspace_id == "ws-test-1"
    assert not submit.reused
    assert submit.replaced_task_id is None

    by_ws = store.find_active_by_workspace("ws-test-1")
    assert len(by_ws) == 1
    assert by_ws[0].workspace_key == f"{tmp_path}:."

    by_target = store.find_active_by_target(f"{tmp_path}:.")
    assert len(by_target) == 1

    by_session = store.list_active_by_session("test:sess-1")
    assert len(by_session) == 1

    await store._tasks[submit.task_id]

    status = store.get_status(task_id=submit.task_id)
    task_dict = status["tasks"][0]
    assert task_dict["workspace_id"] == "ws-test-1"
    assert task_dict["isolation_mode"] == "inplace"
    assert task_dict["repo_root"] == str(tmp_path)

    row = db.fetchone("SELECT extra FROM bg_tasks WHERE task_id = ?", (submit.task_id,))
    extra = json.loads(row["extra"] or "{}")
    assert extra["workspace_id"] == "ws-test-1"
    assert extra["workspace_key"] == f"{tmp_path}:."


@pytest.mark.asyncio
async def test_workspace_exclusive_replaces_existing(tmp_path: Path):
    from ava.agent.worktree_manager import ProjectTarget, make_inplace_workspace

    db = Database(tmp_path / "bg-tasks.sqlite3")
    store = BackgroundTaskStore(db=db)
    loop = _FakeLoop()
    store.set_agent_loop(loop)

    target = ProjectTarget(
        repo_root=str(tmp_path),
        workdir_relpath=".",
        requested_path=str(tmp_path),
        workspace_key=f"{tmp_path}:.",
    )
    ws = make_inplace_workspace(target, workspace_id="ws-exclusive")

    import asyncio

    async def _slow_executor(**_kw):
        await asyncio.sleep(60)
        return {"result": "should not complete"}

    submit1 = store.submit_coding_task(
        executor=_slow_executor,
        origin_session_key="test:sess-2",
        prompt="First task",
        timeout=120,
        target=target,
        workspace=ws,
    )

    submit2 = store.submit_coding_task(
        executor=_slow_executor,
        origin_session_key="test:sess-2",
        prompt="Replacing task",
        timeout=120,
        target=target,
        workspace=ws,
        workspace_exclusive=True,
    )

    assert submit2.replaced_task_id == submit1.task_id

    await asyncio.sleep(0.05)

    task1 = store._tasks.get(submit1.task_id)
    if task1:
        assert task1.cancelled() or task1.done()

    for tid in [submit1.task_id, submit2.task_id]:
        task = store._tasks.get(tid)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
