from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from ava.console.app import create_console_app
from ava.console.mock_bundle_runtime import MOCK_TESTER_PASSWORD_FILE


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


def _create_client(tmp_path, monkeypatch) -> tuple[TestClient, object]:
    monkeypatch.setattr("ava.console.app.prepare_console_ui_dist", lambda: None)

    nanobot_dir = tmp_path / "nanobot-home"
    workspace = tmp_path / "workspace"
    nanobot_dir.mkdir()
    workspace.mkdir()

    agent_loop = SimpleNamespace(lifecycle_manager=None)
    app = create_console_app(
        nanobot_dir=nanobot_dir,
        workspace=workspace,
        agent_loop=agent_loop,
        config=_build_config(),
        token_stats_collector=None,
        db=None,
    )
    return TestClient(app), nanobot_dir


def _login_mock_tester(client: TestClient, nanobot_dir) -> None:
    password = (nanobot_dir / "console" / "local-secrets" / MOCK_TESTER_PASSWORD_FILE).read_text("utf-8").strip()
    response = client.post(
        "/api/auth/login",
        json={"username": "mock_tester", "password": password},
    )
    assert response.status_code == 200


def test_mock_tester_can_open_mock_safe_console_pages(tmp_path, monkeypatch):
    client, nanobot_dir = _create_client(tmp_path, monkeypatch)
    _login_mock_tester(client, nanobot_dir)

    sessions = client.get("/api/chat/sessions")
    assert sessions.status_code == 200
    assert any(item["key"] == "console:mock-session-1" for item in sessions.json())
    assert any(item["key"] == "console:mock-session-2" for item in sessions.json())
    assert any(item["key"] == "console:mock-session-3" for item in sessions.json())

    conversations = client.get(
        "/api/chat/conversations",
        params={"session_key": "console:mock-session-1"},
    )
    assert conversations.status_code == 200
    assert conversations.json()[0]["conversation_id"] == "mock-conv-1"

    messages = client.get(
        "/api/chat/messages",
        params={"session_key": "console:mock-session-1"},
    )
    assert messages.status_code == 200
    assert "[图片识别:" in messages.json()[0]["content"]

    tool_messages = client.get(
        "/api/chat/messages",
        params={"session_key": "console:mock-session-2"},
    )
    assert tool_messages.status_code == 200
    tool_payload = tool_messages.json()
    assistant_with_tools = next(msg for msg in tool_payload if msg["role"] == "assistant" and msg.get("tool_calls"))
    assert assistant_with_tools["reasoning_content"]
    tool_names = {call["function"]["name"] for call in assistant_with_tools["tool_calls"]}
    assert tool_names == {"page_agent", "vision", "transcribe", "memory_tool", "image_gen", "claude_code", "codex"}
    assert any(msg["role"] == "tool" and msg.get("tool_call_id") == "mock-call-page-agent" for msg in tool_payload)
    assert any(msg["role"] == "tool" and msg.get("tool_call_id") == "mock-call-memory-tool" for msg in tool_payload)
    assert isinstance(tool_payload[-1]["content"], list)

    subagent_messages = client.get(
        "/api/chat/messages",
        params={"session_key": "console:mock-session-3"},
    )
    assert subagent_messages.status_code == 200
    assert subagent_messages.json()[0]["content"].startswith("[Subagent 'layout-inspector'")

    bg_tasks = client.get("/api/bg-tasks", params={"include_finished": "false"})
    assert bg_tasks.status_code == 200
    statuses = {task["status"] for task in bg_tasks.json()["tasks"]}
    assert statuses == {"queued", "running"}
    codex_task = next(task for task in bg_tasks.json()["tasks"] if task["task_type"] == "codex")
    assert codex_task["cli_run_id"] == "mock-codex-thread-01"
    assert codex_task["cli_session_id"] == "mock-codex-thread-01"

    history = client.get("/api/bg-tasks/history", params={"page": 1, "page_size": 10})
    assert history.status_code == 200
    history_statuses = {task["status"] for task in history.json()["tasks"]}
    assert {"succeeded", "failed", "cancelled"} <= history_statuses

    detail = client.get("/api/bg-tasks/mock-task-run-1/detail")
    assert detail.status_code == 200
    assert "mock_tester coverage" in detail.json()["full_prompt"]

    token_turns = client.get(
        "/api/stats/tokens/by-session",
        params={"session_key": "console:mock-session-2", "conversation_id": "mock-conv-2"},
    )
    assert token_turns.status_code == 200
    assert token_turns.json()[0]["llm_calls"] == 7

    token_details = client.get(
        "/api/stats/tokens/by-session/detailed",
        params={"session_key": "console:mock-session-2", "conversation_id": "mock-conv-2"},
    )
    assert token_details.status_code == 200
    model_roles = {row["model_role"] for row in token_details.json()}
    assert {"page-agent", "vision", "voice", "mini", "imageGen", "claude_code", "default"} <= model_roles

    timeline = client.get("/api/bg-tasks/mock-task-run-1/timeline")
    assert timeline.status_code == 200
    assert any(event["event"] == "checkpoint" for event in timeline.json()["events"])

    skills = client.get("/api/skills/list")
    assert skills.status_code == 200
    assert isinstance(skills.json()["skills"], list)

    tools = client.get("/api/skills/tools")
    assert tools.status_code == 200
    assert isinstance(tools.json()["tools"], list)

    persona = client.get("/api/files/read", params={"path": "workspace/AGENTS.md"})
    assert persona.status_code == 200
    assert persona.json()["path"] == "workspace/AGENTS.md"


def test_mock_tester_can_manage_mock_chat_sessions_but_not_mutate_real_skill_registry(tmp_path, monkeypatch):
    client, nanobot_dir = _create_client(tmp_path, monkeypatch)
    _login_mock_tester(client, nanobot_dir)

    created = client.post("/api/chat/sessions", json={"title": "Mock smoke"})
    assert created.status_code == 200
    session_id = created.json()["session_id"]

    sessions = client.get("/api/chat/sessions")
    assert any(item["key"] == f"console:{session_id}" for item in sessions.json())

    deleted = client.delete(f"/api/chat/sessions/{session_id}")
    assert deleted.status_code == 200

    cancel = client.post("/api/bg-tasks/mock-task-queue-1/cancel")
    assert cancel.status_code == 200
    assert "cancelled" in cancel.json()["message"].lower()

    toggle = client.put(
        "/api/skills/toggle",
        json={"name": "console_ui_regression", "enabled": False},
    )
    assert toggle.status_code == 403
