from __future__ import annotations

import pytest

from ava.agent.workflow_store import ArtifactStore, WorkflowStore
from ava.storage import Database


def test_workflow_store_registers_chain_and_advances_linear_nodes(tmp_path):
    db = Database(tmp_path / "workflow.sqlite3")
    store = WorkflowStore(db)

    chain = store.register_chain(chain_id="chain-1", trace_id="trace-1", title="Skill run")
    assert chain.chain_id == "chain-1"
    assert chain.status == "pending"

    store.upsert_node(
        chain_id="chain-1",
        task_id="task-a",
        status="succeeded",
        node_kind="codex",
        title="Inspect",
        position=0,
    )
    store.upsert_node(
        chain_id="chain-1",
        task_id="task-b",
        status="awaiting_deps",
        parent_task_ids=["task-a"],
        node_kind="claude_code",
        title="Patch",
        position=1,
    )

    advanced = store.advance_linear_chain("chain-1")

    assert advanced is not None
    assert [node.task_id for node in advanced.nodes] == ["task-a", "task-b"]
    assert advanced.nodes[1].status == "queued"
    assert advanced.status == "running"


def test_workflow_store_marks_downstream_skipped_after_failed_parent(tmp_path):
    db = Database(tmp_path / "workflow.sqlite3")
    store = WorkflowStore(db)

    store.register_chain(chain_id="chain-fail")
    store.upsert_node(chain_id="chain-fail", task_id="task-a", status="failed")
    store.upsert_node(
        chain_id="chain-fail",
        task_id="task-b",
        status="awaiting_deps",
        parent_task_ids=["task-a"],
    )

    advanced = store.advance_linear_chain("chain-fail")

    assert advanced is not None
    assert advanced.nodes[1].status == "skipped"
    assert advanced.status == "failed"


def test_artifact_store_indexes_task_chain_and_trace(tmp_path):
    db = Database(tmp_path / "workflow.sqlite3")
    store = ArtifactStore(db)

    artifact = store.record_artifact(
        artifact_id="artifact-1",
        task_id="task-a",
        chain_id="chain-1",
        trace_id="trace-1",
        artifact_type="diff",
        uri="file:///tmp/patch.diff",
        preview="diff summary",
        metadata={"lines": 12},
    )

    assert artifact.artifact_id == "artifact-1"
    assert store.list_artifacts(task_id="task-a")[0].preview == "diff summary"
    assert store.list_artifacts(chain_id="chain-1")[0].artifact_type == "diff"
    assert store.list_artifacts(trace_id="trace-1")[0].metadata == {"lines": 12}


def test_artifact_store_supports_p1b_artifact_types(tmp_path):
    db = Database(tmp_path / "workflow.sqlite3")
    store = ArtifactStore(db)

    for artifact_type in ["image", "diff", "json", "file"]:
        store.record_artifact(
            artifact_id=f"artifact-{artifact_type}",
            task_id=f"task-{artifact_type}",
            artifact_type=artifact_type,
            uri=f"artifact://task/{artifact_type}",
        )

    assert [item.artifact_type for item in store.list_artifacts(limit=10)] == ["file", "json", "diff", "image"]


def test_workflow_store_supports_streaming_terminal_paths(tmp_path):
    db = Database(tmp_path / "workflow.sqlite3")
    store = WorkflowStore(db)

    store.upsert_node(chain_id="chain-stream-ok", task_id="task-ok", status="streaming")
    assert store.get_chain("chain-stream-ok").status == "running"
    store.update_node_status("task-ok", "succeeded")
    assert store.get_chain("chain-stream-ok").status == "succeeded"

    store.upsert_node(chain_id="chain-stream-fail", task_id="task-fail", status="streaming")
    store.update_node_status("task-fail", "failed")
    assert store.get_chain("chain-stream-fail").status == "failed"


def test_workflow_store_retry_chain_preserves_trace_and_creates_new_chain(tmp_path):
    db = Database(tmp_path / "workflow.sqlite3")
    store = WorkflowStore(db)

    store.register_chain(chain_id="chain-original", trace_id="trace-keep", title="Skill run")
    store.upsert_node(chain_id="chain-original", task_id="task-a", status="succeeded", position=0)
    store.upsert_node(
        chain_id="chain-original",
        task_id="task-b",
        status="failed",
        parent_task_ids=["task-a"],
        position=1,
    )

    retried = store.retry_chain("chain-original", new_chain_id="chain-retry")

    assert retried.chain_id == "chain-retry"
    assert retried.trace_id == "trace-keep"
    assert retried.metadata["retry_of"] == "chain-original"
    assert [node.status for node in retried.nodes] == ["queued", "awaiting_deps"]
    assert retried.nodes[1].parent_task_ids == [retried.nodes[0].task_id]


def test_upsert_node_rejects_empty_chain_id(tmp_path):
    """Guards against accidentally writing orphan nodes with chain_id=""
    plus a stray random workflow_chains row from the register_chain fallback.
    """
    db = Database(tmp_path / "workflow.sqlite3")
    store = WorkflowStore(db)

    with pytest.raises(ValueError, match="chain_id is required"):
        store.upsert_node(chain_id="", task_id="orphan")

    assert store.list_chains() == []
