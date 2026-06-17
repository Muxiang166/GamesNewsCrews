"""Discussion and engagement signals for game-news candidates."""

from __future__ import annotations

import math
import re
from typing import Any


PLATFORM_PATTERNS: dict[str, tuple[str, ...]] = {
    "bilibili": (r"\bbilibili\b", r"b\s*站", r"哔哩哔哩", r"b23\.tv"),
    "weibo": (r"\bweibo\b", r"微博"),
    "reddit": (r"\breddit\b", r"r/[a-z0-9_]+"),
    "x": (r"\bx\.com\b", r"\btwitter\b", r"推特"),
    "tieba": (r"贴吧", r"百度贴吧", r"\btieba\b"),
    "xiaohongshu": (r"小红书",),
    "xiaheihe": (r"小黑盒", r"\bheybox\b", r"小黒盒"),
    "steam": (r"\bsteam\b", r"steamcommunity"),
    "resetera": (r"\bresetera\b",),
    "taptap": (r"\btaptap\b",),
}

DIRECT_ENGAGEMENT_KEYS = {"comments", "shares", "reposts", "danmaku"}
ENGAGEMENT_WEIGHTS = {
    "likes": 0.004,
    "comments": 0.075,
    "shares": 0.11,
    "reposts": 0.11,
    "favorites": 0.015,
    "views": 0.00022,
    "danmaku": 0.055,
}

STRONG_DISCUSSION_PATTERNS = (
    r"热议",
    r"疯传",
    r"刷屏",
    r"大量玩家",
    r"玩家社区",
    r"社交平台",
    r"社区.*讨论",
    r"引发.*讨论",
    r"引发.*争议",
    r"争议",
    r"转发",
    r"转载",
    r"go(?:es|ing)? viral",
    r"\bviral\b",
    r"\btrending\b",
    r"players? (?:are )?(?:debating|sharing|discussing)",
    r"community (?:is )?(?:debating|sharing|discussing)",
)

WEAK_DISCUSSION_PATTERNS = (
    r"欢迎.*评论区",
    r"评论区.*聊",
    r"你怎么看",
    r"你会.*吗",
    r"大家觉得",
)

GENERIC_MULTI_PLATFORM_PATTERNS = (
    r"多平台",
    r"多个平台",
    r"各平台",
    r"全网",
    r"海内外社区",
    r"社交媒体",
    r"across social media",
)


def _number(value: Any) -> float:
    if isinstance(value, (int, float)):
        return max(float(value), 0.0)
    if isinstance(value, str):
        cleaned = value.replace(",", "").strip()
        try:
            return max(float(cleaned), 0.0)
        except ValueError:
            return 0.0
    return 0.0


def _search(pattern: str, text: str) -> bool:
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def _text_blob(candidate: dict[str, Any], evidence_texts: list[str] | None) -> str:
    tags = " ".join(str(tag) for tag in candidate.get("tags", []))
    parts = [
        candidate.get("title", ""),
        candidate.get("snippet", ""),
        candidate.get("description", ""),
        candidate.get("query", ""),
        candidate.get("url", ""),
        candidate.get("source_id", ""),
        tags,
        " ".join(evidence_texts or []),
    ]
    return " ".join(str(part) for part in parts if part).lower()


def _detect_platforms(text: str) -> list[str]:
    platforms: list[str] = []
    for platform, patterns in PLATFORM_PATTERNS.items():
        if any(_search(pattern, text) for pattern in patterns):
            platforms.append(platform)
    return platforms


def _engagement_score(signals: dict[str, Any]) -> tuple[float, list[str], bool]:
    raw = 0.0
    reasons: list[str] = []
    has_direct_engagement = False
    for key, weight in ENGAGEMENT_WEIGHTS.items():
        value = _number(signals.get(key))
        if value <= 0:
            continue
        raw += value * weight
        reasons.append(f"engagement:{key}")
        if key in DIRECT_ENGAGEMENT_KEYS:
            has_direct_engagement = True

    if raw <= 0:
        return 0.0, [], False
    return min(45.0, 8.0 + math.log1p(raw) * 7.0), reasons, has_direct_engagement


def _language_score(text: str) -> tuple[float, list[str], bool]:
    strong_hits = sum(1 for pattern in STRONG_DISCUSSION_PATTERNS if _search(pattern, text))
    weak_hits = sum(1 for pattern in WEAK_DISCUSSION_PATTERNS if _search(pattern, text))

    score = 0.0
    reasons: list[str] = []
    if strong_hits:
        score += min(34.0, 22.0 + strong_hits * 4.0)
        reasons.append("discussion_language:hot_topic")
    if weak_hits:
        score += 10.0
        reasons.append("weak_call_to_comment_only")
    return score, reasons, bool(strong_hits)


def _platform_score(platforms: list[str], text: str) -> tuple[float, list[str], bool]:
    has_generic_multi = any(_search(pattern, text) for pattern in GENERIC_MULTI_PLATFORM_PATTERNS)
    reasons: list[str] = []
    if len(platforms) >= 2 or has_generic_multi:
        reasons.append("multi_platform_discussion")
        return 30.0, reasons, True
    if len(platforms) == 1:
        reasons.append(f"platform:{platforms[0]}")
        return 6.0, reasons, False
    return 0.0, reasons, False


def _level(score: float) -> str:
    if score >= 70:
        return "trending"
    if score >= 35:
        return "discussed"
    if score >= 10:
        return "weak"
    return "none"


def build_discussion_profile(
    candidate: dict[str, Any],
    evidence_texts: list[str] | None = None,
) -> dict[str, Any]:
    """Build a compact discussion profile from candidate metadata and text.

    This is intentionally conservative: a single embedded platform plus a
    generic "comment below" prompt is only weak support, not a hot-topic proof.
    """

    text = _text_blob(candidate, evidence_texts)
    platforms = _detect_platforms(text)
    signals = candidate.get("heat_signals", {})
    if not isinstance(signals, dict):
        signals = {}

    engagement_score, engagement_reasons, has_direct_engagement = _engagement_score(signals)
    language_score, language_reasons, has_strong_language = _language_score(text)
    platform_score, platform_reasons, has_multi_platform = _platform_score(platforms, text)

    tags = {str(tag).lower() for tag in candidate.get("tags", [])}
    tag_score = 0.0
    tag_reasons: list[str] = []
    if "hot_discussion" in tags:
        tag_score += 16.0
        tag_reasons.append("tag:hot_discussion")

    score = min(100.0, engagement_score + language_score + platform_score + tag_score)
    level = _level(score)
    reasons = [*engagement_reasons, *platform_reasons, *language_reasons, *tag_reasons]
    has_discussion_evidence = (
        level in {"discussed", "trending"}
        and (has_direct_engagement or has_multi_platform or has_strong_language or "hot_discussion" in tags)
    )

    return {
        "score": round(score, 2),
        "level": level,
        "platforms": platforms,
        "reasons": reasons,
        "engagement_score": round(engagement_score, 2),
        "discussion_language_score": round(language_score, 2),
        "platform_diversity_score": round(platform_score, 2),
        "has_direct_engagement": has_direct_engagement,
        "has_multi_platform_discussion": has_multi_platform,
        "has_discussion_evidence": has_discussion_evidence,
    }
