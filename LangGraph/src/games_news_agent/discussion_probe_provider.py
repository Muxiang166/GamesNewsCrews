"""Low-frequency discussion search observation provider.

The provider records lightweight search-page observations. It does not treat
search results as facts and it intentionally avoids login-only or app-only
targets.
"""

from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import urljoin


DISCUSSION_HINT_PATTERNS = (
    r"\bcomments?\b",
    r"\breplies?\b",
    r"\breposts?\b",
    r"\bshares?\b",
    r"\bviews?\b",
    r"\bupvotes?\b",
    r"\btrending\b",
    r"\bviral\b",
    r"\bdiscuss(?:ed|ing|ion)?\b",
    r"\bdebate[ds]?\b",
    r"\u8bc4\u8bba",
    r"\u8f6c\u53d1",
    r"\u5f39\u5e55",
    r"\u5e16\u5b50",
    r"\u6d4f\u89c8",
    r"\u64ad\u653e",
    r"\u70ed\u8bae",
    r"\u8ba8\u8bba",
    r"\u4e89\u8bae",
)

ENGLISH_STOPWORDS = {
    "about",
    "after",
    "announced",
    "announcement",
    "available",
    "before",
    "date",
    "details",
    "from",
    "game",
    "games",
    "into",
    "look",
    "more",
    "news",
    "new",
    "old",
    "release",
    "revealed",
    "says",
    "the",
    "this",
    "with",
}

