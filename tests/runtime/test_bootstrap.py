"""Tests for ava.runtime.bootstrap."""

from __future__ import annotations

import os
from pathlib import Path

import pytest


def test_preparse_argv_skips_model_flag_value():
    from ava.runtime.bootstrap import preparse_argv

    parsed = preparse_argv(["-m", "gpt-5", "migrate-home", "--dry-run"])

    assert parsed.argv == ["-m", "gpt-5", "migrate-home", "--dry-run"]
    assert parsed.subcommand == "migrate-home"
    assert parsed.legacy_home is False


def test_preparse_argv_strips_legacy_flag_but_preserves_double_dash_payload():
    from ava.runtime.bootstrap import preparse_argv

    parsed = preparse_argv(["--legacy-home", "gateway", "--", "--legacy-home"])

    assert parsed.argv == ["gateway", "--", "--legacy-home"]
    assert parsed.subcommand == "gateway"
    assert parsed.legacy_home is True


def test_configure_bootstrap_sets_legacy_home_env(monkeypatch, tmp_path: Path):
    from ava.runtime.bootstrap import configure_bootstrap

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.delenv("AVA_HOME", raising=False)

    rewritten = configure_bootstrap(["--legacy-home", "gateway"])

    assert rewritten == ["gateway"]
    assert Path(os.environ["AVA_HOME"]).resolve(strict=False) == (
        fake_home / ".nanobot"
    ).resolve(strict=False)


def test_gate_fails_closed_when_only_legacy_home_exists(monkeypatch, tmp_path: Path, capsys):
    from ava.runtime.bootstrap import configure_bootstrap, enforce_home_migration_gate

    fake_home = tmp_path / "home"
    legacy_home = fake_home / ".nanobot"
    fake_home.mkdir()
    legacy_home.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.delenv("AVA_HOME", raising=False)
    monkeypatch.delenv("AVA_LEGACY_HOME", raising=False)

    configure_bootstrap(["gateway"])

    with pytest.raises(SystemExit) as exc_info:
        enforce_home_migration_gate()

    captured = capsys.readouterr()
    assert exc_info.value.code == 1
    assert "ava migrate-home" in captured.err
    assert str(fake_home / ".ava") in captured.err


def test_gate_allows_migrate_home_and_fresh_install(monkeypatch, tmp_path: Path):
    from ava.runtime.bootstrap import configure_bootstrap, enforce_home_migration_gate

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.delenv("AVA_HOME", raising=False)
    monkeypatch.delenv("AVA_LEGACY_HOME", raising=False)

    configure_bootstrap(["migrate-home", "--dry-run"])
    enforce_home_migration_gate()

    configure_bootstrap(["gateway"])
    enforce_home_migration_gate()
