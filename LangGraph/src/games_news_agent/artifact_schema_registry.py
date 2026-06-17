"""Schema validation for pipeline artifacts produced during each run."""

from __future__ import annotations

from pathlib import Path
from typing import Any, TypedDict

from .artifact_manifest import ARTIFACT_STAGES
from .io import read_json, write_json
from .run_trace import build_user_notification

# ---------------------------------------------------------------------------
# Schema definitions
# ---------------------------------------------------------------------------


class CandidateRequiredFields(TypedDict):
    title: str
    url: str
    source_id: str
    published_at: str


class DocumentRequiredFields(TypedDict):
    candidate_url: str
    title: str
    source_id: str
    content: str


class EvidenceChunkRequiredFields(TypedDict):
    chunk_id: str
    url: str
    source_id: str
    quote: str


class ClaimRequiredFields(TypedDict):
    claim_id: str
    text: str
    source_urls: list[str]


class ClaimVerificationRequiredFields(TypedDict):
    claim_id: str
    status: str
    evidence_chunk_ids: list[str]


class StoryRequiredFields(TypedDict):
    id: str
    title: str
    source_urls: list[str]


class ContextPackRequiredFields(TypedDict):
    candidate_url: str
    title: str


class PlatformPostRequiredFields(TypedDict):
    platform: str
    story_id: str
    content: str


class RunManifestRequiredFields(TypedDict):
    run_id: str
    status: str
    artifact_index: list[dict[str, Any]]


class UserNotificationRequiredFields(TypedDict):
    notification_id: str
    severity: str
    title: str
    message: str


class ContentQualityReportRequiredFields(TypedDict):
    overall_score: int
    gate_status: str


class ArtifactSchema(TypedDict):
    schema_version: str
    required_fields: list[str]
    any_of_fields: list[list[str]]
    is_list: bool
    description: str


ARTIFACT_SCHEMA_VERSION = "0.1.0"

ARTIFACT_SCHEMAS: dict[str, ArtifactSchema] = {
    "candidates": {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "required_fields": ["title", "url", "source_id"],
        "any_of_fields": [["published_at", "observed_at", "event_time"]],
        "is_list": True,
        "description": "Collected search/fetch candidates from source collection stage",
    },
    "documents": {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "required_fields": ["candidate_url", "title", "source_id", "content"],
        "any_of_fields": [],
        "is_list": True,
        "description": "Fetched full-text documents for theme candidates",
    },
    "evidence_chunks": {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "required_fields": ["chunk_id", "url", "source_id", "quote"],
        "any_of_fields": [],
        "is_list": True,
        "description": "Evidence chunks extracted from documents",
    },
    "claims": {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "required_fields": ["story_id", "text", "source_urls"],
        "any_of_fields": [],
        "is_list": True,
        "description": "Extracted factual claims from evidence",
    },
    "claim_verifications": {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "required_fields": ["story_id", "check_status", "evidence_chunk_ids"],
        "any_of_fields": [],
        "is_list": True,
        "description": "Verification results for extracted claims",
    },
    "stories": {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "required_fields": ["id", "title", "source_urls"],
        "any_of_fields": [],
        "is_list": True,
        "description": "Final ranked stories for publication",
    },
    "context_packs": {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "required_fields": ["candidate", "evidence"],
        "any_of_fields": [],
        "is_list": True,
        "description": "Context packs assembled for story candidates",
    },
    "platform_posts": {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "required_fields": ["story_id", "title", "platforms"],
        "any_of_fields": [],
        "is_list": True,
        "description": "Platform-specific formatted posts",
    },
    "run_manifest": {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "required_fields": ["run_id", "status", "artifact_index"],
        "any_of_fields": [],
        "is_list": False,
        "description": "Run-level manifest with artifact index",
    },
    "user_notifications": {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "required_fields": ["notification_id", "severity", "title", "message"],
        "any_of_fields": [],
        "is_list": True,
        "description": "User-facing notifications generated during the run",
    },
    "content_quality_report": {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "required_fields": ["overall_score", "gate_status"],
        "any_of_fields": [],
        "is_list": False,
        "description": "Content quality gate report",
    },
    "rejected_candidates": {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "required_fields": ["title", "url", "source_id"],
        "any_of_fields": [],
        "is_list": True,
        "description": "Candidates that failed filtering",
    },
    "theme_candidate_pool": {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "required_fields": [],
        "any_of_fields": [],
        "is_list": False,
        "description": "Balanced theme candidate pool dict",
    },
    "assets": {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "required_fields": ["kind", "source_url"],
        "any_of_fields": [],
        "is_list": True,
        "description": "Discovered media assets for stories",
    },
    "story_clusters": {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "required_fields": [],
        "any_of_fields": [],
        "is_list": True,
        "description": "Dedup story clusters",
    },
    "theme_sections": {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "required_fields": [],
        "any_of_fields": [],
        "is_list": False,
        "description": "Theme section definitions",
    },
    "content_review": {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "required_fields": [],
        "any_of_fields": [],
        "is_list": False,
        "description": "Content review markdown",
    },
    "material_bundle": {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "required_fields": [],
        "any_of_fields": [],
        "is_list": False,
        "description": "Material bundle for downstream consumers",
    },
    "layout_manifest": {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "required_fields": [],
        "any_of_fields": [],
        "is_list": False,
        "description": "Layout manifest for rendering",
    },
    "render_queue": {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "required_fields": [],
        "any_of_fields": [],
        "is_list": False,
        "description": "Render queue entries",
    },
}


