"""Human-readable CLI progress formatting."""

from __future__ import annotations

from typing import Any


THEME_LABELS = {
    "sony": "索尼",
    "nintendo": "任天堂",
    "microsoft": "微软",
    "pc": "PC",
    "supplemental": "补充",
}


def _count(state: dict[str, Any], key: str) -> int:
    value = state.get(key, [])
    return len(value) if isinstance(value, list) else 0


def _theme_counts_text(theme_counts: dict[str, Any]) -> str:
    parts: list[str] = []
    for section_id, label in THEME_LABELS.items():
        count = theme_counts.get(section_id, 0)
        if isinstance(count, int) and count > 0:
            parts.append(f"{label}={count}条")
    return "，".join(parts) if parts else "暂无入池主题"


def _source_theme_lines(state: dict[str, Any], *, limit: int = 8) -> list[str]:
    report = state.get("source_theme_counts", {})
    if not isinstance(report, dict):
        return []
    sources = report.get("sources", [])
    if not isinstance(sources, list):
        return []

    lines: list[str] = []
    for source in sources[:limit]:
        if not isinstance(source, dict):
            continue
        accepted_count = source.get("accepted_count", 0)
        if not isinstance(accepted_count, int) or accepted_count <= 0:
            continue
        theme_counts = source.get("theme_counts", {})
        if not isinstance(theme_counts, dict):
            theme_counts = {}
        name = str(source.get("name") or source.get("source_id") or "unknown")
        lines.append(f"  - {name}: {_theme_counts_text(theme_counts)}")
    return lines


def _theme_pool_text(state: dict[str, Any]) -> str:
    pool = state.get("theme_candidate_pool", {})
    if not isinstance(pool, dict):
        return ""
    sections = pool.get("sections", [])
    if not isinstance(sections, list):
        return ""
    parts: list[str] = []
    for section in sections:
        if not isinstance(section, dict):
            continue
        label = str(section.get("label") or THEME_LABELS.get(str(section.get("id")), "未分类"))
        count = section.get("pool_count", 0)
        if isinstance(count, int) and count > 0:
            fetch_count = section.get("fetch_selected_count")
            if isinstance(fetch_count, int):
                parts.append(f"{label}={count}条(fetch={fetch_count})")
            else:
                parts.append(f"{label}={count}条")
    return "，".join(parts)


def _candidate_memory_text(state: dict[str, Any]) -> str:
    summary = state.get("candidate_memory_summary", {})
    if not isinstance(summary, dict) or not summary:
        return ""
    return (
        "memory: "
        f"new={summary.get('new_records', 0)} "
        f"updated={summary.get('updated_records', 0)} "
        f"total={summary.get('total_records', 0)}"
    )


def _collector_diagnostics_text(state: dict[str, Any]) -> str:
    diagnostics = state.get("collector_diagnostics", {})
    if not isinstance(diagnostics, dict):
        return ""
    summary = diagnostics.get("summary", {})
    if not isinstance(summary, dict) or not summary:
        return ""
    return (
        "diagnostics: "
        f"links={summary.get('link_count', 0)} "
        f"missing_time={summary.get('missing_time_count', 0)} "
        f"detail_backfill={summary.get('detail_time_backfill_count', 0)}"
    )


def _search_expansion_methods_text(state: dict[str, Any]) -> str:
    counts: dict[str, int] = {}
    requests = state.get("search_expansion_requests", [])
    if isinstance(requests, list):
        for request in requests:
            if not isinstance(request, dict):
                continue
            method = str(request.get("method") or "unknown")
            counts[method] = counts.get(method, 0) + 1
    if not counts:
        observations = state.get("search_expansion_observations", {})
        summary = observations.get("summary", {}) if isinstance(observations, dict) else {}
        method_counts = summary.get("method_counts", {}) if isinstance(summary, dict) else {}
        if isinstance(method_counts, dict):
            for method, count in method_counts.items():
                if isinstance(count, int) and count > 0:
                    counts[str(method)] = count
    if not counts:
        return ""
    parts = [f"{method}={counts[method]}" for method in sorted(counts)]
    return "methods: " + " ".join(parts)


