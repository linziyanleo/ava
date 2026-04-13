"""Replace ``nanobot.config.schema`` with the sidecar fork early in startup."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from loguru import logger

from ava.adapters.nanobot.discovery import resolve_nanobot_checkout
from ava.launcher import register_patch


def _fork_module_is_healthy(module: ModuleType) -> bool:
    """Check whether an already-loaded fork is complete enough to reuse."""
    try:
        if "claude_code_model" in getattr(module.AgentDefaults, "model_fields", {}):
            return False
        if not hasattr(module, "DreamConfig"):
            return False

        dumped = module.Config().model_dump(mode="json", by_alias=True)
        defaults = dumped["agents"]["defaults"]
        if "visionModel" not in defaults:
            return False
        if module.WebSearchConfig().provider != "brave":
            return False

        validated = module.Config.model_validate({"gateway": {"console": {"enabled": False}}})
        return getattr(validated.gateway, "console", None) is not None
    except Exception:
        return False


def _load_upstream_schema_module() -> ModuleType:
    """Load a clean upstream schema module from disk for fork inheritance."""
    module_name = "_ava_upstream_config_schema"
    cached = sys.modules.get(module_name)
    if isinstance(cached, ModuleType) and hasattr(cached, "Base") and hasattr(cached, "Config"):
        return cached

    upstream_path = resolve_nanobot_checkout().schema_file
    spec = importlib.util.spec_from_file_location(module_name, upstream_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Upstream schema not found at {upstream_path}")

    upstream_mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = upstream_mod
    spec.loader.exec_module(upstream_mod)
    return upstream_mod


def _sync_schema_references(schema_mod: ModuleType) -> None:
    """Update already-imported modules to use the active schema module."""
    config_pkg = sys.modules.get("nanobot.config")
    if config_pkg is not None:
        config_pkg.schema = schema_mod
        if hasattr(schema_mod, "Config"):
            config_pkg.Config = schema_mod.Config

    loader_mod = sys.modules.get("nanobot.config.loader")
    if loader_mod is not None and hasattr(schema_mod, "Config"):
        loader_mod.Config = schema_mod.Config


def apply_schema_patch() -> str:
    """Replace ``nanobot.config.schema`` with the inherited ava fork."""
    fork_path = (Path(__file__).parent.parent / "forks" / "config" / "schema.py").resolve()
    current_schema = sys.modules.get("nanobot.config.schema")

    if getattr(current_schema, "_ava_fork", False):
        current_path = getattr(current_schema, "__file__", None)
        if current_path and Path(current_path).resolve() == fork_path and _fork_module_is_healthy(current_schema):
            _sync_schema_references(current_schema)
            return "schema already patched (skipped)"

    if isinstance(current_schema, ModuleType):
        current_path = getattr(current_schema, "__file__", None)
        if current_path and Path(current_path).resolve() == fork_path and _fork_module_is_healthy(current_schema):
            current_schema._ava_fork = True
            _sync_schema_references(current_schema)
            logger.info("Reused existing ava fork for nanobot.config.schema")
            return "nanobot.config.schema already points to ava fork (reused existing module)"

    try:
        if not fork_path.exists():
            return f"Fork schema not found at {fork_path} - skipped"

        if isinstance(current_schema, ModuleType) and not getattr(current_schema, "_ava_fork", False):
            upstream_schema = current_schema
        else:
            upstream_schema = _load_upstream_schema_module()

        spec = importlib.util.spec_from_file_location("nanobot.config.schema", fork_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Unable to load fork schema at {fork_path}")

        fork_mod = importlib.util.module_from_spec(spec)
        fork_mod._ava_fork = True
        fork_mod._ava_upstream_schema = upstream_schema

        # Register the fork before execution so forward refs bind to the fork.
        sys.modules["nanobot.config.schema"] = fork_mod

        try:
            spec.loader.exec_module(fork_mod)
        except Exception:
            if current_schema is not None:
                sys.modules["nanobot.config.schema"] = current_schema
            else:
                sys.modules.pop("nanobot.config.schema", None)
            raise

        sys.modules["nanobot.config.schema"] = fork_mod
        _sync_schema_references(fork_mod)

        logger.info("Replaced nanobot.config.schema with ava fork")
        return "nanobot.config.schema replaced with inherited ava fork (sidecar config extensions enabled)"
    except Exception as exc:
        logger.error("Failed to apply schema_patch: {}", exc)
        return f"schema_patch FAILED: {exc}"


register_patch("config_schema_fork", apply_schema_patch)
