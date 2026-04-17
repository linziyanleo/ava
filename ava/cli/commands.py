"""Custom ava CLI commands layered on top of nanobot's Typer app.

Registered commands:
  ava console            Open the Web Console URL in the default browser.
  ava console-status     Show Web Console / gateway lifecycle status.
  ava console-restart    Signal the running gateway to restart only the Web Console.

`ava start` is handled by argv rewriting in `ava.launcher` (start → gateway),
not as a separate Typer command, to keep full argument compatibility with
nanobot's native `gateway` command.
"""

from __future__ import annotations

import json
import os
import signal
import socket
import sys
import webbrowser
from pathlib import Path
from typing import Any

import typer


_STATE_FILE = Path.home() / ".nanobot" / "runtime" / "state.json"
_CONSOLE_META_FILE = Path.home() / ".nanobot" / "console.json"
_PID_FILE = Path.home() / ".nanobot" / "gateway.pid"
_DEFAULT_CONSOLE_PORT = 6688
_DEFAULT_CONSOLE_HOST = "127.0.0.1"


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _read_state() -> dict[str, Any] | None:
    return _read_json(_STATE_FILE)


def _read_console_meta() -> dict[str, Any] | None:
    return _read_json(_CONSOLE_META_FILE)


def _read_pid() -> int | None:
    state = _read_state()
    if state and isinstance(state.get("pid"), int):
        return state["pid"]
    meta = _read_console_meta()
    if meta and isinstance(meta.get("pid"), int):
        return meta["pid"]
    try:
        return int(_PID_FILE.read_text().strip())
    except (OSError, ValueError):
        return None


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    except OSError:
        return False
    return True


def _resolve_console() -> tuple[str, int]:
    meta = _read_console_meta() or {}
    host = (
        meta.get("console_host")
        or os.environ.get("CAFE_CONSOLE_HOST")
        or _DEFAULT_CONSOLE_HOST
    )
    port = (
        meta.get("console_port")
        or os.environ.get("CAFE_CONSOLE_PORT")
        or _DEFAULT_CONSOLE_PORT
    )
    if host in ("0.0.0.0", "::"):
        host = "127.0.0.1"
    return host, int(port)


def _port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def register_cli_commands(app: typer.Typer) -> None:
    """Register ava-specific commands on the shared nanobot Typer app."""

    existing = {
        getattr(cmd.callback, "__name__", None)
        for cmd in getattr(app, "registered_commands", [])
    }

    if "ava_console" not in existing:

        @app.command(
            "console",
            help="Open the Web Console URL in the default browser.",
        )
        def ava_console(
            url_only: bool = typer.Option(
                False,
                "--url-only",
                help="Print the URL instead of opening a browser.",
            ),
        ) -> None:
            host, port = _resolve_console()
            url = f"http://{host}:{port}/"
            if url_only or not sys.stdout.isatty():
                typer.echo(url)
                return
            typer.echo(f"Opening {url} …")
            if not webbrowser.open(url):
                typer.echo("(no browser available — url printed above)")

    if "ava_console_status" not in existing:

        @app.command(
            "console-status",
            help="Show Web Console / gateway lifecycle status.",
        )
        def ava_console_status() -> None:
            state = _read_state() or {}
            pid = _read_pid()
            host, port = _resolve_console()
            running = pid is not None and _pid_alive(pid)
            reachable = _port_open(host, port) if running else False
            supervisor = state.get("supervisor") or (
                "supervised" if state.get("supervised") else "none"
            )
            typer.echo("Gateway:")
            typer.echo(f"  pid              : {pid if pid is not None else '—'}")
            typer.echo(f"  running          : {'yes' if running else 'no'}")
            typer.echo(f"  supervisor       : {supervisor}")
            typer.echo(f"  boot_generation  : {state.get('boot_generation', '—')}")
            typer.echo("Web Console:")
            typer.echo(f"  url              : http://{host}:{port}/")
            typer.echo(f"  reachable        : {'yes' if reachable else 'no'}")
            if not running:
                raise typer.Exit(1)

    if "ava_console_restart" not in existing:

        @app.command(
            "console-restart",
            help="Restart only the Web Console (uvicorn) inside the running gateway.",
        )
        def ava_console_restart() -> None:
            pid = _read_pid()
            if pid is None:
                typer.echo("Gateway is not running (no PID).")
                raise typer.Exit(1)
            if not _pid_alive(pid):
                typer.echo(f"Gateway PID {pid} is not alive.")
                raise typer.Exit(1)
            try:
                os.kill(pid, signal.SIGUSR1)
            except OSError as exc:
                typer.echo(f"Failed to signal gateway: {exc}")
                raise typer.Exit(1) from exc
            typer.echo(
                f"Signalled gateway (pid={pid}) — Web Console will restart shortly."
            )
