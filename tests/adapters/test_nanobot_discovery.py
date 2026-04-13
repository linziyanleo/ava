from __future__ import annotations

import sys
from pathlib import Path

import pytest

from ava.adapters.nanobot.discovery import (
    ensure_nanobot_on_sys_path,
    resolve_nanobot_checkout,
    resolve_nanobot_root,
)


def _make_checkout(root: Path) -> Path:
    (root / "nanobot" / "cli").mkdir(parents=True)
    (root / "nanobot" / "__main__.py").write_text("from nanobot.cli.commands import app\n")
    (root / "nanobot" / "cli" / "commands.py").write_text("app = object()\n")
    (root / "nanobot" / "config").mkdir(parents=True)
    (root / "nanobot" / "config" / "schema.py").write_text("class Config: ...\nclass Base: ...\n")
    (root / "pyproject.toml").write_text("[project]\nname='nanobot-ai'\n")
    return root


def test_resolve_nanobot_root_prefers_explicit_path(tmp_path: Path):
    explicit = _make_checkout(tmp_path / "explicit")
    _make_checkout(tmp_path / "nanobot")

    resolved = resolve_nanobot_root(project_root=tmp_path / "ava", explicit_root=explicit)

    assert resolved == explicit.resolve()


def test_resolve_nanobot_root_uses_sibling_checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    project_root = tmp_path / "ava"
    project_root.mkdir()
    sibling = _make_checkout(tmp_path / "nanobot")
    monkeypatch.delenv("AVA_NANOBOT_ROOT", raising=False)

    resolved = resolve_nanobot_root(project_root=project_root)

    assert resolved == sibling.resolve()


def test_resolve_nanobot_checkout_exposes_schema_and_skills_paths(tmp_path: Path):
    checkout_root = _make_checkout(tmp_path / "nanobot")
    (checkout_root / "nanobot" / "skills").mkdir()
    (checkout_root / "nanobot" / "templates").mkdir()

    checkout = resolve_nanobot_checkout(explicit_root=checkout_root)

    assert checkout.schema_file == checkout_root / "nanobot" / "config" / "schema.py"
    assert checkout.skills_dir == checkout_root / "nanobot" / "skills"
    assert checkout.templates_dir == checkout_root / "nanobot" / "templates"


def test_ensure_nanobot_on_sys_path_inserts_checkout_root(tmp_path: Path):
    checkout_root = _make_checkout(tmp_path / "nanobot")

    ensure_nanobot_on_sys_path(explicit_root=checkout_root)

    assert str(checkout_root.resolve()) in sys.path


def test_resolve_nanobot_root_reports_checked_candidates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    project_root = tmp_path / "ava"
    project_root.mkdir()
    missing = tmp_path / "missing"
    monkeypatch.setenv("AVA_NANOBOT_ROOT", str(missing))

    with pytest.raises(RuntimeError) as exc_info:
        resolve_nanobot_root(project_root=project_root)

    message = str(exc_info.value)
    assert "AVA_NANOBOT_ROOT" in message
    assert str(missing.resolve()) in message
