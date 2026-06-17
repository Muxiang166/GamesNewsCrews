"""Candidate recency filtering and heat scoring."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import yaml

from .memory import apply_memory_freshness
from .trend_signals import build_discussion_profile

logger = logging.getLogger(__name__)

DEFAULT_HEAT_WEIGHTS_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "heat_weights.yaml"
)

# Hardcoded fallback defaults — kept in sync with heat_weights.yaml
_DEFAULT_HEAT_WEIGHTS = {
    "recency_multiplier": 15.0,
    "source_priority_weight": 0.12,
    "source_kind_bonus": {
        "community": 8.0,
        "official": 4.0,
        "media": 2.0,
    },
    "candidate_type_bonus": {
        "meme_player_story": 14.0,
        "hot_discussion": 6.0,
        "controversy_market_risk": 7.0,
    },
    "discussion_score_weight": 0.45,
}


def _namespaceify(data: dict) -> SimpleNamespace:
    """Recursively convert a nested dict into a :class:`SimpleNamespace`."""
    converted: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, dict):
            converted[key] = _namespaceify(value)
        else:
            converted[key] = value
    return SimpleNamespace(**converted)


def load_heat_weights(config_path: Path | None = None) -> SimpleNamespace:
    """Load heat scoring weights from a YAML config file.

    Falls back to hardcoded defaults if the file is missing, unreadable,
    or missing the ``scoring`` key.  Logs a warning on any fallback path.

    Parameters
    ----------
    config_path:
        Optional path to a ``heat_weights.yaml`` file.  Defaults to
        ``<project-root>/LangGraph/config/heat_weights.yaml``.

    Returns
    -------
    SimpleNamespace
        Dot-accessible namespace mirroring the ``scoring`` section of the
        YAML file (e.g. ``weights.recency_multiplier``,
        ``weights.source_kind_bonus.community``).
    """
    path = config_path or DEFAULT_HEAT_WEIGHTS_PATH
    try:
        with path.open("r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}
    except (FileNotFoundError, yaml.YAMLError, OSError) as exc:
        logger.warning(
            "Could not load heat weights from %s — using hardcoded defaults (%s)",
            path,
            exc,
        )
        return _namespaceify(_DEFAULT_HEAT_WEIGHTS)

    scoring = raw.get("scoring")
    if not isinstance(scoring, dict):
        logger.warning(
            "%s is missing the 'scoring' key — using hardcoded defaults", path
        )
        return _namespaceify(_DEFAULT_HEAT_WEIGHTS)

    # Merge with defaults so new keys can be added without breaking old configs
    merged = _DEFAULT_HEAT_WEIGHTS.copy()
    for key in merged:
        if key in scoring and isinstance(scoring[key], dict):
            merged[key].update(scoring[key])
        elif key in scoring:
            merged[key] = scoring[key]

    return _namespaceify(merged)


def _parse_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _event_time(candidate: dict[str, Any]) -> datetime | None:
    return _parse_datetime(candidate.get("published_at")) or _parse_datetime(
        candidate.get("observed_at")
    )


def _list_config(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return []


def _matches_pattern(pattern: str, text: str) -> bool:
    try:
        return re.search(pattern, text, flags=re.IGNORECASE) is not None
    except re.error:
        return pattern.lower() in text.lower()


def _matches_any_pattern(patterns: list[str], text: str) -> bool:
    return any(_matches_pattern(pattern, text) for pattern in patterns)


def _candidate_haystack(candidate: dict[str, Any]) -> str:
    tags = " ".join(str(tag) for tag in candidate.get("tags", []))
    parts = [
        candidate.get("title", ""),
        candidate.get("snippet", ""),
        candidate.get("url", ""),
        tags,
    ]
    return " ".join(str(part) for part in parts if part).lower()


def _keyword_hit(keywords: list[str], haystack: str) -> str:
    for keyword in keywords:
        term = keyword.strip().lower()
        if not term:
            continue
        if term.startswith("re:"):
            pattern = term[3:]
            try:
                if re.search(pattern, haystack, flags=re.IGNORECASE):
                    return keyword
            except re.error:
                continue
        elif re.fullmatch(r"[a-z0-9]+", term):
            pattern = rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])"
            if re.search(pattern, haystack, flags=re.IGNORECASE):
                return keyword
        elif term in haystack:
            return keyword
    return ""


def _relevance_reasons(candidate: dict[str, Any], source: dict[str, Any]) -> list[str]:
    config = source.get("collector_config", {})
    if not isinstance(config, dict):
        return []

    reasons: list[str] = []
    url = str(candidate.get("url", ""))
    allowed_url_patterns = _list_config(config.get("allowed_url_patterns"))
    if allowed_url_patterns and not _matches_any_pattern(allowed_url_patterns, url):
        reasons.append("url_not_allowed")

    excluded_url_patterns = _list_config(config.get("excluded_url_patterns"))
    if excluded_url_patterns and _matches_any_pattern(excluded_url_patterns, url):
        reasons.append("url_excluded")

    haystack = _candidate_haystack(candidate)
    excluded_keyword = _keyword_hit(_list_config(config.get("excluded_keywords")), haystack)
    if excluded_keyword:
        reasons.append(f"excluded_keyword:{excluded_keyword}")

    required_any_keywords = _list_config(config.get("required_any_keywords"))
    if required_any_keywords and not _keyword_hit(required_any_keywords, haystack):
        reasons.append("missing_required_keyword")

    return reasons


def score_candidate_heat(
    candidate: dict[str, Any],
    source: dict[str, Any],
    *,
    now: datetime,
    lookback_hours: int,
    weights: SimpleNamespace | None = None,
) -> tuple[float, list[str]]:
    w = weights or _namespaceify(_DEFAULT_HEAT_WEIGHTS)

    event_time = _event_time(candidate)
    age_hours = (
        0.0
        if event_time is None
        else max((now - event_time).total_seconds() / 3600, 0.0)
    )
    recency_score = (
        max(0.0, 1.0 - age_hours / lookback_hours) * w.recency_multiplier
    )

    priority = source.get("priority", 50)
    if not isinstance(priority, (int, float)):
        priority = 50
    score = min(max(float(priority), 0.0), 100.0) * w.source_priority_weight + recency_score
    reasons = ["source-priority", "freshness"]

    source_kind = str(source.get("kind", "")).lower()
    sk_bonus = w.source_kind_bonus
    kind_bonus = {
        "community": sk_bonus.community,
        "official": sk_bonus.official,
        "media": sk_bonus.media,
    }
    if source_kind in kind_bonus:
        score += kind_bonus[source_kind]
        reasons.append(f"{source_kind}-source")

    ct_bonus = w.candidate_type_bonus
    tags = {str(tag).lower() for tag in candidate.get("tags", [])}
    if tags & {"meme", "player_story"}:
        score += ct_bonus.meme_player_story
        reasons.append("meme/player-story")
    if "hot_discussion" in tags:
        score += ct_bonus.hot_discussion
        reasons.append("hot-discussion")
    if tags & {"controversy", "price", "dei", "loss"}:
        score += ct_bonus.controversy_market_risk
        reasons.append("controversy-or-market-risk")

    discussion_profile = candidate.get("discussion_profile")
    if not isinstance(discussion_profile, dict):
        discussion_profile = build_discussion_profile(candidate)
    discussion_score = discussion_profile.get("score", 0)
    if not isinstance(discussion_score, (int, float)):
        discussion_score = 0
    score += float(discussion_score) * w.discussion_score_weight
    discussion_level = str(discussion_profile.get("level", "none"))
    if discussion_level != "none":
        reasons.append(f"discussion:{discussion_level}")
    if discussion_profile.get("has_multi_platform_discussion"):
        reasons.append("multi-platform-discussion")
    if discussion_profile.get("has_direct_engagement"):
        reasons.append("direct-engagement")

    return round(min(score, 100.0), 2), reasons


def filter_and_rank_candidates(
    candidates: list[dict[str, Any]],
    sources: dict[str, dict[str, Any]],
    *,
    now: datetime,
    lookback_hours: int,
    memory_records: Any | None = None,
    weights: SimpleNamespace | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)

    w = weights or _namespaceify(_DEFAULT_HEAT_WEIGHTS)

    window_start = now.timestamp() - lookback_hours * 3600
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for candidate in candidates:
        event_time = _event_time(candidate)
        enriched = apply_memory_freshness(
            candidate,
            memory_records=memory_records or {},
            now=now,
            lookback_hours=lookback_hours,
        )

        if event_time is None:
            enriched["reject_reason"] = "missing_time"
            rejected.append(enriched)
            continue

        if event_time.timestamp() < window_start or event_time > now:
            enriched["reject_reason"] = "outside_time_window"
            rejected.append(enriched)
            continue

        if enriched.get("memory_status") == "late_repost":
            enriched["reject_reason"] = "late_repost_without_current_update"
            rejected.append(enriched)
            continue

        source = sources.get(str(candidate.get("source_id")), {})
        relevance_reasons = _relevance_reasons(enriched, source)
        if relevance_reasons:
            enriched["reject_reason"] = "irrelevant_topic"
            enriched["relevance_reasons"] = relevance_reasons
            rejected.append(enriched)
            continue

        discussion_profile = build_discussion_profile(enriched)
        enriched["discussion_profile"] = discussion_profile
        enriched["discussion_score"] = discussion_profile.get("score", 0)
        enriched["discussion_level"] = discussion_profile.get("level", "none")
        heat_score, heat_reasons = score_candidate_heat(
            enriched,
            source,
            now=now,
            lookback_hours=lookback_hours,
            weights=w,
        )
        if enriched.get("memory_status") == "follow_up_update":
            heat_reasons = [*heat_reasons, "memory-follow-up-update"]
        enriched["heat_score"] = heat_score
        enriched["heat_reasons"] = heat_reasons
        enriched["event_time"] = event_time.isoformat()
        accepted.append(enriched)

    accepted.sort(
        key=lambda item: (
            item.get("heat_score", 0.0),
            item.get("event_time", ""),
        ),
        reverse=True,
    )
    return accepted, rejected
