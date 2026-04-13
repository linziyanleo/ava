from __future__ import annotations

from pathlib import Path

from ava.console.services.skills_service import SkillsService


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