# Map of stage artifact filenames to artifact key names
def _filename_to_artifact_key() -> dict[str, str]:
    """Build mapping from filename (e.g. 'candidates.json') to artifact key ('candidates')."""
    mapping: dict[str, str] = {}
    for stage in ARTIFACT_STAGES:
        for key, filename in stage.get("artifacts", []):
            mapping[str(filename)] = str(key)
    return mapping


CRITICAL_ARTIFACTS: set[str] = {
    "candidates",
    "documents",
    "stories",
    "platform_posts",
    "claim_verifications",
}


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _is_non_empty(value: Any) -> bool:
    """Return True if value is non-null and (for strings) non-empty.

    Empty lists, dicts, and other containers are considered structurally
    valid --- only ``None`` and blank strings are flagged as empty.
    """
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    return True


def validate_artifact(
    artifact_key: str,
    data: Any,
) -> list[dict[str, Any]]:
    """Validate artifact data against its registered schema.

    Returns a list of validation error dicts.  An empty list means the
    artifact passed validation.
    """
    errors: list[dict[str, Any]] = []
    schema = ARTIFACT_SCHEMAS.get(artifact_key)
    if schema is None:
        errors.append(
            {
                "artifact_key": artifact_key,
                "error": "unknown_artifact_key",
                "message": f"No schema registered for artifact key '{artifact_key}'.",
            }
        )
        return errors

    required_fields = schema["required_fields"]
    any_of_fields = schema.get("any_of_fields", [])
    is_list = schema["is_list"]

    if not required_fields:
        # Schema has no required fields — always valid.
        return errors

    if is_list:
        if not isinstance(data, list):
            errors.append(
                {
                    "artifact_key": artifact_key,
                    "error": "unexpected_type",
                    "message": f"Expected a list for artifact '{artifact_key}', got {type(data).__name__}.",
                }
            )
            return errors
        items = data
    else:
        items = [data]

    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(
                {
                    "artifact_key": artifact_key,
                    "error": "invalid_item_type",
                    "message": (
                        f"Item at index {idx} in artifact '{artifact_key}' "
                        f"is not a dict, got {type(item).__name__}."
                    ),
                }
            )
            continue
        for field in required_fields:
            if field not in item:
                errors.append(
                    {
                        "artifact_key": artifact_key,
                        "index": idx,
                        "error": "missing_field",
                        "message": (
                            f"Required field '{field}' is missing from item at "
                            f"index {idx} in artifact '{artifact_key}'."
                        ),
                    }
                )
            elif not _is_non_empty(item[field]):
                errors.append(
                    {
                        "artifact_key": artifact_key,
                        "index": idx,
                        "error": "empty_field",
                        "message": (
                            f"Required field '{field}' is empty/null at "
                            f"index {idx} in artifact '{artifact_key}'."
                        ),
                    }
                )
        for alternatives in any_of_fields:
            if not any(field in item and _is_non_empty(item[field]) for field in alternatives):
                errors.append(
                    {
                        "artifact_key": artifact_key,
                        "index": idx,
                        "error": "missing_alternative_field",
                        "message": (
                            "At least one of "
                            f"{', '.join(repr(field) for field in alternatives)} "
                            f"must be present and non-empty at index {idx} in artifact "
                            f"'{artifact_key}'."
                        ),
                    }
                )
    return errors


