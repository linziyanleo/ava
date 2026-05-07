from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from ava.tools.page_agent import PageAgentTool


class _FakeRegistry:
    def __init__(self, responses: dict[str, str], registered: set[str] | None = None) -> None:
        self.responses = responses
        self.registered = registered if registered is not None else set(responses)
        self.calls: list[tuple[str, dict]] = []

    def has(self, name: str) -> bool:
        return name in self.registered

    async def execute(self, name: str, params: dict) -> str:
        self.calls.append((name, params))
        return self.responses.get(name, f"Error: missing fake response for {name}")


def _official_mcp_config(server: str = "page_agent_ext") -> SimpleNamespace:
    return SimpleNamespace(enabled=True, backend="official_mcp", mcp_server=server)


@pytest.mark.asyncio
async def test_official_mcp_execute_delegates_to_wrapped_tool() -> None:
    registry = _FakeRegistry({
        "mcp_page_agent_ext_execute_task": "Task completed.\n\nDone.",
    })
    tool = PageAgentTool(config=_official_mcp_config(), tool_registry=registry)

    result = await tool.execute(
        action="execute",
        url="https://example.com",
        instruction="click the sign in button",
        response_format="json",
    )

    payload = json.loads(result)
    assert payload["status"] == "SUCCESS"
    assert payload["backend"] == "official_mcp"
    assert payload["result"]["data"] == "Done."
    assert registry.calls == [
        (
            "mcp_page_agent_ext_execute_task",
            {"task": "Open https://example.com and then follow this instruction: click the sign in button"},
        )
    ]


@pytest.mark.asyncio
async def test_official_mcp_missing_wrapped_tool_is_clear_error() -> None:
    registry = _FakeRegistry({}, registered=set())
    tool = PageAgentTool(config=_official_mcp_config(), tool_registry=registry)

    result = await tool.execute(action="execute", instruction="open settings")

    assert "mcp_page_agent_ext_execute_task" in result
    assert "not registered" in result
    assert registry.calls == []


@pytest.mark.asyncio
async def test_official_mcp_screenshot_is_explicitly_unsupported() -> None:
    tool = PageAgentTool(config=_official_mcp_config(), tool_registry=_FakeRegistry({}))

    result = await tool.execute(action="screenshot", session_id="s_123", response_format="json")

    payload = json.loads(result)
    assert payload["status"] == "ERROR"
    assert payload["backend"] == "official_mcp"
    assert payload["error"]["code"] == "UNSUPPORTED_BACKEND_ACTION"
    assert "execute_task, get_status, and stop_task" in payload["error"]["message"]


@pytest.mark.asyncio
async def test_official_mcp_status_and_stop_delegate_to_wrapped_tools() -> None:
    registry = _FakeRegistry({
        "mcp_page_agent_ext_get_status": '{"connected": true, "busy": false}',
        "mcp_page_agent_ext_stop_task": "Stop signal sent.",
    })
    tool = PageAgentTool(config=_official_mcp_config(), tool_registry=registry)

    status = json.loads(await tool.execute(action="get_status", response_format="json"))
    stop = await tool.execute(action="stop_task")

    assert status["result"]["data"] == {"connected": True, "busy": False}
    assert stop == "Stop signal sent."
    assert registry.calls == [
        ("mcp_page_agent_ext_get_status", {}),
        ("mcp_page_agent_ext_stop_task", {}),
    ]


def test_page_agent_config_accepts_official_mcp_backend_aliases() -> None:
    from ava.forks.config.schema import PageAgentConfig

    cfg = PageAgentConfig.model_validate({
        "backend": "official_mcp",
        "mcpServer": "page_agent_ext",
    })

    assert cfg.backend == "official_mcp"
    assert cfg.mcp_server == "page_agent_ext"
    assert cfg.model_dump(by_alias=True)["mcpServer"] == "page_agent_ext"
