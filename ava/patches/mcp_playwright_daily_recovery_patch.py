"""Ava-only recovery for Playwright MCP extension stale browser targets."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from ava.launcher import register_patch

_SERVER_NAME = "playwright_daily"


@dataclass
class _RecoveryState:
    command: str
    args: list[str]
    env: dict[str, str] | None
    last_navigate_arguments: dict[str, Any] | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


_STATES: dict[str, _RecoveryState] = {}


def _extract_mcp_text(result: Any) -> str:
    try:
        from mcp import types
    except Exception:  # pragma: no cover - defensive fallback
        types = None

    parts: list[str] = []
    for block in getattr(result, "content", []) or []:
        if types is not None and isinstance(block, types.TextContent):
            parts.append(block.text)
        elif hasattr(block, "text"):
            parts.append(str(getattr(block, "text")))
        else:
            parts.append(str(block))
    return "\n".join(parts) or "(no output)"


def _is_mcp_error_result(result: Any) -> bool:
    return bool(getattr(result, "isError", False) or getattr(result, "is_error", False))


def _as_runner_error(message: str) -> str:
    text = message.strip() or "MCP tool call failed"
    if text.startswith("Error"):
        return text
    if text.startswith("### Error"):
        for line in (line.strip() for line in text.splitlines() if line.strip()):
            if line.startswith("Error"):
                return line
    return f"Error: {text}"


def _is_runner_error(text: str) -> bool:
    stripped = text.lstrip()
    return stripped.startswith("Error") or stripped.startswith("### Error")


def _is_closed_target_error(text: str) -> bool:
    lowered = text.lower()
    return (
        "target page, context or browser has been closed" in lowered
        or "browserbackend.calltool: target" in lowered and "has been closed" in lowered
    )


def _get_recovery_state(server_name: str) -> _RecoveryState | None:
    if server_name != _SERVER_NAME:
        return None

    cached = _STATES.get(server_name)
    if cached is not None:
        return cached

    try:
        import nanobot.agent.tools.mcp as mcp_mod
        from nanobot.config.loader import load_config

        cfg = load_config().tools.mcp_servers.get(server_name)
        if cfg is None:
            return None

        transport_type = cfg.type
        if not transport_type:
            transport_type = "stdio" if cfg.command else ""
        if transport_type != "stdio" or not cfg.command:
            return None

        command, args, env = mcp_mod._normalize_windows_stdio_command(
            cfg.command,
            cfg.args,
            cfg.env or None,
        )
    except Exception as exc:
        logger.debug("playwright_daily recovery unavailable: {}", exc)
        return None

    state = _RecoveryState(command=command, args=args, env=env)
    _STATES[server_name] = state
    return state


@asynccontextmanager
async def _fresh_stdio_session(state: _RecoveryState):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=state.command,
        args=list(state.args),
        env=state.env,
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def _recover_closed_target(wrapper: Any, state: _RecoveryState, kwargs: dict[str, Any]) -> str:
    original_name = getattr(wrapper, "_original_name", "")
    tool_timeout = getattr(wrapper, "_tool_timeout", 30)
    wrapped_name = getattr(wrapper, "_name", original_name)

    async with state.lock:
        try:
            should_replay_navigate = (
                original_name not in {"browser_navigate", "browser_tabs"}
                and state.last_navigate_arguments is not None
            )
            async with _fresh_stdio_session(state) as session:
                if should_replay_navigate:
                    replay = await asyncio.wait_for(
                        session.call_tool(
                            "browser_navigate",
                            arguments=dict(state.last_navigate_arguments or {}),
                        ),
                        timeout=tool_timeout,
                    )
                    replay_text = _extract_mcp_text(replay)
                    if _is_mcp_error_result(replay):
                        return _as_runner_error(
                            "Playwright daily browser target was closed and "
                            f"fresh-session navigate replay failed: {replay_text}"
                        )

                retried = await asyncio.wait_for(
                    session.call_tool(original_name, arguments=dict(kwargs)),
                    timeout=tool_timeout,
                )
                retried_text = _extract_mcp_text(retried)
                if _is_mcp_error_result(retried):
                    return _as_runner_error(
                        "Playwright daily browser target was closed and "
                        f"fresh-session retry failed: {retried_text}"
                    )

                if original_name == "browser_navigate":
                    state.last_navigate_arguments = dict(kwargs)
                return retried_text
        except asyncio.TimeoutError:
            return _as_runner_error(
                "Playwright daily browser target was closed and "
                f"fresh-session retry timed out after {tool_timeout}s"
            )
        except Exception as exc:
            logger.warning(
                "MCP tool '{}' closed-target recovery failed: {}: {}",
                wrapped_name,
                type(exc).__name__,
                exc,
            )
            return _as_runner_error(
                "Playwright daily browser target was closed and "
                f"fresh-session recovery failed: {type(exc).__name__}: {exc}"
            )


def apply_playwright_daily_recovery_patch() -> str:
    """Patch MCPToolWrapper with Ava's Playwright extension recovery."""
    import nanobot.agent.tools.mcp as mcp_mod

    wrapper_cls = mcp_mod.MCPToolWrapper
    if getattr(wrapper_cls.execute, "_ava_playwright_daily_recovery_patched", False):
        return "playwright_daily recovery already applied (skipped)"

    original_init = wrapper_cls.__init__
    original_execute = wrapper_cls.execute

    def patched_init(self, session, server_name: str, tool_def, *args, **kwargs):
        original_init(self, session, server_name, tool_def, *args, **kwargs)
        self._ava_mcp_server_name = server_name
        self._ava_playwright_recovery_state = _get_recovery_state(server_name)

    async def patched_execute(self, **kwargs: Any) -> str:
        result = await original_execute(self, **kwargs)
        state = getattr(self, "_ava_playwright_recovery_state", None)
        if state is None:
            return result

        original_name = getattr(self, "_original_name", "")
        if original_name == "browser_navigate" and not _is_runner_error(result):
            state.last_navigate_arguments = dict(kwargs)
            return result

        if _is_closed_target_error(result):
            return await _recover_closed_target(self, state, kwargs)

        return result

    patched_init._ava_playwright_daily_recovery_patched = True
    patched_execute._ava_playwright_daily_recovery_patched = True
    patched_execute._ava_original_execute = original_execute
    wrapper_cls.__init__ = patched_init
    wrapper_cls.execute = patched_execute

    return "playwright_daily closed-target recovery moved to Ava patch layer"


register_patch("playwright_daily_recovery", apply_playwright_daily_recovery_patch)
