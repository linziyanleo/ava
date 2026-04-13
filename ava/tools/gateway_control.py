"""Gateway lifecycle control tool.

仅提供 status / restart 两个动作。
restart 限制 cli/console 上下文，unsupervised 模式拒绝。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from nanobot.agent.tools.base import Tool

if TYPE_CHECKING:
    from ava.runtime.lifecycle import LifecycleManager


class GatewayControlTool(Tool):
    """查询网关状态或请求重启。"""

    def __init__(self, lifecycle: LifecycleManager | None = None) -> None:
        self._lifecycle = lifecycle
        self._channel: str = ""
        self._chat_id: str = ""
        self._session_key: str = ""

    def set_context(
        self,
        channel: str,
        chat_id: str,
        *,
        session_key: str | None = None,
    ) -> None:
        self._channel = channel
        self._chat_id = chat_id
        self._session_key = session_key or f"{channel}:{chat_id}"

    @property
    def name(self) -> str:
        return "gateway_control"

    @property
    def description(self) -> str:
        return (
            "Query gateway status or request a restart. "
            "action='status' returns lifecycle info (PID, uptime, supervisor, boot_generation). "
            "action='restart' requests a graceful shutdown (supervisor handles restart). "
            "Restart is only allowed from cli/console context and requires a supervisor."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["status", "restart"],
                    "description": "status: 查询网关状态; restart: 请求重启",
                },
                "reason": {
                    "type": "string",
                    "description": "重启原因（仅 restart 时使用）",
                },
                "force": {
                    "type": "boolean",
                    "description": "是否强制重启（缩短 drain 等待时间）",
                    "default": False,
                },
            },
            "required": ["action"],
        }

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "status")

        if not self._lifecycle:
            return "LifecycleManager not initialized."

        if action == "status":
            status = self._lifecycle.get_status()
            lines = [
                f"Gateway Status (gen {status['boot_generation']}):",
                f"  PID: {status['pid']}",
                f"  Uptime: {status['uptime_seconds']}s",
                f"  Supervised: {status['supervised']} ({status.get('supervisor', 'none')})",
                f"  Restart Pending: {status['restart_pending']}",
            ]
            if status.get("last_exit_reason"):
                lines.append(f"  Last Exit Reason: {status['last_exit_reason']}")
            return "\n".join(lines)

        if action == "restart":
            if self._channel not in ("cli", "console"):
                return "restart 仅允许在 cli/console 上下文执行，当前上下文: " + self._channel

            reason = kwargs.get("reason", "Manual restart requested")
            force = kwargs.get("force", False)

            result = self._lifecycle.request_restart(
                requested_by=f"{self._channel}:{self._chat_id}",
                task_id=kwargs.get("task_id"),
                origin_session_key=self._session_key,
                reason=reason,
                force=force,
            )
            return result.get("message", str(result))

        return f"Unknown action: {action}. Use 'status' or 'restart'."
