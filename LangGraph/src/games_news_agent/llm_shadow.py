"""LLM shadow tasks v0 — advisory LLM calls that run after the main pipeline.

Shadow tasks produce separate *_shadow_results.json and *_shadow_failures.json
artifacts. They MUST NOT modify PipelineState, claim_verifications, stories,
or any main-flow artifact. The roadmap says:

    LLM 输出 JSON 建议与人工评审包，不直接改最终事实或排序.

Each shadow task follows the LLM artifact contract from the roadmap (lines
1257-1263): every task has a task_type, references input artifacts,
uses prompt_registry.json for configuration, and writes structured results
or failures with fallback semantics.
"""

from __future__ import annotations

import json
import os
import time as _time
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .llm_provider import (
    LlmConfig,
    OpenAICompatibleVerifierClient,
    load_llm_config,
    _messages_for_json_request,
    _provider_error_json_result,
)
from .prompt_registry import (
    build_prompt_failure,
    get_prompt_config,
    load_prompt_registry,
    record_prompt_failure,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SHADOW_TASK_TYPES = frozenset(
    {
        "query_compression",
        "search_relevance",
        "story_cluster_review",
        "editorial_judgment",
    }
)

SHADOW_SCHEMA_VERSION = "llm_shadow_v0"


# ---------------------------------------------------------------------------
# LLMShadowTask
# ---------------------------------------------------------------------------


@dataclass
class LLMShadowTask:
    """One shadow task execution with full audit trail.

    Fields match the LLM artifact contract: task_type, prompt_id,
    input_artifact_refs, status, output, failure, token_usage, model,
    started_at, ended_at.
    """

    task_type: str
    prompt_id: str
    input_artifact_refs: list[str] = field(default_factory=list)
    status: str = "pending"
    output: dict[str, Any] = field(default_factory=dict)
    failure: dict[str, Any] | None = None
    token_usage: dict[str, int] = field(
        default_factory=lambda: {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    )
    model: str = ""
    started_at: str = ""
    ended_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_type": self.task_type,
            "prompt_id": self.prompt_id,
            "input_artifact_refs": list(self.input_artifact_refs),
            "status": self.status,
            "output": deepcopy(self.output),
            "failure": deepcopy(self.failure) if self.failure else None,
            "token_usage": dict(self.token_usage),
            "model": self.model,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LLMShadowTask":
        return cls(
            task_type=data.get("task_type", ""),
            prompt_id=data.get("prompt_id", ""),
            input_artifact_refs=list(data.get("input_artifact_refs", [])),
            status=data.get("status", "pending"),
            output=dict(data.get("output", {})),
            failure=dict(data.get("failure")) if data.get("failure") else None,
            token_usage={
                "prompt_tokens": int(data.get("token_usage", {}).get("prompt_tokens", 0)),
                "completion_tokens": int(data.get("token_usage", {}).get("completion_tokens", 0)),
                "total_tokens": int(data.get("token_usage", {}).get("total_tokens", 0)),
            },
            model=str(data.get("model", "")),
            started_at=str(data.get("started_at", "")),
            ended_at=str(data.get("ended_at", "")),
        )


# ---------------------------------------------------------------------------
# build_shadow_request
# ---------------------------------------------------------------------------


def build_shadow_request(
    task_type: str,
    prompt_registry: dict[str, Any],
    input_data: dict[str, Any],
    *,
    sample_index: int = 0,
) -> LLMShadowTask:
    """Prepare a shadow task from the prompt registry and input data.

    Args:
        task_type: One of the SHADOW_TASK_TYPES values.
        prompt_registry: Loaded prompt_registry.json dict.
        input_data: Mapping of artifact names to their loaded contents.
            Keys must include all artifacts declared in the prompt config's
            ``input_artifacts``.
        sample_index: Ordinal index for traceability in the request_id.

    Returns:
        A prepared :class:`LLMShadowTask` with ``status="pending"``.

    Raises:
        ValueError: If *task_type* is not a recognised shadow task type,
            or if required input artifacts are missing from *input_data*.
    """
    if task_type not in SHADOW_TASK_TYPES:
        raise ValueError(
            f"Unknown shadow task_type '{task_type}'. "
            f"Allowed: {sorted(SHADOW_TASK_TYPES)}"
        )

    prompt_config = get_prompt_config(task_type, prompt_registry)
    required_artifacts = prompt_config.get("input_artifacts", [])

    # Validate that all required input artifacts are present
    missing = [a for a in required_artifacts if a not in input_data]
    if missing:
        raise ValueError(
            f"Shadow task '{task_type}' requires input artifacts {required_artifacts!r}; "
            f"missing: {missing!r}"
        )

    return LLMShadowTask(
        task_type=task_type,
        prompt_id=str(prompt_config.get("prompt_id") or task_type),
        input_artifact_refs=list(required_artifacts),
        status="pending",
        output={},
        failure=None,
        token_usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        model="",
        started_at="",
        ended_at="",
    )


# ---------------------------------------------------------------------------
# LLM request construction helpers
# ---------------------------------------------------------------------------


def _build_shadow_llm_request(
    task: LLMShadowTask,
    prompt_config: dict[str, Any],
    input_data: dict[str, Any],
) -> dict[str, Any]:
    """Build an LLM JSON request dict from a shadow task.

    This reuses the same message serialisation pattern as
    ``_messages_for_json_request`` in ``llm_provider.py``.
    """
    compact_input = _compact_shadow_input(task.task_type, input_data)
    request_id = f"shadow_{task.task_type}_{hash(json.dumps(compact_input, sort_keys=True, default=str)) % 10**8:08d}"

    return {
        "request_id": request_id,
        "instructions": (
            f"Execute shadow task '{task.task_type}'. "
            "Return only valid JSON matching the output schema. "
            "Do not add facts. Do not invent sources."
        ),
        "task_type": task.task_type,
        "prompt_id": task.prompt_id,
        "input_artifact_refs": task.input_artifact_refs,
        "input_data": compact_input,
        "output_schema": prompt_config.get("output_schema", ""),
        "json_schema": {},
    }


def _trim_text(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _copy_fields(item: dict[str, Any], fields: list[str], *, text_limit: int = 360) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for field in fields:
        if field not in item:
            continue
        value = item.get(field)
        if isinstance(value, str):
            compact[field] = _trim_text(value, text_limit)
        elif isinstance(value, (int, float, bool)) or value is None:
            compact[field] = value
        elif isinstance(value, list):
            compact[field] = value[:8]
        elif isinstance(value, dict):
            compact[field] = {
                str(key): val
                for key, val in list(value.items())[:12]
                if isinstance(val, (str, int, float, bool)) or val is None
            }
    return compact


def _compact_candidate(item: dict[str, Any]) -> dict[str, Any]:
    fields = [
        "title",
        "url",
        "source_id",
        "published_at",
        "observed_at",
        "theme_section",
        "candidate_type",
        "candidate_lane",
        "snippet",
        "heat_score",
        "discussion_score",
        "discussion_level",
        "editorial_intent",
        "editorial_priority",
        "tags",
        "memory_status",
        "reject_reason",
    ]
    compact = _copy_fields(item, fields, text_limit=420)
    if "snippet" in compact:
        compact["snippet"] = _trim_text(compact["snippet"], 360)
    return compact


def _compact_story_candidate(item: dict[str, Any]) -> dict[str, Any]:
    fields = [
        "id",
        "story_id",
        "title",
        "url",
        "source_id",
        "source_urls",
        "published_at",
        "theme_section",
        "category",
        "status",
        "score",
        "story_score",
        "heat_score",
        "discussion_score",
        "discussion_level",
        "editorial_fit_score",
        "editorial_intent",
        "story_editorial_intent",
        "editorial_priority",
        "source_preference",
        "source_language",
    ]
    return _copy_fields(item, fields, text_limit=420)


def _compact_evidence(item: dict[str, Any]) -> dict[str, Any]:
    compact = _copy_fields(
        item,
        ["chunk_id", "url", "source_id", "title", "published_at", "quote", "credibility_hint"],
        text_limit=360,
    )
    if "quote" in compact:
        compact["quote"] = _trim_text(compact["quote"], 700)
    return compact


def _compact_context_pack(item: dict[str, Any]) -> dict[str, Any]:
    candidate = item.get("candidate") if isinstance(item.get("candidate"), dict) else {}
    evidence = item.get("evidence") if isinstance(item.get("evidence"), list) else []
    return {
        "candidate": _compact_candidate(candidate),
        "evidence_scope": str(item.get("evidence_scope") or ""),
        "missing_fields": list(item.get("missing_fields") or [])[:8],
        "evidence": [
            _compact_evidence(evidence_item)
            for evidence_item in evidence[:2]
            if isinstance(evidence_item, dict)
        ],
    }


def _compact_search_result(item: dict[str, Any]) -> dict[str, Any]:
    return _copy_fields(
        item,
        [
            "title",
            "url",
            "source_id",
            "platform",
            "query",
            "snippet",
            "published_at",
            "observed_at",
            "result_published_at",
            "result_metadata",
            "same_event",
            "same_game",
            "is_current_window",
            "risk_flags",
        ],
        text_limit=360,
    )


def _compact_shadow_input(task_type: str, input_data: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for artifact_name, value in input_data.items():
        if artifact_name == "candidates" and isinstance(value, list):
            compact[artifact_name] = [
                _compact_candidate(item) for item in value[:3] if isinstance(item, dict)
            ]
        elif artifact_name == "story_candidates" and isinstance(value, list):
            compact[artifact_name] = [
                _compact_story_candidate(item) for item in value[:3] if isinstance(item, dict)
            ]
        elif artifact_name == "context_packs" and isinstance(value, list):
            compact[artifact_name] = [
                _compact_context_pack(item) for item in value[:2] if isinstance(item, dict)
            ]
        elif artifact_name in {"search_expansion_candidates", "search_expansion_observations"} and isinstance(value, list):
            compact[artifact_name] = [
                _compact_search_result(item) for item in value[:3] if isinstance(item, dict)
            ]
        elif isinstance(value, list):
            compact[artifact_name] = value[:3]
        else:
            compact[artifact_name] = value
    compact["_shadow_input_compaction"] = {
        "task_type": task_type,
        "policy": "small_sample_core_fields_v0",
    }
    return compact


def _parse_shadow_response(
    request_id: str,
    content: str,
    prompt_config: dict[str, Any],
) -> dict[str, Any]:
    """Parse the LLM shadow response, returning structured output or error.

    On valid JSON: returns {"parse_status": "ok", "output": parsed}.
    On invalid JSON: returns {"parse_status": "invalid_json", "output": {}}.
    """
    # Attempt JSON repair for common LLM mistakes (PRM-006)
    from .editorial_judgment import _try_repair_json

    parse_status = "ok"
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        repaired = _try_repair_json(content)
        if repaired is not None:
            try:
                payload = json.loads(repaired)
                parse_status = "ok_repaired"
            except json.JSONDecodeError:
                return {
                    "request_id": request_id,
                    "parse_status": "invalid_json",
                    "output": {},
                    "error": "LLM response was not valid JSON.",
                }
        else:
            return {
                "request_id": request_id,
                "parse_status": "invalid_json",
                "output": {},
                "error": "LLM response was not valid JSON.",
            }
    if not isinstance(payload, dict):
        return {
            "request_id": request_id,
            "parse_status": "invalid_schema",
            "output": {},
            "error": "LLM response JSON root was not an object.",
        }
    return {
        "request_id": request_id,
        "parse_status": parse_status,
        "output": payload,
        "error": "",
    }


# ---------------------------------------------------------------------------
# PRM-006 / SHD-004: Shadow output validation gate
# ---------------------------------------------------------------------------

# Required fields per shadow task_type.  If any required field is missing
# or empty, the shadow result is downgraded to fallback.
SHADOW_REQUIRED_FIELDS: dict[str, list[str]] = {
    # These fields mirror the current prompt files, not a separate imagined
    # schema. Keep this table in sync with LangGraph/prompts/*.md.
    "story_cluster_review": ["cluster_relationship", "confidence", "reason"],
    "editorial_judgment": ["judgment", "game_relevance", "publishability", "reason"],
}

# Cross-field checks: (field_a, field_b, rule_description, predicate)
# If predicate(field_a_value, field_b_value) returns True, it's a violation.
SHADOW_CROSS_FIELD_CHECKS: dict[str, list[dict[str, Any]]] = {
    "editorial_judgment": [
        {
            "field_a": "game_relevance",
            "field_b": "publishability",
            "description": "off_topic but publishable",
            "violation": lambda g, p: str(g).strip() == "off_topic" and str(p).strip() == "publishable",
        },
        {
            "field_a": "judgment",
            "field_b": "publishability",
            "description": "rejected but publishable",
            "violation": lambda j, p: str(j).strip() == "reject" and str(p).strip() == "publishable",
        },
    ],
}


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "yes", "1"}:
        return True
    if text in {"false", "no", "0"}:
        return False
    return None


def _normalize_query_compression_output(output: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    normalized = dict(output)
    fixes: list[str] = []
    queries = normalized.get("queries")
    compressed = normalized.get("compressed_queries")

    if not isinstance(queries, list) and isinstance(compressed, list):
        extracted: list[str] = []
        for item in compressed:
            if isinstance(item, str) and item.strip():
                extracted.append(item.strip())
            elif isinstance(item, dict) and str(item.get("query") or "").strip():
                extracted.append(str(item.get("query")).strip())
        if extracted:
            normalized["queries"] = extracted[:3]
            fixes.append("normalized:compressed_queries_to_queries")

    if "entities" not in normalized or not isinstance(normalized.get("entities"), dict):
        normalized["entities"] = {}
    if "risk_flags" not in normalized or not isinstance(normalized.get("risk_flags"), list):
        normalized["risk_flags"] = []
    return normalized, fixes


def _validate_query_compression_output(output: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    normalized, fixes = _normalize_query_compression_output(output)
    violations: list[str] = []
    queries = normalized.get("queries")
    if not isinstance(queries, list) or not any(str(item).strip() for item in queries):
        violations.append("missing_required_field:queries")
    else:
        normalized["queries"] = [str(item).strip() for item in queries if str(item).strip()][:3]
    if "confidence" in normalized and not isinstance(normalized.get("confidence"), (int, float)):
        violations.append("invalid_field:confidence")
    if fixes:
        normalized["_normalization_fixes"] = fixes
    return normalized, violations


def _search_relevance_records(output: dict[str, Any]) -> list[dict[str, Any]]:
    records = output.get("results")
    if isinstance(records, list):
        return [item for item in records if isinstance(item, dict)]
    if output.get("relevance") is not None:
        return [output]
    return []


def _normalize_search_relevance_output(output: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    normalized = dict(output)
    fixes: list[str] = []
    records = _search_relevance_records(normalized)

    def normalize_record(record: dict[str, Any]) -> dict[str, Any]:
        item = dict(record)
        if "current_window_valid" not in item and "is_current_window" in item:
            item["current_window_valid"] = item.get("is_current_window")
            fixes.append("normalized:is_current_window_to_current_window_valid")
        if "reason" not in item and str(item.get("reject_reason") or "").strip():
            item["reason"] = str(item.get("reject_reason") or "").strip()
            fixes.append("normalized:reject_reason_to_reason")
        return item

    if "results" in normalized and isinstance(normalized.get("results"), list):
        normalized["results"] = [normalize_record(item) for item in records]
    elif records:
        normalized = normalize_record(records[0])
    return normalized, fixes


def _validate_search_relevance_output(
    output: dict[str, Any],
    input_data: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    normalized, fixes = _normalize_search_relevance_output(output)
    violations: list[str] = []
    records = _search_relevance_records(normalized)
    if not records:
        violations.append("missing_required_field:results_or_relevance")
        return normalized, violations

    for index, record in enumerate(records):
        prefix = f"results[{index}]" if "results" in normalized else "result"
        relevance = str(record.get("relevance") or "").strip()
        same_game = _as_bool(record.get("same_game"))
        same_event = _as_bool(record.get("same_event"))
        current_window = _as_bool(record.get("current_window_valid"))
        reason = str(record.get("reason") or record.get("reject_reason") or "").strip()
        if not relevance:
            violations.append(f"missing_required_field:{prefix}.relevance")
        if same_game is None:
            violations.append(f"missing_required_field:{prefix}.same_game")
        if same_event is None:
            violations.append(f"missing_required_field:{prefix}.same_event")
        if current_window is None:
            violations.append(f"missing_required_field:{prefix}.current_window_valid")
        if not reason:
            violations.append(f"missing_required_field:{prefix}.reason")
        if relevance == "same_game" and same_game is False:
            violations.append(f"inconsistent:{prefix}.relevance=same_game but same_game=false")
        if relevance == "same_event" and same_event is False:
            violations.append(f"inconsistent:{prefix}.relevance=same_event but same_event=false")
        if reason and _is_shadow_reason_echo("search_relevance", reason, input_data):
            violations.append(f"echo_detected:{prefix}.reason_mirrors_input")

    if fixes:
        normalized["_normalization_fixes"] = fixes
    return normalized, violations


def _validate_shadow_output(
    task_type: str,
    output: dict[str, Any],
    input_data: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """PRM-006 / SHD-004: Validate shadow LLM output for structural integrity.

    Checks:
    1. Required fields exist and are non-empty
    2. Cross-field consistency (no contradictory values)
    3. Echo detection (output doesn't just parrot input)

    Returns ``(normalized_output, violation_flags)``.  If violation_flags is
    non-empty the caller should treat this as a fallback.
    """
    if task_type == "query_compression":
        return _validate_query_compression_output(output)
    if task_type == "search_relevance":
        return _validate_search_relevance_output(output, input_data)

    violations: list[str] = []

    # ---- Check 1: Required fields ----
    required = SHADOW_REQUIRED_FIELDS.get(task_type, [])
    for field in required:
        value = output.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            violations.append(f"missing_required_field:{field}")

    # ---- Check 2: Cross-field consistency ----
    checks = SHADOW_CROSS_FIELD_CHECKS.get(task_type, [])
    for check in checks:
        field_a = output.get(check["field_a"])
        field_b = output.get(check["field_b"])
        try:
            if check["violation"](field_a, field_b):
                violations.append(f"inconsistent:{check['description']}")
        except Exception:
            pass  # Don't crash on type mismatches — those are separate issues

    # ---- Check 3: Echo detection ----
    reason = str(output.get("reason", "")).strip()
    if task_type in ("search_relevance", "editorial_judgment") and len(reason) < 10:
        violations.append("reason_too_short")

    normalized = dict(output)

    # Detect echo: does the output mainly restate input fields?
    if task_type == "editorial_judgment":
        candidate = input_data.get("story_candidates") or input_data.get("candidates") or [{}]
        candidate_item = candidate[0] if isinstance(candidate, list) and candidate else {}
        from .editorial_judgment import _detect_echo
        if _detect_echo(normalized, candidate_item):
            violations.append("echo_detected")

    return normalized, violations


def _is_shadow_reason_echo(task_type: str, reason: str, input_data: dict[str, Any]) -> bool:
    """Check if a shadow reason is just echoing input fields verbatim."""
    candidate_texts: list[str] = []

    # Collect candidate titles/snippets from input
    for key in ("candidates", "story_candidates", "search_expansion_candidates"):
        items = input_data.get(key, [])
        if isinstance(items, list):
            for item in items[:3]:
                if isinstance(item, dict):
                    candidate_texts.append(str(item.get("title", "")))
                    candidate_texts.append(str(item.get("snippet", "")))

    combined_input = " ".join(t for t in candidate_texts if t).strip()
    if not combined_input or len(combined_input) < 20:
        return False

    # If reason is entirely contained in input text, it's an echo
    if reason in combined_input:
        return True

    # If the first 80 chars of reason match the first 80 chars of some input field
    for text in candidate_texts:
        if len(text) > 20 and text[:80] == reason[:80]:
            return True

    return False


# ---------------------------------------------------------------------------
# execute_shadow_task
# ---------------------------------------------------------------------------


def execute_shadow_task(
    task: LLMShadowTask,
    llm_client: OpenAICompatibleVerifierClient,
    prompt_config: dict[str, Any],
    input_data: dict[str, Any],
    output_dir: str | Path,
) -> LLMShadowTask:
    """Execute a single shadow task and write result/failure artifacts.

    On success: writes ``<task_type>_shadow_results.json`` with the parsed
    LLM output alongside task metadata.

    On failure: writes ``<task_type>_shadow_failures.json`` with a
    ``prompt_failure`` structure and logs that fallback was used.

    **NEVER** raises — always returns the task with status updated.
    Token usage is always recorded.

    Args:
        task: A pending :class:`LLMShadowTask` to execute.
        llm_client: An initialized OpenAI-compatible LLM client.
        prompt_config: The prompt registry config for this task_type.
        input_data: The loaded input artifacts.
        output_dir: Directory to write shadow artifacts into.

    Returns:
        The same task object with status updated to one of
        ``"success"``, ``"failure"``, or ``"fallback_used"``.
    """
    output_path = Path(output_dir)
    task.started_at = datetime.now(timezone.utc).isoformat()

    # Build the request
    llm_request = _build_shadow_llm_request(task, prompt_config, input_data)
    request_id = llm_request["request_id"]

    fallback_strategy = prompt_config.get("fallback", "")

    # Attempt the LLM call
    try:
        # Reuse the same HTTP call pattern as llm_provider.py
        result = _call_llm_for_shadow(llm_client, llm_request)
    except Exception as exc:
        # Provider-level failure
        task.status = "fallback_used"
        failure = build_prompt_failure(
            prompt_id=task.prompt_id,
            error_type="provider_error",
            details={
                "task_type": task.task_type,
                "input_artifact_refs": task.input_artifact_refs,
                "exception_message": str(exc),
            },
        )
        failure["fallback_used"] = fallback_strategy
        task.failure = failure
        task.ended_at = datetime.now(timezone.utc).isoformat()
        task.model = llm_client.config.model
        _write_shadow_failure(task, output_path)
        return task

    # Record token usage
    usage = result.get("usage", {})
    task.token_usage = {
        "prompt_tokens": int(usage.get("prompt_tokens", 0)),
        "completion_tokens": int(usage.get("completion_tokens", 0)),
        "total_tokens": int(usage.get("total_tokens", 0)),
    }
    task.model = str(result.get("model", llm_client.config.model))

    # Check for provider errors
    if result.get("parse_status") == "provider_error":
        task.status = "fallback_used"
        failure = build_prompt_failure(
            prompt_id=task.prompt_id,
            error_type="provider_error",
            details={
                "task_type": task.task_type,
                "input_artifact_refs": task.input_artifact_refs,
                "error": result.get("error", ""),
            },
        )
        failure["fallback_used"] = fallback_strategy
        task.failure = failure
        task.ended_at = datetime.now(timezone.utc).isoformat()
        _write_shadow_failure(task, output_path)
        return task

    # Parse the LLM content
    content = str(result.get("content", ""))
    parsed = _parse_shadow_response(request_id, content, prompt_config)

    if parsed["parse_status"] != "ok" and parsed["parse_status"] != "ok_repaired":
        # Parse failure → fallback
        parse_status = parsed["parse_status"]
        error_type = "parse_error" if parse_status == "invalid_json" else "schema_mismatch"
        task.status = "fallback_used"
        failure = build_prompt_failure(
            prompt_id=task.prompt_id,
            error_type=error_type,
            details={
                "task_type": task.task_type,
                "input_artifact_refs": task.input_artifact_refs,
                "raw_output_prefix": content[:200] if content else "",
                "parse_status": parse_status,
            },
        )
        failure["fallback_used"] = fallback_strategy
        task.failure = failure
        task.ended_at = datetime.now(timezone.utc).isoformat()
        _write_shadow_failure(task, output_path)
        return task

    # ---- PRM-006 / SHD-004: Validate shadow output structure ----
    raw_output = parsed["output"]
    validated_output, violations = _validate_shadow_output(
        task.task_type, raw_output, input_data
    )

    if violations:
        # Output parses as JSON but fails structural validation
        task.status = "fallback_used"
        failure = build_prompt_failure(
            prompt_id=task.prompt_id,
            error_type="validation_failure",
            details={
                "task_type": task.task_type,
                "input_artifact_refs": task.input_artifact_refs,
                "violations": violations,
                "raw_output_prefix": json.dumps(raw_output)[:300] if raw_output else "",
                "parse_status": parsed["parse_status"],
            },
        )
        failure["fallback_used"] = fallback_strategy
        task.failure = failure
        task.ended_at = datetime.now(timezone.utc).isoformat()
        _write_shadow_failure(task, output_path)
        return task

    # Success — use validated/normalized output
    task.status = "success"
    task.output = validated_output
    task.ended_at = datetime.now(timezone.utc).isoformat()
    _write_shadow_result(task, output_path)
    return task


def _call_llm_for_shadow(
    client: OpenAICompatibleVerifierClient,
    llm_request: dict[str, Any],
) -> dict[str, Any]:
    """Make an LLM call for a shadow task, returning the result dict.

    Uses the same HTTP request pattern as ``run_llm_json_requests`` in
    ``llm_provider.py``.
    """
    request_id = str(llm_request.get("request_id", ""))
    config = client.config

    if not config.api_key:
        return _provider_error_json_result(request_id, "missing_api_key")

    payload = {
        "model": config.model,
        "messages": _messages_for_json_request(llm_request),
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "response_format": {"type": "json_object"},
    }

    http_request = Request(
        f"{config.base_url}/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with client.open_url(http_request, timeout=config.timeout) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else ""
        return _provider_error_json_result(request_id, f"HTTP {exc.code}: {body}")
    except (OSError, URLError, json.JSONDecodeError) as exc:
        return _provider_error_json_result(request_id, str(exc))

    choices = response_payload.get("choices", [])
    if not choices:
        return _provider_error_json_result(request_id, "missing_choices")
    message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
    return {
        "request_id": request_id,
        "parse_status": "ok",
        "content": str(message.get("content", "")),
        "usage": response_payload.get("usage", {}),
        "model": response_payload.get("model", config.model),
    }


def _write_shadow_result(task: LLMShadowTask, output_dir: Path) -> None:
    """Write a shadow task result to ``<task_type>_shadow_results.json``."""
    file_path = output_dir / f"{task.task_type}_shadow_results.json"
    record = {
        "schema_version": SHADOW_SCHEMA_VERSION,
        "task_type": task.task_type,
        "prompt_id": task.prompt_id,
        "status": task.status,
        "started_at": task.started_at,
        "ended_at": task.ended_at,
        "model": task.model,
        "token_usage": task.token_usage,
        "input_artifact_refs": task.input_artifact_refs,
        "output": task.output,
    }
    file_path.parent.mkdir(parents=True, exist_ok=True)
    # Append to existing file or create new one
    existing: list[dict[str, Any]] = []
    if file_path.exists():
        try:
            existing = json.loads(file_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, FileNotFoundError):
            existing = []
    if not isinstance(existing, list):
        existing = []
    existing.append(record)
    file_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_shadow_failure(task: LLMShadowTask, output_dir: Path) -> None:
    """Write a shadow task failure to ``<task_type>_shadow_failures.json``."""
    file_path = output_dir / f"{task.task_type}_shadow_failures.json"
    record = {
        "schema_version": SHADOW_SCHEMA_VERSION,
        "task_type": task.task_type,
        "prompt_id": task.prompt_id,
        "status": task.status,
        "started_at": task.started_at,
        "ended_at": task.ended_at,
        "model": task.model,
        "token_usage": task.token_usage,
        "input_artifact_refs": task.input_artifact_refs,
        "failure": task.failure,
    }
    file_path.parent.mkdir(parents=True, exist_ok=True)
    existing: list[dict[str, Any]] = []
    if file_path.exists():
        try:
            existing = json.loads(file_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, FileNotFoundError):
            existing = []
    if not isinstance(existing, list):
        existing = []
    existing.append(record)
    file_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# run_shadow_pipeline
# ---------------------------------------------------------------------------


def run_shadow_pipeline(
    task_types: list[str],
    input_dir: str | Path,
    output_dir: str | Path,
    llm_config: LlmConfig | None = None,
    max_samples_per_type: int = 5,
    *,
    prompt_registry_path: str | Path | None = None,
    open_url: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Run the full shadow pipeline for the given task types.

    For each *task_type*, loads the relevant input artifacts from
    *input_dir*, builds up to *max_samples_per_type* shadow requests,
    executes them, collects results, and writes a shadow report.

    Does **NOT** modify any existing artifacts — writes only to
    ``*_shadow_results.json`` and ``*_shadow_failures.json`` inside
    *output_dir*.

    Args:
        task_types: List of shadow task types to run (e.g.
            ``["query_compression", "search_relevance"]``).
        input_dir: Directory containing the main pipeline's output
            artifacts (e.g. ``candidates.json``, etc.).
        output_dir: Directory where shadow artifacts will be written.
        llm_config: Optional :class:`LlmConfig`. If None, loaded from env.
        max_samples_per_type: Maximum shadow executions per task type.
        prompt_registry_path: Path to prompt_registry.json. If None,
            defaults to ``LangGraph/prompts/prompt_registry.json`` relative
            to the project root (resolved from this file's location).
        open_url: Optional urlopen-compatible callable for testing.

    Returns:
        A ``shadow_run_report`` dict with keys:
        ``schema_version``, ``started_at``, ``ended_at``,
        ``per_task_type`` (dict of task_type -> stats), and ``tasks``
        (list of :class:`LLMShadowTask` dicts).
    """
    started_at = datetime.now(timezone.utc).isoformat()

    # Resolve prompt registry path
    if prompt_registry_path is None:
        this_dir = Path(__file__).resolve().parent
        repo_root = this_dir.parent.parent  # LangGraph/src/games_news_agent -> LangGraph
        prompt_registry_path = repo_root / "prompts" / "prompt_registry.json"

    registry = load_prompt_registry(prompt_registry_path)
    effective_config = llm_config or load_llm_config()
    inp = Path(input_dir)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    client = OpenAICompatibleVerifierClient(effective_config, open_url=open_url or urlopen)

    per_task_type: dict[str, dict[str, Any]] = {}
    all_tasks: list[LLMShadowTask] = []

    for task_type in task_types:
        prompt_config = get_prompt_config(task_type, registry)
        required_artifacts = prompt_config.get("input_artifacts", [])

        # Load input artifacts from input_dir
        input_data: dict[str, Any] = {}
        for artifact_name in required_artifacts:
            artifact_path = inp / f"{artifact_name}.json"
            if artifact_path.exists():
                try:
                    input_data[artifact_name] = json.loads(
                        artifact_path.read_text(encoding="utf-8")
                    )
                except (json.JSONDecodeError, FileNotFoundError):
                    input_data[artifact_name] = []
            else:
                input_data[artifact_name] = []

        # Build and execute tasks (one per sample)
        tasks_for_type: list[LLMShadowTask] = []
        samples = _extract_samples(input_data, required_artifacts, max_samples_per_type)

        for i, sample_input in enumerate(samples):
            try:
                task = build_shadow_request(
                    task_type, registry, sample_input, sample_index=i
                )
            except ValueError as exc:
                # Cannot build request → record as failure immediately
                task = LLMShadowTask(
                    task_type=task_type,
                    prompt_id=task_type,
                    input_artifact_refs=list(required_artifacts),
                    status="failure",
                    failure=build_prompt_failure(
                        prompt_id=task_type,
                        error_type="provider_error",
                        details={
                            "task_type": task_type,
                            "input_artifact_refs": list(required_artifacts),
                            "exception_message": str(exc),
                        },
                    ),
                    started_at=datetime.now(timezone.utc).isoformat(),
                    ended_at=datetime.now(timezone.utc).isoformat(),
                )
                _write_shadow_failure(task, out)
                tasks_for_type.append(task)
                continue

            executed = execute_shadow_task(
                task, client, prompt_config, sample_input, out
            )
            tasks_for_type.append(executed)

        all_tasks.extend(tasks_for_type)

        # Per-task-type stats
        success_count = sum(1 for t in tasks_for_type if t.status == "success")
        failure_count = sum(1 for t in tasks_for_type if t.status == "failure")
        fallback_count = sum(1 for t in tasks_for_type if t.status == "fallback_used")
        total_tokens = sum(t.token_usage.get("total_tokens", 0) for t in tasks_for_type)

        per_task_type[task_type] = {
            "total": len(tasks_for_type),
            "success": success_count,
            "failure": failure_count,
            "fallback_used": fallback_count,
            "total_tokens": total_tokens,
            "fallback_strategy": prompt_config.get("fallback", ""),
        }

    ended_at = datetime.now(timezone.utc).isoformat()

    report: dict[str, Any] = {
        "schema_version": SHADOW_SCHEMA_VERSION,
        "started_at": started_at,
        "ended_at": ended_at,
        "per_task_type": per_task_type,
        "tasks": [t.to_dict() for t in all_tasks],
    }

    # Write the full report
    report_path = out / "shadow_run_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    return report


def _extract_samples(
    input_data: dict[str, Any],
    required_artifacts: list[str],
    max_samples: int,
) -> list[dict[str, Any]]:
    """Extract up to *max_samples* sample inputs from *input_data*.

    Each sample is a dict mapping artifact names to a single-item slice
    of their content, so the LLM sees one item per shadow call.

    For list artifacts, takes one item per sample index.
    For dict artifacts, includes the whole dict as context for each sample.
    """
    if max_samples <= 0:
        return []

    # Determine the primary artifact (first in the list)
    primary_artifact = required_artifacts[0] if required_artifacts else ""
    primary_data = input_data.get(primary_artifact, [])

    if isinstance(primary_data, list) and len(primary_data) > 0:
        sample_count = min(len(primary_data), max_samples)
    elif isinstance(primary_data, dict):
        sample_count = 1
    else:
        sample_count = 0

    samples: list[dict[str, Any]] = []
    for i in range(sample_count):
        sample: dict[str, Any] = {}
        primary_item = primary_data[i] if isinstance(primary_data, list) and len(primary_data) > i else {}
        for artifact_name in required_artifacts:
            data = input_data.get(artifact_name, [])
            if isinstance(data, list):
                if (
                    primary_artifact == "story_candidates"
                    and artifact_name == "context_packs"
                    and isinstance(primary_item, dict)
                ):
                    sample[artifact_name] = _matching_context_packs(primary_item, data, fallback_index=i)
                elif len(data) > i:
                    sample[artifact_name] = [data[i]]
                else:
                    sample[artifact_name] = []
            elif isinstance(data, dict):
                sample[artifact_name] = data
            else:
                sample[artifact_name] = data
        samples.append(sample)

    return samples


def _urls_for_shadow_match(item: dict[str, Any]) -> set[str]:
    urls: set[str] = set()

    def add(value: Any) -> None:
        text = str(value or "").strip()
        if text.startswith("http://") or text.startswith("https://"):
            urls.add(text)

    add(item.get("url"))
    for value in item.get("source_urls") or []:
        add(value)
    candidate = item.get("candidate")
    if isinstance(candidate, dict):
        add(candidate.get("url"))
        for value in candidate.get("source_urls") or []:
            add(value)
    for claim in item.get("claims") or []:
        if not isinstance(claim, dict):
            continue
        for value in claim.get("source_urls") or []:
            add(value)
    return urls


def _matching_context_packs(
    story_candidate: dict[str, Any],
    context_packs: list[Any],
    *,
    fallback_index: int,
    limit: int = 2,
) -> list[dict[str, Any]]:
    story_urls = _urls_for_shadow_match(story_candidate)
    matches: list[dict[str, Any]] = []
    for pack in context_packs:
        if not isinstance(pack, dict):
            continue
        pack_urls = _urls_for_shadow_match(pack)
        if story_urls and story_urls & pack_urls:
            matches.append(pack)
            if len(matches) >= limit:
                return matches
    if matches:
        return matches
    if 0 <= fallback_index < len(context_packs) and isinstance(context_packs[fallback_index], dict):
        return [context_packs[fallback_index]]
    return []


# ---------------------------------------------------------------------------
# Shadow-specific CLI helper
# ---------------------------------------------------------------------------


def parse_shadow_task_types(raw: str) -> list[str]:
    """Parse a comma-separated list of task types.

    Returns only valid shadow task types. Prints a warning for unknowns.
    """
    if not raw or not raw.strip():
        return []
    candidates = [name.strip() for name in raw.split(",") if name.strip()]
    valid: list[str] = []
    for name in candidates:
        if name in SHADOW_TASK_TYPES:
            valid.append(name)
        else:
            print(
                f"[shadow:warning] Unknown task_type '{name}' — ignored. "
                f"Allowed: {sorted(SHADOW_TASK_TYPES)}"
            )
    return valid


def print_shadow_summary(report: dict[str, Any]) -> None:
    """Print a human-readable summary of shadow pipeline results."""
    per_type = report.get("per_task_type", {})
    if not per_type:
        print("[shadow] No shadow tasks were executed.")
        return

    print("\n=== LLM Shadow Run Summary ===")
    grand_total_tokens = 0
    for task_type, stats in sorted(per_type.items()):
        total = stats.get("total", 0)
        success = stats.get("success", 0)
        failure = stats.get("failure", 0)
        fallback = stats.get("fallback_used", 0)
        tokens = stats.get("total_tokens", 0)
        grand_total_tokens += tokens
        print(
            f"  {task_type}: {total} total, "
            f"{success} success, {failure} failure, {fallback} fallback, "
            f"{tokens} tokens"
        )
    print(f"  Total tokens consumed: {grand_total_tokens}")
    print(f"  Report: shadow_run_report.json")
    print("=== End Shadow Summary ===\n")
