from __future__ import annotations

from pathlib import Path

import pytest

from ava.agent.worktree_manager import (
    ProjectTarget,
    resolve_target,
    make_inplace_workspace,
)


def test_resolve_target_git_repo(tmp_path: Path):
    """resolve_target on a git repo should find repo_root and relpath."""
    import subprocess

    subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True, check=True)
    subdir = tmp_path / "src" / "app"
    subdir.mkdir(parents=True)

    target = resolve_target(str(subdir))

    assert target.repo_root == str(tmp_path)
    assert target.workdir_relpath == "src/app"
    assert target.requested_path == str(subdir)
    assert target.workspace_key == f"{tmp_path}:src/app"


def test_resolve_target_repo_root(tmp_path: Path):
    """resolve_target on repo root should have relpath='.'."""
    import subprocess

    subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True, check=True)

    target = resolve_target(str(tmp_path))

    assert target.repo_root == str(tmp_path)
    assert target.workdir_relpath == "."
    assert target.workspace_key == f"{tmp_path}:."


def test_resolve_target_non_git_dir(tmp_path: Path):
    """Non-git directories fall back to using the path as repo_root."""
    plain = tmp_path / "plain_project"
    plain.mkdir()

    target = resolve_target(str(plain))

    assert target.repo_root == str(plain)
    assert target.workdir_relpath == "."


def test_resolve_target_nonexistent_raises():
    with pytest.raises(ValueError, match="does not exist"):
        resolve_target("/nonexistent/path/foo/bar")


def test_make_inplace_workspace(tmp_path: Path):
    target = ProjectTarget(
        repo_root=str(tmp_path),
        workdir_relpath="subdir",
        requested_path=str(tmp_path / "subdir"),
        workspace_key=f"{tmp_path}:subdir",
    )
    ws = make_inplace_workspace(target, workspace_id="ws-1")

    assert ws.workspace_id == "ws-1"
    assert ws.isolation_mode == "inplace"
    assert ws.execution_cwd == str(tmp_path / "subdir")
    assert ws.workspace_key == f"{tmp_path}:subdir"
    assert ws.branch_name is None
    assert ws.worktree_path is None


def test_make_inplace_workspace_root(tmp_path: Path):
    target = ProjectTarget(
        repo_root=str(tmp_path),
        workdir_relpath=".",
        requested_path=str(tmp_path),
        workspace_key=f"{tmp_path}:.",
    )
    ws = make_inplace_workspace(target, workspace_id="ws-root")

    assert ws.execution_cwd == str(tmp_path)
