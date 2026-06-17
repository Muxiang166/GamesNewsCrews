"""LangChain adapter v0 — project-native tool wrapper without langchain dependency.

Provides ToolWrapper with .invoke / .with_retry / schema contracts matching
the LangChain Runnable interface shape using only project dataclasses and
stdlib modules.  All tools log structured ToolResult (from agent_contracts.py)
instead of raw exceptions.

Concrete tools:
  - FetchDocumentTool       (wraps HttpFetcher.fetch_text)
  - SearchExpansionTool     (wraps run_search_expansion_provider)
  - SocialHeatProbeTool     (wraps run_discussion_probe_provider)
  - EvidenceRetrieverTool   (wraps retrieve_evidence)
  - StoryClusterReviewTool  (wraps StoryClusterReviewAgent)
"""

from __future__ import annotations

import copy
import logging
import time
from dataclasses import dataclass, field, fields as dc_fields
from enum import Enum
from typing import Any, Callable

from .agent_contracts import ToolResult, ToolStatus
from .fetching import HttpFetcher

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# JSON Schema helpers (stdlib only — no pydantic / langchain)
# ---------------------------------------------------------------------------

JSON_TYPE_MAP = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
    type(None): "null",
}


def _py_type_to_json_type(py_type: type | None) -> str:
    if py_type is None:
        return "string"
    return JSON_TYPE_MAP.get(py_type, "string")


def _make_property_schema(
    field_type: type,
    description: str = "",
    default: Any = None,
) -> dict[str, Any]:
    json_type = _py_type_to_json_type(field_type)
    prop: dict[str, Any] = {"type": json_type}
    if description:
        prop["description"] = description
    if default is not None:
        prop["default"] = default
    return prop


# Sentinel to mark a field as optional (not in "required").
_OPTIONAL = object()


def build_input_schema(schema_spec: dict[str, tuple[type, str, Any]]) -> dict[str, Any]:
    """Build a JSON Schema v7 object for tool inputs.

    ``schema_spec`` maps field name → (python_type, description, default).
    Fields whose default is ``_OPTIONAL`` are excluded from the
    ``required`` list — use this for optional parameters (e.g. ``timeout``).
    All other fields are ``required``.
    """
    properties: dict[str, Any] = {}
    required: list[str] = []
    for name, (py_type, desc, default) in schema_spec.items():
        properties[name] = _make_property_schema(py_type, description=desc, default=default)
        if default is not _OPTIONAL:
            required.append(name)
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def build_output_schema(schema_spec: dict[str, tuple[type, str]]) -> dict[str, Any]:
    """Build a JSON Schema v7 object for tool outputs."""
    properties: dict[str, Any] = {}
    for name, (py_type, desc) in schema_spec.items():
        properties[name] = _make_property_schema(py_type, description=desc)
    return {
        "type": "object",
        "properties": properties,
    }


# ---------------------------------------------------------------------------
# Retry policy
# ---------------------------------------------------------------------------


class RetryPolicy(Enum):
    """Controls transient-error retry behaviour for ToolWrapper."""

    ALWAYS = "always"
    NEVER = "never"


@dataclass(frozen=True)
class RetryConfig:
    stop_after_attempt: int = 1
    wait_between_seconds: tuple[float, float] = (0.5, 8.0)
    retryable_exceptions: tuple[type[BaseException], ...] = (
        ConnectionError,
        TimeoutError,
        OSError,
    )


# ---------------------------------------------------------------------------
# ToolWrapper
# ---------------------------------------------------------------------------


class ToolInvokeError(Exception):
    """Raised when ToolWrapper.invoke exhausts retries or hits a non-retryable error."""


