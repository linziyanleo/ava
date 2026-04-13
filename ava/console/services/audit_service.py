"""Audit logging with SQLite backend (or legacy JSONL fallback)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ava.console.models import AuditEntry


class AuditService:
    def __init__(self, console_dir: Path, db: Any | None = None):
        self._file = console_dir / "audit.jsonl"
        console_dir.mkdir(parents=True, exist_ok=True)
        self._db = db

    @property
    def _use_db(self) -> bool:
        return self._db is not None

    def log(
        self,
        user: str,
        role: str,
        action: str,
        target: str,
        detail: dict | None = None,
        ip: str = "",
    ) -> None:
        ts = datetime.now(timezone.utc).isoformat()

        if self._use_db:
            self._db.execute(
                """INSERT INTO audit_entries
                   (timestamp, user, role, action, target, detail, ip)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    ts, user, role, action, target,
                    json.dumps(detail, ensure_ascii=False) if detail else None,
                    ip,
                ),
            )
            self._db.commit()
            return

        entry = AuditEntry(
            ts=ts,
            user=user,
            role=role,
            action=action,
            target=target,
            detail=detail,
            ip=ip,
        )
        with open(self._file, "a", encoding="utf-8") as f:
            f.write(entry.model_dump_json() + "\n")

    def query(
        self,
        page: int = 1,
        size: int = 50,
        user: str | None = None,
        action: str | None = None,
    ) -> dict[str, Any]:
        if self._use_db:
            return self._query_db(page, size, user, action)
        return self._query_jsonl(page, size, user, action)

    def _query_db(
        self, page: int, size: int, user: str | None, action: str | None
    ) -> dict[str, Any]:
        conditions: list[str] = []
        params: list[Any] = []
        if user:
            conditions.append("user = ?")
            params.append(user)
        if action:
            conditions.append("action = ?")
            params.append(action)

        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""

        total_row = self._db.fetchone(f"SELECT COUNT(*) as cnt FROM audit_entries{where}", tuple(params))
        total = total_row["cnt"] if total_row else 0

        offset = (page - 1) * size
        params_page = params + [size, offset]
        rows = self._db.fetchall(
            f"""SELECT * FROM audit_entries{where}
                ORDER BY timestamp DESC LIMIT ? OFFSET ?""",
            tuple(params_page),
        )

        entries = []
        for r in rows:
            detail = None
            if r["detail"]:
                try:
                    detail = json.loads(r["detail"])
                except json.JSONDecodeError:
                    pass
            entries.append(AuditEntry(
                ts=r["timestamp"],
                user=r["user"],
                role=r["role"],
                action=r["action"],
                target=r["target"],
                detail=detail,
                ip=r["ip"] or "",
            ).model_dump())

        return {"entries": entries, "total": total, "page": page, "size": size}

    def _query_jsonl(
        self, page: int, size: int, user: str | None, action: str | None
    ) -> dict[str, Any]:
        if not self._file.exists():
            return {"entries": [], "total": 0, "page": page, "size": size}

        all_entries: list[AuditEntry] = []
        for line in self._file.read_text("utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = AuditEntry.model_validate_json(line)
                if user and entry.user != user:
                    continue
                if action and entry.action != action:
                    continue
                all_entries.append(entry)
            except Exception:
                continue

        all_entries.reverse()
        total = len(all_entries)
        start = (page - 1) * size
        page_entries = all_entries[start: start + size]

        return {
            "entries": [e.model_dump() for e in page_entries],
            "total": total,
            "page": page,
            "size": size,
        }
