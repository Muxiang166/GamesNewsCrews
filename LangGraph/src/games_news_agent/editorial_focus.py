"""Lightweight editorial intent scoring for pre-story candidates."""

from __future__ import annotations

from typing import Any


CORE_GAME_SIGNALS = (
    "release date",
    "release window",
    "launch date",
    "gameplay trailer",
    "story trailer",
    "new trailer",
    "first trailer",
    "new gameplay",
    "new details",
    "new screenshots",
    "confirms",
    "confirmed",
    "announced",
    "revealed",
    "coming to",
    "will arrive",
    "arrives on",
    "early access",
    "full release",
    "demo",
    "dlc",
    "patch",
    "update",
    "remake",
    "remaster",
    "port",
    "review score",
    "metacritic",
    "opencritic",
    "新作",
    "续作",
    "重制",
    "移植",
    "发售日",
    "发售",
    "上线",
    "更新",
    "补丁",
    "试玩",
    "演示",
    "实机",
    "预告",
    "官宣",
    "公布",
    "情报",
    "新内容",
    "新玩法",
    "评分解禁",
)

STRONG_PLATFORM_CORE_SIGNALS = (
    "release date",
    "release window",
    "launch date",
    "gameplay trailer",
    "story trailer",
    "new trailer",
    "first trailer",
    "new gameplay",
    "new screenshots",
    "early access",
    "full release",
    "demo",
    "dlc",
    "remake",
    "remaster",
    "port",
    "review score",
    "metacritic",
    "opencritic",
)

PERSONAL_SENTIMENT_SIGNALS = (
    "unused",
    "left unused",
    "debate leaving",
    "players debate",
    "hot take",
    "old streams",
    "goes viral",
    "share of the week",
    "吃灰",
    "吐槽",
    "折磨",
    "后悔",
    "值不值",
    "怎么看",
    "锐评",
    "热议",
    "个人感悟",
    "广告太野",
    "依然震撼",
    "走红",
)

PLATFORM_BUSINESS_TYPES = {"platform_price", "hardware_platform"}
CORE_GAME_TYPES = {"game_detail", "game_update", "game_announcement", "release_date", "trailer", "review_score"}

EDITORIAL_PRIORITY = {
    "core_game_update": 4,
    "core_game_report": 3,
    "platform_business": 2,
    "community_or_meme": 1,
    "personal_or_sentiment": 0,
    "general": 1,
}


def _candidate_text(candidate: dict[str, Any]) -> str:
    tags = " ".join(str(tag) for tag in candidate.get("tags", []) if str(tag).strip())
    return " ".join(
        str(part)
        for part in (
            candidate.get("title", ""),
            candidate.get("snippet", ""),
            candidate.get("candidate_type", ""),
            tags,
        )
        if str(part).strip()
    ).lower()


def candidate_editorial_intent(candidate: dict[str, Any]) -> str:
    existing = str(candidate.get("editorial_intent") or "").strip()
    if existing in EDITORIAL_PRIORITY:
        return existing

    text = _candidate_text(candidate)
    candidate_type = str(candidate.get("candidate_type") or "").strip()

    if candidate_type in PLATFORM_BUSINESS_TYPES:
        if any(signal in text for signal in STRONG_PLATFORM_CORE_SIGNALS):
            return "core_game_update"
        return "platform_business"
    if candidate_type in CORE_GAME_TYPES or any(signal in text for signal in CORE_GAME_SIGNALS):
        return "core_game_update"
    if any(signal in text for signal in PERSONAL_SENTIMENT_SIGNALS):
        return "personal_or_sentiment"
    if candidate_type in {"rumor", "news"}:
        return "core_game_report"
    return "general"


def candidate_editorial_priority(candidate: dict[str, Any]) -> int:
    return EDITORIAL_PRIORITY.get(candidate_editorial_intent(candidate), 1)


def annotate_candidate_editorial_focus(candidate: dict[str, Any]) -> dict[str, Any]:
    annotated = dict(candidate)
    intent = candidate_editorial_intent(annotated)
    annotated["editorial_intent"] = intent
    annotated["editorial_priority"] = EDITORIAL_PRIORITY.get(intent, 1)
    return annotated
