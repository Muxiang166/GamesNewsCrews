"""LLM helpers for SearchExpansion query and result filtering.

This module is intentionally pure: it builds JSON-shaped LLM requests, parses
schema-shaped responses, and applies them to SearchExpansion artifacts. The
provider call remains in ``llm_provider.py``.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote_plus


QUERY_COMPRESSION_METHODS = {"candidate_followup", "event_burst", "new_content_watch"}
ALLOWED_RELEVANCE = {
    "same_event",
    "same_game",
    "related_current",
    "unknown_time",
    "reject",
}
REJECT_RELEVANCE = {"reject"}

QUERY_COMPRESSION_INSTRUCTIONS = (
    "Return JSON only. You compress games-news search intent into 1-3 short "
    "queries for Chinese social search. Use only provided text. Do not invent "
    "game names, dates, platforms, or claims. Prefer game name + event/change. "
    "Avoid full sentences, adjectives, clickbait, and filler words."
)

RESULT_RELEVANCE_INSTRUCTIONS = (
    "Return JSON only. Classify whether each search result is a useful lead for "
    "the same games-news event. Do not verify the fact itself. Reject old news, "
    "generic discussion, similar but unrelated events, marketing reposts, and "
    "clickbait. If time is unclear, use unknown_time instead of guessing."
)


def _load_response(raw_response: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw_response, dict):
        return dict(raw_response)
    return json.loads(raw_response)


def _search_target(platform: str, query: str, *, access: str = "public_search_page") -> dict[str, Any]:
    encoded = quote_plus(query)
    if platform == "bilibili":
        url = f"https://search.bilibili.com/all?keyword={encoded}"
    elif platform == "weibo":
        url = f"https://s.weibo.com/weibo?q={encoded}"
    elif platform == "reddit":
        url = f"https://www.reddit.com/search/?q={encoded}&sort=new"
    elif platform == "steam":
        url = f"https://steamcommunity.com/search/?q={encoded}"
    elif platform == "tieba":
        url = f"https://tieba.baidu.com/f/search/res?ie=utf-8&qw={encoded}"
    else:
        url = ""
        access = "manual_or_api_required"
    return {
        "platform": platform,
        "query": query,
        "url": url,
        "access": access,
    }


def _query_is_usable(query: Any) -> bool:
    if not isinstance(query, str):
        return False
    text = query.strip()
    if not text:
        return False
    if len(text) > 24:
        return False
    if text.count(" ") > 3:
        return False
    return True


def _source_request_id(llm_request_id: str, prefix: str) -> str:
    if llm_request_id.startswith(prefix):
        return llm_request_id[len(prefix) :]
    return llm_request_id


def _source_and_platform_from_relevance_id(request_id: str) -> tuple[str, str]:
    rest = _source_request_id(request_id, "result-relevance-")
    if "-" not in rest:
        return rest, ""
    source_request_id, platform = rest.rsplit("-", 1)
    return source_request_id, platform


def build_query_compression_requests(
    expansion_requests: list[dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    """Build compact JSON requests for high-value SearchExpansion queries."""

    requests: list[dict[str, Any]] = []
    for request in expansion_requests:
        if not isinstance(request, dict):
            continue
        method = str(request.get("method") or "")
        if method not in QUERY_COMPRESSION_METHODS:
            continue
        source_request_id = str(request.get("request_id") or "")
        if not source_request_id:
            continue
        requests.append(
            {
                "request_id": f"query-compression-{source_request_id}",
                "schema_version": "search_query_compression_v0",
                "prompt_name": "search_query_compressor.md",
                "instructions": QUERY_COMPRESSION_INSTRUCTIONS,
                "source_request_id": source_request_id,
                "method": method,
                "theme_section": request.get("theme_section", ""),
                "fallback_query": str(request.get("query") or ""),
                "source_candidate_title": str(request.get("source_candidate_title") or ""),
                "source_candidate_url": str(request.get("source_candidate_url") or ""),
                "event_context": request.get("event_context", {}),
                "json_schema": {
                    "type": "object",
                    "required": ["queries", "confidence", "risk_flags"],
                    "properties": {
                        "queries": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
                        "entities": {"type": "object"},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "risk_flags": {"type": "array", "items": {"type": "string"}},
                    },
                },
            }
        )
        if len(requests) >= max(limit, 0):
            break
    return requests


def parse_query_compression_result(
    request_id: str,
    raw_response: str | dict[str, Any],
) -> dict[str, Any]:
    """Parse and sanitize a query-compression LLM response."""

    try:
        parsed = _load_response(raw_response)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        return {
            "request_id": request_id,
            "source_request_id": _source_request_id(request_id, "query-compression-"),
            "parse_status": "invalid_json",
            "queries": [],
            "confidence": 0.0,
            "risk_flags": ["invalid_llm_json"],
            "error": str(exc),
        }

    queries: list[str] = []
    for item in parsed.get("queries", []):
        if not _query_is_usable(item):
            continue
        query = str(item).strip()
        if query not in queries:
            queries.append(query)
        if len(queries) >= 3:
            break
    confidence = parsed.get("confidence", 0.0)
    if not isinstance(confidence, (int, float)):
        confidence = 0.0
    return {
        "request_id": request_id,
        "source_request_id": str(parsed.get("source_request_id") or _source_request_id(request_id, "query-compression-")),
        "parse_status": "parsed",
        "queries": queries,
        "entities": parsed.get("entities", {}) if isinstance(parsed.get("entities", {}), dict) else {},
        "confidence": max(0.0, min(float(confidence), 1.0)),
        "risk_flags": [
            str(item)
            for item in parsed.get("risk_flags", [])
            if str(item).strip()
        ],
    }


def _coerce_query_result(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("parse_status") == "ok" and result.get("content"):
        return parse_query_compression_result(str(result.get("request_id") or ""), str(result.get("content") or ""))
    return dict(result)


def _platforms_from_targets(targets: Any) -> list[tuple[str, str]]:
    platforms: list[tuple[str, str]] = []
    if not isinstance(targets, list):
        return platforms
    for target in targets:
        if not isinstance(target, dict):
            continue
        platform = str(target.get("platform") or "")
        if not platform:
            continue
        access = str(target.get("access") or "public_search_page")
        platforms.append((platform, access))
    return platforms


def apply_query_compression_results(
    expansion_requests: list[dict[str, Any]],
    llm_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Apply compressed query choices while preserving fallback queries."""

    normalized_results = [_coerce_query_result(result) for result in llm_results if isinstance(result, dict)]
    by_source_id = {
        str(result.get("source_request_id") or _source_request_id(str(result.get("request_id") or ""), "query-compression-")): result
        for result in normalized_results
    }
    updated: list[dict[str, Any]] = []
    for request in expansion_requests:
        if not isinstance(request, dict):
            continue
        item = dict(request)
        source_request_id = str(item.get("request_id") or "")
        fallback_query = str(item.get("query") or "")
        result = by_source_id.get(source_request_id)
        if not result:
            updated.append(item)
            continue
        queries = result.get("queries", []) if result.get("parse_status") == "parsed" else []
        selected_query = str(queries[0]).strip() if isinstance(queries, list) and queries else ""
        item["fallback_query"] = fallback_query
        item["llm_query_compression"] = result
        if selected_query:
            item["query"] = selected_query
            item["query_source"] = "llm_compressed"
            platforms = _platforms_from_targets(item.get("search_targets", []))
            item["search_targets"] = [
                _search_target(platform, selected_query, access=access)
                for platform, access in platforms
            ]
        else:
            item["query_source"] = "fallback"
        updated.append(item)
    return updated