@dataclass
class ToolWrapper:
    """Wraps a callable with input/output JSON schemas and retry support.

    Interface shape (Runnable-compatible):
        .invoke(input_dict) -> output_dict
        .with_retry(stop_after_attempt=3) -> ToolWrapper (configured clone)

    Every invocation returns a **result dict** on success.  Errors are
    logged as ToolResult artefacts but re-raised as ``ToolInvokeError``
    so that callers that need the raw message can catch it.
    """

    fn: Callable[..., Any]
    name: str = ""
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    retry_config: RetryConfig = field(default_factory=RetryConfig)

    # ------------------------------------------------------------------
    # Properties (matching LangChain tool.name / tool.description)
    # ------------------------------------------------------------------

    @property
    def tool_name(self) -> str:
        return self.name

    @property
    def tool_description(self) -> str:
        return self.description

    # ------------------------------------------------------------------
    # Schema helpers
    # ------------------------------------------------------------------

    def _validate_input(self, input_dict: dict[str, Any]) -> list[str]:
        """Validate input_dict against input_schema (best-effort).

        Returns a list of error messages (empty = valid).
        """
        errors: list[str] = []
        required = self.input_schema.get("required", [])
        for key in required:
            if key not in input_dict:
                errors.append(f"missing required field: {key!r}")
        if not isinstance(input_dict, dict):
            errors.append("input must be a dict")
        return errors

    # ------------------------------------------------------------------
    # Retry
    # ------------------------------------------------------------------

    def with_retry(self, stop_after_attempt: int = 3) -> "ToolWrapper":
        """Return a new ToolWrapper configured with the given retry count."""
        rc = RetryConfig(
            stop_after_attempt=max(int(stop_after_attempt), 1),
            wait_between_seconds=self.retry_config.wait_between_seconds,
            retryable_exceptions=self.retry_config.retryable_exceptions,
        )
        return ToolWrapper(
            fn=self.fn,
            name=self.name,
            description=self.description,
            input_schema=copy.deepcopy(self.input_schema),
            output_schema=copy.deepcopy(self.output_schema),
            retry_config=rc,
        )

    # ------------------------------------------------------------------
    # Invoke
    # ------------------------------------------------------------------

    def invoke(self, input_dict: dict[str, Any]) -> dict[str, Any]:
        """Execute the wrapped callable with retry on transient errors.

        Validates input, invokes ``fn(**input_dict)``, and returns the
        raw callable result on success.

        Raises ``ToolInvokeError`` on unrecoverable failure, including
        after retries are exhausted.
        """
        # Validate
        validation_errors = self._validate_input(input_dict)
        if validation_errors:
            tr = ToolResult(status="error", errors=validation_errors)
            logger.warning("ToolResult %s %s", self.name, tr)
            raise ToolInvokeError(
                f"{self.name} input validation failed: {'; '.join(validation_errors)}"
            )

        last_exception: Exception | None = None
        for attempt in range(1, self.retry_config.stop_after_attempt + 1):
            try:
                result = self.fn(**input_dict)
                return result
            except self.retry_config.retryable_exceptions as exc:
                last_exception = exc
                if attempt < self.retry_config.stop_after_attempt:
                    wait = min(
                        self.retry_config.wait_between_seconds[0] * (2 ** (attempt - 1)),
                        self.retry_config.wait_between_seconds[1],
                    )
                    logger.debug(
                        "%s attempt %d/%d failed (retryable): %s — waiting %.1fs",
                        self.name,
                        attempt,
                        self.retry_config.stop_after_attempt,
                        exc,
                        wait,
                    )
                    time.sleep(wait)
                    continue
                break
            except Exception as exc:
                last_exception = exc
                # Non-retryable — do not retry
                break

        # All retries exhausted or non-retryable error
        tr = ToolResult(status="error", errors=[str(last_exception)])
        logger.error("ToolResult %s %s", self.name, tr)
        raise ToolInvokeError(
            f"{self.name} failed after {attempt} attempt(s): {last_exception}"
        )

    # ------------------------------------------------------------------
    # Convenience: run and return ToolResult
    # ------------------------------------------------------------------

    def run(self, input_dict: dict[str, Any]) -> ToolResult:
        """Invoke and wrap result in a ToolResult envelope.

        Unlike ``invoke``, this method **never raises** — errors are
        captured in the returned ToolResult.
        """
        try:
            output = self.invoke(input_dict)
            return ToolResult(
                status="ok",
                metrics_delta={"tool": self.name, "input_keys": list(input_dict.keys())},
            )
        except ToolInvokeError as exc:
            return ToolResult(status="error", errors=[str(exc)])


# ===================================================================
# Concrete tool definitions
# ===================================================================

# -------------------------------------------------------------------
# FetchDocumentTool
# -------------------------------------------------------------------

_FETCH_INPUT_SCHEMA = build_input_schema(
    {
        "url": (str, "Document URL to fetch", ""),
        "timeout": (float, "Optional per-request timeout override", _OPTIONAL),
    }
)

