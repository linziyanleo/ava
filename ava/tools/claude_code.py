"""Claude Code CLI integration tool."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from loguru import logger

from nanobot.agent.tools.base import Tool

if TYPE_CHECKING:
    from ava.agent.bg_tasks import BackgroundTaskStore, SubmitResult

_MAX_OUTPUT_CHARS = 32000   # hard cap for extreme cases
_HEAD_CHARS = 8000          # keep first N chars (task breakdown, early progress)
_TAIL_CHARS = 12000         # keep last N chars (final summary, conclusions)

class ClaudeCodeTool(Tool):
    """Run Claude Code CLI to modify code, add features, fix bugs, or analyze a codebase.

    All runs are async via BackgroundTaskStore.
    """

    def __init__(
        self,
        workspace: Path,
        token_stats: Any | None = None,
        default_project: str = "",
        model: str = "claude-sonnet-4-20250514",
        max_turns: int = 15,
        allowed_tools: str = "Read,Edit,Bash,Glob,Grep",
        timeout: int = 600,
        subagent_manager: Any | None = None,
        task_store: BackgroundTaskStore | None = None,
        cc_config: Any | None = None,
    ) -> None:
        self._workspace = workspace
        self._token_stats = token_stats
        self._default_project = default_project or str(workspace)
        self._model = model
        self._max_turns = max_turns
        self._allowed_tools = allowed_tools
        self._timeout = timeout
        self._subagent_manager = subagent_manager
        self._task_store = task_store
        self.cc_config = cc_config or SimpleNamespace(api_key="", base_url="")
        self._channel = "cli"
        self._chat_id = "direct"
        self._session_key = "cli:direct"

    def set_context(
        self, channel: str, chat_id: str, *, session_key: str | None = None,
    ) -> None:
        """Set the origin context for async task result routing."""
        self._channel = channel
        self._chat_id = chat_id
        self._session_key = session_key or f"{channel}:{chat_id}"

    @property
    def name(self) -> str:
        return "claude_code"

    @property
    def description(self) -> str:
        return (
            "Run Claude Code CLI for code tasks. "
            "For ANY task involving code modification, refactoring, bug fixing, "
            "or multi-file analysis, ALWAYS prefer this tool over manually "
            "reading/writing files one by one with read_file/write_file/edit_file. "
            "All runs are async (background, notifies when complete). "
            "Modes: 'standard' (default, full tool access), "
            "'readonly' (read-only analysis)."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "The task prompt for Claude Code. Be specific: include file paths, expected behavior, and constraints.",
                },
                "project_path": {
                    "type": "string",
                    "description": "Project directory (absolute path). Omit to use default project.",
                },
                "mode": {
                    "type": "string",
                    "enum": ["standard", "readonly"],
                    "description": (
                        "standard: async, full tool access (default); "
                        "readonly: async, analysis only"
                    ),
                },
                "session_id": {
                    "type": "string",
                    "description": "Resume a previous Claude Code session by its session ID",
                },
            },
            "required": ["prompt"],
        }

    async def execute(
        self,
        prompt: str,
        project_path: str | None = None,
        mode: str = "standard",
        session_id: str | None = None,
        **kwargs: Any,
    ) -> str:
        project = self._resolve_project(project_path)
        if not Path(project).is_dir():
            return f"Error: Project directory does not exist: {project}"

        if not self._task_store:
            return "Error: BackgroundTaskStore not available."

        from ava.agent.worktree_manager import resolve_target, make_inplace_workspace

        try:
            target = resolve_target(project)
        except ValueError:
            target = None

        workspace = None
        if target:
            ws_id = f"{self._session_key}:{target.workspace_key}"
            workspace = make_inplace_workspace(target, workspace_id=ws_id)

        result = self._task_store.submit_coding_task(
            executor=self._execute_background,
            origin_session_key=self._session_key,
            prompt=prompt,
            project_path=project,
            timeout=self._timeout,
            task_type="claude_code",
            auto_continue=mode == "standard",
            target=target,
            workspace=workspace,
            mode=mode,
            session_id=session_id,
            project=project,
        )
        return self._format_submit_result(result)

    async def _execute_background(
        self,
        *,
        prompt: str = "",
        mode: str = "standard",
        session_id: str | None = None,
        project: str = "",
        **_kw: Any,
    ) -> dict[str, Any]:
        """Execute Claude Code in background. Called by BackgroundTaskStore."""
        claude_bin = shutil.which("claude")
        if not claude_bin:
            raise RuntimeError(
                "claude not found in PATH. Install: npm install -g @anthropic-ai/claude-code"
            )
        if not prompt:
            raise ValueError("prompt is required")
        cmd = self._build_command(prompt, project, mode, session_id)
        stdout, stderr = await self._run_subprocess(cmd, project, self._timeout)
        if stderr and not stdout:
            raise RuntimeError(f"Claude Code failed: {stderr[:500]}")
        parsed = self._parse_result(stdout)
        if parsed.get("_parse_error"):
            raise RuntimeError(f"Claude Code parse error: {stderr[:300] or '(no output)'}")
        self._record_stats(parsed, prompt)
        return parsed

    async def cancel(self, task_id: str) -> str:
        """Cancel a running Claude Code task."""
        if not self._task_store:
            return "Error: BackgroundTaskStore not available."
        return await self._task_store.cancel(task_id)

    def _resolve_project(self, project_path: str | None) -> str:
        if project_path:
            return project_path
        return self._default_project

    def _build_command(
        self,
        prompt: str,
        project: str,
        mode: str,
        session_id: str | None,
    ) -> list[str]:
        allowed = "View,Read,Glob,Grep" if mode == "readonly" else self._allowed_tools

        cmd = [
            "claude",
            "-p", prompt,
            "--output-format", "json",
            "--model", self._model,
            "--max-turns", str(self._max_turns),
            "--allowedTools", allowed,
        ]

        if session_id:
            cmd.extend(["--resume", session_id])

        return cmd

    async def _run_subprocess(
        self,
        cmd: list[str],
        cwd: str,
        timeout: int,
    ) -> tuple[str, str]:
        env = os.environ.copy()
        # Inject Claude Code auth from nanobot config
        if self.cc_config.api_key:
            env["ANTHROPIC_API_KEY"] = self.cc_config.api_key
            logger.debug("claude_code: injected ANTHROPIC_API_KEY from config")
        if self.cc_config.base_url:
            env["ANTHROPIC_BASE_URL"] = self.cc_config.base_url
            logger.debug("claude_code: injected ANTHROPIC_BASE_URL from config")
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=env,
                limit=10 * 1024 * 1024,  # 10MB per line limit to avoid StreamReader overflow
            )
            try:
                # Use read() instead of communicate() to avoid asyncio StreamReader
                # "Separator is found, but chunk is longer than limit" ValueError
                # when claude CLI outputs a very large single-line JSON event.
                async def _read_stdout() -> bytes:
                    return await process.stdout.read() if process.stdout else b""

                async def _read_stderr() -> bytes:
                    return await process.stderr.read() if process.stderr else b""

                stdout_bytes, stderr_bytes, _ = await asyncio.wait_for(
                    asyncio.gather(_read_stdout(), _read_stderr(), process.wait()),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                process.kill()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    pass
                return "", f"Claude Code timed out after {timeout}s"
            except asyncio.CancelledError:
                logger.info("claude_code: cancelled, killing child pid={}", process.pid)
                process.kill()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    pass
                raise
        except asyncio.CancelledError:
            raise
        except Exception as e:
            return "", f"Failed to start Claude Code: {e}"

        stdout = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
        stderr = stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else ""
        return stdout, stderr

    def _parse_result(self, stdout: str) -> dict[str, Any]:
        """Parse the JSON output from Claude Code CLI."""
        stdout = stdout.strip()
        if not stdout:
            return {"_parse_error": True}

        for line in reversed(stdout.splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                continue

        return {"_parse_error": True}

    def _record_stats(self, parsed: dict[str, Any], prompt: str = "") -> None:
        if not self._token_stats:
            return

        usage = parsed.get("usage", {})
        cost = parsed.get("total_cost_usd", 0.0)
        duration_ms = parsed.get("duration_ms", 0)
        num_turns = parsed.get("num_turns", 0)
        session_id = parsed.get("session_id", "")
        result_text = parsed.get("result", "")
        is_error = parsed.get("is_error", False)
        stop_reason = parsed.get("stop_reason", "")

        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        cache_read = usage.get("cache_read_input_tokens", 0)
        cache_creation = usage.get("cache_creation_input_tokens", 0)
        total_input = input_tokens + cache_read + cache_creation

        model_usage = parsed.get("modelUsage", {})
        model_name = self._model
        if model_usage:
            model_name = next(iter(model_usage), self._model)

        finish = "error" if is_error else stop_reason or "end_turn"

        user_msg = (
            f"[claude_code] session={session_id} turns={num_turns} "
            f"duration={duration_ms}ms\n\n--- Prompt ---\n{prompt}"
        )

        self._token_stats.record(
            model=model_name,
            provider="claude-code-cli",
            usage={
                "prompt_tokens": total_input,
                "completion_tokens": output_tokens,
                "total_tokens": total_input + output_tokens,
                "cache_creation_input_tokens": cache_creation,
                "prompt_tokens_details": {"cached_tokens": cache_read},
            },
            user_message=user_msg,
            output_content=result_text[:_MAX_OUTPUT_CHARS] if result_text else "",
            finish_reason=finish,
            model_role="claude_code",
            cost_usd=cost,
        )

        logger.info(
            "claude_code stats: model={} input={} output={} cache_read={} cache_create={} cost=${:.6f} turns={} duration={}ms",
            model_name, input_tokens, output_tokens, cache_read, cache_creation,
            cost, num_turns, duration_ms,
        )

    @staticmethod
    def _format_submit_result(result: SubmitResult) -> str:
        parts = [f"Claude Code task started (id: {result.task_id})."]
        if result.replaced_task_id:
            parts.append(f" Replaced previous task {result.replaced_task_id}.")
        if result.active_in_session:
            parts.append(
                f" ({len(result.active_in_session)} other active task(s) in this session)"
            )
        parts.append(" Use /task to check progress.")
        return "".join(parts)

    def _format_output(self, parsed: dict[str, Any], mode: str) -> str:
        is_error = parsed.get("is_error", False)
        result_text = parsed.get("result", "")
        subtype = parsed.get("subtype", "")
        num_turns = parsed.get("num_turns", 0)
        duration_ms = parsed.get("duration_ms", 0)
        cost = parsed.get("total_cost_usd", 0.0)
        session_id = parsed.get("session_id", "")

        status = "ERROR" if is_error else subtype.upper() or "SUCCESS"

        parts = [
            f"[Claude Code {status}]",
            f"Turns: {num_turns} | Duration: {duration_ms}ms | Cost: ${cost:.4f}",
        ]

        if session_id:
            parts.append(f"Session: {session_id}")

        parts.append("")

        if result_text:
            if len(result_text) > _MAX_OUTPUT_CHARS:
                head = result_text[:_HEAD_CHARS]
                tail = result_text[-_TAIL_CHARS:]
                omitted = len(result_text) - _HEAD_CHARS - _TAIL_CHARS
                result_text = (
                    head
                    + f"\n\n... [{omitted} chars omitted — output too long] ...\n\n"
                    + tail
                )
            parts.append(result_text)
        else:
            parts.append("(no result text)")

        return "\n".join(parts)
