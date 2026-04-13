import json

from ava.console.services.chat_service import ChatService
from ava.storage import Database


def _create_service(tmp_path):
    db = Database(tmp_path / "chat.db")
    service = ChatService(agent_loop=None, workspace=tmp_path, db=db)
    return service, db


def _insert_session(db: Database, *, key: str, metadata: dict):
    db.execute(
        """
        INSERT INTO sessions (key, created_at, updated_at, metadata, token_stats)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            key,
            "2026-04-07T00:00:00+00:00",
            "2026-04-07T00:00:00+00:00",
            json.dumps(metadata, ensure_ascii=False),
            json.dumps({}, ensure_ascii=False),
        ),
    )
    db.commit()
    row = db.fetchone("SELECT id FROM sessions WHERE key = ?", (key,))
    assert row is not None
    return row["id"]


def _insert_message(db: Database, *, session_id: int, conversation_id: str, seq: int, role: str, content: str, timestamp: str):
    db.execute(
        """
        INSERT INTO session_messages
            (session_id, seq, conversation_id, role, content, tool_calls, tool_call_id, name, reasoning_content, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (session_id, seq, conversation_id, role, content, None, None, None, None, timestamp),
    )
    db.commit()


def test_get_messages_defaults_to_active_conversation(tmp_path):
    service, db = _create_service(tmp_path)
    session_id = _insert_session(
        db,
        key="telegram:1",
        metadata={"conversation_id": "conv_current"},
    )

    _insert_message(
        db,
        session_id=session_id,
        conversation_id="conv_old",
        seq=0,
        role="user",
        content="old question",
        timestamp="2026-04-07T00:00:00+00:00",
    )
    _insert_message(
        db,
        session_id=session_id,
        conversation_id="conv_current",
        seq=0,
        role="user",
        content="current question",
        timestamp="2026-04-07T01:00:00+00:00",
    )

    active_messages = service.get_messages("telegram:1")
    old_messages = service.get_messages("telegram:1", conversation_id="conv_old")

    assert [msg["content"] for msg in active_messages] == ["current question"]
    assert [msg["content"] for msg in old_messages] == ["old question"]


def test_list_conversations_returns_active_and_synthetic_empty_active(tmp_path):
    service, db = _create_service(tmp_path)
    session_id = _insert_session(
        db,
        key="telegram:2",
        metadata={"conversation_id": "conv_active"},
    )

    _insert_message(
        db,
        session_id=session_id,
        conversation_id="conv_old",
        seq=0,
        role="user",
        content="older branch",
        timestamp="2026-04-07T00:00:00+00:00",
    )

    conversations = service.list_conversations("telegram:2")

    assert [item["conversation_id"] for item in conversations] == ["conv_active", "conv_old"]
    assert conversations[0]["is_active"] is True
    assert conversations[0]["message_count"] == 0
    assert conversations[1]["first_message_preview"] == "older branch"
