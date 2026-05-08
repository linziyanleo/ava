"""P1b workflow chain and artifact stores."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

TaskNodeStatus = Literal[
    "pending",
    "awaiting_deps",
    "queued",
    "running",
    "streaming",
    "succeeded",
    "failed",
    "cancelled",
    "interrupted",
    "skipped",
]
ChainStatus = Literal["pending", "running", "succeeded", "failed", "cancelled", "interrupted"]
ArtifactType = Literal["text", "file", "diff", "image", "log", "json", "workspace"]

ACTIVE_NODE_STATUSES = {
    "pending",
    "awaiting_deps",
    "queued",
    "running",
    "streaming",
}
FAILED_NODE_STATUSES = {"failed", "interrupted"}
DONE_NODE_STATUSES = {"succeeded", "skipped"}
CANCELLED_NODE_STATUSES = {"cancelled"}


@dataclass
class WorkflowNode:
    task_id: str
    chain_id: str
    status: TaskNodeStatus = "pending"
    parent_task_ids: list[str] = field(default_factory=list)
    node_kind: str = ""
    title: str = ""
    position: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WorkflowChain:
    chain_id: str
    trace_id: str = ""
    title: str = ""
    status: ChainStatus = "pending"
    created_at: float = 0
    updated_at: float = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    nodes: list[WorkflowNode] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["nodes"] = [node.to_dict() for node in self.nodes]
        return data


@dataclass
class ArtifactRecord:
    artifact_id: str
    task_id: str
    artifact_type: ArtifactType
    uri: str
    chain_id: str = ""
    trace_id: str = ""
    preview: str = ""
    created_at: float = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class WorkflowStore:
    """SQLite-backed P1b chain metadata store."""

    def __init__(self, db: Any | None = None) -> None:
        self._db = db
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        if not self._db:
            return
        self._db.execute(
            """CREATE TABLE IF NOT EXISTS workflow_chains (
                chain_id TEXT PRIMARY KEY,
                trace_id TEXT DEFAULT '',
                title TEXT DEFAULT '',
                status TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                metadata_json TEXT DEFAULT '{}'
            )"""
        )
        self._db.execute(
            """CREATE TABLE IF NOT EXISTS workflow_nodes (
                task_id TEXT PRIMARY KEY,
                chain_id TEXT NOT NULL,
                status TEXT NOT NULL,
                parent_task_ids_json TEXT DEFAULT '[]',
                node_kind TEXT DEFAULT '',
                title TEXT DEFAULT '',
                position INTEGER DEFAULT 0,
                metadata_json TEXT DEFAULT '{}'
            )"""
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_workflow_chains_trace ON workflow_chains(trace_id)"
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_workflow_nodes_chain ON workflow_nodes(chain_id, position)"
        )
        self._db.commit()

    def register_chain(
        self,
        *,
        chain_id: str | None = None,
        trace_id: str = "",
        title: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> WorkflowChain:
        chain_id = chain_id or uuid.uuid4().hex
        now = time.time()
        existing = self.get_chain(chain_id)
        if existing:
            return existing
        if self._db:
            self._db.execute(
                """INSERT INTO workflow_chains
                   (chain_id, trace_id, title, status, created_at, updated_at, metadata_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    chain_id,
                    trace_id,
                    title,
                    "pending",
                    now,
                    now,
                    json.dumps(metadata or {}, ensure_ascii=False),
                ),
            )
            self._db.commit()
        return WorkflowChain(
            chain_id=chain_id,
            trace_id=trace_id,
            title=title,
            status="pending",
            created_at=now,
            updated_at=now,
            metadata=metadata or {},
        )

    def upsert_node(
        self,
        *,
        chain_id: str,
        task_id: str,
        status: TaskNodeStatus = "pending",
        parent_task_ids: list[str] | None = None,
        node_kind: str = "",
        title: str = "",
        position: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> WorkflowNode:
        self.register_chain(chain_id=chain_id)
        if position is None:
            position = self._next_position(chain_id)
        node = WorkflowNode(
            task_id=task_id,
            chain_id=chain_id,
            status=status,
            parent_task_ids=list(parent_task_ids or []),
            node_kind=node_kind,
            title=title,
            position=position,
            metadata=metadata or {},
        )
        if self._db:
            self._db.execute(
                """INSERT OR REPLACE INTO workflow_nodes
                   (task_id, chain_id, status, parent_task_ids_json, node_kind, title, position, metadata_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    node.task_id,
                    node.chain_id,
                    node.status,
                    json.dumps(node.parent_task_ids, ensure_ascii=False),
                    node.node_kind,
                    node.title,
                    node.position,
                    json.dumps(node.metadata, ensure_ascii=False),
                ),
            )
            self._touch_chain(chain_id)
            self._db.commit()
            self._recompute_chain_status(chain_id)
        return node

    def update_node_status(self, task_id: str, status: TaskNodeStatus) -> WorkflowNode | None:
        node = self.get_node(task_id)
        if not node or not self._db:
            return node
        self._db.execute("UPDATE workflow_nodes SET status = ? WHERE task_id = ?", (status, task_id))
        self._touch_chain(node.chain_id)
        self._db.commit()
        self._recompute_chain_status(node.chain_id)
        return self.get_node(task_id)

    def advance_linear_chain(self, chain_id: str) -> WorkflowChain | None:
        """Promote waiting nodes after their parents finish; no DAG runner side effects."""
        chain = self.get_chain(chain_id)
        if not chain or not self._db:
            return chain
        by_id = {node.task_id: node for node in chain.nodes}
        for node in chain.nodes:
            if node.status not in {"pending", "awaiting_deps"} or not node.parent_task_ids:
                continue
            parents = [by_id.get(parent_id) for parent_id in node.parent_task_ids]
            if any(parent is None for parent in parents):
                continue
            parent_statuses = {parent.status for parent in parents if parent}
            if parent_statuses & (FAILED_NODE_STATUSES | CANCELLED_NODE_STATUSES):
                self.update_node_status(node.task_id, "skipped")
            elif parent_statuses and parent_statuses <= DONE_NODE_STATUSES:
                self.update_node_status(node.task_id, "queued")
        return self.get_chain(chain_id)

    def cancel_chain(self, chain_id: str) -> WorkflowChain | None:
        chain = self.get_chain(chain_id)
        if not chain or not self._db:
            return chain
        for node in chain.nodes:
            if node.status in ACTIVE_NODE_STATUSES:
                self.update_node_status(node.task_id, "cancelled")
        self._set_chain_status(chain_id, "cancelled")
        return self.get_chain(chain_id)

    def retry_chain(self, chain_id: str, *, new_chain_id: str | None = None) -> WorkflowChain | None:
        chain = self.get_chain(chain_id)
        if not chain or not self._db:
            return chain
        retry_id = new_chain_id or uuid.uuid4().hex
        retry = self.register_chain(
            chain_id=retry_id,
            trace_id=chain.trace_id,
            title=chain.title,
            metadata={**chain.metadata, "retry_of": chain.chain_id},
        )
        task_id_map = {
            node.task_id: f"{node.task_id}-retry-{retry_id[:8]}"
            for node in chain.nodes
        }
        for node in chain.nodes:
            parent_task_ids = [task_id_map[parent_id] for parent_id in node.parent_task_ids if parent_id in task_id_map]
            self.upsert_node(
                chain_id=retry.chain_id,
                task_id=task_id_map[node.task_id],
                status="awaiting_deps" if parent_task_ids else "queued",
                parent_task_ids=parent_task_ids,
                node_kind=node.node_kind,
                title=node.title,
                position=node.position,
                metadata={**node.metadata, "retry_of_task_id": node.task_id},
            )
        return self.get_chain(retry.chain_id)

    def get_node(self, task_id: str) -> WorkflowNode | None:
        if not self._db:
            return None
        row = self._db.fetchone("SELECT * FROM workflow_nodes WHERE task_id = ?", (task_id,))
        return self._node_from_row(row) if row else None

    def get_chain(self, chain_id: str) -> WorkflowChain | None:
        if not self._db:
            return None
        row = self._db.fetchone("SELECT * FROM workflow_chains WHERE chain_id = ?", (chain_id,))
        if not row:
            return None
        nodes = self.list_nodes(chain_id)
        return self._chain_from_row(row, nodes)

    def list_nodes(self, chain_id: str) -> list[WorkflowNode]:
        if not self._db:
            return []
        rows = self._db.fetchall(
            "SELECT * FROM workflow_nodes WHERE chain_id = ? ORDER BY position ASC, task_id ASC",
            (chain_id,),
        )
        return [self._node_from_row(row) for row in rows]

    def list_chains(
        self,
        *,
        trace_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[WorkflowChain]:
        if not self._db:
            return []
        clauses: list[str] = []
        params: list[Any] = []
        if trace_id:
            clauses.append("trace_id = ?")
            params.append(trace_id)
        if status:
            clauses.append("status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._db.fetchall(
            f"SELECT * FROM workflow_chains {where} ORDER BY updated_at DESC LIMIT ?",
            tuple(params + [max(1, min(limit, 250))]),
        )
        return [self._chain_from_row(row, self.list_nodes(row["chain_id"])) for row in rows]

    def _next_position(self, chain_id: str) -> int:
        if not self._db:
            return 0
        row = self._db.fetchone(
            "SELECT COALESCE(MAX(position), -1) AS max_position FROM workflow_nodes WHERE chain_id = ?",
            (chain_id,),
        )
        return int(row["max_position"] if row else -1) + 1

    def _touch_chain(self, chain_id: str) -> None:
        if self._db:
            self._db.execute(
                "UPDATE workflow_chains SET updated_at = ? WHERE chain_id = ?",
                (time.time(), chain_id),
            )

    def _set_chain_status(self, chain_id: str, status: ChainStatus) -> None:
        if self._db:
            self._db.execute(
                "UPDATE workflow_chains SET status = ?, updated_at = ? WHERE chain_id = ?",
                (status, time.time(), chain_id),
            )
            self._db.commit()

    def _recompute_chain_status(self, chain_id: str) -> None:
        nodes = self.list_nodes(chain_id)
        if not nodes:
            return
        statuses = {node.status for node in nodes}
        if statuses & FAILED_NODE_STATUSES:
            status: ChainStatus = "failed"
        elif statuses <= {"succeeded", "skipped"}:
            status = "succeeded"
        elif statuses <= {"cancelled", "skipped"}:
            status = "cancelled"
        else:
            status = "running"
        self._set_chain_status(chain_id, status)

    @staticmethod
    def _chain_from_row(row: Any, nodes: list[WorkflowNode]) -> WorkflowChain:
        return WorkflowChain(
            chain_id=row["chain_id"],
            trace_id=row["trace_id"] or "",
            title=row["title"] or "",
            status=row["status"],
            created_at=float(row["created_at"] or 0),
            updated_at=float(row["updated_at"] or 0),
            metadata=_load_json_object(row["metadata_json"]),
            nodes=nodes,
        )

    @staticmethod
    def _node_from_row(row: Any) -> WorkflowNode:
        return WorkflowNode(
            task_id=row["task_id"],
            chain_id=row["chain_id"],
            status=row["status"],
            parent_task_ids=_load_json_list(row["parent_task_ids_json"]),
            node_kind=row["node_kind"] or "",
            title=row["title"] or "",
            position=int(row["position"] or 0),
            metadata=_load_json_object(row["metadata_json"]),
        )


class ArtifactStore:
    """SQLite-backed task artifact index."""

    def __init__(self, db: Any | None = None) -> None:
        self._db = db
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        if not self._db:
            return
        self._db.execute(
            """CREATE TABLE IF NOT EXISTS task_artifacts (
                artifact_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                chain_id TEXT DEFAULT '',
                trace_id TEXT DEFAULT '',
                artifact_type TEXT NOT NULL,
                uri TEXT NOT NULL,
                preview TEXT DEFAULT '',
                created_at REAL NOT NULL,
                metadata_json TEXT DEFAULT '{}'
            )"""
        )
        self._db.execute("CREATE INDEX IF NOT EXISTS idx_task_artifacts_task ON task_artifacts(task_id)")
        self._db.execute("CREATE INDEX IF NOT EXISTS idx_task_artifacts_chain ON task_artifacts(chain_id)")
        self._db.execute("CREATE INDEX IF NOT EXISTS idx_task_artifacts_trace ON task_artifacts(trace_id)")
        self._db.commit()

    def record_artifact(
        self,
        *,
        task_id: str,
        artifact_type: ArtifactType,
        uri: str,
        artifact_id: str | None = None,
        chain_id: str = "",
        trace_id: str = "",
        preview: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> ArtifactRecord:
        record = ArtifactRecord(
            artifact_id=artifact_id or uuid.uuid4().hex,
            task_id=task_id,
            chain_id=chain_id,
            trace_id=trace_id,
            artifact_type=artifact_type,
            uri=uri,
            preview=preview,
            created_at=time.time(),
            metadata=metadata or {},
        )
        if self._db:
            self._db.execute(
                """INSERT OR REPLACE INTO task_artifacts
                   (artifact_id, task_id, chain_id, trace_id, artifact_type, uri, preview, created_at, metadata_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.artifact_id,
                    record.task_id,
                    record.chain_id,
                    record.trace_id,
                    record.artifact_type,
                    record.uri,
                    record.preview,
                    record.created_at,
                    json.dumps(record.metadata, ensure_ascii=False),
                ),
            )
            self._db.commit()
        return record

    def list_artifacts(
        self,
        *,
        task_id: str | None = None,
        chain_id: str | None = None,
        trace_id: str | None = None,
        artifact_type: str | None = None,
        limit: int = 100,
    ) -> list[ArtifactRecord]:
        if not self._db:
            return []
        clauses: list[str] = []
        params: list[Any] = []
        if task_id:
            clauses.append("task_id = ?")
            params.append(task_id)
        if chain_id:
            clauses.append("chain_id = ?")
            params.append(chain_id)
        if trace_id:
            clauses.append("trace_id = ?")
            params.append(trace_id)
        if artifact_type:
            clauses.append("artifact_type = ?")
            params.append(artifact_type)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._db.fetchall(
            f"SELECT * FROM task_artifacts {where} ORDER BY created_at DESC LIMIT ?",
            tuple(params + [max(1, min(limit, 500))]),
        )
        return [self._artifact_from_row(row) for row in rows]

    @staticmethod
    def _artifact_from_row(row: Any) -> ArtifactRecord:
        return ArtifactRecord(
            artifact_id=row["artifact_id"],
            task_id=row["task_id"],
            chain_id=row["chain_id"] or "",
            trace_id=row["trace_id"] or "",
            artifact_type=row["artifact_type"],
            uri=row["uri"],
            preview=row["preview"] or "",
            created_at=float(row["created_at"] or 0),
            metadata=_load_json_object(row["metadata_json"]),
        )


def _load_json_object(raw: str | None) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _load_json_list(raw: str | None) -> list[str]:
    try:
        value = json.loads(raw or "[]")
        return [str(item) for item in value] if isinstance(value, list) else []
    except Exception:
        return []
