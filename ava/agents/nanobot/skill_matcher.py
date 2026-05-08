"""Deterministic Nanobot-side skill matcher for P1b chat routing."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_WORD_RE = re.compile(r"[a-z0-9][a-z0-9_-]{1,}", re.IGNORECASE)


@dataclass(frozen=True)
class SkillMatch:
    skill_name: str
    confidence: float
    matched_terms: list[str]
    matched_by: str = "natural_language"


def _normalize(text: str) -> str:
    return " ".join(text.lower().replace("_", " ").replace("-", " ").split())


def _words(text: str) -> set[str]:
    return {match.group(0).lower().replace("_", " ").replace("-", " ") for match in _WORD_RE.finditer(text)}


def _metadata_terms(skill: dict[str, Any]) -> tuple[list[str], list[str]]:
    name = str(skill.get("name") or "")
    description = str(skill.get("description") or "")
    raw_keywords = (
        skill.get("trigger_keywords")
        or skill.get("triggers")
        or skill.get("keywords")
        or []
    )
    if isinstance(raw_keywords, str):
        keywords = [raw_keywords]
    elif isinstance(raw_keywords, list):
        keywords = [str(item) for item in raw_keywords if item]
    else:
        keywords = []

    path = skill.get("path")
    if isinstance(path, str) and path:
        try:
            description = f"{description}\n{Path(path).read_text(encoding='utf-8')[:1200]}"
        except OSError:
            pass

    name_terms = [name, *_words(name)]
    keyword_terms = [*keywords, *_words(" ".join(keywords))]
    description_terms = list(_words(description))
    return (
        [term for term in name_terms + keyword_terms if len(term) >= 3],
        [term for term in description_terms if len(term) >= 3],
    )


def _score_skill(message: str, skill: dict[str, Any]) -> tuple[float, list[str]]:
    message_norm = _normalize(message)
    message_words = _words(message_norm)
    primary_terms, secondary_terms = _metadata_terms(skill)
    score = 0.0
    matched: list[str] = []

    for term in primary_terms:
        term_norm = _normalize(term)
        if not term_norm:
            continue
        if term_norm in message_norm or term_norm in message_words:
            score += 0.28
            if term_norm not in matched:
                matched.append(term_norm)

    for term in secondary_terms:
        term_norm = _normalize(term)
        if term_norm in message_words:
            score += 0.08
            if len(matched) < 5 and term_norm not in matched:
                matched.append(term_norm)

    return min(score, 1.0), matched


def match_skill_for_message(
    message: str,
    skills: list[dict[str, Any]],
    *,
    min_confidence: float = 0.34,
    min_gap: float = 0.08,
) -> SkillMatch | None:
    if not message.strip() or message.lstrip().startswith(("@", "/")):
        return None

    candidates: list[SkillMatch] = []
    for skill in skills:
        if skill.get("enabled") is False:
            continue
        skill_name = str(skill.get("name") or "").strip()
        if not skill_name:
            continue
        confidence, matched_terms = _score_skill(message, skill)
        if confidence > 0:
            candidates.append(SkillMatch(skill_name, confidence, matched_terms))

    if not candidates:
        return None

    candidates.sort(key=lambda item: item.confidence, reverse=True)
    best = candidates[0]
    runner_up = candidates[1].confidence if len(candidates) > 1 else 0.0
    if best.confidence < min_confidence or best.confidence - runner_up < min_gap:
        return None
    return best


def natural_language_skill_matching(
    message: str,
    skills: list[dict[str, Any]],
    *,
    enabled: bool = True,
) -> SkillMatch | None:
    if not enabled:
        return None
    return match_skill_for_message(message, skills)


def skill_match_narration(match: SkillMatch, message: str) -> str:
    goal = re.sub(r"\s+", " ", message.strip())[:80]
    if len(message.strip()) > 80:
        goal += "..."
    return f"我会用 skill {match.skill_name} 来完成：{goal}"