def validate_artifact_file(
    artifact_key: str,
    file_path: str | Path,
) -> dict[str, Any]:
    """Read artifact JSON from *file_path* and validate it.

    Returns a result dict with keys ``artifact_key``, ``file_path``,
    ``schema_version``, ``valid`` (bool), ``errors``, and ``record_count``.
    """
    file_path = Path(file_path)
    schema = ARTIFACT_SCHEMAS.get(artifact_key, {})

    if not file_path.exists():
        return {
            "artifact_key": artifact_key,
            "file_path": str(file_path),
            "schema_version": schema.get("schema_version", ARTIFACT_SCHEMA_VERSION),
            "valid": False,
            "errors": [
                {
                    "artifact_key": artifact_key,
                    "error": "file_not_found",
                    "message": f"Artifact file not found: {file_path}",
                }
            ],
            "record_count": None,
        }

    try:
        data = read_json(file_path)
    except Exception as exc:
        return {
            "artifact_key": artifact_key,
            "file_path": str(file_path),
            "schema_version": schema.get("schema_version", ARTIFACT_SCHEMA_VERSION),
            "valid": False,
            "errors": [
                {
                    "artifact_key": artifact_key,
                    "error": "json_parse_error",
                    "message": f"Failed to parse JSON from {file_path}: {exc}",
                }
            ],
            "record_count": None,
        }

    errors = validate_artifact(artifact_key, data)

    record_count: int | None = None
    if isinstance(data, list):
        record_count = len(data)
    elif isinstance(data, dict):
        record_count = 1

    return {
        "artifact_key": artifact_key,
        "file_path": str(file_path),
        "schema_version": schema.get("schema_version", ARTIFACT_SCHEMA_VERSION),
        "valid": len(errors) == 0,
        "errors": errors,
        "record_count": record_count,
    }


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def _known_artifact_files() -> list[tuple[str, str]]:
    """Return (artifact_key, filename) pairs from the artifact manifest stages."""
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()
    for stage in ARTIFACT_STAGES:
        for key, filename in stage.get("artifacts", []):
            art_key = str(key)
            # Strip "_path" to get the logical artifact key
            logical_key = art_key[:-5] if art_key.endswith("_path") else art_key
            if logical_key not in seen:
                seen.add(logical_key)
                pairs.append((logical_key, str(filename)))
    return pairs


