"""Monkey patch to inject ava capabilities into AgentLoop.

Injected attributes (after __init__):
  - self.db                      — shared Database instance (from storage_patch)
  - self.token_stats             — TokenStatsCollector instance
  - self.media_service           — MediaService instance (for image_gen tool)
  - self.categorized_memory      — CategorizedMemoryStore instance
  - self.history_summarizer      — HistorySummarizer instance
  - self.history_compressor      — HistoryCompressor instance
  - self.context._agent_loop     — back-reference for context_patch to access loop
  - self._current_session_key    — correct session_key for current turn (fixes console routing)

Also patches _process_message to record token usage after each turn,
and broadcasts observe events via MessageBus for real-time Console updates.

Execution order note:
  storage_patch runs after this (s > l alphabetically).
  We handle _shared_db being None by constructing a fallback Database.
  storage_patch later calls set_shared_db() which will be used by
  newly created AgentLoop instances.
"""

from __future__ import annotations

import weakref
from datetime import datetime, timezone
from uuid import uuid4

from loguru import logger

from ava.launcher import register_patch


# Module-level shared db reference (set by storage_patch after us)
_shared_db = None
# Module-level reference to the most recently created AgentLoop (for console_patch)
_agent_loop_ref: weakref.ReferenceType | None = None


def set_shared_db(db) -> None:
    """Called by storage_patch to share the Database instance."""
    global _shared_db
    _shared_db = db


def get_agent_loop():
    """Return the most recently created AgentLoop instance (or None)."""
    return _agent_loop_ref() if _agent_loop_ref is not None else None


def _get_or_create_db(workspace_path) -> object | None:
    """Return _shared_db if available, otherwise create a fresh Database."""
    if _shared_db is not None:
        return _shared_db
    try:
        from ava.storage import Database
        from nanobot.config.paths import get_data_dir
        db_path = get_data_dir() / "nanobot.db"
        return Database(db_path)
    except Exception as exc:
        logger.warning("Failed to create fallback Database: {}", exc)
        return None


def _new_conversation_id() -> str:
    return f"conv_{uuid4().hex[:12]}"


def _ensure_session_conversation_id(session, *, rotate: bool = False) -> tuple[str, bool]:
    metadata = getattr(session, "metadata", None)
    if not isinstance(metadata, dict):
        metadata = {}
        session.metadata = metadata

    current = metadata.get("conversation_id")
    if rotate or not isinstance(current, str) or not current:
        current = _new_conversation_id()
        metadata["conversation_id"] = current
        return current, True

    return current, False


def _is_new_command(raw: str) -> bool:
    stripped = (raw or "").strip().lower()
    if not stripped.startswith("/"):
        return False
    return (stripped[1:].split() or [""])[0] == "new"


def _split_session_key(session_key: str | None) -> tuple[str | None, str | None]:
    if not session_key or ":" not in session_key:
        return None, None
    return session_key.split(":", 1)


def _get_latest_history_entry(store, previous_cursor: int | None) -> str:
    try:
        last_entry = store._read_last_entry()
    except Exception:
        return ""

    if not isinstance(last_entry, dict):
        return ""

    cursor = last_entry.get("cursor")
    if isinstance(previous_cursor, int) and isinstance(cursor, int) and cursor <= previous_cursor:
        return ""

    content = last_entry.get("content")
    return content if isinstance(content, str) else ""


def _get_snapshot_content_max_chars() -> int:
    """Read the configured snapshot truncation limit with a safe fallback."""
    default_limit = 3000
    try:
        from nanobot.config.loader import load_config

        cfg = load_config()
        raw_limit = getattr(getattr(cfg, "token_stats", None), "snapshot_content_max_chars", default_limit)
        limit = int(raw_limit)
        return limit if limit > 0 else default_limit
    except Exception:
        return default_limit


def _sync_categorized_memory(consolidator, session_key: str | None, history_entry: str) -> None:
    if not session_key or not history_entry:
        return

    channel, chat_id = _split_session_key(session_key)
    if not channel or not chat_id:
        return

    loop_ref = getattr(consolidator, "_ava_agent_loop_ref", None)
    loop = loop_ref() if loop_ref else None
    categorized_memory = getattr(loop, "categorized_memory", None) if loop else None
    if categorized_memory is None:
        return

    try:
        categorized_memory.on_consolidate(channel, chat_id, history_entry, "")
    except Exception as exc:
        logger.warning("Failed to sync categorized memory for {}: {}", session_key, exc)


