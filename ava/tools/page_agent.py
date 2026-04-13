"""通用 PageAgent 页面操作工具。

通过常驻 Node runner 进程（page-agent-runner.mjs）管理 Playwright 浏览器，
在页面内注入 page-agent 实现自然语言操控网页。

通信协议：stdin/stdout JSON-RPC（每行一个 JSON）。
推送事件（frame/activity/status/session_closed）无 id 字段，RPC 响应有 id 字段。
"""

from __future__ import annotations

import asyncio
import atexit
import json
import os
import shutil
import time
import uuid
import weakref
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from loguru import logger

from nanobot.agent.tools.base import Tool

_RUNNER_SCRIPT = Path(__file__).resolve().parents[2] / "console-ui" / "e2e" / "page-agent-runner.mjs"

_IDLE_TIMEOUT = 300  # 空闲 5 分钟自动回收 runner
_LIVE_PAGE_AGENT_TOOLS: weakref.WeakSet[PageAgentTool] | None = None
_PROCESS_CLEANUP_REGISTERED = False


def _find_node() -> str | None:
    """查找 node 可执行文件，支持 nvm/fnm/homebrew 等非标准 PATH 场景。"""
    # 1. 标准 PATH 查找
    found = shutil.which("node")
    if found:
        return found

    # 2. 常见安装路径探测
    home = Path.home()
    candidates: list[Path] = []

    # nvm：取最新版本
    nvm_dir = home / ".nvm" / "versions" / "node"
    if nvm_dir.is_dir():
        versions = sorted(nvm_dir.iterdir(), reverse=True)
        candidates.extend(v / "bin" / "node" for v in versions)

    # fnm
    fnm_dir = home / ".local" / "share" / "fnm" / "node-versions"
    if fnm_dir.is_dir():
        versions = sorted(fnm_dir.iterdir(), reverse=True)
        candidates.extend(v / "installation" / "bin" / "node" for v in versions)

    # homebrew (macOS)
    for prefix in ("/opt/homebrew/bin/node", "/usr/local/bin/node"):
        candidates.append(Path(prefix))

    for c in candidates:
        if c.is_file() and os.access(c, os.X_OK):
            logger.info("page_agent: node found at {}", c)
            return str(c)

    return None


