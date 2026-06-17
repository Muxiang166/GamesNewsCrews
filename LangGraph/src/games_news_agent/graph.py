"""Graph assembly for the games news pipeline."""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from .nodes import (
    build_event_timeline_node,
    check_source_health,
    deduplicate_stories,
    design_layout,
    draft_markdown,
    expand_search_candidates,
    extract_assets,
    extract_claims,
    fetch_documents,
    mine_historical_context_node,
    plan_selection_backfill,
    plan_sources,
    probe_discussions,
    organize_artifacts,
    render_assets,
    retrieve_evidence_node,
    score_heat,
    search_candidates,
    validate_content_quality,
    verify_claims,
    write_content_review_pack,
    write_material_bundle,
    write_platform_posts,
)
from .schemas import PipelineState


def should_continue_after_quality_gate(state: PipelineState) -> str:
    """GEN-005 / RUN-004: Route after content quality gate.

    ``write_content_review_pack`` now always runs when there is content to
    review — even when the gate is ``blocked`` but stories exist.  The review
    pack (``content_review.md`` + ``human_review_template.json``) is the
    primary deliverable for human evaluation; skipping it hides quality
    problems.

    Returns
    -------
    * ``"continue"`` — proceed to ``write_content_review_pack``.  Always taken
      when stories exist, regardless of gate status or feature flags.
    * ``"end_early"`` — no stories at all *and* gate is blocked; nothing to
      review, stop pipeline (skip layout/render).
    """
    report = state.get("content_quality_report", {})
    gate_status = str(report.get("gate_status", "") or "")
    stories = state.get("stories", [])
    has_stories = isinstance(stories, list) and len(stories) > 0

    # GEN-005: Always generate the review pack when there is content.
    # The review pack is the human's window into what the pipeline produced —
    # hiding it behind a feature flag defeats the purpose of Phase 4.5.
    if has_stories or gate_status in ("pass", "needs_review"):
        return "continue"

    # Truly blocked and no stories — nothing to review.
    return "end_early"


def should_check_source_health(state: PipelineState) -> str:
    """Route to ``check_source_health`` only when the flag is enabled."""
    if state.get("run_source_recovery_agent"):
        return "check"
    return "skip"


def should_retrieve_evidence(state: PipelineState) -> str:
    """EVI-003 gate: route to ``retrieve_evidence_node`` when enabled."""
    if state.get("run_evidence_retrieval"):
        return "retrieve"
    return "skip"


def should_mine_historical_context(state: PipelineState) -> str:
    """MEM-004 gate: route to ``mine_historical_context_node`` when enabled."""
    if state.get("run_historical_context"):
        return "mine"
    return "skip"


def build_graph():
    graph = StateGraph(PipelineState)

    # -- existing nodes -------------------------------------------------------
    graph.add_node("plan_sources", plan_sources)
    graph.add_node("search_candidates", search_candidates)
    graph.add_node("expand_search_candidates", expand_search_candidates)
    graph.add_node("fetch_documents", fetch_documents)
    graph.add_node("probe_discussions", probe_discussions)
    graph.add_node("extract_assets", extract_assets)
    graph.add_node("deduplicate_stories", deduplicate_stories)
    graph.add_node("extract_claims", extract_claims)
    graph.add_node("verify_claims", verify_claims)
    graph.add_node("score_heat", score_heat)
    graph.add_node("plan_selection_backfill", plan_selection_backfill)
    graph.add_node("write_platform_posts", write_platform_posts)
    graph.add_node("validate_content_quality", validate_content_quality)
    graph.add_node("write_content_review_pack", write_content_review_pack)
    graph.add_node("write_material_bundle", write_material_bundle)
    graph.add_node("draft_markdown", draft_markdown)
    graph.add_node("design_layout", design_layout)
    graph.add_node("render_assets", render_assets)
    graph.add_node("organize_artifacts", organize_artifacts)

    # -- new nodes (feature-gated — default OFF) ------------------------------
    graph.add_node("check_source_health", check_source_health)
    graph.add_node("retrieve_evidence", retrieve_evidence_node)
    graph.add_node("build_event_timeline", build_event_timeline_node)
    graph.add_node("mine_historical_context", mine_historical_context_node)

    # -- edges ----------------------------------------------------------------
    graph.set_entry_point("plan_sources")

    # search_candidates → (optional) check_source_health → expand_search_candidates
    graph.add_edge("plan_sources", "search_candidates")
    graph.add_conditional_edges(
        "search_candidates",
        should_check_source_health,
        {"check": "check_source_health", "skip": "expand_search_candidates"},
    )
    graph.add_edge("check_source_health", "expand_search_candidates")

    # expand_search_candidates → … → deduplicate_stories
    graph.add_edge("expand_search_candidates", "fetch_documents")
    graph.add_edge("fetch_documents", "probe_discussions")
    graph.add_edge("probe_discussions", "extract_assets")
    graph.add_edge("extract_assets", "deduplicate_stories")

    # CLU-003: build_event_timeline (always runs) after dedup, before claims
    graph.add_edge("deduplicate_stories", "build_event_timeline")
    graph.add_edge("build_event_timeline", "extract_claims")

    graph.add_edge("extract_claims", "verify_claims")

    # EVI-003: retrieve_evidence (conditional on run_evidence_retrieval)
    graph.add_conditional_edges(
        "verify_claims",
        should_retrieve_evidence,
        {"retrieve": "retrieve_evidence", "skip": "score_heat"},
    )
    graph.add_edge("retrieve_evidence", "score_heat")

    # MEM-004: mine_historical_context (conditional on run_historical_context)
    graph.add_conditional_edges(
        "score_heat",
        should_mine_historical_context,
        {"mine": "mine_historical_context", "skip": "plan_selection_backfill"},
    )
    graph.add_edge("mine_historical_context", "plan_selection_backfill")

    graph.add_edge("plan_selection_backfill", "write_platform_posts")
    graph.add_edge("write_platform_posts", "validate_content_quality")

    # GEN-005 / RUN-004: content_review pack always runs when stories exist
    graph.add_conditional_edges(
        "validate_content_quality",
        should_continue_after_quality_gate,
        {
            "continue": "write_content_review_pack",
            "end_early": END,
        },
    )
    graph.add_edge("write_content_review_pack", "write_material_bundle")
    graph.add_edge("write_material_bundle", "draft_markdown")
    graph.add_edge("draft_markdown", "design_layout")
    graph.add_edge("design_layout", "render_assets")
    graph.add_edge("render_assets", "organize_artifacts")
    graph.add_edge("organize_artifacts", END)

    return graph.compile()