def build_result_relevance_requests(
    observations_report: dict[str, Any],
    *,
    limit: int,
    lookback_hours: int = 48,
) -> list[dict[str, Any]]:
    """Build batched relevance-classification requests from search observations."""

    observations = observations_report.get("observations", []) if isinstance(observations_report, dict) else []
    requests: list[dict[str, Any]] = []
    if not isinstance(observations, list):
        return requests
    for observation in observations:
        if not isinstance(observation, dict) or observation.get("status") != "ok":
            continue
        top_results = observation.get("top_results", [])
        if not isinstance(top_results, list) or not top_results:
            continue
        source_request_id = str(observation.get("request_id") or "")
        platform = str(observation.get("platform") or "search")
        if not source_request_id:
            continue
        requests.append(
            {
                "request_id": f"result-relevance-{source_request_id}-{platform}",
                "schema_version": "search_result_relevance_v0",
                "prompt_name": "search_result_relevance.md",
                "instructions": RESULT_RELEVANCE_INSTRUCTIONS,
                "source_request_id": source_request_id,
                "platform": platform,
                "query": str(observation.get("query") or ""),
                "candidate_title": str(observation.get("candidate_title") or ""),
                "event_context": observation.get("event_context", {}),
                "lookback_hours": lookback_hours,
                "allowed_relevance": sorted(ALLOWED_RELEVANCE),
                "results": [
                    {
                        "title": str(result.get("title") or ""),
                        "url": str(result.get("url") or ""),
                        "snippet": str(result.get("snippet") or ""),
                    }
                    for result in top_results[:5]
                    if isinstance(result, dict)
                ],
            }
        )
        if len(requests) >= max(limit, 0):
            break
    return requests


