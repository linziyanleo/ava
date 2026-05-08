import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from nanobot.bus.events import OutboundMessage

from ava.console import auth
from ava.console.routes.chat_routes import (
    _build_direct_task_prompt,
    _extract_direct_task_mention,
    _listener_message_to_payload,
    _parse_skill_trigger,
    _register_skill_chain,
    _route_skill_trigger,
    _should_skip_listener_message,
)
from ava.console.routes import chat_routes
from ava.agent.workflow_store import WorkflowStore
from ava.storage import Database


class _FakeChatService:
    def __init__(self) -> None:
        self.trace_calls: list[str] = []
        self.message_calls: list[tuple[str, str | None]] = []
        self.create_calls: list[tuple[str, str, list[str]]] = []
        self.update_calls: list[tuple[str, list[str] | None]] = []
        self.context_size_calls: list[str] = []
        self.compress_calls: list[str] = []

    def get_messages_by_trace_id(self, trace_id: str):
        self.trace_calls.append(trace_id)
        return [{
            "role": "user",
            "content": "trace question",
            "trace_id": trace_id,
            "metadata": {
                "session_key": "console:abc123",
                "conversation_id": "conv_trace",
                "trace_id": trace_id,
            },
        }]

    def get_messages(self, session_key: str, conversation_id: str | None = None):
        self.message_calls.append((session_key, conversation_id))
        return []

    def create_session(self, username: str, title: str = "", participants: list[str] | None = None):
        self.create_calls.append((username, title, participants or []))
        return {
            "session_id": "abc123",
            "conversation_id": "conv_route",
            "participants": participants or [],
            "default_responder_agent_id": "nanobot",
        }

    def update_session(self, session_id: str, *, participants: list[str] | None = None):
        self.update_calls.append((session_id, participants))
        return {
            "ok": True,
            "session_id": session_id,
            "participants": participants or [],
            "default_responder_agent_id": "nanobot",
        }

    def get_context_size(self, session_id: str):
        self.context_size_calls.append(session_id)
        return {
            "used_tokens": 120,
            "model_limit": 200_000,
            "breakdown": {"messages": 120, "system": 0, "persona": 0},
            "compression_preview": "",
            "before_after_diff": None,
        }

    def compress_context(self, session_id: str):
        self.compress_calls.append(session_id)
        return {
            "before_tokens": 120,
            "after_tokens": 40,
            "used_tokens": 40,
            "model_limit": 200_000,
            "breakdown": {"messages": 40, "system": 10, "persona": 0},
            "compression_preview": "已压缩早期上下文",
            "before_after_diff": {"before": [], "after": []},
            "history": [],
        }

    def list_context_compressions(self, session_id: str):
        return [{"session_id": session_id, "summary_text": "已压缩早期上下文"}]


def _headers(role: str = "viewer") -> dict[str, str]:
    token = auth.create_access_token({
        "sub": f"{role}_user",
        "role": role,
        "created_at": "",
    })
    return {"Authorization": f"Bearer {token}"}


def _create_app_with_chat_service(service: _FakeChatService) -> FastAPI:
    auth.configure("x" * 48)
    app = FastAPI()
    app.include_router(chat_routes.router)
    app.include_router(chat_routes.messages_router)
    return app


def test_listener_message_defaults_to_async_result():
    payload = _listener_message_to_payload(
        OutboundMessage(
            channel="console",
            chat_id="tester",
            content="hello",
            metadata={"session_key": "console:abc123"},
        )
    )

    assert payload == {
        "type": "async_result",
        "content": "hello",
    }


def test_extract_direct_task_mention_builds_task_prompt():
    assert _extract_direct_task_mention("@codex write tests") == (
        "codex",
        "write tests",
        ["codex"],
    )
    assert _extract_direct_task_mention("please @claude-code review this") == (
        "claude_code",
        "please review this",
        ["claude_code"],
    )
    assert _extract_direct_task_mention("@nanobot hello") is None


def test_build_direct_task_prompt_includes_chat_context():
    prompt = _build_direct_task_prompt(
        "write tests",
        [
            {"role": "user", "content": "existing request"},
            {"role": "assistant", "content": "existing answer"},
        ],
    )

    assert "Conversation context:" in prompt
    assert "user: existing request" in prompt
    assert prompt.endswith("Current @agent request:\nwrite tests")


