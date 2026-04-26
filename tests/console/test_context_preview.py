from __future__ import annotations

import base64
import json
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from ava.console.app import create_console_app
from ava.console.mock_bundle_runtime import LOCAL_ADMIN_PASSWORD_FILE
from ava.console.services.chat_service import ChatService
from ava.storage import Database
from nanobot.agent.context import ContextBuilder
from nanobot.session.manager import Session


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


def _insert_session(db: Database, *, key: str, metadata: dict[str, object]) -> None:
    db.execute(
        """
        INSERT INTO sessions (key, created_at, updated_at, metadata, token_stats)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            key,
            "2026-04-21T00:00:00+00:00",
            "2026-04-21T00:00:00+00:00",
            json.dumps(metadata, ensure_ascii=False),
            json.dumps({}, ensure_ascii=False),
        ),
    )
    db.commit()


class _FakeSessions:
    def __init__(self, session: Session):
        self._session = session

    def get_or_create(self, key: str) -> Session:
        assert key == self._session.key
        return self._session


class _FakeTools:
    def get_definitions(self) -> list[dict[str, object]]:
        return [{
            "type": "function",
            "function": {
                "name": "bash",
                "description": "Run a shell command",
                "parameters": {"type": "object"},
            },
        }]


class _FakeCategorizedMemory:
    def get_combined_context(self, channel: str | None, chat_id: str | None) -> str:
        assert channel == "console"
        assert chat_id == "ctx"
        return "## Personal Memory\n- secret sk-abcdefghijklmnopqrstuvwxyz"


class _FakeBgTasks:
    def get_active_digest(self, session_key: str | None = None) -> str:
        assert session_key == "console:ctx"
        return "[Background Task RUNNING]\nType: codex"


def _make_agent_loop(workspace: Path, session: Session) -> SimpleNamespace:
    context = ContextBuilder(workspace)
    return SimpleNamespace(
        lifecycle_manager=None,
        workspace=workspace,
        context=context,
        provider=SimpleNamespace(generation=SimpleNamespace(max_tokens=4096)),
        model="gpt-test",
        context_window_tokens=200_000,
        tools=_FakeTools(),
        sessions=_FakeSessions(session),
        categorized_memory=_FakeCategorizedMemory(),
        bg_tasks=_FakeBgTasks(),
        auto_compact=SimpleNamespace(_summaries={}, _format_summary=lambda text, last_active: text),
        _pending_queues={"console:ctx": object()},
    )


def _build_session() -> Session:
    png_b64 = base64.b64encode(b"abc").decode("ascii")
    return Session(
        key="console:ctx",
        messages=[
            {"role": "user", "content": "hello"},
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "see secret sk-abcdefghijklmnopqrstuvwxyz"},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{png_b64}"}},
                ],
            },
        ],
        metadata={"conversation_id": "conv_ctx"},
    )


def _login_admin(client: TestClient, nanobot_dir: Path) -> None:
    password = (
        nanobot_dir / "console" / "local-secrets" / LOCAL_ADMIN_PASSWORD_FILE
    ).read_text("utf-8").strip()
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": password},
    )
    assert response.status_code == 200


def test_chat_service_context_preview_redacts_and_omits_image_payload(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "AGENTS.md").write_text(
        "Bootstrap token sk-abcdefghijklmnopqrstuvwxyz",
        encoding="utf-8",
    )

    db = Database(tmp_path / "preview.db")
    _insert_session(db, key="console:ctx", metadata={"conversation_id": "conv_ctx"})

    session = _build_session()
    agent_loop = _make_agent_loop(workspace, session)
    service = ChatService(agent_loop=agent_loop, workspace=workspace, db=db)

    preview = service.get_context_preview("console:ctx", full=False, reveal=False)

    assert preview["scope"] == "idle_baseline"
    assert preview["flags"]["sanitized"] is True
    assert preview["flags"]["in_flight"] is True
    assert preview["tools"]["count"] == 1
    assert preview["tools"]["tokens"] > 0
    assert preview["totals"]["request_total_tokens"] > 0
    assert any(section["name"] == "categorized_memory" for section in preview["system_sections"])
    assert any(section["name"] == "background_tasks" for section in preview["system_sections"])
    assert preview["messages"][1]["content_type"] == "blocks"
    assert preview["messages"][1]["content_blocks"][0]["text"].startswith("see secret [REDACTED]")
    assert preview["messages"][1]["content_blocks"][1]["image_url"]["url"] == "data:image/png;base64,[omitted bytes=3]"


def test_context_preview_route_returns_payload_and_404(tmp_path, monkeypatch):
    monkeypatch.setattr("ava.console.app.prepare_console_ui_dist", lambda: None)

    nanobot_dir = tmp_path / "nanobot-home"
    workspace = tmp_path / "workspace"
    nanobot_dir.mkdir()
    workspace.mkdir()
    (workspace / "AGENTS.md").write_text("hello", encoding="utf-8")

    db = Database(tmp_path / "preview-route.db")
    _insert_session(db, key="console:ctx", metadata={"conversation_id": "conv_ctx"})

    session = _build_session()
    agent_loop = _make_agent_loop(workspace, session)

    app = create_console_app(
        nanobot_dir=nanobot_dir,
        workspace=workspace,
        agent_loop=agent_loop,
        config=_build_config(),
        token_stats_collector=None,
        db=db,
    )
    client = TestClient(app)
    _login_admin(client, nanobot_dir)

    ok = client.get("/api/chat/sessions/console:ctx/context-preview")
    assert ok.status_code == 200
    assert ok.json()["session_key"] == "console:ctx"

    missing = client.get("/api/chat/sessions/console:missing/context-preview")
    assert missing.status_code == 404
