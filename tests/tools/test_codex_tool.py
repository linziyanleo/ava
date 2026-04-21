from __future__ import annotations

import json

import pytest

from ava.tools.codex import CodexTool


def test_resolve_invocation_prefix_uses_paired_node(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    codex_bin = bin_dir / "codex"
    codex_bin.write_text("#!/usr/bin/env node\nconsole.log('codex')\n")
    node_bin = bin_dir / "node"
    node_bin.write_text("")

    tool = CodexTool(workspace=tmp_path)

    assert tool._resolve_invocation_prefix(str(codex_bin)) == [
        str(node_bin),
        str(codex_bin),
    ]


def test_parse_jsonl_prefers_nonempty_agent_message_after_transient_error(tmp_path):
    tool = CodexTool(workspace=tmp_path)
    stdout = "\n".join([
        json.dumps({"type": "thread.started", "thread_id": "thr_1"}),
        json.dumps({"type": "error", "message": "Reconnecting... 1/100"}),
        json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "   "}}),
        json.dumps({"type": "agent_message", "message": "[中等] 分页方案需要补服务端边界说明"}),
        json.dumps({"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 2}}),
    ])

    parsed = tool._parse_jsonl(stdout)

    assert parsed["thread_id"] == "thr_1"
    assert parsed["is_error"] is False
    assert parsed["result"] == "[中等] 分页方案需要补服务端边界说明"


@pytest.mark.asyncio
async def test_run_background_raises_when_codex_only_emits_error(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    codex_bin = bin_dir / "codex"
    codex_bin.write_text("#!/usr/bin/env node\nconsole.log('codex')\n")
    node_bin = bin_dir / "node"
    node_bin.write_text("")

    monkeypatch.setattr("ava.tools.codex.shutil.which", lambda name: str(codex_bin))

    tool = CodexTool(workspace=tmp_path)

    async def _fake_run_subprocess(cmd, cwd, timeout):
        assert cmd[:2] == [str(node_bin), str(codex_bin)]
        assert cwd == str(tmp_path)
        return (
            "\n".join([
                json.dumps({"type": "thread.started", "thread_id": "thr_2"}),
                json.dumps({"type": "error", "message": "Token data is not available."}),
                json.dumps({"type": "turn.completed", "usage": {"input_tokens": 3, "output_tokens": 0}}),
            ]),
            "",
        )

    monkeypatch.setattr(tool, "_run_subprocess", _fake_run_subprocess)

    with pytest.raises(RuntimeError, match="Token data is not available\\."):
        await tool._run_background(
            prompt="Review the spec only.",
            project=str(tmp_path),
            mode="standard",
        )
