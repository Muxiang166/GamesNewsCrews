"""LLM-assisted source navigation request/response helpers.

The navigator never invents URLs. It only ranks URLs observed by deterministic
collectors so humans can decide whether a source needs better entry points.
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from .llm_provider import LlmConfig, load_llm_config, run_llm_json_requests


NAVIGATION_INSTRUCTIONS = """
You are a source navigation assistant for a games news collector.
Choose only from observed_urls. Do not invent URLs.
Recommend URLs that are likely to improve 48-hour games news collection for
Sony, Nintendo, Microsoft, PC, or supplemental meme/community material.
Return JSON only with recommended_entry_urls and skip_urls.
""".strip()


def _source_id(item: dict[str, Any]) -> str:
    return str(item.get("source_id") or item.get("id") or "")


def _diagnostics_by_source(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    sources = report.get("sources", []) if isinstance(report, dict) else []
    result: dict[str, dict[str, Any]] = {}
    if isinstance(sources, list):
        for item in sources:
            if isinstance(item, dict):
                result[_source_id(item)] = item
    return result


def _number(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return 0.0


def _reject_reason_count(diagnostics: dict[str, Any], reason: str) -> float:
    reject_reasons = diagnostics.get("reject_reasons", {})
    if not isinstance(reject_reasons, dict):
        return 0.0
    return _number(reject_reasons.get(reason, 0))


def _navigation_need_score(diagnostics: dict[str, Any]) -> float:
    candidate_count = _number(diagnostics.get("candidate_count", 0))
    score = 0.0

    if candidate_count == 0:
        score += 80.0
    elif candidate_count < 5:
        score += 30.0
    elif candidate_count < 10:
        score += 10.0

    score += _number(diagnostics.get("error_count", 0)) * 20.0
    score += _number(diagnostics.get("parse_warning_count", 0)) * 8.0
    score += _number(diagnostics.get("missing_time_count", 0)) * 4.0
    score += _number(diagnostics.get("rejected_missing_time_count", 0)) * 4.0
    score += _number(diagnostics.get("duplicate_url_count", 0)) * 1.0
    score += _reject_reason_count(diagnostics, "missing_time") * 3.0
    score += _reject_reason_count(diagnostics, "irrelevant_topic") * 5.0
    score += _reject_reason_count(diagnostics, "outside_time_window") * 0.5
    return round(score, 2)


def _append_observed_url(
    observed: list[dict[str, Any]],
    seen: set[str],
    *,
    url: Any,
    kind: str,
    title: Any = "",
    theme_section: Any = "",
    reason: Any = "",
) -> None:
    value = str(url or "").strip()
    if not value or value in seen:
        return
    seen.add(value)
    observed.append(
        {
            "url": value,
            "kind": kind,
            "title": str(title or ""),
            "theme_section": str(theme_section or ""),
            "reason": str(reason or ""),
        }
    )


def build_source_navigation_requests(
    *,
    sources: list[dict[str, Any]],
    collector_diagnostics: dict[str, Any],
    candidates: list[dict[str, Any]],
    raw_sources: list[dict[str, Any]],
    rejected_candidates: list[dict[str, Any]],
    max_urls_per_source: int = 25,
) -> list[dict[str, Any]]:
    diagnostics = _diagnostics_by_source(collector_diagnostics)
    raw_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    candidates_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    rejected_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for item in raw_sources:
        if isinstance(item, dict):
            raw_by_source[_source_id(item)].append(item)
    for item in candidates:
        if isinstance(item, dict):
            candidates_by_source[_source_id(item)].append(item)
    for item in rejected_candidates:
        if isinstance(item, dict):
            rejected_by_source[_source_id(item)].append(item)

    requests_with_order: list[tuple[float, int, dict[str, Any]]] = []
    for index, source in enumerate(sources):
        source_id = str(source.get("id", "")).strip()
        observed: list[dict[str, Any]] = []
        seen: set[str] = set()
        for raw in raw_by_source[source_id]:
            _append_observed_url(observed, seen, url=raw.get("url"), kind="source_entry")
        for candidate in candidates_by_source[source_id]:
            _append_observed_url(
                observed,
                seen,
                url=candidate.get("url"),
                kind="candidate",
                title=candidate.get("title"),
                theme_section=candidate.get("theme_section"),
            )
        for rejected in rejected_by_source[source_id]:
            _append_observed_url(
                observed,
                seen,
                url=rejected.get("url"),
                kind="rejected_candidate",
                title=rejected.get("title"),
                reason=rejected.get("reject_reason"),
            )
        if not observed:
            continue
        diagnostic = diagnostics.get(source_id, {})
        navigation_need_score = _navigation_need_score(diagnostic)
        request = (
            {
                "request_id": f"source_navigation:{source_id}",
                "schema_version": "source_navigation_request_v0",
                "instructions": NAVIGATION_INSTRUCTIONS,
                "source": {
                    "id": source_id,
                    "name": source.get("name", source_id),
                    "collector": source.get("collector", ""),
                    "kind": source.get("kind", ""),
                    "tags": source.get("tags", []),
                },
                "diagnostics": diagnostic,
                "navigation_need_score": navigation_need_score,
                "observed_urls": observed[: max(max_urls_per_source, 0)],
                "json_schema": {
                    "type": "object",
                    "properties": {
                        "recommended_entry_urls": {"type": "array"},
                        "skip_urls": {"type": "array"},
                    },
                    "required": ["recommended_entry_urls", "skip_urls"],
                },
            }
        )
        requests_with_order.append((navigation_need_score, index, request))
    return [
        request
        for _score, _index, request in sorted(
            requests_with_order,
            key=lambda item: (-item[0], item[1]),
        )
    ]


def _bounded_confidence(value: Any) -> float:
    if isinstance(value, (int, float)):
        return max(0.0, min(1.0, float(value)))
    return 0.0


def parse_source_navigation_response(
    request_id: str,
    content: str,
    *,
    observed_urls: set[str],
) -> dict[str, Any]:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        return {
            "request_id": request_id,
            "parse_status": "invalid_json",
            "error": str(exc),
            "recommended_entry_urls": [],
            "skip_urls": [],
            "dropped_unobserved_urls": [],
        }
    if not isinstance(payload, dict):
        return {
            "request_id": request_id,
            "parse_status": "invalid_json_shape",
            "recommended_entry_urls": [],
            "skip_urls": [],
            "dropped_unobserved_urls": [],
        }

    recommended: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    dropped: list[str] = []
    for item in payload.get("recommended_entry_urls", []):
        if not isinstance(item, dict):
            continue
        url = str(item.get("url", "")).strip()
        if url not in observed_urls:
            if url:
                dropped.append(url)
            continue
        recommended.append(
            {
                "url": url,
                "reason": str(item.get("reason", "")),
                "expected_theme": str(item.get("expected_theme", "")),
                "confidence": _bounded_confidence(item.get("confidence")),
                "crawl_budget": max(int(item.get("crawl_budget", 0) or 0), 0),
            }
        )
    for item in payload.get("skip_urls", []):
        if not isinstance(item, dict):
            continue
        url = str(item.get("url", "")).strip()
        if url in observed_urls:
            skipped.append({"url": url, "reason": str(item.get("reason", ""))})

    return {
        "request_id": request_id,
        "parse_status": "ok",
        "recommended_entry_urls": recommended,
        "skip_urls": skipped,
        "dropped_unobserved_urls": dropped,
    }


def run_source_navigation_requests(
    requests: list[dict[str, Any]],
    *,
    config: LlmConfig | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    raw_results = run_llm_json_requests(
        requests,
        config=config or load_llm_config(),
        limit=limit,
    )
    parsed: list[dict[str, Any]] = []
    by_request_id = {str(request.get("request_id", "")): request for request in requests}
    for result in raw_results:
        request_id = str(result.get("request_id", ""))
        request = by_request_id.get(request_id, {})
        observed_urls = {str(item.get("url", "")) for item in request.get("observed_urls", []) if isinstance(item, dict)}
        if result.get("parse_status") != "ok":
            parsed.append(
                {
                    "request_id": request_id,
                    "parse_status": result.get("parse_status", "provider_error"),
                    "error": result.get("error") or result.get("content", ""),
                    "recommended_entry_urls": [],
                    "skip_urls": [],
                    "dropped_unobserved_urls": [],
                    "usage": result.get("usage", {}),
                }
            )
            continue
        navigation = parse_source_navigation_response(
            request_id,
            str(result.get("content", "")),
            observed_urls=observed_urls,
        )
        navigation["usage"] = result.get("usage", {})
        navigation["model"] = result.get("model", "")
        parsed.append(navigation)
    return parsed