def _register_bg_task_commands(router, bg_store) -> None:
    """Register /task, /task_cancel, /cc_status into upstream CommandRouter."""
    from nanobot.bus.events import OutboundMessage

    async def cmd_task(ctx):
        parts = ctx.raw.strip().split()
        task_id = None
        verbose = False
        for token in parts[1:]:
            low = token.lower()
            if low in {"-v", "--verbose", "verbose"}:
                verbose = True
            elif task_id is None:
                task_id = token

        snapshot = bg_store.get_status(
            task_id=task_id,
            session_key=None if task_id else ctx.key,
        )
        if task_id and snapshot["total"] == 0:
            content = f"Task '{task_id}' not found."
        elif snapshot["total"] == 0:
            content = "No background tasks."
        else:
            lines = [
                f"Background Tasks: {snapshot['running']} running / {snapshot['total']} tracked",
            ]
            visible = snapshot["tasks"] if (verbose or task_id) else snapshot["tasks"][:5]
            for item in visible:
                elapsed = item.get("elapsed_ms", 0)
                lines.append(
                    f"- [{item['task_type']}:{item['task_id']}] {item['status']} ({elapsed}ms)"
                )
                if item.get("error_message"):
                    lines.append(f"  error: {str(item['error_message'])[:200]}")
                if verbose and item.get("prompt_preview"):
                    lines.append(f"  prompt: {item['prompt_preview']}")
                if verbose and item.get("timeline"):
                    for evt in item["timeline"][-5:]:
                        lines.append(f"  [{evt['event']}] {evt.get('detail', '')[:80]}")
            if not (verbose or task_id) and snapshot["total"] > len(visible):
                lines.append(f"... {snapshot['total'] - len(visible)} more (use /task --verbose)")
            content = "\n".join(lines)

        return OutboundMessage(channel=ctx.msg.channel, chat_id=ctx.msg.chat_id, content=content)

    async def cmd_task_cancel(ctx):
        parts = ctx.raw.strip().split()
        if len(parts) < 2:
            content = "Usage: /task_cancel <task_id>"
        else:
            content = await bg_store.cancel(parts[1])
        return OutboundMessage(channel=ctx.msg.channel, chat_id=ctx.msg.chat_id, content=content)

    async def cmd_stop_with_bg(ctx):
        import asyncio as _asyncio
        loop = ctx.loop
        msg = ctx.msg
        tasks = loop._active_tasks.pop(msg.session_key, [])
        cancelled = sum(1 for t in tasks if not t.done() and t.cancel())
        for t in tasks:
            try:
                await t
            except (_asyncio.CancelledError, Exception):
                pass
        sub_cancelled = await loop.subagents.cancel_by_session(msg.session_key)
        bg_cancelled = await bg_store.cancel_by_session(msg.session_key)
        total = cancelled + sub_cancelled + bg_cancelled
        content = f"Stopped {total} task(s)." if total else "No active task to stop."
        return OutboundMessage(channel=ctx.msg.channel, chat_id=ctx.msg.chat_id, content=content)

    router.exact("/task", cmd_task)
    router.exact("/task_cancel", cmd_task_cancel)
    router.exact("/cc_status", cmd_task)
    router.priority("/stop", cmd_stop_with_bg)


