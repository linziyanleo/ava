"""Seed a demo workflow chain that exercises every visual state on
WorkflowDetailPage (DESIGN_DETAILS §8.4) + ArtifactPreview (§8.5).

Idempotent: rerun with the same chain_id to upsert. Pass --reset to drop the
existing chain and reseed cleanly.

Usage:
    python scripts/seed_demo_workflow.py
    python scripts/seed_demo_workflow.py --chain-id demo-workflow-001 --reset
    python scripts/seed_demo_workflow.py --db-path ~/.ava/nanobot.db

Then launch Ava.app and visit /workflows/demo-workflow-001.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

# nanobot is a sibling repo; the workflow_store lives under ava.agent
# but its types Literal'd statuses are imported via ava.agent.workflow_store.
from ava.agent.workflow_store import ArtifactStore, WorkflowStore  # noqa: E402
from ava.storage.database import Database  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db-path",
        default=os.path.expanduser("~/.ava/nanobot.db"),
        help="Path to Ava's nanobot.db (default: ~/.ava/nanobot.db).",
    )
    parser.add_argument(
        "--chain-id",
        default="demo-workflow-001",
        help="Chain id to seed (default: demo-workflow-001).",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop existing chain + nodes + artifacts before seeding.",
    )
    return parser.parse_args()


def reset_chain(db: Database, chain_id: str) -> None:
    db.execute("DELETE FROM task_artifacts WHERE chain_id = ?", (chain_id,))
    db.execute("DELETE FROM workflow_nodes WHERE chain_id = ?", (chain_id,))
    db.execute("DELETE FROM workflow_chains WHERE chain_id = ?", (chain_id,))
    db.commit()


def seed(db_path: Path, chain_id: str, reset: bool) -> None:
    if not db_path.exists():
        print(f"创建新 DB: {db_path}")
        db_path.parent.mkdir(parents=True, exist_ok=True)
    db = Database(db_path)
    workflow_store = WorkflowStore(db)
    artifact_store = ArtifactStore(db)

    if reset:
        reset_chain(db, chain_id)
        print(f"重置 chain {chain_id}")

    now = time.time()
    started = now - 240  # 4 minutes ago

    # Override the chain row directly so created_at reads as a real elapsed window.
    workflow_store.register_chain(
        chain_id=chain_id,
        trace_id="demo-trace-aa11bb22",
        title="Demo · 视觉验证 workflow",
        metadata={
            "coordinator": "Claude Code",
            "purpose": "exercise every visual state on WorkflowDetailPage",
        },
    )
    db.execute(
        "UPDATE workflow_chains SET created_at = ?, updated_at = ? WHERE chain_id = ?",
        (started, now, chain_id),
    )
    db.commit()

    nodes = [
        {
            "task_id": "demo-step-01",
            "status": "succeeded",
            "title": "拉取仓库 + 配置 venv",
            "node_kind": "shell",
            "metadata": {
                "agent": "Claude Code",
                "input_summary": "git clone https://github.com/example/demo.git && cd demo && uv sync",
                "output_summary": "克隆成功，依赖 17 个包安装完毕",
            },
        },
        {
            "task_id": "demo-step-02",
            "status": "succeeded",
            "title": "初次构建 + 类型检查",
            "node_kind": "shell",
            "parent_task_ids": ["demo-step-01"],
            "metadata": {
                "agent": "Claude Code",
                "input_summary": "pnpm install && pnpm tsc -b --noEmit",
                "output_summary": "TypeScript: No errors found",
            },
        },
        {
            "task_id": "demo-step-03",
            "status": "failed",
            "title": "跑 e2e 测试",
            "node_kind": "test",
            "parent_task_ids": ["demo-step-02"],
            "metadata": {
                "agent": "Codex",
                "input_summary": "pnpm playwright test --workers=2",
                "error": (
                    "Test failed: workflow-detail.spec.ts › renders header\n"
                    "  Expected: '运行中'\n"
                    "  Received: 'pending'\n"
                    "  at workflow-detail.spec.ts:42:18\n\n"
                    "1 failed, 23 passed"
                ),
                "retry_count": 1,
            },
        },
        {
            "task_id": "demo-step-04",
            "status": "running",
            "title": "诊断失败原因 + 修补 spec",
            "node_kind": "coding",
            "parent_task_ids": ["demo-step-03"],
            "metadata": {
                "agent": "Claude Code",
                "input_summary": "Read failure log, locate stale fixture, regenerate snapshot",
                "phase": "regenerating snapshot",
            },
        },
        {
            "task_id": "demo-step-05",
            "status": "awaiting_deps",
            "title": "重跑 e2e 全集",
            "node_kind": "test",
            "parent_task_ids": ["demo-step-04"],
            "metadata": {
                "agent": "Codex",
                "input_summary": "pnpm playwright test (after fix)",
            },
        },
        {
            "task_id": "demo-step-06",
            "status": "queued",
            "title": "构建 release artifact",
            "node_kind": "shell",
            "parent_task_ids": ["demo-step-05"],
            "metadata": {
                "agent": "Claude Code",
                "input_summary": "pnpm build && tar czf dist.tgz dist/",
            },
        },
    ]

    for position, node in enumerate(nodes):
        workflow_store.upsert_node(
            chain_id=chain_id,
            task_id=node["task_id"],
            status=node["status"],
            parent_task_ids=node.get("parent_task_ids"),
            node_kind=node["node_kind"],
            title=node["title"],
            position=position,
            metadata=node["metadata"],
        )

    # Re-stamp chain status to "running" since the live store may have ticked it
    # to something else via _recompute_chain_status.
    db.execute(
        "UPDATE workflow_chains SET status = ?, updated_at = ? WHERE chain_id = ?",
        ("running", now, chain_id),
    )
    db.commit()

    artifacts = [
        {
            "task_id": "demo-step-02",
            "artifact_type": "log",
            "uri": "tasks/demo-step-02/build.log",
            "preview": (
                "[10:01:14] $ pnpm install\n"
                "[10:01:36] Lockfile up to date\n"
                "[10:01:38] Done in 22.4s\n"
                "[10:01:38] $ pnpm tsc -b --noEmit\n"
                "[10:02:05] TypeScript: No errors found\n"
            ),
            "metadata": {"source_agent": "Claude Code"},
        },
        {
            "task_id": "demo-step-03",
            "artifact_type": "diff",
            "uri": "tasks/demo-step-03/snapshot.diff",
            "preview": (
                "--- a/test/__snapshots__/workflow-detail.snap.ts\n"
                "+++ b/test/__snapshots__/workflow-detail.snap.ts\n"
                "@@ -3,7 +3,7 @@\n"
                "   chain_id: 'demo-workflow-001',\n"
                "-  status: 'pending',\n"
                "+  status: 'running',\n"
                "   nodes: [\n"
                "     { task_id: 'demo-step-01', status: 'succeeded' },\n"
            ),
            "metadata": {"source_agent": "Codex"},
        },
        {
            "task_id": "demo-step-03",
            "artifact_type": "log",
            "uri": "tasks/demo-step-03/playwright.log",
            "preview": (
                "Running 24 tests using 2 workers\n"
                "  ✓ 1 task-card renders status badge (231ms)\n"
                "  ✓ 2 task-card sorts by attention (108ms)\n"
                "  ...\n"
                "  ✘ 23 workflow-detail renders header (4.2s)\n"
                "  ✓ 24 artifact-preview type=image (412ms)\n"
                "\n"
                "1 failed, 23 passed (38s)\n"
            ),
            "metadata": {
                "source_agent": "Codex",
                "error": "1 failed, 23 passed",
            },
        },
        {
            "task_id": "demo-step-04",
            "artifact_type": "json",
            "uri": "tasks/demo-step-04/snapshot.json",
            "preview": (
                '{\n'
                '  "chain_id": "demo-workflow-001",\n'
                '  "title": "Demo · 视觉验证 workflow",\n'
                '  "status": "running",\n'
                '  "nodes": [\n'
                '    {"task_id": "demo-step-01", "status": "succeeded"},\n'
                '    {"task_id": "demo-step-02", "status": "succeeded"},\n'
                '    {"task_id": "demo-step-03", "status": "failed"}\n'
                '  ]\n'
                '}\n'
            ),
            "metadata": {"source_agent": "Claude Code"},
        },
        {
            "task_id": "demo-step-04",
            "artifact_type": "text",
            "uri": "tasks/demo-step-04/notes.md",
            "preview": (
                "## 修补思路\n\n"
                "snapshot 里 `status` 字段过期了，写脚本时初始 status 是 `pending`，"
                "实际 runner 在 advance_linear_chain 之后会把它推进到 `running`。\n\n"
                "**步骤**：\n\n"
                "1. 重跑生成脚本\n"
                "2. 比对 diff\n"
                "3. 用 `vitest -u` 更新 snapshot\n"
            ),
            "metadata": {"source_agent": "Claude Code"},
        },
    ]

    for spec in artifacts:
        artifact_store.record_artifact(
            task_id=spec["task_id"],
            artifact_type=spec["artifact_type"],
            uri=spec["uri"],
            chain_id=chain_id,
            trace_id="demo-trace-aa11bb22",
            preview=spec["preview"],
            metadata=spec["metadata"],
        )

    print(f"\n✅ seeded chain {chain_id}")
    print(f"   db: {db_path}")
    print(f"   nodes: {len(nodes)}")
    print(f"   artifacts: {len(artifacts)}")
    print(f"\n在 Ava 里访问：/workflows/{chain_id}")


def main() -> None:
    args = parse_args()
    seed(Path(args.db_path).expanduser(), args.chain_id, args.reset)


if __name__ == "__main__":
    main()