def test_parse_skill_trigger_only_accepts_message_prefix():
    assert _parse_skill_trigger("@my-skill write summary") == ("my-skill", "write summary")
    assert _parse_skill_trigger("@my_skill") == ("my_skill", "")
    assert _parse_skill_trigger("please @my-skill write summary") is None
    assert _parse_skill_trigger("@codex write tests") is None
    assert _parse_skill_trigger("@") is None


class _FakeSkillsService:
    def __init__(self, skill):
        self.skill = skill

    def get_skill(self, name: str):
        return self.skill if name == "my-skill" else None


class _FakeSkillChatService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def send_message(self, **kwargs):
        self.calls.append(kwargs)
        return "ok"


@pytest.mark.asyncio
async def test_route_skill_trigger_forces_registered_skill_context(tmp_path):
    skill_file = tmp_path / "SKILL.md"
    skill_file.write_text("# My Skill\n\nUse this skill.", encoding="utf-8")
    chat_service = _FakeSkillChatService()

    result = await _route_skill_trigger(
        svc_chat=chat_service,
        skills_service=_FakeSkillsService({"name": "my-skill", "path": str(skill_file)}),
        session_id="abc123",
        skill_name="my-skill",
        prompt="write summary",
        user_id="tester",
        on_progress=None,
        on_stream=None,
        on_stream_end=None,
    )

    assert result == "ok"
    assert chat_service.calls[0]["message"] == "write summary"
    assert chat_service.calls[0]["skill_names"] == ["my-skill"]
    assert chat_service.calls[0]["skill_contents"] == {"my-skill": "# My Skill\n\nUse this skill."}


@pytest.mark.asyncio
async def test_route_skill_trigger_rejects_missing_skill():
    with pytest.raises(KeyError):
        await _route_skill_trigger(
            svc_chat=_FakeSkillChatService(),
            skills_service=_FakeSkillsService(None),
            session_id="abc123",
            skill_name="unknown",
            prompt="write summary",
            user_id="tester",
            on_progress=None,
            on_stream=None,
            on_stream_end=None,
        )


def test_register_skill_chain_preserves_trigger_turn_metadata(tmp_path):
    db = Database(tmp_path / "workflow.db")
    svc = type("_Svc", (), {"workflow_store": WorkflowStore(db)})()

    chain_id, task_id = _register_skill_chain(
        svc,
        session_key="console:abc123",
        skill_name="summarize",
        prompt="summarize this chat",
        matched_by="natural_language",
        skill_match_confidence=0.92,
        origin_conversation_id="conv_current",
        origin_turn_seq=3,
    )

    chain = svc.workflow_store.get_chain(chain_id)
    node = svc.workflow_store.get_node(task_id)
    assert chain is not None
    assert node is not None
    assert chain.metadata["origin_conversation_id"] == "conv_current"
    assert chain.metadata["origin_turn_seq"] == 3
    assert node.metadata["origin_conversation_id"] == "conv_current"
    assert node.metadata["origin_turn_seq"] == 3


def test_listener_message_preserves_event_type_and_tool_hint():
    payload = _listener_message_to_payload(
        OutboundMessage(
            channel="console",
            chat_id="tester",
            content="done",
            metadata={
                "session_key": "console:abc123",
                "event_type": "complete",
                "tool_hint": True,
            },
        )
    )

    assert payload == {
        "type": "complete",
        "content": "done",
        "tool_hint": True,
    }


def test_empty_complete_is_not_skipped():
    msg = OutboundMessage(
        channel="console",
        chat_id="tester",
        content="",
        metadata={
            "session_key": "console:abc123",
            "event_type": "complete",
        },
    )

    assert _should_skip_listener_message(msg) is False


def test_stream_end_payload_preserves_resuming_flag():
    payload = _listener_message_to_payload(
        OutboundMessage(
            channel="console",
            chat_id="tester",
            content="",
            metadata={
                "session_key": "console:abc123",
                "event_type": "stream_end",
                "resuming": True,
            },
        )
    )

    assert payload == {
        "type": "stream_end",
        "content": "",
        "resuming": True,
    }


def test_empty_stream_end_is_not_skipped():
    msg = OutboundMessage(
        channel="console",
        chat_id="tester",
        content="",
        metadata={
            "session_key": "console:abc123",
            "event_type": "stream_end",
            "resuming": True,
        },
    )

    assert _should_skip_listener_message(msg) is False


