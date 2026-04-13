"""Supervisor-first 进程生命周期管理器。

职责：
  - 启动时写入 runtime state（PID、boot generation、supervisor 检测）
  - 接收 restart request（含 task_id / origin_session_key / reason）
  - 协调优雅退出（分层 drain → interrupted 标记 → 退出）
  - 新进程启动时检查 pending restart、orphan task recovery
"""

from __future__ import annotations

import json
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any

from loguru import logger


_DEFAULT_RUNTIME_DIR = Path.home() / ".nanobot" / "runtime"


class LifecycleManager:
    """进程生命周期管理器。"""

    def __init__(
        self,
        runtime_dir: Path | None = None,
        bg_store: Any | None = None,
        gateway_port: int = 18790,
        console_port: int = 6688,
    ) -> None:
        self.runtime_dir = (runtime_dir or _DEFAULT_RUNTIME_DIR).resolve()
        self._bg_store = bg_store
        self._gateway_port = gateway_port
        self._console_port = console_port

        self.boot_generation: int = 0
        self.boot_time: float = 0.0
        self.supervised: bool = False
        self.supervisor: str = "none"
        self.pid: int = os.getpid()
        self.last_exit_reason: str | None = None
        self._restart_request: dict[str, Any] | None = None
        self._shutting_down: bool = False

    # ------------------------------------------------------------------
    # 初始化
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """启动时调用：写 state / 检测 supervisor / recovery。"""
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.boot_time = time.time()
        self.pid = os.getpid()

        self.supervised, self.supervisor = _detect_supervisor()

        prev_state = self._read_state()
        if prev_state:
            self.boot_generation = prev_state.get("boot_generation", 0) + 1
            self.last_exit_reason = prev_state.get("last_exit_reason")
        else:
            self.boot_generation = 1

        pending = self.check_pending_restart()
        if pending:
            logger.info(
                "LifecycleManager: restart applied (gen {}), requested by {}",
                self.boot_generation, pending.get("requested_by", "?"),
            )
            self._clear_restart_request()

        if self._bg_store:
            recovered = self._bg_store.recover_orphan_tasks(self.boot_generation)
            if recovered:
                logger.info("LifecycleManager: recovered {} orphan bg_tasks", recovered)

        self._write_state()
        logger.info(
            "LifecycleManager initialized: gen={}, supervised={} ({}), pid={}",
            self.boot_generation, self.supervised, self.supervisor, self.pid,
        )

    # ------------------------------------------------------------------
    # 状态查询
    # ------------------------------------------------------------------

    def get_status(self) -> dict[str, Any]:
        """返回完整 lifecycle 状态。"""
        uptime = time.time() - self.boot_time if self.boot_time else None
        return {
            "running": True,
            "pid": self.pid,
            "uptime_seconds": round(uptime, 1) if uptime else None,
            "gateway_port": self._gateway_port,
            "console_port": self._console_port,
            "supervised": self.supervised,
            "supervisor": self.supervisor if self.supervised else None,
            "restart_pending": self._restart_request is not None,
            "boot_generation": self.boot_generation,
            "last_exit_reason": self.last_exit_reason,
        }

    def is_healthy(self) -> dict[str, Any]:
        """Health check：核心服务是否就绪。"""
        return {
            "ready": not self._shutting_down,
            "boot_generation": self.boot_generation,
            "uptime_seconds": round(time.time() - self.boot_time, 1) if self.boot_time else 0,
            "shutting_down": self._shutting_down,
        }

    # ------------------------------------------------------------------
    # Restart 请求
    # ------------------------------------------------------------------

    def request_restart(
        self,
        *,
        requested_by: str,
        task_id: str | None = None,
        origin_session_key: str | None = None,
        reason: str = "",
        force: bool = False,
    ) -> dict[str, Any]:
        """落盘 restart request → 触发优雅退出。"""
        if not self.supervised:
            return {
                "status": "rejected",
                "message": "当前为 unsupervised 模式，不支持自动重启。请手动重启进程。",
            }

        if self._shutting_down:
            return {
                "status": "rejected",
                "message": "进程已在关闭中，请等待 supervisor 重启。",
            }

        self._restart_request = {
            "requested_at": time.time(),
            "requested_by": requested_by,
            "task_id": task_id,
            "origin_session_key": origin_session_key,
            "reason": reason,
            "force": force,
        }
        self._write_restart_request()
        self._write_state(exit_reason=f"restart requested by {requested_by}")

        logger.info(
            "LifecycleManager: restart requested by {} (force={}), reason: {}",
            requested_by, force, reason,
        )

        self._initiate_shutdown(force=force)

        return {
            "status": "accepted",
            "message": "Restart request accepted. Process will exit gracefully.",
            "boot_generation": self.boot_generation,
        }

    # ------------------------------------------------------------------
    # 优雅退出
    # ------------------------------------------------------------------

    def _initiate_shutdown(self, *, force: bool = False) -> None:
        """触发优雅退出流程。"""
        if self._shutting_down:
            return
        self._shutting_down = True

        if self._bg_store:
            active_tasks = self._bg_store.list_tasks(include_finished=False)
            for task in active_tasks:
                if task.status in ("running", "queued"):
                    task.status = "interrupted"
                    task.finished_at = time.time()
                    task.error_message = "Interrupted by gateway restart"
                    self._bg_store._update_task_status(task.task_id, "interrupted", task)
                    self._bg_store._record_event(task.task_id, "interrupted", "gateway restart")
            if active_tasks:
                for tid in [t.task_id for t in active_tasks]:
                    self._bg_store._finished[tid] = self._bg_store._active.pop(tid, active_tasks[0])
                    atask = self._bg_store._tasks.pop(tid, None)
                    if atask and not atask.done():
                        atask.cancel()

        os.kill(self.pid, signal.SIGTERM)

    # ------------------------------------------------------------------
    # Pending restart 检查
    # ------------------------------------------------------------------

    def check_pending_restart(self) -> dict[str, Any] | None:
        """启动时检查是否有未完成的 restart request。"""
        req_file = self.runtime_dir / "restart_request.json"
        if not req_file.exists():
            return None
        try:
            return json.loads(req_file.read_text())
        except Exception:
            return None

    def _clear_restart_request(self) -> None:
        req_file = self.runtime_dir / "restart_request.json"
        try:
            req_file.unlink(missing_ok=True)
        except OSError:
            pass

    # ------------------------------------------------------------------
    # State 持久化
    # ------------------------------------------------------------------

    def _read_state(self) -> dict[str, Any] | None:
        state_file = self.runtime_dir / "state.json"
        if not state_file.exists():
            return None
        try:
            return json.loads(state_file.read_text())
        except Exception:
            return None

    def _write_state(self, exit_reason: str | None = None) -> None:
        state = {
            "pid": self.pid,
            "boot_time": self.boot_time,
            "boot_generation": self.boot_generation,
            "supervised": self.supervised,
            "supervisor": self.supervisor,
            "entry_point": "python -m ava gateway",
            "last_exit_reason": exit_reason or self.last_exit_reason,
        }
        state_file = self.runtime_dir / "state.json"
        try:
            state_file.write_text(json.dumps(state, indent=2))
        except Exception as exc:
            logger.warning("LifecycleManager: failed to write state: {}", exc)

    def _write_restart_request(self) -> None:
        if not self._restart_request:
            return
        req_file = self.runtime_dir / "restart_request.json"
        try:
            req_file.write_text(json.dumps(self._restart_request, indent=2))
        except Exception as exc:
            logger.warning("LifecycleManager: failed to write restart request: {}", exc)

    # ------------------------------------------------------------------
    # 清理
    # ------------------------------------------------------------------

    def cleanup(self) -> None:
        """进程退出时清理（不删除 state.json，供下一代读取）。"""
        pid_file = Path.home() / ".nanobot" / "gateway.pid"
        try:
            pid_file.unlink(missing_ok=True)
        except OSError:
            pass


def _detect_supervisor() -> tuple[bool, str]:
    """检测是否受 supervisor 管理。

    优先级：显式声明 > 强阳性探测 > 默认 unsupervised。
    """
    env_val = os.environ.get("AVA_SUPERVISOR", "").lower()
    if env_val in ("docker", "systemd"):
        return True, env_val
    if env_val == "none":
        return False, "none"

    # auto（默认）：强阳性探测
    cgroup_path = Path("/proc/1/cgroup")
    if cgroup_path.exists():
        try:
            cgroup = cgroup_path.read_text()
            if "docker" in cgroup or "containerd" in cgroup:
                return True, "docker"
        except OSError:
            pass

    if os.environ.get("INVOCATION_ID"):
        return True, "systemd"

    return False, "none"
