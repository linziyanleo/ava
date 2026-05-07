"""Direct background task submission for Console slash commands."""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any, Literal

from ava.tools import ClaudeCodeTool, CodexTool, ImageGenTool

DirectTaskType = Literal["codex", "claude_code", "image_gen"]

SUPPORTED_TASK_TYPES: set[str] = {"codex", "claude_code", "image_gen"}
_TASK_ID_RE = re.compile(r"\(id:\s*([^)]+)\)")


class DirectTaskService:
    """Thin adapter from Console slash command payloads to background tools."""

    def __init__(
        self,
        *,
        agent_loop: Any,
        workspace: Path,
        bg_store: Any,
        token_stats: Any | None = None,
        media_service: Any | None = None,
    ) -> None:
        self._agent_loop = agent_loop
        self._workspace = Path(workspace)
        self._bg_store = bg_store
        self._token_stats = token_stats
        self._media_service = media_service

    async def submit(
        self,
        *,
        task_type: str,
        prompt: str,
        session_key: str,
        conversation_id: str = "",
        turn_seq: int | None = None,
        project_path: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        task_type = task_type.strip()
        prompt = prompt.strip()
        if task_type not in SUPPORTED_TASK_TYPES:
            raise ValueError(f"Unsupported direct task type: {task_type}")
        if not prompt:
            raise ValueError("prompt is required")
        if not session_key:
            raise ValueError("session_key is required")

        binary_error = self.check_binary(task_type)
        if binary_error:
            raise RuntimeError(binary_error)

        params = dict(params or {})
        tool = self._make_tool(
            task_type=task_type,
            session_key=session_key,
            conversation_id=conversation_id,
            turn_seq=turn_seq,
        )
        result_text = await self._execute_tool(
            tool=tool,
            task_type=task_type,
            prompt=prompt,
            project_path=project_path,
            params=params,
        )
        if result_text.startswith("Error:"):
            raise ValueError(result_text[len("Error:"):].strip())

        match = _TASK_ID_RE.search(result_text)
        if not match:
            raise RuntimeError(f"Direct task did not return a task id: {result_text}")

        task_id = match.group(1).strip()
        status = self._lookup_status(task_id)
        return {
            "task_id": task_id,
            "status": status,
            "task_type": task_type,
        }

    def _make_tool(
        self,
        *,
        task_type: str,
        session_key: str,
        conversation_id: str,
        turn_seq: int | None,
    ) -> Any:
        existing = self._get_registered_tool(task_type)
        if task_type == "codex":
            tool = CodexTool(
                workspace=getattr(existing, "_workspace", self._workspace),
                token_stats=self._token_stats or getattr(existing, "_token_stats", None),
                default_project=getattr(existing, "_default_project", str(self._workspace)),
                model=getattr(existing, "_model", ""),
                timeout=getattr(existing, "_timeout", 600),
                task_store=self._bg_store,
                codex_config=getattr(existing, "_codex_config", None),
            )
        elif task_type == "claude_code":
            tool = ClaudeCodeTool(
                workspace=getattr(existing, "_workspace", self._workspace),
                token_stats=self._token_stats or getattr(existing, "_token_stats", None),
                default_project=getattr(existing, "_default_project", str(self._workspace)),
                model=getattr(existing, "_model", "claude-sonnet-4-20250514"),
                max_turns=getattr(existing, "_max_turns", 15),
                allowed_tools=getattr(existing, "_allowed_tools", "Read,Edit,Bash,Glob,Grep"),
                timeout=getattr(existing, "_timeout", 600),
                subagent_manager=getattr(existing, "_subagent_manager", None),
                task_store=self._bg_store,
                cc_config=getattr(existing, "cc_config", None),
            )
        else:
            tool = ImageGenTool(
                token_stats=self._token_stats or getattr(existing, "_token_stats", None),
                media_service=self._media_service or getattr(existing, "_media_service", None),
                task_store=self._bg_store,
                timeout=getattr(existing, "_timeout", 300),
                background=getattr(existing, "_background", True),
                auto_continue=getattr(existing, "_auto_continue", False),
                auto_send=getattr(existing, "_auto_send", True),
            )

        # Direct path intentionally avoids set_context(), which carries nanobot
        # turn metadata. Only inject the routing fields needed by bg_tasks.
        setattr(tool, "_task_store", self._bg_store)
        setattr(tool, "_session_key", session_key)
        if hasattr(tool, "_channel"):
            setattr(tool, "_channel", "console")
        if hasattr(tool, "_chat_id"):
            setattr(tool, "_chat_id", session_key.split(":", 1)[1] if ":" in session_key else session_key)
        if hasattr(tool, "_conversation_id"):
            setattr(tool, "_conversation_id", conversation_id or "")
        if hasattr(tool, "_turn_seq"):
            setattr(tool, "_turn_seq", turn_seq)
        return tool

    async def _execute_tool(
        self,
        *,
        tool: Any,
        task_type: str,
        prompt: str,
        project_path: str | None,
        params: dict[str, Any],
    ) -> str:
        if task_type in {"codex", "claude_code"}:
            mode = str(params.get("mode") or "standard")
            if mode not in {"standard", "readonly"}:
                raise ValueError("mode must be standard or readonly")
            kwargs: dict[str, Any] = {
                "prompt": prompt,
                "project_path": project_path,
                "mode": mode,
            }
            if task_type == "claude_code":
                if params.get("session_id"):
                    kwargs["session_id"] = str(params["session_id"])
                if "auto_continue" in params:
                    kwargs["auto_continue"] = bool(params["auto_continue"])
            return str(await tool.execute(**kwargs))

        reference_image = params.get("reference_image")
        return str(await tool.execute(
            prompt=prompt,
            reference_image=str(reference_image).strip() if reference_image else None,
            continue_after_completion=bool(params["continue_after_completion"])
            if "continue_after_completion" in params else None,
        ))

    def check_binary(self, task_type: str) -> str | None:
        if task_type == "codex" and not shutil.which("codex"):
            return "codex not found in PATH. Install: npm install -g @openai/codex"
        if task_type == "claude_code" and not shutil.which("claude"):
            return "claude not found in PATH. Install: npm install -g @anthropic-ai/claude-code"
        return None

    def _get_registered_tool(self, task_type: str) -> Any | None:
        tools = getattr(self._agent_loop, "tools", None)
        getter = getattr(tools, "get", None)
        if callable(getter):
            try:
                return getter(task_type)
            except Exception:
                return None
        return None

    def _lookup_status(self, task_id: str) -> str:
        getter = getattr(self._bg_store, "get_status", None)
        if not callable(getter):
            return "queued"
        status = getter(task_id=task_id, include_finished=True)
        tasks = status.get("tasks", []) if isinstance(status, dict) else []
        if tasks:
            task = tasks[0]
            if isinstance(task, dict):
                return str(task.get("status") or "queued")
        return "queued"
