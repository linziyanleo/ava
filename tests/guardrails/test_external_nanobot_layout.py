"""Guardrails for the extracted repo layout."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).parents[2]


def test_repo_does_not_track_embedded_nanobot_checkout() -> None:
    assert not (REPO_ROOT / "nanobot" / "__main__.py").exists()
    assert not (REPO_ROOT / "nanobot" / "cli" / "commands.py").exists()


def test_start_script_exists_and_uses_external_nanobot_root() -> None:
    script = REPO_ROOT / "scripts" / "start-ava.sh"
    assert script.exists(), "scripts/start-ava.sh not found"

    content = script.read_text(encoding="utf-8")
    assert "AVA_NANOBOT_ROOT" in content
    assert "../nanobot" in content
    assert "-m ava" in content
