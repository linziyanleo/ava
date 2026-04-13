"""Locate and bootstrap the external nanobot checkout."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


_NANOBOT_ROOT_ENV = "AVA_NANOBOT_ROOT"


@dataclass(frozen=True)
class NanobotCheckout:
    """Resolved external nanobot checkout."""

    root: Path

    @property
    def package_dir(self) -> Path:
        return self.root / "nanobot"

    @property
    def skills_dir(self) -> Path:
        return self.package_dir / "skills"

    @property
    def templates_dir(self) -> Path:
        return self.package_dir / "templates"

    @property
    def schema_file(self) -> Path:
        return self.package_dir / "config" / "schema.py"

    @property
    def venv_python(self) -> Path | None:
        candidate = self.root / ".venv" / "bin" / "python"
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
        return None


def _project_root(project_root: Path | None = None) -> Path:
    if project_root is not None:
        return Path(project_root).expanduser().resolve()
    return Path(__file__).resolve().parents[3]


def _candidate_roots(project_root: Path | None = None, explicit_root: Path | str | None = None) -> Iterable[Path]:
    root = _project_root(project_root)
    seen: set[Path] = set()

    raw_candidates: list[Path] = []
    if explicit_root:
        raw_candidates.append(Path(explicit_root).expanduser())

    env_root = os.environ.get(_NANOBOT_ROOT_ENV)
    if env_root:
        raw_candidates.append(Path(env_root).expanduser())

    raw_candidates.extend(
        [
            root.parent / "nanobot",
            root / "vendor" / "nanobot",
        ]
    )

    for candidate in raw_candidates:
        resolved = candidate.resolve(strict=False)
        if resolved in seen:
            continue
        seen.add(resolved)
        yield resolved


def _is_nanobot_checkout(path: Path) -> bool:
    return (
        path.is_dir()
        and (path / "pyproject.toml").is_file()
        and (path / "nanobot" / "__main__.py").is_file()
        and (path / "nanobot" / "cli" / "commands.py").is_file()
    )


def resolve_nanobot_root(
    project_root: Path | None = None,
    explicit_root: Path | str | None = None,
) -> Path:
    """Resolve the external nanobot checkout root or raise a clear error."""

    checked: list[str] = []
    for candidate in _candidate_roots(project_root=project_root, explicit_root=explicit_root):
        checked.append(str(candidate))
        if _is_nanobot_checkout(candidate):
            return candidate

    detail = ", ".join(checked) if checked else "(no candidates)"
    raise RuntimeError(
        "Unable to locate a nanobot checkout. "
        f"Checked: {detail}. "
        f"Set {_NANOBOT_ROOT_ENV} to a full HKUDS/nanobot checkout."
    )


def resolve_nanobot_checkout(
    project_root: Path | None = None,
    explicit_root: Path | str | None = None,
) -> NanobotCheckout:
    return NanobotCheckout(resolve_nanobot_root(project_root=project_root, explicit_root=explicit_root))


def ensure_nanobot_on_sys_path(
    project_root: Path | None = None,
    explicit_root: Path | str | None = None,
) -> Path:
    """Ensure the external checkout root is importable."""

    root = resolve_nanobot_root(project_root=project_root, explicit_root=explicit_root)
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    return root