def apply_loop_patch() -> str:
    from nanobot.agent.loop import AgentLoop
    from nanobot.agent.memory import Consolidator

    required_methods = [
        "__init__",
        "_set_tool_context",
        "_run_agent_loop",
        "_save_turn",
        "_process_message",
    ]
    missing = [name for name in required_methods if not hasattr(AgentLoop, name)]
    if missing:
        logger.warning("loop_patch skipped: AgentLoop missing methods {}", missing)
        return f"loop_patch skipped (missing methods: {', '.join(missing)})"

    if getattr(AgentLoop._process_message, "_ava_loop_patched", False):
        return "loop_patch already applied (skipped)"

    # ------------------------------------------------------------------
    # 1. Patch __init__ to inject extra attributes
    # ------------------------------------------------------------------
    original_init = AgentLoop.__init__

    def patched_init(self: AgentLoop, *args, **kwargs) -> None:
        original_init(self, *args, **kwargs)

        # Save ref for console_patch to access the AgentLoop instance
        global _agent_loop_ref
        _agent_loop_ref = weakref.ref(self)

        db = _get_or_create_db(self.workspace)
        self.db = db
        self._current_conversation_id = ""

        # TokenStatsCollector
        try:
            from ava.console.services.token_stats_service import TokenStatsCollector
            from nanobot.config.paths import get_data_dir as _get_data_dir
            stats_data_dir = _get_data_dir()
            stats_data_dir.mkdir(parents=True, exist_ok=True)
            self.token_stats = TokenStatsCollector(data_dir=stats_data_dir, db=db)
        except Exception as exc:
            logger.warning("Failed to init TokenStatsCollector: {}", exc)
            self.token_stats = None

        # MediaService
        try:
            from ava.console.services.media_service import MediaService
            from nanobot.config.paths import get_media_dir as _get_media_dir
            media_dir = _get_media_dir() / "generated"
            self.media_service = MediaService(
                media_dir=media_dir,
                screenshot_dir=media_dir.parent / "screenshots",
                db=db,
            )
        except Exception as exc:
            logger.warning("Failed to init MediaService: {}", exc)
            self.media_service = None

        # CategorizedMemoryStore — 基于身份的分类记忆
        try:
            from ava.agent.categorized_memory import CategorizedMemoryStore
            self.categorized_memory = CategorizedMemoryStore(workspace=self.workspace)
        except Exception as exc:
            logger.warning("Failed to init CategorizedMemoryStore: {}", exc)
            self.categorized_memory = None

        try:
            if hasattr(self, "consolidator"):
                self.consolidator._ava_agent_loop_ref = weakref.ref(self)
        except Exception as exc:
            logger.warning("Failed to attach AgentLoop ref to Consolidator: {}", exc)

        # HistorySummarizer — 旧轮次摘要压缩
        try:
            from ava.agent.history_summarizer import HistorySummarizer
            _protect_recent = (
                getattr(self.config, "get", lambda *a, **kw: None)("history_compressor.protect_recent")
                if hasattr(self, "config") and self.config is not None
                else None
            )
            if _protect_recent is None:
                try:
                    _protect_recent = self.config.history_compressor.protect_recent
                except Exception:
                    _protect_recent = None
            if not isinstance(_protect_recent, int) or _protect_recent < 0:
                _protect_recent = 6
            self.history_summarizer = HistorySummarizer(enabled=True, protect_recent=_protect_recent)
        except Exception as exc:
            logger.warning("Failed to init HistorySummarizer: {}", exc)
            self.history_summarizer = None

        # HistoryCompressor — 基于字符预算的历史裁剪
        try:
            from ava.agent.history_compressor import HistoryCompressor
            _max_chars = (
                getattr(self.config, "get", lambda *a, **kw: None)("history_compressor.max_chars")
                if hasattr(self, "config") and self.config is not None
                else None
            )
            if _max_chars is None:
                try:
                    _max_chars = self.config.history_compressor.max_chars
                except Exception:
                    _max_chars = None
            if not isinstance(_max_chars, int) or _max_chars <= 0:
                _max_chars = 20000
            self.history_compressor = HistoryCompressor(max_chars=_max_chars, recent_turns=10)
        except Exception as exc:
            logger.warning("Failed to init HistoryCompressor: {}", exc)
            self.history_compressor = None

        # BackgroundTaskStore
        try:
            from ava.agent.bg_tasks import BackgroundTaskStore
            self.bg_tasks = BackgroundTaskStore(db=db)
            self.bg_tasks.set_agent_loop(self)
        except Exception as exc:
            logger.warning("Failed to init BackgroundTaskStore: {}", exc)
            self.bg_tasks = None

        # LifecycleManager
        try:
            from ava.runtime.lifecycle import LifecycleManager
            from nanobot.config.loader import load_config as _lc_load
            _lc_cfg = _lc_load()
            _gw_port = getattr(getattr(_lc_cfg, "gateway", None), "port", 18790) or 18790
            _console_port = getattr(
                getattr(getattr(_lc_cfg, "gateway", None), "console", None), "port", 6688
            ) or 6688
            self.lifecycle_manager = LifecycleManager(
                bg_store=getattr(self, "bg_tasks", None),
                gateway_port=_gw_port,
                console_port=_console_port,
            )
            self.lifecycle_manager.initialize()
        except Exception as exc:
            logger.warning("Failed to init LifecycleManager: {}", exc)
            self.lifecycle_manager = None

        # Register /task, /task_cancel, /cc_status into upstream CommandRouter,
        # and override /stop to also cancel bg_tasks.
        if hasattr(self, "commands") and hasattr(self, "bg_tasks") and self.bg_tasks:
            _register_bg_task_commands(self.commands, self.bg_tasks)

        # Back-reference for context_patch to access loop attributes
        if hasattr(self, "context"):
            self.context._agent_loop = self

        # tools_patch registers tools during original_init (before token_stats/media_service
        # are set), so update those references now that everything is initialized.
        try:
            token_stats = getattr(self, "token_stats", None)
            media_service = getattr(self, "media_service", None)
            if hasattr(self, "tools"):
                if vision_tool := self.tools.get("vision"):
                    if hasattr(vision_tool, "_token_stats"):
                        vision_tool._token_stats = token_stats
                if image_gen_tool := self.tools.get("image_gen"):
                    if hasattr(image_gen_tool, "_token_stats"):
                        image_gen_tool._token_stats = token_stats
                    if hasattr(image_gen_tool, "_media_service"):
                        image_gen_tool._media_service = media_service
                if cc_tool := self.tools.get("claude_code"):
                    if hasattr(cc_tool, "_token_stats"):
                        cc_tool._token_stats = token_stats
                    if hasattr(cc_tool, "_task_store"):
                        cc_tool._task_store = getattr(self, "bg_tasks", None)
                if codex_tool := self.tools.get("codex"):
                    if hasattr(codex_tool, "_token_stats"):
                        codex_tool._token_stats = token_stats
                    if hasattr(codex_tool, "_task_store"):
                        codex_tool._task_store = getattr(self, "bg_tasks", None)
                if pa_tool := self.tools.get("page_agent"):
                    if hasattr(pa_tool, "_token_stats"):
                        pa_tool._token_stats = token_stats
                if gc_tool := self.tools.get("gateway_control"):
                    if hasattr(gc_tool, "_lifecycle"):
                        gc_tool._lifecycle = getattr(self, "lifecycle_manager", None)
        except Exception as exc:
            logger.warning("Failed to update tool refs after init: {}", exc)

    patched_init._ava_loop_patched = True
    AgentLoop.__init__ = patched_init

    # ------------------------------------------------------------------
    # 1b. Patch Consolidator so session-key-aware turns can sync their
    #     archived summary into categorized_memory after append_history().
    # ------------------------------------------------------------------
    original_archive = Consolidator.archive
    original_maybe_consolidate = Consolidator.maybe_consolidate_by_tokens

    async def patched_archive(self, messages):
        previous_cursor = None
        if getattr(self, "_ava_current_session_key", None):
            try:
                last_entry = self.store._read_last_entry()
                if isinstance(last_entry, dict):
                    previous_cursor = last_entry.get("cursor")
            except Exception:
                previous_cursor = None

        result = await original_archive(self, messages)
        if result:
            history_entry = _get_latest_history_entry(self.store, previous_cursor)
            _sync_categorized_memory(
                self,
                getattr(self, "_ava_current_session_key", None),
                history_entry,
            )
        return result

    async def patched_maybe_consolidate_by_tokens(self, session):
        previous_session_key = getattr(self, "_ava_current_session_key", None)
        self._ava_current_session_key = getattr(session, "key", None)
        try:
            return await original_maybe_consolidate(self, session)
        finally:
            self._ava_current_session_key = previous_session_key

    patched_archive._ava_loop_patched = True
    patched_maybe_consolidate_by_tokens._ava_loop_patched = True
    Consolidator.archive = patched_archive
    Consolidator.maybe_consolidate_by_tokens = patched_maybe_consolidate_by_tokens

    # ------------------------------------------------------------------
    # 2. Patch _set_tool_context to propagate channel/chat_id/session_key
    #    to ALL sidecar tools that implement set_context().
    #    session_key comes from self._current_session_key (set by
    #    patched_process_message before upstream calls _set_tool_context).
    #    This fixes the console routing bug where channel="console" +
    #    chat_id=user_id would produce "console:{user_id}" instead of
    #    the correct "console:{session_id}".
    # ------------------------------------------------------------------
    original_set_tool_context = AgentLoop._set_tool_context

    def patched_set_tool_context(self: AgentLoop, channel: str, chat_id: str, message_id: str | None = None) -> None:
        original_set_tool_context(self, channel, chat_id, message_id)
        session_key = getattr(self, "_current_session_key", None) or f"{channel}:{chat_id}"
        for tool_name in self.tools.tool_names:
            tool = self.tools.get(tool_name)
            if tool and hasattr(tool, "set_context"):
                try:
                    tool.set_context(channel, chat_id, session_key=session_key)
                except TypeError:
                    tool.set_context(channel, chat_id)

    patched_set_tool_context._ava_loop_patched = True
    AgentLoop._set_tool_context = patched_set_tool_context

    # ------------------------------------------------------------------
    # 3. Patch _run_agent_loop to record token usage per-iteration (immediately).
    #    Each LLM call is written to DB right away so console can show progress
    #    before the turn completes. Tool names are extracted from response.tool_calls.
    #    The first record's id and last record's id are tracked so _process_message
    #    can backfill user_message / output_content after the turn.
    # ------------------------------------------------------------------
    original_run_agent_loop = AgentLoop._run_agent_loop

    async def patched_run_agent_loop(self: AgentLoop, initial_messages, **kwargs):
        import json as _json
        from datetime import datetime as _dt

        sk = getattr(self, "_current_session_key", "") or ""
        conversation_id = getattr(self, "_current_conversation_id", "") or ""
        user_msg = getattr(self, "_current_user_message", "") or ""
        turn_seq = getattr(self, "_current_turn_seq", None)

        # === 实时广播 + Phase 0 预记录（LLM 调用前，slash command 已过）===
        self._phase0_record_id = None
        if sk and user_msg:
            bus = getattr(self, "bus", None)
            if bus and hasattr(bus, "dispatch_observe_event"):
                bus.dispatch_observe_event(sk, {
                    "type": "message_arrived",
                    "session_key": sk,
                    "conversation_id": conversation_id,
                    "turn_seq": turn_seq,
                    "role": "user",
                    "content": user_msg[:500],
                    "timestamp": _dt.now().isoformat(),
                })

            token_stats = getattr(self, "token_stats", None)
            if token_stats:
                try:
                    snapshot_limit = _get_snapshot_content_max_chars()
                    conv_history = _json.dumps(
                        [{"role": m.get("role", ""), "content": str(m.get("content", ""))[:snapshot_limit]}
                         for m in initial_messages if m.get("role") != "system"],
                        ensure_ascii=False,
                    )
                except Exception:
                    conv_history = ""
                provider_name = type(self.provider).__name__.lower().replace("provider", "")
                phase0_id = token_stats.record(
                    model=self.model,
                    provider=provider_name,
                    usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                    session_key=sk,
                    conversation_id=conversation_id,
                    turn_seq=turn_seq,
                    user_message=user_msg[:1000],
                    system_prompt=getattr(self, "_last_system_prompt", ""),
                    conversation_history=conv_history,
                    finish_reason="pending",
                    model_role="pending",
                )
                self._phase0_record_id = phase0_id
                if bus and hasattr(bus, "dispatch_observe_event") and phase0_id is not None:
                    bus.dispatch_observe_event(sk, {
                        "type": "token_recorded",
                        "session_key": sk,
                        "record_id": phase0_id,
                        "phase": "pending",
                    })

            if bus and hasattr(bus, "dispatch_observe_event"):
                bus.dispatch_observe_event(sk, {
                    "type": "processing_started",
                    "session_key": sk,
                    "conversation_id": conversation_id,
                    "turn_seq": turn_seq,
                    "model": self.model,
                })

        original_chat = self.provider.chat_with_retry
        original_chat_stream = self.provider.chat_stream_with_retry
        self._turn_record_ids = []
        self._turn_iteration = 0

        def _record_immediately(response):
            """Extract usage + tool names from response and write to DB now."""
            token_stats = getattr(self, "token_stats", None)
            if not token_stats:
                return

            usage_data = _extract_usage(response)
            finish_reason = usage_data["finish_reason"]
            is_tool_call = finish_reason in ("tool_calls", "tool_use")

            tool_names_list = []
            try:
                if hasattr(response, "tool_calls") and response.tool_calls:
                    tool_names_list = [tc.name for tc in response.tool_calls if hasattr(tc, "name")]
            except Exception:
                pass
            tool_names_str = ", ".join(tool_names_list)

            # Extract text content from response for output_content
            output_text = ""
            try:
                if response.content:
                    output_text = response.content
            except Exception:
                pass

            sk_inner = getattr(self, "_current_session_key", "") or ""
            provider_name = type(self.provider).__name__.lower().replace("provider", "")
            iteration = self._turn_iteration
            self._turn_iteration += 1

            current_turn_tokens = 0
            if iteration == 0:
                try:
                    from nanobot.utils.helpers import estimate_prompt_tokens
                    u_msg = getattr(self, "_current_user_message", "") or ""
                    if u_msg:
                        current_turn_tokens = estimate_prompt_tokens(
                            [{"role": "user", "content": u_msg}]
                        )
                except Exception:
                    pass

            system_prompt = getattr(self, "_last_system_prompt", "") or ""
            prev_sys = getattr(self, "_prev_recorded_system_prompt", "")
            if system_prompt == prev_sys:
                system_prompt_to_store = ""
            else:
                system_prompt_to_store = system_prompt
                self._prev_recorded_system_prompt = system_prompt

            # Phase 0 UPDATE: 第一次 LLM 调用完成后更新已有的 pending 记录
            phase0_id = getattr(self, "_phase0_record_id", None)
            if iteration == 0 and phase0_id is not None:
                try:
                    token_stats.update_record(
                        phase0_id,
                        prompt_tokens=usage_data["prompt_tokens"],
                        completion_tokens=usage_data["completion_tokens"],
                        total_tokens=usage_data["total_tokens"],
                        cached_tokens=usage_data.get("cached_tokens", 0),
                        cache_creation_tokens=usage_data.get("cache_creation_tokens", 0),
                        finish_reason=finish_reason,
                        model_role="tool_call" if is_tool_call else "chat",
                        current_turn_tokens=current_turn_tokens,
                        tool_names=tool_names_str,
                    )
                    self._turn_record_ids.append(phase0_id)
                    self._phase0_record_id = None
                    bus = getattr(self, "bus", None)
                    if bus and hasattr(bus, "dispatch_observe_event"):
                        bus.dispatch_observe_event(sk_inner, {
                            "type": "token_recorded",
                            "session_key": sk_inner,
                            "record_id": phase0_id,
                            "phase": "completed",
                        })
                except Exception as exc:
                    logger.warning("Failed to update Phase 0 record: {}", exc)
                return

            try:
                rec_id = token_stats.record(
                    model=self.model,
                    provider=provider_name,
                    usage=usage_data,
                    session_key=sk_inner,
                    conversation_id=conversation_id,
                    turn_seq=turn_seq,
                    iteration=iteration,
                    user_message="",
                    output_content=output_text,
                    system_prompt=system_prompt_to_store,
                    conversation_history="",
                    finish_reason=finish_reason,
                    model_role="tool_call" if is_tool_call else "chat",
                    cached_tokens=usage_data.get("cached_tokens"),
                    cache_creation_tokens=usage_data.get("cache_creation_tokens"),
                    current_turn_tokens=current_turn_tokens,
                    tool_names=tool_names_str,
                )
                if rec_id is not None:
                    self._turn_record_ids.append(rec_id)
                elif token_stats._use_db:
                    row = token_stats._db.fetchone("SELECT last_insert_rowid() as id")
                    if row:
                        self._turn_record_ids.append(row["id"])
            except Exception as exc:
                logger.warning("Failed to record token stats inline: {}", exc)

        async def intercepted_chat(*args, **kw):
            response = await original_chat(*args, **kw)
            _record_immediately(response)
            return response

        async def intercepted_chat_stream(*args, **kw):
            response = await original_chat_stream(*args, **kw)
            _record_immediately(response)
            return response

        self.provider.chat_with_retry = intercepted_chat
        self.provider.chat_stream_with_retry = intercepted_chat_stream
        try:
            return await original_run_agent_loop(self, initial_messages, **kwargs)
        finally:
            self.provider.chat_with_retry = original_chat
            self.provider.chat_stream_with_retry = original_chat_stream

    def _extract_usage(response) -> dict:
        """Extract and pre-parse all token fields from an LLM response."""
        usage = response.usage or {}
        prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
        completion_tokens = int(usage.get("completion_tokens", 0) or 0)
        total_tokens = int(usage.get("total_tokens", 0) or 0) or (prompt_tokens + completion_tokens)
        prompt_details = usage.get("prompt_tokens_details") or {}
        cached_tokens = int(
            prompt_details.get("cached_tokens", 0)
            or usage.get("cache_read_input_tokens", 0)
            or 0
        )
        cache_creation_tokens = int(usage.get("cache_creation_input_tokens", 0) or 0)
        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "cached_tokens": cached_tokens,
            "cache_creation_tokens": cache_creation_tokens,
            "finish_reason": response.finish_reason or "",
        }

    patched_run_agent_loop._ava_loop_patched = True
    AgentLoop._run_agent_loop = patched_run_agent_loop

    # ------------------------------------------------------------------
    # 3b. Patch _save_turn to fix skip mismatch with compressed history.
    #     context_patch's HistorySummarizer/Compressor reduce history size,
    #     but upstream skip = 1 + len(original_history), which overshoots
    #     all_msgs length and causes new messages to be silently dropped.
    #     Fix: use _last_build_msg_count (set by context_patch) as the
    #     actual number of non-system messages in build_messages output.
    # ------------------------------------------------------------------
    original_save_turn = AgentLoop._save_turn

    def fixed_save_turn(self_loop, session, messages, skip):
        corrected = getattr(self_loop, "_last_build_msg_count", None)
        if corrected is not None:
            skip = 1 + corrected  # 1 for system + compressed history (excl. user)
            current_user_idx = skip
            if (
                current_user_idx < len(messages)
                and session.messages
                and messages[current_user_idx].get("role") == "user"
                and session.messages[-1].get("role") == "user"
                and session.messages[-1].get("content") == messages[current_user_idx].get("content")
            ):
                # Upstream may have already persisted the current user message
                # before _run_agent_loop starts. Preserve that extra skip.
                skip += 1
        original_save_turn(self_loop, session, messages, skip)

    fixed_save_turn._ava_loop_patched = True
    AgentLoop._save_turn = fixed_save_turn

    # ------------------------------------------------------------------
    # 4. Patch _process_message to set context for inline recording,
    #    then backfill user_message / output_content / conversation_history
    #    on the first and last DB records after the turn completes.
    # ------------------------------------------------------------------
    original_process_message = AgentLoop._process_message

    async def patched_process_message(
        self: AgentLoop,
        msg,
        session_key=None,
        on_progress=None,
        on_stream=None,
        on_stream_end=None,
        pending_queue=None,
        **kwargs,
    ):
        sk = session_key or getattr(msg, "session_key", "")
        raw = (getattr(msg, "content", "") or "").strip()
        is_new_command = _is_new_command(raw)
        self._current_session_key = sk
        self._current_user_message = getattr(msg, "content", "") or ""
        self._current_conversation_id = ""
        self._current_turn_seq = None
        self._turn_record_ids = []
        self._turn_iteration = 0
        pending_rotation_event: dict[str, str] | None = None

        if sk:
            try:
                session = self.sessions.get_or_create(sk)
                if is_new_command:
                    previous_conversation_id = ""
                    metadata = getattr(session, "metadata", None)
                    if isinstance(metadata, dict):
                        previous_conversation_id = metadata.get("conversation_id") or ""
                    conversation_id, changed = _ensure_session_conversation_id(session, rotate=True)
                    self._current_conversation_id = conversation_id
                    if changed:
                        pending_rotation_event = {
                            "old_conversation_id": previous_conversation_id,
                            "new_conversation_id": conversation_id,
                        }
                elif not raw.startswith("/"):
                    conversation_id, changed = _ensure_session_conversation_id(session)
                    self._current_conversation_id = conversation_id
                    if changed:
                        self.sessions.save(session)
                existing_messages = getattr(session, "messages", []) or []
                self._current_turn_seq = sum(
                    1
                    for item in existing_messages
                    if isinstance(item, dict) and item.get("role") == "user"
                )
            except Exception:
                self._current_turn_seq = None

        bg_store = getattr(self, "bg_tasks", None)
        if bg_store and hasattr(bg_store, "reset_continuation_budget") and sk:
            bg_store.reset_continuation_budget(sk)

        import asyncio as _asyncio_pm
        try:
            result = await original_process_message(
                self, msg,
                session_key=session_key,
                on_progress=on_progress,
                on_stream=on_stream,
                on_stream_end=on_stream_end,
                pending_queue=pending_queue,
                **kwargs,
            )
        except BaseException as exc:
            phase0_id = getattr(self, "_phase0_record_id", None)
            token_stats = getattr(self, "token_stats", None)
            is_cancel = isinstance(exc, _asyncio_pm.CancelledError)
            if token_stats:
                reason = "cancelled" if is_cancel else "error"
                if phase0_id is not None:
                    try:
                        token_stats.update_record(phase0_id, finish_reason=reason, model_role="error")
                    except Exception:
                        pass
                record_ids = getattr(self, "_turn_record_ids", [])
                if record_ids:
                    try:
                        user_msg = (getattr(msg, "content", "") or "")[:1000]
                        first_id = record_ids[0]
                        token_stats._db.execute(
                            "UPDATE token_usage SET user_message = ? WHERE id = ? AND user_message = ''",
                            (user_msg, first_id),
                        )
                        last_id = record_ids[-1]
                        token_stats._db.execute(
                            "UPDATE token_usage SET output_content = ?, model_role = ? WHERE id = ?",
                            (f"[{reason}] {type(exc).__name__}: {str(exc)[:200]}", "error", last_id),
                        )
                        token_stats._db.commit()
                    except Exception:
                        pass
            self._current_turn_seq = None
            self._turn_record_ids = []
            self._turn_iteration = 0
            self._phase0_record_id = None
            self._current_conversation_id = ""
            raise

        # Backfill user_message, output_content on DB records
        token_stats = getattr(self, "token_stats", None)
        record_ids = getattr(self, "_turn_record_ids", [])
        if token_stats and token_stats._use_db and record_ids:
            try:
                user_msg = (getattr(msg, "content", "") or "")[:1000]
                output_content = (getattr(result, "content", "") or "")[:4000]

                first_id = record_ids[0]
                token_stats._db.execute(
                    "UPDATE token_usage SET user_message = ? WHERE id = ? AND user_message = ''",
                    (user_msg, first_id),
                )

                last_id = record_ids[-1]
                token_stats._db.execute(
                    "UPDATE token_usage SET output_content = ? WHERE id = ?",
                    (output_content, last_id),
                )
                token_stats._db.commit()
            except Exception as exc:
                logger.warning("Failed to backfill token stats: {}", exc)

        if sk and pending_rotation_event:
            bus = getattr(self, "bus", None)
            if bus and hasattr(bus, "dispatch_observe_event"):
                try:
                    bus.dispatch_observe_event(sk, {
                        "type": "conversation_rotated",
                        "session_key": sk,
                        "old_conversation_id": pending_rotation_event["old_conversation_id"],
                        "new_conversation_id": pending_rotation_event["new_conversation_id"],
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                except Exception:
                    pass

        # 广播 turn_completed（此时 _save_turn + sessions.save 已完成，DB 中消息已持久化）
        if sk:
            bus = getattr(self, "bus", None)
            if bus and hasattr(bus, "dispatch_observe_event"):
                try:
                    session = self.sessions.get_or_create(sk)
                    bus.dispatch_observe_event(sk, {
                        "type": "turn_completed",
                        "session_key": sk,
                        "conversation_id": self._current_conversation_id,
                        "turn_seq": self._current_turn_seq,
                        "message_count": len(session.messages) if session else 0,
                    })
                except Exception:
                    pass

        # Clear turn state
        self._turn_record_ids = []
        self._turn_iteration = 0
        self._phase0_record_id = None
        self._current_turn_seq = None
        self._current_conversation_id = ""

        return result

    patched_process_message._ava_loop_patched = True
    AgentLoop._process_message = patched_process_message

    return "AgentLoop patched: injected db/token_stats/media_service/categorized_memory/summarizer/compressor; _process_message records rich token usage"


register_patch("agent_loop", apply_loop_patch)
