"""
Sidecar Launcher — the single entry point for all Monkey Patches.

Usage:
    python -m ava              # replaces `python -m nanobot`
    ava gateway                # installed console_script entry (pyproject.toml)

This module:
1. Normalises ava's CLI syntax sugar (``start``, ``-help``, ``-m``, ``-v``).
2. Discovers and applies all registered patches under ava/patches.
3. Registers ava-specific commands (``console``/``console-status``/...).
4. Delegates to the original nanobot CLI Typer ``app``.

Patches are discovered in lexical file order so early schema/config patches
can run before later runtime patches.
"""

from __future__ import annotations

import importlib
import os
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


# ---------------------------------------------------------------------------
# argv rewriting for ava-flavoured CLI syntax
# ---------------------------------------------------------------------------

_START_ALIAS = "start"
_START_TARGET = "gateway"
_VERSION_FLAGS = frozenset({"-v", "-version", "--version"})
_MODEL_FLAGS = frozenset({"-m", "--model"})


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


def _print_version_and_exit() -> None:
    try:
        from ava import __version__ as ava_version
    except Exception:
        ava_version = "unknown"
    nanobot_version = "unknown"
    try:
        ensure_nanobot_on_sys_path()
        from nanobot import __version__ as nanobot_version  # type: ignore[no-redef]
    except Exception:
        pass
    print(f"ava {ava_version} (nanobot {nanobot_version})")
    sys.exit(0)


def _normalize_argv(argv: list[str]) -> tuple[list[str], bool]:
    """Rewrite ava-flavoured CLI syntax before Typer parses argv.

    Transforms (reason — how it differs from nanobot):
      ``start``            → ``gateway``   (ava alias for launching the gateway)
      ``-help``            → ``--help``    (single-dash help is ava-only;
                                            ``-h``/``--help`` already work upstream)
      ``-v`` / ``-version``/``--version`` at top level
                           → print ``ava <v> (nanobot <v>)`` and exit.
                           (nanobot's own ``-v``/``--version`` only prints
                           nanobot's version — ava wraps it.)
      ``-m``/``--model`` ``<model>`` at top level
                           → ``os.environ["AVA_MODEL"] = <model>``;
                           flag removed before handing off to nanobot.

    ``-v``/``-m`` inside a subcommand (e.g. ``ava gateway -v``) is **not**
    rewritten, so ``gateway``'s own ``--verbose`` short flag keeps working.

    Returns ``(rewritten_argv, wants_version)``.
    """
    out: list[str] = []
    wants_version = False
    subcommand_seen = False
    i = 0
    while i < len(argv):
        token = argv[i]

        # -help is an ava alias for --help, usable anywhere.
        if token == "-help":
            out.append("--help")
            i += 1
            continue

        if not subcommand_seen:
            if token in _VERSION_FLAGS:
                wants_version = True
                i += 1
                continue

            if token in _MODEL_FLAGS:
                if i + 1 < len(argv):
                    os.environ["AVA_MODEL"] = argv[i + 1]
                    i += 2
                else:
                    i += 1
                continue

            if token.startswith("-m=") or token.startswith("--model="):
                os.environ["AVA_MODEL"] = token.split("=", 1)[1]
                i += 1
                continue

            if not token.startswith("-"):
                subcommand_seen = True
                if token == _START_ALIAS:
                    out.append(_START_TARGET)
                    i += 1
                    continue

        out.append(token)
        i += 1

    return out, wants_version


def main() -> None:
    """Normalise argv, apply patches, register ava commands, start nanobot."""
    argv, wants_version = _normalize_argv(sys.argv[1:])
    if wants_version:
        _print_version_and_exit()
    sys.argv = [sys.argv[0], *argv]

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

    # Delegate to the original nanobot CLI, layering our extra commands on top.
    from nanobot.cli.commands import app

    try:
        from ava.cli.commands import register_cli_commands

        register_cli_commands(app)
    except Exception as exc:
        logger.warning("Failed to register ava CLI commands: {}", exc)

    app()


if __name__ == "__main__":
    main()
