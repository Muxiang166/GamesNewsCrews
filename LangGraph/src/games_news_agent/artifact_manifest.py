"""Organize pipeline artifacts into stage folders for review."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from .io import write_json


ARTIFACT_STAGES: list[dict[str, Any]] = [
    {
        "id": "run_trace",
        "label": "Run trace and user notifications",
        "artifacts": [
            ("run_manifest_path", "run_manifest.json"),
            ("run_events_path", "run_events.jsonl"),
            ("user_notifications_path", "user_notifications.json"),
        ],
    },
    {
        "id": "source_collection",
        "label": "Source collection and candidate filtering",
        "artifacts": [
            ("raw_sources_path", "raw_sources.jsonl"),
            ("source_health_path", "source_health.json"),
            ("source_theme_counts_path", "source_theme_counts.json"),
            ("collector_diagnostics_path", "collector_diagnostics.json"),
            ("collector_errors_path", "collector_errors.json"),
            ("source_navigation_requests_path", "source_navigation_requests.json"),
            ("source_navigation_results_path", "source_navigation_results.json"),
            ("source_recovery_plan_path", "source_recovery_plan.json"),
            ("candidates_path", "candidates.json"),
            ("supplemental_candidates_path", "supplemental_candidates.json"),
            ("rejected_candidates_path", "rejected_candidates.json"),
        ],
    },
    {
        "id": "search_expansion",
        "label": "Search expansion",
        "artifacts": [
            ("search_expansion_requests_path", "search_expansion_requests.json"),
            ("search_expansion_observations_path", "search_expansion_observations.json"),
            ("search_expansion_candidates_path", "search_expansion_candidates.json"),
            ("search_expansion_llm_query_requests_path", "search_expansion_llm_query_requests.json"),
            ("search_expansion_llm_query_results_path", "search_expansion_llm_query_results.json"),
            ("search_expansion_llm_relevance_requests_path", "search_expansion_llm_relevance_requests.json"),
            ("search_expansion_llm_relevance_results_path", "search_expansion_llm_relevance_results.json"),
        ],
    },
    {
        "id": "evidence_fetch",
        "label": "Document fetch and evidence packs",
        "artifacts": [
            ("theme_candidate_pool_path", "theme_candidate_pool.json"),
            ("documents_path", "documents.json"),
            ("document_errors_path", "document_errors.json"),
            ("raw_document_fetches_path", "raw_document_fetches.jsonl"),
            ("evidence_chunks_path", "evidence_chunks.json"),
            ("context_packs_path", "context_packs.json"),
        ],
    },
    {
        "id": "discussion_heat",
        "label": "Discussion and social heat",
        "artifacts": [
            ("discussion_probe_requests_path", "discussion_probe_requests.json"),
            ("discussion_probe_observations_path", "discussion_probe_observations.json"),
            ("discussion_probe_report_path", "discussion_probe_report.json"),
            ("social_heat_observations_path", "social_heat_observations.json"),
            ("social_heat_relevance_checks_path", "social_heat_relevance_checks.json"),
            ("semantic_relevance_requests_path", "semantic_relevance_requests.json"),
            ("semantic_relevance_results_path", "semantic_relevance_results.json"),
        ],
    },
    {
        "id": "asset_and_dedup",
        "label": "Assets and story clustering",
        "artifacts": [
            ("assets_path", "assets.json"),
            ("story_clusters_path", "story_clusters.json"),
            ("dedup_semantic_review_requests_path", "dedup_semantic_review_requests.json"),
        ],
    },
    {
        "id": "claim_verification",
        "label": "Claim extraction and verification",
        "artifacts": [
            ("claims_path", "claims.json"),
            ("claim_verifications_path", "claim_verifications.json"),
            ("llm_verification_requests_path", "llm_verification_requests.json"),
            ("llm_verification_results_path", "llm_verification_results.json"),
        ],
    },
    {
        "id": "story_selection",
        "label": "Story selection and diagnostics",
        "artifacts": [
            ("story_candidates_path", "story_candidates.json"),
            ("theme_sections_path", "theme_sections.json"),
            ("stories_path", "stories.json"),
            ("story_localization_requests_path", "story_localization_requests.json"),
            ("editorial_judgment_requests_path", "editorial_judgment_requests.json"),
            ("source_selection_diagnostics_path", "source_selection_diagnostics.json"),
            ("source_dominance_audit_path", "source_dominance_audit.json"),
            ("selection_stage_diagnostics_path", "selection_stage_diagnostics.json"),
            ("selection_backfill_candidates_path", "selection_backfill_candidates.json"),
        ],
    },
    {
        "id": "platform_content",
        "label": "Platform content and human review",
        "artifacts": [
            ("platform_posts_path", "platform_posts.json"),
            ("content_quality_report_path", "content_quality_report.json"),
            ("content_review_path", "content_review.md"),
            ("human_review_template_path", "human_review_template.json"),
            ("material_bundle_path", "material_bundle.json"),
            ("briefing_path", "briefing.md"),
        ],
    },
    {
        "id": "layout_render",
        "label": "Deferred layout and render placeholders",
        "artifacts": [
            ("layout_manifest_path", "layout_manifest.json"),
            ("render_queue_path", "render_queue.json"),
        ],
    },
]


def _source_path(output_dir: Path, state: dict[str, Any], key: str, filename: str) -> Path:
    value = str(state.get(key) or "").strip()
    return Path(value) if value else output_dir / filename


def organize_artifacts_by_stage(
    *,
    output_dir: str | Path,
    state: dict[str, Any],
) -> dict[str, Any]:
    """Copy known artifacts into stage folders and write a manifest.

    Root-level artifact paths remain the source of truth for now. The staged
    folder is a review-friendly mirror that can later become the primary layout.
    """

    root = Path(output_dir)
    staged_root = root / "artifacts_by_stage"
    manifest_path = root / "artifact_manifest.json"
    stages: list[dict[str, Any]] = []
    copied_files = 0
    missing_files = 0

    for stage in ARTIFACT_STAGES:
        stage_dir = staged_root / str(stage["id"])
        files: list[dict[str, Any]] = []
        for key, filename in stage["artifacts"]:
            source = _source_path(root, state, key, filename)
            target = stage_dir / filename
            exists = source.exists()
            size = source.stat().st_size if exists else 0
            entry = {
                "artifact_key": key,
                "filename": filename,
                "source_path": str(source),
                "staged_path": str(target),
                "exists": exists,
                "size_bytes": size,
            }
            if exists:
                target.parent.mkdir(parents=True, exist_ok=True)
                if source.resolve() != target.resolve():
                    shutil.copy2(source, target)
                copied_files += 1
            else:
                missing_files += 1
            files.append(entry)
        stages.append(
            {
                "id": stage["id"],
                "label": stage["label"],
                "directory": str(stage_dir),
                "files": files,
            }
        )

    manifest = {
        "version": "0.1.0",
        "root_output_dir": str(root),
        "staged_output_dir": str(staged_root),
        "summary": {
            "stage_count": len(stages),
            "copied_files": copied_files,
            "missing_files": missing_files,
        },
        "stages": stages,
    }
    write_json(manifest_path, manifest)
    return {
        "artifact_manifest": manifest,
        "artifact_manifest_path": str(manifest_path),
        "artifacts_by_stage_path": str(staged_root),
    }
