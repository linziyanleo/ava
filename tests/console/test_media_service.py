"""Tests for MediaService screenshot path handling."""

from __future__ import annotations

import json

from ava.console.services.media_service import MediaService


def test_media_service_uses_sibling_screenshot_dir(tmp_path):
    media_dir = tmp_path / "media" / "generated"
    service = MediaService(media_dir=media_dir)

    assert service._screenshot_dir == tmp_path / "media" / "screenshots"


def test_get_image_path_supports_screenshot_dir(tmp_path):
    media_dir = tmp_path / "media" / "generated"
    screenshot_dir = tmp_path / "media" / "screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    screenshot = screenshot_dir / "page-agent-20260410-s_test.png"
    screenshot.write_bytes(b"png")

    service = MediaService(media_dir=media_dir, screenshot_dir=screenshot_dir)

    assert service.get_image_path(screenshot.name) == screenshot


def test_init_migrates_legacy_screenshot_and_keeps_symlink(tmp_path):
    media_dir = tmp_path / "media" / "generated"
    screenshot_dir = tmp_path / "media" / "screenshots"
    media_dir.mkdir(parents=True, exist_ok=True)
    legacy_path = media_dir / "page-agent-20260410-s_test.png"
    legacy_path.write_bytes(b"png")

    MediaService(media_dir=media_dir, screenshot_dir=screenshot_dir)

    target_path = screenshot_dir / legacy_path.name
    assert target_path.read_bytes() == b"png"
    assert legacy_path.is_symlink()
    assert legacy_path.resolve() == target_path


def test_delete_record_removes_screenshot_and_legacy_symlink(tmp_path):
    media_dir = tmp_path / "media" / "generated"
    screenshot_dir = tmp_path / "media" / "screenshots"
    media_dir.mkdir(parents=True, exist_ok=True)
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    filename = "page-agent-20260410-s_test.png"
    target_path = screenshot_dir / filename
    target_path.write_bytes(b"png")
    legacy_path = media_dir / filename
    legacy_path.symlink_to(target_path)
    records_file = media_dir / "records.jsonl"
    records_file.write_text(
        json.dumps({"id": "rec-1", "output_images": [filename]}, ensure_ascii=False) + "\n",
        "utf-8",
    )

    service = MediaService(media_dir=media_dir, screenshot_dir=screenshot_dir)
    assert service.delete_record("rec-1") is True

    assert not target_path.exists()
    assert not legacy_path.exists()
    assert not legacy_path.is_symlink()
    assert records_file.read_text("utf-8") == ""
