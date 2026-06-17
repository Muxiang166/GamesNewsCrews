"""Diagnostics for collection quality and source entry behavior."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any


def _source_id(item: dict[str, Any]) -> str:
    return str(item.get("source_id") or item.get("id") or "")


def _has_time(candidate: dict[str, Any]) -> bool:
    return bool(candidate.get("published_at") or candidate.get("observed_at"))


def _sum_entry_metric(entries: list[dict[str, Any]], key: str) -> int:
    total = 0
    for entry in entries:
        value = entry.get(key, 0)
        if isinstance(value, int):
            total += value
    return total


def build_collector_diagnostics_report(
    *,
    sources: list[dict[str, Any]],
    raw_sources: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    rejected: list[dict[str, Any]],
    errors: list[dict[str, Any]],
    entry_diagnostics: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Roll up observable collection signals by source."""

    raw_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    candidates_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    rejected_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    errors_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    entries_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for item in raw_sources:
        raw_by_source[_source_id(item)].append(item)
    for item in candidates:
        candidates_by_source[_source_id(item)].append(item)
    for item in rejected:
        rejected_by_source[_source_id(item)].append(item)
    for item in errors:
        errors_by_source[_source_id(item)].append(item)
    for item in entry_diagnostics or []:
        entries_by_source[_source_id(item)].append(item)

    source_reports: list[dict[str, Any]] = []
    for source in sources:
        source_id = str(source.get("id", ""))
        source_candidates = candidates_by_source[source_id]
        source_rejected = rejected_by_source[source_id]
        source_entries = entries_by_source[source_id]
        reject_reasons = Counter(str(item.get("reject_reason", "unknown")) for item in source_rejected)
        candidate_missing_time = sum(1 for item in source_candidates if not _has_time(item))
        rejected_missing_time = reject_reasons.get("missing_time", 0)
        source_reports.append(
            {
                "source_id": source_id,
                "name": source.get("name", source_id),
                "collector": source.get("collector", ""),
                "raw_fetch_count": len(raw_by_source[source_id]),
                "entry_count": len(source_entries),
                "link_count": _sum_entry_metric(source_entries, "link_count"),
                "candidate_count": len(source_candidates),
                "missing_time_count": candidate_missing_time + rejected_missing_time,
                "candidate_missing_time_count": candidate_missing_time,
                "rejected_missing_time_count": rejected_missing_time,
                "duplicate_url_count": _sum_entry_metric(source_entries, "duplicate_url_count"),
                "detail_time_backfill_count": _sum_entry_metric(source_entries, "detail_time_backfill_count"),
                "parse_warning_count": _sum_entry_metric(source_entries, "parse_warning_count"),
                "error_count": len(errors_by_source[source_id]),
                "reject_reasons": dict(reject_reasons),
                "entries": source_entries,
            }
        )

    totals = {
        "sources": len(source_reports),
        "raw_fetch_count": sum(item["raw_fetch_count"] for item in source_reports),
        "link_count": sum(item["link_count"] for item in source_reports),
        "candidate_count": sum(item["candidate_count"] for item in source_reports),
        "missing_time_count": sum(item["missing_time_count"] for item in source_reports),
        "duplicate_url_count": sum(item["duplicate_url_count"] for item in source_reports),
        "detail_time_backfill_count": sum(item["detail_time_backfill_count"] for item in source_reports),
        "parse_warning_count": sum(item["parse_warning_count"] for item in source_reports),
        "error_count": sum(item["error_count"] for item in source_reports),
    }
    return {
        "version": "0.1.0",
        "summary": totals,
        "sources": source_reports,
    }
