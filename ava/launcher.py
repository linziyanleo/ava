"""
Sidecar Launcher — the single entry point for all Monkey Patches.

Usage:
    python -m ava.launcher          # replaces `python -m nanobot`

This module:
1. Discovers and applies all registered patches under ava/patches
2. Then delegates to the original nanobot CLI entry point

Patches are discovered in lexical file order so early schema/config patches
can run before later runtime patches.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Callable

from loguru import logger

from ava.adapters.nanobot.discovery import ensure_nanobot_on_sys_path

# ---------------------------------------------------------------------------
# Patch registry — each patch is a callable that takes no args and returns
# a human-readable description of what it did.
# ---------------------------------------------------------------------------

_PATCHES: list[tuple[str, Callable[[], str]]] = []


def register_patch(name: str, apply_fn: Callable[[], str]) -> None:
    """Register a patch to be applied at launch time."""
    _PATCHES.append((name, apply_fn))


def _discover_patches() -> None:
    """Import all patch modules so they self-register via register_patch()."""
    ensure_nanobot_on_sys_path()
    patches_dir = Path(__file__).parent / "patches"
    for path in sorted(patches_dir.glob("*_patch.py")):
        module_name = f"ava.patches.{path.stem}"
        try:
            importlib.import_module(module_name)
        except Exception as exc:
            logger.warning("Failed to load patch {}: {}", module_name, exc)


def apply_all_patches() -> list[str]:
    """Discover and apply all Sidecar patches. Returns list of descriptions."""
    _discover_patches()
    results = []
    for name, apply_fn in _PATCHES:
        try:
            description = apply_fn()
            results.append(f"  ✓ {name}: {description}")
            logger.info("Patch applied: {} — {}", name, description)
        except Exception as exc:
            msg = f"  ✗ {name}: FAILED — {exc}"
            results.append(msg)
            logger.error("Patch failed: {} — {}", name, exc)
    return results


def main() -> None:
    """Apply patches then start nanobot."""
    nanobot_root = ensure_nanobot_on_sys_path()
    print("☕ Sidecar launching…")
    print(f"☕ Using nanobot checkout: {nanobot_root}")
    results = apply_all_patches()
    if results:
        print("☕ Patches applied:")
        for line in results:
            print(line)
    else:
        print("☕ No patches found — running vanilla nanobot.")
    print()

    # Delegate to the original nanobot CLI
    from nanobot.cli.commands import app
    app()


if __name__ == "__main__":
    main()
