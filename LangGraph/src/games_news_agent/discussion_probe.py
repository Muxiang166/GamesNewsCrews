"""Low-frequency discussion probe helpers.

The v0 probe is intentionally conservative. It prepares auditable search
targets and mines already-fetched article/context text for discussion signals;
it does not scrape social platforms or convert discussion into confirmed fact.
"""

from __future__ import annotations

import re
from typing import Any

from .discussion_probe_provider import (
    build_provider_discussion_profile,
    observations_by_candidate,
)
from .regional_heat import build_regional_heat_targets
from .trend_signals import build_discussion_profile


DEFAULT_DISCUSSION_PLATFORMS: tuple[str, ...] | None = None
BOILERPLATE_PATTERNS = (
    r"stay ahead with pc gamer",
    r"become a member",
    r"newsletter",
    r"privacy policy",
    r"terms & conditions",
    r"latest hardware news",
    r"straight to your inbox",
    r"you are now subscribed",
)


def _candidate_url(candidate: dict[str, Any]) -> str:
    return str(candidate.get("url") or "").strip()


def _candidate_key(candidate: dict[str, Any]) -> str:
    return _candidate_url(candidate) or str(candidate.get("title") or "").strip()


def _clean_query(title: Any, *, max_chars: int = 96) -> str:
    text = re.sub(r"\s+", " ", str(title or "")).strip()
    text = re.sub(r"\s*[|_-]\s*(IGN|GameSpot|PC Gamer).*$", "", text, flags=re.IGNORECASE)
    return text[:max_chars].strip()


def build_discussion_probe_requests(
    candidates: list[dict[str, Any]],
    *,
    limit: int = 20,
    platforms: tuple[str, ...] | None = DEFAULT_DISCUSSION_PLATFORMS,
) -> list[dict[str, Any]]:
    """Build auditable low-frequency discussion probe requests."""

    requests: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        key = _candidate_key(candidate)
        if not key or key in seen:
            continue
        seen.add(key)
        query = _clean_query(candidate.get("title") or candidate.get("query") or key)
        if not query:
            continue
        heat_region, search_targets = build_regional_heat_targets(
            candidate,
            query,
            platforms=platforms,
        )
        requests.append(
            {
                "candidate_url": _candidate_url(candidate),
                "candidate_title": str(candidate.get("title") or ""),
                "source_id": str(candidate.get("source_id") or ""),
                "source_language": str(candidate.get("source_language") or candidate.get("language") or ""),
                "heat_region": heat_region,
                "theme_section": str(candidate.get("theme_section") or ""),
                "query": query,
                "usage_policy": "manual_or_low_frequency_probe_only",
                "search_targets": search_targets,
            }
        )
        if len(requests) >= max(limit, 0):
            break
    return requests


def _evidence_texts_by_url(context_packs: list[dict[str, Any]]) -> dict[str, list[str]]:
    by_url: dict[str, list[str]] = {}
    for pack in context_packs:
        if not isinstance(pack, dict):
            continue
        candidate = pack.get("candidate", {})
        if not isinstance(candidate, dict):
            continue
        url = _candidate_url(candidate)
        if not url:
            continue
        texts: list[str] = []
        for evidence in pack.get("evidence", []):
            if not isinstance(evidence, dict):
                continue
            quote = str(evidence.get("quote") or evidence.get("text") or "").strip()
            if quote and not _is_boilerplate_text(quote):
                texts.append(quote)
        by_url[url] = texts
    return by_url


def _is_boilerplate_text(text: str) -> bool:
    lowered = text.lower()
    return any(re.search(pattern, lowered) for pattern in BOILERPLATE_PATTERNS)


