"""Managed workspace / worktree lifecycle for coding background tasks.

Phase 1: ProjectTarget resolve + ExecutionWorkspace data model (inplace only).
Phase 2: WorktreeManager.ensure / cleanup / list_managed (worktree isolation).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class ProjectTarget:
    """Canonical identity of the user's intended modification target."""

    repo_root: str
    workdir_relpath: str
    requested_path: str
    workspace_key: str  # canonical identity = repo_root + ":" + relpath


@dataclass(frozen=True)
class ExecutionWorkspace:
    """Where a coding worker actually runs."""

    workspace_id: str
    workspace_key: str
    isolation_mode: Literal["inplace", "worktree"]
    repo_root: str
    workdir_relpath: str
    execution_cwd: str
    branch_name: str | None = None
    worktree_path: str | None = None


def resolve_target(raw_path: str) -> ProjectTarget:
    """Resolve a raw filesystem path into a canonical ProjectTarget.

    Uses `git rev-parse` to find repo root, then computes the relative
    working directory within that repo. Non-git directories fall back
    to using the path itself as both repo_root and workdir.
    """
    path = Path(raw_path).resolve()
    if not path.exists():
        raise ValueError(f"Path does not exist: {raw_path}")

    search_dir = path if path.is_dir() else path.parent

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(search_dir),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            repo_root = result.stdout.strip()
            try:
                relpath = str(path.relative_to(repo_root))
            except ValueError:
                relpath = "."
            if relpath == repo_root or relpath == ".":
                relpath = "."
        else:
            repo_root = str(search_dir)
            relpath = "."
    except (subprocess.TimeoutExpired, FileNotFoundError):
        repo_root = str(search_dir)
        relpath = "."

    workspace_key = f"{repo_root}:{relpath}"

    return ProjectTarget(
        repo_root=repo_root,
        workdir_relpath=relpath,
        requested_path=raw_path,
        workspace_key=workspace_key,
    )


def make_inplace_workspace(
    target: ProjectTarget,
    *,
    workspace_id: str,
) -> ExecutionWorkspace:
    """Create an inplace (non-isolated) workspace from a resolved target."""
    execution_cwd = (
        str(Path(target.repo_root) / target.workdir_relpath)
        if target.workdir_relpath != "."
        else target.repo_root
    )
    return ExecutionWorkspace(
        workspace_id=workspace_id,
        workspace_key=target.workspace_key,
        isolation_mode="inplace",
        repo_root=target.repo_root,
        workdir_relpath=target.workdir_relpath,
        execution_cwd=execution_cwd,
    )
