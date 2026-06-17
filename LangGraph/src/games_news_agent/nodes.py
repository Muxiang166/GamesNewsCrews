"""LangGraph node implementations.

The current nodes are intentionally conservative stubs. They establish state
shape, output contracts, and file artifacts before live collectors are wired in.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .candidate_types import split_candidate_lanes
from .artifact_manifest import organize_artifacts_by_stage
from .claim_extraction import build_claims_from_context_packs
from .collector_diagnostics import build_collector_diagnostics_report
from .collectors.registry import collect_from_sources, live_collectible_sources
from .content_quality import build_content_quality_report
from .content_review import build_content_review_markdown, build_human_review_template
from .context_packs import build_context_packs
from .document_fetching import fetch_candidate_documents, synthetic_documents_from_candidates
from .discussion_probe import (
    apply_discussion_probe_report,
    build_discussion_probe_report,
    build_discussion_probe_requests,
)
from .discussion_probe_provider import (
    empty_discussion_probe_provider_report,
    run_discussion_probe_provider,
)
from .deduplication import annotate_story_clusters
from .event_timeline import build_event_timeline
from .evidence_store import build_evidence_chunks
from .historical_context_miner import mine_historical_context
from .evidence_verification import verify_claims_against_evidence
from .editorial_judgment import build_editorial_judgment_requests
from .fetching import HttpFetcher
from .harness import DEFAULT_HARNESS_DIR, load_harness_candidates
from .io import read_json, write_json, write_jsonl
from .llm_verifier import apply_llm_verification_results, build_llm_verification_requests
from .llm_provider import run_llm_json_requests, run_llm_verification_requests
from .markdown_editor import build_briefing_markdown
from .materials import attach_assets_to_stories, build_assets_from_documents, build_material_bundle
from .memory import update_candidate_memory_store
from .platform_writer import build_platform_posts
from .progress import format_live_collection_event
from .ranking import filter_and_rank_candidates
from .retrieval import retrieve_evidence
from .schemas import PipelineState
from .source_health import build_source_health_report
from .source_catalog import load_sources
from .source_dominance import build_source_dominance_audit
from .source_metrics import build_source_theme_counts
from .source_navigation import build_source_navigation_requests, run_source_navigation_requests
from .source_recovery import build_source_recovery_plan
from .source_selection_diagnostics import build_source_selection_diagnostics
from .search_expansion import (
    build_search_expansion_candidates,
    build_search_expansion_requests,
    run_search_expansion_provider,
)
from .search_expansion_llm import (
    apply_query_compression_results,
    apply_result_relevance_results,
    build_query_compression_requests,
    build_result_relevance_requests,
    parse_query_compression_result,
    parse_result_relevance_result,
)
from .selection_backfill import select_backfill_candidates
from .selection_diagnostics import build_selection_stage_diagnostics
from .story_ranking import build_ranked_stories
from .story_sections import build_thematic_candidate_selection, build_thematic_story_selection
from .story_localization import build_story_localization_requests
from .social_heat import (
    build_social_heat_summary,
    default_social_platform_profiles,
    observations_from_discussion_provider_report,
    public_search_first_batch_platforms,
)
from .social_heat_relevance import (
    build_semantic_relevance_requests,
    build_social_heat_relevance_checks,
    build_social_heat_relevance_summary,
)


DISCUSSION_ENRICHMENT_KEYS = {
    "discussion_profile",
    "discussion_score",
    "discussion_level",
    "discussion_probe",
    "discussion_probe_status",
}

SEARCH_EXPANSION_FETCH_TIMEOUT = 8.0


def _append_note(state: PipelineState, note: str) -> list[str]:
    return [*state.get("notes", []), note]


def _output_dir(state: PipelineState) -> Path:
    output_dir = Path(state.get("output_dir", "outputs/langgraph/latest"))
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def plan_sources(state: PipelineState) -> dict[str, Any]:
    sources = load_sources()
    return {
        "sources": [source.model_dump(mode="json") for source in sources],
        "notes": _append_note(state, f"Loaded {len(sources)} configured sources."),
    }


def _run_now(state: PipelineState) -> datetime:
    raw = state.get("started_at")
    if isinstance(raw, str) and raw:
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return parsed.astimezone(timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _sources_by_id(state: PipelineState) -> dict[str, dict[str, Any]]:
    return {str(source["id"]): source for source in state.get("sources", [])}


def _persist_candidate_memory(
    state: PipelineState,
    *,
    candidates: list[dict[str, Any]],
    supplemental_candidates: list[dict[str, Any]],
    seen_at: datetime,
) -> tuple[dict[str, Any], str]:
    memory_path = str(state.get("memory_path") or "").strip()
    if not memory_path:
        return {}, ""
    summary = update_candidate_memory_store(
        memory_path,
        [*candidates, *supplemental_candidates],
        seen_at=seen_at,
    )
    return summary, memory_path


def _print_live_collection_event(event: dict[str, Any]) -> None:
    print(format_live_collection_event(event), flush=True)


def _dry_run_candidates(now: datetime) -> list[dict[str, Any]]:
    examples = [
        {
            "title": "示例线索：微软游戏爆笑梗图在社区刷屏",
            "url": "dry-run://example/microsoft-game-meme",
            "source_id": "xiaoheihe",
            "snippet": "示例：玩家围绕某微软游戏的离谱 BUG 制作梗图，评论和转发快速升高。",
            "query": "微软 游戏 梗图 热门",
            "observed_at": (now - timedelta(hours=2)).isoformat(),
            "heat_signals": {"likes": 5200, "comments": 980, "shares": 1300},
            "tags": ["meme", "player_story", "hot_discussion"],
        },
        {
            "title": "示例线索：索尼 DEI 与亏损相关说法待核查",
            "url": "dry-run://example/sony-dei-loss-rumor",
            "source_id": "weibo",
            "snippet": "示例：社区将索尼业务亏损与 DEI 争议关联传播，需要区分事实与因果推断。",
            "query": "索尼 DEI 亏损 游戏",
            "observed_at": (now - timedelta(hours=5)).isoformat(),
            "heat_signals": {"likes": 2300, "comments": 1600, "reposts": 760},
            "tags": ["controversy", "dei", "loss", "hot_discussion"],
        },
        {
            "title": "示例线索：Nintendo Switch 2 与初代涨价讨论升温",
            "url": "dry-run://example/switch-price-increase",
            "source_id": "gamergen",
            "snippet": "示例：多平台讨论 Switch 2 与初代配件/游戏价格上涨，需要核对官方售价和地区差异。",
            "query": "Switch 2 Switch 涨价",
            "observed_at": (now - timedelta(hours=7)).isoformat(),
            "heat_signals": {"likes": 1200, "comments": 340, "shares": 120},
            "tags": ["price", "market", "hot_discussion"],
        },
        {
            "title": "示例线索：玩家无厘头操作聊天截图被大量转载",
            "url": "dry-run://example/player-chat-screenshot",
            "source_id": "bilibili",
            "snippet": "示例：玩家在游戏内做出反常操作后留下聊天截图，被二创视频和动态大量转发。",
            "query": "游戏 玩家 聊天截图 离谱 操作",
            "observed_at": (now - timedelta(hours=1)).isoformat(),
            "heat_signals": {"views": 180000, "likes": 9000, "comments": 1800, "danmaku": 900},
            "tags": ["player_story", "meme", "hot_discussion"],
        },
        {
            "title": "示例旧线索：Nintendo Switch 2 发布复盘",
            "url": "dry-run://example/old-switch-2-recap",
            "source_id": "ign",
            "snippet": "示例：旧硬件发布复盘，应被 48 小时时间窗口过滤。",
            "query": "Nintendo Switch 2 recap",
            "observed_at": (now - timedelta(hours=96)).isoformat(),
            "heat_signals": {"likes": 50, "comments": 3},
            "tags": ["official_news"],
        },
    ]

    discovered_at = now.isoformat()
    for item in examples:
        item["discovered_at"] = discovered_at
    return examples


def _all_rejected_by_stale_time(rejected: list[dict[str, Any]]) -> bool:
    if not rejected:
        return False
    return all(item.get("reject_reason") == "outside_time_window" for item in rejected)


def search_candidates(state: PipelineState) -> dict[str, Any]:
    if state.get("dry_run", True):
        now = _run_now(state)
        harness_dir = state.get("harness_dir") or str(DEFAULT_HARNESS_DIR)
        raw_candidates = load_harness_candidates(harness_dir)
        if not raw_candidates:
            raw_candidates = _dry_run_candidates(now)
        ranked_candidates, rejected = filter_and_rank_candidates(
            raw_candidates,
            _sources_by_id(state),
            now=now,
            lookback_hours=int(state.get("lookback_hours", 48)),
            memory_records=state.get("memory_records", {}),
        )
        candidates, supplemental_candidates = split_candidate_lanes(ranked_candidates)
        fallback_note = ""
        if raw_candidates and not candidates and _all_rejected_by_stale_time(rejected):
            raw_candidates = _dry_run_candidates(now)
            ranked_candidates, rejected = filter_and_rank_candidates(
                raw_candidates,
                _sources_by_id(state),
                now=now,
                lookback_hours=int(state.get("lookback_hours", 48)),
                memory_records=state.get("memory_records", {}),
            )
            candidates, supplemental_candidates = split_candidate_lanes(ranked_candidates)
            fallback_note = " Dry-run harness stale; regenerated relative example candidates."
        output_dir = _output_dir(state)
        raw_sources_path = output_dir / "raw_sources.jsonl"
        candidates_path = output_dir / "candidates.json"
        supplemental_candidates_path = output_dir / "supplemental_candidates.json"
        rejected_candidates_path = output_dir / "rejected_candidates.json"
        source_theme_counts_path = output_dir / "source_theme_counts.json"
        collector_diagnostics_path = output_dir / "collector_diagnostics.json"
        source_navigation_requests_path = output_dir / "source_navigation_requests.json"
        source_navigation_results_path = output_dir / "source_navigation_results.json"
        source_recovery_plan_path = output_dir / "source_recovery_plan.json"
        source_theme_counts = build_source_theme_counts(
            candidates=candidates,
            supplemental_candidates=supplemental_candidates,
            rejected_candidates=rejected,
            raw_candidates=raw_candidates,
            raw_sources=[],
            sources=state.get("sources", []),
        )
        collector_diagnostics = build_collector_diagnostics_report(
            sources=state.get("sources", []),
            raw_sources=[],
            candidates=[*candidates, *supplemental_candidates],
            rejected=rejected,
            errors=[],
            entry_diagnostics=[],
        )
        source_navigation_requests = build_source_navigation_requests(
            sources=state.get("sources", []),
            collector_diagnostics=collector_diagnostics,
            candidates=[*candidates, *supplemental_candidates],
            raw_sources=[],
            rejected_candidates=rejected,
        )
        source_recovery_plan = build_source_recovery_plan(
            sources=state.get("sources", []),
            collector_diagnostics=collector_diagnostics,
            source_theme_counts=source_theme_counts,
        )
        source_navigation_results: list[dict[str, Any]] = []
        candidate_memory_summary, candidate_memory_path = _persist_candidate_memory(
            state,
            candidates=candidates,
            supplemental_candidates=supplemental_candidates,
            seen_at=now,
        )
        write_jsonl(raw_sources_path, raw_candidates)
        write_json(candidates_path, candidates)
        write_json(supplemental_candidates_path, supplemental_candidates)
        write_json(rejected_candidates_path, rejected)
        write_json(source_theme_counts_path, source_theme_counts)
        write_json(collector_diagnostics_path, collector_diagnostics)
        write_json(source_navigation_requests_path, source_navigation_requests)
        write_json(source_navigation_results_path, source_navigation_results)
        write_json(source_recovery_plan_path, source_recovery_plan)
        return {
            "candidates": candidates,
            "supplemental_candidates": supplemental_candidates,
            "rejected_candidates": rejected,
            "source_theme_counts": source_theme_counts,
            "collector_diagnostics": collector_diagnostics,
            "source_navigation_requests": source_navigation_requests,
            "source_navigation_results": source_navigation_results,
            "source_recovery_plan": source_recovery_plan,
            "raw_sources_path": str(raw_sources_path),
            "candidates_path": str(candidates_path),
            "supplemental_candidates_path": str(supplemental_candidates_path),
            "rejected_candidates_path": str(rejected_candidates_path),
            "source_theme_counts_path": str(source_theme_counts_path),
            "collector_diagnostics_path": str(collector_diagnostics_path),
            "source_navigation_requests_path": str(source_navigation_requests_path),
            "source_navigation_results_path": str(source_navigation_results_path),
            "source_recovery_plan_path": str(source_recovery_plan_path),
            "candidate_memory_summary": candidate_memory_summary,
            "candidate_memory_path": candidate_memory_path,
            "notes": _append_note(
                state,
                (
                    "Dry run: loaded harness/example high-heat game/community leads "
                    "and applied the configured time window."
                    f"{fallback_note}"
                ),
            ),
        }

    now = _run_now(state)
    output_dir = _output_dir(state)
    fetcher = HttpFetcher()
    collection = collect_from_sources(
        state.get("sources", []),
        fetcher=fetcher,
        discovered_at=now,
        query=str(state.get("topic", "games")),
        lookback_hours=int(state.get("lookback_hours", 48)),
        progress_callback=_print_live_collection_event,
    )
    ranked_candidates, rejected = filter_and_rank_candidates(
        collection.candidates,
        _sources_by_id(state),
        now=now,
        lookback_hours=int(state.get("lookback_hours", 48)),
        memory_records=state.get("memory_records", {}),
    )
    candidates, supplemental_candidates = split_candidate_lanes(ranked_candidates)

    raw_sources_path = output_dir / "raw_sources.jsonl"
    candidates_path = output_dir / "candidates.json"
    supplemental_candidates_path = output_dir / "supplemental_candidates.json"
    rejected_candidates_path = output_dir / "rejected_candidates.json"
    collector_errors_path = output_dir / "collector_errors.json"
    source_health_path = output_dir / "source_health.json"
    source_theme_counts_path = output_dir / "source_theme_counts.json"
    collector_diagnostics_path = output_dir / "collector_diagnostics.json"
    source_navigation_requests_path = output_dir / "source_navigation_requests.json"
    source_navigation_results_path = output_dir / "source_navigation_results.json"
    source_recovery_plan_path = output_dir / "source_recovery_plan.json"
    live_sources = live_collectible_sources(state.get("sources", []))
    source_health = build_source_health_report(
        sources=live_sources,
        raw_sources=collection.raw_sources,
        candidates=candidates,
        rejected=rejected,
        errors=collection.errors,
    )
    source_theme_counts = build_source_theme_counts(
        candidates=candidates,
        supplemental_candidates=supplemental_candidates,
        rejected_candidates=rejected,
        raw_candidates=collection.candidates,
        raw_sources=collection.raw_sources,
        sources=state.get("sources", []),
    )
    collector_diagnostics = build_collector_diagnostics_report(
        sources=live_sources,
        raw_sources=collection.raw_sources,
        candidates=[*candidates, *supplemental_candidates],
        rejected=rejected,
        errors=collection.errors,
        entry_diagnostics=collection.diagnostics,
    )
    source_navigation_requests = build_source_navigation_requests(
        sources=live_sources,
        collector_diagnostics=collector_diagnostics,
        candidates=[*candidates, *supplemental_candidates],
        raw_sources=collection.raw_sources,
        rejected_candidates=rejected,
    )
    source_recovery_plan = build_source_recovery_plan(
        sources=live_sources,
        collector_diagnostics=collector_diagnostics,
        source_theme_counts=source_theme_counts,
    )
    source_navigation_results: list[dict[str, Any]] = []
    if state.get("run_llm_source_navigator"):
        source_navigation_results = run_source_navigation_requests(
            source_navigation_requests,
            limit=int(state.get("llm_source_navigation_limit", len(source_navigation_requests))),
        )
    candidate_memory_summary, candidate_memory_path = _persist_candidate_memory(
        state,
        candidates=candidates,
        supplemental_candidates=supplemental_candidates,
        seen_at=now,
    )
    write_jsonl(raw_sources_path, collection.raw_sources)
    write_json(candidates_path, candidates)
    write_json(supplemental_candidates_path, supplemental_candidates)
    write_json(rejected_candidates_path, rejected)
    write_json(collector_errors_path, collection.errors)
    write_json(source_health_path, source_health)
    write_json(source_theme_counts_path, source_theme_counts)
    write_json(collector_diagnostics_path, collector_diagnostics)
    write_json(source_navigation_requests_path, source_navigation_requests)
    write_json(source_navigation_results_path, source_navigation_results)
    write_json(source_recovery_plan_path, source_recovery_plan)

    supported_sources = {item.get("source_id") for item in collection.raw_sources}
    return {
        "candidates": candidates,
        "supplemental_candidates": supplemental_candidates,
        "rejected_candidates": rejected,
        "source_theme_counts": source_theme_counts,
        "collector_diagnostics": collector_diagnostics,
        "source_navigation_requests": source_navigation_requests,
        "source_navigation_results": source_navigation_results,
        "source_recovery_plan": source_recovery_plan,
        "raw_sources_path": str(raw_sources_path),
        "candidates_path": str(candidates_path),
        "supplemental_candidates_path": str(supplemental_candidates_path),
        "rejected_candidates_path": str(rejected_candidates_path),
        "collector_errors_path": str(collector_errors_path),
        "source_health_path": str(source_health_path),
        "source_theme_counts_path": str(source_theme_counts_path),
        "collector_diagnostics_path": str(collector_diagnostics_path),
        "source_navigation_requests_path": str(source_navigation_requests_path),
        "source_navigation_results_path": str(source_navigation_results_path),
        "source_recovery_plan_path": str(source_recovery_plan_path),
        "candidate_memory_summary": candidate_memory_summary,
        "candidate_memory_path": candidate_memory_path,
        "notes": _append_note(
            state,
            (
                f"Live run: collected {len(collection.candidates)} candidates "
                f"from {len(supported_sources)} configured media sources; "
                f"{len(candidates)} remained in the main lane and "
                f"{len(supplemental_candidates)} moved to the supplemental lane; "
                f"{len(collection.errors)} collector errors were written to {collector_errors_path}; "
                f"source health was written to {source_health_path}."
            ),
        ),
    }


def fetch_documents(state: PipelineState) -> dict[str, Any]:
    now = _run_now(state)
    output_dir = _output_dir(state)
    candidates = state.get("candidates", [])
    supplemental_candidates = state.get("supplemental_candidates", [])
    fetch_limit = int(state.get("document_fetch_limit", 8))
    pool_limit = int(state.get("theme_candidate_pool_limit", 100))
    theme_candidate_pool = build_thematic_candidate_selection(
        candidates,
        supplemental_candidates=supplemental_candidates,
        per_section_limit=int(state.get("theme_pool_per_section_limit", 20)),
        total_limit=max(pool_limit, 0),
    )
    fetch_candidates = _select_document_fetch_candidates(
        theme_candidate_pool,
        fetch_limit=max(fetch_limit, 0),
    )
    theme_candidate_pool = _annotate_document_fetch_selection(
        theme_candidate_pool,
        fetch_candidates,
        fetch_limit=max(fetch_limit, 0),
    )
    fetch_candidates = theme_candidate_pool["fetch_candidates"]

    if state.get("dry_run", True):
        documents = synthetic_documents_from_candidates(
            fetch_candidates,
            fetched_at=now,
            limit=len(fetch_candidates),
        )
        document_errors: list[dict[str, Any]] = []
        raw_document_fetches: list[dict[str, Any]] = []
    else:
        fetch_result = fetch_candidate_documents(
            fetch_candidates,
            fetcher=HttpFetcher(),
            fetched_at=now,
            limit=len(fetch_candidates),
        )
        documents = fetch_result.documents
        document_errors = fetch_result.errors
        raw_document_fetches = fetch_result.raw_fetches

    evidence_chunks = build_evidence_chunks(documents)
    context_packs = build_context_packs(fetch_candidates, evidence_chunks)

    theme_candidate_pool_path = output_dir / "theme_candidate_pool.json"
    documents_path = output_dir / "documents.json"
    document_errors_path = output_dir / "document_errors.json"
    raw_document_fetches_path = output_dir / "raw_document_fetches.jsonl"
    evidence_chunks_path = output_dir / "evidence_chunks.json"
    context_packs_path = output_dir / "context_packs.json"
    write_json(theme_candidate_pool_path, theme_candidate_pool)
    write_json(documents_path, documents)
    write_json(document_errors_path, document_errors)
    write_jsonl(raw_document_fetches_path, raw_document_fetches)
    write_json(evidence_chunks_path, evidence_chunks)
    write_json(context_packs_path, context_packs)

    return {
        "documents": documents,
        "document_errors": document_errors,
        "raw_document_fetches_path": str(raw_document_fetches_path),
        "theme_candidate_pool": theme_candidate_pool,
        "theme_candidate_pool_path": str(theme_candidate_pool_path),
        "documents_path": str(documents_path),
        "document_errors_path": str(document_errors_path),
        "evidence_chunks": evidence_chunks,
        "evidence_chunks_path": str(evidence_chunks_path),
        "context_packs": context_packs,
        "context_packs_path": str(context_packs_path),
        "notes": _append_note(
            state,
            (
                f"Fetched/created {len(documents)} documents from "
                f"{len(fetch_candidates)} document-fetch candidates "
                f"inside a {theme_candidate_pool.get('candidate_pool_count', 0)} item theme pool "
                f"({len(candidates)} main + {len(supplemental_candidates)} supplemental seen); "
                f"built {len(evidence_chunks)} evidence chunks and "
                f"{len(context_packs)} context packs."
            ),
        ),
    }


def _select_document_fetch_candidates(
    theme_candidate_pool: dict[str, Any],
    *,
    fetch_limit: int,
) -> list[dict[str, Any]]:
    if fetch_limit <= 0:
        return []

    selected: list[dict[str, Any]] = []
    selected_keys: set[str] = set()

    def add_candidate(candidate: dict[str, Any]) -> bool:
        key = _candidate_identity(candidate)
        if key and key in selected_keys:
            return False
        if key:
            selected_keys.add(key)
        selected.append(candidate)
        return True

    sections = [
        section
        for section in theme_candidate_pool.get("sections", [])
        if isinstance(section, dict) and isinstance(section.get("candidates"), list)
    ]
    if sections:
        for section in sections:
            added_for_section = 0
            for candidate in section.get("candidates", []):
                if not isinstance(candidate, dict):
                    continue
                if add_candidate(candidate):
                    added_for_section += 1
                if added_for_section >= fetch_limit:
                    break

    return selected


def _annotate_document_fetch_selection(
    theme_candidate_pool: dict[str, Any],
    fetch_candidates: list[dict[str, Any]],
    *,
    fetch_limit: int,
) -> dict[str, Any]:
    pool = dict(theme_candidate_pool)
    fetch_keys = {_candidate_identity(candidate) for candidate in fetch_candidates if isinstance(candidate, dict)}

    def annotate_candidates(items: Any) -> list[dict[str, Any]]:
        annotated: list[dict[str, Any]] = []
        if not isinstance(items, list):
            return annotated
        for item in items:
            if not isinstance(item, dict):
                continue
            candidate = dict(item)
            candidate["document_fetch_selected"] = _candidate_identity(candidate) in fetch_keys
            annotated.append(candidate)
        return annotated

    selected_candidates = annotate_candidates(pool.get("selected_candidates", []))
    fetch_selected = [
        candidate for candidate in selected_candidates if candidate.get("document_fetch_selected")
    ]
    selected_keys = {_candidate_identity(candidate) for candidate in selected_candidates}

    sections: list[dict[str, Any]] = []
    for section in pool.get("sections", []):
        if not isinstance(section, dict):
            continue
        next_section = dict(section)
        next_candidates = annotate_candidates(section.get("candidates", []))
        next_section["candidates"] = next_candidates
        next_section["fetch_selected_count"] = sum(
            1 for candidate in next_candidates if candidate.get("document_fetch_selected")
        )
        sections.append(next_section)

    pool["sections"] = sections
    pool["selected_candidates"] = selected_candidates
    pool["fetch_candidates"] = fetch_selected
    pool["fetch_limit"] = fetch_limit
    pool["fetch_limit_scope"] = "per_section"
    pool["fetch_selected_count"] = len(fetch_selected)
    pool["fetch_candidate_urls"] = [_candidate_identity(candidate) for candidate in fetch_selected]
    pool["dropped_before_fetch"] = [
        _candidate_identity(candidate)
        for candidate in selected_candidates
        if _candidate_identity(candidate) in selected_keys
        and _candidate_identity(candidate) not in fetch_keys
    ]
    return pool


def _candidate_url(candidate: dict[str, Any]) -> str:
    return str(candidate.get("url") or "").strip()


def _candidate_identity(candidate: dict[str, Any]) -> str:
    return _candidate_url(candidate) or str(candidate.get("title") or "").strip().lower()


def _merge_supplemental_candidates(
    existing: list[dict[str, Any]],
    additions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in [*existing, *additions]:
        if not isinstance(candidate, dict):
            continue
        key = _candidate_identity(candidate)
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        merged.append(dict(candidate))
    return merged


def expand_search_candidates(state: PipelineState) -> dict[str, Any]:
    """Optionally expand supplemental candidates from low-frequency search observations."""

    output_dir = _output_dir(state)
    now = _run_now(state)
    expansion_limit = int(state.get("search_expansion_limit", 10))
    platform_limit = int(state.get("search_expansion_platform_limit", 2))
    llm_limit = int(state.get("llm_search_expansion_limit", 3))
    expansion_requests = build_search_expansion_requests(
        topic=str(state.get("topic", "games")),
        source_theme_counts=state.get("source_theme_counts", {}),
        candidates=[
            item
            for item in [*state.get("candidates", []), *state.get("supplemental_candidates", [])]
            if isinstance(item, dict)
        ],
        limit=expansion_limit,
    )
    query_compression_requests: list[dict[str, Any]] = []
    query_compression_results: list[dict[str, Any]] = []
    relevance_requests: list[dict[str, Any]] = []
    relevance_results: list[dict[str, Any]] = []
    if state.get("run_llm_search_expansion"):
        query_compression_requests = build_query_compression_requests(
            expansion_requests,
            limit=llm_limit,
        )
        raw_query_results = run_llm_json_requests(
            query_compression_requests,
            limit=llm_limit,
        )
        query_compression_results = [
            parse_query_compression_result(
                str(result.get("request_id") or ""),
                str(result.get("content") or ""),
            )
            if isinstance(result, dict) and result.get("parse_status") == "ok"
            else dict(result)
            for result in raw_query_results
            if isinstance(result, dict)
        ]
        expansion_requests = apply_query_compression_results(
            expansion_requests,
            query_compression_results,
        )
    expansion_observations = {
        "version": "1.0.0",
        "summary": {
            "probe_requests": 0,
            "targets": 0,
            "fetched": 0,
            "ok": 0,
            "blocked": 0,
            "errors": 0,
            "skipped": 0,
            "with_result_signal": 0,
            "platform_counts": {},
        },
        "observations": [],
    }
    if state.get("run_search_expansion"):
        expansion_observations = run_search_expansion_provider(
            expansion_requests,
            fetcher=HttpFetcher(timeout=SEARCH_EXPANSION_FETCH_TIMEOUT),
            request_limit=expansion_limit,
            platform_limit=platform_limit,
        )
    if state.get("run_llm_search_expansion"):
        relevance_requests = build_result_relevance_requests(
            expansion_observations,
            limit=llm_limit,
            lookback_hours=int(state.get("lookback_hours", 48)),
        )
        raw_relevance_results = run_llm_json_requests(
            relevance_requests,
            limit=llm_limit,
        )
        relevance_results = [
            parse_result_relevance_result(
                str(result.get("request_id") or ""),
                str(result.get("content") or ""),
            )
            if isinstance(result, dict) and result.get("parse_status") == "ok"
            else dict(result)
            for result in raw_relevance_results
            if isinstance(result, dict)
        ]
        expansion_observations = apply_result_relevance_results(
            expansion_observations,
            relevance_results,
        )
    expansion_candidates = build_search_expansion_candidates(
        expansion_observations,
        discovered_at=now,
        per_observation_limit=1,
    )
    supplemental_candidates = _merge_supplemental_candidates(
        state.get("supplemental_candidates", []),
        expansion_candidates,
    )

    search_expansion_requests_path = output_dir / "search_expansion_requests.json"
    search_expansion_observations_path = output_dir / "search_expansion_observations.json"
    search_expansion_candidates_path = output_dir / "search_expansion_candidates.json"
    search_expansion_llm_query_requests_path = output_dir / "search_expansion_llm_query_requests.json"
    search_expansion_llm_query_results_path = output_dir / "search_expansion_llm_query_results.json"
    search_expansion_llm_relevance_requests_path = output_dir / "search_expansion_llm_relevance_requests.json"
    search_expansion_llm_relevance_results_path = output_dir / "search_expansion_llm_relevance_results.json"
    supplemental_candidates_path = Path(
        state.get("supplemental_candidates_path") or output_dir / "supplemental_candidates.json"
    )
    write_json(search_expansion_requests_path, expansion_requests)
    write_json(search_expansion_observations_path, expansion_observations)
    write_json(search_expansion_candidates_path, expansion_candidates)
    write_json(search_expansion_llm_query_requests_path, query_compression_requests)
    write_json(search_expansion_llm_query_results_path, query_compression_results)
    write_json(search_expansion_llm_relevance_requests_path, relevance_requests)
    write_json(search_expansion_llm_relevance_results_path, relevance_results)
    write_json(supplemental_candidates_path, supplemental_candidates)

    summary = expansion_observations.get("summary", {})
    return {
        "search_expansion_requests": expansion_requests,
        "search_expansion_requests_path": str(search_expansion_requests_path),
        "search_expansion_observations": expansion_observations,
        "search_expansion_observations_path": str(search_expansion_observations_path),
        "search_expansion_candidates": expansion_candidates,
        "search_expansion_candidates_path": str(search_expansion_candidates_path),
        "search_expansion_llm_query_requests": query_compression_requests,
        "search_expansion_llm_query_requests_path": str(search_expansion_llm_query_requests_path),
        "search_expansion_llm_query_results": query_compression_results,
        "search_expansion_llm_query_results_path": str(search_expansion_llm_query_results_path),
        "search_expansion_llm_relevance_requests": relevance_requests,
        "search_expansion_llm_relevance_requests_path": str(search_expansion_llm_relevance_requests_path),
        "search_expansion_llm_relevance_results": relevance_results,
        "search_expansion_llm_relevance_results_path": str(search_expansion_llm_relevance_results_path),
        "supplemental_candidates": supplemental_candidates,
        "supplemental_candidates_path": str(supplemental_candidates_path),
        "notes": _append_note(
            state,
            (
                f"SearchExpansion prepared {len(expansion_requests)} expansion queries, "
                f"observed {summary.get('targets', 0)} targets, and added "
                f"{len(expansion_candidates)} supplemental leads."
            ),
        ),
    }


def _enriched_by_url(candidates: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        _candidate_url(candidate): candidate
        for candidate in candidates
        if isinstance(candidate, dict) and _candidate_url(candidate)
    }


def _apply_enriched_discussion_to_context_packs(
    context_packs: list[dict[str, Any]],
    enriched: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    updated: list[dict[str, Any]] = []
    for pack in context_packs:
        if not isinstance(pack, dict):
            continue
        item = dict(pack)
        candidate = item.get("candidate", {})
        if isinstance(candidate, dict):
            candidate_update = enriched.get(_candidate_url(candidate))
            if candidate_update:
                next_candidate = dict(candidate)
                for key in DISCUSSION_ENRICHMENT_KEYS:
                    if key in candidate_update:
                        next_candidate[key] = candidate_update[key]
                item["candidate"] = next_candidate
        updated.append(item)
    return updated


def _apply_enriched_discussion_to_theme_pool(
    theme_candidate_pool: dict[str, Any],
    enriched: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    pool = dict(theme_candidate_pool)

    def replace_list(items: Any) -> list[dict[str, Any]]:
        replaced: list[dict[str, Any]] = []
        if not isinstance(items, list):
            return replaced
        for candidate in items:
            if not isinstance(candidate, dict):
                continue
            candidate_update = enriched.get(_candidate_url(candidate))
            next_candidate = dict(candidate)
            if candidate_update:
                for key in DISCUSSION_ENRICHMENT_KEYS:
                    if key in candidate_update:
                        next_candidate[key] = candidate_update[key]
            replaced.append(next_candidate)
        return replaced

    pool["selected_candidates"] = replace_list(pool.get("selected_candidates", []))
    sections: list[dict[str, Any]] = []
    for section in pool.get("sections", []):
        if not isinstance(section, dict):
            continue
        next_section = dict(section)
        next_section["candidates"] = replace_list(section.get("candidates", []))
        sections.append(next_section)
    pool["sections"] = sections
    return pool


def probe_discussions(state: PipelineState) -> dict[str, Any]:
    output_dir = _output_dir(state)
    theme_candidate_pool = state.get("theme_candidate_pool", {})
    if not isinstance(theme_candidate_pool, dict):
        theme_candidate_pool = {}
    probe_candidates = [
        item
        for item in theme_candidate_pool.get("selected_candidates", [])
        if isinstance(item, dict)
    ]
    if not probe_candidates:
        probe_candidates = [
            item
            for item in [*state.get("candidates", []), *state.get("supplemental_candidates", [])]
            if isinstance(item, dict)
        ]
    probe_limit = int(state.get("discussion_probe_limit", 20))
    probe_requests = build_discussion_probe_requests(
        probe_candidates,
        limit=probe_limit,
    )
    probe_observations = empty_discussion_probe_provider_report()
    if state.get("run_discussion_probe_provider"):
        probe_observations = run_discussion_probe_provider(
            probe_requests,
            fetcher=HttpFetcher(timeout=SEARCH_EXPANSION_FETCH_TIMEOUT),
            candidate_limit=probe_limit,
            platform_limit=int(state.get("discussion_probe_provider_platform_limit", 2)),
            timeout=SEARCH_EXPANSION_FETCH_TIMEOUT,
        )
    social_heat_observations = observations_from_discussion_provider_report(probe_observations)
    social_heat_summary = build_social_heat_summary(social_heat_observations)
    social_heat_relevance_checks = build_social_heat_relevance_checks(
        [*state.get("candidates", []), *state.get("supplemental_candidates", []), *probe_candidates],
        social_heat_observations,
    )
    social_heat_relevance_summary = build_social_heat_relevance_summary(social_heat_relevance_checks)
    semantic_relevance_requests = build_semantic_relevance_requests(social_heat_relevance_checks)
    semantic_relevance_results = state.get("semantic_relevance_results", [])
    probe_report = build_discussion_probe_report(
        probe_candidates,
        context_packs=state.get("context_packs", []),
        probe_requests=probe_requests,
        provider_observations=probe_observations,
    )

    candidates = apply_discussion_probe_report(state.get("candidates", []), probe_report)
    supplemental_candidates = apply_discussion_probe_report(
        state.get("supplemental_candidates", []),
        probe_report,
    )
    enriched = _enriched_by_url([*candidates, *supplemental_candidates])
    context_packs = _apply_enriched_discussion_to_context_packs(
        state.get("context_packs", []),
        enriched,
    )
    theme_candidate_pool = _apply_enriched_discussion_to_theme_pool(
        theme_candidate_pool,
        enriched,
    )

    discussion_probe_requests_path = output_dir / "discussion_probe_requests.json"
    discussion_probe_observations_path = output_dir / "discussion_probe_observations.json"
    discussion_probe_report_path = output_dir / "discussion_probe_report.json"
    social_heat_observations_path = output_dir / "social_heat_observations.json"
    social_heat_relevance_checks_path = output_dir / "social_heat_relevance_checks.json"
    semantic_relevance_requests_path = output_dir / "semantic_relevance_requests.json"
    semantic_relevance_results_path = output_dir / "semantic_relevance_results.json"
    write_json(discussion_probe_requests_path, probe_requests)
    write_json(discussion_probe_observations_path, probe_observations)
    write_json(discussion_probe_report_path, probe_report)
    write_json(
        social_heat_observations_path,
        {
            "version": "1.0.0",
            "summary": social_heat_summary,
            "platform_profiles": default_social_platform_profiles(),
            "public_search_first_batch": public_search_first_batch_platforms(),
            "observations": social_heat_observations,
        },
    )
    write_json(
        social_heat_relevance_checks_path,
        {
            "version": "1.0.0",
            "summary": social_heat_relevance_summary,
            "checks": social_heat_relevance_checks,
        },
    )
    write_json(semantic_relevance_requests_path, semantic_relevance_requests)
    write_json(semantic_relevance_results_path, semantic_relevance_results)

    context_packs_path = Path(state.get("context_packs_path") or output_dir / "context_packs.json")
    theme_candidate_pool_path = Path(state.get("theme_candidate_pool_path") or output_dir / "theme_candidate_pool.json")
    candidates_path = Path(state.get("candidates_path") or output_dir / "candidates.json")
    supplemental_candidates_path = Path(
        state.get("supplemental_candidates_path") or output_dir / "supplemental_candidates.json"
    )
    write_json(context_packs_path, context_packs)
    write_json(theme_candidate_pool_path, theme_candidate_pool)
    write_json(candidates_path, candidates)
    write_json(supplemental_candidates_path, supplemental_candidates)

    summary = probe_report.get("summary", {})
    return {
        "discussion_probe_requests": probe_requests,
        "discussion_probe_requests_path": str(discussion_probe_requests_path),
        "discussion_probe_observations": probe_observations,
        "discussion_probe_observations_path": str(discussion_probe_observations_path),
        "discussion_probe_report": probe_report,
        "discussion_probe_report_path": str(discussion_probe_report_path),
        "social_heat_observations": social_heat_observations,
        "social_heat_observations_path": str(social_heat_observations_path),
        "social_heat_summary": social_heat_summary,
        "social_heat_relevance_checks": social_heat_relevance_checks,
        "social_heat_relevance_checks_path": str(social_heat_relevance_checks_path),
        "social_heat_relevance_summary": social_heat_relevance_summary,
        "semantic_relevance_requests": semantic_relevance_requests,
        "semantic_relevance_requests_path": str(semantic_relevance_requests_path),
        "semantic_relevance_results": semantic_relevance_results,
        "semantic_relevance_results_path": str(semantic_relevance_results_path),
        "candidates": candidates,
        "supplemental_candidates": supplemental_candidates,
        "context_packs": context_packs,
        "context_packs_path": str(context_packs_path),
        "theme_candidate_pool": theme_candidate_pool,
        "theme_candidate_pool_path": str(theme_candidate_pool_path),
        "candidates_path": str(candidates_path),
        "supplemental_candidates_path": str(supplemental_candidates_path),
        "notes": _append_note(
            state,
            (
                f"DiscussionProbe checked {summary.get('probed_candidates', 0)} "
                f"theme candidates and found discussion evidence for "
                f"{summary.get('with_discussion_evidence', 0)}."
            ),
        ),
    }


def extract_assets(state: PipelineState) -> dict[str, Any]:
    output_dir = _output_dir(state)
    assets = build_assets_from_documents(state.get("documents", []))
    assets_path = output_dir / "assets.json"
    write_json(assets_path, assets)
    return {
        "assets": assets,
        "assets_path": str(assets_path),
        "notes": _append_note(
            state,
            f"Extracted {len(assets)} article image assets to {assets_path}.",
        ),
    }


def deduplicate_stories(state: PipelineState) -> dict[str, Any]:
    output_dir = _output_dir(state)
    update = annotate_story_clusters(state.get("context_packs", []))
    context_packs = update["context_packs"]
    story_clusters = update["story_clusters"]
    dedup_semantic_review_requests = update.get("dedup_semantic_review_requests", [])
    story_clusters_path = output_dir / "story_clusters.json"
    dedup_semantic_review_requests_path = output_dir / "dedup_semantic_review_requests.json"
    context_packs_path = output_dir / "context_packs.json"
    write_json(story_clusters_path, story_clusters)
    write_json(dedup_semantic_review_requests_path, dedup_semantic_review_requests)
    write_json(context_packs_path, context_packs)
    return {
        "context_packs": context_packs,
        "context_packs_path": str(context_packs_path),
        "story_clusters": story_clusters,
        "story_clusters_path": str(story_clusters_path),
        "dedup_semantic_review_requests": dedup_semantic_review_requests,
        "dedup_semantic_review_requests_path": str(dedup_semantic_review_requests_path),
        "stories": [],
        "notes": _append_note(
            state,
            (
                f"Annotated {len(context_packs)} context packs into {len(story_clusters)} "
                f"story clusters and prepared {len(dedup_semantic_review_requests)} "
                "semantic dedup review requests."
            ),
        ),
    }


def extract_claims(state: PipelineState) -> dict[str, Any]:
    output_dir = _output_dir(state)
    context_packs = state.get("context_packs", [])
    claims = build_claims_from_context_packs(context_packs)
    claims_path = output_dir / "claims.json"
    write_json(claims_path, claims)
    return {
        "claims": claims,
        "claims_path": str(claims_path),
        "stories": state.get("stories", []),
        "notes": _append_note(
            state,
            (
                f"Extracted {len(claims)} candidate-level claims from "
                f"{len(context_packs)} context packs."
            ),
        ),
    }


def verify_claims(state: PipelineState) -> dict[str, Any]:
    output_dir = _output_dir(state)
    claims = state.get("claims", [])
    evidence_chunks = state.get("evidence_chunks", [])
    rule_verifications = verify_claims_against_evidence(claims, evidence_chunks)
    llm_verification_requests = build_llm_verification_requests(
        rule_verifications,
        state.get("context_packs", []),
    )
    llm_results = state.get("llm_verification_results", [])
    if state.get("run_llm_verifier") and not llm_results:
        llm_results = run_llm_verification_requests(
            llm_verification_requests,
            limit=int(state.get("llm_verification_limit", len(llm_verification_requests))),
        )
    if llm_results:
        claim_verifications = apply_llm_verification_results(rule_verifications, llm_results)
        llm_status = "results_applied"
    else:
        claim_verifications = rule_verifications
        llm_status = "requests_prepared"
    claim_verifications_path = output_dir / "claim_verifications.json"
    llm_verification_requests_path = output_dir / "llm_verification_requests.json"
    llm_verification_results_path = output_dir / "llm_verification_results.json"
    write_json(claim_verifications_path, claim_verifications)
    write_json(llm_verification_requests_path, llm_verification_requests)
    write_json(llm_verification_results_path, llm_results)
    return {
        "claim_verifications": claim_verifications,
        "claim_verifications_path": str(claim_verifications_path),
        "llm_verification_requests": llm_verification_requests,
        "llm_verification_requests_path": str(llm_verification_requests_path),
        "llm_verification_results": llm_results,
        "llm_verification_results_path": str(llm_verification_results_path),
        "llm_verification_status": llm_status,
        "claims": claim_verifications,
        "stories": state.get("stories", []),
        "notes": _append_note(
            state,
            (
                f"Verified {len(claim_verifications)} claims with deterministic "
                "evidence-overlap rules and prepared LLM verification requests."
            ),
        ),
    }


def score_heat(state: PipelineState) -> dict[str, Any]:
    output_dir = _output_dir(state)
    story_candidates = build_ranked_stories(state.get("claim_verifications", []))
    theme_sections = build_thematic_story_selection(
        story_candidates,
        per_section_limit=int(state.get("theme_pool_per_section_limit", 20)),
        final_per_section_limit=int(state.get("final_stories_per_section_limit", 10)),
    )
    stories = theme_sections["selected_stories"]
    story_candidates_path = output_dir / "story_candidates.json"
    theme_sections_path = output_dir / "theme_sections.json"
    stories_path = output_dir / "stories.json"
    story_localization_requests_path = output_dir / "story_localization_requests.json"
    editorial_judgment_requests_path = output_dir / "editorial_judgment_requests.json"
    source_selection_diagnostics_path = output_dir / "source_selection_diagnostics.json"
    source_dominance_audit_path = output_dir / "source_dominance_audit.json"
    selection_stage_diagnostics_path = output_dir / "selection_stage_diagnostics.json"
    story_localization_requests = build_story_localization_requests(
        story_candidates,
        theme_candidate_pool=state.get("theme_candidate_pool", {}),
        selected_stories=stories,
    )
    editorial_judgment_requests = build_editorial_judgment_requests(
        story_candidates,
        limit=20,
    )
    source_selection_diagnostics = build_source_selection_diagnostics(
        source_theme_counts=state.get("source_theme_counts", {}),
        theme_candidate_pool=state.get("theme_candidate_pool", {}),
        story_candidates=story_candidates,
        final_stories=stories,
        context_packs=state.get("context_packs", []),
        document_errors=state.get("document_errors", []),
    )
    source_dominance_audit = build_source_dominance_audit(
        {
            **state,
            "story_candidates": story_candidates,
            "stories": stories,
        }
    )
    selection_stage_diagnostics = build_selection_stage_diagnostics(
        source_theme_counts=state.get("source_theme_counts", {}),
        theme_candidate_pool=state.get("theme_candidate_pool", {}),
        context_packs=state.get("context_packs", []),
        claim_verifications=state.get("claim_verifications", []),
        story_candidates=story_candidates,
        theme_sections=theme_sections,
    )
    write_json(story_candidates_path, story_candidates)
    write_json(theme_sections_path, theme_sections)
    write_json(stories_path, stories)
    write_json(story_localization_requests_path, story_localization_requests)
    write_json(editorial_judgment_requests_path, editorial_judgment_requests)
    write_json(source_selection_diagnostics_path, source_selection_diagnostics)
    write_json(source_dominance_audit_path, source_dominance_audit)
    write_json(selection_stage_diagnostics_path, selection_stage_diagnostics)
    return {
        "stories": stories,
        "stories_path": str(stories_path),
        "story_candidates": story_candidates,
        "story_candidates_path": str(story_candidates_path),
        "theme_sections": theme_sections,
        "theme_sections_path": str(theme_sections_path),
        "story_localization_requests": story_localization_requests,
        "story_localization_requests_path": str(story_localization_requests_path),
        "editorial_judgment_requests": editorial_judgment_requests,
        "editorial_judgment_requests_path": str(editorial_judgment_requests_path),
        "source_selection_diagnostics": source_selection_diagnostics,
        "source_selection_diagnostics_path": str(source_selection_diagnostics_path),
        "source_dominance_audit": source_dominance_audit,
        "source_dominance_audit_path": str(source_dominance_audit_path),
        "selection_stage_diagnostics": selection_stage_diagnostics,
        "selection_stage_diagnostics_path": str(selection_stage_diagnostics_path),
        "notes": _append_note(
            state,
            (
                f"Built {len(story_candidates)} story candidates, capped each theme "
                f"section pool at 20, then selected up to 10 final stories per section "
                f"({len(stories)} total)."
            ),
        ),
    }


def plan_selection_backfill(state: PipelineState) -> dict[str, Any]:
    output_dir = _output_dir(state)
    if not state.get("run_selection_backfill"):
        candidates: list[dict[str, Any]] = []
    else:
        candidates = select_backfill_candidates(
            theme_candidate_pool=state.get("theme_candidate_pool", {}),
            selection_stage_diagnostics=state.get("selection_stage_diagnostics", {}),
            min_story_candidates_per_section=int(state.get("selection_backfill_min_stories", 5)),
            max_total_backfill_fetch=int(state.get("selection_backfill_limit", 20)),
        )

    path = output_dir / "selection_backfill_candidates.json"
    write_json(path, candidates)
    return {
        "selection_backfill_candidates": candidates,
        "selection_backfill_candidates_path": str(path),
        "notes": _append_note(state, f"Planned {len(candidates)} selection backfill candidates."),
    }


def write_platform_posts(state: PipelineState) -> dict[str, Any]:
    output_dir = _output_dir(state)
    stories = attach_assets_to_stories(state.get("stories", []), state.get("assets", []))
    platform_posts = build_platform_posts(stories)
    platform_posts_path = output_dir / "platform_posts.json"
    write_json(platform_posts_path, platform_posts)
    return {
        "platform_posts": platform_posts,
        "platform_posts_path": str(platform_posts_path),
        "notes": _append_note(
            state,
            f"Wrote {len(platform_posts)} platform post drafts to {platform_posts_path}.",
        ),
    }


def _load_json_artifact(path: str | None) -> Any:
    if not path:
        return None
    try:
        return read_json(path)
    except (FileNotFoundError, OSError, ValueError):
        return None


def validate_content_quality(state: PipelineState) -> dict[str, Any]:
    output_dir = _output_dir(state)
    quality_state = dict(state)
    if "source_health" not in quality_state:
        source_health = _load_json_artifact(state.get("source_health_path"))
        if source_health is not None:
            quality_state["source_health"] = source_health
    report = build_content_quality_report(quality_state)
    report_path = output_dir / "content_quality_report.json"
    write_json(report_path, report)

    user_notifications: list[dict[str, Any]] = list(state.get("user_notifications", []))
    if report.get("gate_status") == "blocked":
        user_notifications.append({
            "code": "content_quality_gate_blocked",
            "severity": "error",
            "message": (
                f"Content quality gate blocked the pipeline: overall score {report.get('overall_score', 0)}, "
                f"readiness {report.get('readiness', 'blocked')}. "
                "Check the content quality report for stage-level scores and actionable recommendations."
            ),
            "recommendation": "Review issues in content_quality_report.json; fix source health, evidence coverage, "
                              "or claim verification before re-running.",
            "report_path": str(report_path),
            "issues": report.get("issues", []),
        })

    return {
        "content_quality_report": report,
        "content_quality_report_path": str(report_path),
        "user_notifications": user_notifications,
        "notes": _append_note(
            state,
            f"Content quality gate is {report['gate_status']}; wrote report to {report_path}.",
        ),
    }


def write_content_review_pack(state: PipelineState) -> dict[str, Any]:
    output_dir = _output_dir(state)
    content_review_path = output_dir / "content_review.md"
    human_review_template_path = output_dir / "human_review_template.json"
    content_review_path.write_text(
        build_content_review_markdown(state),
        encoding="utf-8",
    )
    write_json(human_review_template_path, build_human_review_template())
    return {
        "content_review_path": str(content_review_path),
        "human_review_template_path": str(human_review_template_path),
        "notes": _append_note(
            state,
            f"Wrote human content review pack to {content_review_path}.",
        ),
    }


def write_material_bundle(state: PipelineState) -> dict[str, Any]:
    output_dir = _output_dir(state)
    material_bundle = build_material_bundle(state)
    material_bundle_path = output_dir / "material_bundle.json"
    write_json(material_bundle_path, material_bundle)
    return {
        "material_bundle": material_bundle,
        "material_bundle_path": str(material_bundle_path),
        "notes": _append_note(
            state,
            f"Wrote material bundle to {material_bundle_path}.",
        ),
    }


def draft_markdown(state: PipelineState) -> dict[str, Any]:
    output_dir = _output_dir(state)
    briefing_path = output_dir / "briefing.md"
    now = datetime.now(timezone.utc).isoformat()
    content = build_briefing_markdown(state, generated_at=now)
    briefing_path.write_text(content, encoding="utf-8")

    return {
        "briefing_path": str(briefing_path),
        "notes": _append_note(state, f"Wrote briefing to {briefing_path}."),
    }


def design_layout(state: PipelineState) -> dict[str, Any]:
    output_dir = _output_dir(state)
    manifest_path = output_dir / "layout_manifest.json"
    manifest = {
        "version": "0.1.0",
        "status": "skeleton",
        "canvases": [
            {
                "platform": "xiaohongshu",
                "size": {"width": 1242, "height": 1660},
                "slides": [],
            },
            {
                "platform": "weibo",
                "size": {"width": 1080, "height": 1920},
                "slides": [],
            },
            {
                "platform": "bilibili",
                "size": {"width": 1920, "height": 1080},
                "slides": [],
            },
        ],
        "missing_assets": [],
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {
        "layout_manifest_path": str(manifest_path),
        "notes": _append_note(state, f"Wrote layout manifest to {manifest_path}."),
    }


def render_assets(state: PipelineState) -> dict[str, Any]:
    output_dir = _output_dir(state)
    render_queue_path = output_dir / "render_queue.json"
    queue = {
        "status": "skeleton",
        "renderer": "html_css_playwright_planned",
        "items": [],
        "layout_manifest_path": state.get("layout_manifest_path"),
    }
    render_queue_path.write_text(
        json.dumps(queue, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {
        "render_queue_path": str(render_queue_path),
        "notes": _append_note(state, f"Wrote render queue to {render_queue_path}."),
    }


def organize_artifacts(state: PipelineState) -> dict[str, Any]:
    output_dir = _output_dir(state)
    update = organize_artifacts_by_stage(output_dir=output_dir, state=state)
    return {
        **update,
        "notes": _append_note(
            state,
            f"Wrote staged artifact manifest to {update['artifact_manifest_path']}.",
        ),
    }


# ---------------------------------------------------------------------------
# New nodes (additive, gated behind feature flags — default OFF)
# ---------------------------------------------------------------------------


def check_source_health(state: PipelineState) -> dict[str, Any]:
    """Re-examine source recovery plan and optionally suggest recovery actions.

    This node runs when ``--run-source-recovery-agent`` is enabled.  It rebuilds
    the source recovery plan from the latest collection diagnostics and writes
    recovery suggestions.
    """
    output_dir = _output_dir(state)
    source_health = _load_json_artifact(state.get("source_health_path"))
    collector_diagnostics = state.get("collector_diagnostics", {})

    source_recovery_plan = build_source_recovery_plan(
        sources=state.get("sources", []),
        collector_diagnostics=collector_diagnostics,
        source_theme_counts=state.get("source_theme_counts", {}),
    )
    source_recovery_plan_path = output_dir / "source_recovery_plan.json"
    write_json(source_recovery_plan_path, source_recovery_plan)

    summary = source_recovery_plan.get("summary", {})
    return {
        "source_recovery_plan": source_recovery_plan,
        "source_recovery_plan_path": str(source_recovery_plan_path),
        "notes": _append_note(
            state,
            f"Source health check: {summary.get('needs_recovery', 0)} sources need recovery, "
            f"{summary.get('healthy_enough', 0)} are healthy.",
        ),
    }


def retrieve_evidence_node(state: PipelineState) -> dict[str, Any]:
    """EVI-003: Retrieve evidence packs for claims using the configured retriever.

    Iterates over claim verifications and calls :func:`retrieve_evidence` with
    the in-memory evidence chunks as the BM25/keyword fallback corpus.
    """
    output_dir = _output_dir(state)
    claims = state.get("claim_verifications", []) or state.get("claims", [])
    evidence_chunks = state.get("evidence_chunks", [])

    retrieved_packs: list[dict[str, Any]] = []
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        result = retrieve_evidence(
            claim,
            chunks=evidence_chunks,
            max_results=5,
        )
        retrieved_packs.append(result)

    retrieved_evidence_path = output_dir / "retrieved_evidence_packs.json"
    write_json(retrieved_evidence_path, retrieved_packs)

    total_packs = sum(len(r.get("packs", [])) for r in retrieved_packs)
    return {
        "retrieved_evidence_packs": retrieved_packs,
        "retrieved_evidence_packs_path": str(retrieved_evidence_path),
        "notes": _append_note(
            state,
            f"EVI-003: Retrieved {total_packs} evidence packs across "
            f"{len(claims)} claims.",
        ),
    }


def build_event_timeline_node(state: PipelineState) -> dict[str, Any]:
    """CLU-003: Build event timelines from story clusters and claims.

    Calls :func:`games_news_agent.event_timeline.build_event_timeline` to
    group story clusters into chronological event timelines with entry labels.
    """
    output_dir = _output_dir(state)
    story_clusters = state.get("story_clusters", [])
    claims = state.get("claims", [])
    context_packs = state.get("context_packs", [])

    event_timelines = build_event_timeline(story_clusters, claims, context_packs)

    event_timelines_path = output_dir / "event_timelines.json"
    write_json(event_timelines_path, event_timelines)

    return {
        "event_timelines": event_timelines,
        "event_timelines_path": str(event_timelines_path),
        "notes": _append_note(
            state,
            f"CLU-003: Built {event_timelines.get('total_timelines', 0)} event timelines "
            f"with {event_timelines.get('total_entries', 0)} total entries.",
        ),
    }


def mine_historical_context_node(state: PipelineState) -> dict[str, Any]:
    """MEM-004: Mine historical context for the final ranked stories.

    Calls :func:`games_news_agent.historical_context_miner.mine_historical_context`
    for each story.  Requires a SQLite event store; gracefully degrades on
    missing or unreadable database files.
    """
    output_dir = _output_dir(state)
    stories = state.get("stories", [])

    # Use a configurable or default event store path.
    event_store_db = (
        Path(state.get("output_dir", "outputs/langgraph/latest")) / "event_store.db"
    )

    historical_contexts: list[dict[str, Any]] = []
    for story in stories:
        if not isinstance(story, dict):
            continue
        try:
            ctx = mine_historical_context(
                story,
                event_store_db=str(event_store_db),
                lookback_years=5,
                max_context_items=5,
            )
        except Exception:
            ctx = {
                "story_title": story.get("title", ""),
                "entities": [],
                "event_types": [],
                "related_events": [],
                "first_since_patterns": [],
                "context_sentences": [],
                "error": "historical_context_mining_failed",
            }
        historical_contexts.append(ctx)

    historical_context_path = output_dir / "historical_context.json"
    write_json(historical_context_path, historical_contexts)

    return {
        "historical_contexts": historical_contexts,
        "historical_context_path": str(historical_context_path),
        "notes": _append_note(
            state,
            f"MEM-004: Mined historical context for {len(stories)} stories.",
        ),
    }
