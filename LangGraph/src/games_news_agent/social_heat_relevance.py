"""Deterministic relevance checks for social heat observations."""

from __future__ import annotations

from collections import Counter
import re
from typing import Any


SUBJECT_PATTERNS: dict[str, tuple[str, ...]] = {
    "switch_2": ("switch 2", "switch2", "ns2", "switch 二代"),
    "switch": ("switch", "任天堂", "nintendo"),
    "nintendo": ("nintendo", "任天堂"),
    "xbox": ("xbox", "微软", "microsoft"),
    "playstation": ("playstation", "ps5", "ps4", "索尼", "sony"),
    "steam": ("steam",),
    "pc": ("pc", "电脑"),
}

EVENT_PATTERNS: dict[str, tuple[str, ...]] = {
    "price": ("price", "价格", "涨价", "售价", "定价"),
    "trailer": ("trailer", "预告", "pv"),
    "showcase": ("showcase", "发布会", "直面会", "展示会"),
    "release": ("release", "released", "发售", "上线", "公布", "官宣"),
    "demo": ("demo", "试玩"),
    "rumor": ("rumor", "leak", "爆料", "传闻", "流言"),
    "update": ("update", "patch", "更新", "补丁"),
    "delay": ("delay", "delayed", "延期", "跳票"),
    "meme": ("meme", "梗图", "爆笑", "整活"),
    "discussion": ("debate", "discussion", "讨论", "热议", "争议"),
}

TIME_WITHIN_PATTERNS = (
    r"最近一天",
    r"今天",
    r"昨日",
    r"昨天",
    r"\d+\s*(?:h|hr|hrs|hour|hours)\s*ago",
    r"\d+\s*(?:m|min|mins|minute|minutes)\s*ago",
    r"\d+\s*小时前",
    r"\d+\s*分钟前",
    r"\b0?[1-9]-[0-3]?\d\b",
    r"\b1[0-2]-[0-3]?\d\b",
    r"\b20\d{2}-[01]?\d-[0-3]?\d\b",
)

TIME_OUTSIDE_PATTERNS = (
    r"202[0-5]",
    r"201\d",
    r"去年",
    r"往年",
    r"old news",
)

RESULT_TYPE_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("video", ("bilibili.com/video", "youtube.com/watch", "youtu.be")),
    ("steam_discussion", ("steamcommunity.com",)),
    ("user_page", ("space.bilibili.com", "/user/", "profile")),
    ("shopping_or_deal", ("优惠", "折扣", "deal", "sale", "手柄")),
    ("article_or_post", ("article", "post", "thread")),
)

SEMANTIC_QUESTIONS = ["same_event", "same_game", "within_48h", "old_news", "marketing_or_clickbait"]


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _normalized(value: Any) -> str:
    return _clean(value).lower()


def _remove_self_reference(text: str, candidate: dict[str, Any], observation: dict[str, Any]) -> tuple[str, bool]:
    cleaned = text
    removed = False
    for value in (
        candidate.get("title"),
        candidate.get("query"),
        observation.get("candidate_title"),
        observation.get("query"),
    ):
        ref = _clean(value)
        if ref and ref in cleaned:
            cleaned = cleaned.replace(ref, " ")
            removed = True
    return " ".join(cleaned.split()), removed


def _result_text(observation: dict[str, Any]) -> tuple[str, str]:
    top_results = observation.get("top_results", [])
    first_result_url = ""
    parts: list[str] = []
    if isinstance(top_results, list):
        for result in top_results[:3]:
            if not isinstance(result, dict):
                continue
            if not first_result_url:
                first_result_url = _clean(result.get("url"))
            parts.extend([_clean(result.get("title")), _clean(result.get("snippet"))])
    evidence_texts = observation.get("evidence_texts", [])
    if isinstance(evidence_texts, list):
        parts.extend(_clean(item) for item in evidence_texts[:2])
    return " ".join(part for part in parts if part), first_result_url


def _extract_entities(text: str, patterns: dict[str, tuple[str, ...]]) -> set[str]:
    normalized = _normalized(text)
    entities: set[str] = set()
    for entity, aliases in patterns.items():
        if any(alias.lower() in normalized for alias in aliases):
            entities.add(entity)
    return entities


def _time_hint_status(text: str) -> str:
    normalized = _normalized(text)
    if any(re.search(pattern, normalized, flags=re.IGNORECASE) for pattern in TIME_OUTSIDE_PATTERNS):
        return "outside_window"
    if any(re.search(pattern, normalized, flags=re.IGNORECASE) for pattern in TIME_WITHIN_PATTERNS):
        return "within_window"
    return "unknown_time"


def _result_type(text: str, result_url: str) -> str:
    haystack = f"{_normalized(text)} {_normalized(result_url)}"
    for result_type, markers in RESULT_TYPE_PATTERNS:
        if any(marker.lower() in haystack for marker in markers):
            return result_type
    return "unknown"


def _observation_id(observation: dict[str, Any], index: int = 0) -> str:
    value = _clean(observation.get("observation_id") or observation.get("id"))
    if value:
        return value
    candidate_url = _clean(observation.get("candidate_url"))
    platform = _clean(observation.get("platform") or "unknown")
    safe_url = re.sub(r"[^a-zA-Z0-9]+", "_", candidate_url).strip("_")[:48]
    return f"{platform}_{safe_url}_{index}"