def _search_expansion_llm_text(state: dict[str, Any]) -> str:
    query_requests = _count(state, "search_expansion_llm_query_requests")
    query_results = _count(state, "search_expansion_llm_query_results")
    relevance_requests = _count(state, "search_expansion_llm_relevance_requests")
    relevance_results = _count(state, "search_expansion_llm_relevance_results")
    if not any((query_requests, query_results, relevance_requests, relevance_results)):
        return ""
    return (
        f"llm_query={query_requests}/{query_results} "
        f"llm_relevance={relevance_requests}/{relevance_results}"
    )


def format_live_collection_event(event: dict[str, Any]) -> str:
    """Format a live collector event emitted while search_candidates is running."""

    event_name = str(event.get("event", ""))
    source_name = str(event.get("source_name") or event.get("source_id") or "unknown")
    source_id = str(event.get("source_id") or "unknown")
    if event_name == "source_start":
        return (
            "[search_candidates] "
            f"collecting {source_name} "
            f"({event.get('collector', 'collector')}, entries={event.get('entry_url_count', 0)})"
        )
    if event_name == "source_done":
        return (
            "[search_candidates] "
            f"collected {source_name}: "
            f"candidates={event.get('candidate_count', 0)} "
            f"raw_fetches={event.get('raw_fetch_count', 0)} "
            f"errors={event.get('error_count', 0)} "
            f"elapsed={event.get('elapsed_seconds', 0)}s"
        )
    if event_name == "detail_time_backfill_start":
        return (
            f"  - detail_time_backfill {source_id}: "
            f"needed={event.get('needed', 0)} limit={event.get('limit', 0)}"
        )
    if event_name == "detail_time_backfill_done":
        return (
            f"  - detail_time_backfill {source_id}: "
            f"attempted={event.get('attempted', 0)} "
            f"backfilled={event.get('backfilled', 0)} "
            f"errors={event.get('error_count', 0)} "
            f"elapsed={event.get('elapsed_seconds', 0)}s"
        )
    return f"[search_candidates] collector_event={event_name or 'unknown'} source={source_id}"


