"""Tests for _0_home_resolver_patch."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _restore_home_resolver_state(monkeypatch):
    import ava.runtime.bootstrap as bootstrap
    import nanobot.config.loader as loader
    import nanobot.config.paths as upstream_paths

    original_attrs = {
        name: getattr(upstream_paths, name)
        for name in (
            "get_data_dir",
            "get_workspace_path",
            "is_default_workspace",
            "get_cli_history_path",
            "get_bridge_install_dir",
            "get_legacy_sessions_dir",
        )
    }
    monkeypatch.setattr(loader, "_current_config_path", None, raising=False)
    monkeypatch.setattr(bootstrap, "_BOOTSTRAP_ARGS", None, raising=False)

    yield

    monkeypatch.setattr(loader, "_current_config_path", None, raising=False)
    monkeypatch.setattr(bootstrap, "_BOOTSTRAP_ARGS", None, raising=False)
    for name, value in original_attrs.items():
        monkeypatch.setattr(upstream_paths, name, value, raising=False)

    patch_mod = sys.modules.get("ava.patches._0_home_resolver_patch")
    if patch_mod is not None:
        monkeypatch.setattr(patch_mod, "_PATCHED", False, raising=False)
        importlib.reload(patch_mod)


def test_apply_sets_config_path_and_upstream_helpers(monkeypatch, tmp_path: Path):
    from ava.runtime.bootstrap import configure_bootstrap
    from ava.patches._0_home_resolver_patch import apply_home_resolver_patch
    import nanobot.config.paths as upstream_paths
    from nanobot.config.loader import get_config_path

    ava_home = tmp_path / "ava-home"
    monkeypatch.setenv("AVA_HOME", str(ava_home))
    configure_bootstrap(["gateway"])

    result = apply_home_resolver_patch()

    assert "ava-home" in result
    assert get_config_path() == ava_home / "config.json"
    assert upstream_paths.get_data_dir() == ava_home
    assert upstream_paths.get_workspace_path() == ava_home / "workspace"
    assert upstream_paths.is_default_workspace(None) is True
    assert upstream_paths.get_cli_history_path() == ava_home / "history" / "cli_history"
    assert upstream_paths.get_bridge_install_dir() == ava_home / "bridge"
    assert upstream_paths.get_legacy_sessions_dir() == ava_home / "sessions"


def test_apply_skips_during_migrate_home_bypass(monkeypatch, tmp_path: Path):
    from ava.runtime.bootstrap import configure_bootstrap
    from ava.patches._0_home_resolver_patch import apply_home_resolver_patch
    from nanobot.config.loader import get_config_path

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    configure_bootstrap(["migrate-home", "--dry-run"])

    result = apply_home_resolver_patch()

    assert "skip" in result.lower()
    assert get_config_path() == fake_home / ".nanobot" / "config.json"
    assert not (fake_home / ".ava").exists()
