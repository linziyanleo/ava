"""Token usage statistics collector — records per-call LLM usage to SQLite (or legacy JSON file)."""

from __future__ import annotations

import json
import threading
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

@dataclass
class TokenUsageRecord:
    """A single LLM call's token usage with context."""

    timestamp: str
    model: str
    provider: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    session_key: str = ""
    conversation_id: str = ""
    turn_seq: int | None = None
    iteration: int = 0
    user_message: str = ""
    output_content: str = ""
    system_prompt_preview: str = ""
    conversation_history: str = ""
    full_request_payload: str = ""
    finish_reason: str = ""
    model_role: str = "default"
    cached_tokens: int = 0
    cache_creation_tokens: int = 0
    cost_usd: float = 0.0
    current_turn_tokens: int = 0
    tool_names: str = ""

class TokenStatsCollector:
    """Collects per-call LLM token usage.

    Primary backend: SQLite (via Database instance).
    Fallback: legacy JSON file for backward compatibility.
    """

    def __init__(
        self,
        data_dir: Path,
        max_records: int = 10000,
        db: Any | None = None,
    ):
        self._data_dir = data_dir
        self._max_records = max_records
        self._db = db

        # Legacy JSON fallback fields
        self._records: list[TokenUsageRecord] = []
        self._lock = threading.Lock()
        self._dirty = False
        self._file = data_dir / "token_stats.json"
        self._last_mtime: float = 0.0
        self._iteration_backfilled: set[str] = set()
        if not self._use_db:
            self._load()

    @property
    def _use_db(self) -> bool:
        return self._db is not None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record(
        self,
        model: str,
        provider: str,
        usage: dict[str, Any],
        session_key: str = "",
        conversation_id: str = "",
        turn_seq: int | None = None,
        iteration: int = 0,
        user_message: str = "",
        output_content: str = "",
        system_prompt: str = "",
        conversation_history: str = "",
        full_request_payload: str = "",
        finish_reason: str = "",
        model_role: str = "default",
        cost_usd: float = 0.0,
        # Pre-resolved token counts — if provided, skip internal re-parsing from usage dict
        cached_tokens: int | None = None,
        cache_creation_tokens: int | None = None,
        current_turn_tokens: int = 0,
        tool_names: str = "",
    ) -> int | None:
        """Append a single LLM call record. Returns the inserted row id (DB mode) or None."""
        ts = datetime.now().isoformat()
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", 0) or (prompt_tokens + completion_tokens)

        if cached_tokens is None:
            prompt_details = usage.get("prompt_tokens_details")
            if isinstance(prompt_details, dict):
                cached_tokens = int(prompt_details.get("cached_tokens", 0) or 0)
            else:
                cached_tokens = int(usage.get("cache_read_input_tokens", 0) or 0)
        if cache_creation_tokens is None:
            cache_creation_tokens = int(usage.get("cache_creation_input_tokens", 0) or 0)

        if self._use_db:
            self._db.execute(
                """INSERT INTO token_usage
                   (timestamp, model, provider, prompt_tokens, completion_tokens, total_tokens,
                    session_key, conversation_id, turn_seq, iteration, user_message, output_content,
                    system_prompt_preview, conversation_history, full_request_payload, finish_reason,
                    model_role, cached_tokens, cache_creation_tokens, cost_usd, current_turn_tokens,
                    tool_names)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    ts, model, provider, prompt_tokens, completion_tokens, total_tokens,
                    session_key, conversation_id, turn_seq, iteration, user_message, output_content,
                    system_prompt, conversation_history, full_request_payload, finish_reason,
                    model_role, cached_tokens, cache_creation_tokens, cost_usd, current_turn_tokens,
                    tool_names,
                ),
            )
            self._db.commit()
            row = self._db.fetchone("SELECT last_insert_rowid() as id")
            return row["id"] if row else None

        rec = TokenUsageRecord(
            timestamp=ts,
            model=model,
            provider=provider,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            session_key=session_key,
            conversation_id=conversation_id,
            turn_seq=turn_seq,
            iteration=iteration,
            user_message=user_message,
            output_content=output_content,
            system_prompt_preview=system_prompt,
            conversation_history=conversation_history,
            full_request_payload=full_request_payload,
            finish_reason=finish_reason,
            model_role=model_role,
            cached_tokens=cached_tokens,
            cache_creation_tokens=cache_creation_tokens,
            cost_usd=cost_usd,
            tool_names=tool_names,
        )
        with self._lock:
            self._records.append(rec)
            self._dirty = True
            if len(self._records) > self._max_records:
                self._records = self._records[-self._max_records:]
        self.flush()

    def update_record(self, record_id: int, **fields) -> None:
        """Update specific fields of an existing token_usage record by id (DB mode only)."""
        if not self._use_db or not fields:
            return
        allowed = {
            "prompt_tokens", "completion_tokens", "total_tokens",
            "user_message", "output_content", "system_prompt_preview",
            "conversation_history", "finish_reason", "model_role",
            "cached_tokens", "cache_creation_tokens", "cost_usd",
            "current_turn_tokens", "tool_names",
        }
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        params = list(updates.values()) + [record_id]
        self._db.execute(f"UPDATE token_usage SET {set_clause} WHERE id = ?", params)
        self._db.commit()

    def _ensure_turn_seq(self, session_key: str | None) -> None:
        if not self._use_db or not session_key:
            return

        row = self._db.fetchone(
            "SELECT 1 as needs_backfill FROM token_usage WHERE session_key = ? AND turn_seq IS NULL LIMIT 1",
            (session_key,),
        )
        if not row:
            return

        backfill = getattr(self._db, "backfill_turn_seq", None)
        if callable(backfill):
            backfill(session_key=session_key)

    def _ensure_iteration(self, session_key: str | None, conversation_id: str | None = None) -> None:
        if not self._use_db or not session_key:
            return

        scope_key = session_key if conversation_id is None else f"{session_key}::{conversation_id}"
        if scope_key in self._iteration_backfilled or session_key in self._iteration_backfilled:
            return

        self._ensure_turn_seq(session_key)

        clauses = ["session_key = ?", "turn_seq IS NOT NULL"]
        params: list[Any] = [session_key]
        if conversation_id is not None:
            clauses.append("conversation_id = ?")
            params.append(conversation_id)

        row = self._db.fetchone(
            f"""
            SELECT 1 AS needs_backfill
              FROM token_usage
             WHERE {" AND ".join(clauses)}
             GROUP BY conversation_id, turn_seq
            HAVING COUNT(*) > 1 AND COALESCE(MAX(iteration), 0) = 0
             LIMIT 1
            """,
            tuple(params),
        )
        if not row:
            self._iteration_backfilled.add(scope_key)
            return

        backfill = getattr(self._db, "backfill_iteration", None)
        if callable(backfill):
            updated = backfill(session_key=session_key)
            logger.info("Backfilled iteration for {} token_usage records in session {}", updated, session_key)
        self._iteration_backfilled.add(session_key)

    def _build_filter(
        self,
        session_key: str | None = None,
        conversation_id: str | None = None,
        model: str | None = None,
        provider: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        turn_seq: int | None = None,
        model_role: str | None = None,
    ) -> tuple[str, list]:
        """Build SQL WHERE clause and params from optional filters."""
        clauses: list[str] = []
        params: list = []
        if session_key:
            clauses.append("session_key = ?")
            params.append(session_key)
        if conversation_id is not None:
            clauses.append("conversation_id = ?")
            params.append(conversation_id)
        if model:
            clauses.append("model LIKE ?")
            params.append(f"%{model}%")
        if provider:
            clauses.append("provider LIKE ?")
            params.append(f"%{provider}%")
        if start_time:
            clauses.append("timestamp >= ?")
            params.append(start_time)
        if end_time:
            clauses.append("timestamp <= ?")
            params.append(end_time)
        if turn_seq is not None:
            clauses.append("turn_seq = ?")
            params.append(turn_seq)
        if model_role:
            if model_role == "coder":
                # coder: any background coding tool (claude_code + codex)
                clauses.append(
                    "(model_role IN (?, ?) OR provider IN (?, ?))"
                )
                params.extend(["claude_code", "codex", "claude-code-cli", "codex-cli"])
            elif model_role == "claude_code":
                # legacy: claude_code only (kept for backwards deep-link compatibility)
                clauses.append("(model_role = ? OR provider = ?)")
                params.append("claude_code")
                params.append("claude-code-cli")
            elif model_role == "chat":
                # main chat: model_role=chat OR model_role=main OR model_role=default
                clauses.append("(model_role = ? OR model_role = ? OR model_role = ?)")
                params.append("chat")
                params.append("main")
                params.append("default")
            else:
                clauses.append("model_role = ?")
                params.append(model_role)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        return where, params

    def get_records(
        self,
        limit: int = 100,
        offset: int = 0,
        session_key: str | None = None,
        conversation_id: str | None = None,
        model: str | None = None,
        provider: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        turn_seq: int | None = None,
        model_role: str | None = None,
    ) -> list[dict[str, Any]]:
        if self._use_db:
            self._ensure_turn_seq(session_key)
            self._ensure_iteration(session_key, conversation_id)
            where, params = self._build_filter(session_key, conversation_id, model, provider, start_time, end_time, turn_seq, model_role)
            rows = self._db.fetchall(
                f"SELECT * FROM token_usage{where} ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                (*params, limit, offset),
            )
            return [dict(r) for r in rows]

        self._reload_if_changed()
        with self._lock:
            filtered = self._records
            if session_key:
                filtered = [r for r in filtered if getattr(r, "session_key", "") == session_key]
            if conversation_id is not None:
                filtered = [r for r in filtered if getattr(r, "conversation_id", "") == conversation_id]
            if model:
                filtered = [r for r in filtered if model.lower() in getattr(r, "model", "").lower()]
            if provider:
                filtered = [r for r in filtered if provider.lower() in getattr(r, "provider", "").lower()]
            if start_time:
                filtered = [r for r in filtered if getattr(r, "timestamp", "") >= start_time]
            if end_time:
                filtered = [r for r in filtered if getattr(r, "timestamp", "") <= end_time]
            if turn_seq is not None:
                filtered = [r for r in filtered if getattr(r, "turn_seq", None) == turn_seq]
            if model_role:
                if model_role == "coder":
                    filtered = [r for r in filtered if getattr(r, "model_role", "") in ("claude_code", "codex") or getattr(r, "provider", "") in ("claude-code-cli", "codex-cli")]
                elif model_role == "claude_code":
                    filtered = [r for r in filtered if getattr(r, "model_role", "") == "claude_code" or getattr(r, "provider", "") == "claude-code-cli"]
                elif model_role == "chat":
                    filtered = [r for r in filtered if getattr(r, "model_role", "") in ("chat", "main", "default")]
                else:
                    filtered = [r for r in filtered if getattr(r, "model_role", "") == model_role]
            reversed_records = list(reversed(filtered))
            sliced = reversed_records[offset: offset + limit]
            return [asdict(r) for r in sliced]

    def get_total_count(
        self,
        session_key: str | None = None,
        conversation_id: str | None = None,
        model: str | None = None,
        provider: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        turn_seq: int | None = None,
        model_role: str | None = None,
    ) -> int:
        if self._use_db:
            self._ensure_turn_seq(session_key)
            self._ensure_iteration(session_key, conversation_id)
            where, params = self._build_filter(session_key, conversation_id, model, provider, start_time, end_time, turn_seq, model_role)
            row = self._db.fetchone(f"SELECT COUNT(*) as cnt FROM token_usage{where}", tuple(params))
            return row["cnt"] if row else 0

        self._reload_if_changed()
        with self._lock:
            filtered = self._records
            if session_key:
                filtered = [r for r in filtered if getattr(r, "session_key", "") == session_key]
            if conversation_id is not None:
                filtered = [r for r in filtered if getattr(r, "conversation_id", "") == conversation_id]
            if model:
                filtered = [r for r in filtered if model.lower() in getattr(r, "model", "").lower()]
            if provider:
                filtered = [r for r in filtered if provider.lower() in getattr(r, "provider", "").lower()]
            if start_time:
                filtered = [r for r in filtered if getattr(r, "timestamp", "") >= start_time]
            if end_time:
                filtered = [r for r in filtered if getattr(r, "timestamp", "") <= end_time]
            if turn_seq is not None:
                filtered = [r for r in filtered if getattr(r, "turn_seq", None) == turn_seq]
            if model_role:
                if model_role == "coder":
                    filtered = [r for r in filtered if getattr(r, "model_role", "") in ("claude_code", "codex") or getattr(r, "provider", "") in ("claude-code-cli", "codex-cli")]
                elif model_role == "claude_code":
                    filtered = [r for r in filtered if getattr(r, "model_role", "") == "claude_code" or getattr(r, "provider", "") == "claude-code-cli"]
                elif model_role == "chat":
                    filtered = [r for r in filtered if getattr(r, "model_role", "") in ("chat", "main", "default")]
                else:
                    filtered = [r for r in filtered if getattr(r, "model_role", "") == model_role]
            return len(filtered)

    def get_summary(self) -> dict[str, Any]:
        return {
            "totals": self.get_totals(),
            "by_model": self.get_by_model(),
            "by_provider": self.get_by_provider(),
        }

    def get_totals(self) -> dict[str, int]:
        if self._use_db:
            row = self._db.fetchone(
                """SELECT COALESCE(SUM(prompt_tokens),0) as prompt_tokens,
                          COALESCE(SUM(completion_tokens),0) as completion_tokens,
                          COALESCE(SUM(total_tokens),0) as total_tokens,
                          COUNT(*) as total_calls
                   FROM token_usage"""
            )
            return dict(row) if row else {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "total_calls": 0}

        with self._lock:
            prompt = sum(r.prompt_tokens for r in self._records)
            completion = sum(r.completion_tokens for r in self._records)
            total = sum(r.total_tokens for r in self._records)
            return {
                "prompt_tokens": prompt,
                "completion_tokens": completion,
                "total_tokens": total,
                "total_calls": len(self._records),
            }

    def get_by_model(self) -> list[dict[str, Any]]:
        if self._use_db:
            rows = self._db.fetchall(
                """SELECT model,
                          SUM(prompt_tokens) as prompt_tokens,
                          SUM(completion_tokens) as completion_tokens,
                          SUM(total_tokens) as total_tokens,
                          COUNT(*) as calls
                   FROM token_usage GROUP BY model
                   ORDER BY total_tokens DESC"""
            )
            return [dict(r) for r in rows]

        with self._lock:
            agg: dict[str, dict[str, int]] = defaultdict(
                lambda: {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "calls": 0}
            )
            for r in self._records:
                d = agg[r.model]
                d["prompt_tokens"] += r.prompt_tokens
                d["completion_tokens"] += r.completion_tokens
                d["total_tokens"] += r.total_tokens
                d["calls"] += 1
            return [{"model": k, **v} for k, v in sorted(agg.items(), key=lambda x: -x[1]["total_tokens"])]

    def get_by_provider(self) -> list[dict[str, Any]]:
        if self._use_db:
            rows = self._db.fetchall(
                """SELECT provider,
                          SUM(prompt_tokens) as prompt_tokens,
                          SUM(completion_tokens) as completion_tokens,
                          SUM(total_tokens) as total_tokens,
                          COUNT(*) as calls
                   FROM token_usage GROUP BY provider
                   ORDER BY total_tokens DESC"""
            )
            return [dict(r) for r in rows]

        with self._lock:
            agg: dict[str, dict[str, int]] = defaultdict(
                lambda: {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "calls": 0}
            )
            for r in self._records:
                d = agg[r.provider]
                d["prompt_tokens"] += r.prompt_tokens
                d["completion_tokens"] += r.completion_tokens
                d["total_tokens"] += r.total_tokens
                d["calls"] += 1
            return [{"provider": k, **v} for k, v in sorted(agg.items(), key=lambda x: -x[1]["total_tokens"])]

    def get_timeline(self, interval: str = "hour") -> list[dict[str, Any]]:
        if self._use_db:
            fmt = "%Y-%m-%d %H:00" if interval != "day" else "%Y-%m-%d"
            rows = self._db.fetchall(
                f"""SELECT strftime('{fmt}', timestamp) as time,
                           SUM(prompt_tokens) as prompt_tokens,
                           SUM(completion_tokens) as completion_tokens,
                           SUM(total_tokens) as total_tokens,
                           COUNT(*) as calls
                    FROM token_usage
                    GROUP BY 1 ORDER BY 1"""
            )
            return [dict(r) for r in rows]

        self._reload_if_changed()
        with self._lock:
            buckets: dict[str, dict[str, int]] = defaultdict(
                lambda: {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "calls": 0}
            )
            for r in self._records:
                try:
                    dt = datetime.fromisoformat(r.timestamp)
                except ValueError:
                    continue
                if interval == "day":
                    key = dt.strftime("%Y-%m-%d")
                else:
                    key = dt.strftime("%Y-%m-%d %H:00")
                d = buckets[key]
                d["prompt_tokens"] += r.prompt_tokens
                d["completion_tokens"] += r.completion_tokens
                d["total_tokens"] += r.total_tokens
                d["calls"] += 1
            return [{"time": k, **v} for k, v in sorted(buckets.items())]

    def get_by_session(self, session_key: str, conversation_id: str | None = None) -> list[dict[str, Any]]:
        """Per-turn token aggregation for a given session."""
        if self._use_db:
            self._ensure_turn_seq(session_key)
            self._ensure_iteration(session_key, conversation_id)
            where = "WHERE session_key = ?"
            params: list[Any] = [session_key]
            if conversation_id is not None:
                where += " AND conversation_id = ?"
                params.append(conversation_id)
            rows = self._db.fetchall(
                f"""SELECT conversation_id, turn_seq,
                          SUM(prompt_tokens) as prompt_tokens,
                          SUM(completion_tokens) as completion_tokens,
                          SUM(total_tokens) as total_tokens,
                          COUNT(*) as llm_calls,
                          GROUP_CONCAT(DISTINCT model) as models
                   FROM token_usage
                   {where}
                   GROUP BY conversation_id, turn_seq
                   ORDER BY conversation_id, turn_seq""",
                tuple(params),
            )
            return [dict(r) for r in rows]

        self._reload_if_changed()
        with self._lock:
            buckets: dict[tuple[str, int | None], dict[str, Any]] = defaultdict(
                lambda: {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "llm_calls": 0, "models": set()}
            )
            for r in self._records:
                if r.session_key != session_key:
                    continue
                if conversation_id is not None and getattr(r, "conversation_id", "") != conversation_id:
                    continue
                bucket_key = (getattr(r, "conversation_id", ""), r.turn_seq)
                d = buckets[bucket_key]
                d["prompt_tokens"] += r.prompt_tokens
                d["completion_tokens"] += r.completion_tokens
                d["total_tokens"] += r.total_tokens
                d["llm_calls"] += 1
                d["models"].add(r.model)
            return [
                {
                    "conversation_id": conv_id,
                    "turn_seq": turn_seq,
                    **{kk: (", ".join(sorted(vv)) if kk == "models" else vv) for kk, vv in v.items()},
                }
                for (conv_id, turn_seq), v in sorted(buckets.items(), key=lambda x: (x[0][0], x[0][1] is None, x[0][1]))
            ]

    def get_by_session_detailed(self, session_key: str, conversation_id: str | None = None) -> list[dict[str, Any]]:
        """Per-iteration token records for a given session (no aggregation)."""
        if self._use_db:
            self._ensure_turn_seq(session_key)
            self._ensure_iteration(session_key, conversation_id)
            where = "WHERE session_key = ?"
            params: list[Any] = [session_key]
            if conversation_id is not None:
                where += " AND conversation_id = ?"
                params.append(conversation_id)
            rows = self._db.fetchall(
                f"""SELECT conversation_id, turn_seq, iteration,
                          prompt_tokens, completion_tokens, total_tokens,
                          cached_tokens, cache_creation_tokens,
                          model, model_role, tool_names, finish_reason
                   FROM token_usage
                   {where}
                   ORDER BY conversation_id, turn_seq, iteration""",
                tuple(params),
            )
            return [dict(r) for r in rows]

        self._reload_if_changed()
        with self._lock:
            results = []
            for r in self._records:
                if r.session_key != session_key:
                    continue
                if conversation_id is not None and getattr(r, "conversation_id", "") != conversation_id:
                    continue
                results.append({
                    "conversation_id": getattr(r, "conversation_id", ""),
                    "turn_seq": r.turn_seq,
                    "iteration": r.iteration,
                    "prompt_tokens": r.prompt_tokens,
                    "completion_tokens": r.completion_tokens,
                    "total_tokens": r.total_tokens,
                    "cached_tokens": r.cached_tokens,
                    "cache_creation_tokens": r.cache_creation_tokens,
                    "model": r.model,
                    "model_role": r.model_role,
                    "tool_names": r.tool_names,
                    "finish_reason": r.finish_reason,
                })
            results.sort(key=lambda x: (x["conversation_id"], x["turn_seq"] is None, x["turn_seq"] or 0, x["iteration"]))
            return results

    def reset(self) -> None:
        if self._use_db:
            self._db.execute("DELETE FROM token_usage")
            self._db.commit()
            self._iteration_backfilled.clear()
            return

        with self._lock:
            self._records.clear()
            self._dirty = True
        self.flush()

    def flush(self) -> None:
        """Persist current records to disk (legacy JSON mode only)."""
        if self._use_db:
            return
        with self._lock:
            if not self._dirty:
                return
            data = [asdict(r) for r in self._records]
            self._dirty = False

        try:
            self._data_dir.mkdir(parents=True, exist_ok=True)
            with open(self._file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=None)
            self._last_mtime = self._file.stat().st_mtime
        except Exception as e:
            logger.warning("Failed to flush token stats: {}", e)

    # ------------------------------------------------------------------
    # Internal (legacy JSON)
    # ------------------------------------------------------------------

    def _reload_if_changed(self) -> None:
        if self._use_db:
            return
        try:
            if not self._file.exists():
                return
            mtime = self._file.stat().st_mtime
            if mtime <= self._last_mtime:
                return
        except OSError:
            return
        with self._lock:
            if not self._dirty:
                self._records.clear()
                self._load_inner()

    def _load(self) -> None:
        self._load_inner()

    def _load_inner(self) -> None:
        if not self._file.exists():
            return
        try:
            self._last_mtime = self._file.stat().st_mtime
            with open(self._file, encoding="utf-8") as f:
                raw = json.load(f)
            if not isinstance(raw, list):
                return
            for item in raw:
                if not isinstance(item, dict):
                    continue
                self._records.append(TokenUsageRecord(
                    timestamp=item.get("timestamp", ""),
                    model=item.get("model", ""),
                    provider=item.get("provider", ""),
                    prompt_tokens=item.get("prompt_tokens", 0),
                    completion_tokens=item.get("completion_tokens", 0),
                    total_tokens=item.get("total_tokens", 0),
                    session_key=item.get("session_key", ""),
                    turn_seq=item.get("turn_seq"),
                    iteration=item.get("iteration", 0),
                    user_message=item.get("user_message", ""),
                    output_content=item.get("output_content", ""),
                    system_prompt_preview=item.get("system_prompt_preview", ""),
                    conversation_history=item.get("conversation_history", ""),
                    full_request_payload=item.get("full_request_payload", ""),
                    finish_reason=item.get("finish_reason", ""),
                    model_role=item.get("model_role", "default"),
                    cached_tokens=item.get("cached_tokens", 0),
                    cache_creation_tokens=item.get("cache_creation_tokens", 0),
                    cost_usd=item.get("cost_usd", 0.0),
                ))
            if len(self._records) > self._max_records:
                self._records = self._records[-self._max_records:]
            logger.info("Loaded {} token stats records from disk", len(self._records))
        except Exception as e:
            logger.warning("Failed to load token stats: {}", e)
