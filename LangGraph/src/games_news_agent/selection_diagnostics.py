"""Diagnostics for post-collection selection and ranking drop-off."""

from __future__ import annotations

from typing import Any


SECTION_IDS = ("sony", "nintendo", "microsoft", "pc", "supplemental")


def _safe_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return 0


def _section_id(value: Any) -> str:
    section = str(value or "").strip()
    return section if section in SECTION_IDS else "supplemental"


def _candidate_url(value: dict[str, Any]) -> str:
    return str(value.get("url") or value.get("candidate_url") or "").strip()


def _metadata(value: dict[str, Any]) -> dict[str, Any]:
    metadata = value.get("metadata", {})
    return metadata if isinstance(metadata, dict) else {}


def _candidate_theme(value: dict[str, Any], url_to_section: dict[str, str] | None = None) -> str:
    metadata = _metadata(value)
    section = str(value.get("theme_section") or metadata.get("theme_section") or "").strip()
    if section in SECTION_IDS:
        return section
    url = _candidate_url(value) or str(metadata.get("candidate_url") or "").strip()
    if url and url_to_section and url in url_to_section:
        return url_to_section[url]
    return "supplemental"


def _build_url_to_section(theme_candidate_pool: dict[str, Any]) -> dict[str, str]:
    by_url: dict[str, str] = {}
    for section in theme_candidate_pool.get("sections", []):
        if not isinstance(section, dict):
            continue
        section_id = _section_id(section.get("id"))
        for candidate in section.get("candidates", []):
            if not isinstance(candidate, dict):
                continue
            url = _candidate_url(candidate)
            if url and url not in by_url:
                by_url[url] = section_id
    return by_url


def _context_pack_counts(
    context_packs: list[dict[str, Any]],
    url_to_section: dict[str, str],
) -> dict[str, int]:
    counts = {section_id: 0 for section_id in SECTION_IDS}
    for pack in context_packs:
        candidate = pack.get("candidate", {}) if isinstance(pack, dict) else {}
        if isinstance(candidate, dict):
            counts[_candidate_theme(candidate, url_to_section)] += 1
    return counts


def _claim_counts(
    claim_verifications: list[dict[str, Any]],
    url_to_section: dict[str, str],
) -> dict[str, int]:
    counts = {section_id: 0 for section_id in SECTION_IDS}
    for claim in claim_verifications:
        if not isinstance(claim, dict):
            continue
        metadata = _metadata(claim)
        candidate = {
            "url": metadata.get("candidate_url"),
            "candidate_url": metadata.get("candidate_url"),
            "theme_section": metadata.get("theme_section"),
            "metadata": metadata,
        }
        counts[_candidate_theme(candidate, url_to_section)] += 1
    return counts


def _story_counts(story_candidates: list[dict[str, Any]]) -> dict[str, int]:
    counts = {section_id: 0 for section_id in SECTION_IDS}
    for story in story_candidates:
        if isinstance(story, dict):
            counts[_candidate_theme(story)] += 1
    return counts


def _final_counts(theme_sections: dict[str, Any]) -> dict[str, int]:
    counts = {section_id: 0 for section_id in SECTION_IDS}
    sections = theme_sections.get("sections", []) if isinstance(theme_sections, dict) else []
    for section in sections:
        if not isinstance(section, dict):
            continue
        section_id = _section_id(section.get("id"))
        if "selected_count" in section:
            counts[section_id] = _safe_int(section.get("selected_count"))
            continue
        stories = section.get("stories", [])
        counts[section_id] = len(stories) if isinstance(stories, list) else 0
    return counts


def _source_intake_counts(source_theme_counts: dict[str, Any]) -> dict[str, dict[str, Any]]:
    sections: dict[str, dict[str, Any]] = {
        section_id: {
            "source_accepted_count": 0,
            "source_main_count": 0,
            "source_supplemental_count": 0,
            "source_counts": {},
        }
        for section_id in SECTION_IDS
    }
    for source in source_theme_counts.get("sources", []):
        if not isinstance(source, dict):
            continue
        source_id = str(source.get("source_id") or "unknown")
        theme_counts = source.get("theme_counts", {})
        lane_counts = source.get("lane_theme_counts", {})
        main_counts = lane_counts.get("main", {}) if isinstance(lane_counts, dict) else {}
        supplemental_counts = lane_counts.get("supplemental", {}) if isinstance(lane_counts, dict) else {}
        for section_id in SECTION_IDS:
            main_count = _safe_int(main_counts.get(section_id) if isinstance(main_counts, dict) else 0)
            supplemental_count = _safe_int(
                supplemental_counts.get(section_id) if isinstance(supplemental_counts, dict) else 0
            )
            accepted_count = _safe_int(theme_counts.get(section_id) if isinstance(theme_counts, dict) else 0)
            if not accepted_count:
                accepted_count = main_count + supplemental_count
            if not (accepted_count or main_count or supplemental_count):
                continue
            section_item = sections[section_id]
            section_item["source_accepted_count"] += accepted_count
            section_item["source_main_count"] += main_count
            section_item["source_supplemental_count"] += supplemental_count
            section_item["source_counts"][source_id] = {
                "accepted_count": accepted_count,
                "main_count": main_count,
                "supplemental_count": supplemental_count,
            }
    return sections


