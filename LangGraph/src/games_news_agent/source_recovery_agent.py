"""AG-003 SourceRecoveryAgent -- deterministic recovery action selection from collection diagnostics.

The agent reads diagnostics artifacts and selects the best recovery action using
deterministic decision-tree logic.  It never auto-modifies configs; it writes
ConfigPatchProposal objects that callers must review before application.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Whitelist Actions
# ---------------------------------------------------------------------------

WHITELIST_ACTIONS: dict[str, dict[str, Any]] = {
    "retry_same_source": {
        "description": (
            "Re-run the same collector entry with exponential backoff.  "
            "Suitable when errors are transient (timeout, rate-limit, DNS, 5xx)."
        ),
        "risk_level": "low",
        "requires_approval": False,
        "params_schema": {
            "max_retries": {
                "type": "integer",
                "default": 3,
                "minimum": 1,
                "maximum": 5,
            },
            "backoff_seconds": {
                "type": "integer",
                "default": 10,
                "minimum": 5,
                "maximum": 300,
            },
            "backoff_multiplier": {
                "type": "number",
                "default": 2.0,
                "minimum": 1.0,
                "maximum": 5.0,
            },
        },
    },
    "switch_entry_point": {
        "description": (
            "Switch to an alternative entry URL or page for the same source.  "
            "Use when the current entry point is accessible but produces zero "
            "candidates."
        ),
        "risk_level": "medium",
        "requires_approval": True,
        "params_schema": {
            "candidate_entry_urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Alternative URLs observed by navigation or manual review.",
            },
            "reason": {
                "type": "string",
                "description": "Why the current entry point is insufficient.",
            },
        },
    },
    "enable_detail_time_backfill": {
        "description": (
            "Enable detail-page time backfill for sources where list pages lack "
            "reliable timestamps.  The collector will fetch detail pages to extract "
            "publication dates."
        ),
        "risk_level": "low",
        "requires_approval": False,
        "params_schema": {
            "detail_time_backfill_limit": {
                "type": "integer",
                "default": 10,
                "minimum": 1,
                "maximum": 50,
            },
            "missing_time_ratio": {
                "type": "number",
                "description": "Current ratio of candidates missing timestamps.",
            },
        },
    },
    "enable_browser_probe": {
        "description": (
            "Use a headless browser to probe the source.  Required when the source "
            "uses heavy JavaScript rendering or anti-bot protection that blocks "
            "deterministic HTTP collectors."
        ),
        "risk_level": "high",
        "requires_approval": True,
        "params_schema": {
            "probe_urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": "URLs to probe with the browser.",
            },
            "wait_seconds": {
                "type": "integer",
                "default": 5,
                "minimum": 1,
                "maximum": 30,
            },
            "screenshot": {"type": "boolean", "default": False},
        },
    },
    "use_cache": {
        "description": (
            "Fall back to cached data from a previous successful run.  "
            "Suitable when the source is temporarily unavailable but recent "
            "cached data exists."
        ),
        "risk_level": "low",
        "requires_approval": False,
        "params_schema": {
            "cache_source_id": {
                "type": "string",
                "description": "Source ID to retrieve from cache.",
            },
            "max_cache_age_hours": {
                "type": "integer",
                "default": 24,
                "minimum": 1,
                "maximum": 168,
            },
        },
    },
    "mark_manual_review": {
        "description": (
            "Mark the source for human review.  Used when no automated recovery "
            "action applies or when the diagnostics are inconclusive."
        ),
        "risk_level": "low",
        "requires_approval": True,
        "params_schema": {
            "reason": {
                "type": "string",
                "description": "Why manual review is needed.",
            },
            "diagnostics_summary": {
                "type": "object",
                "description": "Relevant diagnostics excerpt for the reviewer.",
            },
        },
    },
}


# ---------------------------------------------------------------------------
# Error classification helpers
# ---------------------------------------------------------------------------

_TRANSIENT_ERROR_TOKENS: tuple[str, ...] = (
    "timeout",
    "timed out",
    "rate limit",
    "rate_limit",
    "429",
    "connection reset",
    "connection_reset",
    "connection refused",
    "connection_error",
    "dns",
    "name resolution",
    "temporary failure",
    "service unavailable",
    "503",
    "504",
    "502",
    "bad gateway",
    "gateway timeout",
    "too many requests",
    "econnrefused",
    "econnreset",
    "etimedout",
    "enotfound",
    "eagain",
)

_CONNECTION_ERROR_TOKENS: tuple[str, ...] = (
    "connection refused",
    "connection_error",
    "connection reset",
    "connection_reset",
    "dns",
    "name resolution",
    "econnrefused",
    "econnreset",
    "enotfound",
    "eagain",
    "network",
    "unreachable",
)


def _is_transient_status(status_code: object) -> bool:
    """Return True when the HTTP status code indicates a transient failure."""
    if not isinstance(status_code, int):
        return False
    return status_code in (408, 429) or 500 <= status_code <= 599


def _classify_errors(
    page_samples: list[dict[str, Any]],
) -> dict[str, Any]:
    """Classify errors from page samples into transient / connection / permanent buckets."""
    transient_count = 0
    connection_count = 0
    permanent_count = 0
    total_attempts = len(page_samples)
    error_samples: list[dict[str, Any]] = []

    for sample in page_samples:
        error_type = str(sample.get("error_type", "")).lower()
        error_message = str(sample.get("error_message", "")).lower()
        status_code = sample.get("status_code")
        combined = f"{error_type} {error_message}"

        is_error = False
        if isinstance(status_code, int) and status_code >= 400:
            is_error = True
        if error_type or error_message:
            is_error = True

        if not is_error:
            continue

        is_transient = _is_transient_status(status_code) or any(
            token in combined for token in _TRANSIENT_ERROR_TOKENS
        )
        is_connection = any(token in combined for token in _CONNECTION_ERROR_TOKENS)

        if is_transient:
            transient_count += 1
        if is_connection:
            connection_count += 1
        if not is_transient and not is_connection:
            permanent_count += 1

        error_samples.append(
            {
                "url": sample.get("url", ""),
                "status_code": status_code,
                "error_type": error_type,
                "error_message": error_message,
                "is_transient": is_transient,
                "is_connection": is_connection,
            }
        )

    return {
        "total_attempts": total_attempts,
        "transient_count": transient_count,
        "connection_count": connection_count,
        "permanent_count": permanent_count,
        "all_failed": total_attempts > 0
        and (transient_count + permanent_count) >= total_attempts,
        "all_connection_failures": total_attempts > 0
        and connection_count >= total_attempts,
        "any_transient": transient_count > 0,
        "error_samples": error_samples,
    }


def _compute_missing_time_ratio(diagnostics: dict[str, Any]) -> float:
    """Return the ratio of candidates that lack usable timestamps."""
    candidate_count = int(diagnostics.get("candidate_count", 0))
    missing_time_count = int(diagnostics.get("missing_time_count", 0))
    reject_reasons = diagnostics.get("reject_reasons", {})
    rejected_missing_time = 0
    if isinstance(reject_reasons, dict):
        rejected_missing_time = int(reject_reasons.get("missing_time", 0))
    denominator = max(candidate_count + rejected_missing_time, 1)
    return missing_time_count / denominator


def _has_cache_available(_source_id: str, diagnostics: dict[str, Any]) -> bool:
    """Return True when diagnostics indicate prior successful fetches exist."""
    raw_fetch_count = int(diagnostics.get("raw_fetch_count", 0))
    detail_time_backfill = int(diagnostics.get("detail_time_backfill_count", 0))
    return raw_fetch_count > 0 or detail_time_backfill > 0


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class AgentDecision:
    """A recovery action decision produced by the agent."""

    action_id: str
    params: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    risk_level: str = "low"
    requires_approval: bool = False
    confidence: float = 0.0
    source_id: str = ""


@dataclass
class ConfigPatchProposal:
    """A proposed config change that must be reviewed before application."""

    source_id: str
    patch: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    requires_approval: bool = True
    action_id: str = ""


@dataclass
class ToolResult:
    """Result of attempting to execute a recovery action."""

    action_id: str
    status: str  # "proposed" | "deferred" | "blocked"
    message: str = ""
    config_patch: ConfigPatchProposal | None = None
    decision: AgentDecision | None = None


@dataclass(frozen=True)
class SourceRecoveryPolicy:
    """Tunable thresholds for ``SourceRecoveryAgent`` decisions.

    Defaults mirror the original deterministic v0 behavior, but keeping them in
    one object makes later CLI/config/Agent wiring explicit instead of hidden in
    branch bodies.
    """

    retry_max_retries: int = 5
    retry_backoff_seconds: int = 10
    retry_backoff_multiplier: float = 2.0
    missing_time_ratio_threshold: float = 0.3
    detail_time_backfill_max: int = 50
    detail_time_backfill_multiplier: float = 1.5
    browser_wait_seconds: int = 5
    browser_screenshot: bool = True
    cache_max_age_hours: int = 24


# ---------------------------------------------------------------------------
# SourceRecoveryAgent
# ---------------------------------------------------------------------------


class SourceRecoveryAgent:
    """Deterministic agent that selects recovery actions from diagnostics.

    The agent evaluates whitelist actions against collector diagnostics using
    decision-tree logic.  It never auto-modifies configs -- it writes
    ``ConfigPatchProposal`` objects instead.
    """

    def __init__(
        self,
        source_id: str,
        source_health: dict[str, Any] | None = None,
        collector_diagnostics: dict[str, Any] | None = None,
        run_events: list[dict[str, Any]] | None = None,
        page_samples: list[dict[str, Any]] | None = None,
        policy: SourceRecoveryPolicy | None = None,
    ) -> None:
        self.source_id = source_id
        self.source_health = source_health or {}
        self.collector_diagnostics = collector_diagnostics or {}
        self.run_events = run_events or []
        self.page_samples = page_samples or []
        self.policy = policy or SourceRecoveryPolicy()

        # Per-source diagnostics slice
        self._source_diag: dict[str, Any] = self._resolve_source_diagnostics()

        # Error classification
        self._error_analysis = _classify_errors(self.page_samples)

        # Key metrics
        self._candidate_count = int(self._source_diag.get("candidate_count", 0))
        self._error_count = int(self._source_diag.get("error_count", 0))
        self._missing_time_ratio = _compute_missing_time_ratio(self._source_diag)
        self._collector = str(self._source_diag.get("collector", ""))
        self._raw_fetch_count = int(self._source_diag.get("raw_fetch_count", 0))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_source_diagnostics(self) -> dict[str, Any]:
        sources = self.collector_diagnostics.get("sources", [])
        if not isinstance(sources, list):
            return {}
        for item in sources:
            if isinstance(item, dict):
                sid = str(item.get("source_id", ""))
                if sid == self.source_id:
                    return item
        return {}

    # ------------------------------------------------------------------
    # Action evaluators (one private method per whitelist action)
    # ------------------------------------------------------------------

    def _evaluate_retry_same_source(self) -> AgentDecision | None:
        """Retry when error_count > 0 includes transient errors."""
        if self._error_count == 0:
            return None
        if not self._error_analysis["any_transient"]:
            return None

        transient_count = self._error_analysis["transient_count"]
        confidence = min(0.9, 0.5 + transient_count * 0.1)

        return AgentDecision(
            action_id="retry_same_source",
            params={
                "max_retries": min(
                    self.policy.retry_max_retries,
                    self._error_count + 1,
                ),
                "backoff_seconds": self.policy.retry_backoff_seconds,
                "backoff_multiplier": self.policy.retry_backoff_multiplier,
                "error_count": self._error_count,
                "transient_count": transient_count,
            },
            reason=(
                f"Source {self.source_id} has {self._error_count} error(s) "
                f"({transient_count} transient).  "
                "Retry with exponential backoff may resolve transient failures."
            ),
            risk_level="low",
            requires_approval=False,
            confidence=confidence,
            source_id=self.source_id,
        )

    def _evaluate_switch_entry_point(self) -> AgentDecision | None:
        """Switch entry when candidate_count == 0 but the entry is reachable."""
        if self._candidate_count > 0:
            return None
        # Entry is not reachable at all -- let another evaluator handle that.
        if self._raw_fetch_count == 0:
            return None

        confidence = 0.75

        return AgentDecision(
            action_id="switch_entry_point",
            params={
                "candidate_entry_urls": [],
                "reason": (
                    f"Source {self.source_id} produced {self._raw_fetch_count} "
                    f"raw fetches but {self._candidate_count} candidates.  "
                    "The entry point may need to be switched to a more "
                    "productive URL or page structure."
                ),
            },
            reason=(
                f"Source {self.source_id} has {self._candidate_count} candidates "
                f"from {self._raw_fetch_count} raw fetches.  "
                "Entry point may be stale or misconfigured."
            ),
            risk_level="medium",
            requires_approval=True,
            confidence=confidence,
            source_id=self.source_id,
        )

    def _evaluate_enable_detail_time_backfill(self) -> AgentDecision | None:
        """Enable time backfill when missing_time_ratio exceeds policy threshold."""
        if self._missing_time_ratio <= self.policy.missing_time_ratio_threshold:
            return None
        if self._candidate_count == 0:
            return None

        confidence = min(0.9, 0.5 + self._missing_time_ratio)

        return AgentDecision(
            action_id="enable_detail_time_backfill",
            params={
                "detail_time_backfill_limit": min(
                    self.policy.detail_time_backfill_max,
                    max(
                        1,
                        int(
                            self._candidate_count
                            * self.policy.detail_time_backfill_multiplier
                        ),
                    ),
                ),
                "missing_time_ratio": round(self._missing_time_ratio, 3),
                "missing_time_count": int(
                    self._source_diag.get("missing_time_count", 0)
                ),
            },
            reason=(
                f"Source {self.source_id} has "
                f"missing_time_ratio={self._missing_time_ratio:.1%} "
                f"(above {self.policy.missing_time_ratio_threshold:.0%} threshold).  "
                "Enabling detail-page time backfill "
                "may recover timestamps from article pages."
            ),
            risk_level="low",
            requires_approval=False,
            confidence=confidence,
            source_id=self.source_id,
        )

    def _evaluate_enable_browser_probe(self) -> AgentDecision | None:
        """Suggest browser probe when all HTTP attempts fail with connection errors."""
        if not self._error_analysis["all_connection_failures"]:
            return None
        if self._raw_fetch_count > 0:
            return None

        return AgentDecision(
            action_id="enable_browser_probe",
            params={
                "probe_urls": [
                    s.get("url", "")
                    for s in self.page_samples
                    if isinstance(s, dict) and s.get("url")
                ],
                "wait_seconds": self.policy.browser_wait_seconds,
                "screenshot": self.policy.browser_screenshot,
                "error_summary": {
                    "connection_count": self._error_analysis["connection_count"],
                    "total_attempts": self._error_analysis["total_attempts"],
                },
            },
            reason=(
                f"All {self._error_analysis['total_attempts']} HTTP attempts for "
                f"source {self.source_id} failed with connection errors.  "
                "A browser probe may bypass anti-bot protection or JS "
                "rendering requirements."
            ),
            risk_level="high",
            requires_approval=True,
            confidence=0.7,
            source_id=self.source_id,
        )

    def _evaluate_use_cache(self) -> AgentDecision | None:
        """Suggest cache fallback when prior data exists and source is failing."""
        if not _has_cache_available(self.source_id, self._source_diag):
            return None
        if self._error_count == 0 and self._candidate_count > 0:
            return None

        return AgentDecision(
            action_id="use_cache",
            params={
                "cache_source_id": self.source_id,
                "max_cache_age_hours": self.policy.cache_max_age_hours,
            },
            reason=(
                f"Source {self.source_id} has cached data available and is "
                f"currently experiencing issues "
                f"(errors={self._error_count}, candidates={self._candidate_count}).  "
                "Using cached data as temporary fallback."
            ),
            risk_level="low",
            requires_approval=False,
            confidence=0.5,
            source_id=self.source_id,
        )

    def _evaluate_mark_manual_review(self) -> AgentDecision:
        """Fallback evaluator -- always returns a decision."""
        return AgentDecision(
            action_id="mark_manual_review",
            params={
                "reason": (
                    f"No automated recovery action clearly applies for source "
                    f"{self.source_id}.  "
                    f"Diagnostics: candidates={self._candidate_count}, "
                    f"errors={self._error_count}, "
                    f"missing_time_ratio={self._missing_time_ratio:.1%}, "
                    f"collector={self._collector}."
                ),
                "diagnostics_summary": {
                    "candidate_count": self._candidate_count,
                    "error_count": self._error_count,
                    "missing_time_ratio": round(self._missing_time_ratio, 3),
                    "raw_fetch_count": self._raw_fetch_count,
                    "collector": self._collector,
                    "error_analysis": {
                        "transient_count": self._error_analysis["transient_count"],
                        "connection_count": self._error_analysis["connection_count"],
                        "permanent_count": self._error_analysis["permanent_count"],
                        "all_failed": self._error_analysis["all_failed"],
                    },
                },
            },
            reason=(
                f"Source {self.source_id} requires manual review.  "
                "No automated recovery action matched with sufficient confidence."
            ),
            risk_level="low",
            requires_approval=True,
            confidence=0.3,
            source_id=self.source_id,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def select_recovery_action(self) -> AgentDecision:
        """Evaluate whitelist actions in priority order; return the first match.

        The decision tree v0 priority:

        1. **retry_same_source** -- transient errors present
        2. **switch_entry_point** -- zero candidates, entry accessible
        3. **enable_detail_time_backfill** -- missing-time ratio > 0.3
        4. **use_cache** -- prior data exists, source is failing
        5. **enable_browser_probe** -- all HTTP attempts fail with connection errors
        6. **mark_manual_review** -- fallback (always matches)
        """
        evaluators = [
            self._evaluate_retry_same_source,
            self._evaluate_switch_entry_point,
            self._evaluate_enable_detail_time_backfill,
            self._evaluate_use_cache,
            self._evaluate_enable_browser_probe,
        ]

        logger.info(
            "SourceRecoveryAgent selecting action for source=%s "
            "candidates=%d errors=%d missing_time_ratio=%.1f%%",
            self.source_id,
            self._candidate_count,
            self._error_count,
            self._missing_time_ratio * 100,
        )

        for evaluator in evaluators:
            decision = evaluator()
            if decision is not None:
                logger.info(
                    "Selected action=%s confidence=%.2f risk=%s",
                    decision.action_id,
                    decision.confidence,
                    decision.risk_level,
                )
                return decision

        # Fallback
        decision = self._evaluate_mark_manual_review()
        logger.info("Fallback to action=%s", decision.action_id)
        return decision

    def execute_recovery(
        self, decision: AgentDecision | None = None
    ) -> ToolResult:
        """Log a recovery decision and produce a ``ConfigPatchProposal``.

        This method does **not** auto-modify configs.  It returns a
        ``ConfigPatchProposal`` that must be reviewed before application.

        Args:
            decision: The recovery decision to execute.  If *None*, calls
                :meth:`select_recovery_action` first.

        Returns:
            ``ToolResult`` with status, message, and optional config patch.
        """
        if decision is None:
            decision = self.select_recovery_action()

        action_def = WHITELIST_ACTIONS.get(decision.action_id, {})
        requires_approval = decision.requires_approval or action_def.get(
            "requires_approval", False
        )

        # Build config patch
        patch: dict[str, Any] = self._build_config_patch(decision)
        config_patch = ConfigPatchProposal(
            source_id=self.source_id,
            patch=patch,
            reason=decision.reason,
            requires_approval=requires_approval,
            action_id=decision.action_id,
        )

        status = "blocked" if requires_approval else "proposed"

        logger.info(
            "execute_recovery source=%s action=%s status=%s requires_approval=%s",
            self.source_id,
            decision.action_id,
            status,
            requires_approval,
        )

        return ToolResult(
            action_id=decision.action_id,
            status=status,
            message=(
                f"Recovery action '{decision.action_id}' {status} for source "
                f"'{self.source_id}'.  "
                f"{'Requires human approval.' if requires_approval else 'Ready to apply.'}"
            ),
            config_patch=config_patch,
            decision=decision,
        )

    def _build_config_patch(self, decision: AgentDecision) -> dict[str, Any]:
        """Translate an AgentDecision into a concrete config patch dict."""
        action_id = decision.action_id

        if action_id == "retry_same_source":
            return {
                "collector_config": {
                    "max_retries": decision.params.get("max_retries", 3),
                    "backoff_seconds": decision.params.get("backoff_seconds", 10),
                }
            }
        if action_id == "switch_entry_point":
            return {
                "page_entries": decision.params.get("candidate_entry_urls", []),
            }
        if action_id == "enable_detail_time_backfill":
            return {
                "collector_config": {
                    "detail_time_backfill": True,
                    "detail_time_backfill_limit": decision.params.get(
                        "detail_time_backfill_limit", 10
                    ),
                }
            }
        if action_id == "enable_browser_probe":
            return {
                "collector": "browser_probe",
                "collector_config": {
                    "probe_urls": decision.params.get("probe_urls", []),
                    "wait_seconds": decision.params.get("wait_seconds", 5),
                },
            }
        if action_id == "use_cache":
            return {
                "use_cache": True,
                "max_cache_age_hours": decision.params.get("max_cache_age_hours", 24),
            }
        if action_id == "mark_manual_review":
            return {
                "manual_review_required": True,
                "manual_review_reason": decision.params.get("reason", ""),
            }

        return {}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def run_source_recovery(
    source_id: str,
    diagnostics_dir: str,
    run_id: str,
) -> dict[str, Any]:
    """Main entry point for source recovery.

    Reads diagnostics artifacts from *diagnostics_dir*, runs the
    ``SourceRecoveryAgent``, and writes ``source_recovery_decisions.json``.

    Args:
        source_id: The source identifier to recover.
        diagnostics_dir: Directory containing diagnostics artifacts
            (``collector_diagnostics.json``, ``run_events.json``,
            ``page_samples.json``, ``source_health.json``).
        run_id: Identifier for this run.

    Returns:
        Dict with ``source_id``, ``decision``, ``execution``, and
        ``output_path`` keys.
    """
    # -- load diagnostics artifacts ------------------------------------------
    collector_diagnostics: dict[str, Any] = {}
    run_events: list[dict[str, Any]] = []
    page_samples: list[dict[str, Any]] = []
    source_health: dict[str, Any] = {}

    diag_path = os.path.join(diagnostics_dir, "collector_diagnostics.json")
    if os.path.isfile(diag_path):
        try:
            with open(diag_path, "r", encoding="utf-8") as fh:
                collector_diagnostics = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load %s: %s", diag_path, exc)

    events_path = os.path.join(diagnostics_dir, "run_events.json")
    if os.path.isfile(events_path):
        try:
            with open(events_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                run_events = data if isinstance(data, list) else data.get("events", [])
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load %s: %s", events_path, exc)

    samples_path = os.path.join(diagnostics_dir, "page_samples.json")
    if os.path.isfile(samples_path):
        try:
            with open(samples_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                page_samples = (
                    data if isinstance(data, list) else data.get("samples", [])
                )
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load %s: %s", samples_path, exc)

    health_path = os.path.join(diagnostics_dir, "source_health.json")
    if os.path.isfile(health_path):
        try:
            with open(health_path, "r", encoding="utf-8") as fh:
                source_health = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load %s: %s", health_path, exc)

    # -- filter to the target source -----------------------------------------
    source_page_samples = [
        s
        for s in page_samples
        if isinstance(s, dict) and str(s.get("source_id", "")) == source_id
    ]
    source_run_events = [
        e
        for e in run_events
        if isinstance(e, dict) and str(e.get("source_id", "")) == source_id
    ]

    # -- run agent -----------------------------------------------------------
    agent = SourceRecoveryAgent(
        source_id=source_id,
        source_health=source_health.get(source_id, {}),
        collector_diagnostics=collector_diagnostics,
        run_events=source_run_events,
        page_samples=source_page_samples,
    )

    decision = agent.select_recovery_action()
    result = agent.execute_recovery(decision)

    # -- serialize output ----------------------------------------------------
    output: dict[str, Any] = {
        "version": "0.1.0",
        "run_id": run_id,
        "source_id": source_id,
        "decision": {
            "action_id": decision.action_id,
            "params": decision.params,
            "reason": decision.reason,
            "risk_level": decision.risk_level,
            "requires_approval": decision.requires_approval,
            "confidence": decision.confidence,
        },
        "execution": {
            "status": result.status,
            "message": result.message,
        },
    }

    if result.config_patch is not None:
        output["config_patch_proposal"] = {
            "source_id": result.config_patch.source_id,
            "patch": result.config_patch.patch,
            "reason": result.config_patch.reason,
            "requires_approval": result.config_patch.requires_approval,
            "action_id": result.config_patch.action_id,
        }

    output_path = os.path.join(diagnostics_dir, "source_recovery_decisions.json")
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(output, fh, ensure_ascii=False, indent=2)

    logger.info(
        "Source recovery complete for source=%s action=%s output=%s",
        source_id,
        decision.action_id,
        output_path,
    )

    return {
        "source_id": source_id,
        "decision": output["decision"],
        "execution": output["execution"],
        "output_path": output_path,
    }