def _normal_relevance_item(item: dict[str, Any]) -> dict[str, Any]:
    relevance = str(item.get("relevance") or "reject")
    risk_flags = [
        str(flag)
        for flag in item.get("risk_flags", [])
        if str(flag).strip()
    ]
    if relevance not in ALLOWED_RELEVANCE:
        relevance = "reject"
        risk_flags.append("invalid_relevance")
    confidence = item.get("confidence", 0.0)
    if not isinstance(confidence, (int, float)):
        confidence = 0.0
    return {
        "url": str(item.get("url") or ""),
        "relevance": relevance,
        "same_game": bool(item.get("same_game")),
        "same_event": bool(item.get("same_event")),
        "current_window_valid": bool(item.get("current_window_valid")),
        "reject_reason": str(item.get("reject_reason") or ""),
        "confidence": max(0.0, min(float(confidence), 1.0)),
        "risk_flags": risk_flags,
    }


def parse_result_relevance_result(
    request_id: str,
    raw_response: str | dict[str, Any],
) -> dict[str, Any]:
    """Parse and normalize batched search-result relevance response."""

    try:
        parsed = _load_response(raw_response)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        source_request_id, platform = _source_and_platform_from_relevance_id(request_id)
        return {
            "request_id": request_id,
            "source_request_id": source_request_id,
            "platform": platform,
            "parse_status": "invalid_json",
            "results": [],
            "risk_flags": ["invalid_llm_json"],
            "error": str(exc),
        }
    source_request_id, platform = _source_and_platform_from_relevance_id(request_id)
    return {
        "request_id": request_id,
        "source_request_id": str(parsed.get("source_request_id") or source_request_id),
        "platform": str(parsed.get("platform") or platform),
        "parse_status": "parsed",
        "results": [
            _normal_relevance_item(item)
            for item in parsed.get("results", [])
            if isinstance(item, dict)
        ],
    }


def _coerce_relevance_result(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("parse_status") == "ok" and result.get("content"):
        parsed = parse_result_relevance_result(str(result.get("request_id") or ""), str(result.get("content") or ""))
        if result.get("source_request_id") and not parsed.get("source_request_id"):
            parsed["source_request_id"] = result["source_request_id"]
        return parsed
    return dict(result)


def apply_result_relevance_results(
    observations_report: dict[str, Any],
    llm_results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Attach LLM relevance decisions to top results without dropping artifacts."""

    normalized_results = [_coerce_relevance_result(result) for result in llm_results if isinstance(result, dict)]
    by_observation: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
    for result in normalized_results:
        if result.get("parse_status") != "parsed":
            continue
        source_request_id = str(result.get("source_request_id") or "")
        platform = str(result.get("platform") or "")
        url_map = {
            str(item.get("url") or ""): item
            for item in result.get("results", [])
            if isinstance(item, dict) and str(item.get("url") or "")
        }
        by_observation[(source_request_id, platform)] = url_map

    report = dict(observations_report)
    observations = observations_report.get("observations", []) if isinstance(observations_report, dict) else []
    updated_observations: list[dict[str, Any]] = []
    if not isinstance(observations, list):
        report["observations"] = updated_observations
        return report
    relevance_applied = 0
    relevance_rejected = 0
    for observation in observations:
        if not isinstance(observation, dict):
            continue
        item = dict(observation)
        source_request_id = str(item.get("request_id") or "")
        platform = str(item.get("platform") or "")
        url_map = by_observation.get((source_request_id, platform), {})
        top_results = item.get("top_results", [])
        next_results: list[dict[str, Any]] = []
        if isinstance(top_results, list):
            for result in top_results:
                if not isinstance(result, dict):
                    continue
                next_result = dict(result)
                decision = url_map.get(str(next_result.get("url") or ""))
                if decision:
                    next_result["llm_relevance"] = decision
                    relevance_applied += 1
                    if decision.get("relevance") in REJECT_RELEVANCE:
                        relevance_rejected += 1
                next_results.append(next_result)
        item["top_results"] = next_results
        updated_observations.append(item)

    report["observations"] = updated_observations
    summary = dict(report.get("summary", {}) if isinstance(report.get("summary", {}), dict) else {})
    summary["llm_relevance_applied"] = relevance_applied
    summary["llm_relevance_rejected"] = relevance_rejected
    report["summary"] = summary
    return report


def result_is_llm_rejected(result: dict[str, Any]) -> bool:
    relevance = result.get("llm_relevance", {}) if isinstance(result, dict) else {}
    return isinstance(relevance, dict) and str(relevance.get("relevance") or "") in REJECT_RELEVANCE
