import json

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
