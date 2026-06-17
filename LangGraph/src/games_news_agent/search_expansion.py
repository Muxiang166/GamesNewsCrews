"""Theme-based low-frequency search expansion.

SearchExpansion expands the candidate pool with auditable search leads. It is
kept separate from DiscussionProbe: expansion discovers possible leads, while
DiscussionProbe evaluates discussion evidence for selected candidates.
"""

from __future__ import annotations

from datetime import datetime
import re
from typing import Any
from urllib.parse import quote_plus

from .discussion_probe_provider import (
    empty_discussion_probe_provider_report,
    run_discussion_probe_provider,
)
from .search_expansion_llm import result_is_llm_rejected


DEFAULT_SEARCH_EXPANSION_PLATFORMS = ("bilibili", "weibo")
DEFAULT_SEARCH_EXPANSION_METHODS = (
    "theme_gap",
    "event_burst",
    "candidate_followup",
    "new_content_watch",
)
THEME_TARGET = 20

THEME_QUERY_SEEDS: dict[str, list[str]] = {
    "sony": [
        "PlayStation PS5 玩家 热议",
        "索尼 游戏 争议 玩家",
        "PS5 新作 爆料 玩家讨论",
    ],
    "nintendo": [
        "Switch 2 玩家 热议",
        "任天堂 新作 曝光 玩家反馈",
        "Switch 2 涨价 争议",
    ],
    "microsoft": [
        "Xbox 玩家 热议",
        "微软 游戏 独占 争议",
        "Game Pass 新作 玩家讨论",
    ],
    "pc": [
        "Steam 新作 玩家 热议",
        "PC 游戏 争议 评论区",
        "Steam 差评 玩家讨论",
    ],
    "supplemental": [
        "游戏 梗图 玩家 离谱操作",
        "游戏 聊天截图 热议",
        "玩家 操作 笑疯 转发",
    ],
}

THEME_ORDER = ("nintendo", "sony", "microsoft", "pc", "supplemental")

EVENT_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("summer game fest", "Summer Game Fest"),
    ("xbox games showcase", "Xbox Games Showcase"),
    ("state of play", "State of Play"),
    ("nintendo direct", "Nintendo Direct"),
    ("gamescom", "gamescom"),
    ("tokyo game show", "Tokyo Game Show"),
    ("the game awards", "The Game Awards"),
    ("showcase", "showcase"),
    ("direct", "Direct"),
    ("\u6e38\u620f\u8282", "\u6e38\u620f\u8282"),
    ("\u6e38\u620f\u5c55", "\u6e38\u620f\u5c55"),
    ("\u53d1\u5e03\u4f1a", "\u53d1\u5e03\u4f1a"),
    ("\u76f4\u9762\u4f1a", "\u76f4\u9762\u4f1a"),
    ("\u5c55\u793a\u4f1a", "\u5c55\u793a\u4f1a"),
)

GENERIC_EVENT_LABELS = {
    "showcase",
    "Direct",
    "\u6e38\u620f\u8282",
    "\u6e38\u620f\u5c55",
    "\u53d1\u5e03\u4f1a",
    "\u76f4\u9762\u4f1a",
    "\u5c55\u793a\u4f1a",
}

NEW_CONTENT_KEYWORDS: tuple[str, ...] = (
    "announced",
    "reveal",
    "reveals",
    "revealed",
    "new trailer",
    "release date",
    "demo",
    "world premiere",
    "gameplay trailer",
    "\u516c\u5e03",
    "\u516c\u5f00",
    "\u65b0\u4f5c",
    "\u65b0\u9884\u544a",
    "\u53d1\u552e\u65e5",
    "\u8bd5\u73a9",
    "\u5b9e\u673a",
    "\u9996\u66dd",
)

EVENT_BURST_QUERY_TEMPLATES: tuple[tuple[str, str], ...] = (
    ("pc", "{event_name} new games trailer release date discussion"),
    ("microsoft", "Xbox {event_name} new games player reactions"),
    ("sony", "PlayStation {event_name} new games player reactions"),
    ("nintendo", "Nintendo {event_name} new games player reactions"),
    ("supplemental", "{event_name} memes player reactions"),
)