_FETCH_OUTPUT_SCHEMA = build_output_schema(
    {
        "ok": (bool, "Whether the fetch succeeded"),
        "status_code": (int, "HTTP status code, if any"),
        "text": (str, "Decoded response body text"),
        "content_type": (str, "Response content-type header"),
        "attempts": (list, "Per-attempt diagnostic records"),
    }
)


def _build_fetch_document_tool(fetcher: HttpFetcher | None = None) -> ToolWrapper:
    """Create a FetchDocumentTool wrapping an HttpFetcher instance."""
    f = fetcher or HttpFetcher()

    def _fetch(url: str, timeout: float | None = None) -> dict[str, Any]:
        result = f.fetch_text(url, timeout=timeout)
        return {
            "ok": result.ok,
            "status_code": result.status_code,
            "text": result.text,
            "content_type": result.content_type,
            "attempts": result.attempts,
        }

    return ToolWrapper(
        fn=_fetch,
        name="FetchDocumentTool",
        description="Fetch a document by URL with retry and charset detection. "
        "Returns ok/status_code/text/content_type/attempts.",
        input_schema=_FETCH_INPUT_SCHEMA,
        output_schema=_FETCH_OUTPUT_SCHEMA,
        retry_config=RetryConfig(stop_after_attempt=3),
    )


# -------------------------------------------------------------------
# SearchExpansionTool
# -------------------------------------------------------------------

_SEARCH_EXPANSION_INPUT_SCHEMA = build_input_schema(
    {
        "query": (str, "Search query text", ""),
        "platform": (str, "Target platform (bilibili, weibo, etc.)", ""),
        "max_results": (int, "Maximum number of observation results", _OPTIONAL),
    }
)

_SEARCH_EXPANSION_OUTPUT_SCHEMA = build_output_schema(
    {
        "results": (list, "List of search observation dicts"),
        "platform": (str, "Platform searched"),
        "status": (str, "Result status string"),
    }
)


def _build_search_expansion_tool(fetcher: HttpFetcher | None = None) -> ToolWrapper:
    """Create a SearchExpansionTool wrapping run_search_expansion_provider.

    Uses the public-search probe pipeline to evaluate search targets
    for a given query on a given platform.
    """
    from .discussion_probe_provider import run_discussion_probe_provider, empty_discussion_probe_provider_report
    from .search_expansion import _search_target

    f = fetcher or HttpFetcher()

    def _search(query: str, platform: str, max_results: int = 5) -> dict[str, Any]:
        target = _search_target(platform, query)
        request = {
            "candidate_url": f"search-expansion://adapter/{platform}",
            "candidate_title": query,
            "query": query,
            "search_targets": [target],
        }
        report = run_discussion_probe_provider(
            [request],
            fetcher=f,
            candidate_limit=1,
            platform_limit=1,
        )
        observations = report.get("observations", [])
        summary = report.get("summary", {})
        return {
            "results": observations[: max_results],
            "platform": platform,
            "status": "ok" if summary.get("ok", 0) > 0 else "no_results",
        }

    return ToolWrapper(
        fn=_search,
        name="SearchExpansionTool",
        description="Execute a low-frequency public search observation for a "
        "query on a given platform. Returns observation results.",
        input_schema=_SEARCH_EXPANSION_INPUT_SCHEMA,
        output_schema=_SEARCH_EXPANSION_OUTPUT_SCHEMA,
        retry_config=RetryConfig(stop_after_attempt=2),
    )


# -------------------------------------------------------------------
# SocialHeatProbeTool
# -------------------------------------------------------------------

_SOCIAL_HEAT_INPUT_SCHEMA = build_input_schema(
    {
        "candidate_title": (str, "Candidate story title", ""),
        "candidate_url": (str, "Candidate source URL", ""),
        "platforms": (list, "List of platform names to probe", _OPTIONAL),
    }
)

_SOCIAL_HEAT_OUTPUT_SCHEMA = build_output_schema(
    {
        "observations": (list, "Normalized social heat observations"),
        "summary": (dict, "Aggregate summary by platform/status/heat-validity"),
    }
)