SKIP_TEXT_PATTERNS = (
    r"javascript:",
    r"privacy policy",
    r"terms of service",
    r"cookie",
    r"sign in",
    r"log in",
)


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _strip_tags(text: str) -> str:
    text = re.sub(r"<script\b.*?</script>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style\b.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    return _normalize_text(text)


def _query_terms(query: str) -> list[str]:
    terms: list[str] = []
    lowered = query.lower()
    for term in re.findall(r"[a-z][a-z0-9]{2,}", lowered):
        if term in ENGLISH_STOPWORDS:
            continue
        if term not in terms:
            terms.append(term)
    for cjk_text in re.findall(r"[\u4e00-\u9fff]{2,}", query):
        if len(cjk_text) <= 4:
            if cjk_text not in terms:
                terms.append(cjk_text)
            continue
        for size in (4, 3, 2):
            for index in range(0, max(len(cjk_text) - size + 1, 0)):
                term = cjk_text[index : index + size]
                if term not in terms:
                    terms.append(term)
                if len(terms) >= 16:
                    return terms
    for term in re.findall(r"[0-9a-z\u4e00-\u9fff]{2,}", lowered):
        if term in ENGLISH_STOPWORDS or term in terms:
            continue
        terms.append(term)
        if len(terms) >= 16:
            break
    return terms[:8]


def _keyword_hit_count(text: str, terms: list[str]) -> int:
    lowered = text.lower()
    return sum(1 for term in terms if term and term in lowered)


def _discussion_hint_count(text: str) -> int:
    return sum(1 for pattern in DISCUSSION_HINT_PATTERNS if re.search(pattern, text, flags=re.IGNORECASE))


def _is_skip_text(text: str) -> bool:
    lowered = text.lower()
    return any(re.search(pattern, lowered) for pattern in SKIP_TEXT_PATTERNS)


def _top_results_from_html(text: str, *, base_url: str, limit: int = 5) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    seen_titles: set[str] = set()
    pattern = r"<a\b[^>]*\bhref=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>"
    for href, raw_title in re.findall(pattern, text, flags=re.IGNORECASE | re.DOTALL):
        title = _strip_tags(raw_title)
        if not title or len(title) < 4 or _is_skip_text(title) or _is_skip_text(href):
            continue
        if "space.bilibili.com" in href or re.fullmatch(r"[\d\s\.:,\+\-\u4e07\u4ebfkmKM]+", title):
            continue
        if re.fullmatch(r"[\d\.]+\s*[\u4e07\u4ebfkmKM]?\s+\d+\s+\d{1,2}:\d{2}", title):
            continue
        normalized_title = title.lower()
        if normalized_title in seen_titles:
            continue
        seen_titles.add(normalized_title)
        results.append(
            {
                "title": title[:180],
                "url": urljoin(base_url, html.unescape(href)),
                "snippet": "",
            }
        )
        if len(results) >= limit:
            break
    return results


def _page_title(text: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", text, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return _strip_tags(match.group(1))[:180]


def _empty_report() -> dict[str, Any]:
    return {
        "version": "1.0.0",
        "summary": {
            "probe_requests": 0,
            "targets": 0,
            "fetched": 0,
            "ok": 0,
            "blocked": 0,
            "errors": 0,
            "skipped": 0,
            "with_result_signal": 0,
            "platform_counts": {},
        },
        "observations": [],
    }


def empty_discussion_probe_provider_report() -> dict[str, Any]:
    """Return an empty provider report with the v1 artifact shape."""

    return _empty_report()


def _platform_counts(observations: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {}
    for observation in observations:
        platform = str(observation.get("platform") or "unknown")
        status = str(observation.get("status") or "unknown")
        item = counts.setdefault(platform, {})
        item[status] = item.get(status, 0) + 1
    return counts


def _summarize(probe_request_count: int, observations: list[dict[str, Any]]) -> dict[str, Any]:
    fetched_statuses = {"ok", "blocked", "error"}
    summary = {
        "probe_requests": probe_request_count,
        "targets": len(observations),
        "fetched": sum(1 for item in observations if item.get("status") in fetched_statuses),
        "ok": sum(1 for item in observations if item.get("status") == "ok"),
        "blocked": sum(1 for item in observations if item.get("status") == "blocked"),
        "errors": sum(1 for item in observations if item.get("status") == "error"),
        "skipped": sum(
            1
            for item in observations
            if item.get("status") in {"skipped_manual", "missing_url", "skipped_limit"}
        ),
        "with_result_signal": sum(1 for item in observations if item.get("has_result_signal")),
        "platform_counts": _platform_counts(observations),
    }
    return summary


def _manual_observation(request: dict[str, Any], target: dict[str, Any], *, status: str) -> dict[str, Any]:
    return {
        "candidate_url": str(request.get("candidate_url") or ""),
        "candidate_title": str(request.get("candidate_title") or ""),
        "platform": str(target.get("platform") or ""),
        "query": str(target.get("query") or request.get("query") or ""),
        "url": str(target.get("url") or ""),
        "access": str(target.get("access") or ""),
        "status": status,
        "status_code": None,
        "content_type": "",
        "content_length": 0,
        "page_title": "",
        "result_count": 0,
        "keyword_hit_count": 0,
        "discussion_hint_count": 0,
        "has_result_signal": False,
        "top_results": [],
        "evidence_texts": [],
        "error": "",
    }


def _observe_target(
    request: dict[str, Any],
    target: dict[str, Any],
    *,
    fetcher: Any,
    timeout: float,
) -> dict[str, Any]:
    url = str(target.get("url") or "").strip()
    access = str(target.get("access") or "")
    if not url:
        status = "skipped_manual" if "manual" in access else "missing_url"
        return _manual_observation(request, target, status=status)

    result = fetcher.fetch_text(url, timeout=timeout)
    if not result.ok:
        status = "blocked" if result.status_code in {401, 403, 429} else "error"
        observation = _manual_observation(request, target, status=status)
        observation.update(
            {
                "status_code": result.status_code,
                "content_type": result.content_type,
                "content_length": len(result.text or ""),
                "error": result.error,
            }
        )
        return observation

    page_text = result.text or ""
    top_results = _top_results_from_html(page_text, base_url=url)
    visible_text = _strip_tags(page_text)
    title = _page_title(page_text)
    evidence_parts = [title, *[item["title"] for item in top_results], visible_text[:500]]
    evidence_text = _normalize_text(" ".join(part for part in evidence_parts if part))
    result_text = _normalize_text(" ".join(item["title"] for item in top_results))
    terms = _query_terms(str(target.get("query") or request.get("query") or ""))
    keyword_hits = _keyword_hit_count(result_text, terms)
    hint_count = _discussion_hint_count(result_text)
    result_count = len(top_results)
    required_hits = min(2, len(terms)) if terms else 1
    has_result_signal = result_count > 0 and keyword_hits >= required_hits

    return {
        "candidate_url": str(request.get("candidate_url") or ""),
        "candidate_title": str(request.get("candidate_title") or ""),
        "platform": str(target.get("platform") or ""),
        "query": str(target.get("query") or request.get("query") or ""),
        "url": url,
        "access": access,
        "status": "ok",
        "status_code": result.status_code,
        "content_type": result.content_type,
        "content_length": len(page_text),
        "page_title": title,
        "result_count": result_count,
        "keyword_hit_count": keyword_hits,
        "discussion_hint_count": hint_count,
        "has_result_signal": has_result_signal,
        "top_results": top_results,
        "evidence_texts": [evidence_text[:700]] if evidence_text else [],
        "error": "",
    }


def run_discussion_probe_provider(
    probe_requests: list[dict[str, Any]],
    *,
    fetcher: Any,
    candidate_limit: int = 20,
    platform_limit: int = 2,
    timeout: float = 8.0,
) -> dict[str, Any]:
    """Fetch low-frequency public search targets and record observations."""

    if candidate_limit <= 0 or platform_limit <= 0:
        return _empty_report()

    observations: list[dict[str, Any]] = []
    limited_requests = [request for request in probe_requests if isinstance(request, dict)][:candidate_limit]
    for request in limited_requests:
        targets = request.get("search_targets", [])
        if not isinstance(targets, list):
            continue
        for target in [item for item in targets if isinstance(item, dict)][:platform_limit]:
            observations.append(
                _observe_target(
                    request,
                    target,
                    fetcher=fetcher,
                    timeout=timeout,
                )
            )

    return {
        "version": "1.0.0",
        "summary": _summarize(len(limited_requests), observations),
        "observations": observations,
    }


def observations_by_candidate(provider_report: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    observations = provider_report.get("observations", []) if isinstance(provider_report, dict) else []
    by_url: dict[str, list[dict[str, Any]]] = {}
    if not isinstance(observations, list):
        return by_url
    for observation in observations:
        if not isinstance(observation, dict):
            continue
        url = str(observation.get("candidate_url") or "").strip()
        if url:
            by_url.setdefault(url, []).append(observation)
    return by_url


def build_provider_discussion_profile(
    candidate: dict[str, Any],
    observations: list[dict[str, Any]],
) -> dict[str, Any]:
    """Convert search observations into a conservative discussion profile."""

    result_observations = [
        item
        for item in observations
        if item.get("status") == "ok" and item.get("has_result_signal")
    ]
    if not result_observations:
        return {
            "score": 0.0,
            "level": "none",
            "platforms": [],
            "reasons": [],
            "engagement_score": 0.0,
            "discussion_language_score": 0.0,
            "platform_diversity_score": 0.0,
            "has_direct_engagement": False,
            "has_multi_platform_discussion": False,
            "has_discussion_evidence": False,
        }

    platforms: list[str] = []
    for observation in result_observations:
        platform = str(observation.get("platform") or "")
        if platform and platform not in platforms:
            platforms.append(platform)

    total_hints = sum(
        int(item.get("discussion_hint_count", 0))
        for item in result_observations
        if isinstance(item.get("discussion_hint_count", 0), int)
    )
    total_results = sum(
        int(item.get("result_count", 0))
        for item in result_observations
        if isinstance(item.get("result_count", 0), int)
    )
    reasons: list[str] = []
    score = 12.0
    if len(platforms) >= 2:
        score += 22.0
        reasons.append("provider_multi_platform_results")
    else:
        reasons.append("provider_single_platform_result")
    if total_hints > 0:
        score += min(18.0, total_hints * 4.0)
        reasons.append("provider_discussion_hints")
    if total_results >= 4:
        score += 4.0
        reasons.append("provider_multiple_results")

    score = min(100.0, score)
    level = "trending" if score >= 70 else "discussed" if score >= 35 else "weak" if score >= 10 else "none"
    has_multi_platform = len(platforms) >= 2
    has_direct_engagement = total_hints >= 2
    has_evidence = level in {"discussed", "trending"} and (has_multi_platform or has_direct_engagement)
    return {
        "score": round(score, 2),
        "level": level,
        "platforms": platforms,
        "reasons": reasons,
        "engagement_score": round(min(45.0, total_hints * 4.0), 2),
        "discussion_language_score": 0.0,
        "platform_diversity_score": 30.0 if has_multi_platform else 0.0,
        "has_direct_engagement": has_direct_engagement,
        "has_multi_platform_discussion": has_multi_platform,
        "has_discussion_evidence": has_evidence,
    }
