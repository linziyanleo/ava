"""SQLite store for the P2a workflow definition baseline (AVA-47).

Owns CRUD over the six tables created in `ava/storage/database.py`:

    agent_workflows, workflow_versions,
    workflow_runs, workflow_steps, workflow_artifacts, workspace_leases

The store does not run workflows; that is the job of
`workflow_run_service.WorkflowRunService`. The split keeps persistence
separable from orchestration so the run service can be unit-tested without
a real database.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from ava.storage.database import Database


@dataclass
class WorkflowRecord:
    workflow_id: str
    name: str
    description: str = ""
    current_version: int = 1
    created_by_agent: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0
    deleted_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WorkflowVersionRecord:
    workflow_id: str
    version: int
    definition_json: str
    change_summary: str = ""
    base_version: int | None = None
    created_by_agent: str = ""
    created_at: float = 0.0
    is_current: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WorkflowRunRecord:
    run_id: str
    workflow_id: str
    version: int
    triggered_by: str = ""
    status: str = "pending"
    started_at: float | None = None
    completed_at: float | None = None
    final_outputs_json: str = "{}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WorkflowStepRecord:
    step_run_id: str
    run_id: str
    step_id: str
    status: str = "pending"
    agent: str = ""
    bg_task_id: str = ""
    started_at: float | None = None
    completed_at: float | None = None
    outputs_json: str = "{}"
    error_json: str = "{}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WorkspaceLeaseRecord:
    lease_id: str
    path: str
    holder_run_id: str = ""
    holder_step_id: str = ""
    acquired_at: float = 0.0
    expires_at: float | None = None
    released_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class WorkflowDefinitionStore:
    """Persistence for workflow definitions, versions, runs, steps, leases."""

    def __init__(self, db: Database) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # agent_workflows + workflow_versions
    # ------------------------------------------------------------------

    def create_workflow(
        self,
        *,
        name: str,
        description: str = "",
        definition_json: str,
        change_summary: str = "",
        created_by_agent: str = "",
    ) -> tuple[WorkflowRecord, WorkflowVersionRecord]:
        workflow_id = f"wf_{uuid.uuid4().hex[:16]}"
        now = time.time()
        wf = WorkflowRecord(
            workflow_id=workflow_id,
            name=name,
            description=description,
            current_version=1,
            created_by_agent=created_by_agent,
            created_at=now,
            updated_at=now,
        )
        self._db.execute(
            """INSERT INTO agent_workflows
               (workflow_id, name, description, current_version,
                created_by_agent, created_at, updated_at, deleted_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, NULL)""",
            (
                wf.workflow_id, wf.name, wf.description, wf.current_version,
                wf.created_by_agent, wf.created_at, wf.updated_at,
            ),
        )
        version = WorkflowVersionRecord(
            workflow_id=workflow_id,
            version=1,
            definition_json=definition_json,
            change_summary=change_summary,
            base_version=None,
            created_by_agent=created_by_agent,
            created_at=now,
            is_current=True,
        )
        self._db.execute(
            """INSERT INTO workflow_versions
               (workflow_id, version, definition_json, change_summary,
                base_version, created_by_agent, created_at, is_current)
               VALUES (?, ?, ?, ?, ?, ?, ?, 1)""",
            (
                version.workflow_id, version.version, version.definition_json,
                version.change_summary, version.base_version,
                version.created_by_agent, version.created_at,
            ),
        )
        self._db.commit()
        return wf, version

    def update_workflow(
        self,
        *,
        workflow_id: str,
        base_version: int,
        definition_json: str,
        change_summary: str = "",
        created_by_agent: str = "",
    ) -> WorkflowVersionRecord:
        """Append a new version. Caller must check base_version concurrency.

        Raises ValueError on stale base_version. The conflict response shape
        belongs to the HTTP route (AVA-48); this layer just refuses the write.
        """
        wf = self.get_workflow(workflow_id)
        if wf is None:
            raise LookupError(f"workflow_id {workflow_id} not found")
        if base_version != wf.current_version:
            raise ValueError(
                f"base_version {base_version} != current_version {wf.current_version}"
            )
        now = time.time()
        new_version = wf.current_version + 1
        # Demote the previous current row.
        self._db.execute(
            "UPDATE workflow_versions SET is_current = 0 WHERE workflow_id = ? AND is_current = 1",
            (workflow_id,),
        )
        version = WorkflowVersionRecord(
            workflow_id=workflow_id,
            version=new_version,
            definition_json=definition_json,
            change_summary=change_summary,
            base_version=base_version,
            created_by_agent=created_by_agent,
            created_at=now,
            is_current=True,
        )
        self._db.execute(
            """INSERT INTO workflow_versions
               (workflow_id, version, definition_json, change_summary,
                base_version, created_by_agent, created_at, is_current)
               VALUES (?, ?, ?, ?, ?, ?, ?, 1)""",
            (
                version.workflow_id, version.version, version.definition_json,
                version.change_summary, version.base_version,
                version.created_by_agent, version.created_at,
            ),
        )
        self._db.execute(
            "UPDATE agent_workflows SET current_version = ?, updated_at = ? WHERE workflow_id = ?",
            (new_version, now, workflow_id),
        )
        self._db.commit()
        return version

    def soft_delete_workflow(self, workflow_id: str) -> None:
        now = time.time()
        self._db.execute(
            "UPDATE agent_workflows SET deleted_at = ?, updated_at = ? WHERE workflow_id = ?",
            (now, now, workflow_id),
        )
        self._db.commit()

    def get_workflow(self, workflow_id: str) -> WorkflowRecord | None:
        row = self._db.fetchone(
            """SELECT workflow_id, name, description, current_version,
                      created_by_agent, created_at, updated_at, deleted_at
               FROM agent_workflows WHERE workflow_id = ?""",
            (workflow_id,),
        )
        if row is None:
            return None
        return WorkflowRecord(
            workflow_id=row["workflow_id"],
            name=row["name"],
            description=row["description"] or "",
            current_version=row["current_version"],
            created_by_agent=row["created_by_agent"] or "",
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            deleted_at=row["deleted_at"],
        )

    def list_workflows(
        self,
        *,
        include_deleted: bool = False,
        limit: int = 100,
    ) -> list[WorkflowRecord]:
        if include_deleted:
            rows = self._db.fetchall(
                """SELECT workflow_id, name, description, current_version,
                          created_by_agent, created_at, updated_at, deleted_at
                   FROM agent_workflows ORDER BY updated_at DESC LIMIT ?""",
                (limit,),
            )
        else:
            rows = self._db.fetchall(
                """SELECT workflow_id, name, description, current_version,
                          created_by_agent, created_at, updated_at, deleted_at
                   FROM agent_workflows WHERE deleted_at IS NULL
                   ORDER BY updated_at DESC LIMIT ?""",
                (limit,),
            )
        return [
            WorkflowRecord(
                workflow_id=r["workflow_id"], name=r["name"],
                description=r["description"] or "",
                current_version=r["current_version"],
                created_by_agent=r["created_by_agent"] or "",
                created_at=r["created_at"], updated_at=r["updated_at"],
                deleted_at=r["deleted_at"],
            )
            for r in rows
        ]

    def get_version(
        self, workflow_id: str, version: int
    ) -> WorkflowVersionRecord | None:
        row = self._db.fetchone(
            """SELECT workflow_id, version, definition_json, change_summary,
                      base_version, created_by_agent, created_at, is_current
               FROM workflow_versions WHERE workflow_id = ? AND version = ?""",
            (workflow_id, version),
        )
        if row is None:
            return None
        return _row_to_version(row)

    def get_current_version(self, workflow_id: str) -> WorkflowVersionRecord | None:
        row = self._db.fetchone(
            """SELECT workflow_id, version, definition_json, change_summary,
                      base_version, created_by_agent, created_at, is_current
               FROM workflow_versions WHERE workflow_id = ? AND is_current = 1""",
            (workflow_id,),
        )
        return _row_to_version(row) if row else None

    def list_versions(self, workflow_id: str) -> list[WorkflowVersionRecord]:
        rows = self._db.fetchall(
            """SELECT workflow_id, version, definition_json, change_summary,
                      base_version, created_by_agent, created_at, is_current
               FROM workflow_versions WHERE workflow_id = ?
               ORDER BY version DESC""",
            (workflow_id,),
        )
        return [_row_to_version(row) for row in rows]

    # ------------------------------------------------------------------
    # workflow_runs + workflow_steps
    # ------------------------------------------------------------------

    def create_run(
        self,
        *,
        workflow_id: str,
        version: int,
        triggered_by: str = "",
    ) -> WorkflowRunRecord:
        run_id = f"run_{uuid.uuid4().hex[:16]}"
        record = WorkflowRunRecord(
            run_id=run_id, workflow_id=workflow_id, version=version,
            triggered_by=triggered_by, status="pending",
        )
        self._db.execute(
            """INSERT INTO workflow_runs
               (run_id, workflow_id, version, triggered_by, status,
                started_at, completed_at, final_outputs_json)
               VALUES (?, ?, ?, ?, ?, NULL, NULL, '{}')""",
            (record.run_id, record.workflow_id, record.version,
             record.triggered_by, record.status),
        )
        self._db.commit()
        return record

    def update_run_status(
        self,
        run_id: str,
        status: str,
        *,
        final_outputs: dict[str, Any] | None = None,
    ) -> None:
        now = time.time()
        if status == "running":
            self._db.execute(
                "UPDATE workflow_runs SET status = ?, started_at = COALESCE(started_at, ?) WHERE run_id = ?",
                (status, now, run_id),
            )
        elif status in {"succeeded", "failed", "cancelled"}:
            self._db.execute(
                """UPDATE workflow_runs SET status = ?, completed_at = ?,
                          final_outputs_json = ? WHERE run_id = ?""",
                (status, now, json.dumps(final_outputs or {}, ensure_ascii=False), run_id),
            )
        else:
            self._db.execute(
                "UPDATE workflow_runs SET status = ? WHERE run_id = ?",
                (status, run_id),
            )
        self._db.commit()

    def get_run(self, run_id: str) -> WorkflowRunRecord | None:
        row = self._db.fetchone(
            """SELECT run_id, workflow_id, version, triggered_by, status,
                      started_at, completed_at, final_outputs_json
               FROM workflow_runs WHERE run_id = ?""",
            (run_id,),
        )
        if row is None:
            return None
        return WorkflowRunRecord(
            run_id=row["run_id"], workflow_id=row["workflow_id"],
            version=row["version"], triggered_by=row["triggered_by"] or "",
            status=row["status"], started_at=row["started_at"],
            completed_at=row["completed_at"],
            final_outputs_json=row["final_outputs_json"] or "{}",
        )

    def list_runs_for_workflow(
        self, workflow_id: str, *, limit: int = 50
    ) -> list[WorkflowRunRecord]:
        rows = self._db.fetchall(
            """SELECT run_id, workflow_id, version, triggered_by, status,
                      started_at, completed_at, final_outputs_json
               FROM workflow_runs WHERE workflow_id = ?
               ORDER BY started_at DESC, run_id DESC LIMIT ?""",
            (workflow_id, limit),
        )
        return [
            WorkflowRunRecord(
                run_id=r["run_id"], workflow_id=r["workflow_id"],
                version=r["version"], triggered_by=r["triggered_by"] or "",
                status=r["status"], started_at=r["started_at"],
                completed_at=r["completed_at"],
                final_outputs_json=r["final_outputs_json"] or "{}",
            )
            for r in rows
        ]

    def create_step(
        self,
        *,
        run_id: str,
        step_id: str,
        agent: str = "",
    ) -> WorkflowStepRecord:
        step_run_id = f"sr_{uuid.uuid4().hex[:16]}"
        record = WorkflowStepRecord(
            step_run_id=step_run_id, run_id=run_id, step_id=step_id,
            status="pending", agent=agent,
        )
        self._db.execute(
            """INSERT INTO workflow_steps
               (step_run_id, run_id, step_id, status, agent, bg_task_id,
                started_at, completed_at, outputs_json, error_json)
               VALUES (?, ?, ?, ?, ?, '', NULL, NULL, '{}', '{}')""",
            (record.step_run_id, record.run_id, record.step_id,
             record.status, record.agent),
        )
        self._db.commit()
        return record

    def settle_step(
        self,
        step_run_id: str,
        *,
        status: str,
        outputs: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
        bg_task_id: str = "",
    ) -> None:
        now = time.time()
        self._db.execute(
            """UPDATE workflow_steps
               SET status = ?, completed_at = ?, outputs_json = ?, error_json = ?,
                   bg_task_id = COALESCE(NULLIF(?, ''), bg_task_id)
               WHERE step_run_id = ?""",
            (status, now,
             json.dumps(outputs or {}, ensure_ascii=False),
             json.dumps(error or {}, ensure_ascii=False),
             bg_task_id, step_run_id),
        )
        self._db.commit()

    def mark_step_running(self, step_run_id: str, *, bg_task_id: str = "") -> None:
        now = time.time()
        self._db.execute(
            """UPDATE workflow_steps
               SET status = 'running', started_at = COALESCE(started_at, ?),
                   bg_task_id = COALESCE(NULLIF(?, ''), bg_task_id)
               WHERE step_run_id = ?""",
            (now, bg_task_id, step_run_id),
        )
        self._db.commit()

    def list_steps_for_run(self, run_id: str) -> list[WorkflowStepRecord]:
        rows = self._db.fetchall(
            """SELECT step_run_id, run_id, step_id, status, agent, bg_task_id,
                      started_at, completed_at, outputs_json, error_json
               FROM workflow_steps WHERE run_id = ? ORDER BY started_at""",
            (run_id,),
        )
        return [
            WorkflowStepRecord(
                step_run_id=r["step_run_id"], run_id=r["run_id"],
                step_id=r["step_id"], status=r["status"],
                agent=r["agent"] or "", bg_task_id=r["bg_task_id"] or "",
                started_at=r["started_at"], completed_at=r["completed_at"],
                outputs_json=r["outputs_json"] or "{}",
                error_json=r["error_json"] or "{}",
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # workspace_leases
    # ------------------------------------------------------------------

    def acquire_lease(
        self,
        *,
        path: str,
        run_id: str,
        step_run_id: str,
        ttl_seconds: float | None = None,
    ) -> WorkspaceLeaseRecord:
        """Insert a fresh lease row. P2a baseline does not enforce
        cross-step exclusion; AVA-25 (P2b) is expected to add a single-row
        active-lease constraint per path. We just record the acquisition.
        """
        lease_id = f"lease_{uuid.uuid4().hex[:16]}"
        now = time.time()
        record = WorkspaceLeaseRecord(
            lease_id=lease_id, path=path, holder_run_id=run_id,
            holder_step_id=step_run_id, acquired_at=now,
            expires_at=now + ttl_seconds if ttl_seconds else None,
        )
        self._db.execute(
            """INSERT INTO workspace_leases
               (lease_id, path, holder_run_id, holder_step_id,
                acquired_at, expires_at, released_at)
               VALUES (?, ?, ?, ?, ?, ?, NULL)""",
            (record.lease_id, record.path, record.holder_run_id,
             record.holder_step_id, record.acquired_at, record.expires_at),
        )
        self._db.commit()
        return record

    def release_lease(self, lease_id: str) -> None:
        now = time.time()
        self._db.execute(
            "UPDATE workspace_leases SET released_at = ? WHERE lease_id = ? AND released_at IS NULL",
            (now, lease_id),
        )
        self._db.commit()

    def list_active_leases(self, path: str | None = None) -> list[WorkspaceLeaseRecord]:
        if path is not None:
            rows = self._db.fetchall(
                """SELECT lease_id, path, holder_run_id, holder_step_id,
                          acquired_at, expires_at, released_at
                   FROM workspace_leases
                   WHERE path = ? AND released_at IS NULL
                   ORDER BY acquired_at""",
                (path,),
            )
        else:
            rows = self._db.fetchall(
                """SELECT lease_id, path, holder_run_id, holder_step_id,
                          acquired_at, expires_at, released_at
                   FROM workspace_leases
                   WHERE released_at IS NULL
                   ORDER BY acquired_at"""
            )
        return [
            WorkspaceLeaseRecord(
                lease_id=r["lease_id"], path=r["path"],
                holder_run_id=r["holder_run_id"] or "",
                holder_step_id=r["holder_step_id"] or "",
                acquired_at=r["acquired_at"], expires_at=r["expires_at"],
                released_at=r["released_at"],
            )
            for r in rows
        ]


def _row_to_version(row: Any) -> WorkflowVersionRecord:
    return WorkflowVersionRecord(
        workflow_id=row["workflow_id"], version=row["version"],
        definition_json=row["definition_json"],
        change_summary=row["change_summary"] or "",
        base_version=row["base_version"],
        created_by_agent=row["created_by_agent"] or "",
        created_at=row["created_at"],
        is_current=bool(row["is_current"]),
    )


__all__ = [
    "WorkflowDefinitionStore",
    "WorkflowRecord",
    "WorkflowRunRecord",
    "WorkflowStepRecord",
    "WorkflowVersionRecord",
    "WorkspaceLeaseRecord",
]
