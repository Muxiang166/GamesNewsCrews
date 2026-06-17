"""User notification contract — severity spec, validation, and convenience builders.

Implements RUN-003.  Every notification consumed by the UI or by downstream
automation must conform to the schema defined in docs/issues.md lines 277-290.
"""

from __future__ import annotations

import re
from typing import Any

from .run_trace import build_user_notification

# ---------------------------------------------------------------------------
# Severity specification
# ---------------------------------------------------------------------------

NOTIFICATION_SEVERITY_SPEC: dict[str, dict[str, Any]] = {
    "info": {
        "description": (
            "Routine operational information.  The run is proceeding normally "
            "and no action is required from the user.  These notifications are "
            "primarily for audit trails and UI dashboards."
        ),
        "requires_user_action": False,
        "blocks_run": False,
        "examples": [
            "Run started successfully with parameters X.",
            "Stage 'source_collection' completed — 42 candidates collected.",
            "Artifact written: candidates.json (120 records, 45 KiB).",
        ],
    },
    "warning": {
        "description": (
            "Something unusual or sub-optimal was detected but the run can "
            "continue.  The user should review at their convenience but no "
            "immediate action is required to keep the run going."
        ),
        "requires_user_action": False,
        "blocks_run": False,
        "examples": [
            "Source 'ign-cn' returned only 3 candidates (expected >= 10).",
            "Content quality score for story 'X' fell below threshold (0.55 < 0.60).",
            "Discussion probe for Bilibili timed out; heat signals may be incomplete.",
        ],
    },
    "needs_user_action": {
        "description": (
            "Automation cannot decide the next step without human input.  The "
            "workflow is paused at this stage and will not proceed until the "
            "user acknowledges the notification and provides guidance (e.g. "
            "choose a recovery action, approve a parser change, or manually "
            "fill a missing artifact)."
        ),
        "requires_user_action": True,
        "blocks_run": True,
        "examples": [
            "Source parser for 'weibo' returned an unrecognized HTML structure. "
            "Select a recovery action: retry, switch to browser probe, or skip.",
            "All tools exhausted for claim verification — no suitable tool can "
            "evaluate the provided evidence.  Manual review required.",
            "Artifact 'candidates.json' is missing or corrupt; cannot proceed "
            "to filtering stage.",
        ],
    },
    "blocking": {
        "description": (
            "A fatal, unrecoverable error has occurred.  The run has stopped "
            "and will not continue until the root cause is resolved.  This is "
            "the highest severity — typically triggered by unhandled "
            "exceptions, missing required artifacts, or critical constraint "
            "violations."
        ),
        "requires_user_action": True,
        "blocks_run": True,
        "examples": [
            "Unhandled RuntimeError in node 'fetch_documents': unexpected "
            "parser shape — full traceback attached.",
            "Required artifact 'sources.yaml' could not be loaded — file is "
            "malformed or missing.",
            "All source collectors failed after exhausting retry budgets.",
        ],
    },
}

VALID_SEVERITIES = frozenset(NOTIFICATION_SEVERITY_SPEC.keys())

VALID_STATUSES: frozenset[str] = frozenset({"open", "acknowledged", "resolved"})

# notification_id format: "notif_" + 12 hex digits (as produced by build_user_notification)
_NOTIF_ID_RE = re.compile(r"^notif_[0-9a-f]{12}$")

# issue_id format: uppercase prefix + hyphen + digits (e.g. RUN-003, COL-001)
_ISSUE_ID_RE = re.compile(r"^[A-Z]{2,5}-\d{3,}$")

REQUIRED_FIELDS: tuple[str, ...] = (
    "notification_id",
    "severity",
    "stage",
    "issue_id",
    "title",
    "message",
    "details",
    "suggested_actions",
    "artifact_refs",
    "created_at",
    "status",
)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class NotificationContractError(ValueError):
    """Raised when a notification fails the contract validation."""


