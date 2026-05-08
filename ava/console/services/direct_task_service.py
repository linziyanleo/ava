"""Direct background task submission for Console slash commands."""

from __future__ import annotations

import json
import re
import shutil
import tomllib
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal

from ava.tools import ClaudeCodeTool, CodexTool, ImageGenTool

DirectTaskType = Literal["codex", "claude_code", "image_gen"]

SUPPORTED_TASK_TYPES: set[str] = {"codex", "claude_code", "image_gen"}
_TASK_ID_RE = re.compile(r"\(id:\s*([^)]+)\)")
_IMAGE_REFERENCE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif"}


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
        config_service: Any | None = None,
    ) -> None:
        self._agent_loop = agent_loop
        self._workspace = Path(workspace)
        self._bg_store = bg_store
        self._token_stats = token_stats
        self._media_service = media_service
        self._config_service = config_service

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
        if task_type == "image_gen" and params.get("reference_image"):
            params["reference_image"] = self._resolve_image_reference(params.get("reference_image"))
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
            cfg = self._load_agent_config("codex")
            existing_config = getattr(existing, "_codex_config", None)
            tool = CodexTool(
                workspace=getattr(existing, "_workspace", self._workspace),
                token_stats=self._token_stats or getattr(existing, "_token_stats", None),
                default_project=getattr(existing, "_default_project", str(self._workspace)),
                model=str(self._config_value(cfg, "model", fallback=getattr(existing, "_model", "")) or ""),
                timeout=int(self._config_value(cfg, "timeout", fallback=getattr(existing, "_timeout", 600)) or 600),
                task_store=self._bg_store,
                codex_config=SimpleNamespace(
                    api_key=str(self._config_value(cfg, "api_key", "apiKey", fallback=getattr(existing_config, "api_key", "")) or ""),
                    api_base=str(self._config_value(cfg, "api_base", "apiBase", fallback=getattr(existing_config, "api_base", "")) or ""),
                ),
            )
        elif task_type == "claude_code":
            cfg = self._load_agent_config("claude_code")
            existing_config = getattr(existing, "cc_config", None)
            tool = ClaudeCodeTool(
                workspace=getattr(existing, "_workspace", self._workspace),
                token_stats=self._token_stats or getattr(existing, "_token_stats", None),
                default_project=getattr(existing, "_default_project", str(self._workspace)),
                model=str(self._config_value(cfg, "model", fallback=getattr(existing, "_model", "claude-sonnet-4-20250514")) or "claude-sonnet-4-20250514"),
                max_turns=int(self._config_value(cfg, "max_turns", "maxTurns", fallback=getattr(existing, "_max_turns", 15)) or 15),
                allowed_tools=str(self._config_value(cfg, "allowed_tools", "allowedTools", fallback=getattr(existing, "_allowed_tools", "Read,Edit,Bash,Glob,Grep")) or "Read,Edit,Bash,Glob,Grep"),
                timeout=int(self._config_value(cfg, "timeout", fallback=getattr(existing, "_timeout", 600)) or 600),
                subagent_manager=getattr(existing, "_subagent_manager", None),
                task_store=self._bg_store,
                cc_config=SimpleNamespace(
                    api_key=str(self._config_value(cfg, "api_key", "apiKey", fallback=getattr(existing_config, "api_key", "")) or ""),
                    base_url=str(self._config_value(cfg, "base_url", "baseUrl", "api_base", "apiBase", fallback=getattr(existing_config, "base_url", "")) or ""),
                ),
            )
        else:
            cfg = self._load_agent_config("image_gen")
            tool = ImageGenTool(
                token_stats=self._token_stats or getattr(existing, "_token_stats", None),
                media_service=self._media_service or getattr(existing, "_media_service", None),
                task_store=self._bg_store,
                timeout=int(self._config_value(cfg, "timeout", fallback=getattr(existing, "_timeout", 300)) or 300),
                background=bool(self._config_value(cfg, "background", fallback=getattr(existing, "_background", True))),
                auto_continue=bool(self._config_value(cfg, "auto_continue", "autoContinue", fallback=getattr(existing, "_auto_continue", False))),
                auto_send=bool(self._config_value(cfg, "auto_send", "autoSend", fallback=getattr(existing, "_auto_send", True))),
            )

        # Direct path intentionally avoids set_context(), which carries the
        # primary chat-agent turn metadata. Only inject routing fields needed by bg_tasks.
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
            reference_image=reference_image,
            continue_after_completion=self._optional_bool(params.get("continue_after_completion"))
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

    def _load_agent_config(self, task_type: str) -> dict[str, Any]:
        if self._config_service is None:
            return {}
        name = {
            "codex": "codex-config.toml",
            "claude_code": "claude-code-settings.json",
            "image_gen": "image-gen-config.json",
        }.get(task_type)
        if not name:
            return {}
        try:
            payload = self._config_service.read_config(name, mask=False)
            content = str(payload.get("content") or "")
            fmt = str(payload.get("format") or "")
            if fmt == "toml" or name.endswith(".toml"):
                parsed = tomllib.loads(content)
            else:
                parsed = json.loads(content)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _config_value(config: dict[str, Any], *keys: str, fallback: Any = None) -> Any:
        for key in keys:
            if key in config and config[key] not in {"", None}:
                return config[key]
        return fallback

    def _resolve_image_reference(self, raw_reference: Any) -> str | None:
        if not raw_reference:
            return None
        reference = str(raw_reference).strip()
        if not reference:
            return None

        filename = reference.replace("\\", "/").split("/")[-1]
        if not filename or filename in {".", ".."} or ".." in filename:
            raise ValueError("reference_image must be a previously uploaded image")
        if Path(filename).suffix.lower() not in _IMAGE_REFERENCE_EXTENSIONS:
            raise ValueError("reference_image must be an image file")

        getter = getattr(self._media_service, "get_image_path", None)
        if not callable(getter):
            raise ValueError("reference_image uploads are unavailable")
        resolved = getter(filename)
        if not resolved:
            raise ValueError("reference_image must be a previously uploaded image")
        return str(resolved)

    @staticmethod
    def _optional_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "on"}:
                return True
            if normalized in {"false", "0", "no", "off", ""}:
                return False
        return bool(value)

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
