"""GatewayService 测试：确认已完全迁移到 LifecycleManager。"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ava.console.services.gateway_service import GatewayService


def test_get_status_without_lifecycle():
    svc = GatewayService(gateway_port=9999, console_port=7777)
    status = svc.get_status()
    assert status.running is True
    assert status.gateway_port == 9999
    assert status.console_port == 7777


def test_get_status_with_lifecycle():
    lc = MagicMock()
    lc.get_status.return_value = {
        "running": True,
        "pid": 42,
        "uptime_seconds": 100.0,
        "gateway_port": 18790,
        "console_port": 6688,
        "supervised": True,
        "supervisor": "docker",
        "restart_pending": False,
        "boot_generation": 3,
        "last_exit_reason": None,
    }
    svc = GatewayService(lifecycle=lc)
    status = svc.get_status()
    assert status.pid == 42
    assert status.supervised is True
    assert status.boot_generation == 3
    lc.get_status.assert_called_once()


@pytest.mark.asyncio
async def test_restart_without_lifecycle():
    svc = GatewayService()
    result = await svc.restart()
    assert result["status"] == "error"


@pytest.mark.asyncio
async def test_restart_with_lifecycle():
    lc = MagicMock()
    lc.request_restart.return_value = {"status": "ok", "message": "Restart requested"}
    svc = GatewayService(lifecycle=lc)
    result = await svc.restart(delay_ms=3000, force=True)
    assert result["status"] == "ok"
    lc.request_restart.assert_called_once_with(
        requested_by="console",
        reason="Console restart (delay=3000ms)",
        force=True,
    )


def test_health_without_lifecycle():
    svc = GatewayService()
    h = svc.health()
    assert h["ready"] is True


def test_health_with_lifecycle():
    lc = MagicMock()
    lc.is_healthy.return_value = {"ready": True, "boot_generation": 5, "uptime_seconds": 60.0, "shutting_down": False}
    svc = GatewayService(lifecycle=lc)
    h = svc.health()
    assert h["boot_generation"] == 5
    lc.is_healthy.assert_called_once()


def test_set_lifecycle():
    svc = GatewayService()
    assert svc._lifecycle is None
    lc = MagicMock()
    svc.set_lifecycle(lc)
    assert svc._lifecycle is lc


def test_no_shell_subprocess_references():
    """确认 GatewayService 中没有 subprocess / shell 引用。"""
    import inspect
    source = inspect.getsource(GatewayService)
    assert "subprocess" not in source
    assert "restart_gateway" not in source
    assert "shell" not in source.lower() or "shell" in "marshalling"
