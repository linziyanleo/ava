"""OpenAI Codex CLI integration tool."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import time
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from loguru import logger

from nanobot.agent.tools.base import Tool

if TYPE_CHECKING:
    from ava.agent.bg_tasks import BackgroundTaskStore, SubmitResult

_MAX_OUTPUT_CHARS = 32000
_HEAD_CHARS = 8000
_TAIL_CHARS = 12000

_CODEX_SUBCMD = "exec"


class CodexTool(Tool):
    """Run OpenAI Codex CLI to run code tasks in background.

    All runs are async via BackgroundTaskStore. Codex CLI is invoked
    in non-interactive mode (`codex exec`) with JSONL output.
    """

    def __init__(
        self,
        workspace: Path,
        token_stats: Any | None = None,
        default_project: str = "",
        model: str = "",
        timeout: int = 600,
        task_store: BackgroundTaskStore | None = None,
        codex_config: Any | None = None,
    ) -> None:
        self._workspace = workspace
        self._token_stats = token_stats
        self._default_project = default_project or str(workspace)
        self._model = model
        self._timeout = timeout
        self._task_store = task_store
        self._codex_config = codex_config or SimpleNamespace(api_key="", api_base="")
        self._channel = "cli"
        self._chat_id = "direct"
        self._session_key = "cli:direct"

    def set_context(
        self, channel: str, chat_id: str, *, session_key: str | None = None,
    ) -> None:
        self._channel = channel
        self._chat_id = chat_id
        self._session_key = session_key or f"{channel}:{chat_id}"

    @property
    def name(self) -> str:
        return "codex"

    @property
    def description(self) -> str:
        return (
            "Run OpenAI Codex CLI for code tasks. "
            "ALWAYS prefer this tool (or claude_code) for code modification, "
            "refactoring, bug fixing, or multi-file analysis over manually "
            "reading/writing files with read_file/write_file/edit_file. "
            "All runs are async (background, notifies when complete). "
            "Modes: 'fast' (shorter timeout), 'standard' (default), "
            "'readonly' (read-only sandbox)."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "The task prompt for Codex. Be specific: include file paths, expected behavior, and constraints.",
                },
                "project_path": {
                    "type": "string",
                    "description": "Project directory (absolute path). Omit to use default project.",
                },
                "mode": {
                    "type": "string",
                    "enum": ["fast", "standard", "readonly"],
                    "description": (
                        "fast: async, 120s timeout, full-auto sandbox; "
                        "standard: async, default timeout, full-auto sandbox (default); "
                        "readonly: async, read-only sandbox"
                    ),
                },
            },
            "required": ["prompt"],
        }

    async def execute(
        self,
        prompt: str,
        project_path: str | None = None,
        mode: str = "standard",
        **kwargs: Any,
    ) -> str:
        codex_bin = shutil.which("codex")
        if not codex_bin:
            return "Error: codex not found in PATH. Install: npm install -g @openai/codex"

        project = self._resolve_project(project_path)
        if not Path(project).is_dir():
            return f"Error: Project directory does not exist: {project}"

        if not self._task_store:
            logger.warning("codex: BackgroundTaskStore not available, running inline")
            try:
                parsed = await self._run_background(
                    prompt=prompt, mode=mode, project=project,
                )
                return self._format_output(parsed, mode)
            except Exception as e:
                return f"Error: {e}"

        from ava.agent.worktree_manager import resolve_target, make_inplace_workspace

        try:
            target = resolve_target(project)
        except ValueError:
            target = None

        workspace = None
        if target:
            ws_id = f"{self._session_key}:{target.workspace_key}"
            workspace = make_inplace_workspace(target, workspace_id=ws_id)

        timeout = 120 if mode == "fast" else self._timeout
        result = self._task_store.submit_coding_task(
            executor=self._run_background,
            origin_session_key=self._session_key,
            prompt=prompt,
            project_path=project,
            timeout=timeout,
            task_type="codex",
            auto_continue=mode in ("standard", "fast"),
            target=target,
            workspace=workspace,
            mode=mode,
            project=project,
        )
        return self._format_submit_result(result)

    async def _run_background(
        self,
        *,
        prompt: str = "",
        mode: str = "standard",
        project: str = "",
        **_kw: Any,
    ) -> dict[str, Any]:
        """Perform Codex CLI run in background. Called by BackgroundTaskStore."""
        codex_bin = shutil.which("codex")
        if not codex_bin:
            raise RuntimeError(
                "codex not found in PATH. Install: npm install -g @openai/codex"
            )
        if not prompt:
            raise ValueError("prompt is required")

        cmd = self._build_command(prompt, project, mode)
        t0 = time.monotonic()
        stdout, stderr = await self._run_subprocess(cmd, project, self._timeout)
        duration_ms = int((time.monotonic() - t0) * 1000)

        if stderr and not stdout:
            raise RuntimeError(f"Codex failed: {stderr[:500]}")

        parsed = self._parse_jsonl(stdout)
        parsed["duration_ms"] = duration_ms

        if parsed.get("_parse_error"):
            raise RuntimeError(
                f"Codex parse error: {stderr[:300] or stdout[:300] or '(no output)'}"
            )

        self._record_stats(parsed, prompt)
        return parsed

    async def cancel(self, task_id: str) -> str:
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
    ) -> list[str]:
        cmd = ["codex", _CODEX_SUBCMD, prompt, "--json", "-C", project]

        if self._model:
            cmd.extend(["-m", self._model])

        if mode == "readonly":
            cmd.extend(["-s", "read-only"])
        else:
            cmd.append("--full-auto")

        return cmd

    async def _run_subprocess(
        self,
        cmd: list[str],
        cwd: str,
        timeout: int,
    ) -> tuple[str, str]:
        env = os.environ.copy()

        api_key = getattr(self._codex_config, "api_key", "") or ""
        api_base = getattr(self._codex_config, "api_base", "") or ""
        if api_key:
            env["CODEX_API_KEY"] = api_key
            logger.debug("codex: injected CODEX_API_KEY from config")
        if api_base:
            env["OPENAI_BASE_URL"] = api_base
            logger.debug("codex: injected OPENAI_BASE_URL from config")

        try:
            _create_subproc = asyncio.create_subprocess_exec
            process = await _create_subproc(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=env,
                limit=10 * 1024 * 1024,
            )
            try:
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
                return "", f"Codex timed out after {timeout}s"
            except asyncio.CancelledError:
                logger.info("codex: subprocess cancelled, killing child process pid={}", process.pid)
                process.kill()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    pass
                raise
        except asyncio.CancelledError:
            raise
        except Exception as e:
            return "", f"Failed to start Codex: {e}"

        stdout = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
        stderr = stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else ""
        return stdout, stderr

    def _parse_jsonl(self, stdout: str) -> dict[str, Any]:
        """Parse JSONL event stream from `codex exec --json`."""
        if not stdout or not stdout.strip():
            return {"_parse_error": True}

        thread_id = ""
        result_text = ""
        is_error = False
        error_message = ""
        num_turns = 0
        total_input = 0
        total_cached_input = 0
        total_output = 0

        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            etype = event.get("type", "")

            if etype == "thread.started":
                thread_id = event.get("thread_id", "")

            elif etype == "turn.completed":
                num_turns += 1
                usage = event.get("usage") or {}
                total_input += int(usage.get("input_tokens", 0) or 0)
                total_cached_input += int(usage.get("cached_input_tokens", 0) or 0)
                total_output += int(usage.get("output_tokens", 0) or 0)

            elif etype == "turn.failed":
                is_error = True
                err_obj = event.get("error")
                if isinstance(err_obj, dict):
                    error_message = err_obj.get("message", "")
                else:
                    error_message = str(err_obj or "")

            elif etype == "item.completed":
                item = event.get("item") or {}
                if item.get("type") == "agent_message":
                    result_text = item.get("text", "") or ""

            elif etype == "error":
                is_error = True
                error_message = event.get("message", "") or str(event)

        if not result_text and not is_error:
            return {"_parse_error": True}

        return {
            "run_id": thread_id,
            "thread_id": thread_id,
            "result": result_text,
            "is_error": is_error,
            "error_message": error_message,
            "num_turns": num_turns,
            "usage": {
                "input_tokens": total_input,
                "cached_input_tokens": total_cached_input,
                "output_tokens": total_output,
            },
        }

    def _record_stats(self, parsed: dict[str, Any], prompt: str = "") -> None:
        if not self._token_stats:
            return

        usage = parsed.get("usage", {})
        input_tokens = usage.get("input_tokens", 0)
        cached_input = usage.get("cached_input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        total_input = input_tokens + cached_input

        run_id = parsed.get("run_id", "") or parsed.get("thread_id", "")
        num_turns = parsed.get("num_turns", 0)
        duration_ms = parsed.get("duration_ms", 0)
        result_text = parsed.get("result", "")
        is_error = parsed.get("is_error", False)
        finish = "error" if is_error else "end_turn"
        model_name = self._model or "codex-default"

        user_msg = (
            f"[codex] run={run_id} turns={num_turns} "
            f"duration={duration_ms}ms\n\n--- Prompt ---\n{prompt}"
        )

        self._token_stats.record(
            model=model_name,
            provider="codex-cli",
            usage={
                "prompt_tokens": total_input,
                "completion_tokens": output_tokens,
                "total_tokens": total_input + output_tokens,
                "prompt_tokens_details": {"cached_tokens": cached_input},
            },
            user_message=user_msg,
            output_content=result_text[:_MAX_OUTPUT_CHARS] if result_text else "",
            finish_reason=finish,
            model_role="codex",
        )

        logger.info(
            "codex stats: model={} input={} cached={} output={} turns={} duration={}ms",
            model_name, input_tokens, cached_input, output_tokens,
            num_turns, duration_ms,
        )

    @staticmethod
    def _format_submit_result(result: SubmitResult) -> str:
        parts = [f"Codex task started (id: {result.task_id})."]
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
        error_msg = parsed.get("error_message", "")
        num_turns = parsed.get("num_turns", 0)
        duration_ms = parsed.get("duration_ms", 0)
        run_id = parsed.get("run_id", "") or parsed.get("thread_id", "")

        status = "ERROR" if is_error else "SUCCESS"

        parts = [
            f"[Codex {status}]",
            f"Turns: {num_turns} | Duration: {duration_ms}ms",
        ]

        if run_id:
            parts.append(f"Run: {run_id}")

        parts.append("")

        if is_error and error_msg:
            parts.append(f"Error: {error_msg}")

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
        elif not is_error:
            parts.append("(no result text)")

        return "\n".join(parts)
