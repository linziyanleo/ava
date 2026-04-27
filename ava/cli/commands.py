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
import shutil
import signal
import socket
import sys
import webbrowser
from pathlib import Path
from typing import Any

import typer

from ava.runtime import config_overlay
from ava.runtime import paths as runtime_paths


_DEFAULT_CONSOLE_PORT = 6688
_DEFAULT_CONSOLE_HOST = "127.0.0.1"
_DRIFT_NOTICE_NAME = "DRIFT_NOTICE.txt"
_MIGRATION_ITEMS = (
    "config.json",
    "extra_config.json",
    "console.json",
    "sticker.json",
    "gateway.pid",
    "runtime",
    "media",
    "page-agent",
    "tasks",
    "console",
    "certs",
    "workspace",
    "bridge",
    "history",
    "cron",
    "logs",
    "sessions",
)


def _state_file() -> Path:
    return runtime_paths.get_state_file()


def _console_meta_file() -> Path:
    return runtime_paths.get_console_meta_file()


def _pid_file() -> Path:
    return runtime_paths.get_pid_file()


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _read_state() -> dict[str, Any] | None:
    return _read_json(_state_file())


def _read_console_meta() -> dict[str, Any] | None:
    return _read_json(_console_meta_file())


def _read_pid() -> int | None:
    state = _read_state()
    if state and isinstance(state.get("pid"), int):
        return state["pid"]
    meta = _read_console_meta()
    if meta and isinstance(meta.get("pid"), int):
        return meta["pid"]
    try:
        return int(_pid_file().read_text().strip())
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


def _iter_migration_paths(home: Path) -> list[Path]:
    entries: list[Path] = []
    seen: set[Path] = set()

    for item in _MIGRATION_ITEMS:
        path = home / item
        if path.exists() or path.is_symlink():
            resolved = path.resolve(strict=False)
            if resolved not in seen:
                seen.add(resolved)
                entries.append(path)

    for path in sorted(home.glob("nanobot.db*")):
        resolved = path.resolve(strict=False)
        if resolved in seen:
            continue
        seen.add(resolved)
        entries.append(path)

    return entries


def _remove_existing(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def _copy_entry(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.is_symlink():
        if target.exists() or target.is_symlink():
            _remove_existing(target)
        target.symlink_to(source.resolve(strict=False))
        return
    if source.is_dir():
        shutil.copytree(source, target, dirs_exist_ok=True)
        return
    shutil.copy2(source, target)


def _move_entry(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        _remove_existing(target)
    shutil.move(str(source), str(target))


def _symlink_entry(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        _remove_existing(target)
    target.symlink_to(source.resolve(strict=False), target_is_directory=source.is_dir())


def _write_drift_notice(target_home: Path, source_home: Path, mode: str) -> None:
    if mode not in {"copy", "symlink"}:
        return
    notice = target_home / _DRIFT_NOTICE_NAME
    notice.write_text(
        "\n".join(
            [
                "This Ava home was created from a legacy nanobot home.",
                f"Mode: {mode}",
                f"Legacy source: {source_home}",
                "Changes under the old and new homes can drift after migration.",
                "Prefer editing the new home and remove the old one only after verification.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def migrate_home(
    *,
    source_home: Path,
    target_home: Path,
    mode: str = "copy",
    dry_run: bool = False,
) -> list[str]:
    mode = mode.lower().strip()
    if mode not in {"copy", "move", "symlink"}:
        raise ValueError("mode must be one of: copy, move, symlink")

    entries = _iter_migration_paths(source_home)
    if not entries:
        return [f"No migration candidates found under {source_home}"]

    lines = [f"{mode.upper()} {source_home} -> {target_home}"]
    for source in entries:
        relative = source.relative_to(source_home)
        target = target_home / relative
        lines.append(f"{mode}: {relative}")
        if dry_run:
            continue
        if mode == "copy":
            _copy_entry(source, target)
        elif mode == "move":
            _move_entry(source, target)
        else:
            _symlink_entry(source, target)

    if not dry_run:
        if mode in {"copy", "move"} and target_home.resolve(strict=False) == runtime_paths.resolve_ava_home():
            overlay = config_overlay.normalize_config_overlay(target_home / "config.json")
            lines.append(
                f"normalized: config.json rewritten as Ava overlay ({len(overlay)} top-level key(s))"
            )
        _write_drift_notice(target_home, source_home, mode)
    return lines


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

    if "ava_migrate_home" not in existing:

        @app.command(
            "migrate-home",
            help="Migrate Ava runtime data from the legacy nanobot home to the new Ava home.",
        )
        def ava_migrate_home(
            mode: str = typer.Option(
                "copy",
                "--mode",
                help="Migration strategy: copy, move, or symlink.",
            ),
            dry_run: bool = typer.Option(
                False,
                "--dry-run",
                help="Preview migration operations without changing any files.",
            ),
            rollback: bool = typer.Option(
                False,
                "--rollback",
                help="Move data from the current Ava home back to the legacy nanobot home.",
            ),
        ) -> None:
            source_home = runtime_paths.resolve_legacy_home()
            target_home = runtime_paths.resolve_ava_home()
            if rollback:
                source_home, target_home = target_home, source_home
            lines = migrate_home(
                source_home=source_home,
                target_home=target_home,
                mode=mode,
                dry_run=dry_run,
            )
            for line in lines:
                typer.echo(line)
