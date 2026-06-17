"""Run trace and user notification artifacts for replayable executions."""

from __future__ import annotations

import hashlib
import json
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .artifact_manifest import ARTIFACT_STAGES
from .io import write_json, write_jsonl


TRACE_SCHEMA_VERSION = "0.1.0"

SCHEMA_VERSIONS: dict[str, str] = {
    "run_manifest_path": "0.1.0",
    "run_events_path": "0.1.0",
    "user_notifications_path": "0.1.0",
    "raw_sources_path": "0.1.0",
    "source_health_path": "0.1.0",
    "source_theme_counts_path": "0.1.0",
    "collector_diagnostics_path": "0.1.0",
    "collector_errors_path": "0.1.0",
    "source_navigation_requests_path": "0.1.0",
    "source_navigation_results_path": "0.1.0",
    "source_recovery_plan_path": "0.1.0",
    "candidates_path": "0.1.0",
    "supplemental_candidates_path": "0.1.0",
    "rejected_candidates_path": "0.1.0",
    "search_expansion_requests_path": "0.1.0",
    "search_expansion_observations_path": "0.1.0",
    "search_expansion_candidates_path": "0.1.0",
    "search_expansion_llm_query_requests_path": "0.1.0",
    "search_expansion_llm_query_results_path": "0.1.0",
    "search_expansion_llm_relevance_requests_path": "0.1.0",
    "search_expansion_llm_relevance_results_path": "0.1.0",
    "theme_candidate_pool_path": "0.1.0",
    "documents_path": "0.1.0",
    "document_errors_path": "0.1.0",
    "raw_document_fetches_path": "0.1.0",
    "evidence_chunks_path": "0.1.0",
    "context_packs_path": "0.1.0",
    "discussion_probe_requests_path": "0.1.0",
    "discussion_probe_observations_path": "0.1.0",
    "discussion_probe_report_path": "0.1.0",
    "social_heat_observations_path": "0.1.0",
    "social_heat_relevance_checks_path": "0.1.0",
    "semantic_relevance_requests_path": "0.1.0",
    "semantic_relevance_results_path": "0.1.0",
    "assets_path": "0.1.0",
    "story_clusters_path": "0.1.0",
    "dedup_semantic_review_requests_path": "0.1.0",
    "claims_path": "0.1.0",
    "claim_verifications_path": "0.1.0",
    "llm_verification_requests_path": "0.1.0",
    "llm_verification_results_path": "0.1.0",
    "story_candidates_path": "0.1.0",
    "theme_sections_path": "0.1.0",
    "stories_path": "0.1.0",
    "story_localization_requests_path": "0.1.0",
    "editorial_judgment_requests_path": "0.1.0",
    "source_selection_diagnostics_path": "0.1.0",
    "source_dominance_audit_path": "0.1.0",
    "selection_stage_diagnostics_path": "0.1.0",
    "selection_backfill_candidates_path": "0.1.0",
    "platform_posts_path": "0.1.0",
    "content_quality_report_path": "0.1.0",
    "content_review_path": "0.1.0",
    "human_review_template_path": "0.1.0",
    "material_bundle_path": "0.1.0",
    "briefing_path": "0.1.0",
    "layout_manifest_path": "0.1.0",
    "render_queue_path": "0.1.0",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stage_by_artifact_key() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for stage in ARTIFACT_STAGES:
        stage_id = str(stage.get("id") or "")
        for key, _filename in stage.get("artifacts", []):
            mapping[str(key)] = stage_id
    return mapping


def _safe_parameters(state: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "topic",
        "dry_run",
        "lookback_hours",
        "document_fetch_limit",
        "theme_candidate_pool_limit",
        "run_search_expansion",
        "run_discussion_probe_provider",
        "run_llm_verifier",
        "run_llm_source_navigator",
        "run_llm_search_expansion",
        "memory_path",
        "harness_dir",
    ]
    return {key: state[key] for key in keys if key in state}


def _count_summary(value: Any) -> dict[str, Any]:
    if isinstance(value, list):
        return {"type": "list", "count": len(value)}
    if isinstance(value, dict):
        return {"type": "dict", "count": len(value), "keys": sorted(value.keys())[:20]}
    return {"type": type(value).__name__}


def _record_count(value: Any) -> int | None:
    """Return len() for lists and dicts; None for other types."""
    if isinstance(value, (list, dict)):
        return len(value)
    return None


def _file_record_count(path: Path) -> int | None:
    """Read a JSON artifact file and return its record count, or None."""
    if not path.exists() or not path.is_file():
        return None
    if path.suffix != ".json":
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return _record_count(data)
    except Exception:
        return None


def build_user_notification(
    *,
    severity: str,
    stage: str,
    issue_id: str,
    title: str,
    message: str,
    details: dict[str, Any] | None = None,
    suggested_actions: list[str] | None = None,
    artifact_refs: list[str] | None = None,
    status: str = "open",
) -> dict[str, Any]:
    """Build a UI-ready notification for issues automation cannot resolve."""

    return {
        "notification_id": f"notif_{uuid.uuid4().hex[:12]}",
        "severity": severity,
        "stage": stage,
        "issue_id": issue_id,
        "title": title,
        "message": message,
        "details": details or {},
        "suggested_actions": suggested_actions or [],
        "artifact_refs": artifact_refs or [],
        "created_at": _utc_now(),
        "status": status,
    }


class RunTraceRecorder:
    """Collect lightweight run events and write replay-friendly artifacts."""

    def __init__(self, *, output_dir: str | Path, initial_state: dict[str, Any]) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.run_id = f"run_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}_{uuid.uuid4().hex[:8]}"
        self.started_at = _utc_now()
        self.initial_state = dict(initial_state)
        self.events: list[dict[str, Any]] = []
        self.notifications: list[dict[str, Any]] = []
        self._finished = False

    @property
    def run_manifest_path(self) -> Path:
        return self.output_dir / "run_manifest.json"

    @property
    def run_events_path(self) -> Path:
        return self.output_dir / "run_events.jsonl"

    @property
    def user_notifications_path(self) -> Path:
        return self.output_dir / "user_notifications.json"

    def record_event(
        self,
        event_type: str,
        *,
        node_name: str = "",
        stage: str = "",
        details: dict[str, Any] | None = None,
    ) -> None:
        self.events.append(
            {
                "event_id": f"evt_{len(self.events) + 1:05d}",
                "run_id": self.run_id,
                "event_type": event_type,
                "node_name": node_name,
                "stage": stage,
                "created_at": _utc_now(),
                "details": details or {},
            }
        )

    def record_run_started(self) -> None:
        self.record_event(
            "run_started",
            details={
                "parameters": _safe_parameters(self.initial_state),
                "output_dir": str(self.output_dir),
            },
        )

    def record_node_finished(self, node_name: str, update: dict[str, Any]) -> None:
        self.record_event(
            "node_finished",
            node_name=node_name,
            details={
                "update_keys": sorted(update.keys()),
                "value_summaries": {
                    key: _count_summary(value)
                    for key, value in update.items()
                    if not str(key).endswith("_path")
                },
            },
        )
        for key, value in update.items():
            if str(key).endswith("_path") and str(value).strip():
                path = Path(str(value))
                artifact_key = str(key)
                data_key = artifact_key[:-5]  # strip "_path" suffix
                data_value = update.get(data_key)
                self.record_event(
                    "artifact_written",
                    node_name=node_name,
                    stage=_stage_by_artifact_key().get(artifact_key, "unknown"),
                    details={
                        "artifact_key": artifact_key,
                        "path": str(path),
                        "exists": path.exists(),
                        "size_bytes": path.stat().st_size if path.exists() else 0,
                        "schema_version": SCHEMA_VERSIONS.get(artifact_key, "0.1.0"),
                        "record_count": _record_count(data_value) if data_value is not None else _file_record_count(path),
                    },
                )

    def add_notification(self, notification: dict[str, Any]) -> None:
        self.notifications.append(notification)
        self.record_event(
            "user_notification_created",
            stage=str(notification.get("stage") or ""),
            details={
                "notification_id": notification.get("notification_id"),
                "severity": notification.get("severity"),
                "issue_id": notification.get("issue_id"),
                "title": notification.get("title"),
            },
        )

    def record_exception(
        self,
        exc: BaseException,
        *,
        stage: str = "runtime",
        issue_id: str = "RUN-003",
    ) -> None:
        error_type = type(exc).__name__
        message = str(exc)
        self.record_event(
            "run_exception",
            stage=stage,
            details={
                "error_type": error_type,
                "message": message,
                "traceback": traceback.format_exception_only(type(exc), exc),
            },
        )
        self.add_notification(
            build_user_notification(
                severity="blocking",
                stage=stage,
                issue_id=issue_id,
                title="Run stopped by an unexpected error",
                message=f"{error_type}: {message}",
                details={"error_type": error_type},
                suggested_actions=[
                    "Open run_events.jsonl for the last successful node.",
                    "Inspect the related stage artifact before retrying.",
                    "If no existing recovery action fits, ask for a parser or workflow update.",
                ],
            )
        )

    def _artifact_index(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        stage_by_key = _stage_by_artifact_key()
        paths: dict[str, str] = {
            key: str(value)
            for key, value in state.items()
            if str(key).endswith("_path") and str(value).strip()
        }
        paths.update(
            {
                "run_events_path": str(self.run_events_path),
                "user_notifications_path": str(self.user_notifications_path),
            }
        )
        index: list[dict[str, Any]] = []
        for key in sorted(paths):
            path = Path(paths[key])
            exists = path.exists()
            index.append(
                {
                    "artifact_key": key,
                    "path": str(path),
                    "stage": stage_by_key.get(key, "run_trace" if key.startswith("run_") else "unknown"),
                    "exists": exists,
                    "size_bytes": path.stat().st_size if exists else 0,
                    "sha256": _sha256(path) if exists and path.is_file() else "",
                    "schema_version": SCHEMA_VERSIONS.get(key, "0.1.0"),
                    "record_count": _file_record_count(path) if exists else None,
                }
            )
        return index

    def write(self, *, final_state: dict[str, Any], status: str) -> dict[str, Any]:
        if not self._finished:
            self.record_event("run_finished", details={"status": status})
            self._finished = True

        write_jsonl(self.run_events_path, self.events)
        write_json(self.user_notifications_path, self.notifications)

        manifest = {
            "schema_version": TRACE_SCHEMA_VERSION,
            "run_id": self.run_id,
            "status": status,
            "started_at": self.started_at,
            "ended_at": _utc_now(),
            "output_dir": str(self.output_dir),
            "parameters": _safe_parameters(self.initial_state),
            "summary": {
                "event_count": len(self.events),
                "notification_count": len(self.notifications),
            },
            "artifact_index": self._artifact_index(final_state),
        }
        write_json(self.run_manifest_path, manifest)
        return {
            "run_id": self.run_id,
            "run_manifest": manifest,
            "run_manifest_path": str(self.run_manifest_path),
            "run_events_path": str(self.run_events_path),
            "user_notifications": self.notifications,
            "user_notifications_path": str(self.user_notifications_path),
        }