def format_progress_update(node_name: str, state: dict[str, Any]) -> list[str]:
    """Format a concise progress update after one graph node completes."""

    if node_name == "plan_sources":
        return [f"[plan_sources] sources={_count(state, 'sources')}"]

    if node_name == "search_candidates":
        lines = [
            (
                "[search_candidates] "
                f"main={_count(state, 'candidates')} "
                f"supplemental={_count(state, 'supplemental_candidates')} "
                f"rejected={_count(state, 'rejected_candidates')}"
            )
        ]
        memory_text = _candidate_memory_text(state)
        if memory_text:
            lines.append(f"  - {memory_text}")
        diagnostics_text = _collector_diagnostics_text(state)
        if diagnostics_text:
            lines.append(f"  - {diagnostics_text}")
        navigation_requests = state.get("source_navigation_requests", [])
        navigation_results = state.get("source_navigation_results", [])
        if isinstance(navigation_requests, list):
            result_count = len(navigation_results) if isinstance(navigation_results, list) else 0
            lines.append(f"  - source_navigation: requests={len(navigation_requests)} results={result_count}")
        lines.extend(_source_theme_lines(state))
        return lines

    if node_name == "fetch_documents":
        pool = state.get("theme_candidate_pool", {})
        pool_count = pool.get("candidate_pool_count", 0) if isinstance(pool, dict) else 0
        fetch_selected = pool.get("fetch_selected_count", 0) if isinstance(pool, dict) else 0
        fetch_limit = pool.get("fetch_limit", 0) if isinstance(pool, dict) else 0
        fetch_limit_scope = pool.get("fetch_limit_scope", "") if isinstance(pool, dict) else ""
        if fetch_limit_scope == "per_section":
            fetch_budget_text = f"fetch_selected={fetch_selected} per_section_limit={fetch_limit}"
        else:
            fetch_budget_text = f"fetch_selected={fetch_selected}/{fetch_limit}"
        dropped_before_fetch = pool.get("dropped_before_fetch", []) if isinstance(pool, dict) else []
        dropped_count = len(dropped_before_fetch) if isinstance(dropped_before_fetch, list) else 0
        lines = [
            (
                "[fetch_documents] "
                f"theme_pool={pool_count} "
                f"{fetch_budget_text} "
                f"documents={_count(state, 'documents')} "
                f"context_packs={_count(state, 'context_packs')}"
            )
        ]
        if dropped_count:
            lines.append(f"  - dropped_before_fetch={dropped_count}")
        theme_text = _theme_pool_text(state)
        if theme_text:
            lines.append(f"  - 主题候选池: {theme_text}")
        return lines

    if node_name == "expand_search_candidates":
        observations = state.get("search_expansion_observations", {})
        summary = observations.get("summary", {}) if isinstance(observations, dict) else {}
        lines = [
            (
                "[expand_search_candidates] "
                f"requests={_count(state, 'search_expansion_requests')} "
                f"targets={summary.get('targets', 0)} "
                f"ok={summary.get('ok', 0)} "
                f"blocked={summary.get('blocked', 0)} "
                f"signals={summary.get('with_result_signal', 0)} "
                f"candidates={_count(state, 'search_expansion_candidates')}"
            )
        ]
        methods_text = _search_expansion_methods_text(state)
        if methods_text:
            lines.append(f"  - {methods_text}")
        llm_text = _search_expansion_llm_text(state)
        if llm_text:
            lines.append(f"  - {llm_text}")
        return lines

    if node_name == "probe_discussions":
        report = state.get("discussion_probe_report", {})
        summary = report.get("summary", {}) if isinstance(report, dict) else {}
        line = (
            "[probe_discussions] "
            f"probed={summary.get('probed_candidates', 0)} "
            f"with_evidence={summary.get('with_discussion_evidence', 0)} "
            f"coverage={summary.get('coverage', 0)}"
        )
        observations = state.get("discussion_probe_observations", {})
        observation_summary = observations.get("summary", {}) if isinstance(observations, dict) else {}
        if observation_summary and observation_summary.get("targets", 0):
            line = (
                f"{line} "
                f"provider_targets={observation_summary.get('targets', 0)} "
                f"provider_ok={observation_summary.get('ok', 0)} "
                f"provider_blocked={observation_summary.get('blocked', 0)} "
                f"provider_signals={observation_summary.get('with_result_signal', 0)}"
            )
        return [line]

    if node_name == "verify_claims":
        return [
            (
                "[verify_claims] "
                f"claims={_count(state, 'claims')} "
                f"verifications={_count(state, 'claim_verifications')} "
                f"llm_requests={_count(state, 'llm_verification_requests')} "
                f"llm_results={_count(state, 'llm_verification_results')}"
            )
        ]

    if node_name == "score_heat":
        return [
            (
                "[score_heat] "
                f"story_candidates={_count(state, 'story_candidates')} "
                f"final_stories={_count(state, 'stories')} "
                f"editorial_judgment_requests={_count(state, 'editorial_judgment_requests')}"
            )
        ]

    if node_name == "plan_selection_backfill":
        return [
            (
                "[plan_selection_backfill] "
                f"candidates={_count(state, 'selection_backfill_candidates')}"
            )
        ]

    if node_name == "validate_content_quality":
        report = state.get("content_quality_report", {})
        if not isinstance(report, dict):
            return ["[validate_content_quality] report=missing"]
        return [
            (
                "[validate_content_quality] "
                f"score={report.get('overall_score', 'n/a')} "
                f"gate={report.get('gate_status', 'n/a')} "
                f"readiness={report.get('readiness', 'n/a')}"
            )
        ]

    if node_name == "draft_markdown":
        return [f"[draft_markdown] briefing={state.get('briefing_path', '')}"]

    if node_name == "organize_artifacts":
        return [f"[organize_artifacts] manifest={state.get('artifact_manifest_path', '')}"]

    return [f"[{node_name}] done"]