def _summary(source_theme_counts: dict[str, Any]) -> dict[str, int]:
    raw = source_theme_counts.get("summary", {}) if isinstance(source_theme_counts, dict) else {}
    if not isinstance(raw, dict):
        raw = {}
    return {
        "raw_candidates": _safe_int(raw.get("raw_candidates")),
        "accepted_candidates": _safe_int(raw.get("accepted_candidates")),
        "main_candidates": _safe_int(raw.get("main_candidates")),
        "supplemental_candidates": _safe_int(raw.get("supplemental_candidates")),
        "rejected_candidates": _safe_int(raw.get("rejected_candidates")),
    }


def _bottleneck(item: dict[str, int]) -> str:
    if item["pool_count"] > item["fetch_selected_count"]:
        return "document_fetch_budget"
    if item["fetch_selected_count"] > item["context_pack_count"]:
        return "document_fetch_failure"
    if item["context_pack_count"] > item["claim_verification_count"]:
        return "claim_extraction_or_verification"
    if item["claim_verification_count"] > item["story_candidate_count"]:
        return "story_publishability_filter"
    if item["story_candidate_count"] > item["final_selected_count"]:
        return "final_ranking_limit"
    if item["source_accepted_count"] > item["candidate_count"]:
        return "candidate_pool_classification"
    return "no_drop_detected"


def build_selection_stage_diagnostics(
    *,
    theme_candidate_pool: dict[str, Any],
    context_packs: list[dict[str, Any]],
    claim_verifications: list[dict[str, Any]],
    story_candidates: list[dict[str, Any]],
    theme_sections: dict[str, Any],
    source_theme_counts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return per-theme stage counts from source intake to final story selection."""

    source_counts = source_theme_counts or {}
    url_to_section = _build_url_to_section(theme_candidate_pool)
    context_counts = _context_pack_counts(context_packs, url_to_section)
    claim_counts = _claim_counts(claim_verifications, url_to_section)
    story_counts = _story_counts(story_candidates)
    final_counts = _final_counts(theme_sections)
    source_intake = _source_intake_counts(source_counts)

    sections: dict[str, dict[str, Any]] = {}
    seen_sections: set[str] = set()
    for section in theme_candidate_pool.get("sections", []):
        if not isinstance(section, dict):
            continue
        section_id = _section_id(section.get("id"))
        seen_sections.add(section_id)
        intake = source_intake.get(section_id, {})
        item = {
            "source_accepted_count": _safe_int(intake.get("source_accepted_count")),
            "source_main_count": _safe_int(intake.get("source_main_count")),
            "source_supplemental_count": _safe_int(intake.get("source_supplemental_count")),
            "source_counts": intake.get("source_counts", {}),
            "candidate_count": _safe_int(section.get("candidate_count")),
            "pool_count": _safe_int(section.get("pool_count")),
            "fetch_selected_count": _safe_int(section.get("fetch_selected_count")),
            "context_pack_count": context_counts.get(section_id, 0),
            "claim_verification_count": claim_counts.get(section_id, 0),
            "story_candidate_count": story_counts.get(section_id, 0),
            "final_selected_count": final_counts.get(section_id, 0),
        }
        sections[section_id] = {**item, "primary_bottleneck": _bottleneck(item)}

    for section_id in SECTION_IDS:
        if section_id in seen_sections:
            continue
        intake = source_intake.get(section_id, {})
        item = {
            "source_accepted_count": _safe_int(intake.get("source_accepted_count")),
            "source_main_count": _safe_int(intake.get("source_main_count")),
            "source_supplemental_count": _safe_int(intake.get("source_supplemental_count")),
            "source_counts": intake.get("source_counts", {}),
            "candidate_count": 0,
            "pool_count": 0,
            "fetch_selected_count": 0,
            "context_pack_count": context_counts.get(section_id, 0),
            "claim_verification_count": claim_counts.get(section_id, 0),
            "story_candidate_count": story_counts.get(section_id, 0),
            "final_selected_count": final_counts.get(section_id, 0),
        }
        sections[section_id] = {**item, "primary_bottleneck": _bottleneck(item)}

    bottlenecks: dict[str, int] = {}
    for section in sections.values():
        key = str(section.get("primary_bottleneck") or "unknown")
        bottlenecks[key] = bottlenecks.get(key, 0) + 1

    return {
        "version": "0.1.0",
        "summary": {
            **_summary(source_counts),
            "sections": len(sections),
            "bottleneck_counts": bottlenecks,
        },
        "sections": sections,
    }
