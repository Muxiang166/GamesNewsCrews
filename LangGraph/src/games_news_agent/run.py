"""CLI entry point for the LangGraph skeleton."""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from dotenv import load_dotenv

from .artifact_manifest import organize_artifacts_by_stage
from .artifact_schema_registry import (
    build_validation_notifications,
    generate_schema_report,
)
from .graph import build_graph
from .llm_shadow import (
    parse_shadow_task_types,
    print_shadow_summary,
    run_shadow_pipeline,
)
from .memory import load_candidate_memory
from .progress import format_progress_update
from .run_notifications import build_all_run_warnings
from .run_trace import RunTraceRecorder
from .schemas import PipelineState


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="games-news-agent",
        description="Run the LangGraph games news intelligence skeleton.",
    )
    parser.add_argument("--topic", default="games", help="Topic seed for the run.")
    parser.add_argument(
        "--lookback-hours",
        type=int,
        default=48,
        help="Hard recency window for future collectors.",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/langgraph/latest",
        help="Directory for generated artifacts.",
    )
    parser.add_argument(
        "--memory-path",
        default="outputs/langgraph/memory/candidate_memory.json",
        help="Persistent candidate memory file used to identify repeats and late reposts.",
    )
    parser.add_argument(
        "--harness-dir",
        default="",
        help="Directory containing offline replay fixtures. Defaults to LangGraph/harness.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without live search/fetch collectors.",
    )
    parser.add_argument(
        "--document-fetch-limit",
        type=int,
        default=8,
        help="Maximum number of theme candidates to fetch for evidence per theme section.",
    )
    parser.add_argument(
        "--run-selection-backfill",
        action="store_true",
        help="Plan second-pass document fetch candidates for underfilled theme sections.",
    )
    parser.add_argument(
        "--selection-backfill-min-stories",
        type=int,
        default=5,
        help="Minimum story candidates per theme before no fetch backfill is planned.",
    )
    parser.add_argument(
        "--selection-backfill-limit",
        type=int,
        default=20,
        help="Maximum total second-pass document fetch candidates to plan.",
    )
    parser.add_argument(
        "--theme-candidate-pool-limit",
        type=int,
        default=100,
        help="Maximum balanced theme candidates to retain before document fetching.",
    )
    parser.add_argument(
        "--theme-pool-per-section-limit",
        type=int,
        default=20,
        help="Max candidates per theme section in pool",
    )
    parser.add_argument(
        "--final-stories-per-section-limit",
        type=int,
        default=10,
        help="Max final stories per theme section",
    )
    parser.add_argument(
        "--run-search-expansion",
        action="store_true",
        help="Run low-frequency public search expansion before document fetching.",
    )
    parser.add_argument(
        "--search-expansion-limit",
        type=int,
        default=10,
        help="Maximum number of theme search-expansion queries to prepare.",
    )
    parser.add_argument(
        "--search-expansion-platform-limit",
        type=int,
        default=2,
        help="Maximum public search targets to fetch per expansion query when enabled.",
    )
    parser.add_argument(
        "--discussion-probe-limit",
        type=int,
        default=20,
        help="Maximum number of theme-prefetch candidates to prepare discussion probes for.",
    )
    parser.add_argument(
        "--run-discussion-probe-provider",
        action="store_true",
        help="Fetch low-frequency public search pages for DiscussionProbeProvider v1 observations.",
    )
    parser.add_argument(
        "--discussion-probe-provider-platform-limit",
        type=int,
        default=2,
        help="Maximum public search targets to fetch per probed candidate when provider v1 is enabled.",
    )
    parser.add_argument(
        "--run-llm-verifier",
        action="store_true",
        help="Call the configured OpenAI-compatible LLM provider for claim verification.",
    )
    parser.add_argument(
        "--run-llm-source-navigator",
        action="store_true",
        help="Call the configured OpenAI-compatible LLM provider to rank observed source URLs.",
    )
    parser.add_argument(
        "--run-llm-search-expansion",
        action="store_true",
        help="Call the configured OpenAI-compatible LLM provider for SearchExpansion query compression and result relevance.",
    )
    parser.add_argument(
        "--run-evidence-retrieval",
        action="store_true",
        help="Run EVI-003 evidence retrieval for claims using the configured retriever.",
    )
    parser.add_argument(
        "--run-historical-context",
        action="store_true",
        help="Run MEM-004 historical context mining for final stories.",
    )
    parser.add_argument(
        "--run-source-recovery-agent",
        action="store_true",
        help="Run source health check and recovery planning after candidate collection.",
    )
    parser.add_argument(
        "--run-story-cluster-review-agent",
        action="store_true",
        help="Run StoryClusterReviewAgent to process dedup semantic review requests (AG-004).",
    )
    parser.add_argument(
        "--run-editorial-judgment-agent",
        action="store_true",
        help="Call LLM for editorial judgment on story candidates (RANK-004).",
    )
    parser.add_argument(
        "--content-quality-pass-threshold",
        type=int,
        default=None,
        help="Override the pass threshold for the content quality gate. "
        "Scores >= this value pass. Defaults to the value in content_quality.yaml (85).",
    )
    parser.add_argument(
        "--content-quality-review-threshold",
        type=int,
        default=None,
        help="Override the needs-review threshold for the content quality gate. "
        "Scores >= this value but below pass go to review. "
        "Defaults to the value in content_quality.yaml (60).",
    )
    parser.add_argument(
        "--llm-verification-limit",
        type=int,
        default=3,
        help="Maximum number of LLM verifier requests to run when --run-llm-verifier is set.",
    )
    parser.add_argument(
        "--llm-source-navigation-limit",
        type=int,
        default=3,
        help="Maximum number of source navigation requests to run when --run-llm-source-navigator is set.",
    )
    parser.add_argument(
        "--llm-search-expansion-limit",
        type=int,
        default=3,
        help="Maximum number of SearchExpansion LLM requests to run for each LLM substage.",
    )
    parser.add_argument(
        "--run-llm-shadow",
        default="",
        help="Comma-separated list of shadow task types to run after the main graph "
        "(query_compression, search_relevance, story_cluster_review, editorial_judgment).",
    )
    parser.add_argument(
        "--llm-shadow-max-samples",
        type=int,
        default=5,
        help="Maximum shadow executions per task type (default 5).",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    load_dotenv(override=False)
    args = parse_args(argv)

    if args.lookback_hours <= 0:
        raise ValueError("--lookback-hours must be positive")
    if args.document_fetch_limit < 0:
        raise ValueError("--document-fetch-limit cannot be negative")
    if args.selection_backfill_min_stories < 0:
        raise ValueError("--selection-backfill-min-stories cannot be negative")
    if args.selection_backfill_limit < 0:
        raise ValueError("--selection-backfill-limit cannot be negative")
    if args.theme_candidate_pool_limit < 0:
        raise ValueError("--theme-candidate-pool-limit cannot be negative")
    if args.theme_pool_per_section_limit < 0:
        raise ValueError("--theme-pool-per-section-limit cannot be negative")
    if args.final_stories_per_section_limit < 0:
        raise ValueError("--final-stories-per-section-limit cannot be negative")
    if args.search_expansion_limit < 0:
        raise ValueError("--search-expansion-limit cannot be negative")
    if args.search_expansion_platform_limit < 0:
        raise ValueError("--search-expansion-platform-limit cannot be negative")
    if args.discussion_probe_limit < 0:
        raise ValueError("--discussion-probe-limit cannot be negative")
    if args.discussion_probe_provider_platform_limit < 0:
        raise ValueError("--discussion-probe-provider-platform-limit cannot be negative")
    if args.llm_verification_limit < 0:
        raise ValueError("--llm-verification-limit cannot be negative")
    if args.llm_source_navigation_limit < 0:
        raise ValueError("--llm-source-navigation-limit cannot be negative")
    if args.llm_search_expansion_limit < 0:
        raise ValueError("--llm-search-expansion-limit cannot be negative")
    if args.content_quality_pass_threshold is not None and args.content_quality_pass_threshold < 0:
        raise ValueError("--content-quality-pass-threshold cannot be negative")
    if args.content_quality_review_threshold is not None and args.content_quality_review_threshold < 0:
        raise ValueError("--content-quality-review-threshold cannot be negative")
    if (
        args.content_quality_pass_threshold is not None
        and args.content_quality_review_threshold is not None
        and args.content_quality_pass_threshold <= args.content_quality_review_threshold
    ):
        raise ValueError(
            "--content-quality-pass-threshold must be greater than "
            "--content-quality-review-threshold"
        )

    # ---- CRIT-2: LLM dry-run token warning ----
    _LLM_FLAGS = [
        ("--run-llm-verifier", args.run_llm_verifier),
        ("--run-llm-source-navigator", args.run_llm_source_navigator),
        ("--run-llm-search-expansion", args.run_llm_search_expansion),
        ("--run-editorial-judgment-agent", args.run_editorial_judgment_agent),
    ]
    _active_llm_flags = [flag for flag, enabled in _LLM_FLAGS if enabled]
    if args.dry_run and _active_llm_flags:
        print(
            "[warn] --dry-run is set, but the following LLM flags are also enabled: "
            f"{', '.join(_active_llm_flags)}."
        )
        print(
            "[warn] LLM calls will still be made and may consume tokens even in dry-run mode."
        )
        print("[warn] Press Ctrl+C within 3 seconds to cancel...")
        try:
            time.sleep(3)
        except KeyboardInterrupt:
            print("\n[cancel] Run aborted by user.")
            return 1

    Path(args.output_dir).mkdir(parents=True, exist_ok=True)

    initial_state: PipelineState = {
        "topic": args.topic,
        "dry_run": args.dry_run,
        "harness_dir": args.harness_dir,
        "lookback_hours": args.lookback_hours,
        "document_fetch_limit": args.document_fetch_limit,
        "run_selection_backfill": args.run_selection_backfill,
        "selection_backfill_min_stories": args.selection_backfill_min_stories,
        "selection_backfill_limit": args.selection_backfill_limit,
        "theme_candidate_pool_limit": args.theme_candidate_pool_limit,
        "theme_pool_per_section_limit": args.theme_pool_per_section_limit,
        "final_stories_per_section_limit": args.final_stories_per_section_limit,
        "run_search_expansion": args.run_search_expansion,
        "search_expansion_limit": args.search_expansion_limit,
        "search_expansion_platform_limit": args.search_expansion_platform_limit,
        "discussion_probe_limit": args.discussion_probe_limit,
        "run_discussion_probe_provider": args.run_discussion_probe_provider,
        "discussion_probe_provider_platform_limit": args.discussion_probe_provider_platform_limit,
        "run_llm_verifier": args.run_llm_verifier,
        "run_llm_source_navigator": args.run_llm_source_navigator,
        "run_llm_search_expansion": args.run_llm_search_expansion,
        "run_evidence_retrieval": args.run_evidence_retrieval,
        "run_historical_context": args.run_historical_context,
        "run_source_recovery_agent": args.run_source_recovery_agent,
        "run_story_cluster_review_agent": args.run_story_cluster_review_agent,
        "run_editorial_judgment_agent": args.run_editorial_judgment_agent,
        "llm_verification_limit": args.llm_verification_limit,
        "llm_source_navigation_limit": args.llm_source_navigation_limit,
        "llm_search_expansion_limit": args.llm_search_expansion_limit,
        "content_quality_pass_threshold": args.content_quality_pass_threshold,
        "content_quality_review_threshold": args.content_quality_review_threshold,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "output_dir": args.output_dir,
        "memory_path": args.memory_path,
        "memory_records": load_candidate_memory(args.memory_path),
        "notes": [],
    }

    app = build_graph()
    final_state = dict(initial_state)
    trace = RunTraceRecorder(output_dir=args.output_dir, initial_state=initial_state)
    trace.record_run_started()

    print(
        "[start] "
        f"topic={args.topic} lookback_hours={args.lookback_hours} "
        f"dry_run={args.dry_run} output_dir={args.output_dir} "
        f"memory_path={args.memory_path}"
    )
    try:
        for event in app.stream(initial_state, stream_mode="updates"):
            for node_name, update in event.items():
                if isinstance(update, dict):
                    final_state.update(update)
                    trace.record_node_finished(node_name, update)
                for line in format_progress_update(node_name, final_state):
                    print(line)
    except Exception as exc:
        trace.record_exception(exc)
        final_state.update(trace.write(final_state=final_state, status="failed"))
        final_state.update(
            organize_artifacts_by_stage(output_dir=args.output_dir, state=final_state)
        )
        schema_report = generate_schema_report(args.output_dir)
        schema_notifications = build_validation_notifications(schema_report)
        for notif in schema_notifications:
            trace.add_notification(notif)
        final_state["schema_validation_report"] = schema_report
        final_state["schema_validation_report_path"] = str(
            Path(args.output_dir) / "schema_validation_report.json"
        )
        final_state.update(trace.write(final_state=final_state, status="failed"))
        final_state.update(
            organize_artifacts_by_stage(output_dir=args.output_dir, state=final_state)
        )
        raise

    final_state.update(trace.write(final_state=final_state, status="success"))
    final_state.update(
        organize_artifacts_by_stage(output_dir=args.output_dir, state=final_state)
    )
    schema_report = generate_schema_report(args.output_dir)
    schema_notifications = build_validation_notifications(schema_report)
    for notif in schema_notifications:
        trace.add_notification(notif)
    final_state["schema_validation_report"] = schema_report
    final_state["schema_validation_report_path"] = str(
        Path(args.output_dir) / "schema_validation_report.json"
    )
    final_state.update(trace.write(final_state=final_state, status="success"))
    final_state.update(
        organize_artifacts_by_stage(output_dir=args.output_dir, state=final_state)
    )

    # ---- LLM Shadow Pipeline ----
    shadow_report = None
    shadow_task_types = parse_shadow_task_types(args.run_llm_shadow)
    if shadow_task_types:
        print(
            f"[shadow] Running shadow tasks: {', '.join(shadow_task_types)} "
            f"(max {args.llm_shadow_max_samples} samples per type)"
        )
        try:
            shadow_report = run_shadow_pipeline(
                task_types=shadow_task_types,
                input_dir=args.output_dir,
                output_dir=args.output_dir,
                max_samples_per_type=args.llm_shadow_max_samples,
            )
            print_shadow_summary(shadow_report)
        except Exception as exc:
            print(f"[shadow:error] Shadow pipeline failed: {exc}")

    # ---- RUN-006: Non-blocking warning notifications ----
    run_warnings = build_all_run_warnings(
        state=final_state,
        output_dir=args.output_dir,
        shadow_report=shadow_report,
    )
    for notif in run_warnings:
        trace.add_notification(notif)
    if run_warnings:
        # Re-write notifications to include the new warnings
        final_state.update(
            trace.write(final_state=final_state, status="success")
        )
        final_state.update(
            organize_artifacts_by_stage(
                output_dir=args.output_dir, state=final_state
            )
        )

    print("LangGraph skeleton run finished.")
    print(f"Run manifest: {final_state.get('run_manifest_path')}")
    print(f"Run events: {final_state.get('run_events_path')}")
    print(f"User notifications: {final_state.get('user_notifications_path')}")
    print(f"Briefing: {final_state.get('briefing_path')}")
    print(f"Layout manifest: {final_state.get('layout_manifest_path')}")
    print(f"Render queue: {final_state.get('render_queue_path')}")
    print(f"Artifact manifest: {final_state.get('artifact_manifest_path')}")
    print(f"Schema validation report: {final_state.get('schema_validation_report_path')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
