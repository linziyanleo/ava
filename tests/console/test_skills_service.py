from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ava.console.services.skills_service import MCPStatusInspector, SkillsService


def test_list_tools_reads_from_ava_tools_directory(tmp_path: Path):
    service = SkillsService(
        workspace=tmp_path,
        builtin_skills_dir=Path(__file__).resolve().parents[2] / "ava" / "skills",
        nanobot_dir=tmp_path,
        upstream_skills_dir=None,
    )

    tools = service.list_tools()

    tool_names = {item["name"] for item in tools}
    assert "codex" in tool_names
    assert "claude_code" in tool_names
    assert "gateway_control" in tool_names


def _write_mcp_config(nanobot_dir: Path) -> None:
    payload = {
        "tools": {
            "mcpServers": {
                "playwright_cdp": {
                    "command": "/bin/echo",
                    "args": ["--extension"],
                    "env": {
                        "PLAYWRIGHT_MCP_EXTENSION_TOKEN": "secret-token",
                        "OPENAI_API_KEY": "sk-secret",
                    },
                    "headers": {
                        "Authorization": "Bearer secret",
                    },
                    "toolTimeout": 60,
                    "enabledTools": ["browser_navigate", "browser_snapshot"],
                }
            }
        }
    }
    (nanobot_dir / "config.json").write_text(json.dumps(payload), encoding="utf-8")


def test_mcp_status_redacts_env_and_headers(tmp_path: Path):
    _write_mcp_config(tmp_path)
    agent = SimpleNamespace(
        _mcp_connected=True,
        _mcp_connecting=False,
        _mcp_stacks={"playwright_cdp": object()},
        tools=SimpleNamespace(
            get_definitions=lambda: [
                {"function": {"name": "mcp_playwright_cdp_browser_navigate"}},
                {"name": "mcp_playwright_cdp_browser_snapshot"},
            ]
        ),
    )

    result = MCPStatusInspector(tmp_path, agent_loop=agent).list_mcp_servers()

    server = result["servers"][0]
    assert server["name"] == "playwright_cdp"
    assert server["status"] == "connected"
    assert server["redacted"] == ["env", "headers"]
    assert server["config_redacted"]["env"] == {
        "OPENAI_API_KEY": "****",
        "PLAYWRIGHT_MCP_EXTENSION_TOKEN": "****",
    }
    assert server["config_redacted"]["headers"] == {"Authorization": "****"}
    assert "secret-token" not in json.dumps(server)
    assert server["registered_tools"] == [
        "mcp_playwright_cdp_browser_navigate",
        "mcp_playwright_cdp_browser_snapshot",
    ]


def test_mcp_status_runtime_unloaded_falls_back_to_static_config(tmp_path: Path):
    _write_mcp_config(tmp_path)

    result = MCPStatusInspector(tmp_path).list_mcp_servers()

    assert result["runtime"]["loaded"] is False
    assert result["servers"][0]["status"] == "unloaded"
    assert result["servers"][0]["registered_tools"] == []


def test_mcp_probe_rejects_unconfigured_server(tmp_path: Path):
    _write_mcp_config(tmp_path)

    with pytest.raises(ValueError, match="not configured"):
        asyncio.run(MCPStatusInspector(tmp_path).probe_mcp_server("other"))


def test_mcp_probe_timeout_returns_structured_failure(tmp_path: Path):
    _write_mcp_config(tmp_path)

    class SlowInspector(MCPStatusInspector):
        async def _probe_server(self, name, cfg):
            await asyncio.sleep(0.05)
            return []

    result = asyncio.run(SlowInspector(tmp_path).probe_mcp_server("playwright_cdp", timeout=0.001))

    assert result["ok"] is False
    assert result["status"] == "timeout"
    assert result["raw_tools"] == []
