"""Launcher bootstrap helpers for home migration."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Sequence

from ava.runtime import paths as runtime_paths


_TOP_LEVEL_OPTS_WITH_VALUE = frozenset({"-m", "--model"})
_TRUTHY_VALUES = frozenset({"1", "true", "yes", "on"})
_BOOTSTRAP_ARGS: "BootstrapArgs | None" = None


@dataclass(frozen=True)
class BootstrapArgs:
    argv: list[str]
    subcommand: str | None
    legacy_home: bool


def preparse_argv(argv: Sequence[str]) -> BootstrapArgs:
    out: list[str] = []
    subcommand: str | None = None
    legacy_home = False
    i = 0

    while i < len(argv):
        token = argv[i]

        if token == "--":
            out.extend(argv[i:])
            break

        if token == "--legacy-home":
            legacy_home = True
            i += 1
            continue

        if subcommand is None and token in _TOP_LEVEL_OPTS_WITH_VALUE:
            out.append(token)
            if i + 1 < len(argv):
                out.append(argv[i + 1])
                i += 2
            else:
                i += 1
            continue

        if subcommand is None and (token.startswith("-m=") or token.startswith("--model=")):
            out.append(token)
            i += 1
            continue

        if subcommand is None and not token.startswith("-"):
            subcommand = token

        out.append(token)
        i += 1

    return BootstrapArgs(argv=out, subcommand=subcommand, legacy_home=legacy_home)


def configure_bootstrap(argv: Sequence[str]) -> list[str]:
    global _BOOTSTRAP_ARGS

    parsed = preparse_argv(argv)
    env_legacy = os.environ.get("AVA_LEGACY_HOME", "").strip().lower() in _TRUTHY_VALUES
    if parsed.legacy_home or env_legacy:
        os.environ["AVA_HOME"] = str(runtime_paths.resolve_legacy_home())
        parsed = BootstrapArgs(
            argv=parsed.argv,
            subcommand=parsed.subcommand,
            legacy_home=True,
        )

    _BOOTSTRAP_ARGS = parsed
    return list(parsed.argv)


def get_bootstrap_args() -> BootstrapArgs | None:
    return _BOOTSTRAP_ARGS


def should_skip_home_resolver_patch() -> bool:
    return _BOOTSTRAP_ARGS is not None and _BOOTSTRAP_ARGS.subcommand == "migrate-home"


def _uses_legacy_home() -> bool:
    current_home = runtime_paths.resolve_ava_home()
    legacy_home = runtime_paths.resolve_legacy_home()
    return current_home == legacy_home or (
        _BOOTSTRAP_ARGS is not None and _BOOTSTRAP_ARGS.legacy_home
    )


def enforce_home_migration_gate() -> None:
    if should_skip_home_resolver_patch() or _uses_legacy_home():
        return

    ava_home = runtime_paths.resolve_ava_home()
    legacy_home = runtime_paths.resolve_legacy_home()
    if ava_home.exists() or not legacy_home.exists():
        return

    print(
        "\n".join(
            [
                "Detected legacy Ava data home that still lives under nanobot.",
                f"Legacy home: {legacy_home}",
                f"New home: {ava_home}",
                "",
                "Run `ava migrate-home --dry-run` to preview the migration,",
                "then run `ava migrate-home` to copy data into the new home.",
                "If you need a temporary escape hatch, run the command again with",
                "`--legacy-home` or set `AVA_LEGACY_HOME=1`.",
            ]
        ),
        file=sys.stderr,
    )
    raise SystemExit(1)