def _build_social_heat_probe_tool(fetcher: HttpFetcher | None = None) -> ToolWrapper:
    """Create a SocialHeatProbeTool wrapping discussion_probe_provider.

    Probes social-platform search pages for a candidate and returns
    normalized observations with a summary.
    """
    from .discussion_probe_provider import (
        run_discussion_probe_provider,
        build_provider_discussion_profile,
    )
    from .social_heat import (
        observations_from_discussion_provider_report,
        normalize_social_heat_observation,
        build_social_heat_summary,
    )
    from .social_heat import default_social_platform_profiles

    f = fetcher or HttpFetcher()

    def _probe(
        candidate_title: str,
        candidate_url: str,
        platforms: list[str] | None = None,
    ) -> dict[str, Any]:
        profiles = default_social_platform_profiles()
        requested = [p.lower() for p in (platforms or [])]
        if requested:
            profiles = [p for p in profiles if p["platform"] in requested]
        # Fall back to public-search-first platforms
        from .social_heat import public_search_first_batch_platforms
        if not profiles:
            first = public_search_first_batch_platforms()
            profiles = [p for p in default_social_platform_profiles() if p["platform"] in first]

        targets: list[dict[str, Any]] = []
        for profile in profiles:
            query = f"{candidate_title} 热议"
            if profile["platform"] == "bilibili":
                from urllib.parse import quote_plus
                url = f"https://search.bilibili.com/all?keyword={quote_plus(query)}"
            elif profile["platform"] == "steam_discussions":
                from urllib.parse import quote_plus
                url = f"https://steamcommunity.com/search/?q={quote_plus(query)}"
            else:
                url = ""
            targets.append({
                "platform": profile["platform"],
                "query": query,
                "url": url,
                "access": profile.get("default_access_mode", "public_search"),
            })

        probe_request = {
            "candidate_url": candidate_url,
            "candidate_title": candidate_title,
            "query": candidate_title,
            "search_targets": targets,
        }

        report = run_discussion_probe_provider(
            [probe_request],
            fetcher=f,
            candidate_limit=1,
            platform_limit=len(targets),
        )
        observations = observations_from_discussion_provider_report(report)
        summary = build_social_heat_summary(observations)
        return {
            "observations": observations,
            "summary": summary,
        }

    return ToolWrapper(
        fn=_probe,
        name="SocialHeatProbeTool",
        description="Probe social platforms for discussion heat signals "
        "around a candidate title/URL. Returns normalized observations "
        "and a summary.",
        input_schema=_SOCIAL_HEAT_INPUT_SCHEMA,
        output_schema=_SOCIAL_HEAT_OUTPUT_SCHEMA,
        retry_config=RetryConfig(stop_after_attempt=2),
    )


# -------------------------------------------------------------------
# EvidenceRetrieverTool
# -------------------------------------------------------------------

_EVIDENCE_RET_INPUT_SCHEMA = build_input_schema(
    {
        "claim_or_story": (str, "Claim text, story dict, or query string", ""),
        "db_path": (str, "Optional path to SQLite mirror DB", _OPTIONAL),
        "max_results": (int, "Maximum evidence packs to return", _OPTIONAL),
    }
)

_EVIDENCE_RET_OUTPUT_SCHEMA = build_output_schema(
    {
        "evidence_packs": (list, "List of evidence pack dicts"),
        "total_found": (int, "Total number of matching evidence packs found"),
        "query": (str, "Derived query text used"),
        "retriever": (str, "Retrieval method used (fts5/bm25/keyword/none)"),
    }
)


def _build_evidence_retriever_tool() -> ToolWrapper:
    """Create an EvidenceRetrieverTool wrapping retrieve_evidence."""
    from .retrieval import retrieve_evidence

    def _retrieve(
        claim_or_story: str,
        db_path: str | None = None,
        max_results: int = 5,
    ) -> dict[str, Any]:
        result = retrieve_evidence(
            claim_or_story,
            db_path=db_path,
            max_results=max(max_results, 1),
        )
        packs = result.get("packs", [])
        return {
            "evidence_packs": packs,
            "total_found": len(packs),
            "query": result.get("query", ""),
            "retriever": result.get("retriever", "none"),
        }

    return ToolWrapper(
        fn=_retrieve,
        name="EvidenceRetrieverTool",
        description="Retrieve evidence packs for a claim or story using FTS5, "
        "BM25, or keyword fallback. Returns evidence packs with relevance scores.",
        input_schema=_EVIDENCE_RET_INPUT_SCHEMA,
        output_schema=_EVIDENCE_RET_OUTPUT_SCHEMA,
        retry_config=RetryConfig(stop_after_attempt=1),
    )


# -------------------------------------------------------------------
# StoryClusterReviewTool
# -------------------------------------------------------------------

