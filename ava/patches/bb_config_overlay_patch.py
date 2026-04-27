"""Patch nanobot config loading to support Ava overlay config files."""

from __future__ import annotations

import json

import pydantic
from loguru import logger

from ava.launcher import register_patch
from ava.runtime import config_overlay

_PATCHED = False


def apply_config_overlay_patch() -> str:
    global _PATCHED

    import nanobot.config.loader as loader_mod

    if _PATCHED or getattr(loader_mod.load_config, "_ava_overlay_patch", False):
        return "config overlay already applied (skipped)"

    original_load_config = loader_mod.load_config
    def load_config(config_path=None):
        path = config_path or loader_mod.get_config_path()
        if not config_overlay.uses_overlay_config(path):
            return original_load_config(config_path)

        config = loader_mod.Config()
        data = config_overlay.load_effective_config_data(path)
        if data:
            try:
                migrated = loader_mod._migrate_config(data)
                config = loader_mod.Config.model_validate(migrated)
            except (json.JSONDecodeError, ValueError, pydantic.ValidationError) as exc:
                logger.warning("Failed to load merged Ava config from {}: {}", path, exc)
                logger.warning("Using default configuration.")

        loader_mod._apply_ssrf_whitelist(config)
        return config

    load_config._ava_overlay_patch = True
    loader_mod.load_config = load_config
    _PATCHED = True
    return "load_config patched with Ava overlay merge"


register_patch("config_overlay", apply_config_overlay_patch)
