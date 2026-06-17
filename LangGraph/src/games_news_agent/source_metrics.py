"""Source-level candidate and theme coverage metrics."""

from __future__ import annotations

from typing import Any

from .story_sections import THEME_SECTIONS, classify_candidate_section


SECTION_IDS = [section["id"] for section in THEME_SECTIONS]


def _source_id(item: dict[str, Any]) -> str:
    return str(item.get("source_id", "")).strip() or "unknown"


def _empty_theme_counts() -> dict[str, int]:
    return {section_id: 0 for section_id in SECTION_IDS}


def _empty_lane_counts() -> dict[str, dict[str, int]]:
    return {
        "main": _empty_theme_counts(),
        "supplemental": _empty_theme_counts(),
    }


def _source_names(sources: list[dict[str, Any]]) -> dict[str, str]:
    names: dict[str, str] = {}
    for source in sources:
        if not isinstance(source, dict):
            continue
        source_id = str(source.get("id", "")).strip()
        if source_id:
            names[source_id] = str(source.get("name") or source_id)
    return names


def _ensure_source(
    records: dict[str, dict[str, Any]],
    source_id: str,
    names: dict[str, str],
) -> dict[str, Any]:
    if source_id not in records:
        records[source_id] = {
            "source_id": source_id,
            "name": names.get(source_id, source_id),
            "raw_fetch_count": 0,
            "raw_candidate_count": 0,
            "main_count": 0,
            "supplemental_count": 0,
            "accepted_count": 0,
            "rejected_count": 0,
            "theme_counts": _empty_theme_counts(),
            "lane_theme_counts": _empty_lane_counts(),
            "reject_reasons": {},
        }
    return records[source_id]


def _count_candidate(
    records: dict[str, dict[str, Any]],
    candidate: dict[str, Any],
    *,
    lane: str,
    names: dict[str, str],
) -> None:
    source_id = _source_id(candidate)
    record = _ensure_source(records, source_id, names)
    section_id = classify_candidate_section(candidate)
    if section_id not in SECTION_IDS:
        section_id = "supplemental"

    record[f"{lane}_count"] += 1
    record["accepted_count"] += 1
    record["theme_counts"][section_id] += 1
    record["lane_theme_counts"][lane][section_id] += 1


def build_source_theme_counts(
    *,
    candidates: list[dict[str, Any]],
    supplemental_candidates: list[dict[str, Any]] | None = None,
    rejected_candidates: list[dict[str, Any]] | None = None,
    raw_candidates: list[dict[str, Any]] | None = None,
    raw_sources: list[dict[str, Any]] | None = None,
    sources: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Summarize source output by candidate lane and editorial theme."""

    names = _source_names(sources or [])
    records: dict[str, dict[str, Any]] = {}

    for raw_source in raw_sources or []:
        if not isinstance(raw_source, dict):
            continue
        _ensure_source(records, _source_id(raw_source), names)["raw_fetch_count"] += 1

    for raw_candidate in raw_candidates or []:
        if not isinstance(raw_candidate, dict):
            continue
        _ensure_source(records, _source_id(raw_candidate), names)["raw_candidate_count"] += 1

    for candidate in candidates:
        if isinstance(candidate, dict):
            _count_candidate(records, candidate, lane="main", names=names)

    for candidate in supplemental_candidates or []:
        if isinstance(candidate, dict):
            _count_candidate(records, candidate, lane="supplemental", names=names)

    for rejected in rejected_candidates or []:
        if not isinstance(rejected, dict):
            continue
        record = _ensure_source(records, _source_id(rejected), names)
        record["rejected_count"] += 1
        reason = str(rejected.get("reject_reason") or "unknown")
        record["reject_reasons"][reason] = record["reject_reasons"].get(reason, 0) + 1

    source_records = sorted(
        records.values(),
        key=lambda item: (item["accepted_count"], item["raw_candidate_count"], item["source_id"]),
        reverse=True,
    )
    accepted = sum(item["accepted_count"] for item in source_records)
    return {
        "version": "0.1.0",
        "sections": THEME_SECTIONS,
        "summary": {
            "sources": len(source_records),
            "raw_candidates": sum(item["raw_candidate_count"] for item in source_records),
            "accepted_candidates": accepted,
            "main_candidates": sum(item["main_count"] for item in source_records),
            "supplemental_candidates": sum(item["supplemental_count"] for item in source_records),
            "rejected_candidates": sum(item["rejected_count"] for item in source_records),
        },
        "sources": source_records,
    }