NEW_CONTENT_WATCH_TEMPLATES: tuple[tuple[str, str], ...] = (
    ("pc", "new game announced trailer player discussion"),
    ("microsoft", "Xbox new game reveal player discussion"),
    ("sony", "PlayStation new game reveal player discussion"),
    ("nintendo", "Nintendo new game reveal player discussion"),
    ("supplemental", "game showcase memes player reactions"),
)

DISCUSSION_SUFFIX = "\u73a9\u5bb6\u8ba8\u8bba \u70ed\u8bae"


def _theme_counts(source_theme_counts: dict[str, Any]) -> dict[str, int]:
    summary = source_theme_counts.get("summary", {}) if isinstance(source_theme_counts, dict) else {}
    counts = summary.get("theme_counts", {}) if isinstance(summary, dict) else {}
    result: dict[str, int] = {theme_id: 0 for theme_id in THEME_QUERY_SEEDS}
    if isinstance(counts, dict) and counts:
        for theme_id in THEME_QUERY_SEEDS:
            value = counts.get(theme_id, 0)
            result[theme_id] = value if isinstance(value, int) else 0
        return result
    sources = source_theme_counts.get("sources", []) if isinstance(source_theme_counts, dict) else []
    if isinstance(sources, list):
        for source in sources:
            if not isinstance(source, dict):
                continue
            theme_counts = source.get("theme_counts", {})
            if not isinstance(theme_counts, dict):
                continue
            for theme_id in THEME_QUERY_SEEDS:
                value = theme_counts.get(theme_id, 0)
                if isinstance(value, int):
                    result[theme_id] += value
    return result


def _candidate_text(candidate: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("title", "snippet", "query", "source_id", "theme_section"):
        value = candidate.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value)
    return " ".join(parts)


