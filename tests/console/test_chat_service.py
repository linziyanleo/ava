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


def _insert_message_row(
    db: Database,
    *,
    session_id: int,
    conversation_id: str,
    seq: int,
    role: str,
    content: str,
    timestamp: str,
    tool_calls: list[dict] | None = None,
    tool_call_id: str | None = None,
    name: str | None = None,
):
    db.execute(
        """
        INSERT INTO session_messages
            (session_id, seq, conversation_id, role, content, tool_calls, tool_call_id, name, reasoning_content, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            seq,
            conversation_id,
            role,
            content,
            json.dumps(tool_calls, ensure_ascii=False) if tool_calls else None,
            tool_call_id,
            name,
            None,
            timestamp,
        ),
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


def test_get_messages_supports_explicit_legacy_conversation_id(tmp_path):
    service, db = _create_service(tmp_path)
    session_id = _insert_session(
        db,
        key="telegram:3",
        metadata={"conversation_id": "conv_current"},
    )

    _insert_message(
        db,
        session_id=session_id,
        conversation_id="",
        seq=0,
        role="user",
        content="legacy question",
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

    conversations = service.list_conversations("telegram:3")
    assert [item["conversation_id"] for item in conversations] == ["conv_current", ""]

    legacy_messages = service.get_messages("telegram:3", conversation_id="")
    assert [msg["content"] for msg in legacy_messages] == ["legacy question"]


def test_get_messages_repairs_retry_duplicate_and_toolcall_text_duplication(tmp_path):
    service, db = _create_service(tmp_path)
    session_id = _insert_session(
        db,
        key="telegram:4",
        metadata={"conversation_id": "conv_live"},
    )

    _insert_message_row(
        db,
        session_id=session_id,
        conversation_id="conv_live",
        seq=0,
        role="user",
        content="same prompt",
        timestamp="2026-04-16T16:24:46.173563",
    )
    _insert_message_row(
        db,
        session_id=session_id,
        conversation_id="conv_live",
        seq=1,
        role="user",
        content="same prompt",
        timestamp="2026-04-16T16:27:17.598893",
    )
    _insert_message_row(
        db,
        session_id=session_id,
        conversation_id="conv_live",
        seq=2,
        role="assistant",
        content="duplicate answer",
        tool_calls=[{
            "id": "call_1",
            "type": "function",
            "function": {"name": "send_sticker", "arguments": "{\"sticker_id\": 1}"},
        }],
        timestamp="2026-04-16T16:27:17.598909",
    )
    _insert_message_row(
        db,
        session_id=session_id,
        conversation_id="conv_live",
        seq=3,
        role="tool",
        content="send_sticker, 👍",
        tool_call_id="call_1",
        name="send_sticker",
        timestamp="2026-04-16T16:27:17.598911",
    )
    _insert_message_row(
        db,
        session_id=session_id,
        conversation_id="conv_live",
        seq=4,
        role="assistant",
        content="duplicate answer",
        timestamp="2026-04-16T16:27:17.598916",
    )

    messages = service.get_messages("telegram:4")

    assert [(msg["role"], msg["content"]) for msg in messages] == [
        ("user", "same prompt"),
        ("assistant", ""),
        ("tool", "send_sticker, 👍"),
        ("assistant", "duplicate answer"),
    ]

    rows = db.fetchall(
        """
        SELECT seq, role, content
          FROM session_messages
         WHERE session_id = ? AND conversation_id = ?
         ORDER BY seq
        """,
        (session_id, "conv_live"),
    )
    assert [(row["seq"], row["role"], row["content"]) for row in rows] == [
        (0, "user", "same prompt"),
        (2, "assistant", ""),
        (3, "tool", "send_sticker, 👍"),
        (4, "assistant", "duplicate answer"),
    ]


def test_get_messages_repairs_duplicate_tool_call_rows(tmp_path):
    service, db = _create_service(tmp_path)
    session_id = _insert_session(
        db,
        key="telegram:5",
        metadata={"conversation_id": "conv_live"},
    )

    tool_calls = [{
        "id": "call_dup",
        "type": "function",
        "function": {"name": "send_sticker", "arguments": "{\"sticker_id\": 8}"},
    }]

    _insert_message_row(
        db,
        session_id=session_id,
        conversation_id="conv_live",
        seq=0,
        role="user",
        content="老板说okr周五之前交上来，你有什么想法吗",
        timestamp="2026-04-20T20:19:51.444936",
    )
    for seq in (1, 1, 1):
        _insert_message_row(
            db,
            session_id=session_id,
            conversation_id="conv_live",
            seq=seq,
            role="assistant",
            content="",
            tool_calls=tool_calls,
            timestamp="2026-04-20T20:20:17.659672",
        )
    _insert_message_row(
        db,
        session_id=session_id,
        conversation_id="conv_live",
        seq=2,
        role="tool",
        content="send_sticker, 💡",
        tool_call_id="call_dup",
        name="send_sticker",
        timestamp="2026-04-20T20:20:17.659675",
    )
    _insert_message_row(
        db,
        session_id=session_id,
        conversation_id="conv_live",
        seq=3,
        role="assistant",
        content="哦这个，聊到工作了。",
        timestamp="2026-04-20T20:20:17.659677",
    )

    messages = service.get_messages("telegram:5")

    assert [(msg["role"], msg["content"]) for msg in messages] == [
        ("user", "老板说okr周五之前交上来，你有什么想法吗"),
        ("assistant", ""),
        ("tool", "send_sticker, 💡"),
        ("assistant", "哦这个，聊到工作了。"),
    ]
    assert len([msg for msg in messages if msg.get("tool_calls")]) == 1

    rows = db.fetchall(
        """
        SELECT seq, role, content, tool_calls
          FROM session_messages
         WHERE session_id = ? AND conversation_id = ?
         ORDER BY seq, id
        """,
        (session_id, "conv_live"),
    )
    assert [(row["seq"], row["role"], row["content"]) for row in rows] == [
        (0, "user", "老板说okr周五之前交上来，你有什么想法吗"),
        (1, "assistant", ""),
        (2, "tool", "send_sticker, 💡"),
        (3, "assistant", "哦这个，聊到工作了。"),
    ]


def test_get_messages_repairs_duplicate_background_task_rows(tmp_path):
    service, db = _create_service(tmp_path)
    session_id = _insert_session(
        db,
        key="telegram:6",
        metadata={"conversation_id": "conv_live"},
    )

    summary = (
        "[Background Task c9031eb1e76d SUCCESS]\n"
        "Type: codex | Duration: 554444ms\n\n"
        "只读结论"
    )
    continuation = (
        "[Background Task Completed — SUCCESS]\n"
        "Task: codex:c9031eb1e76d\n"
        "Duration: 554444ms\n\n"
        "只读结论\n\n"
        "请基于以上结果继续处理后续步骤。如果所有工作已完成，请总结。"
    )

    _insert_message_row(
        db,
        session_id=session_id,
        conversation_id="conv_live",
        seq=0,
        role="user",
        content="你让codex哥研究一下ava仓库",
        timestamp="2026-04-20T20:22:49.463318",
    )
    for _ in range(4):
        _insert_message_row(
            db,
            session_id=session_id,
            conversation_id="conv_live",
            seq=1,
            role="assistant",
            content=summary,
            timestamp="1776688335.40905",
        )
    _insert_message_row(
        db,
        session_id=session_id,
        conversation_id="conv_live",
        seq=2,
        role="user",
        content=continuation,
        timestamp="2026-04-20T20:32:15.650320",
    )

    messages = service.get_messages("telegram:6")

    assert [(msg["role"], msg["content"]) for msg in messages] == [
        ("user", "你让codex哥研究一下ava仓库"),
        ("assistant", summary),
        ("user", continuation),
    ]

    rows = db.fetchall(
        """
        SELECT seq, role, content
          FROM session_messages
         WHERE session_id = ? AND conversation_id = ?
         ORDER BY seq, id
        """,
        (session_id, "conv_live"),
    )
    assert [(row["seq"], row["role"], row["content"]) for row in rows] == [
        (0, "user", "你让codex哥研究一下ava仓库"),
        (1, "assistant", summary),
        (2, "user", continuation),
    ]


def test_get_messages_resequences_colliding_seq_rows_by_timestamp(tmp_path):
    service, db = _create_service(tmp_path)
    session_id = _insert_session(
        db,
        key="telegram:7",
        metadata={"conversation_id": "conv_live"},
    )

    tool_calls = [{
        "id": "call_old",
        "type": "function",
        "function": {"name": "send_sticker", "arguments": "{\"sticker_id\": 8}"},
    }]

    _insert_message_row(
        db,
        session_id=session_id,
        conversation_id="conv_live",
        seq=260,
        role="user",
        content="老板说okr周五之前交上来，你有什么想法吗",
        timestamp="2026-04-20T20:19:51.444936",
    )
    _insert_message_row(
        db,
        session_id=session_id,
        conversation_id="conv_live",
        seq=261,
        role="assistant",
        content="",
        tool_calls=tool_calls,
        timestamp="2026-04-20T20:20:17.659672",
    )
    _insert_message_row(
        db,
        session_id=session_id,
        conversation_id="conv_live",
        seq=264,
        role="tool",
        content="send_sticker, 💡",
        tool_call_id="call_old",
        name="send_sticker",
        timestamp="2026-04-20T20:20:17.659675",
    )
    _insert_message_row(
        db,
        session_id=session_id,
        conversation_id="conv_live",
        seq=265,
        role="assistant",
        content="哦这个，聊到工作了。",
        timestamp="2026-04-20T20:20:17.659677",
    )
    _insert_message_row(
        db,
        session_id=session_id,
        conversation_id="conv_live",
        seq=260,
        role="user",
        content="前端果然在2026年死了。",
        timestamp="2026-04-20T20:51:48.842226",
    )
    _insert_message_row(
        db,
        session_id=session_id,
        conversation_id="conv_live",
        seq=261,
        role="assistant",
        content="就这一个瞬间，我突然理解了为什么程序员也需要心理疏导。",
        timestamp="2026-04-20T20:52:07.651410",
    )

    messages = service.get_messages("telegram:7")

    assert [(msg["role"], msg["content"]) for msg in messages] == [
        ("user", "老板说okr周五之前交上来，你有什么想法吗"),
        ("assistant", ""),
        ("tool", "send_sticker, 💡"),
        ("assistant", "哦这个，聊到工作了。"),
        ("user", "前端果然在2026年死了。"),
        ("assistant", "就这一个瞬间，我突然理解了为什么程序员也需要心理疏导。"),
    ]

    rows = db.fetchall(
        """
        SELECT seq, role, content
          FROM session_messages
         WHERE session_id = ? AND conversation_id = ?
         ORDER BY seq, id
        """,
        (session_id, "conv_live"),
    )
    assert [(row["seq"], row["role"], row["content"]) for row in rows] == [
        (0, "user", "老板说okr周五之前交上来，你有什么想法吗"),
        (1, "assistant", ""),
        (2, "tool", "send_sticker, 💡"),
        (3, "assistant", "哦这个，聊到工作了。"),
        (4, "user", "前端果然在2026年死了。"),
        (5, "assistant", "就这一个瞬间，我突然理解了为什么程序员也需要心理疏导。"),
    ]
