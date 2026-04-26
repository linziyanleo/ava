"""统一后台任务上下文层。

采用"写多读一"模式：各事件源（coding/cron/subagent）向 store 写入事件，
store 统一提供查询、digest、timeline 接口。

Phase 1 只实装 coding 事件源，但读接口从第一天起就是通用的。
"""

from __future__ import annotations

import asyncio
import re
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Literal

from loguru import logger

if TYPE_CHECKING:
    from nanobot.agent.loop import AgentLoop
    from ava.agent.worktree_manager import ExecutionWorkspace, ProjectTarget

TaskStatus = Literal["queued", "running", "succeeded", "failed", "cancelled", "interrupted"]

_MAX_CONTINUATION_BUDGET = 5
_FINISHED_RETENTION_MAX_ITEMS = 20
_FINISHED_RETENTION_MAX_AGE_S = 30 * 60
_BG_TASK_ASSISTANT_RE = re.compile(r"^\[Background Task ([A-Za-z0-9_-]+) [A-Z_]+\]\n")


@dataclass
class TimelineEvent:
    timestamp: float
    event: str
    detail: str = ""


@dataclass
class TaskSnapshot:
    task_id: str
    task_type: str
    origin_session_key: str
    status: TaskStatus
    prompt_preview: str
    started_at: float | None = None
    finished_at: float | None = None
    elapsed_ms: int = 0
    result_preview: str = ""
    error_message: str = ""
    timeline: list[TimelineEvent] = field(default_factory=list)
    phase: str = "executing"
    last_tool_name: str = ""
    todo_summary: dict[str, int] | None = None
    project_path: str = ""
    cli_run_id: str = ""
    cli_session_id: str = ""
    auto_continue: bool = False
    # workspace-aware fields (Phase 1)
    repo_root: str = ""
    workdir_relpath: str = ""
    workspace_key: str = ""
    workspace_id: str = ""
    execution_cwd: str = ""
    isolation_mode: str = "inplace"
    branch_name: str = ""
    worktree_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["timeline"] = [asdict(e) for e in self.timeline]
        return d


@dataclass
class SubmitResult:
    """Returned by submit_coding_task to give callers workspace-aware context."""
    task_id: str
    reused: bool
    replaced_task_id: str | None
    workspace_id: str
    active_in_session: list[str]


CodingExecutor = Callable[..., Awaitable[dict[str, Any]]]


