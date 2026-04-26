"""Resolve Ava's runtime home before any later patches run."""

from __future__ import annotations

import sys
from types import ModuleType

from ava.launcher import register_patch
from ava.runtime import paths as runtime_paths
from ava.runtime.bootstrap import should_skip_home_resolver_patch

_PATCHED = False


def _patch_loaded_modules(replacements: dict[str, object]) -> None:
    for module in list(sys.modules.values()):
        if not isinstance(module, ModuleType):
            continue
        name = getattr(module, "__name__", "")
        if not name.startswith("nanobot"):
            continue
        for attr, value in replacements.items():
            if hasattr(module, attr):
                setattr(module, attr, value)


def apply_home_resolver_patch() -> str:
    global _PATCHED

    if should_skip_home_resolver_patch():
        return "home_resolver skipped for migrate-home"
    if _PATCHED:
        return "home_resolver already applied (skipped)"

    import nanobot.config.loader as loader
    import nanobot.config.paths as upstream_paths

    loader.set_config_path(runtime_paths.resolve_ava_home() / "config.json")

    replacements: dict[str, object] = {
        "get_data_dir": runtime_paths.get_data_dir,
        "get_workspace_path": runtime_paths.get_workspace_path,
        "is_default_workspace": runtime_paths.is_default_workspace,
        "get_cli_history_path": runtime_paths.get_cli_history_path,
        "get_bridge_install_dir": runtime_paths.get_bridge_install_dir,
        "get_legacy_sessions_dir": runtime_paths.get_legacy_sessions_dir,
    }
    for name, value in replacements.items():
        setattr(upstream_paths, name, value)

    _patch_loaded_modules(replacements)
    _PATCHED = True
    return f"home={runtime_paths.resolve_ava_home()}"


register_patch("home_resolver", apply_home_resolver_patch)