_STORY_CLUSTER_INPUT_SCHEMA = build_input_schema(
    {
        "review_request": (dict, "Dedup review request with candidates", None),
        "context_packs": (list, "Context packs with candidate details per cluster", _OPTIONAL),
        "evidence_chunks": (list, "Optional evidence chunks from fetched documents", _OPTIONAL),
    }
)

_STORY_CLUSTER_OUTPUT_SCHEMA = build_output_schema(
    {
        "decisions": (list, "List of per-pair review decisions"),
        "request_id": (str, "Review request identifier"),
        "entity": (str, "Entity that triggered the dedup grouping"),
        "dominant_role": (str, "Dominant cluster relationship classification"),
        "overall_confidence": (float, "Aggregate confidence score for dominant role"),
    }
)


def _build_story_cluster_review_tool() -> ToolWrapper:
    """Create a StoryClusterReviewTool wrapping StoryClusterReviewAgent."""
    from .story_cluster_review_agent import StoryClusterReviewAgent

    def _review(
        review_request: dict[str, Any],
        context_packs: list[dict[str, Any]] | None = None,
        evidence_chunks: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        agent = StoryClusterReviewAgent(
            dedup_semantic_review_requests=[review_request],
            context_packs=context_packs or [],
            evidence_chunks=evidence_chunks or [],
        )
        results = agent.review_all()
        if results:
            first = results[0]
            return {
                "decisions": first.get("decisions", []),
                "request_id": first.get("request_id", ""),
                "entity": first.get("entity", ""),
                "dominant_role": first.get("dominant_role", "unrelated"),
                "overall_confidence": first.get("overall_confidence", 0.0),
            }
        return {
            "decisions": [],
            "request_id": review_request.get("request_id", ""),
            "entity": review_request.get("entity", ""),
            "dominant_role": "unrelated",
            "overall_confidence": 0.0,
        }

    return ToolWrapper(
        fn=_review,
        name="StoryClusterReviewTool",
        description="Review ambiguous story-cluster relationships using "
        "deterministic heuristics. Compares title Jaccard, entity overlap, "
        "time proximity, and keyword signals to classify cluster pairs.",
        input_schema=_STORY_CLUSTER_INPUT_SCHEMA,
        output_schema=_STORY_CLUSTER_OUTPUT_SCHEMA,
        retry_config=RetryConfig(stop_after_attempt=1),
    )


# ===================================================================
# Tool registry
# ===================================================================

TOOL_REGISTRY: dict[str, ToolWrapper] = {}


def _populate_default_registry() -> None:
    """Create default tool instances and register them."""
    fetcher = HttpFetcher()
    TOOL_REGISTRY.clear()
    TOOL_REGISTRY["FetchDocumentTool"] = _build_fetch_document_tool(fetcher)
    TOOL_REGISTRY["SearchExpansionTool"] = _build_search_expansion_tool(fetcher)
    TOOL_REGISTRY["SocialHeatProbeTool"] = _build_social_heat_probe_tool(fetcher)
    TOOL_REGISTRY["EvidenceRetrieverTool"] = _build_evidence_retriever_tool()
    TOOL_REGISTRY["StoryClusterReviewTool"] = _build_story_cluster_review_tool()


# Populate at import time
_populate_default_registry()


# ===================================================================
# Public API
# ===================================================================


def get_tool(tool_name: str) -> ToolWrapper:
    """Look up a registered tool by name.

    Raises ``KeyError`` if the tool is not found.
    """
    if tool_name not in TOOL_REGISTRY:
        raise KeyError(
            f"Tool {tool_name!r} not found in registry. "
            f"Available: {sorted(TOOL_REGISTRY.keys())}"
        )
    return TOOL_REGISTRY[tool_name]


def run_tool(tool_name: str, input_dict: dict[str, Any]) -> ToolResult:
    """Run a registered tool and return a structured ToolResult.

    ToolResult (from agent_contracts.py) encodes status, errors,
    warnings, and metrics_delta in a frozen envelope.  This function
    never raises — failures are captured in the result status.
    """
    try:
        tool = get_tool(tool_name)
    except KeyError as exc:
        return ToolResult(status="error", errors=[str(exc)])
    return tool.run(input_dict)


def register_tool(tool_name: str, tool: ToolWrapper) -> None:
    """Register (or replace) a tool in the global registry."""
    TOOL_REGISTRY[tool_name] = tool


def list_tools() -> list[str]:
    """Return the names of all registered tools."""
    return sorted(TOOL_REGISTRY.keys())
