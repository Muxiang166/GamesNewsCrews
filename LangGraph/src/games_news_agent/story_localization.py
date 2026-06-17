"""Localization request interfaces for English story candidates.

This module prepares LLM/human-review requests only. It does not translate,
search the web, choose replacements, or change factual story state.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any


LOCALIZATION_INSTRUCTIONS = """
Translate the English story for a Chinese games-news briefing and decide whether
one of the provided Chinese candidates appears to cover the same event.
Use only the provided story and candidate_chinese_replacements.
Do not add facts, dates, sources, or URLs that are not present in the input.
Return JSON only.
""".strip()

CHINESE_SOURCE_IDS = {"gamergen", "gamersky", "bilibili", "weibo", "xiaoheihe", "tieba", "taptap", "3dm", "ali213"}


def _source_ids_from_story(story: dict[str, Any]) -> list[str]:
    source_ids: list[str] = []
    for claim in story.get("claims", []):
        if not isinstance(claim, dict):
            continue
        metadata = claim.get("metadata", {})
        if isinstance(metadata, dict):
            source_id = str(metadata.get("source_id") or "").strip()
            if source_id and source_id not in source_ids:
                source_ids.append(source_id)
        for evidence in claim.get("evidence", []):
            if not isinstance(evidence, dict):
                continue
            source_id = str(evidence.get("source_id") or "").strip()
            if source_id and source_id not in source_ids:
                source_ids.append(source_id)
    return source_ids


def _is_english_story(story: dict[str, Any]) -> bool:
    language = str(story.get("source_language") or "").strip().lower()
    preference = str(story.get("source_preference") or "").strip().lower()
    if language == "en":
        return True
    return preference in {"english_ign_fallback", "original_source_used"} and language != "zh"


def _theme(story: dict[str, Any]) -> str:
    return str(story.get("theme_section") or "").strip()


def _evidence_quotes(story: dict[str, Any], limit: int = 3) -> list[dict[str, str]]:
    quotes: list[dict[str, str]] = []
    for claim in story.get("claims", []):
        if not isinstance(claim, dict):
            continue
        for evidence in claim.get("evidence", []):
            if not isinstance(evidence, dict):
                continue
            quote = str(evidence.get("quote") or "").strip()
            if not quote:
                continue
            quotes.append(
                {
                    "source_id": str(evidence.get("source_id") or ""),
                    "title": str(evidence.get("title") or ""),
                    "quote": quote[:700],
                }
            )
            if len(quotes) >= limit:
                return quotes
    return quotes


def _candidate_key(candidate: dict[str, Any]) -> str:
    return str(candidate.get("url") or candidate.get("title") or "")


def _candidate_source_id(candidate: dict[str, Any]) -> str:
    return str(candidate.get("source_id") or "").strip().lower()


def _is_chinese_candidate(candidate: dict[str, Any]) -> bool:
    source_id = _candidate_source_id(candidate)
    if source_id in CHINESE_SOURCE_IDS:
        return True
    url = str(candidate.get("url") or "").lower()
    return any(domain in url for domain in ("gamersky.com", "bilibili.com", "weibo.com", "3dmgame.com", "ali213.net"))


def _candidate_score(candidate: dict[str, Any]) -> float:
    value = candidate.get("heat_score", 0)
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def _iter_pool_candidates(theme_candidate_pool: dict[str, Any] | None) -> Iterable[dict[str, Any]]:
    if not isinstance(theme_candidate_pool, dict):
        return []
    selected = theme_candidate_pool.get("selected_candidates")
    if isinstance(selected, list):
        return [candidate for candidate in selected if isinstance(candidate, dict)]
    sections = theme_candidate_pool.get("sections", [])
    candidates: list[dict[str, Any]] = []
    if isinstance(sections, list):
        for section in sections:
            if not isinstance(section, dict):
                continue
            for candidate in section.get("candidates", []):
                if isinstance(candidate, dict):
                    candidates.append(candidate)
    return candidates


def _chinese_replacement_candidates(
    story: dict[str, Any],
    theme_candidate_pool: dict[str, Any] | None,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    story_theme = _theme(story)
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in _iter_pool_candidates(theme_candidate_pool):
        if not _is_chinese_candidate(candidate):
            continue
        candidate_theme = str(candidate.get("theme_section") or "").strip()
        if story_theme and candidate_theme and candidate_theme != story_theme:
            continue
        key = _candidate_key(candidate)
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        candidates.append(candidate)
    candidates.sort(key=_candidate_score, reverse=True)
    return [
        {
            "title": str(candidate.get("title") or ""),
            "url": str(candidate.get("url") or ""),
            "source_id": str(candidate.get("source_id") or ""),
            "theme_section": str(candidate.get("theme_section") or ""),
            "heat_score": _candidate_score(candidate),
        }
        for candidate in candidates[: max(limit, 0)]
    ]


def _request_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "translated_title": {"type": "string"},
            "translated_summary": {"type": "string"},
            "chinese_search_queries": {"type": "array"},
            "replacement_decision": {"type": "string"},
            "same_event_chinese_candidates": {"type": "array"},
            "notes": {"type": "array"},
        },
        "required": [
            "translated_title",
            "translated_summary",
            "chinese_search_queries",
            "replacement_decision",
            "same_event_chinese_candidates",
        ],
    }


def build_story_localization_requests(
    story_candidates: list[dict[str, Any]],
    *,
    theme_candidate_pool: dict[str, Any] | None = None,
    selected_stories: list[dict[str, Any]] | None = None,
    max_chinese_candidates_per_story: int = 8,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Build translate-and-replace request packs for English stories."""

    selected_ids = {
        str(story.get("id") or "")
        for story in selected_stories or []
        if isinstance(story, dict)
    }
    requests: list[dict[str, Any]] = []
    for story in story_candidates:
        if not isinstance(story, dict) or not _is_english_story(story):
            continue
        story_id = str(story.get("id") or story.get("title") or "").strip()
        if not story_id:
            continue
        replacements = _chinese_replacement_candidates(
            story,
            theme_candidate_pool,
            limit=max_chinese_candidates_per_story,
        )
        requests.append(
            {
                "request_id": f"story_localization:{story_id}",
                "schema_version": "story_localization_request_v0",
                "instructions": LOCALIZATION_INSTRUCTIONS,
                "produces_facts": False,
                "story": {
                    "id": story_id,
                    "title": str(story.get("title") or ""),
                    "theme_section": _theme(story),
                    "story_score": story.get("story_score", 0),
                    "source_language": story.get("source_language", ""),
                    "source_preference": story.get("source_preference", ""),
                    "source_urls": story.get("source_urls", []),
                    "source_ids": _source_ids_from_story(story),
                    "selected_final_story": story_id in selected_ids,
                    "evidence_quotes": _evidence_quotes(story),
                },
                "candidate_chinese_replacements": replacements,
                "json_schema": _request_schema(),
            }
        )
        if limit is not None and len(requests) >= max(limit, 0):
            break
    return requests