class BackgroundTaskStore:
    """统一后台任务注册/状态机/timeline/持久化/digest。"""

    def __init__(self, db: Any | None = None) -> None:
        self._db = db
        self._active: dict[str, TaskSnapshot] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._finished: dict[str, TaskSnapshot] = {}
        self._agent_loop: AgentLoop | None = None
        self._continuation_budgets: dict[str, int] = {}
        self._last_rebuild_result: Any | None = None
        self._ensure_tables()

    def set_agent_loop(self, loop: AgentLoop) -> None:
        self._agent_loop = loop

    @staticmethod
    def _session_has_bg_completion(messages: list[dict[str, Any]], task_id: str) -> bool:
        for message in messages:
            if not isinstance(message, dict):
                continue
            if message.get("role") != "assistant":
                continue
            content = message.get("content")
            if not isinstance(content, str):
                continue
            match = _BG_TASK_ASSISTANT_RE.match(content)
            if match and match.group(1) == task_id:
                return True
        return False

    def _ensure_tables(self) -> None:
        if not self._db:
            return
        try:
            self._db.execute("""
                CREATE TABLE IF NOT EXISTS bg_tasks (
                    task_id TEXT PRIMARY KEY,
                    task_type TEXT NOT NULL,
                    origin_session_key TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'queued',
                    prompt_preview TEXT,
                    project_path TEXT,
                    started_at REAL,
                    finished_at REAL,
                    result_preview TEXT,
                    error_message TEXT,
                    extra TEXT
                )
            """)
            self._db.execute("""
                CREATE TABLE IF NOT EXISTS bg_task_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    event TEXT NOT NULL,
                    detail TEXT,
                    timestamp REAL NOT NULL
                )
            """)
            self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_bg_tasks_session "
                "ON bg_tasks(origin_session_key)"
            )
            self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_bg_task_events_task "
                "ON bg_task_events(task_id)"
            )
            self._db.commit()
        except Exception as exc:
            logger.warning("BackgroundTaskStore: failed to create tables: {}", exc)

    # ------------------------------------------------------------------
    # 写入接口
    # ------------------------------------------------------------------

    def submit_coding_task(
        self,
        executor: CodingExecutor,
        *,
        origin_session_key: str,
        prompt: str,
        project_path: str = "",
        timeout: int,
        auto_continue: bool = False,
        task_type: str = "coding",
        target: ProjectTarget | None = None,
        workspace: ExecutionWorkspace | None = None,
        replace_task_id: str | None = None,
        workspace_exclusive: bool = True,
        **executor_kwargs: Any,
    ) -> SubmitResult:
        ws_id = workspace.workspace_id if workspace else ""
        ws_key = workspace.workspace_key if workspace else ""

        if replace_task_id:
            self._sync_cancel_and_wait(replace_task_id)
        elif workspace_exclusive and ws_id:
            existing = self.find_active_by_workspace(ws_id)
            if existing:
                replaced = existing[0]
                replace_task_id = replaced.task_id
                self._sync_cancel_and_wait(replaced.task_id)

        task_id = uuid.uuid4().hex[:12]
        now = time.time()

        effective_project_path = project_path
        if workspace:
            effective_project_path = workspace.execution_cwd or project_path

        snapshot = TaskSnapshot(
            task_id=task_id,
            task_type=task_type,
            origin_session_key=origin_session_key,
            status="queued",
            prompt_preview=prompt[:200],
            project_path=effective_project_path,
            started_at=now,
            timeline=[TimelineEvent(timestamp=now, event="submitted", detail=prompt[:100])],
            auto_continue=auto_continue,
            repo_root=target.repo_root if target else "",
            workdir_relpath=target.workdir_relpath if target else "",
            workspace_key=ws_key,
            workspace_id=ws_id,
            execution_cwd=workspace.execution_cwd if workspace else effective_project_path,
            isolation_mode=workspace.isolation_mode if workspace else "inplace",
            branch_name=workspace.branch_name or "" if workspace else "",
            worktree_path=workspace.worktree_path or "" if workspace else "",
        )
        self._active[task_id] = snapshot
        self._persist_task(snapshot, full_prompt=prompt)
        self._persist_event(task_id, "submitted", prompt[:100])

        active_ids = [
            s.task_id for s in self._active.values()
            if s.origin_session_key == origin_session_key
            and s.task_id != task_id
        ]

        async def _run() -> None:
            snapshot.status = "running"
            snapshot.started_at = time.time()
            self._record_event(task_id, "started")
            self._update_task_status(task_id, "running")
            try:
                result = await asyncio.wait_for(
                    executor(prompt=prompt, **executor_kwargs),
                    timeout=timeout,
                )
                snapshot.status = "succeeded"
                snapshot.finished_at = time.time()
                snapshot.elapsed_ms = int((snapshot.finished_at - snapshot.started_at) * 1000)
                full_result_str = self._stringify_result_value(result.get("result"))
                snapshot.result_preview = full_result_str
                snapshot.cli_run_id, snapshot.cli_session_id = self._resolve_cli_ids(result)
                self._record_event(task_id, "succeeded", snapshot.result_preview[:100])
                self._update_task_status(
                    task_id, "succeeded", snapshot, full_result=full_result_str,
                )
                await self._on_complete(snapshot, result)
            except asyncio.TimeoutError:
                snapshot.status = "failed"
                snapshot.finished_at = time.time()
                snapshot.elapsed_ms = int((snapshot.finished_at - snapshot.started_at) * 1000)
                snapshot.error_message = f"Timed out after {timeout}s"
                self._record_event(task_id, "failed", snapshot.error_message)
                self._update_task_status(task_id, "failed", snapshot)
                await self._on_complete(snapshot, None)
            except asyncio.CancelledError:
                snapshot.status = "cancelled"
                snapshot.finished_at = time.time()
                snapshot.elapsed_ms = int((snapshot.finished_at - (snapshot.started_at or snapshot.finished_at)) * 1000)
                snapshot.error_message = "Cancelled by user"
                self._record_event(task_id, "cancelled")
                self._update_task_status(task_id, "cancelled", snapshot)
                await self._on_complete(snapshot, None)
            except Exception as exc:
                snapshot.status = "failed"
                snapshot.finished_at = time.time()
                snapshot.elapsed_ms = int((snapshot.finished_at - snapshot.started_at) * 1000)
                snapshot.error_message = str(exc)[:500]
                self._record_event(task_id, "failed", snapshot.error_message[:100])
                self._update_task_status(task_id, "failed", snapshot)
                await self._on_complete(snapshot, None)
            finally:
                self._finished[task_id] = self._active.pop(task_id, snapshot)
                self._tasks.pop(task_id, None)
                self._prune_finished()

        task = asyncio.create_task(_run())
        self._tasks[task_id] = task
        return SubmitResult(
            task_id=task_id,
            reused=False,
            replaced_task_id=replace_task_id,
            workspace_id=ws_id,
            active_in_session=active_ids,
        )

    def record_event(
        self, task_id: str, event: str, detail: str = "",
    ) -> None:
        """通用事件记录接口（供 cron/subagent observer 使用）。"""
        self._record_event(task_id, event, detail)

    def _record_event(self, task_id: str, event: str, detail: str = "") -> None:
        now = time.time()
        if task_id in self._active:
            self._active[task_id].timeline.append(
                TimelineEvent(timestamp=now, event=event, detail=detail)
            )
        self._persist_event(task_id, event, detail)

    # ------------------------------------------------------------------
    # Workspace-aware query
    # ------------------------------------------------------------------

    def find_active_by_workspace(self, workspace_id: str) -> list[TaskSnapshot]:
        return [
            s for s in self._active.values()
            if s.workspace_id == workspace_id and s.status in ("queued", "running")
        ]

    def find_active_by_target(self, workspace_key: str) -> list[TaskSnapshot]:
        return [
            s for s in self._active.values()
            if s.workspace_key == workspace_key and s.status in ("queued", "running")
        ]

    def list_active_by_session(self, session_key: str) -> list[TaskSnapshot]:
        return [
            s for s in self._active.values()
            if s.origin_session_key == session_key and s.status in ("queued", "running")
        ]

    def _sync_cancel_and_wait(self, task_id: str) -> None:
        """Cancel a task for replace. Also handles the edge case where _run
        hasn't started yet (task cancelled before first await)."""
        if task_id not in self._tasks:
            return
        atask = self._tasks[task_id]
        if atask.done():
            return
        atask.cancel()
        logger.info("BackgroundTaskStore: cancelled task {} for replace", task_id)

        snapshot = self._active.get(task_id)
        if snapshot and snapshot.status == "queued":
            snapshot.status = "cancelled"
            snapshot.finished_at = time.time()
            snapshot.error_message = "Replaced by new task"
            self._record_event(task_id, "cancelled", "Replaced by new task")
            self._update_task_status(task_id, "cancelled", snapshot)
            self._finished[task_id] = self._active.pop(task_id)
            self._tasks.pop(task_id, None)

    # ------------------------------------------------------------------
    # 读取接口
    # ------------------------------------------------------------------

    async def cancel(self, task_id: str) -> str:
        if task_id in self._tasks:
            task = self._tasks[task_id]
            if not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
                return f"Task {task_id} cancelled."
            return f"Task {task_id} already finished."
        if task_id in self._finished:
            return f"Task {task_id} already finished."
        return f"Task {task_id} not found."

    async def cancel_by_session(self, session_key: str) -> int:
        cancelled = 0
        task_ids = [
            tid for tid, snap in self._active.items()
            if snap.origin_session_key == session_key
        ]
        for tid in task_ids:
            result = await self.cancel(tid)
            if "cancelled" in result.lower():
                cancelled += 1
        return cancelled

    def get_status(
        self,
        task_id: str | None = None,
        session_key: str | None = None,
        task_type: str | None = None,
        include_finished: bool = True,
        verbose: bool = False,
    ) -> dict[str, Any]:
        self._prune_finished()
        tasks: list[TaskSnapshot] = []

        if task_id:
            snap = self._active.get(task_id) or self._finished.get(task_id)
            if snap:
                tasks.append(snap)
            else:
                db_snapshot = self._load_snapshot_from_db(task_id)
                if db_snapshot:
                    tasks.append(db_snapshot)
        else:
            tasks.extend(self._active.values())
            if include_finished:
                tasks.extend(self._finished.values())

        if session_key:
            tasks = [t for t in tasks if t.origin_session_key == session_key]
        if task_type:
            tasks = [t for t in tasks if t.task_type == task_type]

        tasks.sort(key=lambda t: t.started_at or 0, reverse=True)
        running = sum(1 for t in tasks if t.status in ("queued", "running"))

        return {
            "running": running,
            "total": len(tasks),
            "tasks": [t.to_dict() for t in tasks],
        }

    def get_active_digest(self, session_key: str | None = None) -> str:
        """返回适合注入 system prompt 的极短任务摘要。无活跃任务时返回空字符串。"""
        self._prune_finished()
        tasks = list(self._active.values())
        recent_finished = [
            s for s in self._finished.values()
            if s.finished_at and (time.time() - s.finished_at) < 300
        ]
        all_relevant = tasks + recent_finished

        if session_key:
            all_relevant = [t for t in all_relevant if t.origin_session_key == session_key]

        if not all_relevant:
            return ""

        lines = ["## Active Background Tasks"]
        for t in sorted(all_relevant, key=lambda x: x.started_at or 0, reverse=True)[:5]:
            if t.status in ("queued", "running"):
                elapsed = int(time.time() - (t.started_at or time.time()))
                lines.append(
                    f"- [{t.task_type}:{t.task_id}] {t.status} {elapsed}s "
                    f"— \"{t.prompt_preview}\""
                )
            else:
                ago = int(time.time() - (t.finished_at or time.time()))
                lines.append(
                    f"- [{t.task_type}:{t.task_id}] {t.status} {ago}s ago "
                    f"— \"{t.prompt_preview}\""
                )
        return "\n".join(lines)

    def get_timeline(self, task_id: str) -> list[TimelineEvent]:
        snap = self._active.get(task_id) or self._finished.get(task_id)
        if snap:
            return list(snap.timeline)
        return self._load_timeline_from_db(task_id)

    def list_tasks(self, *, include_finished: bool = False) -> list[TaskSnapshot]:
        self._prune_finished()
        tasks = list(self._active.values())
        if include_finished:
            tasks.extend(self._finished.values())
        return tasks

    @staticmethod
    def _stringify_result_value(value: Any) -> str:
        if value is None:
            return ""
        return value if isinstance(value, str) else str(value)

    @classmethod
    def _resolve_cli_ids(cls, result: dict[str, Any] | None) -> tuple[str, str]:
        if not result:
            return "", ""

        session_id = cls._stringify_result_value(result.get("session_id")).strip()
        run_id = cls._stringify_result_value(result.get("run_id")).strip()
        thread_id = cls._stringify_result_value(result.get("thread_id")).strip()

        cli_run_id = run_id or session_id or thread_id
        cli_session_id = session_id or cli_run_id
        return cli_run_id, cli_session_id

    def _resolve_result_text(
        self,
        snapshot: TaskSnapshot,
        result: dict[str, Any] | None = None,
    ) -> str:
        """优先返回完整结果，preview 仅作为兜底。"""
        if result:
            result_text = self._stringify_result_value(result.get("result"))
            error_text = self._stringify_result_value(result.get("error_message"))
            if result_text and error_text and error_text not in result_text:
                return f"{result_text}\n\nError: {error_text}"
            if result_text:
                return result_text
            if error_text:
                return error_text
        return snapshot.error_message or snapshot.result_preview or "(no output)"

    # ------------------------------------------------------------------
    # 完成回调
    # ------------------------------------------------------------------

    async def _on_complete(
        self, snapshot: TaskSnapshot, result: dict[str, Any] | None,
    ) -> None:
        loop = self._agent_loop
        if not loop:
            logger.warning("BackgroundTaskStore: no agent_loop ref, skipping completion callback")
            return

        status_label = "SUCCESS" if snapshot.status == "succeeded" else "ERROR"
        result_text = self._resolve_result_text(snapshot, result)
        formatted = (
            f"[Background Task {snapshot.task_id} {status_label}]\n"
            f"Type: {snapshot.task_type} | Duration: {snapshot.elapsed_ms}ms\n\n"
            f"{result_text}"
        )

        try:
            session = loop.sessions.get_or_create(snapshot.origin_session_key)
            if self._session_has_bg_completion(session.messages, snapshot.task_id):
                logger.info(
                    "BackgroundTaskStore: duplicate completion ignored for session {} task {}",
                    snapshot.origin_session_key, snapshot.task_id,
                )
                return
            session.messages.append({
                "role": "assistant",
                "content": formatted,
                "timestamp": datetime.now().isoformat(),
                "tools_used": [f"bg_task:{snapshot.task_type}"],
            })
            loop.sessions.save(session)
            logger.info(
                "BackgroundTaskStore: result persisted to session {} for task {}",
                snapshot.origin_session_key, snapshot.task_id,
            )
        except Exception as exc:
            logger.error("BackgroundTaskStore: failed to persist result: {}", exc)

        try:
            bus = getattr(loop, "bus", None)
            if bus and hasattr(bus, "publish_outbound"):
                from nanobot.bus.events import OutboundMessage
                parts = snapshot.origin_session_key.split(":", 1)
                channel = parts[0] if parts else "cli"
                chat_id = parts[1] if len(parts) > 1 else "direct"
                result_or_coro = bus.publish_outbound(OutboundMessage(
                    channel=channel,
                    chat_id=chat_id,
                    content=formatted,
                ))
                if asyncio.iscoroutine(result_or_coro):
                    await result_or_coro
        except Exception as exc:
            logger.warning("BackgroundTaskStore: failed to publish outbound: {}", exc)

        rebuild_info = await self._run_post_task_hooks(snapshot)

        if snapshot.auto_continue or snapshot.status == "failed":
            await self._trigger_continuation(snapshot, rebuild_info, result=result)

    # ------------------------------------------------------------------
    # Post-task hooks + Continuation
    # ------------------------------------------------------------------

    async def _run_post_task_hooks(self, snapshot: TaskSnapshot) -> str:
        """Post-task 钩子：检测前端变更 → 自动 rebuild。返回 hook 结果描述。"""
        parts: list[str] = []
        if snapshot.task_type == "coding" and snapshot.status == "succeeded":
            rebuild_info = await self._maybe_rebuild_frontend(snapshot)
            if rebuild_info:
                parts.append(rebuild_info)
        return "\n".join(parts)

    async def _maybe_rebuild_frontend(self, snapshot: TaskSnapshot) -> str | None:
        """检测产物新鲜度 → 自动 rebuild。复用 needs_console_ui_build()。"""
        from pathlib import Path
        project = snapshot.project_path
        if not project:
            return None

        console_ui_dir = Path(project) / "console-ui"
        if not console_ui_dir.exists():
            return None

        try:
            from ava.console.ui_build import needs_console_ui_build, rebuild_console_ui
            if not needs_console_ui_build(console_ui_dir):
                return None
            logger.info("Post-task hook: console-ui dist is stale, auto-rebuilding...")
            result = await rebuild_console_ui(console_ui_dir)
            self._last_rebuild_result = result
            if result.success:
                info = f"[Auto Rebuild] Frontend rebuilt: hash={result.version_hash[:12]}, {result.duration_ms}ms"
                logger.info(info)
                return info
            else:
                info = f"[Auto Rebuild] Frontend rebuild failed: {result.error}"
                logger.warning(info)
                return info
        except Exception as exc:
            logger.warning("Post-task frontend rebuild error: {}", exc)
            return f"[Auto Rebuild] Error: {exc}"

    async def _trigger_continuation(
        self,
        snapshot: TaskSnapshot,
        rebuild_info: str = "",
        result: dict[str, Any] | None = None,
    ) -> None:
        """参考 cron 的 process_direct，在 origin session 中触发 agent loop 继续。"""
        if snapshot.status not in ("succeeded", "failed"):
            return

        loop = self._agent_loop
        if not loop:
            return

        key = snapshot.origin_session_key
        budget = self._continuation_budgets.get(key, _MAX_CONTINUATION_BUDGET)
        if budget <= 0:
            logger.warning(
                "Continuation budget exhausted for session {}, skipping", key,
            )
            return

        self._continuation_budgets[key] = budget - 1

        parts = key.split(":", 1)
        channel = parts[0] if parts else "cli"
        chat_id = parts[1] if len(parts) > 1 else "direct"

        content = self._build_continuation_message(snapshot, rebuild_info, result=result)
        try:
            resp = await loop.process_direct(
                content,
                session_key=key,
                channel=channel,
                chat_id=chat_id,
            )
            if resp and resp.content:
                bus = getattr(loop, "bus", None)
                if bus and hasattr(bus, "publish_outbound"):
                    result_or_coro = bus.publish_outbound(resp)
                    if asyncio.iscoroutine(result_or_coro):
                        await result_or_coro
        except Exception as exc:
            logger.error("Continuation failed for session {}: {}", key, exc)

    def _build_continuation_message(
        self,
        snapshot: TaskSnapshot,
        rebuild_info: str = "",
        result: dict[str, Any] | None = None,
    ) -> str:
        status = "SUCCESS" if snapshot.status == "succeeded" else "ERROR"
        result_text = self._resolve_result_text(snapshot, result)
        parts = [
            f"[Background Task Completed — {status}]",
            f"Task: {snapshot.task_type}:{snapshot.task_id}",
            f"Duration: {snapshot.elapsed_ms}ms",
            "",
            result_text,
        ]
        if rebuild_info:
            parts.extend(["", rebuild_info])
        parts.extend(["", "请基于以上结果继续处理后续步骤。如果所有工作已完成，请总结。"])
        return "\n".join(parts)

    def reset_continuation_budget(self, session_key: str) -> None:
        """用户发送新消息时重置 budget（由 loop_patch 调用）。"""
        self._continuation_budgets.pop(session_key, None)

    # ------------------------------------------------------------------
    # Lifecycle 集成
    # ------------------------------------------------------------------

    def recover_orphan_tasks(self, boot_generation: int = 0) -> int:
        """将上一代 running/queued 的任务标记为 interrupted（进程重启导致）。"""
        if not self._db:
            return 0
        try:
            rows = self._db.fetchall(
                "SELECT task_id FROM bg_tasks WHERE status IN ('running', 'queued')"
            )
            if not rows:
                return 0
            now = time.time()
            msg = f"Interrupted by gateway restart (gen {boot_generation})"
            for r in rows:
                tid = r["task_id"]
                self._db.execute(
                    "UPDATE bg_tasks SET status='interrupted', finished_at=?, error_message=? WHERE task_id=?",
                    (now, msg, tid),
                )
                self._persist_event(tid, "interrupted", msg)
            self._db.commit()
            count = len(rows)
            logger.info("BackgroundTaskStore: recovered {} orphan tasks as interrupted", count)
            return count
        except Exception as exc:
            logger.warning("BackgroundTaskStore: recover_orphan_tasks failed: {}", exc)
            return 0

    # ------------------------------------------------------------------
    # SQLite 持久层
    # ------------------------------------------------------------------

    def _persist_task(
        self, snapshot: TaskSnapshot, *, full_prompt: str = "", full_result: str = "",
    ) -> None:
        if not self._db:
            return
        try:
            import json
            extra: dict[str, Any] = {
                "cli_run_id": snapshot.cli_run_id,
                "cli_session_id": snapshot.cli_session_id,
                "repo_root": snapshot.repo_root,
                "workdir_relpath": snapshot.workdir_relpath,
                "workspace_key": snapshot.workspace_key,
                "workspace_id": snapshot.workspace_id,
                "execution_cwd": snapshot.execution_cwd,
                "isolation_mode": snapshot.isolation_mode,
                "branch_name": snapshot.branch_name,
                "worktree_path": snapshot.worktree_path,
            }
            if full_prompt:
                extra["full_prompt"] = full_prompt
            if full_result:
                extra["full_result"] = full_result
            self._db.execute(
                """INSERT OR REPLACE INTO bg_tasks
                   (task_id, task_type, origin_session_key, status,
                    prompt_preview, project_path, started_at, finished_at,
                    result_preview, error_message, extra)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    snapshot.task_id, snapshot.task_type,
                    snapshot.origin_session_key, snapshot.status,
                    snapshot.prompt_preview, snapshot.project_path,
                    snapshot.started_at, snapshot.finished_at,
                    snapshot.result_preview, snapshot.error_message,
                    json.dumps(extra),
                ),
            )
            self._db.commit()
        except Exception as exc:
            logger.warning("BackgroundTaskStore: persist_task failed: {}", exc)

    def _update_task_status(
        self, task_id: str, status: str, snapshot: TaskSnapshot | None = None,
        *, full_result: str = "",
    ) -> None:
        if not self._db:
            return
        try:
            if snapshot:
                import json as _json
                # 读取现有 extra，合并 full_result
                row = self._db.fetchone(
                    "SELECT extra FROM bg_tasks WHERE task_id=?", (task_id,),
                )
                extra: dict[str, Any] = {}
                if row:
                    try:
                        extra = _json.loads(row["extra"] or "{}")
                    except Exception:
                        pass
                extra["cli_run_id"] = snapshot.cli_run_id
                extra["cli_session_id"] = snapshot.cli_session_id
                extra["workspace_id"] = snapshot.workspace_id
                extra["workspace_key"] = snapshot.workspace_key
                extra["execution_cwd"] = snapshot.execution_cwd
                extra["isolation_mode"] = snapshot.isolation_mode
                extra["branch_name"] = snapshot.branch_name
                extra["worktree_path"] = snapshot.worktree_path
                if full_result:
                    extra["full_result"] = full_result
                self._db.execute(
                    """UPDATE bg_tasks SET status=?, finished_at=?,
                       result_preview=?, error_message=?, extra=? WHERE task_id=?""",
                    (status, snapshot.finished_at, snapshot.result_preview,
                     snapshot.error_message, _json.dumps(extra), task_id),
                )
            else:
                self._db.execute(
                    "UPDATE bg_tasks SET status=? WHERE task_id=?",
                    (status, task_id),
                )
            self._db.commit()
        except Exception as exc:
            logger.warning("BackgroundTaskStore: update_task_status failed: {}", exc)

    def _persist_event(self, task_id: str, event: str, detail: str = "") -> None:
        if not self._db:
            return
        try:
            self._db.execute(
                "INSERT INTO bg_task_events (task_id, event, detail, timestamp) VALUES (?, ?, ?, ?)",
                (task_id, event, detail, time.time()),
            )
            self._db.commit()
        except Exception as exc:
            logger.warning("BackgroundTaskStore: persist_event failed: {}", exc)

    @staticmethod
    def _row_val(row: Any, key: str, default: Any = "") -> Any:
        """sqlite3.Row 没有 .get()，用 try/except 安全取值。"""
        try:
            val = row[key]
            return val if val is not None else default
        except (KeyError, IndexError):
            return default

    def _prune_finished(self) -> None:
        if not self._finished:
            return

        now = time.time()
        retained: dict[str, TaskSnapshot] = {}
        for idx, (task_id, snapshot) in enumerate(
            sorted(
                self._finished.items(),
                key=lambda item: item[1].finished_at or 0,
                reverse=True,
            )
        ):
            finished_at = snapshot.finished_at
            if idx >= _FINISHED_RETENTION_MAX_ITEMS:
                continue
            if finished_at and (now - finished_at) > _FINISHED_RETENTION_MAX_AGE_S:
                continue
            retained[task_id] = snapshot
        self._finished = retained

    def _load_snapshot_from_db(self, task_id: str) -> TaskSnapshot | None:
        if not self._db:
            return None
        try:
            row = self._db.fetchone(
                """SELECT task_id, task_type, origin_session_key, status,
                          prompt_preview, project_path, started_at, finished_at,
                          result_preview, error_message, extra
                   FROM bg_tasks
                   WHERE task_id=?""",
                (task_id,),
            )
            if not row:
                return None
            return self._snapshot_from_db_row(row)
        except Exception as exc:
            logger.warning("BackgroundTaskStore: load snapshot failed: {}", exc)
            return None

    def _snapshot_from_db_row(self, row: Any) -> TaskSnapshot:
        started = self._row_val(row, "started_at", None)
        finished = self._row_val(row, "finished_at", None)
        elapsed = int((finished - started) * 1000) if started and finished else 0
        extra = self._load_extra_json(self._row_val(row, "extra", "{}"))
        return TaskSnapshot(
            task_id=row["task_id"],
            task_type=row["task_type"],
            origin_session_key=row["origin_session_key"],
            status=row["status"],
            prompt_preview=self._row_val(row, "prompt_preview"),
            started_at=started,
            finished_at=finished,
            elapsed_ms=elapsed,
            result_preview=self._row_val(row, "result_preview"),
            error_message=self._row_val(row, "error_message"),
            project_path=self._row_val(row, "project_path"),
            cli_run_id=extra.get("cli_run_id", "") or extra.get("cli_session_id", ""),
            cli_session_id=extra.get("cli_session_id", "") or extra.get("cli_run_id", ""),
            repo_root=extra.get("repo_root", ""),
            workdir_relpath=extra.get("workdir_relpath", ""),
            workspace_key=extra.get("workspace_key", ""),
            workspace_id=extra.get("workspace_id", ""),
            execution_cwd=extra.get("execution_cwd", ""),
            isolation_mode=extra.get("isolation_mode", "inplace"),
            branch_name=extra.get("branch_name", ""),
            worktree_path=extra.get("worktree_path", ""),
        )

    @staticmethod
    def _load_extra_json(raw: str) -> dict[str, Any]:
        import json as _json

        try:
            return _json.loads(raw or "{}")
        except Exception:
            return {}

    def query_history(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        session_key: str | None = None,
    ) -> dict[str, Any]:
        """从 DB 查询历史任务（已完成），分页返回。"""
        if not self._db:
            return {"tasks": [], "total": 0, "page": page, "page_size": page_size}
        try:
            where = "WHERE status IN ('succeeded','failed','cancelled','interrupted')"
            params: list[Any] = []
            if session_key:
                where += " AND origin_session_key = ?"
                params.append(session_key)

            count_row = self._db.fetchone(
                f"SELECT COUNT(*) as cnt FROM bg_tasks {where}", tuple(params)
            )
            total = count_row["cnt"] if count_row else 0

            offset = (page - 1) * page_size
            params.extend([page_size, offset])
            rows = self._db.fetchall(
                f"""SELECT task_id, task_type, origin_session_key, status,
                           prompt_preview, project_path, started_at, finished_at,
                           result_preview, error_message, extra
                    FROM bg_tasks {where}
                    ORDER BY started_at DESC
                    LIMIT ? OFFSET ?""",
                tuple(params),
            )
            tasks = [self._snapshot_from_db_row(r).to_dict() for r in rows]
            return {"tasks": tasks, "total": total, "page": page, "page_size": page_size}
        except Exception as exc:
            logger.warning("BackgroundTaskStore: query_history failed: {}", exc)
            return {"tasks": [], "total": 0, "page": page, "page_size": page_size}

    def get_task_detail(self, task_id: str) -> dict[str, Any] | None:
        """获取单个任务的完整 prompt 和 result（从 extra JSON 中读取）。"""
        # 先查内存中的活跃任务
        snap = self._active.get(task_id) or self._finished.get(task_id)
        if not self._db:
            if snap:
                return {"task_id": task_id, "full_prompt": "", "full_result": ""}
            return None
        try:
            row = self._db.fetchone(
                "SELECT extra FROM bg_tasks WHERE task_id=?", (task_id,),
            )
            if not row:
                return None
            import json as _json
            extra = {}
            try:
                extra = _json.loads(row["extra"] or "{}")
            except Exception:
                pass
            return {
                "task_id": task_id,
                "full_prompt": extra.get("full_prompt", ""),
                "full_result": extra.get("full_result", ""),
            }
        except Exception as exc:
            logger.warning("BackgroundTaskStore: get_task_detail failed: {}", exc)
            return None

    def _load_timeline_from_db(self, task_id: str) -> list[TimelineEvent]:
        if not self._db:
            return []
        try:
            rows = self._db.fetchall(
                "SELECT event, detail, timestamp FROM bg_task_events WHERE task_id=? ORDER BY timestamp",
                (task_id,),
            )
            rv = self._row_val
            return [
                TimelineEvent(timestamp=r["timestamp"], event=r["event"], detail=rv(r, "detail"))
                for r in rows
            ]
        except Exception:
            return []