class PageAgentTool(Tool):
    """Control web pages using natural language via page-agent + Playwright."""

    def __init__(
        self,
        config: Any | None = None,
        media_service: Any | None = None,
        token_stats: Any | None = None,
    ) -> None:
        self._config = config
        self._media_service = media_service
        self._token_stats = token_stats
        # Runner 进程
        self._process: asyncio.subprocess.Process | None = None
        self._process_finalizer: weakref.finalize | None = None
        self._reader_task: asyncio.Task | None = None
        self._last_activity: float = time.monotonic()
        self._idle_task: asyncio.Task | None = None
        self._req_counter = 0
        # RPC 请求等待表
        self._pending: dict[str, asyncio.Future] = {}
        # 推送事件订阅者 { session_id: [callback, ...] }
        self._subscribers: dict[str, list[Callable]] = {}
        # 事件缓存：最近 N 条 activity 事件 + 最后一帧，供 WS 连接后回放
        self._event_buffer: dict[str, list[dict]] = {}  # session_id -> recent events
        self._last_frame: dict[str, dict] = {}  # session_id -> last frame event
        self._EVENT_BUFFER_SIZE = 50
        self._lock = asyncio.Lock()
        # Context
        self._channel = "cli"
        self._chat_id = "direct"
        self._get_live_tools().add(self)
        self._register_process_cleanup()

    def set_context(self, channel: str, chat_id: str) -> None:
        self._channel = channel
        self._chat_id = chat_id

    @staticmethod
    def _get_live_tools() -> weakref.WeakSet[PageAgentTool]:
        global _LIVE_PAGE_AGENT_TOOLS
        if _LIVE_PAGE_AGENT_TOOLS is None:
            _LIVE_PAGE_AGENT_TOOLS = weakref.WeakSet()
        return _LIVE_PAGE_AGENT_TOOLS

    @classmethod
    def _register_process_cleanup(cls) -> None:
        global _PROCESS_CLEANUP_REGISTERED
        if _PROCESS_CLEANUP_REGISTERED:
            return
        atexit.register(cls._cleanup_live_tools)
        _PROCESS_CLEANUP_REGISTERED = True

    @classmethod
    def _cleanup_live_tools(cls) -> None:
        for tool in list(cls._get_live_tools()):
            try:
                tool._sync_cleanup()
            except Exception:
                pass

    @staticmethod
    def _kill_process_sync(process: asyncio.subprocess.Process | None) -> None:
        if process and process.returncode is None:
            try:
                process.kill()
            except Exception:
                pass

    def _bind_process_finalizer(self, process: asyncio.subprocess.Process) -> None:
        self._clear_process_finalizer()
        self._process_finalizer = weakref.finalize(
            self,
            type(self)._kill_process_sync,
            process,
        )

    def _clear_process_finalizer(self) -> None:
        if self._process_finalizer and self._process_finalizer.alive:
            self._process_finalizer.detach()
        self._process_finalizer = None

    def _clear_session_state(self, session_id: str | None = None) -> None:
        if session_id is None:
            self._subscribers.clear()
            self._event_buffer.clear()
            self._last_frame.clear()
            return
        self._subscribers.pop(session_id, None)
        self._event_buffer.pop(session_id, None)
        self._last_frame.pop(session_id, None)

    def _sweep_stale_sessions(self, active_session_ids: set[str] | None = None) -> None:
        for session_id, callbacks in list(self._subscribers.items()):
            if not callbacks:
                self._subscribers.pop(session_id, None)

        if active_session_ids is None:
            return

        stale_session_ids = (
            set(self._subscribers)
            | set(self._event_buffer)
            | set(self._last_frame)
        ) - set(active_session_ids)
        for stale_session_id in stale_session_ids:
            self._clear_session_state(stale_session_id)

    # ------------------------------------------------------------------
    # Tool 接口
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "page_agent"

    @property
    def description(self) -> str:
        return (
            "Interact with web pages: click buttons, fill forms, scroll, navigate multi-step flows, "
            "and take screenshots. Use ONLY when the page requires interaction or JS-rendered dynamic content. "
            "For simply reading/summarizing a URL, use web_fetch instead (lighter and more reliable)."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["execute", "screenshot", "get_page_info", "close_session", "restart_runner"],
                    "description": (
                        "Action to perform. "
                        "'execute': interact with page via natural language instruction (click, fill, scroll, navigate). "
                        "'screenshot': capture a PNG screenshot of the current page (requires session_id of an open session; "
                        "supports optional url to navigate before capture). "
                        "IMPORTANT: when the user asks to take a screenshot / 截图 / capture the page, "
                        "always use 'screenshot' — do NOT use 'execute' with a screenshot instruction. "
                        "'get_page_info': get page URL, title, and element summary. "
                        "'close_session': close a browser session. "
                        "'restart_runner': restart the browser runner process."
                    ),
                },
                "url": {
                    "type": "string",
                    "description": (
                        "Target URL to navigate to (for execute and screenshot actions, "
                        "optional if session already has a page open). "
                        "For screenshot: if no session_id exists, a new session is created and navigates to this URL before capture."
                    ),
                },
                "instruction": {
                    "type": "string",
                    "description": "Natural language instruction for page operation (required for execute)",
                },
                "session_id": {
                    "type": "string",
                    "description": (
                        "Session ID for reusing browser context. "
                        "For execute: omit to auto-generate. "
                        "For screenshot: provide to capture an existing session, or omit with url to auto-create."
                    ),
                },
                "response_format": {
                    "type": "string",
                    "enum": ["text", "json"],
                    "description": "Output format for execute/screenshot/get_page_info. Default is text.",
                },
            },
            "required": ["action"],
        }

    async def execute(self, action: str, response_format: str = "text", **kwargs: Any) -> str:
        if not self._is_enabled():
            return "Error: page_agent is disabled in config"

        fmt = self._normalize_response_format(response_format)
        if not fmt:
            return "Error: response_format must be 'text' or 'json'"

        if action == "execute":
            return await self._do_execute(kwargs, fmt)
        elif action == "screenshot":
            return await self._do_screenshot(kwargs, fmt)
        elif action == "get_page_info":
            return await self._do_get_page_info(kwargs, fmt)
        elif action == "close_session":
            return await self._do_close_session(kwargs)
        elif action == "restart_runner":
            return await self._do_restart_runner()
        else:
            if fmt == "json":
                return self._json_dumps({
                    "status": "ERROR",
                    "session_id": kwargs.get("session_id"),
                    "result": {"success": False},
                    "error": {
                        "code": "UNKNOWN_ACTION",
                        "message": f"unknown action '{action}'",
                    },
                })
            return f"Error: unknown action '{action}'"

    # ------------------------------------------------------------------
    # Action 实现
    # ------------------------------------------------------------------

    async def _do_execute(self, kwargs: dict, response_format: str) -> str:
        instruction = kwargs.get("instruction")
        if not instruction:
            return self._format_action_error(
                "instruction is required for execute action",
                response_format=response_format,
                action="execute",
            )

        session_id = kwargs.get("session_id") or f"s_{uuid.uuid4().hex[:8]}"
        url = kwargs.get("url")

        result = await self._rpc("execute", {
            "url": url,
            "instruction": instruction,
            "session_id": session_id,
        })

        if not result.get("success"):
            if response_format == "json":
                return self._json_dumps(self._build_execute_error_payload(result, session_id))
            return self._format_error_result(result, session_id)

        r = result.get("result", {})
        inner_success = r.get("success", True)
        status = "SUCCESS" if inner_success else "ERROR"
        steps = r.get("steps", 0)
        duration = r.get("duration", 0)
        parts = [
            f"[PageAgent {status}] session={r.get('session_id', session_id)} | Steps: {steps} | Duration: {duration}ms",
            f"URL: {r.get('page_url', 'unknown')}",
            f"Title: {r.get('page_title', 'unknown')}",
            "",
            r.get("data", "(no output)"),
        ]

        page_state = r.get("page_state") or {}
        state_lines = self._format_page_state(page_state)
        if state_lines:
            parts.append("")
            parts.append("--- Page State ---")
            parts.extend(state_lines)

        self._record_llm_usage(r.get('llm_usage'), instruction, r)

        if response_format == "json":
            return self._json_dumps(self._build_execute_success_payload(r, session_id))

        return "\n".join(parts)

    def _record_llm_usage(self, llm_usage: dict | None, instruction: str, result: dict) -> None:
        """记录 page-agent 内部 LLM 调用的 token usage。"""
        if not self._token_stats or not llm_usage:
            return
        requests = llm_usage.get("requests", 0)
        if requests == 0:
            return
        prompt_tokens = llm_usage.get("promptTokens", 0)
        completion_tokens = llm_usage.get("completionTokens", 0)
        total_tokens = llm_usage.get("totalTokens", 0) or (prompt_tokens + completion_tokens)
        model = ""
        if self._config:
            model = getattr(self._config, "model", "") or "page-agent"
        else:
            model = "page-agent"
        steps = result.get("steps", 0)
        duration = result.get("duration", 0)
        page_url = result.get("page_url", "")
        self._token_stats.record(
            model=model,
            provider="page-agent",
            usage={
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            },
            user_message=f"[page_agent] steps={steps} duration={duration}ms\n{instruction[:200]}",
            output_content=f"URL: {page_url}",
            finish_reason="end_turn",
            model_role="page-agent",
        )
        logger.info(
            "page_agent stats: model={} prompt={} completion={} total={} requests={} steps={}",
            model, prompt_tokens, completion_tokens, total_tokens, requests, steps,
        )

    @staticmethod
    def _format_page_state(page_state: dict) -> list[str]:
        """将 runner 返回的页面结构化状态格式化为文本行。"""
        if not page_state:
            return []
        lines: list[str] = []
        headings = page_state.get("headings") or []
        if headings:
            lines.append("Headings: " + " > ".join(headings))
        alerts = page_state.get("alerts") or []
        if alerts:
            for a in alerts:
                lines.append(f"Alert: {a}")
        forms = page_state.get("forms") or []
        if forms:
            for i, form in enumerate(forms):
                inputs = form.get("inputs") or []
                if inputs:
                    fields = []
                    for inp in inputs:
                        name = inp.get("name") or inp.get("placeholder") or inp.get("type", "?")
                        filled = "filled" if inp.get("hasValue") else "empty"
                        fields.append(f"{name}({filled})")
                    lines.append(f"Form[{i}]: " + ", ".join(fields))
        buttons = page_state.get("buttons") or []
        if buttons:
            lines.append("Buttons: " + ", ".join(buttons))
        return lines

    @staticmethod
    def _normalize_response_format(response_format: str | None) -> str | None:
        fmt = response_format or "text"
        return fmt if fmt in {"text", "json"} else None

    @staticmethod
    def _json_dumps(payload: dict[str, Any]) -> str:
        return json.dumps(payload, ensure_ascii=False, indent=2)

    @staticmethod
    def _build_page_payload(url: str, title: str, *, viewport: str | None = None) -> dict[str, Any]:
        page = {
            "url": url,
            "title": title,
        }
        if viewport is not None:
            page["viewport"] = viewport
        return page

    def _format_action_error(
        self,
        message: str,
        *,
        response_format: str,
        action: str,
        session_id: str | None = None,
    ) -> str:
        if response_format == "json":
            return self._json_dumps({
                "status": "ERROR",
                "session_id": session_id,
                "result": {"success": False},
                "error": {
                    "code": "INVALID_ARGUMENT",
                    "message": message,
                    "action": action,
                },
            })
        return f"Error: {message}"

    def _build_execute_success_payload(self, result: dict[str, Any], fallback_session_id: str) -> dict[str, Any]:
        inner_success = result.get("success", True)
        error = None
        if not inner_success:
            error = {
                "code": "INNER_RESULT_FAILED",
                "message": result.get("data") or "page-agent execution reported success=false",
            }
        return {
            "status": "SUCCESS" if inner_success else "ERROR",
            "session_id": result.get("session_id", fallback_session_id),
            "steps": result.get("steps", 0),
            "duration_ms": result.get("duration", 0),
            "page": self._build_page_payload(
                result.get("page_url", "unknown"),
                result.get("page_title", "unknown"),
            ),
            "result": {
                "success": inner_success,
                "data": result.get("data", "(no output)"),
            },
            "page_state": result.get("page_state") or {},
            "error": error,
        }

    def _build_execute_error_payload(self, rpc_result: dict[str, Any], fallback_session_id: str) -> dict[str, Any]:
        err = rpc_result.get("error", {})
        if isinstance(err, dict):
            code = err.get("code") or "EXECUTION_FAILED"
            message = err.get("message", str(err))
            session_id = err.get("session_id", fallback_session_id)
            duration = err.get("duration", 0)
            page_url = err.get("page_url", "unknown")
            page_title = err.get("page_title", "unknown")
        else:
            code = "EXECUTION_FAILED"
            message = str(err)
            session_id = fallback_session_id
            duration = 0
            page_url = "unknown"
            page_title = "unknown"
        return {
            "status": "TIMEOUT" if code == "TIMEOUT" else "ERROR",
            "session_id": session_id,
            "steps": 0,
            "duration_ms": duration,
            "page": self._build_page_payload(page_url, page_title),
            "result": {
                "success": False,
                "data": "",
            },
            "page_state": {},
            "error": {
                "code": code,
                "message": message,
            },
        }

    @staticmethod
    def _format_error_result(result: dict, fallback_session_id: str) -> str:
        """将 RPC error / timeout 响应格式化为结构化文本。"""
        err = result.get("error", {})
        if isinstance(err, dict):
            code = err.get("code", "")
            msg = err.get("message", str(err))
            sid = err.get("session_id", fallback_session_id)
            duration = err.get("duration", 0)
            page_url = err.get("page_url", "unknown")
            page_title = err.get("page_title", "unknown")
        else:
            code, msg = "", str(err)
            sid, duration = fallback_session_id, 0
            page_url, page_title = "unknown", "unknown"

        status = "TIMEOUT" if code == "TIMEOUT" else "ERROR"
        parts = [
            f"[PageAgent {status}] session={sid} | Steps: 0 | Duration: {duration}ms",
            f"URL: {page_url}",
            f"Title: {page_title}",
            "",
            f"Error: {msg}",
        ]
        return "\n".join(parts)

    async def _do_screenshot(self, kwargs: dict, response_format: str) -> str:
        session_id = kwargs.get("session_id")
        url = kwargs.get("url")
        if not session_id and not url:
            return self._format_action_error(
                "session_id or url is required for screenshot action",
                response_format=response_format,
                action="screenshot",
            )
        if not session_id:
            session_id = f"s_{uuid.uuid4().hex[:8]}"

        # 生成截图路径
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        screenshot_dir = self._get_screenshot_dir()
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        filename = f"page-agent-{ts}-{session_id[:8]}.png"
        save_path = str(screenshot_dir / filename)

        rpc_params = {
            "session_id": session_id,
            "path": save_path,
        }
        if url:
            rpc_params["url"] = url
        result = await self._rpc("screenshot", rpc_params)

        if not result.get("success"):
            err = result.get("error", {})
            msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
            if response_format == "json":
                return self._json_dumps({
                    "status": "ERROR",
                    "session_id": session_id,
                    "result": {
                        "success": False,
                        "path": save_path,
                    },
                    "error": {
                        "code": err.get("code", "SCREENSHOT_FAILED") if isinstance(err, dict) else "SCREENSHOT_FAILED",
                        "message": msg,
                    },
                })
            return f"Error: {msg}"

        rpc_result = result.get("result", {})

        # 写入 MediaService
        record_id = f"page-agent-{ts}"
        if self._media_service:
            try:
                self._media_service.write_record({
                    "id": record_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "prompt": f"[page_agent screenshot] session={session_id}",
                    "output_images": [filename],
                    "model": "page-agent",
                    "status": "success",
                })
            except Exception as e:
                logger.warning("page_agent: failed to write media record: {}", e)

        if response_format == "json":
            return self._json_dumps({
                "status": "SUCCESS",
                "session_id": session_id,
                "result": {
                    "success": True,
                    "path": save_path,
                    "size_bytes": rpc_result.get("size"),
                    "media_record_id": record_id,
                },
                "error": None,
            })

        return (
            f"[PageAgent Screenshot]\n"
            f"Path: {save_path}\n"
            f"Media record: {record_id}"
        )

    async def _do_get_page_info(self, kwargs: dict, response_format: str) -> str:
        session_id = kwargs.get("session_id")
        if not session_id:
            return self._format_action_error(
                "session_id is required for get_page_info action",
                response_format=response_format,
                action="get_page_info",
            )

        result = await self._rpc("get_page_info", {"session_id": session_id})

        if not result.get("success"):
            err = result.get("error", {})
            msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
            if response_format == "json":
                return self._json_dumps({
                    "status": "ERROR",
                    "session_id": session_id,
                    "result": {"success": False},
                    "error": {
                        "code": err.get("code", "GET_PAGE_INFO_FAILED") if isinstance(err, dict) else "GET_PAGE_INFO_FAILED",
                        "message": msg,
                    },
                })
            return f"Error: {msg}"

        r = result.get("result", {})
        if response_format == "json":
            return self._json_dumps({
                "status": "SUCCESS",
                "session_id": session_id,
                "page": self._build_page_payload(
                    r.get("page_url", "unknown"),
                    r.get("page_title", "unknown"),
                    viewport=r.get("viewport", "unknown"),
                ),
                "result": {"success": True},
                "error": None,
            })
        return (
            f"URL: {r.get('page_url', 'unknown')}\n"
            f"Title: {r.get('page_title', 'unknown')}\n"
            f"Viewport: {r.get('viewport', 'unknown')}"
        )

    async def _do_close_session(self, kwargs: dict) -> str:
        session_id = kwargs.get("session_id")
        if not session_id:
            return "Error: session_id is required for close_session action"

        result = await self._rpc("close_session", {"session_id": session_id})

        if not result.get("success"):
            err = result.get("error", {})
            msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
            return f"Error: {msg}"

        self._clear_session_state(session_id)

        return f"Session {session_id} closed."

    async def _do_restart_runner(self) -> str:
        """停止当前 runner 进程，下次调用时自动重启。"""
        was_running = self._process is not None and self._process.returncode is None
        await self._shutdown_runner()
        if was_running:
            return "Runner stopped. Will restart automatically on next page_agent call."
        return "Runner was not running. Will start on next page_agent call."

    # ------------------------------------------------------------------
    # Screencast 订阅（供 console WS 路由使用）
    # ------------------------------------------------------------------

    async def start_screencast(self, session_id: str, **params: Any) -> dict:
        """启动指定会话的 CDP 帧流。"""
        return await self._rpc("start_screencast", {"session_id": session_id, **params})

    async def stop_screencast(self, session_id: str) -> dict:
        """停止指定会话的 CDP 帧流。"""
        return await self._rpc("stop_screencast", {"session_id": session_id})

    async def get_page_info(self, session_id: str) -> dict[str, Any]:
        """返回结构化页面信息，供 console WS 初始化状态。"""
        return await self._rpc("get_page_info", {"session_id": session_id})

    async def list_sessions(self) -> list[str]:
        """返回 runner 当前持有的会话列表。"""
        if not self._process or self._process.returncode is not None:
            return []

        result = await self._rpc("list_sessions", {})
        if not result.get("success"):
            return []

        sessions = result.get("result", {}).get("sessions", [])
        active_sessions = [session_id for session_id in sessions if isinstance(session_id, str)]
        self._sweep_stale_sessions(set(active_sessions))
        return active_sessions

    def subscribe(self, session_id: str, callback: Callable) -> None:
        """注册推送事件回调（frame/activity/status）。同时回放缓存事件。"""
        if session_id not in self._subscribers:
            self._subscribers[session_id] = []
        self._subscribers[session_id].append(callback)

        # 回放缓存的 activity/status 事件
        for evt in self._event_buffer.get(session_id, []):
            try:
                callback(evt)
            except Exception:
                pass
        # 回放最后一帧
        last_frame = self._last_frame.get(session_id)
        if last_frame:
            try:
                callback(last_frame)
            except Exception:
                pass

    def unsubscribe(self, session_id: str, callback: Callable) -> None:
        """移除推送事件回调。"""
        cbs = self._subscribers.get(session_id, [])
        if callback in cbs:
            cbs.remove(callback)
        if not cbs:
            self._subscribers.pop(session_id, None)

    def get_active_sessions(self) -> list[str]:
        """返回当前已有订阅者的 session id 列表。"""
        return list(self._subscribers.keys())

    # ------------------------------------------------------------------
    # Runner 进程管理
    # ------------------------------------------------------------------

    async def _ensure_runner(self) -> None:
        """懒启动 runner 进程。"""
        async with self._lock:
            if self._process and self._process.returncode is None:
                return

            node_bin = _find_node()
            if not node_bin:
                raise RuntimeError(
                    "node not found in PATH or common install locations "
                    "(nvm/fnm/homebrew). Please ensure Node.js is installed."
                )

            if not _RUNNER_SCRIPT.exists():
                raise RuntimeError(f"runner script not found: {_RUNNER_SCRIPT}")

            env = os.environ.copy()
            node_dir = str(Path(node_bin).parent)
            if node_dir not in env.get("PATH", "").split(os.pathsep):
                env["PATH"] = node_dir + os.pathsep + env.get("PATH", "")

            self._process = await asyncio.create_subprocess_exec(
                node_bin, str(_RUNNER_SCRIPT),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            self._bind_process_finalizer(self._process)
            logger.info("page_agent: runner started (pid={})", self._process.pid)

            # 后台读取 stdout
            self._reader_task = asyncio.create_task(self._read_stdout())

            # 后台读取 stderr（日志/心跳）
            asyncio.create_task(self._read_stderr())

            # 空闲回收
            self._idle_task = asyncio.create_task(self._idle_watchdog())

            # 发送 init 配置（直接写 stdin，不走 _rpc 以避免重入 lock）
            await self._send_init_direct()

    async def _send_init_direct(self) -> None:
        """在 lock 内直接发送 init，绕过 _rpc 避免死锁。"""
        cfg = self._config
        api_key = ""
        if cfg:
            api_key = getattr(cfg, "api_key", "") or ""
            if not api_key:
                env_name = getattr(cfg, "api_key_env", "PAGE_AGENT_API_KEY")
                api_key = os.environ.get(env_name, "")

        params = {
            "headless": getattr(cfg, "headless", True) if cfg else True,
            "browserType": getattr(cfg, "browser_type", "chromium") if cfg else "chromium",
            "viewportWidth": getattr(cfg, "viewport_width", 1280) if cfg else 1280,
            "viewportHeight": getattr(cfg, "viewport_height", 720) if cfg else 720,
            "userDataDir": getattr(cfg, "user_data_dir", "") if cfg else "",
            "apiBase": getattr(cfg, "api_base", "") if cfg else "",
            "apiKey": api_key,
            "model": getattr(cfg, "model", "") if cfg else "",
            "maxSteps": getattr(cfg, "max_steps", 40) if cfg else 40,
            "stepDelay": getattr(cfg, "step_delay", 0.4) if cfg else 0.4,
            "language": getattr(cfg, "language", "zh-CN") if cfg else "zh-CN",
        }

        self._req_counter += 1
        req_id = f"req-{self._req_counter}"
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        self._pending[req_id] = fut

        await self._write_stdin({"id": req_id, "method": "init", "params": params})

        try:
            await asyncio.wait_for(fut, timeout=10)
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            logger.warning("page_agent: init RPC timeout")

    async def _read_stdout(self) -> None:
        """持续读取 runner stdout，分发 RPC 响应和推送事件。"""
        assert self._process and self._process.stdout
        try:
            while True:
                line = await self._process.stdout.readline()
                if not line:
                    break
                try:
                    msg = json.loads(line.decode("utf-8", errors="replace").strip())
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue

                # 有 id -> RPC 响应
                msg_id = msg.get("id")
                if msg_id and msg_id in self._pending:
                    fut = self._pending.pop(msg_id)
                    if not fut.done():
                        fut.set_result(msg)
                    continue

                # 无 id -> 推送事件（frame/activity/status）
                session_id = msg.get("session_id")
                if not session_id:
                    continue

                # 缓存事件（无论是否有订阅者）
                msg_type = msg.get("type")
                if msg_type == "session_closed":
                    if session_id in self._subscribers:
                        for cb in list(self._subscribers[session_id]):
                            try:
                                cb(msg)
                            except Exception:
                                pass
                    self._clear_session_state(session_id)
                    continue
                if msg_type == "frame":
                    self._last_frame[session_id] = msg
                elif msg_type in ("activity", "status"):
                    buf = self._event_buffer.setdefault(session_id, [])
                    buf.append(msg)
                    if len(buf) > self._EVENT_BUFFER_SIZE:
                        buf[:] = buf[-self._EVENT_BUFFER_SIZE:]

                # 分发给订阅者
                if session_id in self._subscribers:
                    for cb in self._subscribers[session_id]:
                        try:
                            cb(msg)
                        except Exception:
                            pass
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning("page_agent: stdout reader error: {}", e)
        finally:
            # runner 退出，清理所有 pending futures
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_result({
                        "success": False,
                            "error": {"code": "RUNNER_EXIT", "message": "runner process exited"},
                    })
            self._pending.clear()
            self._clear_session_state()
            self._clear_process_finalizer()
            if self._process and self._process.returncode is not None:
                self._process = None

    async def _read_stderr(self) -> None:
        """读取 runner stderr（日志/心跳）。"""
        assert self._process and self._process.stderr
        try:
            while True:
                line = await self._process.stderr.readline()
                if not line:
                    break
                logger.debug("page_agent runner: {}", line.decode("utf-8", errors="replace").rstrip())
        except (asyncio.CancelledError, Exception):
            pass

    async def _idle_watchdog(self) -> None:
        """空闲超时自动关闭 runner。"""
        try:
            while True:
                await asyncio.sleep(60)
                if time.monotonic() - self._last_activity > _IDLE_TIMEOUT:
                    logger.info("page_agent: idle timeout, shutting down runner")
                    await self._shutdown_runner()
                    break
        except asyncio.CancelledError:
            pass

    async def _shutdown_runner(self) -> None:
        """优雅关闭 runner 进程。"""
        if not self._process or self._process.returncode is not None:
            self._process = None
            self._clear_session_state()
            self._clear_process_finalizer()
            return

        try:
            await self._write_stdin({"id": "shutdown", "method": "shutdown", "params": {}})
            await asyncio.wait_for(self._process.wait(), timeout=5)
        except (asyncio.TimeoutError, Exception):
            try:
                self._process.kill()
            except Exception:
                pass

        self._process = None
        self._clear_session_state()
        self._clear_process_finalizer()
        if self._reader_task:
            self._reader_task.cancel()
            self._reader_task = None
        if self._idle_task:
            self._idle_task.cancel()
            self._idle_task = None

    def _sync_cleanup(self) -> None:
        """atexit 同步清理。"""
        if self._process and self._process.returncode is None:
            try:
                self._process.kill()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # RPC 通信
    # ------------------------------------------------------------------

    async def _rpc(self, method: str, params: dict) -> dict:
        """发送 RPC 请求并等待响应。"""
        await self._ensure_runner()
        self._last_activity = time.monotonic()

        self._req_counter += 1
        req_id = f"req-{self._req_counter}"

        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        self._pending[req_id] = fut

        await self._write_stdin({"id": req_id, "method": method, "params": params})

        timeout = getattr(self._config, "timeout", 120) if self._config else 120
        try:
            result = await asyncio.wait_for(fut, timeout=timeout)
            if method == "list_sessions" and result.get("success"):
                sessions = result.get("result", {}).get("sessions", [])
                self._sweep_stale_sessions({sid for sid in sessions if isinstance(sid, str)})
            elif not result.get("success"):
                error = result.get("error", {})
                error_code = error.get("code") if isinstance(error, dict) else None
                if error_code == "NO_SESSION":
                    session_id = params.get("session_id")
                    if isinstance(error, dict):
                        session_id = error.get("session_id", session_id)
                    if session_id:
                        self._clear_session_state(session_id)
            return result
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            return {
                "success": False,
                "error": {"code": "TIMEOUT", "message": f"RPC timeout after {timeout}s"},
            }

    async def _write_stdin(self, msg: dict) -> None:
        """向 runner stdin 写入一行 JSON 并 flush。"""
        if not self._process or not self._process.stdin:
            return
        data = json.dumps(msg, ensure_ascii=False) + "\n"
        self._process.stdin.write(data.encode("utf-8"))
        await self._process.stdin.drain()

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------

    def _is_enabled(self) -> bool:
        if self._config is None:
            return True
        return getattr(self._config, "enabled", True)

    def _get_screenshot_dir(self) -> Path:
        if self._config:
            custom = getattr(self._config, "screenshot_dir", "")
            if custom:
                return Path(custom).expanduser()
        return Path.home() / ".nanobot" / "media" / "screenshots"
