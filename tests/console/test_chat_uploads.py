from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path

from fastapi.testclient import TestClient

from ava.console.app import create_console_app
from ava.console.mock_bundle_runtime import LOCAL_ADMIN_PASSWORD_FILE
from ava.storage import Database


def _build_config() -> SimpleNamespace:
    return SimpleNamespace(
        gateway=SimpleNamespace(
            port=18790,
            console=SimpleNamespace(
                port=6688,
                secret_key="x" * 48,
                token_expire_minutes=60,
                session_cookie_name="ava_console_session",
                session_cookie_secure=False,
                session_cookie_samesite="lax",
            ),
        ),
    )


def _create_client(tmp_path, monkeypatch) -> tuple[TestClient, Path]:
    monkeypatch.setattr("ava.console.app.prepare_console_ui_dist", lambda: None)

    nanobot_dir = tmp_path / "nanobot-home"
    workspace = tmp_path / "workspace"
    nanobot_dir.mkdir()
    workspace.mkdir()

    app = create_console_app(
        nanobot_dir=nanobot_dir,
        workspace=workspace,
        agent_loop=SimpleNamespace(lifecycle_manager=None),
        config=_build_config(),
        token_stats_collector=None,
        db=Database(nanobot_dir / "nanobot.db"),
    )
    return TestClient(app), nanobot_dir


def _login_admin(client: TestClient, nanobot_dir: Path) -> None:
    password = (
        nanobot_dir / "console" / "local-secrets" / LOCAL_ADMIN_PASSWORD_FILE
    ).read_text("utf-8").strip()
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": password},
    )
    assert response.status_code == 200


def test_chat_upload_route_saves_image_and_serves_preview(tmp_path, monkeypatch):
    client, nanobot_dir = _create_client(tmp_path, monkeypatch)
    _login_admin(client, nanobot_dir)

    png_bytes = b"\x89PNG\r\n\x1a\nchat-upload"
    upload = client.post(
        "/api/chat/uploads",
        files=[("files", ("pasted.png", png_bytes, "image/png"))],
    )

    assert upload.status_code == 200
    payload = upload.json()
    assert len(payload["uploads"]) == 1

    item = payload["uploads"][0]
    assert item["filename"].endswith(".png")
    assert item["path"].startswith("chat-uploads/")
    assert item["media_path"].endswith(item["filename"])
    assert item["preview_url"] == f"/api/media/images/{item['filename']}"

    preview = client.get(item["preview_url"])
    assert preview.status_code == 200
    assert preview.content == png_bytes
    assert preview.headers["content-type"].startswith("image/png")


def test_chat_upload_route_rejects_non_image_files(tmp_path, monkeypatch):
    client, nanobot_dir = _create_client(tmp_path, monkeypatch)
    _login_admin(client, nanobot_dir)

    upload = client.post(
        "/api/chat/uploads",
        files=[("files", ("notes.txt", b"not-an-image", "text/plain"))],
    )

    assert upload.status_code == 400
    assert "image" in upload.json()["detail"].lower()
