"""Candidate recency filtering and heat scoring."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any


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


def _interaction_score(signals: dict[str, Any]) -> tuple[float, list[str]]:
    weights = {
        "likes": 0.006,
        "comments": 0.06,
        "shares": 0.09,
        "reposts": 0.09,
        "favorites": 0.02,
        "views": 0.00045,
        "danmaku": 0.04,
    }
    raw = 0.0
    for key, weight in weights.items():
        value = signals.get(key, 0)
        if isinstance(value, (int, float)) and value > 0:
            raw += value * weight

    if raw <= 0:
        return 0.0, []
    return min(30.0, 6.0 + math.log1p(raw) * 6.0), ["interaction-volume"]


def score_candidate_heat(
    candidate: dict[str, Any],
    source: dict[str, Any],
    *,
    now: datetime,
    lookback_hours: int,
) -> tuple[float, list[str]]:
    event_time = _event_time(candidate)
    age_hours = 0.0 if event_time is None else max((now - event_time).total_seconds() / 3600, 0.0)
    recency_score = max(0.0, 1.0 - age_hours / lookback_hours) * 20.0

    priority = source.get("priority", 50)
    if not isinstance(priority, (int, float)):
        priority = 50
    score = min(max(float(priority), 0.0), 100.0) * 0.22 + recency_score
    reasons = ["source-priority", "freshness"]

    source_kind = str(source.get("kind", "")).lower()
    if source_kind == "community":
        score += 12.0
        reasons.append("community-source")
    elif source_kind == "official":
        score += 6.0
        reasons.append("official-source")
    elif source_kind == "media":
        score += 4.0
        reasons.append("media-source")

    tags = {str(tag).lower() for tag in candidate.get("tags", [])}
    if tags & {"meme", "player_story"}:
        score += 16.0
        reasons.append("meme/player-story")
    if "hot_discussion" in tags:
        score += 10.0
        reasons.append("hot-discussion")
    if tags & {"controversy", "price", "dei", "loss"}:
        score += 9.0
        reasons.append("controversy-or-market-risk")

    interaction_score, interaction_reasons = _interaction_score(
        candidate.get("heat_signals", {})
    )
    score += interaction_score
    reasons.extend(interaction_reasons)

    return round(min(score, 100.0), 2), reasons


def filter_and_rank_candidates(
    candidates: list[dict[str, Any]],
    sources: dict[str, dict[str, Any]],
    *,
    now: datetime,
    lookback_hours: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)

    window_start = now.timestamp() - lookback_hours * 3600
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for candidate in candidates:
        event_time = _event_time(candidate)
        enriched = dict(candidate)

        if event_time is None:
            enriched["reject_reason"] = "missing_time"
            rejected.append(enriched)
            continue

        if event_time.timestamp() < window_start or event_time > now:
            enriched["reject_reason"] = "outside_time_window"
            rejected.append(enriched)
            continue

        source = sources.get(str(candidate.get("source_id")), {})
        heat_score, heat_reasons = score_candidate_heat(
            enriched,
            source,
            now=now,
            lookback_hours=lookback_hours,
        )
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
