"""Gateway process control — supervisor-first lifecycle backend."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger

from ava.console.models import GatewayStatus

if TYPE_CHECKING:
    from ava.runtime.lifecycle import LifecycleManager


class GatewayService:
    def __init__(
        self,
        lifecycle: LifecycleManager | None = None,
        gateway_port: int = 18790,
        console_port: int = 6688,
    ):
        self._lifecycle = lifecycle
        self._gateway_port = gateway_port
        self._console_port = console_port

    def set_lifecycle(self, lifecycle: LifecycleManager) -> None:
        self._lifecycle = lifecycle

    def get_status(self) -> GatewayStatus:
        if self._lifecycle:
            status = self._lifecycle.get_status()
            return GatewayStatus(**status)

        return GatewayStatus(
            running=True,
            gateway_port=self._gateway_port,
            console_port=self._console_port,
        )

    async def restart(self, delay_ms: int = 5000, force: bool = False) -> dict[str, Any]:
        if not self._lifecycle:
            return {"status": "error", "message": "LifecycleManager not available"}

        result = self._lifecycle.request_restart(
            requested_by="console",
            reason=f"Console restart (delay={delay_ms}ms)",
            force=force,
        )
        return result

    def health(self) -> dict[str, Any]:
        if self._lifecycle:
            return self._lifecycle.is_healthy()
        return {"ready": True, "boot_generation": 0, "uptime_seconds": 0, "shutting_down": False}
