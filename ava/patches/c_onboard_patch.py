"""Monkey patch `nanobot onboard` 的 refresh 分支，保留旧 sidecar 配置形状。

拦截点: Typer `onboard` 命令 callback
修改行为:
  - 仅在「已有 config + 非 wizard + 选择 N(refresh)」路径上生效
  - 写回时保留原始 config.json 中的既有字段和值，只补当前 schema 缺失的默认字段
  - 避免把 extra_config.json 的 overlay 值直接固化回 config.json
"""

from __future__ import annotations

import copy
import functools
import inspect
import json
from pathlib import Path
from typing import Any

from loguru import logger

from ava.launcher import register_patch


_NO_CHANGE = object()


def _merge_missing_defaults(existing: Any, defaults: Any) -> Any:
    """保留现有值，仅补齐缺失字段。"""
    if not isinstance(existing, dict) or not isinstance(defaults, dict):
        return existing

    merged = dict(existing)
    for key, value in defaults.items():
        if key not in merged:
            merged[key] = value
        else:
            merged[key] = _merge_missing_defaults(merged[key], value)
    return merged


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)


def _collect_changes(original: Any, updated: Any) -> Any:
    """收集 updated 相对 original 的变化，不做删除。"""
    if isinstance(original, dict) and isinstance(updated, dict):
        changes: dict[str, Any] = {}
        for key in updated:
            if key not in original:
                changes[key] = updated[key]
                continue

            nested = _collect_changes(original[key], updated[key])
            if nested is not _NO_CHANGE:
                changes[key] = nested
        return changes or _NO_CHANGE

    if original == updated:
        return _NO_CHANGE
    return updated


def _apply_changes(base: Any, changes: Any) -> Any:
    """把差异写回原始 base 结构。"""
    if changes is _NO_CHANGE:
        return copy.deepcopy(base)

    if not isinstance(base, dict) or not isinstance(changes, dict):
        return copy.deepcopy(changes)

    merged = copy.deepcopy(base)
    for key, value in changes.items():
        merged[key] = _apply_changes(merged.get(key), value)
    return merged


def _refresh_config_preserving_existing_shape(config_path: Path, workspace: str | None = None) -> None:
    """基于当前 base config 生成补齐后的结构，但不收缩旧 sidecar 字段。"""
    import nanobot.config.loader as loader_mod

    try:
        with open(config_path, encoding="utf-8") as file:
            existing = json.load(file)
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        logger.warning("onboard refresh fallback to vanilla save_config: {}", exc)
        return

    migrated = loader_mod._migrate_config(copy.deepcopy(existing))
    canonical = loader_mod.Config.model_validate(migrated).model_dump(mode="json", by_alias=True)
    merged = _merge_missing_defaults(existing, canonical)

    if workspace:
        agents = merged.setdefault("agents", {})
        defaults = agents.setdefault("defaults", {})
        defaults["workspace"] = workspace

    _write_json(config_path, merged)


def _save_wizard_result_preserving_existing_shape(
    config_path: Path,
    original_effective: Any,
    updated_effective: Any,
    workspace: str | None = None,
) -> None:
    """wizard 保存时保留 base config 形状，且不把 extra_config overlay 固化回 config.json。"""
    import nanobot.config.loader as loader_mod

    try:
        with open(config_path, encoding="utf-8") as file:
            existing = json.load(file)
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        logger.warning("wizard save fallback to vanilla save_config: {}", exc)
        loader_mod.save_config(updated_effective, config_path)
        return

    migrated = loader_mod._migrate_config(copy.deepcopy(existing))
    defaults = loader_mod.Config.model_validate(migrated).model_dump(mode="json", by_alias=True)
    merged = _merge_missing_defaults(existing, defaults)

    original_dump = original_effective.model_dump(mode="json", by_alias=True)
    updated_dump = updated_effective.model_dump(mode="json", by_alias=True)
    changes = _collect_changes(original_dump, updated_dump)
    saved = _apply_changes(merged, changes)

    if workspace:
        agents = saved.setdefault("agents", {})
        defaults_block = agents.setdefault("defaults", {})
        defaults_block["workspace"] = workspace

    _write_json(config_path, saved)