def _candidate_by_url(candidates: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_url: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        if isinstance(candidate, dict):
            url = _candidate_url(candidate)
            if url and url not in by_url:
                by_url[url] = candidate
    return by_url


def _probe_evidence(profile: dict[str, Any], evidence_texts: list[str]) -> list[dict[str, Any]]:
    if not evidence_texts and not profile.get("platforms") and not profile.get("reasons"):
        return []
    return [
        {
            "source": "document_or_candidate_text",
            "platforms": profile.get("platforms", []),
            "reasons": profile.get("reasons", []),
            "quotes": evidence_texts[:3],
        }
    ]


def _provider_evidence(
    provider_profile: dict[str, Any],
    observations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not observations:
        return []
    quotes: list[str] = []
    compact_observations: list[dict[str, Any]] = []
    for observation in observations:
        if not isinstance(observation, dict):
            continue
        for text in observation.get("evidence_texts", []):
            value = str(text).strip()
            if value and value not in quotes:
                quotes.append(value)
        compact_observations.append(
            {
                "platform": observation.get("platform", ""),
                "status": observation.get("status", ""),
                "result_count": observation.get("result_count", 0),
                "discussion_hint_count": observation.get("discussion_hint_count", 0),
                "has_result_signal": observation.get("has_result_signal", False),
            }
        )
    if not quotes and not compact_observations:
        return []
    return [
        {
            "source": "discussion_probe_provider",
            "platforms": provider_profile.get("platforms", []),
            "reasons": provider_profile.get("reasons", []),
            "quotes": quotes[:3],
            "observations": compact_observations,
        }
    ]


def _stronger_profile(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    return right if _score(right) > _score(left) else left


def build_discussion_probe_report(
    candidates: list[dict[str, Any]],
    *,
    context_packs: list[dict[str, Any]],
    probe_requests: list[dict[str, Any]],
    provider_observations: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build deterministic discussion evidence from probe requests and context text."""

    candidates_by_url = _candidate_by_url(candidates)
    evidence_by_url = _evidence_texts_by_url(context_packs)
    provider_by_url = observations_by_candidate(provider_observations or {})
    results: list[dict[str, Any]] = []
    for request in probe_requests:
        url = str(request.get("candidate_url") or "").strip()
        candidate = dict(candidates_by_url.get(url, {}))
        if not candidate:
            candidate = {
                "url": url,
                "title": request.get("candidate_title", ""),
                "source_id": request.get("source_id", ""),
                "theme_section": request.get("theme_section", ""),
            }
        evidence_texts = evidence_by_url.get(url, [])
        document_profile = build_discussion_profile(candidate, evidence_texts=evidence_texts)
        provider_items = provider_by_url.get(url, [])
        provider_profile = build_provider_discussion_profile(candidate, provider_items)
        profile = _stronger_profile(document_profile, provider_profile)
        evidence = [
            *_probe_evidence(document_profile, evidence_texts),
            *_provider_evidence(provider_profile, provider_items),
        ]
        results.append(
            {
                "candidate_url": url,
                "candidate_title": str(candidate.get("title") or request.get("candidate_title") or ""),
                "source_id": str(candidate.get("source_id") or request.get("source_id") or ""),
                "theme_section": str(candidate.get("theme_section") or request.get("theme_section") or ""),
                "query": request.get("query", ""),
                "discussion_profile": profile,
                "document_discussion_profile": document_profile,
                "provider_discussion_profile": provider_profile,
                "evidence": evidence,
                "provider_observations": provider_items,
                "search_targets": request.get("search_targets", []),
            }
        )

    with_discussion = sum(
        1
        for result in results
        if result.get("discussion_profile", {}).get("has_discussion_evidence")
    )
    return {
        "version": "0.1.0",
        "summary": {
            "probed_candidates": len(results),
            "with_discussion_evidence": with_discussion,
            "coverage": round(with_discussion / len(results), 4) if results else 0.0,
        },
        "results": results,
    }


def _score(profile: dict[str, Any]) -> float:
    value = profile.get("score", 0)
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def _has_promotable_discussion(profile: dict[str, Any]) -> bool:
    if profile.get("has_discussion_evidence"):
        return True
    level = str(profile.get("level", "none"))
    return level in {"discussed", "trending"} and _score(profile) >= 35.0


def _results_by_url(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    results = report.get("results", []) if isinstance(report, dict) else []
    by_url: dict[str, dict[str, Any]] = {}
    if isinstance(results, list):
        for result in results:
            if isinstance(result, dict):
                url = str(result.get("candidate_url") or "").strip()
                if url:
                    by_url[url] = result
    return by_url


def apply_discussion_probe_report(
    candidates: list[dict[str, Any]],
    report: dict[str, Any],
) -> list[dict[str, Any]]:
    """Merge probe results into candidates, only promoting stronger evidence."""

    by_url = _results_by_url(report)
    enriched: list[dict[str, Any]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        item = dict(candidate)
        result = by_url.get(_candidate_url(item))
        if not result:
            enriched.append(item)
            continue
        probe_profile = result.get("discussion_profile", {})
        if not isinstance(probe_profile, dict):
            probe_profile = {}
        existing_profile = item.get("discussion_profile", {})
        if not isinstance(existing_profile, dict):
            existing_profile = {}

        item["discussion_probe"] = {
            "query": result.get("query", ""),
            "evidence": result.get("evidence", []),
            "search_targets": result.get("search_targets", []),
            "provider_observations": result.get("provider_observations", []),
            "profile": probe_profile,
        }
        if _has_promotable_discussion(probe_profile) and _score(probe_profile) > _score(existing_profile):
            item["discussion_profile"] = probe_profile
            item["discussion_score"] = probe_profile.get("score", 0)
            item["discussion_level"] = probe_profile.get("level", "none")
            item["discussion_probe_status"] = "promoted"
        else:
            item["discussion_probe_status"] = "kept_existing"
        enriched.append(item)
    return enriched
