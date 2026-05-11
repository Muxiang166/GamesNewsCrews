"""Graph assembly for the games news pipeline."""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from .nodes import (
    deduplicate_stories,
    design_layout,
    draft_markdown,
    extract_assets,
    extract_claims,
    fetch_documents,
    plan_sources,
    render_assets,
    score_heat,
    search_candidates,
    verify_claims,
)
from .schemas import PipelineState


def build_graph():
    graph = StateGraph(PipelineState)

    graph.add_node("plan_sources", plan_sources)
    graph.add_node("search_candidates", search_candidates)
    graph.add_node("fetch_documents", fetch_documents)
    graph.add_node("extract_assets", extract_assets)
    graph.add_node("deduplicate_stories", deduplicate_stories)
    graph.add_node("extract_claims", extract_claims)
    graph.add_node("verify_claims", verify_claims)
    graph.add_node("score_heat", score_heat)
    graph.add_node("draft_markdown", draft_markdown)
    graph.add_node("design_layout", design_layout)
    graph.add_node("render_assets", render_assets)

    graph.set_entry_point("plan_sources")
    graph.add_edge("plan_sources", "search_candidates")
    graph.add_edge("search_candidates", "fetch_documents")
    graph.add_edge("fetch_documents", "extract_assets")
    graph.add_edge("extract_assets", "deduplicate_stories")
    graph.add_edge("deduplicate_stories", "extract_claims")
    graph.add_edge("extract_claims", "verify_claims")
    graph.add_edge("verify_claims", "score_heat")
    graph.add_edge("score_heat", "draft_markdown")
    graph.add_edge("draft_markdown", "design_layout")
    graph.add_edge("design_layout", "render_assets")
    graph.add_edge("render_assets", END)

    return graph.compile()
