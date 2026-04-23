"""Tests for ava.runtime.paths."""

from __future__ import annotations

from pathlib import Path


def test_resolve_ava_home_defaults_to_dot_ava(monkeypatch, tmp_path: Path):
    from ava.runtime import paths

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.delenv("AVA_HOME", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

    resolved = paths.resolve_ava_home()

    assert resolved == (fake_home / ".ava").resolve(strict=False)
    assert not resolved.exists()


def test_resolve_ava_home_honors_env_without_creating_dir(monkeypatch, tmp_path: Path):
    from ava.runtime import paths

    target = tmp_path / "custom-home"
    monkeypatch.setenv("AVA_HOME", str(target))

    resolved = paths.resolve_ava_home()

    assert resolved == target.resolve(strict=False)
    assert not target.exists()


def test_runtime_path_helpers_create_expected_directories(monkeypatch, tmp_path: Path):
    from ava.runtime import paths

    target = tmp_path / "ava-home"
    monkeypatch.setenv("AVA_HOME", str(target))

    runtime_dir = paths.get_runtime_dir()
    generated_dir = paths.get_generated_media_dir()
    screenshot_dir = paths.get_screenshot_dir()
    chat_upload_dir = paths.get_chat_upload_dir()

    assert runtime_dir == target / "runtime"
    assert runtime_dir.is_dir()
    assert generated_dir == target / "media" / "generated"
    assert generated_dir.is_dir()
    assert screenshot_dir == target / "media" / "screenshots"
    assert screenshot_dir.is_dir()
    assert chat_upload_dir == target / "media" / "chat-uploads"
    assert chat_upload_dir.is_dir()
    assert paths.get_pid_file() == target / "gateway.pid"
    assert paths.get_console_meta_file() == target / "console.json"
    assert paths.get_extra_config_path() == target / "extra_config.json"


def test_workspace_helpers_follow_ava_home_by_default(monkeypatch, tmp_path: Path):
    from ava.runtime import paths

    target = tmp_path / "ava-home"
    monkeypatch.setenv("AVA_HOME", str(target))

    workspace = paths.get_workspace_path()

    assert workspace == target / "workspace"
    assert workspace.is_dir()
    assert paths.is_default_workspace(None) is True
    assert paths.is_default_workspace(workspace) is True
    assert paths.is_default_workspace(tmp_path / "other-workspace") is False
