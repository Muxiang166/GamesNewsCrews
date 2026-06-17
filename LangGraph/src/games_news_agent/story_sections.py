"""Theme-section selection for game-news candidates and ranked stories."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from .editorial_focus import (
    annotate_candidate_editorial_focus,
    candidate_editorial_intent,
    candidate_editorial_priority,
)

logger = logging.getLogger(__name__)

DEFAULT_STORY_EDITORIAL_CONFIG_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "story_editorial.yaml"
)

# Hardcoded fallback defaults — kept in sync with story_editorial.yaml
_DEFAULT_STORY_EDITORIAL_BONUS: dict[str, float] = {
    "core_game_update": 12.0,
    "core_game_report": 8.0,
    "platform_business": 3.0,
    "community_or_meme": 2.0,
    "general": 0.0,
    "personal_or_sentiment": -10.0,
}


def load_editorial_bonus(config_path: Path | None = None) -> dict[str, float]:
    """Load editorial intent bonuses from a YAML config file.

    Falls back to hardcoded defaults if the file is missing, unreadable,
    or missing the ``editorial_bonus`` key.

    Parameters
    ----------
    config_path:
        Optional path to a ``story_editorial.yaml`` file.  Defaults to
        ``<project-root>/LangGraph/config/story_editorial.yaml``.

    Returns
    -------
    dict[str, float]
        Editorial intent label -> bonus score.
    """
    path = config_path or DEFAULT_STORY_EDITORIAL_CONFIG_PATH
    try:
        with path.open("r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}
    except (FileNotFoundError, yaml.YAMLError, OSError) as exc:
        logger.warning(
            "Could not load editorial bonuses from %s — using hardcoded defaults (%s)",
            path,
            exc,
        )
        return dict(_DEFAULT_STORY_EDITORIAL_BONUS)

    bonuses = raw.get("editorial_bonus")
    if not isinstance(bonuses, dict):
        logger.warning(
            "%s is missing the 'editorial_bonus' key — using hardcoded defaults", path
        )
        return dict(_DEFAULT_STORY_EDITORIAL_BONUS)

    # Merge with defaults so new keys can be added without breaking old configs
    merged = dict(_DEFAULT_STORY_EDITORIAL_BONUS)
    for key, value in bonuses.items():
        if key in _DEFAULT_STORY_EDITORIAL_BONUS or isinstance(value, (int, float)):
            merged[str(key)] = float(value)

    return merged


# Module-level editorial bonus loaded from config (with hardcoded fallback)
STORY_EDITORIAL_BONUS: dict[str, float] = load_editorial_bonus()


THEME_SECTIONS = [
    {"id": "sony", "label": "索尼"},
    {"id": "nintendo", "label": "任天堂"},
    {"id": "microsoft", "label": "微软"},
    {"id": "pc", "label": "PC"},
    {"id": "supplemental", "label": "补充板块"},
]

SECTION_IDS = {section["id"] for section in THEME_SECTIONS}

SECTION_KEYWORDS = {
    "sony": (
        "sony",
        "索尼",
        "playstation",
        "ps plus",
        "ps+",
        "ps5",
        "ps6",
        "ps4",
        "psn",
        "insomniac",
        "naughty dog",
        "顽皮狗",
        "漫威金刚狼",
        "wolverine",
    ),
    "nintendo": (
        "nintendo",
        "任天堂",
        "switch",
        "switch 2",
        "ns2",
        "mario",
        "zelda",
        "pokemon",
        "宝可梦",
        "马力欧",
        "塞尔达",
    ),
    "microsoft": (
        "microsoft",
        "微软",
        "xbox",
        "game pass",
        "bethesda",
        "activision",
        "blizzard",
        "forza",
        "halo",
        "gear",
        "战争机器",
    ),
    "pc": (
        "pc",
        "steam",
        "steam deck",
        "epic games",
        "epic",
        "gog",
        "windows",
        "电脑",
        "显卡",
        "掌机",
        "rog ally",
    ),
}


def _hits_by_section(text: str) -> dict[str, int]:
    hits: dict[str, int] = {}
    for section_id, keywords in SECTION_KEYWORDS.items():
        count = sum(1 for keyword in keywords if keyword.lower() in text)
        if count:
            hits[section_id] = count
    return hits


def _story_text(story: dict[str, Any], *, title_only: bool = False) -> str:
    parts = [story.get("title", "")]
    if not title_only:
        parts.extend(str(url) for url in story.get("source_urls", []))
        parts.append(str(story.get("category", "")))
        for claim in story.get("claims", []):
            if not isinstance(claim, dict):
                continue
            parts.append(str(claim.get("text", "")))
            metadata = claim.get("metadata", {})
            if isinstance(metadata, dict):
                parts.append(str(metadata.get("candidate_type", "")))
            for evidence in claim.get("evidence", []):
                if isinstance(evidence, dict):
                    parts.append(str(evidence.get("quote", "")))
    return " ".join(str(part) for part in parts if part).lower()


def _candidate_text(candidate: dict[str, Any], *, title_only: bool = False) -> str:
    parts = [candidate.get("title", "")]
    if not title_only:
        parts.extend(
            [
                candidate.get("snippet", ""),
                candidate.get("url", ""),
                candidate.get("source_id", ""),
                candidate.get("candidate_type", ""),
                candidate.get("query", ""),
            ]
        )
        parts.extend(str(tag) for tag in candidate.get("tags", []) if str(tag).strip())
    return " ".join(str(part) for part in parts if part).lower()


def _first_section_from_hits(hits: dict[str, int]) -> str | None:
    for section_id in ("sony", "nintendo", "microsoft", "pc"):
        if section_id in hits:
            return section_id
    return None


def classify_story_section(story: dict[str, Any]) -> str:
    """Classify a ranked story into one fixed editorial section."""

    existing = str(story.get("theme_section", "")).strip()
    if existing in SECTION_IDS:
        return existing

    title_hits = _hits_by_section(_story_text(story, title_only=True))
    section_id = _first_section_from_hits(title_hits)
    if section_id:
        return section_id

    all_hits = _hits_by_section(_story_text(story))
    if len(all_hits) == 1:
        return next(iter(all_hits))
    return "supplemental"


def classify_candidate_section(candidate: dict[str, Any]) -> str:
    """Classify a source candidate before document fetch."""

    existing = str(candidate.get("theme_section", "")).strip()
    if existing in SECTION_IDS:
        return existing

    title_hits = _hits_by_section(_candidate_text(candidate, title_only=True))
    section_id = _first_section_from_hits(title_hits)
    if section_id:
        return section_id

    all_hits = _hits_by_section(_candidate_text(candidate))
    if len(all_hits) == 1:
        return next(iter(all_hits))
    return "supplemental"


def _candidate_theme_sections(candidate: dict[str, Any]) -> list[str]:
    existing = str(candidate.get("theme_section", "")).strip()
    if existing in SECTION_IDS:
        return [existing]

    sections: list[str] = []
    source_entry_themes = candidate.get("source_entry_themes", [])
    if isinstance(source_entry_themes, list):
        for theme in source_entry_themes:
            section_id = str(theme).strip()
            if section_id in SECTION_IDS and section_id not in sections:
                sections.append(section_id)

    for key in ("source_entry_theme", "source_section_theme"):
        section_id = str(candidate.get(key, "")).strip()
        if section_id in SECTION_IDS and section_id not in sections:
            sections.append(section_id)

    if sections:
        return sections

    return [classify_candidate_section(candidate)]


def _score(story: dict[str, Any]) -> float:
    value = story.get("story_score", 0)
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def _story_editorial_intent(story: dict[str, Any]) -> str:
    existing = str(story.get("story_editorial_intent") or story.get("editorial_intent") or "").strip()
    if existing:
        return existing
    return candidate_editorial_intent(story)


def _story_sort_key(story: dict[str, Any]) -> tuple[float, float]:
    score = _score(story)
    bonus = STORY_EDITORIAL_BONUS.get(_story_editorial_intent(story), 0.0)
    return (score + bonus, score)


def _candidate_score(candidate: dict[str, Any]) -> float:
    value = candidate.get("heat_score", 0)
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def _candidate_sort_key(candidate: dict[str, Any]) -> tuple[int, float]:
    return (candidate_editorial_priority(candidate), _candidate_score(candidate))


def _candidate_key(candidate: dict[str, Any]) -> str:
    return str(candidate.get("url") or candidate.get("title") or "")


def _annotate(story: dict[str, Any], section_id: str) -> dict[str, Any]:
    annotated = dict(story)
    annotated["theme_section"] = section_id
    return annotated


def _annotate_candidate(
    candidate: dict[str, Any],
    section_id: str,
    *,
    default_lane: str,
    section_candidates: list[str] | None = None,
) -> dict[str, Any]:
    annotated = annotate_candidate_editorial_focus(candidate)
    annotated["theme_section"] = section_id
    if section_candidates and len(section_candidates) > 1:
        annotated["theme_section_candidates"] = list(section_candidates)
    annotated.setdefault("candidate_lane", default_lane)
    return annotated


def _dedupe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        key = _candidate_key(candidate)
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        deduped.append(candidate)
    return deduped


def build_thematic_candidate_selection(
    candidates: list[dict[str, Any]],
    *,
    supplemental_candidates: list[dict[str, Any]] | None = None,
    per_section_limit: int = 20,
    total_limit: int | None = None,
) -> dict[str, Any]:
    """Build a balanced prefetch pool from main and supplemental candidates."""

    by_section: dict[str, list[dict[str, Any]]] = {section["id"]: [] for section in THEME_SECTIONS}
    main_candidates = [dict(candidate) for candidate in candidates if isinstance(candidate, dict)]
    for candidate in main_candidates:
        candidate.setdefault("candidate_lane", "main")

    supplemental = [
        dict(candidate)
        for candidate in (supplemental_candidates or [])
        if isinstance(candidate, dict)
    ]
    for candidate in supplemental:
        candidate.setdefault("candidate_lane", "supplemental")

    for candidate in _dedupe_candidates([*main_candidates, *supplemental]):
        section_ids = _candidate_theme_sections(candidate)
        if not section_ids:
            section_ids = ["supplemental"]
        default_lane = str(candidate.get("candidate_lane") or "main")
        for section_id in section_ids:
            if section_id not in by_section:
                section_id = "supplemental"
            by_section[section_id].append(
                _annotate_candidate(
                    candidate,
                    section_id,
                    default_lane=default_lane,
                    section_candidates=section_ids,
                )
            )

    pooled: list[dict[str, Any]] = []
    section_infos: list[dict[str, Any]] = []
    for definition in THEME_SECTIONS:
        section_id = definition["id"]
        ranked = sorted(by_section[section_id], key=_candidate_sort_key, reverse=True)
        pool = ranked[: max(per_section_limit, 0)]
        pooled.extend(pool)
        section_infos.append(
            {
                "id": section_id,
                "label": definition["label"],
                "candidate_count": len(ranked),
                "pool_count": len(pool),
                "selected_count": 0,
                "candidates": pool,
                "candidate_urls": [_candidate_key(candidate) for candidate in pool],
            }
        )

    ranked_pool = sorted(pooled, key=_candidate_sort_key, reverse=True)
    selected: list[dict[str, Any]] = []
    selected_candidate_keys: set[str] = set()
    selected_limit = None if total_limit is None else max(total_limit, 0)
    for candidate in ranked_pool:
        key = _candidate_key(candidate)
        if key and key in selected_candidate_keys:
            continue
        if key:
            selected_candidate_keys.add(key)
        selected.append(candidate)
        if selected_limit is not None and len(selected) >= selected_limit:
            break

    selected_keys = {_candidate_key(candidate) for candidate in selected}
    for section in section_infos:
        section["selected_count"] = sum(
            1
            for candidate in section["candidates"]
            if _candidate_key(candidate) in selected_keys
        )

    return {
        "version": "0.1.0",
        "per_section_limit": per_section_limit,
        "total_limit": total_limit,
        "sections": section_infos,
        "selected_candidates": selected,
        "selected_candidate_urls": [_candidate_key(candidate) for candidate in selected],
        "candidate_pool_count": len(pooled),
        "candidate_pool_urls": [_candidate_key(candidate) for candidate in pooled],
        "dropped_after_total_limit": [
            _candidate_key(candidate)
            for candidate in ranked_pool
            if _candidate_key(candidate) not in selected_keys
        ],
    }


def build_thematic_story_selection(
    stories: list[dict[str, Any]],
    *,
    per_section_limit: int = 20,
    final_per_section_limit: int = 10,
    final_limit: int | None = None,
) -> dict[str, Any]:
    """Select a ranked pool per section, then cap final stories per section."""

    by_section: dict[str, list[dict[str, Any]]] = {section["id"]: [] for section in THEME_SECTIONS}
    for story in stories:
        if not isinstance(story, dict):
            continue
        section_id = classify_story_section(story)
        if section_id not in by_section:
            section_id = "supplemental"
        by_section[section_id].append(_annotate(story, section_id))

    if final_limit is not None:
        final_per_section_limit = final_limit

    pooled: list[dict[str, Any]] = []
    selected: list[dict[str, Any]] = []
    section_infos: list[dict[str, Any]] = []
    for definition in THEME_SECTIONS:
        section_id = definition["id"]
        ranked = sorted(by_section[section_id], key=_story_sort_key, reverse=True)
        pool = ranked[: max(per_section_limit, 0)]
        section_selected = pool[: max(final_per_section_limit, 0)]
        pooled.extend(pool)
        selected.extend(section_selected)
        section_infos.append(
            {
                "id": section_id,
                "label": definition["label"],
                "candidate_count": len(ranked),
                "pool_count": len(pool),
                "selected_count": len(section_selected),
                "stories": section_selected,
                "candidate_story_ids": [story.get("id", "") for story in pool],
            }
        )

    selected_ids = {str(story.get("id", "")) for story in selected}

    return {
        "version": "0.1.0",
        "per_section_limit": per_section_limit,
        "final_per_section_limit": final_per_section_limit,
        "final_limit": final_per_section_limit,
        "final_limit_scope": "per_section",
        "selection_scope": "per_section",
        "sections": section_infos,
        "selected_story_ids": [story.get("id", "") for story in selected],
        "selected_stories": selected,
        "candidate_pool_count": len(pooled),
        "candidate_pool_story_ids": [story.get("id", "") for story in pooled],
        "dropped_after_section_limit": [
            story.get("id", "")
            for story in pooled
            if str(story.get("id", "")) not in selected_ids
        ],
        "dropped_after_final_limit": [
            story.get("id", "")
            for story in pooled
            if str(story.get("id", "")) not in selected_ids
        ],
    }
