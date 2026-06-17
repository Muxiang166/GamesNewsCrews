"""Plan second-pass document fetches for underfilled theme sections.

Also provides FIL-004 Underfilled Section Fill — detect sections below the
minimum story count and fill them from supplemental candidates (same-section
only) or already-selected backfill candidates.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .editorial_focus import annotate_candidate_editorial_focus, candidate_editorial_priority
from .story_sections import classify_candidate_section


PUBLISHABLE_CANDIDATE_TYPES = {
    "news",
    "rumor",
    "platform_price",
    "hardware_platform",
    "review_score",
    "game_detail",
    "game_update",
    "game_announcement",
    "release_date",
    "trailer",
}


def _score(candidate: dict[str, Any]) -> float:
    value = candidate.get("heat_score", 0)
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def _sort_key(candidate: dict[str, Any]) -> tuple[int, float]:
    return (candidate_editorial_priority(candidate), _score(candidate))


def select_backfill_candidates(
    *,
    theme_candidate_pool: dict[str, Any],
    selection_stage_diagnostics: dict[str, Any],
    min_story_candidates_per_section: int = 5,
    max_backfill_fetch_per_section: int = 8,
    max_total_backfill_fetch: int = 20,
) -> list[dict[str, Any]]:
    """Choose unfetched candidates from sections blocked by the fetch budget."""

    selected: list[dict[str, Any]] = []
    diagnostics = selection_stage_diagnostics.get("sections", {})
    if not isinstance(diagnostics, dict):
        return selected

    for section in theme_candidate_pool.get("sections", []):
        if not isinstance(section, dict):
            continue

        section_id = str(section.get("id") or "")
        section_diag = diagnostics.get(section_id, {})
        if not isinstance(section_diag, dict):
            continue
        if int(section_diag.get("story_candidate_count") or 0) >= min_story_candidates_per_section:
            continue
        if section_diag.get("primary_bottleneck") != "document_fetch_budget":
            continue

        candidates = [
            annotate_candidate_editorial_focus(candidate)
            for candidate in section.get("candidates", [])
            if isinstance(candidate, dict)
            and not candidate.get("document_fetch_selected")
            and str(candidate.get("candidate_lane") or "main") == "main"
            and str(candidate.get("candidate_type") or "news") in PUBLISHABLE_CANDIDATE_TYPES
        ]
        candidates.sort(key=_sort_key, reverse=True)

        for candidate in candidates[: max_backfill_fetch_per_section]:
            candidate["backfill_reason"] = "underfilled_section_document_fetch_budget"
            candidate["backfill_theme_section"] = section_id
            selected.append(candidate)
            if len(selected) >= max_total_backfill_fetch:
                return selected

    return selected


# ── FIL-004 Underfilled Section Fill ──────────────────────────────────────────


def detect_underfilled_sections(
    theme_sections: dict[str, Any],
    min_stories_per_section: int = 3,
) -> list[dict[str, Any]]:
    """Identify theme sections whose selected story count is below the minimum.

    Args:
        theme_sections: Output of ``build_thematic_story_selection`` (dict with
            a ``sections`` list; each section has ``id``, ``label``,
            ``selected_count``, and ``stories``).
        min_stories_per_section: Threshold below which a section is considered
            underfilled.

    Returns:
        List of underfilled-section descriptors sorted by deficit descending.
        Each descriptor contains ``section_id``, ``label``, ``current_count``,
        ``deficit`` (how many stories are needed), and the original ``stories``
        list.
    """
    underfilled: list[dict[str, Any]] = []
    for section in theme_sections.get("sections", []):
        if not isinstance(section, dict):
            continue
        current = int(section.get("selected_count") or 0)
        if current >= min_stories_per_section:
            continue
        underfilled.append(
            {
                "section_id": str(section.get("id") or ""),
                "label": str(section.get("label") or ""),
                "current_count": current,
                "deficit": max(min_stories_per_section - current, 0),
                "stories": list(section.get("stories", [])),
            }
        )
    underfilled.sort(key=lambda item: item["deficit"], reverse=True)
    return underfilled


def fill_from_supplemental(
    underfilled_section: dict[str, Any],
    supplemental_candidates: list[dict[str, Any]],
    max_fill: int = 5,
) -> list[dict[str, Any]]:
    """Fill an underfilled section from the supplemental candidate pool.

    **Only** candidates classified to the *same* section are considered — cross-
    section stealing is prohibited.

    Each selected candidate is annotated with ``fill_source: "section_fill"``
    and ``fill_section_id``.

    Args:
        underfilled_section: A single descriptor returned by
            ``detect_underfilled_sections``.
        supplemental_candidates: Raw candidate dicts from the supplemental
            pool (any lane).
        max_fill: Maximum number of candidates to take from supplemental.

    Returns:
        List of selected supplemental candidates (sorted by editorial priority
        then heat score, best first).  May be empty or shorter than *max_fill*
        if the section does not have enough same-section supplemental
        candidates.
    """
    section_id = underfilled_section["section_id"]

    same_section: list[dict[str, Any]] = []
    for candidate in supplemental_candidates:
        if not isinstance(candidate, dict):
            continue
        if classify_candidate_section(candidate) != section_id:
            continue
        same_section.append(candidate)

    same_section.sort(key=_sort_key, reverse=True)

    selected: list[dict[str, Any]] = []
    for candidate in same_section[: max(max_fill, 0)]:
        annotated = annotate_candidate_editorial_focus(dict(candidate))
        annotated["fill_source"] = "section_fill"
        annotated["fill_section_id"] = section_id
        selected.append(annotated)

    return selected


def fill_from_backfill_candidates(
    underfilled_section: dict[str, Any],
    backfill_candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Use already-selected backfill candidates to fill an underfilled section.

    Matches candidates whose ``backfill_theme_section`` field equals the
    underfilled section id.

    Args:
        underfilled_section: A single descriptor returned by
            ``detect_underfilled_sections``.
        backfill_candidates: Candidates previously selected by
            ``select_backfill_candidates`` (each expected to carry
            ``backfill_theme_section``).

    Returns:
        Matching backfill candidates in their original order.
    """
    section_id = underfilled_section["section_id"]

    matched: list[dict[str, Any]] = []
    for candidate in backfill_candidates:
        if not isinstance(candidate, dict):
            continue
        if str(candidate.get("backfill_theme_section") or "") != section_id:
            continue
        matched.append(candidate)

    return matched


