"""Source recovery suggestion engine from collection health and diagnostics.

This module reads source_health and collector_diagnostics reports and
produces auditable recovery suggestions. It does NOT crawl pages or
mutate state — it classifies issues and proposes next inspection steps.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Threshold configuration
# ---------------------------------------------------------------------------

MIN_EXPECTED_CANDIDATES: dict[str, int] = {
    "media_incremental_listing": 10,
    "media_listing": 10,
    "media_jsonp_paged_listing": 10,
    "media_rss": 5,
    "media_embedly_listing": 8,
    "official_rss": 3,
    "default": 8,
}

MISSING_TIME_RATIO_THRESHOLD: float = 0.3
"""If >30% of candidates (or candidate+rejected) lack timestamps, flag it."""

ERROR_COUNT_THRESHOLD: int = 2
"""Sources with this many or more collector errors are flagged for entry_broken."""

LOW_COUNT_RATIO: float = 0.3
"""candidate_count below 30% of expected triggers low_count."""

STRUCTURE_CHANGE_LINK_RATIO: float = 0.1
"""If link_count > 0 but candidate_count / link_count < 0.1, suspect a structure change."""

DUPLICATE_RATIO_THRESHOLD: float = 0.5
"""If duplicate_url_count / max(candidate_count,1) > 0.5, the listing may be stale."""


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


def _health_by_source(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in report.get("sources", []) if isinstance(report, dict) else []:
        if isinstance(item, dict):
            sid = _source_id(item)
            if sid:
                result[sid] = item
    return result


def _diagnostics_by_source(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in report.get("sources", []) if isinstance(report, dict) else []:
        if isinstance(item, dict):
            sid = _source_id(item)
            if sid:
                result[sid] = item
    return result


def _min_expected(collector: str) -> int:
    key = str(collector or "").strip().lower()
    return MIN_EXPECTED_CANDIDATES.get(key, MIN_EXPECTED_CANDIDATES["default"])


def _suggestion(
    action: str,
    *,
    priority: str = "medium",
    rationale: str = "",
) -> dict[str, Any]:
    return {
        "action": action,
        "priority": priority,
        "rationale": rationale,
    }


def _issue(
    source_id: str,
    issue_type: str,
    *,
    observed: dict[str, Any],
    expected: dict[str, Any],
    suggestions: list[dict[str, Any]],
    requires_human_review: bool = False,
) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "issue_type": issue_type,
        "evidence": {
            "observed": observed,
            "expected": expected,
        },
        "suggested_actions": suggestions,
        "requires_human_review": requires_human_review,
    }


def _classify_source_issues(
    source_id: str,
    health: dict[str, Any] | None,
    diagnostics: dict[str, Any] | None,
    collector: str,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []

    candidate_count = _int((diagnostics or {}).get("candidate_count", 0))
    raw_fetch_count = _int((diagnostics or {}).get("raw_fetch_count", 0))
    error_count = _int((diagnostics or {}).get("error_count", 0))
    health_error_count = _int((health or {}).get("error_count", 0))
    resolved_error_count = max(error_count, health_error_count)
    missing_time_count = _int((diagnostics or {}).get("missing_time_count", 0))
    link_count = _int((diagnostics or {}).get("link_count", 0))
    duplicate_url_count = _int((diagnostics or {}).get("duplicate_url_count", 0))
    reject_reasons = (diagnostics or {}).get("reject_reasons", {})
    if not isinstance(reject_reasons, dict):
        reject_reasons = {}
    irrelevant_rejects = _int(reject_reasons.get("irrelevant_topic", 0))

    min_expected = _min_expected(collector)

    # ---- entry_broken: errors dominate, no usable output ----
    if resolved_error_count >= ERROR_COUNT_THRESHOLD and candidate_count == 0:
        issues.append(
            _issue(
                source_id,
                "entry_broken",
                observed={
                    "error_count": resolved_error_count,
                    "raw_fetch_count": raw_fetch_count,
                    "candidate_count": candidate_count,
                },
                expected={
                    "max_error_count": ERROR_COUNT_THRESHOLD - 1,
                    "min_candidates": 1,
                },
                suggestions=[
                    _suggestion(
                        "verify_entry_urls",
                        priority="high",
                        rationale=f"Source produced {error_count} errors and 0 candidates. "
                        f"Check configured entry URLs for correctness and accessibility.",
                    ),
                    _suggestion(
                        "inspect_collector_parser",
                        priority="high",
                        rationale="Errors may stem from parser mismatch with page structure. "
                        "Capture raw HTML fixture and verify parser expectations.",
                    ),
                    _suggestion(
                        "check_network_access",
                        priority="medium",
                        rationale="If fetch errors include timeout/refused, verify network "
                        "connectivity and proxy configuration.",
                    ),
                ],
            )
        )

    # ---- network_persistent: health report indicates blocked source ----
    if health is not None and health.get("status") == "source_blocked":
        issues.append(
            _issue(
                source_id,
                "network_persistent",
                observed={
                    "health_status": "source_blocked",
                    "explanation": health.get("explanation", ""),
                    "error_count": resolved_error_count,
                },
                expected={
                    "health_status": "healthy",
                },
                suggestions=[
                    _suggestion(
                        "run_from_ide_or_allow_network",
                        priority="high",
                        rationale="Fetch was blocked by local network, permissions, "
                        "rate limits, or access rules. Run from a different network "
                        "environment or allow the collector in firewall/proxy.",
                    ),
                    _suggestion(
                        "check_proxy_or_firewall",
                        priority="high",
                        rationale="Inspect proxy settings and firewall rules. Add the "
                        "collector's user-agent and target domains to allow lists.",
                    ),
                    _suggestion(
                        "add_rate_limit_delays",
                        priority="medium",
                        rationale="If blocked by rate limiting (HTTP 429), add "
                        "inter-request delays or reduce concurrent fetches.",
                    ),
                ],
                requires_human_review=True,
            )
        )

    # ---- low_count: candidate count below threshold ----
    if 0 < candidate_count < min_expected:
        issues.append(
            _issue(
                source_id,
                "low_count",
                observed={
                    "candidate_count": candidate_count,
                    "raw_fetch_count": raw_fetch_count,
                    "link_count": link_count,
                },
                expected={
                    "min_candidates": min_expected,
                    "threshold_key": f"min_expected_candidates[{collector or 'default'}]",
                },
                suggestions=[
                    _suggestion(
                        "increase_pagination_depth",
                        priority="high",
                        rationale=f"Candidate count ({candidate_count}) is below "
                        f"expected minimum ({min_expected}) for {collector or 'this'} "
                        f"collector. Increase max_pages_per_entry or pagination limit.",
                    ),
                    _suggestion(
                        "expand_entry_coverage",
                        priority="medium",
                        rationale="Add topic-specific page_entries (e.g., per-platform "
                        "landing pages) to widen the crawl footprint.",
                    ),
                    _suggestion(
                        "on_this_day_backfill",
                        priority="medium",
                        rationale="If the source publishes infrequently, supplement "
                        "with on-this-day or historical record candidates.",
                    ),
                ],
            )
        )

    # ---- zero_candidates: source produced 0 candidates but no clear error ----
    if candidate_count == 0 and resolved_error_count < ERROR_COUNT_THRESHOLD and raw_fetch_count > 0:
        issues.append(
            _issue(
                source_id,
                "low_count",
                observed={
                    "candidate_count": 0,
                    "raw_fetch_count": raw_fetch_count,
                    "link_count": link_count,
                    "error_count": error_count,
                },
                expected={
                    "min_candidates": min_expected,
                    "threshold_key": f"min_expected_candidates[{collector or 'default'}]",
                },
                suggestions=[
                    _suggestion(
                        "inspect_listing_for_structure_change",
                        priority="high",
                        rationale=f"Source fetched {raw_fetch_count} raw records but "
                        f"yielded 0 candidates. The page structure may have changed, "
                        f"breaking the parser. Capture a raw HTML/JSON fixture.",
                    ),
                    _suggestion(
                        "save_fixture_from_real_html",
                        priority="high",
                        rationale="Save the current raw response as a test fixture "
                        "so the parser can be updated and validated offline.",
                    ),
                ],
            )
        )

    # ---- structure_change: many links extracted but few accepted candidates ----
    if link_count > 0 and candidate_count > 0:
        link_ratio = candidate_count / max(link_count, 1)
        if link_ratio < STRUCTURE_CHANGE_LINK_RATIO:
            issues.append(
                _issue(
                    source_id,
                    "structure_change",
                    observed={
                        "link_count": link_count,
                        "candidate_count": candidate_count,
                        "link_conversion_ratio": round(link_ratio, 3),
                    },
                    expected={
                        "min_link_conversion_ratio": STRUCTURE_CHANGE_LINK_RATIO,
                        "threshold": "structure_change_link_ratio",
                    },
                    suggestions=[
                        _suggestion(
                            "inspect_listing_html_structure",
                            priority="high",
                            rationale=f"Only {candidate_count}/{link_count} links "
                            f"({link_ratio:.1%}) converted to candidates. The page "
                            f"structure (CSS selectors, JSON paths) may have changed.",
                        ),
                        _suggestion(
                            "review_relevance_filters",
                            priority="medium",
                            rationale="Check if relevance filters or candidate-type "
                            "gates are rejecting structurally valid entries.",
                        ),
                        _suggestion(
                            "compare_with_historical_fixture",
                            priority="medium",
                            rationale="Diff current page structure against a known-good "
                            "historical fixture to identify changed elements.",
                        ),
                    ],
                )
            )

    # ---- irrelevant_reject_dominance: too many rejected as irrelevant ----
    if irrelevant_rejects >= max(candidate_count * 3, 10):
        issues.append(
            _issue(
                source_id,
                "structure_change",
                observed={
                    "irrelevant_topic_rejects": irrelevant_rejects,
                    "candidate_count": candidate_count,
                },
                expected={
                    "max_irrelevant_ratio": 3.0,
                    "threshold": "irrelevant_rejects > 3x candidate_count",
                },
                suggestions=[
                    _suggestion(
                        "review_relevance_filters",
                        priority="high",
                        rationale=f"Irrelevant-topic rejects ({irrelevant_rejects}) "
                        f"overwhelm accepted candidates ({candidate_count}). "
                        f"Relevance filters may be too narrow, or the source "
                        f"publishes mostly off-topic content.",
                    ),
                    _suggestion(
                        "consider_source_replacement",
                        priority="medium",
                        rationale="If the source consistently produces mostly "
                        "off-topic content, consider replacing it with a more "
                        "targeted alternative.",
                    ),
                ],
            )
        )

    # ---- missing_timestamps: high ratio of entries lack usable time ----
    denom = max(candidate_count + _int(reject_reasons.get("missing_time", 0)), 1)
    if denom > 0 and missing_time_count / denom >= MISSING_TIME_RATIO_THRESHOLD:
        issues.append(
            _issue(
                source_id,
                "missing_timestamps",
                observed={
                    "missing_time_count": missing_time_count,
                    "candidate_count": candidate_count,
                    "missing_ratio": round(missing_time_count / denom, 3),
                },
                expected={
                    "max_missing_ratio": MISSING_TIME_RATIO_THRESHOLD,
                    "threshold": "missing_time_ratio_threshold",
                },
                suggestions=[
                    _suggestion(
                        "improve_time_extraction_from_listing",
                        priority="high",
                        rationale=f"{missing_time_count}/{denom} entries lack "
                        f"timestamps. Prefer extracting time from listing-page "
                        f"markup before falling back to detail pages.",
                    ),
                    _suggestion(
                        "raise_detail_time_backfill_limit",
                        priority="medium",
                        rationale="Increase detail_time_backfill_limit so more "
                        "entries get timestamps from detail pages, but only if "
                        "detail pages reliably expose time metadata.",
                    ),
                    _suggestion(
                        "add_time_parser_patterns",
                        priority="medium",
                        rationale="Add locale-specific or site-specific time format "
                        "patterns to the time-extraction logic.",
                    ),
                ],
            )
        )

    # ---- stale_duplicates: high duplicate ratio suggests stale listing ----
    if candidate_count > 0 and duplicate_url_count / max(candidate_count, 1) >= DUPLICATE_RATIO_THRESHOLD:
        issues.append(
            _issue(
                source_id,
                "structure_change",
                observed={
                    "duplicate_url_count": duplicate_url_count,
                    "candidate_count": candidate_count,
                    "duplicate_ratio": round(duplicate_url_count / max(candidate_count, 1), 3),
                },
                expected={
                    "max_duplicate_ratio": DUPLICATE_RATIO_THRESHOLD,
                    "threshold": "duplicate_ratio_threshold",
                },
                suggestions=[
                    _suggestion(
                        "check_incremental_stop_condition",
                        priority="medium",
                        rationale=f"{duplicate_url_count} duplicate URLs suggest the "
                        f"incremental listing may be re-fetching seen pages or the "
                        f"stop condition (no_new_candidates) is too tight.",
                    ),
                    _suggestion(
                        "verify_candidate_deduplication",
                        priority="low",
                        rationale="Ensure the deduplication logic correctly tracks "
                        "URLs across pagination rounds.",
                    ),
                ],
            )
        )

    return issues


def generate_recovery_suggestions(
    source_health: dict[str, Any],
    collector_diagnostics: dict[str, Any],
) -> dict[str, Any]:
    """Generate auditable recovery suggestions from health and diagnostics.

    Args:
        source_health: Output of ``build_source_health_report()``.
        collector_diagnostics: Output of ``build_collector_diagnostics_report()``.

    Returns:
        A dict with ``version``, ``summary``, ``thresholds``, and ``issues``.
        Each issue contains ``source_id``, ``issue_type``, ``evidence``
        (observed vs expected), ``suggested_actions`` (list of action +
        priority + rationale), and ``requires_human_review``.
    """
    health_map = _health_by_source(source_health)
    diag_map = _diagnostics_by_source(collector_diagnostics)

    # Collect all known source IDs from both reports.
    all_source_ids: set[str] = set()
    all_source_ids.update(health_map.keys())
    all_source_ids.update(diag_map.keys())

    all_issues: list[dict[str, Any]] = []
    for source_id in sorted(all_source_ids):
        health = health_map.get(source_id)
        diag = diag_map.get(source_id)
        collector = str(
            (diag or {}).get("collector", "")
            or (health or {}).get("collector", "")
        ).strip()

        issues = _classify_source_issues(
            source_id=source_id,
            health=health,
            diagnostics=diag,
            collector=collector,
        )
        all_issues.extend(issues)

    issue_type_counts: dict[str, int] = {}
    human_review_count = 0
    for issue in all_issues:
        itype = str(issue.get("issue_type", ""))
        issue_type_counts[itype] = issue_type_counts.get(itype, 0) + 1
        if issue.get("requires_human_review"):
            human_review_count += 1

    return {
        "version": "0.1.0",
        "summary": {
            "total_issues": len(all_issues),
            "by_type": issue_type_counts,
            "requires_human_review": human_review_count,
        },
        "thresholds": {
            "min_expected_candidates": MIN_EXPECTED_CANDIDATES,
            "missing_time_ratio_threshold": MISSING_TIME_RATIO_THRESHOLD,
            "error_count_threshold": ERROR_COUNT_THRESHOLD,
            "low_count_ratio": LOW_COUNT_RATIO,
            "structure_change_link_ratio": STRUCTURE_CHANGE_LINK_RATIO,
            "duplicate_ratio_threshold": DUPLICATE_RATIO_THRESHOLD,
        },
        "issues": all_issues,
    }
