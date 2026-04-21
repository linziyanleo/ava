from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ava.agent.bg_tasks import BackgroundTaskStore
from ava.storage import Database
from ava.tools.codex import CodexTool


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
        return "task_codex_001"


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

    task_id = store.submit_coding_task(
        executor=_executor,
        origin_session_key="console:mock-session-9",
        prompt="Review the workspace with Codex.",
        project_path=str(tmp_path),
        timeout=5,
        auto_continue=True,
        task_type="codex",
    )

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