def _bounded_confidence(value: Any) -> float:
    if isinstance(value, (int, float)):
        return max(0.0, min(1.0, float(value)))
    return 0.0


def parse_story_localization_response(
    request_id: str,
    content: str,
    *,
    allowed_chinese_urls: set[str],
) -> dict[str, Any]:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        return {
            "request_id": request_id,
            "parse_status": "invalid_json",
            "error": str(exc),
            "same_event_chinese_candidates": [],
            "dropped_unobserved_urls": [],
        }
    if not isinstance(payload, dict):
        return {
            "request_id": request_id,
            "parse_status": "invalid_json_shape",
            "same_event_chinese_candidates": [],
            "dropped_unobserved_urls": [],
        }

    replacements: list[dict[str, Any]] = []
    dropped: list[str] = []
    for item in payload.get("same_event_chinese_candidates", []):
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if url not in allowed_chinese_urls:
            if url:
                dropped.append(url)
            continue
        replacements.append(
            {
                "url": url,
                "title": str(item.get("title") or ""),
                "confidence": _bounded_confidence(item.get("confidence")),
                "reason": str(item.get("reason") or ""),
            }
        )

    return {
        "request_id": request_id,
        "parse_status": "ok",
        "translated_title": str(payload.get("translated_title") or ""),
        "translated_summary": str(payload.get("translated_summary") or ""),
        "chinese_search_queries": [
            str(item)
            for item in payload.get("chinese_search_queries", [])
            if str(item).strip()
        ],
        "replacement_decision": str(payload.get("replacement_decision") or "manual_review"),
        "same_event_chinese_candidates": replacements,
        "dropped_unobserved_urls": dropped,
    }