def classify_social_heat_result(candidate: dict[str, Any], observation: dict[str, Any]) -> dict[str, Any]:
    """Classify one social heat observation without LLM or RAG."""

    raw_text, result_url = _result_text(observation)
    comparable_text, removed_self_reference = _remove_self_reference(raw_text, candidate, observation)
    candidate_text = " ".join(
        _clean(value)
        for value in (
            candidate.get("title"),
            candidate.get("snippet"),
            candidate.get("theme_section"),
        )
        if _clean(value)
    )
    candidate_subjects = _extract_entities(candidate_text, SUBJECT_PATTERNS)
    result_subjects = _extract_entities(comparable_text, SUBJECT_PATTERNS)
    candidate_events = _extract_entities(candidate_text, EVENT_PATTERNS)
    result_events = _extract_entities(comparable_text, EVENT_PATTERNS)
    matched_subjects = sorted(candidate_subjects & result_subjects)
    matched_events = sorted(candidate_events & result_events)
    missing_entities = sorted((candidate_subjects | candidate_events) - (result_subjects | result_events))
    time_status = _time_hint_status(comparable_text)
    result_type = _result_type(comparable_text, result_url)

    reasons: list[str] = []
    if removed_self_reference:
        reasons.append("self_reference_removed")
    if matched_subjects:
        reasons.append("matched_subject_entity")
    if matched_events:
        reasons.append("matched_event_entity")
    if candidate_events and not matched_events:
        reasons.append("missing_event_entity")
    if not comparable_text:
        reasons.append("empty_result_text")

    if matched_subjects and matched_events:
        deterministic_status = "same_game_unclear_event"
    elif matched_subjects:
        deterministic_status = "same_platform_only"
    elif comparable_text:
        deterministic_status = "off_topic"
    else:
        deterministic_status = "unknown"

    return {
        "candidate_id": _clean(candidate.get("candidate_id") or candidate.get("id")),
        "candidate_url": _clean(candidate.get("url") or candidate.get("candidate_url") or observation.get("candidate_url")),
        "candidate_title": _clean(candidate.get("title") or observation.get("candidate_title")),
        "observation_id": _observation_id(observation),
        "platform": _clean(observation.get("platform") or "unknown"),
        "result_url": result_url,
        "deterministic_status": deterministic_status,
        "matched_entities": [*matched_subjects, *matched_events],
        "missing_entities": missing_entities,
        "time_hint_status": time_status,
        "result_type": result_type,
        "reasons": reasons,
        "requires_semantic_review": deterministic_status in {"same_game_unclear_event", "likely_same_event"}
        and time_status != "outside_window",
    }


def _candidate_by_url(candidates: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        _clean(candidate.get("url") or candidate.get("candidate_url")): candidate
        for candidate in candidates
        if isinstance(candidate, dict) and _clean(candidate.get("url") or candidate.get("candidate_url"))
    }


def build_social_heat_relevance_checks(
    candidates: list[dict[str, Any]],
    observations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return deterministic relevance checks for social heat observations."""

    candidates_by_url = _candidate_by_url(candidates)
    checks: list[dict[str, Any]] = []
    for index, observation in enumerate(observations):
        if not isinstance(observation, dict):
            continue
        candidate_url = _clean(observation.get("candidate_url"))
        candidate = candidates_by_url.get(candidate_url)
        if not candidate:
            candidate = {
                "title": observation.get("candidate_title", ""),
                "url": candidate_url,
            }
        check = classify_social_heat_result(candidate, {**observation, "observation_id": _observation_id(observation, index)})
        checks.append(check)
    return checks


def build_social_heat_relevance_summary(checks: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(item.get("deterministic_status") or "unknown") for item in checks)
    time_counts = Counter(str(item.get("time_hint_status") or "unknown_time") for item in checks)
    type_counts = Counter(str(item.get("result_type") or "unknown") for item in checks)
    return {
        "total_checks": len(checks),
        "status_counts": dict(status_counts),
        "time_hint_counts": dict(time_counts),
        "result_type_counts": dict(type_counts),
        "semantic_review_candidates": sum(1 for item in checks if item.get("requires_semantic_review")),
    }


def build_semantic_relevance_requests(
    checks: list[dict[str, Any]],
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    requests: list[dict[str, Any]] = []
    for check in checks:
        if not check.get("requires_semantic_review"):
            continue
        requests.append(
            {
                "request_id": f"semantic_relevance_{len(requests) + 1}",
                "candidate_url": check.get("candidate_url", ""),
                "observation_id": check.get("observation_id", ""),
                "deterministic_status": check.get("deterministic_status", "unknown"),
                "candidate": {
                    "title": check.get("candidate_title", ""),
                    "url": check.get("candidate_url", ""),
                },
                "observation": {
                    "platform": check.get("platform", ""),
                    "result_url": check.get("result_url", ""),
                    "matched_entities": check.get("matched_entities", []),
                    "time_hint_status": check.get("time_hint_status", "unknown_time"),
                    "result_type": check.get("result_type", "unknown"),
                    "reasons": check.get("reasons", []),
                },
                "evidence_context_ids": [],
                "questions": list(SEMANTIC_QUESTIONS),
            }
        )
        if len(requests) >= limit:
            break
    return requests