def save_underfilled_section_diagnostics(
    underfilled_sections: list[dict[str, Any]],
    fill_results: dict[str, list[dict[str, Any]]],
    output_dir: Path,
) -> Path:
    """Write ``underfilled_section_diagnostics.json`` with before/after counts.

    Args:
        underfilled_sections: List from ``detect_underfilled_sections``.
        fill_results: Mapping ``section_id`` -> list of fill candidates (from
            either supplemental or backfill).
        output_dir: Directory where the JSON file will be written.

    Returns:
        Path to the written diagnostics file.
    """
    entries: list[dict[str, Any]] = []
    for uf in underfilled_sections:
        section_id = uf["section_id"]
        fills = fill_results.get(section_id, [])
        entries.append(
            {
                "section_id": section_id,
                "label": uf["label"],
                "before_count": uf["current_count"],
                "fill_count": len(fills),
                "after_count": uf["current_count"] + len(fills),
                "deficit": uf["deficit"],
                "deficit_remaining": max(uf["deficit"] - len(fills), 0),
                "fill_sources": sorted(
                    {str(fill.get("fill_source") or fill.get("backfill_reason") or "unknown")
                     for fill in fills}
                ),
            }
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "underfilled_section_diagnostics.json"
    output_path.write_text(
        json.dumps(
            {
                "version": "0.1.0",
                "underfilled_sections": entries,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return output_path
