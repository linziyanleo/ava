"""Periodic SQLite data retention — prune old rows from append-only tables."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from loguru import logger

FINISHED_STATUSES = ("succeeded", "failed", "cancelled", "interrupted", "skipped")


class RetentionManager:
    """Delete old rows from token_usage, trace_spans, bg_tasks/events, and audit_entries."""

    def __init__(
        self,
        db: Any,
        *,
        token_usage_days: int = 30,
        trace_spans_days: int = 14,
        bg_tasks_days: int = 30,
        audit_days: int = 90,
        vacuum_threshold: int = 10000,
    ) -> None:
        self._db = db
        self._token_usage_days = token_usage_days
        self._trace_spans_days = trace_spans_days
        self._bg_tasks_days = bg_tasks_days
        self._audit_days = audit_days
        self._vacuum_threshold = vacuum_threshold

    def run_cleanup(self) -> dict[str, int]:
        total_deleted = 0
        result: dict[str, int] = {}

        result["token_usage"] = self._prune_token_usage()
        result["trace_spans"] = self._prune_trace_spans()
        result["bg_task_events"] = self._prune_bg_task_events()
        result["bg_tasks"] = self._prune_bg_tasks()
        result["audit_entries"] = self._prune_audit_entries()

        total_deleted = sum(result.values())
        if total_deleted > 0:
            logger.info(
                "Retention cleanup: deleted {} rows ({})",
                total_deleted,
                ", ".join(f"{k}={v}" for k, v in result.items() if v > 0),
            )
        if total_deleted >= self._vacuum_threshold:
            try:
                self._db.execute("VACUUM")
                logger.info("Retention: VACUUM executed after deleting {} rows", total_deleted)
            except Exception as exc:
                logger.warning("Retention: VACUUM failed: {}", exc)

        return result

    def _prune_token_usage(self) -> int:
        cutoff = _iso_cutoff(self._token_usage_days)
        return self._delete_and_count(
            "DELETE FROM token_usage WHERE timestamp < ?", (cutoff,)
        )

    def _prune_trace_spans(self) -> int:
        cutoff_ns = _ns_cutoff(self._trace_spans_days)
        return self._delete_and_count(
            "DELETE FROM trace_spans WHERE end_ns IS NOT NULL AND end_ns < ?",
            (cutoff_ns,),
        )

    def _prune_bg_tasks(self) -> int:
        cutoff_ts = time.time() - (self._bg_tasks_days * 86400)
        placeholders = ",".join("?" for _ in FINISHED_STATUSES)
        return self._delete_and_count(
            f"DELETE FROM bg_tasks WHERE status IN ({placeholders}) AND finished_at < ?",
            (*FINISHED_STATUSES, cutoff_ts),
        )

    def _prune_bg_task_events(self) -> int:
        cutoff_ts = time.time() - (self._bg_tasks_days * 86400)
        placeholders = ",".join("?" for _ in FINISHED_STATUSES)
        return self._delete_and_count(
            f"""DELETE FROM bg_task_events WHERE task_id IN (
                SELECT task_id FROM bg_tasks
                WHERE status IN ({placeholders}) AND finished_at < ?
            )""",
            (*FINISHED_STATUSES, cutoff_ts),
        )

    def _prune_audit_entries(self) -> int:
        cutoff = _iso_cutoff(self._audit_days)
        return self._delete_and_count(
            "DELETE FROM audit_entries WHERE timestamp < ?", (cutoff,)
        )

    def _delete_and_count(self, sql: str, params: tuple) -> int:
        try:
            cursor = self._db.execute(sql, params)
            self._db.commit()
            return cursor.rowcount if hasattr(cursor, "rowcount") else 0
        except Exception as exc:
            logger.warning("Retention delete failed: {}", exc)
            return 0

    async def schedule_periodic(self, interval_hours: int = 24) -> None:
        while True:
            try:
                self.run_cleanup()
            except Exception as exc:
                logger.warning("Retention periodic cleanup error: {}", exc)
            await asyncio.sleep(interval_hours * 3600)


def _iso_cutoff(days: int) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=days)
    return dt.isoformat()


def _ns_cutoff(days: int) -> int:
    return int((time.time() - days * 86400) * 1_000_000_000)
