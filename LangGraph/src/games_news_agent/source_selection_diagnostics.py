"""Diagnostics for source/language flow through selection stages."""

from __future__ import annotations

from collections import Counter
from typing import Any


def _source_id(item: dict[str, Any]) -> str:
    return str(item.get("source_id") or item.get("id") or "").strip() or "unknown"


def _story_source_ids(story: dict[str, Any]) -> list[str]:
    source_ids: list[str] = []
    for claim in story.get("claims", []):
        if not isinstance(claim, dict):
            continue
        metadata = claim.get("metadata", {})
        if isinstance(metadata, dict):
            source_id = str(metadata.get("source_id") or "").strip()
            if source_id and source_id not in source_ids:
                source_ids.append(source_id)
        for evidence in claim.get("evidence", []):
            if not isinstance(evidence, dict):
                continue
            source_id = str(evidence.get("source_id") or "").strip()
            if source_id and source_id not in source_ids:
                source_ids.append(source_id)
    if not source_ids:
        for url in story.get("source_urls", []):
            value = str(url).lower()
            if "ign.com" in value and "ign" not in source_ids:
                source_ids.append("ign")
            elif "gamersky.com" in value and "gamergen" not in source_ids:
                source_ids.append("gamergen")
    return source_ids or ["unknown"]


def _story_language(story: dict[str, Any]) -> str:
    return str(story.get("source_language") or "unknown").strip() or "unknown"


def _counter_dict(counter: Counter[str]) -> dict[str, int]:
    return {key: counter[key] for key in sorted(counter)}


def _source_theme_records(source_theme_counts: dict[str, Any]) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for item in source_theme_counts.get("sources", []) if isinstance(source_theme_counts, dict) else []:
        if isinstance(item, dict):
            records[_source_id(item)] = item
    return records


def _pool_counts(theme_candidate_pool: dict[str, Any] | None) -> tuple[Counter[str], Counter[str]]:
    selected_counter: Counter[str] = Counter()
    fetch_counter: Counter[str] = Counter()
    selected = []
    if isinstance(theme_candidate_pool, dict):
        raw_selected = theme_candidate_pool.get("selected_candidates", [])
        if isinstance(raw_selected, list):
            selected = [item for item in raw_selected if isinstance(item, dict)]
    for candidate in selected:
        source_id = _source_id(candidate)
        selected_counter[source_id] += 1
        if candidate.get("document_fetch_selected"):
            fetch_counter[source_id] += 1
    return selected_counter, fetch_counter