def apply_onboard_patch() -> str:
    import nanobot.cli.commands as cli_mod

    onboard_cmd = None
    for cmd_info in cli_mod.app.registered_commands:
        callback = getattr(cmd_info, "callback", None)
        if callback and callback.__name__ == "onboard":
            onboard_cmd = cmd_info
            break

    if onboard_cmd is None:
        logger.warning("onboard command not found in Typer app — onboard patch skipped")
        return "onboard patch skipped (command not found)"

    if getattr(onboard_cmd.callback, "_ava_onboard_patched", False):
        return "onboard_patch already applied (skipped)"

    original_callback = onboard_cmd.callback
    signature = inspect.signature(original_callback)

    @functools.wraps(original_callback)
    def onboard(*args, **kwargs) -> None:
        bound = signature.bind_partial(*args, **kwargs)
        bound.apply_defaults()

        workspace = bound.arguments.get("workspace")
        config_arg = bound.arguments.get("config")
        wizard = bound.arguments.get("wizard", False)

        import typer
        from nanobot import __logo__
        from nanobot.config.loader import get_config_path, load_config, save_config, set_config_path
        from nanobot.config.schema import Config

        if config_arg:
            config_path = Path(config_arg).expanduser().resolve()
            set_config_path(config_path)
            cli_mod.console.print(f"[dim]Using config: {config_path}[/dim]")
        else:
            config_path = get_config_path()

        def _apply_workspace_override(loaded: Config) -> Config:
            if workspace:
                loaded.agents.defaults.workspace = workspace
            return loaded

        if wizard:
            from nanobot.cli.onboard import run_onboard

            if config_path.exists():
                config_obj = _apply_workspace_override(load_config(config_path))
            else:
                config_obj = _apply_workspace_override(Config())

            original_config = config_obj.model_copy(deep=True)

            try:
                result = run_onboard(initial_config=config_obj)
                if not result.should_save:
                    cli_mod.console.print("[yellow]Configuration discarded. No changes were saved.[/yellow]")
                    return

                config_obj = result.config
                if config_path.exists():
                    _save_wizard_result_preserving_existing_shape(
                        config_path,
                        original_effective=original_config,
                        updated_effective=config_obj,
                        workspace=workspace,
                    )
                else:
                    save_config(config_obj, config_path)

                cli_mod.console.print(f"[green]✓[/green] Config saved at {config_path}")
            except Exception as exc:
                cli_mod.console.print(f"[red]✗[/red] Error during configuration: {exc}")
                cli_mod.console.print("[yellow]Please run 'python -m ava onboard' again to complete setup.[/yellow]")
                raise typer.Exit(1)

            cli_mod._onboard_plugins(config_path)

            workspace_path = cli_mod.get_workspace_path(config_obj.workspace_path)
            if not workspace_path.exists():
                workspace_path.mkdir(parents=True, exist_ok=True)
                cli_mod.console.print(f"[green]✓[/green] Created workspace at {workspace_path}")

            cli_mod.sync_workspace_templates(workspace_path)

            agent_cmd = 'python -m ava agent -m "Hello!"'
            gateway_cmd = "python -m ava gateway"
            if config_arg:
                agent_cmd += f" --config {config_path}"
                gateway_cmd += f" --config {config_path}"

            cli_mod.console.print(f"\n{__logo__} nanobot is ready!")
            cli_mod.console.print("\nNext steps:")
            cli_mod.console.print(f"  1. Chat: [cyan]{agent_cmd}[/cyan]")
            cli_mod.console.print(f"  2. Start gateway: [cyan]{gateway_cmd}[/cyan]")
            cli_mod.console.print("\n[dim]Want Telegram/WhatsApp? See: https://github.com/HKUDS/nanobot#-chat-apps[/dim]")
            return

        if config_path.exists():
            cli_mod.console.print(f"[yellow]Config already exists at {config_path}[/yellow]")
            cli_mod.console.print("  [bold]y[/bold] = overwrite with defaults (existing values will be lost)")
            cli_mod.console.print("  [bold]N[/bold] = refresh config, keeping existing values and adding new fields")

            if typer.confirm("Overwrite?"):
                config_obj = _apply_workspace_override(Config())
                save_config(config_obj, config_path)
                cli_mod.console.print(f"[green]✓[/green] Config reset to defaults at {config_path}")
            else:
                config_obj = _apply_workspace_override(load_config(config_path))
                _refresh_config_preserving_existing_shape(config_path, workspace)
                cli_mod.console.print(
                    f"[green]✓[/green] Config refreshed at {config_path} (existing values preserved)"
                )
        else:
            config_obj = _apply_workspace_override(Config())
            save_config(config_obj, config_path)
            cli_mod.console.print(f"[green]✓[/green] Created config at {config_path}")

        cli_mod._onboard_plugins(config_path)

        workspace_path = cli_mod.get_workspace_path(config_obj.workspace_path)
        if not workspace_path.exists():
            workspace_path.mkdir(parents=True, exist_ok=True)
            cli_mod.console.print(f"[green]✓[/green] Created workspace at {workspace_path}")

        cli_mod.sync_workspace_templates(workspace_path)

        agent_cmd = 'python -m ava agent -m "Hello!"'
        gateway_cmd = "python -m ava gateway"
        if config_arg:
            agent_cmd += f" --config {config_path}"
            gateway_cmd += f" --config {config_path}"

        cli_mod.console.print(f"\n{__logo__} nanobot is ready!")
        cli_mod.console.print("\nNext steps:")
        cli_mod.console.print(f"  1. Add your API key to [cyan]{config_path}[/cyan]")
        cli_mod.console.print("     Get one at: https://openrouter.ai/keys")
        cli_mod.console.print(f"  2. Chat: [cyan]{agent_cmd}[/cyan]")
        cli_mod.console.print("\n[dim]Want Telegram/WhatsApp? See: https://github.com/HKUDS/nanobot#-chat-apps[/dim]")

    onboard._ava_onboard_patched = True
    onboard_cmd.callback = onboard
    cli_mod.onboard = onboard

    return "onboard callback wrapped — refresh preserves existing sidecar config shape"


register_patch("onboard_refresh_compat", apply_onboard_patch)
