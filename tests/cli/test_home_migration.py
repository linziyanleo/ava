"""Tests for ava home migration helpers."""

from __future__ import annotations

import json
from pathlib import Path


def test_migrate_home_dry_run_reports_extra_config_without_creating_target(tmp_path: Path):
    from ava.cli.commands import migrate_home

    source = tmp_path / "legacy-home"
    target = tmp_path / "ava-home"
    source.mkdir(parents=True)
    (source / "config.json").write_text("{}", "utf-8")
    (source / "extra_config.json").write_text('{"tools": {"web": {"proxy": "http://proxy"}}}', "utf-8")

    lines = migrate_home(source_home=source, target_home=target, mode="copy", dry_run=True)

    assert any("extra_config.json" in line for line in lines)
    assert not target.exists()


def test_migrate_home_copy_copies_workspace_and_extra_config(tmp_path: Path):
    from ava.cli.commands import migrate_home

    source = tmp_path / "legacy-home"
    target = tmp_path / "ava-home"
    workspace = source / "workspace"
    workspace.mkdir(parents=True)
    (workspace / "note.txt").write_text("hello", "utf-8")
    (source / "extra_config.json").write_text('{"x": 1}', "utf-8")

    migrate_home(source_home=source, target_home=target, mode="copy", dry_run=False)

    assert (target / "workspace" / "note.txt").read_text("utf-8") == "hello"
    assert (target / "extra_config.json").read_text("utf-8") == '{"x": 1}'
    assert (source / "workspace" / "note.txt").exists()


def test_migrate_home_normalizes_active_ava_config_overlay(monkeypatch, tmp_path: Path):
    from ava.cli.commands import migrate_home

    fake_home = tmp_path / "home"
    source = fake_home / ".nanobot"
    target = fake_home / ".ava"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setenv("AVA_HOME", str(target))

    source.mkdir(parents=True)
    (source / "config.json").write_text(
        json.dumps(
            {
                "agents": {"defaults": {"model": "anthropic/base-model"}},
                "providers": {"openai": {"apiKey": "legacy-key"}},
            }
        ),
        "utf-8",
    )
    (source / "extra_config.json").write_text(
        json.dumps({"tools": {"claudeCode": {"model": "claude-opus-4-6"}}}),
        "utf-8",
    )

    lines = migrate_home(source_home=source, target_home=target, mode="copy", dry_run=False)
    saved = json.loads((target / "config.json").read_text("utf-8"))

    assert any("normalized: config.json rewritten as Ava overlay" in line for line in lines)
    assert saved == {}