def _story_counts(stories: list[dict[str, Any]]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for story in stories:
        if not isinstance(story, dict):
            continue
        for source_id in _story_source_ids(story):
            counter[source_id] += 1
    return counter


def _language_counts(stories: list[dict[str, Any]]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for story in stories:
        if isinstance(story, dict):
            counter[_story_language(story)] += 1
    return _counter_dict(counter)


def _context_source_id(pack: dict[str, Any]) -> str:
    candidate = pack.get("candidate", {})
    if isinstance(candidate, dict):
        return _source_id(candidate)
    return "unknown"


def _context_scope_counts(context_packs: list[dict[str, Any]]) -> tuple[dict[str, Counter[str]], Counter[str], dict[str, Counter[str]]]:
    by_source: dict[str, Counter[str]] = {}
    total: Counter[str] = Counter()
    missing_by_source: dict[str, Counter[str]] = {}
    for pack in context_packs:
        if not isinstance(pack, dict):
            continue
        source_id = _context_source_id(pack)
        scope = str(pack.get("evidence_scope") or "unknown")
        by_source.setdefault(source_id, Counter())[scope] += 1
        total[scope] += 1
        for field in pack.get("missing_fields", []):
            value = str(field)
            if value:
                missing_by_source.setdefault(source_id, Counter())[value] += 1
    return by_source, total, missing_by_source


def _document_error_counts(document_errors: list[dict[str, Any]]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for error in document_errors:
        if isinstance(error, dict):
            counter[_source_id(error)] += 1
    return counter


def _diagnostic_reasons(
    *,
    accepted: int,
    theme_pool_selected: int,
    document_fetch_selected: int,
    story_candidates: int,
    final_stories: int,
) -> list[str]:
    reasons: list[str] = []
    if accepted and theme_pool_selected < accepted:
        reasons.append("theme_pool_competition")
    if theme_pool_selected and document_fetch_selected < theme_pool_selected:
        reasons.append("document_fetch_budget_competition")
    if document_fetch_selected and story_candidates < document_fetch_selected:
        reasons.append("claim_or_evidence_gate")
    if story_candidates and final_stories < story_candidates:
        reasons.append("story_score_competition")
    if accepted == 0:
        reasons.append("no_accepted_candidates")
    return reasons


def build_source_selection_diagnostics(
    *,
    source_theme_counts: dict[str, Any],
    theme_candidate_pool: dict[str, Any] | None = None,
    story_candidates: list[dict[str, Any]] | None = None,
    final_stories: list[dict[str, Any]] | None = None,
    context_packs: list[dict[str, Any]] | None = None,
    document_errors: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Summarize where each source/language drops out of the pipeline."""

    source_records = _source_theme_records(source_theme_counts)
    pool_counter, fetch_counter = _pool_counts(theme_candidate_pool)
    story_counter = _story_counts(story_candidates or [])
    final_counter = _story_counts(final_stories or [])
    context_by_source, context_scope_total, missing_by_source = _context_scope_counts(context_packs or [])
    document_error_counter = _document_error_counts(document_errors or [])
    source_ids = sorted(
        set(source_records)
        | set(pool_counter)
        | set(fetch_counter)
        | set(story_counter)
        | set(final_counter)
        | set(context_by_source)
        | set(document_error_counter)
    )

    sources: list[dict[str, Any]] = []
    for source_id in source_ids:
        record = source_records.get(source_id, {})
        main_count = int(record.get("main_count", 0) or 0)
        supplemental_count = int(record.get("supplemental_count", 0) or 0)
        accepted = int(record.get("accepted_count", main_count + supplemental_count) or 0)
        if not accepted:
            accepted = main_count + supplemental_count
        theme_pool_selected = pool_counter[source_id]
        document_fetch_selected = fetch_counter[source_id]
        story_count = story_counter[source_id]
        final_count = final_counter[source_id]
        sources.append(
            {
                "source_id": source_id,
                "raw_candidates": int(record.get("raw_candidate_count", 0) or 0),
                "main_candidates": main_count,
                "supplemental_candidates": supplemental_count,
                "accepted_candidates": accepted,
                "rejected_candidates": int(record.get("rejected_count", 0) or 0),
                "theme_counts": record.get("theme_counts", {}),
                "theme_pool_selected": theme_pool_selected,
                "document_fetch_selected": document_fetch_selected,
                "document_errors": document_error_counter[source_id],
                "evidence_scope_counts": _counter_dict(context_by_source.get(source_id, Counter())),
                "missing_field_counts": _counter_dict(missing_by_source.get(source_id, Counter())),
                "story_candidates": story_count,
                "final_stories": final_count,
                "diagnostic_reasons": _diagnostic_reasons(
                    accepted=accepted,
                    theme_pool_selected=theme_pool_selected,
                    document_fetch_selected=document_fetch_selected,
                    story_candidates=story_count,
                    final_stories=final_count,
                ),
            }
        )

    return {
        "version": "0.1.0",
        "sources": sources,
        "language_summary": {
            "story_candidates": _language_counts(story_candidates or []),
            "final_stories": _language_counts(final_stories or []),
        },
        "evidence_summary": {
            "scope_counts": _counter_dict(context_scope_total),
            "document_errors": sum(document_error_counter.values()),
            "sources_with_retrieved_context": sorted(
                source_id
                for source_id, counter in context_by_source.items()
                if counter.get("retrieved_context", 0)
            ),
        },
    }