def test_listener_payload_is_json_serializable_for_complete():
    payload = _listener_message_to_payload(
        OutboundMessage(
            channel="console",
            chat_id="tester",
            content="done",
            metadata={
                "session_key": "console:abc123",
                "event_type": "complete",
            },
        )
    )

    assert json.loads(json.dumps(payload)) == {
        "type": "complete",
        "content": "done",
    }


def test_get_messages_accepts_trace_id_without_session_key(monkeypatch):
    service = _FakeChatService()
    app = _create_app_with_chat_service(service)
    monkeypatch.setattr(chat_routes, "_get_chat_service", lambda _user: service)

    response = TestClient(app).get(
        "/api/chat/messages",
        params={"trace_id": "trace-deeplink"},
        headers=_headers("read_only"),
    )

    assert response.status_code == 200
    assert response.json()[0]["metadata"]["session_key"] == "console:abc123"
    assert service.trace_calls == ["trace-deeplink"]
    assert service.message_calls == []


def test_messages_alias_accepts_trace_id(monkeypatch):
    service = _FakeChatService()
    app = _create_app_with_chat_service(service)
    monkeypatch.setattr(chat_routes, "_get_chat_service", lambda _user: service)

    response = TestClient(app).get(
        "/api/messages",
        params={"trace_id": "trace-deeplink"},
        headers=_headers("viewer"),
    )

    assert response.status_code == 200
    assert service.trace_calls == ["trace-deeplink"]


def test_context_size_route_returns_session_context_breakdown(monkeypatch):
    service = _FakeChatService()
    app = _create_app_with_chat_service(service)
    monkeypatch.setattr(chat_routes, "_get_chat_service", lambda _user: service)

    response = TestClient(app).get(
        "/api/chat/sessions/abc123/context-size",
        headers=_headers("viewer"),
    )

    assert response.status_code == 200
    assert response.json()["used_tokens"] == 120
    assert service.context_size_calls == ["abc123"]


def test_compress_context_route_requires_editor_and_returns_diff(monkeypatch):
    service = _FakeChatService()
    app = _create_app_with_chat_service(service)
    monkeypatch.setattr(chat_routes, "_get_chat_service", lambda _user: service)

    viewer_response = TestClient(app).post(
        "/api/chat/sessions/abc123/compress",
        headers=_headers("viewer"),
    )
    editor_response = TestClient(app).post(
        "/api/chat/sessions/abc123/compress",
        headers=_headers("editor"),
    )

    assert viewer_response.status_code == 403
    assert editor_response.status_code == 200
    assert editor_response.json()["before_after_diff"] == {"before": [], "after": []}
    assert service.compress_calls == ["abc123"]


def test_get_messages_requires_session_key_or_trace_id(monkeypatch):
    service = _FakeChatService()
    app = _create_app_with_chat_service(service)
    monkeypatch.setattr(chat_routes, "_get_chat_service", lambda _user: service)

    response = TestClient(app).get("/api/chat/messages", headers=_headers("viewer"))

    assert response.status_code == 400
    assert response.json()["detail"] == "session_key or trace_id is required"


def test_create_session_accepts_participants(monkeypatch):
    service = _FakeChatService()
    app = _create_app_with_chat_service(service)
    monkeypatch.setattr(chat_routes, "_get_chat_service", lambda _user: service)

    response = TestClient(app).post(
        "/api/chat/sessions",
        json={"title": "pair", "participants": ["nanobot", "codex"]},
        headers=_headers("editor"),
    )

    assert response.status_code == 200
    assert response.json()["participants"] == ["nanobot", "codex"]
    assert service.create_calls == [("editor_user", "pair", ["nanobot", "codex"])]


def test_update_session_participants(monkeypatch):
    service = _FakeChatService()
    app = _create_app_with_chat_service(service)
    monkeypatch.setattr(chat_routes, "_get_chat_service", lambda _user: service)

    response = TestClient(app).patch(
        "/api/chat/sessions/abc123",
        json={"participants": ["codex"]},
        headers=_headers("editor"),
    )

    assert response.status_code == 200
    assert response.json()["participants"] == ["codex"]
    assert service.update_calls == [("abc123", ["codex"])]
