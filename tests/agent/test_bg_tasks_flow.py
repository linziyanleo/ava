"""End-to-end flow tests simulating actual runtime behavior.

Tests the full lifecycle: tool.execute -> resolve_target -> submit_coding_task
-> background execution -> completion callback -> status query with workspace metadata.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ava.agent.bg_tasks import BackgroundTaskStore, SubmitResult
from ava.agent.worktree_manager import resolve_target, make_inplace_workspace, ProjectTarget
from ava.storage import Database
from ava.tools.codex import CodexTool
from ava.tools.claude_code import ClaudeCodeTool


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

    async def process_direct(self, content: str, *, session_key: str, channel: str, chat_id: str):
        self.processed.append({"content": content, "session_key": session_key})
        return None


# ---------------------------------------------------------------------------
# Flow 1: Codex tool full lifecycle
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_codex_full_lifecycle(tmp_path: Path, monkeypatch):
    """Simulate: user calls codex tool -> task runs in background -> completes
    -> check status has workspace metadata -> check DB persistence."""
    monkeypatch.setattr("ava.tools.codex.shutil.which", lambda name: "/usr/bin/codex")

    db = Database(tmp_path / "flow.sqlite3")
    store = BackgroundTaskStore(db=db)
    loop = _FakeLoop()
    store.set_agent_loop(loop)

    tool = CodexTool(workspace=tmp_path, task_store=store)
    tool.set_context("telegram", "user123", session_key="telegram:user123")

    captured_kwargs: dict = {}

    async def _fake_background(**kwargs):
        captured_kwargs.update(kwargs)
        return {"result": "Fixed the bug in main.py", "thread_id": "run_abc123"}

    monkeypatch.setattr(tool, "_run_background", _fake_background)

    result_text = await tool.execute(
        prompt="Fix the null pointer in main.py",
        project_path=str(tmp_path),
        mode="standard",
    )

    assert "task started" in result_text.lower()
    task_id = result_text.split("id: ")[1].split(")")[0].rstrip(".")

    await asyncio.sleep(0.1)

    status = store.get_status(task_id=task_id)
    assert status["total"] == 1
    task = status["tasks"][0]

    assert task["status"] == "succeeded"
    assert task["workspace_id"] != ""
    assert task["isolation_mode"] == "inplace"
    assert task["repo_root"] != ""
    assert task["cli_run_id"] == "run_abc123"

    row = db.fetchone("SELECT extra FROM bg_tasks WHERE task_id = ?", (task_id,))
    extra = json.loads(row["extra"])
    assert extra["workspace_id"] == task["workspace_id"]
    assert extra["workspace_key"] == task["workspace_key"]

    assert loop.processed, "completion callback should have triggered continuation"
    assert "SUCCESS" in loop.processed[0]["content"]


# ---------------------------------------------------------------------------
# Flow 2: Claude Code tool with workspace replace
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_claude_code_workspace_replace_flow(tmp_path: Path, monkeypatch):
    """Simulate: user submits two claude_code tasks to same project
    -> second should replace first -> only second completes."""
    db = Database(tmp_path / "flow2.sqlite3")
    store = BackgroundTaskStore(db=db)
    loop = _FakeLoop()
    store.set_agent_loop(loop)

    tool = ClaudeCodeTool(workspace=tmp_path, task_store=store)
    tool.set_context("console", "session-1", session_key="console:session-1")

    call_count = 0
    gate = asyncio.Event()

    async def _slow_background(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            await gate.wait()
            return {"result": "first task done"}
        return {"result": "second task done", "session_id": "cc_sess_2"}

    monkeypatch.setattr(tool, "_execute_background", _slow_background)

    result1 = await tool.execute(
        prompt="First: refactor utils.py",
        project_path=str(tmp_path),
    )
    assert "task started" in result1.lower()
    task1_id = result1.split("id: ")[1].split(")")[0].rstrip(".")

    active = store.list_active_by_session("console:session-1")
    assert len(active) == 1, f"Expected 1 active task, got {len(active)}"

    result2 = await tool.execute(
        prompt="Second: fix the test",
        project_path=str(tmp_path),
    )
    assert "replaced" in result2.lower(), f"Expected replace mention, got: {result2}"

    gate.set()
    await asyncio.sleep(0.2)

    status1 = store.get_status(task_id=task1_id)
    if status1["tasks"]:
        assert status1["tasks"][0]["status"] in ("cancelled", "failed")


# ---------------------------------------------------------------------------
# Flow 3: Nested path resolution in real git repo
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_nested_path_resolution_flow(tmp_path: Path, monkeypatch):
    """Simulate: user passes a nested subdir path -> resolve_target finds
    correct repo root -> workspace_key reflects the nesting."""
    import subprocess

    subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True, check=True)
    nested = tmp_path / "packages" / "core" / "src"
    nested.mkdir(parents=True)
    (nested / "index.ts").write_text("export const x = 1;")

    monkeypatch.setattr("ava.tools.codex.shutil.which", lambda name: "/usr/bin/codex")

    db = Database(tmp_path / "flow3.sqlite3")
    store = BackgroundTaskStore(db=db)
    loop = _FakeLoop()
    store.set_agent_loop(loop)

    tool = CodexTool(workspace=tmp_path, task_store=store)

    async def _fake_bg(**kwargs):
        return {"result": "ok", "thread_id": "t1"}
    monkeypatch.setattr(tool, "_run_background", _fake_bg)

    result = await tool.execute(
        prompt="Lint packages/core/src",
        project_path=str(nested),
    )

    task_id = result.split("id: ")[1].split(")")[0].rstrip(".")
    await asyncio.sleep(0.1)

    status = store.get_status(task_id=task_id)
    task = status["tasks"][0]

    assert task["repo_root"] == str(tmp_path)
    assert task["workdir_relpath"] == "packages/core/src"
    assert "packages/core/src" in task["workspace_key"]
    assert task["execution_cwd"] == str(nested)


# ---------------------------------------------------------------------------
# Flow 4: Parallel workspace isolation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_parallel_workspace_isolation(tmp_path: Path):
    """Two tasks with different explicit workspace_ids should both stay active."""
    db = Database(tmp_path / "flow4.sqlite3")
    store = BackgroundTaskStore(db=db)
    loop = _FakeLoop()
    store.set_agent_loop(loop)

    target = ProjectTarget(
        repo_root=str(tmp_path),
        workdir_relpath=".",
        requested_path=str(tmp_path),
        workspace_key=f"{tmp_path}:.",
    )
    ws_a = make_inplace_workspace(target, workspace_id="ws-branch-A")
    ws_b = make_inplace_workspace(target, workspace_id="ws-branch-B")

    async def _slow(**_kw):
        await asyncio.sleep(30)
        return {"result": "done"}

    submit_a = store.submit_coding_task(
        executor=_slow,
        origin_session_key="test:parallel",
        prompt="Work on branch A",
        timeout=60,
        target=target,
        workspace=ws_a,
    )
    submit_b = store.submit_coding_task(
        executor=_slow,
        origin_session_key="test:parallel",
        prompt="Work on branch B",
        timeout=60,
        target=target,
        workspace=ws_b,
    )

    assert submit_a.workspace_id == "ws-branch-A"
    assert submit_b.workspace_id == "ws-branch-B"
    assert submit_b.replaced_task_id is None, "Different workspace should NOT replace"

    active = store.list_active_by_session("test:parallel")
    assert len(active) == 2

    by_ws_a = store.find_active_by_workspace("ws-branch-A")
    by_ws_b = store.find_active_by_workspace("ws-branch-B")
    assert len(by_ws_a) == 1
    assert len(by_ws_b) == 1

    by_target = store.find_active_by_target(f"{tmp_path}:.")
    assert len(by_target) == 2

    for tid in [submit_a.task_id, submit_b.task_id]:
        t = store._tasks.get(tid)
        if t and not t.done():
            t.cancel()
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass


# ---------------------------------------------------------------------------
# Flow 5: API routes with workspace query
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bg_task_routes_workspace_query(tmp_path: Path):
    """Verify the REST API route logic for workspace-based filtering."""
    db = Database(tmp_path / "flow5.sqlite3")
    store = BackgroundTaskStore(db=db)
    loop = _FakeLoop()
    store.set_agent_loop(loop)

    target = ProjectTarget(
        repo_root=str(tmp_path),
        workdir_relpath=".",
        requested_path=str(tmp_path),
        workspace_key=f"{tmp_path}:.",
    )
    ws = make_inplace_workspace(target, workspace_id="ws-route-test")

    async def _fast(**_kw):
        return {"result": "ok"}

    submit = store.submit_coding_task(
        executor=_fast,
        origin_session_key="test:route",
        prompt="Route test",
        timeout=5,
        target=target,
        workspace=ws,
    )

    by_ws = store.find_active_by_workspace("ws-route-test")
    assert len(by_ws) == 1
    task_dict = by_ws[0].to_dict()
    assert task_dict["workspace_id"] == "ws-route-test"
    assert task_dict["isolation_mode"] == "inplace"

    by_wrong = store.find_active_by_workspace("ws-nonexistent")
    assert len(by_wrong) == 0

    await store._tasks[submit.task_id]

    detail = store.get_task_detail(submit.task_id)
    assert detail is not None
    extra_row = db.fetchone("SELECT extra FROM bg_tasks WHERE task_id = ?", (submit.task_id,))
    extra = json.loads(extra_row["extra"])
    assert extra["workspace_id"] == "ws-route-test"
