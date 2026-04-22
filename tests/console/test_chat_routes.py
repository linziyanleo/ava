from nanobot.bus.events import OutboundMessage

from ava.console.routes.chat_routes import _listener_message_to_payload, _should_skip_listener_message


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
