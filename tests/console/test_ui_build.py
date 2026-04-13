from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from ava.console.ui_build import (
    needs_console_ui_build,
    prepare_console_ui_dist,
    rebuild_console_ui,
    write_version_json,
)


def _write_file(path: Path, *, content: str = "x", mtime_ns: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    os.utime(path, ns=(mtime_ns, mtime_ns))


def test_prepare_console_ui_dist_skips_build_when_dist_is_fresh(tmp_path: Path):
    _write_file(tmp_path / "src" / "main.tsx", mtime_ns=100)
    _write_file(tmp_path / "package.json", mtime_ns=100)
    _write_file(tmp_path / "dist" / "index.html", mtime_ns=200)
    _write_file(tmp_path / "dist" / "assets" / "app.js", mtime_ns=200)

    build_calls: list[Path] = []
    dist_dir = prepare_console_ui_dist(tmp_path, build_runner=build_calls.append)

    assert needs_console_ui_build(tmp_path) is False
    assert dist_dir == tmp_path / "dist"
    assert build_calls == []


def test_prepare_console_ui_dist_builds_when_dist_is_missing(tmp_path: Path):
    _write_file(tmp_path / "src" / "main.tsx", mtime_ns=100)
    _write_file(tmp_path / "package.json", mtime_ns=100)

    build_calls: list[Path] = []

    def build_runner(root: Path) -> None:
        build_calls.append(root)
        _write_file(root / "dist" / "index.html", mtime_ns=300)
        _write_file(root / "dist" / "assets" / "app.js", mtime_ns=300)

    dist_dir = prepare_console_ui_dist(tmp_path, build_runner=build_runner)

    assert dist_dir == tmp_path / "dist"
    assert build_calls == [tmp_path]


def test_prepare_console_ui_dist_builds_when_source_is_newer(tmp_path: Path):
    _write_file(tmp_path / "src" / "main.tsx", mtime_ns=300)
    _write_file(tmp_path / "package.json", mtime_ns=300)
    _write_file(tmp_path / "dist" / "index.html", mtime_ns=200)
    _write_file(tmp_path / "dist" / "assets" / "app.js", mtime_ns=200)

    build_calls: list[Path] = []

    def build_runner(root: Path) -> None:
        build_calls.append(root)
        _write_file(root / "dist" / "index.html", mtime_ns=400)
        _write_file(root / "dist" / "assets" / "app.js", mtime_ns=400)

    assert needs_console_ui_build(tmp_path) is True

    dist_dir = prepare_console_ui_dist(tmp_path, build_runner=build_runner)

    assert dist_dir == tmp_path / "dist"
    assert build_calls == [tmp_path]


def test_prepare_console_ui_dist_returns_none_when_build_fails_without_dist(tmp_path: Path):
    _write_file(tmp_path / "src" / "main.tsx", mtime_ns=100)
    _write_file(tmp_path / "package.json", mtime_ns=100)

    def build_runner(_: Path) -> None:
        raise RuntimeError("boom")

    assert prepare_console_ui_dist(tmp_path, build_runner=build_runner) is None


def test_prepare_console_ui_dist_keeps_existing_dist_when_rebuild_fails(tmp_path: Path):
    _write_file(tmp_path / "src" / "main.tsx", mtime_ns=300)
    _write_file(tmp_path / "package.json", mtime_ns=300)
    _write_file(tmp_path / "dist" / "index.html", mtime_ns=200)
    _write_file(tmp_path / "dist" / "assets" / "app.js", mtime_ns=200)

    def build_runner(_: Path) -> None:
        raise RuntimeError("boom")

    assert prepare_console_ui_dist(tmp_path, build_runner=build_runner) == tmp_path / "dist"


# ---------------------------------------------------------------------------
# write_version_json
# ---------------------------------------------------------------------------

def test_write_version_json_creates_file(tmp_path: Path):
    dist = tmp_path / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (assets / "app.js").write_text("console.log('hi')")
    (assets / "style.css").write_text("body{}")

    h = write_version_json(dist)

    version_file = dist / "version.json"
    assert version_file.is_file()
    data = json.loads(version_file.read_text())
    assert data["hash"] == h
    assert "timestamp" in data
    assert "built_at" in data


def test_write_version_json_different_content_different_hash(tmp_path: Path):
    dist1 = tmp_path / "d1"
    (dist1 / "assets").mkdir(parents=True)
    (dist1 / "assets" / "a.js").write_text("v1")
    h1 = write_version_json(dist1)

    dist2 = tmp_path / "d2"
    (dist2 / "assets").mkdir(parents=True)
    (dist2 / "assets" / "a.js").write_text("v2")
    h2 = write_version_json(dist2)

    assert h1 != h2


def test_write_version_json_no_assets(tmp_path: Path):
    dist = tmp_path / "dist"
    dist.mkdir()
    h = write_version_json(dist)
    assert len(h) > 0


# ---------------------------------------------------------------------------
# rebuild_console_ui (async)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rebuild_console_ui_dir_not_found(tmp_path: Path):
    result = await rebuild_console_ui(tmp_path / "nonexistent")
    assert result.success is False
    assert "not found" in result.error


@pytest.mark.asyncio
async def test_rebuild_console_ui_npm_not_found(tmp_path: Path, monkeypatch):
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.tsx").write_text("")
    monkeypatch.setattr("shutil.which", lambda _: None)

    result = await rebuild_console_ui(tmp_path)
    assert result.success is False
    assert "npm" in result.error.lower()
