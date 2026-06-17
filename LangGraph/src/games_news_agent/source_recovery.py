"""Source recovery planning from deterministic collection diagnostics.

The recovery planner does not crawl pages or produce facts. It reads existing
artifacts and proposes which deterministic tool/config path to inspect next.
"""

from __future__ import annotations

from typing import Any


CORE_THEME_IDS = ("sony", "nintendo", "microsoft", "pc")


def _source_id(item: dict[str, Any]) -> str:
    return str(item.get("source_id") or item.get("id") or "").strip()


def _number(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return 0.0


def _int(value: Any) -> int:
    return int(_number(value))


def _diagnostics_by_source(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in report.get("sources", []) if isinstance(report, dict) else []:
        if isinstance(item, dict):
            source_id = _source_id(item)
            if source_id:
                result[source_id] = item
    return result


def _theme_counts_by_source(report: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in (report or {}).get("sources", []) if isinstance(report, dict) else []:
        if isinstance(item, dict):
            source_id = _source_id(item)
            if source_id:
                result[source_id] = item
    return result


def _reject_count(diagnostics: dict[str, Any], reason: str) -> int:
    reject_reasons = diagnostics.get("reject_reasons", {})
    if not isinstance(reject_reasons, dict):
        return 0
    return _int(reject_reasons.get(reason, 0))


def _expected_core_themes(source: dict[str, Any]) -> set[str]:
    tags = {str(tag).strip().lower() for tag in source.get("tags", []) if str(tag).strip()}
    source_id = str(source.get("id") or "").lower()
    name = str(source.get("name") or "").lower()
    text = f" {source_id} {name} {' '.join(tags)} "
    expected: set[str] = set()
    if any(token in text for token in ("sony", "playstation", " ps5 ", " ps4 ")):
        expected.add("sony")
    if any(token in text for token in ("nintendo", "switch")):
        expected.add("nintendo")
    if any(token in text for token in ("xbox", "microsoft")):
        expected.add("microsoft")
    if "pc" in tags or "steam" in tags or " pc " in text or "pcgamer" in source_id:
        expected.add("pc")
    return expected


def _action(
    action_id: str,
    *,
    target_tool: str,
    reason: str,
    expected_effect: str,
    risk_level: str = "low",
    requires_human_approval: bool = False,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "action_id": action_id,
        "target_tool": target_tool,
        "params": params or {},
        "reason": reason,
        "expected_effect": expected_effect,
        "risk_level": risk_level,
        "requires_human_approval": requires_human_approval,
        "produces_facts": False,
    }


def _zero_theme_gaps(
    source: dict[str, Any],
    theme_metrics: dict[str, Any],
    *,
    target_theme_count: int,
) -> dict[str, int]:
    configured_themes = {
        str(entry.get("theme_section") or "").strip()
        for entry in source.get("page_entries", [])
        if isinstance(entry, dict)
    }
    has_configured_theme_entries = bool(configured_themes)
    if not configured_themes:
        configured_themes = _expected_core_themes(source)
    if not configured_themes and str(source.get("kind") or "").strip().lower() == "official":
        return {}
    if not configured_themes:
        configured_themes = set(CORE_THEME_IDS)
    counts = theme_metrics.get("theme_counts", {})
    if not isinstance(counts, dict):
        counts = {}
    gaps: dict[str, int] = {}
    for theme_id in CORE_THEME_IDS:
        if theme_id not in configured_themes:
            continue
        count = _int(counts.get(theme_id, 0))
        if has_configured_theme_entries:
            if count == 0:
                gaps[theme_id] = max(target_theme_count, 0)
        elif count < target_theme_count:
            gaps[theme_id] = max(target_theme_count - count, 0)
    return gaps


def _entry_stop_reasons(entries: list[dict[str, Any]]) -> dict[str, int]:
    reasons: dict[str, int] = {}
    for entry in entries:
        reason = str(entry.get("pagination_stop_reason") or "").strip()
        if reason:
            reasons[reason] = reasons.get(reason, 0) + 1
    return reasons


def _source_plan(
    source: dict[str, Any],
    diagnostics: dict[str, Any],
    theme_metrics: dict[str, Any],
    *,
    target_candidates_per_source: int,
    target_theme_count: int,
) -> dict[str, Any]:
    source_id = str(source.get("id") or _source_id(diagnostics)).strip()
    collector = str(source.get("collector") or diagnostics.get("collector") or "").strip()
    candidate_count = _int(diagnostics.get("candidate_count", 0))
    raw_fetch_count = _int(diagnostics.get("raw_fetch_count", 0))
    missing_time_count = _int(diagnostics.get("missing_time_count", 0))
    error_count = _int(diagnostics.get("error_count", 0))
    parse_warning_count = _int(diagnostics.get("parse_warning_count", 0))
    irrelevant_count = _reject_count(diagnostics, "irrelevant_topic")
    missing_time_rejects = _reject_count(diagnostics, "missing_time")
    entries = diagnostics.get("entries", [])
    if not isinstance(entries, list):
        entries = []
    theme_gaps = _zero_theme_gaps(
        source,
        theme_metrics,
        target_theme_count=target_theme_count,
    )
    stop_reasons = _entry_stop_reasons([entry for entry in entries if isinstance(entry, dict)])

    actions: list[dict[str, Any]] = []
    if error_count and candidate_count == 0:
        actions.append(
            _action(
                "inspect_blocked_or_failed_source",
                target_tool="HttpFetcher/CollectorRegistry",
                reason="The source produced errors and no accepted candidates.",
                expected_effect="Classify the failure as blocked, fetch error, parser error, or wrong entry URL.",
                risk_level="medium",
                params={"error_count": error_count, "raw_fetch_count": raw_fetch_count},
            )
        )

    if candidate_count < target_candidates_per_source:
        if collector == "media_incremental_listing":
            actions.append(
                _action(
                    "inspect_incremental_pagination",
                    target_tool="CollectorRegistry.media_incremental_listing",
                    reason="Incremental listing output is below the per-source target.",
                    expected_effect="Check Load More/next-page detection, max_pages_per_entry, stale stop behavior, and duplicate-heavy pages.",
                    params={
                        "candidate_count": candidate_count,
                        "target_candidates_per_source": target_candidates_per_source,
                        "stop_reasons": stop_reasons,
                    },
                )
            )
        elif collector in {"media_listing", "media_jsonp_paged_listing"}:
            actions.append(
                _action(
                    "inspect_listing_entries",
                    target_tool=f"CollectorRegistry.{collector}",
                    reason="Listing output is below the per-source target.",
                    expected_effect="Check configured entries, pagination depth, and whether the page exposes the expected article cards.",
                    params={
                        "candidate_count": candidate_count,
                        "target_candidates_per_source": target_candidates_per_source,
                    },
                )
            )
        elif collector == "media_rss":
            actions.append(
                _action(
                    "add_or_split_feed_entries",
                    target_tool="SourcePlanner/source config",
                    reason="RSS output is below the per-source target.",
                    expected_effect="Look for additional official feeds or topic-specific feeds before adding unrelated media sources.",
                    params={
                        "candidate_count": candidate_count,
                        "target_candidates_per_source": target_candidates_per_source,
                    },
                )
            )

    if candidate_count and missing_time_count / max(candidate_count + missing_time_rejects, 1) >= 0.3:
        actions.append(
            _action(
                "improve_time_extraction",
                target_tool="ListingCollector/WebPageCollector detail_time_backfill",
                reason="A large share of candidates or rejects lack usable timestamps.",
                expected_effect="Prefer list-page time parsing first; then raise detail_time_backfill_limit only if detail pages expose reliable time metadata.",
                params={
                    "missing_time_count": missing_time_count,
                    "missing_time_rejects": missing_time_rejects,
                },
            )
        )

    if irrelevant_count >= max(candidate_count * 3, 10):
        actions.append(
            _action(
                "review_relevance_filters",
                target_tool="SourceRelevanceGate/CandidateTypeGate",
                reason="Rejected irrelevant-topic results dominate accepted candidates.",
                expected_effect="Separate broad source noise from overly strict filters before changing crawl depth.",
                params={
                    "irrelevant_topic_rejects": irrelevant_count,
                    "candidate_count": candidate_count,
                },
            )
        )

    if theme_gaps:
        actions.append(
            _action(
                "fill_theme_gaps",
                target_tool="SourcePlanner/source entries",
                reason="One or more configured core themes produced zero accepted candidates.",
                expected_effect="Inspect theme page entries, source_entry_theme mapping, and topic filters for empty sections.",
                params={"theme_gaps": theme_gaps},
            )
        )

    if collector == "media_incremental_listing" and (
        candidate_count < target_candidates_per_source or parse_warning_count or missing_time_count
    ):
        actions.append(
            _action(
                "browser_probe_if_deterministic_signals_remain_weak",
                target_tool="browser_probe/manual_probe",
                reason="This source depends on dynamic or incremental navigation; a low-frequency browser probe can reveal the deterministic URL/request pattern.",
                expected_effect="Record observed links, request URLs, and timestamp locations so the deterministic collector can be improved.",
                risk_level="medium",
                requires_human_approval=True,
                params={"collector": collector},
            )
        )

    status = "needs_recovery" if actions else "healthy_enough"
    return {
        "source_id": source_id,
        "name": source.get("name") or diagnostics.get("name") or source_id,
        "collector": collector,
        "status": status,
        "metrics": {
            "raw_fetch_count": raw_fetch_count,
            "candidate_count": candidate_count,
            "missing_time_count": missing_time_count,
            "error_count": error_count,
            "parse_warning_count": parse_warning_count,
            "irrelevant_topic_rejects": irrelevant_count,
        },
        "theme_gaps": theme_gaps,
        "entry_stop_reasons": stop_reasons,
        "recommended_actions": actions,
    }


def build_source_recovery_plan(
    *,
    sources: list[dict[str, Any]],
    collector_diagnostics: dict[str, Any],
    source_theme_counts: dict[str, Any] | None = None,
    target_candidates_per_source: int = 10,
    target_theme_count: int = 20,
) -> dict[str, Any]:
    """Build a non-mutating source recovery plan from collection artifacts."""

    diagnostics = _diagnostics_by_source(collector_diagnostics)
    theme_counts = _theme_counts_by_source(source_theme_counts)
    plans: list[dict[str, Any]] = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        source_id = str(source.get("id") or "").strip()
        source_diagnostics = diagnostics.get(source_id)
        if source_diagnostics is None:
            continue
        plans.append(
            _source_plan(
                source,
                source_diagnostics,
                theme_counts.get(source_id, {}),
                target_candidates_per_source=target_candidates_per_source,
                target_theme_count=target_theme_count,
            )
        )

    needs_recovery = sum(1 for item in plans if item.get("status") == "needs_recovery")
    return {
        "version": "0.1.0",
        "summary": {
            "sources": len(plans),
            "needs_recovery": needs_recovery,
            "healthy_enough": len(plans) - needs_recovery,
        },
        "sources": plans,
    }