def _collect_issues(notification: dict[str, Any]) -> list[str]:
    """Return a list of human-readable validation issues (empty => valid)."""
    issues: list[str] = []

    # --- missing fields ---
    for field in REQUIRED_FIELDS:
        if field not in notification:
            issues.append(f"Missing required field: '{field}'")

    nid = notification.get("notification_id")
    if isinstance(nid, str) and not _NOTIF_ID_RE.match(nid):
        issues.append(
            f"notification_id '{nid}' does not match expected format "
            f"'notif_{{12_hex_digits}}'"
        )

    severity = notification.get("severity")
    if severity is not None and severity not in VALID_SEVERITIES:
        issues.append(
            f"Invalid severity '{severity}'. "
            f"Must be one of: {', '.join(sorted(VALID_SEVERITIES))}"
        )

    status = notification.get("status")
    if status is not None and status not in VALID_STATUSES:
        issues.append(
            f"Invalid status '{status}'. "
            f"Must be one of: {', '.join(sorted(VALID_STATUSES))}"
        )

    issue_id = notification.get("issue_id")
    if isinstance(issue_id, str) and not _ISSUE_ID_RE.match(issue_id):
        issues.append(
            f"issue_id '{issue_id}' does not match expected format "
            f"'{{PREFIX}}-{{NNN}}' (e.g. RUN-003, COL-001)"
        )

    stage = notification.get("stage")
    if isinstance(stage, str) and not stage.strip():
        issues.append("stage must be a non-empty string")

    title = notification.get("title")
    if isinstance(title, str) and not title.strip():
        issues.append("title must be a non-empty string")

    message = notification.get("message")
    if isinstance(message, str) and not message.strip():
        issues.append("message must be a non-empty string")

    suggested_actions = notification.get("suggested_actions")
    if suggested_actions is not None:
        if not isinstance(suggested_actions, list):
            issues.append("suggested_actions must be a list")
        else:
            for i, action in enumerate(suggested_actions):
                if not isinstance(action, str):
                    issues.append(
                        f"suggested_actions[{i}] must be a string, got "
                        f"{type(action).__name__}"
                    )

    artifact_refs = notification.get("artifact_refs")
    if artifact_refs is not None:
        if not isinstance(artifact_refs, list):
            issues.append("artifact_refs must be a list")
        else:
            for i, ref in enumerate(artifact_refs):
                if not isinstance(ref, str):
                    issues.append(
                        f"artifact_refs[{i}] must be a string, got "
                        f"{type(ref).__name__}"
                    )

    details = notification.get("details")
    if details is not None and not isinstance(details, dict):
        issues.append("details must be a dict")

    created_at = notification.get("created_at")
    if created_at is not None and not isinstance(created_at, str):
        issues.append("created_at must be an ISO-8601 string")

    return issues


def validate_notification_contract(
    notification: dict[str, Any],
) -> dict[str, Any]:
    """Validate a notification dict against the RUN-003 contract.

    Returns the notification unchanged on success (allowing callers to use it
    as a pass-through).  Raises `NotificationContractError` with a multi-line
    message listing every violation found.
    """
    issues = _collect_issues(notification)
    if issues:
        raise NotificationContractError(
            "Notification contract validation failed with "
            f"{len(issues)} issue(s):\n"
            + "\n".join(f"  - {issue}" for issue in issues)
        )
    return notification


def is_valid_notification(notification: dict[str, Any]) -> bool:
    """Return True if the notification passes contract validation."""
    return len(_collect_issues(notification)) == 0


# ---------------------------------------------------------------------------
# Convenience builder
# ---------------------------------------------------------------------------


def create_stage_notification(
    stage: str,
    issue_id: str,
    title: str,
    message: str,
    severity: str = "needs_user_action",
    suggested_actions: list[str] | None = None,
    artifact_refs: list[str] | None = None,
    details: dict[str, Any] | None = None,
    *,
    status: str = "open",
) -> dict[str, Any]:
    """Build a validated notification for a specific pipeline stage.

    This is the recommended entry-point for all node-level code.  It delegates
    to `build_user_notification` and then runs `validate_notification_contract`
    so that contract violations are caught at creation time rather than at
    write time.

    Parameters
    ----------
    stage:
        Pipeline stage identifier (e.g. ``"source_collection"``,
        ``"evidence_retrieval"``).
    issue_id:
        Issue tracking id in ``PREFIX-NNN`` format (e.g. ``"COL-004"``).
    title:
        Short, UI-friendly summary.
    message:
        Longer human-readable explanation.
    severity:
        One of ``"info"``, ``"warning"``, ``"needs_user_action"``,
        ``"blocking"``.  Defaults to ``"needs_user_action"``.
    suggested_actions:
        List of actionable strings the user can take.
    artifact_refs:
        File paths or artifact keys relevant to the issue.
    details:
        Arbitrary structured context (error_type, counts, stack traces, etc.).
    status:
        Lifecycle status — ``"open"``, ``"acknowledged"``, or ``"resolved"``.
        Defaults to ``"open"``.
    """
    notification = build_user_notification(
        severity=severity,
        stage=stage,
        issue_id=issue_id,
        title=title,
        message=message,
        details=details,
        suggested_actions=suggested_actions,
        artifact_refs=artifact_refs,
        status=status,
    )
    # Enforce the contract at creation time.
    validate_notification_contract(notification)
    return notification
