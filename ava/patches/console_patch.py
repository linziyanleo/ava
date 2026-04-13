"""Patch to launch Web Console alongside the nanobot gateway.

Strategy:
  Wrap the Typer `gateway` command callback so that before calling
  asyncio.run(), we inject a Console uvicorn server into the same
  event loop as a background task.

  The Console uses the full create_console_app() with a live AgentLoop
  reference (captured by loop_patch during __init__), enabling direct
  chat API without HTTP reverse-proxy.

Console is served at: http://127.0.0.1:<port>
Port priority: config.gateway.console.port → CAFE_CONSOLE_PORT env → 6688
"""

from __future__ import annotations

import os

from loguru import logger

from ava.console.mock_bundle_runtime import validate_console_security
from ava.launcher import register_patch


def apply_console_patch() -> str:
    import nanobot.cli.commands as cli_mod

    # Find the gateway CommandInfo in the Typer app
    gateway_cmd = None
    for cmd_info in cli_mod.app.registered_commands:
        cb = getattr(cmd_info, "callback", None)
        if cb and cb.__name__ == "gateway":
            gateway_cmd = cmd_info
            break

    if gateway_cmd is None:
        logger.warning("gateway command not found in Typer app — console patch skipped")
        return "Console patch skipped (gateway command not found)"

    if getattr(gateway_cmd.callback, "_ava_console_patched", False):
        return "console_patch already applied (skipped)"

    original_callback = gateway_cmd.callback

    import functools

    @functools.wraps(original_callback)
    def gateway(*args, **kwargs) -> None:
        import asyncio

        original_asyncio_run = asyncio.run

        _intercepted = {"done": False}

        def patched_asyncio_run(coro, **run_kwargs):
            if _intercepted["done"]:
                return original_asyncio_run(coro, **run_kwargs)
            _intercepted["done"] = True

            async def _with_console():
                console_task = None
                pid_file = None
                try:
                    from nanobot.config.loader import load_config
                    from nanobot.config.paths import get_workspace_path
                    from pathlib import Path
                    import uvicorn

                    from nanobot.config.paths import get_data_dir

                    cfg = load_config()
                    workspace = get_workspace_path()
                    nanobot_dir = get_data_dir()  # ~/.nanobot/ — aligned with upstream
                    nanobot_dir.mkdir(parents=True, exist_ok=True)

                    # Write PID file so GatewayService can detect running gateway
                    pid_file = Path.home() / ".nanobot" / "gateway.pid"
                    pid_file.parent.mkdir(parents=True, exist_ok=True)
                    pid_file.write_text(str(os.getpid()))

                    # Port config
                    console_cfg = getattr(getattr(cfg, "gateway", None), "console", None)
                    console_port = (
                        (console_cfg.port if console_cfg else None)
                        or int(os.environ.get("CAFE_CONSOLE_PORT", "6688"))
                    )
                    console_host = (
                        (console_cfg.host if console_cfg else None)
                        or os.environ.get("CAFE_CONSOLE_HOST", "127.0.0.1")
                    )
                    validate_console_security(console_cfg, console_host)

                    # Get AgentLoop reference from loop_patch (set during __init__)
                    from ava.patches.loop_patch import get_agent_loop
                    agent_loop = get_agent_loop()

                    if agent_loop is not None:
                        # Full mode: direct AgentLoop access, chat API works
                        from ava.console.app import create_console_app
                        console_app = create_console_app(
                            nanobot_dir=nanobot_dir,
                            workspace=workspace,
                            agent_loop=agent_loop,
                            config=cfg,
                            token_stats_collector=getattr(agent_loop, "token_stats", None),
                            db=getattr(agent_loop, "db", None),
                        )
                        logger.info("Console starting in full mode (direct AgentLoop access)")
                    else:
                        # Fallback: standalone mode with HTTP proxy
                        from ava.console.app import create_console_app_standalone
                        gateway_port = getattr(cfg.gateway, "port", 18790)
                        secret_key = (
                            (console_cfg.secret_key if console_cfg else None)
                            or "change-me-in-production-use-a-longer-key!"
                        )
                        expire_minutes = (
                            (console_cfg.token_expire_minutes if console_cfg else None)
                            or 480
                        )
                        console_app = create_console_app_standalone(
                            nanobot_dir=nanobot_dir,
                            workspace=workspace,
                            gateway_port=gateway_port,
                            console_port=console_port,
                            secret_key=secret_key,
                            expire_minutes=expire_minutes,
                            session_cookie_name=(
                                (console_cfg.session_cookie_name if console_cfg else None)
                                or "ava_console_session"
                            ),
                            session_cookie_secure=bool(
                                (console_cfg.session_cookie_secure if console_cfg else False)
                            ),
                            session_cookie_samesite=(
                                (console_cfg.session_cookie_samesite if console_cfg else None)
                                or "lax"
                            ),
                            token_stats_dir=str(nanobot_dir),
                        )
                        logger.info("Console starting in standalone mode (HTTP proxy)")

                    uvicorn_config = uvicorn.Config(
                        console_app,
                        host=console_host,
                        port=console_port,
                        log_level="warning",
                    )
                    server = uvicorn.Server(uvicorn_config)
                    console_task = asyncio.create_task(server.serve())
                    logger.info(
                        "Web Console starting at http://{}:{}/", console_host, console_port
                    )
                    print(
                        f"☕ Web Console → http://localhost:{console_port}/"
                    )
                except Exception as exc:
                    logger.warning("Failed to start Web Console: {}", exc)

                try:
                    await coro
                finally:
                    if console_task and not console_task.done():
                        console_task.cancel()
                        try:
                            await console_task
                        except asyncio.CancelledError:
                            pass
                    # Clean up PID file
                    if pid_file and pid_file.exists():
                        try:
                            pid_file.unlink()
                        except OSError:
                            pass

            try:
                asyncio.run = original_asyncio_run  # restore before running
                return original_asyncio_run(_with_console(), **run_kwargs)
            finally:
                pass  # asyncio.run already restored

        asyncio.run = patched_asyncio_run
        try:
            original_callback(*args, **kwargs)
        finally:
            asyncio.run = original_asyncio_run  # ensure restore

    # Replace the callback in the CommandInfo (keep original name for Typer)
    gateway._ava_console_patched = True
    gateway_cmd.callback = gateway
    cli_mod.gateway = gateway

    return "gateway callback wrapped — Console will start alongside gateway"


register_patch("web_console", apply_console_patch)
