"""Source health summaries for live collection runs."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any


BLOCKED_ERROR_HINTS = (
    "winerror 10013",
    "permission denied",
    "forbidden",
    "access denied",
    "timed out",
    "timeout",
    "connection refused",
)


def _source_id(item: dict[str, Any]) -> str:
    return str(item.get("source_id") or item.get("id") or "")


def _is_blocked(raw_records: list[dict[str, Any]], errors: list[dict[str, Any]]) -> bool:
    status_codes = {
        record.get("status_code")
        for record in raw_records
        if isinstance(record.get("status_code"), int)
    }
    if status_codes & {401, 403, 407, 408, 429}:
        return True

    joined_errors = " ".join(
        str(item.get("error", "")).lower()
        for item in [*raw_records, *errors]
    )
    return any(hint in joined_errors for hint in BLOCKED_ERROR_HINTS)


def _dominant_reject_reason(rejected: list[dict[str, Any]]) -> str:
    reasons = Counter(str(item.get("reject_reason", "unknown")) for item in rejected)
    if not reasons:
        return ""
    return reasons.most_common(1)[0][0]


def _status_for_source(
    *,
    raw_records: list[dict[str, Any]],
    accepted_count: int,
    rejected: list[dict[str, Any]],
    errors: list[dict[str, Any]],
    min_candidates_per_source: int,
) -> tuple[str, str, list[str]]:
    if accepted_count >= min_candidates_per_source:
        if errors:
            return (
                "healthy",
                f"enough 48h candidates with {len(errors)} non-blocking collector warning(s)",
                ["inspect_non_blocking_collector_warnings"],
            )
        return ("healthy", "enough 48h candidates", [])

    if _is_blocked(raw_records, errors):
        return (
            "source_blocked",
            "fetch was blocked by local network, permissions, rate limits, or access rules",
            ["run_from_ide_or_allow_network", "check_proxy_or_firewall"],
        )

    if errors or not raw_records:
        return (
            "source_broken",
            "collector did not produce a usable fetch result",
            ["verify_url", "inspect_collector_parser"],
        )

    if accepted_count > 0 or rejected:
        reason = _dominant_reject_reason(rejected)
        explanation = "reachable but below the target candidate count"
        if reason:
            explanation = f"{explanation}; dominant reject reason: {reason}"
        return (
            "needs_fill",
            explanation,
            ["on_this_day", "historical_record", "achievement_context"],
        )

    return (
        "source_broken",
        "source fetched but yielded no parseable candidates",
        ["inspect_collector_parser", "save_fixture_from_real_html"],
    )


def build_source_health_report(
    *,
    sources: list[dict[str, Any]],
    raw_sources: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    rejected: list[dict[str, Any]],
    errors: list[dict[str, Any]],
    min_candidates_per_source: int = 3,
) -> dict[str, Any]:
    raw_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    accepted_by_source: Counter[str] = Counter()
    rejected_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    errors_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for item in raw_sources:
        raw_by_source[_source_id(item)].append(item)
    for item in candidates:
        accepted_by_source[_source_id(item)] += 1
    for item in rejected:
        rejected_by_source[_source_id(item)].append(item)
    for item in errors:
        errors_by_source[_source_id(item)].append(item)

    source_reports: list[dict[str, Any]] = []
    for source in sources:
        source_id = str(source.get("id", ""))
        source_raw = raw_by_source.get(source_id, [])
        source_rejected = rejected_by_source.get(source_id, [])
        source_errors = errors_by_source.get(source_id, [])
        status, explanation, suggestions = _status_for_source(
            raw_records=source_raw,
            accepted_count=accepted_by_source[source_id],
            rejected=source_rejected,
            errors=source_errors,
            min_candidates_per_source=min_candidates_per_source,
        )
        source_reports.append(
            {
                "source_id": source_id,
                "name": source.get("name", source_id),
                "collector": source.get("collector", ""),
                "status": status,
                "accepted_count": accepted_by_source[source_id],
                "rejected_count": len(source_rejected),
                "raw_fetch_count": len(source_raw),
                "error_count": len(source_errors),
                "explanation": explanation,
                "fallback_suggestions": suggestions,
            }
        )

    summary = Counter(item["status"] for item in source_reports)
    return {
        "summary": {
            "healthy": summary.get("healthy", 0),
            "needs_fill": summary.get("needs_fill", 0),
            "source_blocked": summary.get("source_blocked", 0),
            "source_broken": summary.get("source_broken", 0),
        },
        "sources": source_reports,
    }
