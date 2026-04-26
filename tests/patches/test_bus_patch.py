"""Tests for bus_patch — MessageBus Console listener injection."""

import asyncio

import pytest

from nanobot.bus.queue import MessageBus


@pytest.fixture
def bus():
    return MessageBus()


@pytest.fixture(autouse=True)
def _apply_bus_patch():
    from ava.patches.bus_patch import apply_bus_patch
    apply_bus_patch()


class TestBusPatch:
    def test_register_listener(self, bus):
        """T8.1: register returns and stores a queue listener."""
        queue = bus.register_console_listener("sess1")
        assert isinstance(queue, asyncio.Queue)
        assert bus._console_listeners["sess1"] is queue

    def test_unregister_listener_marks_detached(self, bus):
        """T8.2: unregistered listener is retained as a detached sticky queue."""
        queue = bus.register_console_listener("sess1")
        bus.unregister_console_listener("sess1")
        assert bus._console_listeners["sess1"] is queue
        assert getattr(queue, "_ava_consumer_detached", False) is True

    async def test_dispatch_event(self, bus):
        """T8.3: dispatch enqueues the event for the registered session."""
        queue = bus.register_console_listener("sess1")
        event = {"type": "test"}
        await bus.dispatch_to_console_listener("sess1", event)
        received = await asyncio.wait_for(queue.get(), timeout=0.1)
        assert received == event

    def test_re_register_listener_reuses_active_queue(self, bus):
        """T8.4: repeated register reuses the sticky queue for the same session."""
        old_queue = bus.register_console_listener("sess1")
        new_queue = bus.register_console_listener("sess1")
        assert old_queue is new_queue
        assert bus._console_listeners["sess1"] is new_queue

    @pytest.mark.asyncio
    async def test_re_register_after_detach_reuses_buffered_queue(self, bus):
        queue = bus.register_console_listener("sess1")
        await queue.put({"type": "complete", "content": "done"})
        bus.unregister_console_listener("sess1")

        reused_queue = bus.register_console_listener("sess1")

        assert reused_queue is queue
        assert getattr(reused_queue, "_ava_consumer_detached", False) is False
        assert reused_queue.get_nowait() == {"type": "complete", "content": "done"}

    def test_reap_idle_listener_removes_detached_queue(self, bus):
        queue = bus.register_console_listener("sess1")
        bus.unregister_console_listener("sess1")
        queue._ava_detached_at = 0.0

        reaped = bus.reap_idle_console_listeners(now=301.0, idle_seconds=300.0)

        assert reaped == ["sess1"]
        assert "sess1" not in getattr(bus, "_console_listeners", {})

    async def test_dispatch_no_listener(self, bus):
        """T8.5: dispatch to unregistered session is a no-op."""
        # Should not raise
        await bus.dispatch_to_console_listener("nonexistent", {"type": "test"})

    def test_lazy_init(self):
        """T8.6: _console_listeners doesn't exist until first register."""
        fresh_bus = MessageBus()
        assert not hasattr(fresh_bus, "_console_listeners")


class TestObserveListener:
    """Tests for observe listener (生命周期事件，追加式注册)."""

    def test_register_observe_listener(self, bus):
        queue = bus.register_observe_listener("tg:123")
        assert isinstance(queue, asyncio.Queue)
        assert queue in bus._observe_listeners["tg:123"]

    def test_multiple_observers_same_session(self, bus):
        q1 = bus.register_observe_listener("tg:123")
        q2 = bus.register_observe_listener("tg:123")
        assert q1 is not q2
        assert len(bus._observe_listeners["tg:123"]) == 2

    def test_dispatch_observe_event_all_receive(self, bus):
        q1 = bus.register_observe_listener("tg:123")
        q2 = bus.register_observe_listener("tg:123")
        event = {"type": "message_arrived", "content": "hello"}
        bus.dispatch_observe_event("tg:123", event)
        assert q1.get_nowait() == event
        assert q2.get_nowait() == event

    def test_dispatch_observe_no_listener(self, bus):
        bus.dispatch_observe_event("nonexistent", {"type": "test"})

    def test_unregister_observe_listener(self, bus):
        q1 = bus.register_observe_listener("tg:123")
        q2 = bus.register_observe_listener("tg:123")
        bus.unregister_observe_listener("tg:123", q1)
        assert q1 not in bus._observe_listeners.get("tg:123", [])
        assert q2 in bus._observe_listeners["tg:123"]

    def test_unregister_last_removes_key(self, bus):
        q = bus.register_observe_listener("tg:123")
        bus.unregister_observe_listener("tg:123", q)
        assert "tg:123" not in bus._observe_listeners

    def test_observe_queue_full(self, bus):
        q = bus.register_observe_listener("tg:123")
        for i in range(200):
            bus.dispatch_observe_event("tg:123", {"i": i})
        assert q.full()
        bus.dispatch_observe_event("tg:123", {"overflow": True})
        assert q.qsize() == 200

    def test_observe_and_console_isolated(self, bus):
        """observe listener 与 console_listener 互不干扰。"""
        console_q = bus.register_console_listener("sess1")
        observe_q = bus.register_observe_listener("sess1")
        bus.dispatch_observe_event("sess1", {"type": "observe_event"})
        assert observe_q.get_nowait() == {"type": "observe_event"}
        assert console_q.empty()
