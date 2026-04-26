"""Ava runtime path helpers."""

from __future__ import annotations

import os
from pathlib import Path


def _resolve(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _ensure_file_parent(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _dir_under_home(*parts: str) -> Path:
    return _ensure_dir(get_ava_home().joinpath(*parts))


def _file_under_home(*parts: str) -> Path:
    return _ensure_file_parent(get_ava_home().joinpath(*parts))


def resolve_legacy_home() -> Path:
    return _resolve(Path.home() / ".nanobot")


def resolve_ava_home() -> Path:
    raw = os.environ.get("AVA_HOME")
    if raw:
        return _resolve(Path(raw))
    return _resolve(Path.home() / ".ava")


def get_ava_home() -> Path:
    return _ensure_dir(resolve_ava_home())


def get_config_path() -> Path:
    return _file_under_home("config.json")


def get_extra_config_path() -> Path:
    return _file_under_home("extra_config.json")


def get_data_dir() -> Path:
    return get_ava_home()


def get_db_path() -> Path:
    return _file_under_home("nanobot.db")


def get_runtime_dir() -> Path:
    return _dir_under_home("runtime")


def get_state_file() -> Path:
    return _ensure_file_parent(get_runtime_dir() / "state.json")


def get_console_meta_file() -> Path:
    return _file_under_home("console.json")


def get_pid_file() -> Path:
    return _file_under_home("gateway.pid")


def get_sticker_config_path() -> Path:
    return _file_under_home("sticker.json")


def get_media_root_dir() -> Path:
    return _dir_under_home("media")


def get_generated_media_dir() -> Path:
    return _dir_under_home("media", "generated")


def get_screenshot_dir() -> Path:
    return _dir_under_home("media", "screenshots")


def get_chat_upload_dir() -> Path:
    return _dir_under_home("media", "chat-uploads")


def get_workspace_path(override: str | Path | None = None) -> Path:
    if override is not None:
        return _ensure_dir(_resolve(Path(override)))
    return _dir_under_home("workspace")


def is_default_workspace(workspace: str | Path | None) -> bool:
    current = get_workspace_path(workspace) if workspace is not None else get_workspace_path()
    default = _resolve(resolve_ava_home() / "workspace")
    return current.resolve(strict=False) == default


def get_history_dir() -> Path:
    return _dir_under_home("history")


def get_cli_history_path() -> Path:
    return _ensure_file_parent(get_history_dir() / "cli_history")


def get_bridge_install_dir() -> Path:
    return _dir_under_home("bridge")


def get_legacy_sessions_dir() -> Path:
    return _dir_under_home("sessions")


def get_cron_dir() -> Path:
    return _dir_under_home("cron")


def get_logs_dir() -> Path:
    return _dir_under_home("logs")


def get_page_agent_dir() -> Path:
    return _dir_under_home("page-agent")


def get_tasks_dir() -> Path:
    return _dir_under_home("tasks")


def get_console_dir() -> Path:
    return _dir_under_home("console")


def get_certs_dir() -> Path:
    return _dir_under_home("certs")
