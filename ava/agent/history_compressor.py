"""History compression utilities for long-running conversations."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass
class _Turn:
    index: int
    messages: list[dict[str, Any]]
    user_text: str


class HistoryCompressor:
    """Compress history by recency + lightweight relevance under a char budget."""

    _BACKFILL_PREFIX = "[auto-backfill]"
    _BACKFILL_SENTINEL = "[bf]"

    def __init__(
        self,
        *,
        max_chars: int = 12000,
        recent_turns: int = 10,
        min_recent_turns: int = 4,
        max_old_turns: int = 4,
        protected_recent_messages: int = 20,
    ) -> None:
        self.max_chars = max_chars
        self.recent_turns = recent_turns
        self.min_recent_turns = min_recent_turns
        self.max_old_turns = max_old_turns
        self.protected_recent_messages = protected_recent_messages

    @staticmethod
    def _is_assistant_final(msg: dict[str, Any]) -> bool:
        return msg.get("role") == "assistant" and not msg.get("tool_calls")

    def _is_backfill(self, msg: dict[str, Any]) -> bool:
        if msg.get("role") != "assistant":
            return False
        metadata = msg.get("metadata")
        if isinstance(metadata, dict) and metadata.get("auto_backfill"):
            return True
        content = msg.get("content")
        return isinstance(content, str) and content.startswith(self._BACKFILL_PREFIX)

    def _normalize_message(self, msg: dict[str, Any]) -> dict[str, Any]:
        out = dict(msg)
        if self._is_backfill(out):
            out["content"] = self._BACKFILL_SENTINEL
        return out

    @staticmethod
    def _char_len(msg: dict[str, Any]) -> int:
        content = msg.get("content")
        if isinstance(content, str):
            return len(content)
        if isinstance(content, list):
            total = 0
            for item in content:
                if isinstance(item, dict):
                    total += len(str(item.get("text", "")))
            return total
        return 0

    @staticmethod
    def extract_terms(text: str) -> set[str]:
        terms = set()
        lower = text.lower()
        terms.update(re.findall(r"[a-z0-9_]{3,}", lower))
        for chunk in re.findall(r"[\u4e00-\u9fff]{2,}", text):
            if len(chunk) <= 12:
                terms.add(chunk)
                continue
            # Very lightweight split for long CJK chunks.
            for i in range(0, min(len(chunk) - 1, 12)):
                terms.add(chunk[i:i + 2])
        return {t for t in terms if t}

    def _split_turns(self, history: list[dict[str, Any]]) -> list[_Turn]:
        turns: list[_Turn] = []
        current: list[dict[str, Any]] = []
        user_text = ""
        idx = 0

        for raw in history:
            msg = self._normalize_message(raw)
            role = msg.get("role")

            if role == "user":
                if current:
                    turns.append(_Turn(index=idx, messages=current, user_text=user_text))
                    idx += 1
                current = [msg]
                content = msg.get("content")
                user_text = content if isinstance(content, str) else ""
                continue

            if not current:
                # Ignore orphan non-user blocks.
                continue

            current.append(msg)
            if self._is_assistant_final(msg):
                turns.append(_Turn(index=idx, messages=current, user_text=user_text))
                idx += 1
                current = []
                user_text = ""

        if current:
            turns.append(_Turn(index=idx, messages=current, user_text=user_text))

        return turns

    def _turn_score(self, turn: _Turn, query_terms: set[str], recency_rank: int) -> float:
        if not query_terms:
            return recency_rank * 0.01
        turn_terms = self.extract_terms(turn.user_text)
        overlap = len(turn_terms & query_terms)
        return overlap * 10.0 + recency_rank * 0.05

    @staticmethod
    def _flatten(turns: list[_Turn]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for turn in turns:
            out.extend(turn.messages)
        return out

    def _within_budget(self, messages: list[dict[str, Any]]) -> bool:
        total = sum(self._char_len(m) for m in messages)
        return total <= self.max_chars

    def compress(self, history: list[dict[str, Any]], current_message: str) -> list[dict[str, Any]]:
        """Return compressed history while preserving turn structure.

        Protected messages (last N) are never compressed; older messages go through
        turn-based compression with relevance scoring.
        """
        if not history:
            return history

        # Phase 1: Protect the most recent messages entirely
        if self.protected_recent_messages > 0 and len(history) > self.protected_recent_messages:
            split = len(history) - self.protected_recent_messages
            # 向前调整分界点，避免切断 tool_call 组：
            # protected 部分不能以 tool_result 或带 tool_calls 的 assistant 开头，
            # 否则会产生 orphan tool_result 导致 API 400 错误。
            while split > 0 and (
                history[split].get("role") == "tool"
                or (history[split].get("role") == "assistant" and history[split].get("tool_calls"))
            ):
                split -= 1
            protected = history[split:]
            to_compress = history[:split]
        elif self.protected_recent_messages == 0:
            # No protection: compress entire history
            protected = []
            to_compress = history
        else:
            # Not enough messages to split; return as-is
            return history

        if not to_compress:
            return protected

        # Phase 2: Compress older messages using turn-based logic
        turns = self._split_turns(to_compress)
        if not turns:
            return protected

        recent = turns[-self.recent_turns:] if len(turns) > self.recent_turns else list(turns)
        old = turns[:-len(recent)] if len(recent) < len(turns) else []

        query_terms = self.extract_terms(current_message)
        scored_old: list[tuple[float, _Turn]] = []
        for i, turn in enumerate(old):
            recency_rank = i + 1
            scored_old.append((self._turn_score(turn, query_terms, recency_rank), turn))

        scored_old.sort(key=lambda x: (x[0], x[1].index), reverse=True)
        selected_old = [turn for score, turn in scored_old if score > 0][: self.max_old_turns]
        if not selected_old and old:
            # Keep at least one old turn to reduce abrupt context loss.
            selected_old = [old[-1]]

        selected_old.sort(key=lambda t: t.index)
        selected_recent = list(recent)

        combined = selected_old + selected_recent
        combined.sort(key=lambda t: t.index)
        messages = self._flatten(combined)

        if self._within_budget(messages):
            return messages + protected

        # Drop oldest selected-old turns first.
        while selected_old and not self._within_budget(self._flatten(selected_old + selected_recent)):
            selected_old.pop(0)

        # Then shrink recent turns conservatively (keep at least min_recent_turns).
        while (
            len(selected_recent) > self.min_recent_turns
            and not self._within_budget(self._flatten(selected_old + selected_recent))
        ):
            selected_recent.pop(0)

        trimmed = self._flatten(selected_old + selected_recent)
        if trimmed:
            return trimmed + protected
        return protected
