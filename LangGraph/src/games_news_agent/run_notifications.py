"""RUN-006: Warning notification generation for non-blocking failures.

Reads pipeline artifacts (source_health, shadow reports, artifact manifest)
and generates structured warning/needs_user_action notifications so that
issues like source_broken, needs_fill, missing expected artifacts, and
high LLM fallback rates are visible to the user and downstream agents.

These are NOT blocking — the run can still finish.  But they ensure the
user knows what needs attention before the next run.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .user_notification_contract import create_stage_notification


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _source_candidate_count(source: dict[str, Any]) -> int:
    """Return the best available accepted-candidate count for source health."""
    for key in ("candidate_count", "accepted_count", "main_count", "raw_candidate_count"):
        if key in source:
            return _safe_int(source.get(key))
    return 0


def build_source_health_warnings(
    state: dict[str, Any],
    output_dir: str | Path,
) -> list[dict[str, Any]]:
    """RUN-006: Generate warning notifications from source_health.json.

    Reads ``source_health.json`` (via state or file path) and produces one
    warning per source that is ``source_broken`` or ``needs_fill``, plus a
    summary notification when any such sources exist.
    """
    notifications: list[dict[str, Any]] = []
    output_path = Path(output_dir)

    # Prefer in-memory state; fall back to reading from disk
    source_health = state.get("source_health", {})
    if not isinstance(source_health, dict) or not source_health:
        source_health_path = state.get("source_health_path")
        if source_health_path:
            try:
                source_health = json.loads(
                    Path(source_health_path).read_text(encoding="utf-8")
                )
            except (json.JSONDecodeError, FileNotFoundError):
                source_health = {}
        else:
            health_file = output_path / "source_health.json"
            if health_file.exists():
                try:
                    source_health = json.loads(
                        health_file.read_text(encoding="utf-8")
                    )
                except (json.JSONDecodeError, FileNotFoundError):
                    source_health = {}

    if not isinstance(source_health, dict) or not source_health:
        return notifications

    sources = source_health.get("sources", [])
    if not isinstance(sources, list):
        return notifications

    summary = source_health.get("summary", {})
    if not isinstance(summary, dict):
        summary = {}

    needs_fill_count = int(summary.get("needs_fill", 0))
    broken_count = int(summary.get("source_broken", 0))

    # Per-source warnings
    for source in sources:
        if not isinstance(source, dict):
            continue
        source_id = str(source.get("source_id", ""))
        status = str(source.get("status", ""))

        if status == "source_broken":
            error_count = int(source.get("error_count", 0))
            error_summary = str(source.get("error_summary", ""))
            notifications.append(
                create_stage_notification(
                    stage="search_candidates",
                    issue_id="RUN-006",
                    title=f"Source broken: {source_id}",
                    message=(
                        f"Source '{source_id}' is marked source_broken "
                        f"after {error_count} error(s). "
                        f"{error_summary}"
                    ),
                    severity="warning",
                    suggested_actions=[
                        f"Review collector errors for {source_id} in collector_diagnostics.json.",
                        f"Check if {source_id} RSS/listing URL is still reachable.",
                        "Consider temporarily disabling this source or switching to a browser probe.",
                    ],
                    artifact_refs=[
                        "source_health.json",
                        "collector_diagnostics.json",
                        "raw_sources.jsonl",
                    ],
                    details={
                        "source_id": source_id,
                        "status": status,
                        "error_count": error_count,
                        "error_summary": error_summary,
                    },
                )
            )

        elif status == "needs_fill":
            candidate_count = _source_candidate_count(source)
            notifications.append(
                create_stage_notification(
                    stage="search_candidates",
                    issue_id="RUN-006",
                    title=f"Source needs fill: {source_id}",
                    message=(
                        f"Source '{source_id}' produced only {candidate_count} "
                        f"candidates in the lookback window. The theme pool may "
                        f"be underfilled for this source's platform."
                    ),
                    severity="warning",
                    suggested_actions=[
                        f"Increase page depth or add more feed URLs for {source_id}.",
                        f"Check source_theme_counts.json to see which theme sections are affected.",
                        "Consider adding alternative sources for the affected platform.",
                    ],
                    artifact_refs=[
                        "source_health.json",
                        "source_theme_counts.json",
                    ],
                    details={
                        "source_id": source_id,
                        "status": status,
                        "candidate_count": candidate_count,
                    },
                )
            )

    # Summary notification when there are problematic sources
    if broken_count > 0 or needs_fill_count > 0:
        problem_sources = [
            str(s.get("source_id", ""))
            for s in sources
            if isinstance(s, dict) and str(s.get("status", "")) in ("source_broken", "needs_fill")
        ]
        notifications.append(
            create_stage_notification(
                stage="search_candidates",
                issue_id="RUN-006",
                title=(
                    f"Source health warnings: {broken_count} broken, "
                    f"{needs_fill_count} need fill"
                ),
                message=(
                    f"The following sources have non-blocking issues: "
                    f"{', '.join(problem_sources[:10])}. "
                    f"The run continued but content quality may be affected."
                ),
                severity="warning",
                suggested_actions=[
                    "Review source_health.json for detailed per-source diagnostics.",
                    "Run with --run-source-recovery-agent to get automated recovery suggestions.",
                    "Before next run, fix broken sources or add alternatives for underfilled platforms.",
                ],
                artifact_refs=["source_health.json"],
                details={
                    "broken_count": broken_count,
                    "needs_fill_count": needs_fill_count,
                    "problem_sources": problem_sources[:20],
                },
            )
        )

    return notifications


def build_shadow_fallback_warnings(
    shadow_report: dict[str, Any] | None,
    output_dir: str | Path,
    *,
    high_fallback_threshold: float = 0.5,
) -> list[dict[str, Any]]:
    """RUN-006: Generate warnings when LLM shadow fallback rate is high.

    If any shadow task type has a fallback (failure + fallback_used) rate
    exceeding *high_fallback_threshold*, a warning notification is produced.
    """
    notifications: list[dict[str, Any]] = []

    if not isinstance(shadow_report, dict) or not shadow_report:
        return notifications

    per_type = shadow_report.get("per_task_type", {})
    if not isinstance(per_type, dict):
        return notifications

    for task_type, stats in sorted(per_type.items()):
        if not isinstance(stats, dict):
            continue
        total = int(stats.get("total", 0))
        if total == 0:
            continue
        success = int(stats.get("success", 0))
        failure = int(stats.get("failure", 0))
        fallback = int(stats.get("fallback_used", 0))
        problem_count = failure + fallback
        problem_rate = problem_count / total

        if problem_rate >= high_fallback_threshold:
            notifications.append(
                create_stage_notification(
                    stage="llm_shadow",
                    issue_id="RUN-006",
                    title=(
                        f"High LLM shadow fallback rate: {task_type} "
                        f"({problem_count}/{total} = {problem_rate:.0%})"
                    ),
                    message=(
                        f"Shadow task '{task_type}' had {success} success, "
                        f"{failure} failure, {fallback} fallback out of {total} "
                        f"attempts.  Review shadow failures and consider prompt "
                        f"or schema adjustments."
                    ),
                    severity="warning",
                    suggested_actions=[
                        f"Review {task_type}_shadow_failures.json for specific failure reasons.",
                        f"Check {task_type}_shadow_results.json for edge cases.",
                        "Consider adding offline fixtures for the failing input patterns.",
                        "Review prompt_registry.json fallback strategy for this task type.",
                    ],
                    artifact_refs=[
                        f"{task_type}_shadow_results.json",
                        f"{task_type}_shadow_failures.json",
                        "shadow_run_report.json",
                    ],
                    details={
                        "task_type": task_type,
                        "total": total,
                        "success": success,
                        "failure": failure,
                        "fallback_used": fallback,
                        "problem_rate": round(problem_rate, 3),
                    },
                )
            )

    return notifications


def build_missing_artifact_warnings(
    state: dict[str, Any],
    output_dir: str | Path,
) -> list[dict[str, Any]]:
    """RUN-006: Generate warnings for expected but missing artifacts.

    Checks for artifacts that should always exist after a run (content_review.md,
    human_review_template.json) and warns if they are missing.
    """
    notifications: list[dict[str, Any]] = []
    output_path = Path(output_dir)

    # GEN-005: These artifacts should ALWAYS be generated
    expected_artifacts: list[tuple[str, str, str]] = [
        ("content_review_path", "content_review.md", "Human content review markdown"),
        ("human_review_template_path", "human_review_template.json", "Human review template JSON"),
        ("user_notifications_path", "user_notifications.json", "User notifications"),
    ]

    missing: list[str] = []
    for state_key, file_name, description in expected_artifacts:
        path_from_state = state.get(state_key)
        if path_from_state and Path(str(path_from_state)).exists():
            continue
        file_path = output_path / file_name
        if not file_path.exists():
            missing.append(f"{file_name} ({description})")

    if missing:
        notifications.append(
            create_stage_notification(
                stage="organize_artifacts",
                issue_id="RUN-006",
                title=f"Missing expected artifacts: {len(missing)} file(s)",
                message=(
                    f"The following expected artifacts were not generated: "
                    f"{'; '.join(missing)}.  This may indicate a pipeline "
                    f"configuration issue or an early exit."
                ),
                severity="warning",
                suggested_actions=[
                    "Check run_events.jsonl for node failures.",
                    "Verify that the pipeline completed all nodes.",
                    "If content_review.md is missing, check GEN-005: the review pack should always generate when stories exist.",
                ],
                artifact_refs=["run_manifest.json", "run_events.jsonl"],
                details={"missing_artifacts": missing},
            )
        )

    return notifications


def build_all_run_warnings(
    state: dict[str, Any],
    output_dir: str | Path,
    shadow_report: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """RUN-006: Build all non-blocking warning notifications for a run.

    This is the single entry point called from ``run.py`` after the main
    graph and shadow pipeline finish.  It aggregates warnings from:
    - Source health (broken / needs_fill sources)
    - Shadow fallback rate
    - Missing expected artifacts

    Returns a flat list of validated notification dicts.
    """
    notifications: list[dict[str, Any]] = []

    notifications.extend(build_source_health_warnings(state, output_dir))
    notifications.extend(build_shadow_fallback_warnings(shadow_report, output_dir))
    notifications.extend(build_missing_artifact_warnings(state, output_dir))

    return notifications