def generate_schema_report(
    output_dir: str | Path,
) -> dict[str, Any]:
    """Scan *output_dir* for known artifact files and validate each one.

    Returns a ``schema_report`` dict that also gets written as
    ``schema_validation_report.json`` inside *output_dir*.
    """
    root = Path(output_dir)
    results: list[dict[str, Any]] = []
    valid_count = 0
    invalid_count = 0
    skipped_count = 0
    skipped_missing_count = 0
    skipped_no_schema_count = 0
    skipped_unsupported_format_count = 0

    for artifact_key, filename in _known_artifact_files():
        file_path = root / filename
        schema = ARTIFACT_SCHEMAS.get(artifact_key)
        if schema is None:
            skipped_count += 1
            skipped_no_schema_count += 1
            results.append(
                {
                    "artifact_key": artifact_key,
                    "file_path": str(file_path),
                    "schema_version": ARTIFACT_SCHEMA_VERSION,
                    "valid": True,
                    "skipped": True,
                    "skip_reason": "no_schema_registered",
                    "errors": [],
                    "record_count": None,
                }
            )
            continue
        if file_path.suffix.lower() != ".json":
            skipped_count += 1
            skipped_unsupported_format_count += 1
            results.append(
                {
                    "artifact_key": artifact_key,
                    "file_path": str(file_path),
                    "schema_version": schema.get("schema_version", ARTIFACT_SCHEMA_VERSION),
                    "valid": True,
                    "skipped": True,
                    "skip_reason": "unsupported_artifact_format",
                    "errors": [],
                    "record_count": None,
                }
            )
            continue
        if not file_path.exists():
            skipped_count += 1
            skipped_missing_count += 1
            is_critical = artifact_key in CRITICAL_ARTIFACTS
            if is_critical:
                invalid_count += 1
            results.append(
                {
                    "artifact_key": artifact_key,
                    "file_path": str(file_path),
                    "schema_version": ARTIFACT_SCHEMA_VERSION,
                    "valid": not is_critical,
                    "skipped": not is_critical,
                    "skip_reason": "missing_optional_artifact" if not is_critical else "",
                    "errors": [
                        {
                            "artifact_key": artifact_key,
                            "error": "file_not_found",
                            "message": f"Artifact file not found: {file_path}",
                        }
                    ],
                    "record_count": None,
                }
            )
            continue

        result = validate_artifact_file(artifact_key, file_path)
        if result["valid"]:
            valid_count += 1
        else:
            invalid_count += 1
        results.append(result)

    report: dict[str, Any] = {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "output_dir": str(root),
        "summary": {
            "total_artifacts_checked": len(results),
            "valid": valid_count,
            "invalid": invalid_count,
            "skipped": skipped_count,
            "skipped_missing": skipped_missing_count,
            "skipped_no_schema": skipped_no_schema_count,
            "skipped_unsupported_format": skipped_unsupported_format_count,
        },
        "results": results,
    }

    report_path = root / "schema_validation_report.json"
    write_json(report_path, report)

    return report


# ---------------------------------------------------------------------------
# Notification integration
# ---------------------------------------------------------------------------


def build_validation_notifications(
    report: dict[str, Any],
) -> list[dict[str, Any]]:
    """Inspect a schema report and emit warning notifications for critical
    artifacts that failed validation.

    Returns a list of ``build_user_notification``-style dicts.
    """
    notifications: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = report.get("results", [])

    for result in results:
        artifact_key = str(result.get("artifact_key") or "")
        if artifact_key not in CRITICAL_ARTIFACTS:
            continue
        if result.get("valid"):
            continue

        error_messages = [
            str(e.get("message") or "") for e in result.get("errors", [])
        ]
        notifications.append(
            build_user_notification(
                severity="warning",
                stage="schema_validation",
                issue_id="SCHEMA-001",
                title=f"Schema validation failed for critical artifact '{artifact_key}'",
                message="; ".join(error_messages) if error_messages else "Unknown validation error.",
                details={
                    "artifact_key": artifact_key,
                    "file_path": result.get("file_path"),
                    "error_count": len(result.get("errors", [])),
                },
                suggested_actions=[
                    f"Inspect {result.get('file_path')} for missing or empty required fields.",
                    "Check the upstream node that produces this artifact.",
                    "If the schema is stale, update artifact_schema_registry.ARTIFACT_SCHEMAS.",
                ],
                artifact_refs=[artifact_key],
            )
        )

    return notifications