def _normalize_query_text(value: str, *, max_length: int = 96) -> str:
    text = re.sub(r"https?://\S+", " ", value)
    text = re.sub(r"[\[\]{}()|<>]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_length:
        return text
    return text[:max_length].rsplit(" ", 1)[0].strip() or text[:max_length].strip()


def _normalize_event_query(value: str) -> str:
    text = value
    for brand in ("Xbox", "PlayStation", "Nintendo"):
        text = re.sub(rf"\b{brand}\s+{brand}\b", brand, text, flags=re.IGNORECASE)
    return _normalize_query_text(text)


def detect_event_context(
    candidates: list[dict[str, Any]] | None,
    *,
    source_theme_counts: dict[str, Any] | None = None,
    threshold: int = 2,
) -> dict[str, Any]:
    """Detect whether current candidates look like a showcase/festival burst day."""

    del source_theme_counts
    event_hits: list[str] = []
    event_labels: list[str] = []
    new_content_hits: list[str] = []
    for candidate in candidates or []:
        if not isinstance(candidate, dict):
            continue
        lowered = _candidate_text(candidate).lower()
        if not lowered:
            continue
        for keyword, label in EVENT_KEYWORDS:
            if keyword.lower() in lowered and keyword not in event_hits:
                event_hits.append(keyword)
                event_labels.append(label)
        for keyword in NEW_CONTENT_KEYWORDS:
            if keyword.lower() in lowered and keyword not in new_content_hits:
                new_content_hits.append(keyword)

    signal_count = len(event_hits) + len(new_content_hits)
    active = bool(event_hits and new_content_hits) or len(new_content_hits) >= max(threshold + 1, 3)
    specific_event_names = [label for label in event_labels if label not in GENERIC_EVENT_LABELS]
    event_name = specific_event_names[0] if specific_event_names else (event_labels[0] if event_labels else "")
    if not event_name and active:
        event_name = "game showcase"
    return {
        "active": active,
        "event_name": event_name,
        "signal_count": signal_count,
        "signals": [*event_hits, *new_content_hits][:12],
        "event_signal_count": len(event_hits),
        "new_content_signal_count": len(new_content_hits),
        "quota_policy": "event_burst" if active else "normal",
    }


def _search_target(platform: str, query: str) -> dict[str, Any]:
    encoded = quote_plus(query)
    if platform == "bilibili":
        url = f"https://search.bilibili.com/all?keyword={encoded}"
        access = "public_search_page"
    elif platform == "weibo":
        url = f"https://s.weibo.com/weibo?q={encoded}"
        access = "public_search_page"
    elif platform == "reddit":
        url = f"https://www.reddit.com/search/?q={encoded}&sort=new"
        access = "public_search_page"
    elif platform == "steam":
        url = f"https://steamcommunity.com/search/?q={encoded}"
        access = "public_search_page"
    else:
        url = ""
        access = "manual_or_api_required"
    return {
        "platform": platform,
        "query": query,
        "url": url,
        "access": access,
    }


def _request_base(
    *,
    method: str,
    theme_section: str,
    query: str,
    platforms: tuple[str, ...],
    usage_policy: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    request = {
        "method": method,
        "theme_section": theme_section,
        "query": query,
        "usage_policy": usage_policy,
        "search_targets": [_search_target(platform, query) for platform in platforms],
    }
    if extra:
        request.update(extra)
    return request


def _theme_priority(source_theme_counts: dict[str, Any]) -> list[str]:
    counts = _theme_counts(source_theme_counts)
    if not counts:
        return list(THEME_ORDER)
    return sorted(
        THEME_ORDER,
        key=lambda theme_id: (counts.get(theme_id, 0) >= THEME_TARGET, counts.get(theme_id, 0)),
    )


def _theme_gap_requests(
    *,
    topic: str,
    source_theme_counts: dict[str, Any],
    platforms: tuple[str, ...] = DEFAULT_SEARCH_EXPANSION_PLATFORMS,
) -> list[dict[str, Any]]:
    requests: list[dict[str, Any]] = []
    theme_ids = _theme_priority(source_theme_counts)
    max_seed_count = max((len(THEME_QUERY_SEEDS.get(theme_id, [])) for theme_id in theme_ids), default=0)
    for seed_index in range(max_seed_count):
        for theme_id in theme_ids:
            seeds = THEME_QUERY_SEEDS.get(theme_id, [])
            if seed_index >= len(seeds):
                continue
            seed = seeds[seed_index]
            query = f"{seed} {topic}".strip() if topic and topic.lower() != "games" else seed
            requests.append(
                _request_base(
                    method="theme_gap",
                    theme_section=theme_id,
                    query=query,
                    platforms=platforms,
                    usage_policy="low_frequency_search_expansion",
                )
            )
    return requests


def _event_burst_requests(
    *,
    event_context: dict[str, Any],
    platforms: tuple[str, ...],
) -> list[dict[str, Any]]:
    if not event_context.get("active"):
        return []
    event_name = str(event_context.get("event_name") or "game showcase").strip()
    requests: list[dict[str, Any]] = []
    for theme_section, template in EVENT_BURST_QUERY_TEMPLATES:
        query = _normalize_event_query(template.format(event_name=event_name))
        requests.append(
            _request_base(
                method="event_burst",
                theme_section=theme_section,
                query=query,
                platforms=platforms,
                usage_policy="event_burst_search_expansion",
                extra={
                    "event_context": event_context,
                    "allow_briefing_overflow": True,
                    "quota_policy": "event_burst_briefing_candidate",
                },
            )
        )
    return requests


def _new_content_watch_requests(
    *,
    event_context: dict[str, Any],
    platforms: tuple[str, ...],
) -> list[dict[str, Any]]:
    if not event_context.get("active"):
        return []
    event_name = str(event_context.get("event_name") or "game showcase").strip()
    return [
        _request_base(
            method="new_content_watch",
            theme_section=theme_section,
            query=_normalize_query_text(f"{event_name} {query}"),
            platforms=platforms,
            usage_policy="new_content_watch_search_expansion",
            extra={
                "event_context": event_context,
                "allow_briefing_overflow": True,
                "quota_policy": "event_burst_briefing_candidate",
            },
        )
        for theme_section, query in NEW_CONTENT_WATCH_TEMPLATES
    ]


def _candidate_followup_requests(
    *,
    candidates: list[dict[str, Any]] | None,
    platforms: tuple[str, ...],
    limit: int,
) -> list[dict[str, Any]]:
    requests: list[dict[str, Any]] = []
    for candidate in candidates or []:
        if not isinstance(candidate, dict):
            continue
        title = _normalize_query_text(str(candidate.get("title") or ""))
        url = str(candidate.get("url") or "").strip()
        if not title or not url:
            continue
        theme_section = str(candidate.get("theme_section") or "supplemental")
        query = _normalize_query_text(f"{title} {DISCUSSION_SUFFIX}")
        requests.append(
            _request_base(
                method="candidate_followup",
                theme_section=theme_section,
                query=query,
                platforms=platforms,
                usage_policy="candidate_followup_search_expansion",
                extra={
                    "source_candidate_url": url,
                    "source_candidate_title": title,
                },
            )
        )
        if len(requests) >= max(limit, 0):
            break
    return requests


def _select_requests_round_robin(
    buckets: dict[str, list[dict[str, Any]]],
    *,
    methods: tuple[str, ...],
    limit: int,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen_queries: set[str] = set()
    indexes = {method: 0 for method in methods}
    max_limit = max(limit, 0)
    while len(selected) < max_limit:
        added = False
        for method in methods:
            items = buckets.get(method, [])
            index = indexes.get(method, 0)
            while index < len(items):
                indexes[method] = index + 1
                item = dict(items[index])
                index += 1
                query_key = str(item.get("query") or "").strip().lower()
                if not query_key or query_key in seen_queries:
                    continue
                seen_queries.add(query_key)
                item["request_id"] = (
                    f"search-expansion-{item.get('method', method)}-"
                    f"{item.get('theme_section', 'supplemental')}-{len(selected) + 1}"
                )
                selected.append(item)
                added = True
                break
            if len(selected) >= max_limit:
                break
        if not added:
            break
    return selected


def build_search_expansion_requests(
    *,
    topic: str,
    source_theme_counts: dict[str, Any],
    candidates: list[dict[str, Any]] | None = None,
    methods: tuple[str, ...] = DEFAULT_SEARCH_EXPANSION_METHODS,
    limit: int = 10,
    platforms: tuple[str, ...] = DEFAULT_SEARCH_EXPANSION_PLATFORMS,
) -> list[dict[str, Any]]:
    """Build low-frequency search expansion requests from several auditable methods."""

    active_methods = tuple(method for method in methods if isinstance(method, str))
    event_context = detect_event_context(
        candidates,
        source_theme_counts=source_theme_counts,
    )
    buckets: dict[str, list[dict[str, Any]]] = {
        "theme_gap": _theme_gap_requests(
            topic=topic,
            source_theme_counts=source_theme_counts,
            platforms=platforms,
        ),
        "event_burst": _event_burst_requests(
            event_context=event_context,
            platforms=platforms,
        ),
        "candidate_followup": _candidate_followup_requests(
            candidates=candidates,
            platforms=platforms,
            limit=max(limit, 0),
        ),
        "new_content_watch": _new_content_watch_requests(
            event_context=event_context,
            platforms=platforms,
        ),
    }
    return _select_requests_round_robin(
        buckets,
        methods=active_methods,
        limit=limit,
    )


def _as_probe_request(request: dict[str, Any]) -> dict[str, Any]:
    request_id = str(request.get("request_id") or "")
    return {
        "candidate_url": f"search-expansion://{request_id}",
        "candidate_title": str(request.get("query") or ""),
        "query": str(request.get("query") or ""),
        "search_targets": request.get("search_targets", []),
    }


def run_search_expansion_provider(
    requests: list[dict[str, Any]],
    *,
    fetcher: Any,
    request_limit: int = 10,
    platform_limit: int = 2,
) -> dict[str, Any]:
    """Run public-search observations for expansion requests."""

    if request_limit <= 0 or platform_limit <= 0:
        return empty_discussion_probe_provider_report()

    selected = [request for request in requests if isinstance(request, dict)][:request_limit]
    probe_requests = [_as_probe_request(request) for request in selected]
    report = run_discussion_probe_provider(
        probe_requests,
        fetcher=fetcher,
        candidate_limit=request_limit,
        platform_limit=platform_limit,
    )
    by_probe_url = {
        f"search-expansion://{request.get('request_id')}": request
        for request in selected
        if request.get("request_id")
    }
    observations: list[dict[str, Any]] = []
    method_counts: dict[str, int] = {}
    for observation in report.get("observations", []):
        if not isinstance(observation, dict):
            continue
        item = dict(observation)
        request = by_probe_url.get(str(item.get("candidate_url") or ""), {})
        item["request_id"] = request.get("request_id", "")
        item["theme_section"] = request.get("theme_section", "")
        item["method"] = request.get("method", "")
        for key in (
            "event_context",
            "quota_policy",
            "allow_briefing_overflow",
            "source_candidate_url",
            "source_candidate_title",
            "usage_policy",
        ):
            if key in request:
                item[key] = request[key]
        method = str(item.get("method") or "unknown")
        method_counts[method] = method_counts.get(method, 0) + 1
        observations.append(item)
    report["observations"] = observations
    summary = report.get("summary", {})
    if isinstance(summary, dict):
        summary["method_counts"] = method_counts
    return report


def _candidate_key(title: str, url: str) -> str:
    return f"{title.strip().lower()}|{url.strip().lower()}"


def _heat_score(observation: dict[str, Any]) -> float:
    result_count = observation.get("result_count", 0)
    hint_count = observation.get("discussion_hint_count", 0)
    if not isinstance(result_count, int):
        result_count = 0
    if not isinstance(hint_count, int):
        hint_count = 0
    return min(45.0, 14.0 + result_count * 2.0 + hint_count * 5.0)


def build_search_expansion_candidates(
    observations_report: dict[str, Any],
    *,
    discovered_at: datetime,
    per_observation_limit: int = 2,
) -> list[dict[str, Any]]:
    """Convert relevant search observations into supplemental candidate leads."""

    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    observations = observations_report.get("observations", []) if isinstance(observations_report, dict) else []
    if not isinstance(observations, list):
        return candidates

    for observation in observations:
        if not isinstance(observation, dict) or not observation.get("has_result_signal"):
            continue
        platform = str(observation.get("platform") or "search")
        theme_section = str(observation.get("theme_section") or "supplemental")
        top_results = observation.get("top_results", [])
        if not isinstance(top_results, list):
            continue
        for result in top_results[: max(per_observation_limit, 0)]:
            if not isinstance(result, dict):
                continue
            if result_is_llm_rejected(result):
                continue
            title = str(result.get("title") or "").strip()
            url = str(result.get("url") or "").strip()
            if not title or not url:
                continue
            key = _candidate_key(title, url)
            if key in seen:
                continue
            seen.add(key)
            method = str(observation.get("method") or "theme_gap")
            event_context = observation.get("event_context")
            allow_briefing_overflow = bool(observation.get("allow_briefing_overflow"))
            quota_policy = str(observation.get("quota_policy") or "normal")
            search_expansion = {
                "request_id": observation.get("request_id", ""),
                "method": method,
                "platform": platform,
                "result_count": observation.get("result_count", 0),
                "discussion_hint_count": observation.get("discussion_hint_count", 0),
            }
            if observation.get("source_candidate_url"):
                search_expansion["source_candidate_url"] = observation.get("source_candidate_url")
                search_expansion["source_candidate_title"] = observation.get("source_candidate_title", "")
            item = {
                "title": title,
                "url": url,
                "source_id": f"search_expansion_{platform}",
                "snippet": str(observation.get("evidence_texts", [""])[0])[:280]
                if observation.get("evidence_texts")
                else title,
                "query": str(observation.get("query") or ""),
                "discovered_at": discovered_at.isoformat(),
                "observed_at": discovered_at.isoformat(),
                "heat_signals": {
                    "search_result_count": observation.get("result_count", 0),
                    "discussion_hint_count": observation.get("discussion_hint_count", 0),
                },
                "tags": ["search_expansion", "discussion_search_lead", platform, f"method:{method}"],
                "candidate_type": "discussion_search_lead",
                "candidate_lane": "supplemental",
                "candidate_type_reasons": ["search_expansion_observation"],
                "theme_section": theme_section,
                "heat_score": _heat_score(observation),
                "heat_reasons": [
                    "search-expansion",
                    f"platform:{platform}",
                    f"method:{method}",
                ],
                "search_expansion": search_expansion,
            }
            if allow_briefing_overflow:
                item["allow_briefing_overflow"] = True
                item["quota_policy"] = quota_policy
            if isinstance(event_context, dict) and event_context:
                item["event_context"] = event_context
            candidates.append(
                item
            )
    return candidates
