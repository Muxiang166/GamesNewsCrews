"""Shared state and data models for the games news pipeline."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional, TypedDict

from pydantic import BaseModel, Field, HttpUrl


class SourceKind(str, Enum):
    OFFICIAL = "official"
    MEDIA = "media"
    COMMUNITY = "community"
    SEARCH = "search"


class SourceConfig(BaseModel):
    id: str
    name: str
    kind: SourceKind
    url: HttpUrl
    feed_url: Optional[HttpUrl] = None
    feed_urls: list[HttpUrl] = Field(default_factory=list)
    feed_entries: list[dict[str, Any]] = Field(default_factory=list)
    page_url: Optional[HttpUrl] = None
    page_urls: list[HttpUrl] = Field(default_factory=list)
    page_entries: list[dict[str, Any]] = Field(default_factory=list)
    region: str = "global"
    priority: int = Field(default=50, ge=0, le=100)
    collector: str
    collector_config: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class SearchCandidate(BaseModel):
    title: str
    url: str
    source_id: str
    snippet: str = ""
    query: str = ""
    discovered_at: datetime
    published_at: Optional[datetime] = None
    observed_at: Optional[datetime] = None
    heat_signals: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    memory_key: Optional[str] = None
    related_story_id: Optional[str] = None
    is_current_update: bool = False
    memory_status: Optional[
        Literal[
            "new_story",
            "known_recent_story",
            "known_story_unknown_first_seen",
            "follow_up_update",
            "late_repost",
        ]
    ] = None
    memory_reasons: list[str] = Field(default_factory=list)
    heat_score: float = Field(default=0.0, ge=0.0, le=100.0)
    heat_reasons: list[str] = Field(default_factory=list)


class SourceDocument(BaseModel):
    candidate_url: str
    title: str
    source_id: str
    content: str = ""
    author: Optional[str] = None
    published_at: Optional[datetime] = None
    fetched_at: datetime
    image_urls: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Asset(BaseModel):
    url: Optional[str] = None
    kind: Literal["article_image", "video_cover", "screenshot", "meme", "placeholder"]
    source_url: str
    status: Literal["available", "missing", "manual_fill_required"] = "available"
    note: str = ""


class Claim(BaseModel):
    text: str
    story_id: str
    source_urls: list[str] = Field(default_factory=list)
    check_status: Literal["unchecked", "verified", "likely", "rumor", "conflict", "reject"] = "unchecked"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class Story(BaseModel):
    id: str
    title: str
    summary: str = ""
    category: Literal["official", "hot_discussion", "player_meme", "controversy", "market"] = "official"
    source_urls: list[str] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    assets: list[Asset] = Field(default_factory=list)
    heat_score: float = Field(default=0.0, ge=0.0, le=100.0)
    credibility_score: float = Field(default=0.0, ge=0.0, le=100.0)
    status: Literal["draft", "ready", "needs_review", "rejected"] = "draft"


class PipelineState(TypedDict, total=False):
    topic: str
    dry_run: bool
    harness_dir: str
    lookback_hours: int
    started_at: str
    output_dir: str
    memory_path: str
    sources: list[dict[str, Any]]
    memory_records: dict[str, dict[str, Any]]
    candidate_memory_summary: dict[str, Any]
    candidate_memory_path: str
    candidates: list[dict[str, Any]]
    supplemental_candidates: list[dict[str, Any]]
    rejected_candidates: list[dict[str, Any]]
    candidates_path: str
    supplemental_candidates_path: str
    rejected_candidates_path: str
    collector_errors_path: str
    source_health_path: str
    source_theme_counts: dict[str, Any]
    source_theme_counts_path: str
    collector_diagnostics: dict[str, Any]
    collector_diagnostics_path: str
    source_navigation_requests: list[dict[str, Any]]
    source_navigation_requests_path: str
    source_navigation_results: list[dict[str, Any]]
    source_navigation_results_path: str
    source_recovery_plan: dict[str, Any]
    source_recovery_plan_path: str
    source_recovery_decisions: dict[str, Any]
    source_recovery_decisions_path: str
    source_recovery_suggestions_path: str
    site_parser_contracts: list[dict[str, Any]]
    site_parser_contracts_path: str
    run_search_expansion: bool
    search_expansion_limit: int
    search_expansion_platform_limit: int
    search_expansion_requests: list[dict[str, Any]]
    search_expansion_requests_path: str
    search_expansion_observations: dict[str, Any]
    search_expansion_observations_path: str
    search_expansion_candidates: list[dict[str, Any]]
    search_expansion_candidates_path: str
    raw_sources_path: str
    documents: list[dict[str, Any]]
    document_errors: list[dict[str, Any]]
    document_fetch_limit: int
    run_selection_backfill: bool
    selection_backfill_min_stories: int
    selection_backfill_limit: int
    theme_candidate_pool_limit: int
    theme_pool_per_section_limit: int
    final_stories_per_section_limit: int
    discussion_probe_limit: int
    run_discussion_probe_provider: bool
    discussion_probe_provider_platform_limit: int
    run_source_recovery_agent: bool
    run_story_cluster_review_agent: bool
    discussion_probe_requests: list[dict[str, Any]]
    discussion_probe_requests_path: str
    discussion_probe_observations: dict[str, Any]
    discussion_probe_observations_path: str
    discussion_probe_report: dict[str, Any]
    discussion_probe_report_path: str
    social_heat_observations: list[dict[str, Any]]
    social_heat_observations_path: str
    social_heat_summary: dict[str, Any]
    social_heat_relevance_checks: list[dict[str, Any]]
    social_heat_relevance_checks_path: str
    social_heat_relevance_summary: dict[str, Any]
    semantic_relevance_requests: list[dict[str, Any]]
    semantic_relevance_requests_path: str
    semantic_relevance_results: list[dict[str, Any]]
    semantic_relevance_results_path: str
    raw_document_fetches_path: str
    theme_candidate_pool: dict[str, Any]
    theme_candidate_pool_path: str
    documents_path: str
    document_errors_path: str
    evidence_chunks: list[dict[str, Any]]
    evidence_chunks_path: str
    retrieved_evidence_packs: list[dict[str, Any]]
    retrieved_evidence_packs_path: str
    run_evidence_retrieval: bool
    context_packs: list[dict[str, Any]]
    context_packs_path: str
    story_clusters: list[dict[str, Any]]
    story_clusters_path: str
    story_cluster_review_decisions: list[dict[str, Any]]
    story_cluster_review_decisions_path: str
    event_timelines: dict[str, Any]
    event_timelines_path: str
    dedup_semantic_review_requests: list[dict[str, Any]]
    dedup_semantic_review_requests_path: str
    historical_duplicate_checks: list[dict[str, Any]]
    historical_duplicate_check_path: str
    run_historical_context: bool
    historical_contexts: list[dict[str, Any]]
    historical_context_path: str
    claims: list[dict[str, Any]]
    claims_path: str
    claim_verifications: list[dict[str, Any]]
    claim_verifications_path: str
    llm_verification_requests: list[dict[str, Any]]
    llm_verification_requests_path: str
    llm_verification_results: list[dict[str, Any]]
    llm_verification_results_path: str
    run_llm_verifier: bool
    run_llm_source_navigator: bool
    run_llm_search_expansion: bool
    run_editorial_judgment_agent: bool
    llm_verification_limit: int
    llm_source_navigation_limit: int
    llm_search_expansion_limit: int
    llm_verification_status: str
    search_expansion_llm_query_requests: list[dict[str, Any]]
    search_expansion_llm_query_requests_path: str
    search_expansion_llm_query_results: list[dict[str, Any]]
    search_expansion_llm_query_results_path: str
    search_expansion_llm_relevance_requests: list[dict[str, Any]]
    search_expansion_llm_relevance_requests_path: str
    search_expansion_llm_relevance_results: list[dict[str, Any]]
    search_expansion_llm_relevance_results_path: str
    search_intelligence_path: str
    assets: list[dict[str, Any]]
    assets_path: str
    story_candidates: list[dict[str, Any]]
    story_candidates_path: str
    theme_sections: dict[str, Any]
    theme_sections_path: str
    underfilled_section_diagnostics: dict[str, Any]
    underfilled_section_diagnostics_path: str
    story_localization_requests: list[dict[str, Any]]
    story_localization_requests_path: str
    editorial_judgment_requests: list[dict[str, Any]]
    editorial_judgment_requests_path: str
    source_selection_diagnostics: dict[str, Any]
    source_selection_diagnostics_path: str
    source_dominance_audit: dict[str, Any]
    source_dominance_audit_path: str
    selection_stage_diagnostics: dict[str, Any]
    selection_stage_diagnostics_path: str
    selection_backfill_candidates: list[dict[str, Any]]
    selection_backfill_candidates_path: str
    stories: list[dict[str, Any]]
    stories_path: str
    platform_posts: list[dict[str, Any]]
    platform_posts_path: str
    content_quality_report: dict[str, Any]
    content_quality_report_path: str
    content_quality_pass_threshold: Optional[int]
    content_quality_review_threshold: Optional[int]
    content_review_path: str
    human_review_template_path: str
    material_bundle: dict[str, Any]
    material_bundle_path: str
    briefing_path: str
    layout_manifest_path: str
    render_queue_path: str
    artifact_manifest: dict[str, Any]
    artifact_manifest_path: str
    artifacts_by_stage_path: str
    run_id: str
    run_manifest: dict[str, Any]
    run_manifest_path: str
    agent_contracts_path: str
    run_events_path: str
    user_notifications: list[dict[str, Any]]
    user_notifications_path: str
    user_notification_contract_path: str
    notes: list[str]
