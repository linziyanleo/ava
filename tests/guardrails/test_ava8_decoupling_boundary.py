"""AVA-8 guardrail for Nanobot references in common Ava surfaces."""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).parents[2]
AVA_ROOT = REPO_ROOT / "ava"
NANOBOT_RE = re.compile(r"nanobot|Nanobot")

EXCLUDED_PREFIXES = (
    Path("ava/adapters/nanobot"),
    Path("ava/agents/nanobot"),
    Path("ava/patches"),
    Path("ava/tools"),
    Path("ava/templates"),
    Path("ava/skills"),
)

COMPATIBILITY_PATH_PREFIXES = (
    Path("ava/cli"),
    Path("ava/launcher.py"),
    Path("ava/runtime"),
)

COMPATIBILITY_FILES = {
    Path("ava/__init__.py"),
    Path("ava/agents/__init__.py"),
    Path("ava/console/mock_bundle_runtime.py"),
}

COMPATIBILITY_LINE_PATTERNS = (
    # Upstream runtime bindings are expected until Nanobot is fully process-isolated.
    re.compile(r"\bfrom nanobot\."),
    re.compile(r"\bimport nanobot\."),
    re.compile(r"ava\.(adapters|agents)\.nanobot"),
    re.compile(r"resolve_nanobot_checkout"),
    # Nanobot is still a concrete adapter id and the default responder value.
    re.compile(r'"nanobot"\s*:\s*"nanobot"'),
    re.compile(r"nanobot_default"),
    re.compile(r'default=.*"nanobot"'),
    re.compile(r'== "nanobot"'),
    re.compile(r'return "nanobot"'),
    # Backward-compatible file names and schema aliases are part of the migration contract.
    re.compile(r"nanobot-config\.json"),
    re.compile(r"NanobotConfig"),
    re.compile(r"Config\(NanobotConfig\)"),
    re.compile(r"Nanobot agent"),
    re.compile(r"Nanobot-owned"),
    re.compile(r"Nanobot root config"),
    re.compile(r'"nanobot": .*resolve'),
    # Existing runtime data names must remain readable during migration.
    re.compile(r"\.nanobot"),
    re.compile(r"nanobot\.db"),
    re.compile(r"legacy .*nanobot|legacy nanobot", re.IGNORECASE),
    # Upstream skill fallback is an explicit three-source discovery contract.
    re.compile(r"nanobot/skills"),
    re.compile(r"upstream builtin"),
    # Public app factory kwargs still use this legacy name at call sites.
    re.compile(r"\bnanobot_dir\b"),
)


def _is_under(path: Path, prefix: Path) -> bool:
    return path == prefix or prefix in path.parents


def _is_compatibility_path(rel_path: Path) -> bool:
    if rel_path in COMPATIBILITY_FILES:
        return True
    return any(_is_under(rel_path, prefix) for prefix in COMPATIBILITY_PATH_PREFIXES)


def _is_excluded_path(rel_path: Path) -> bool:
    return any(_is_under(rel_path, prefix) for prefix in EXCLUDED_PREFIXES)


def test_ava8_common_surface_nanobot_references_are_classified() -> None:
    unclassified: list[str] = []

    for path in sorted(AVA_ROOT.rglob("*.py")):
        rel_path = path.relative_to(REPO_ROOT)
        if "__pycache__" in rel_path.parts or _is_excluded_path(rel_path):
            continue
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not NANOBOT_RE.search(line):
                continue
            if _is_compatibility_path(rel_path):
                continue
            if any(pattern.search(line) for pattern in COMPATIBILITY_LINE_PATTERNS):
                continue
            unclassified.append(f"{rel_path}:{line_no}: {line.strip()}")

    assert unclassified == []
