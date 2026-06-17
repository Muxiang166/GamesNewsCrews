"""Structured request builder for future editorial LLM judgment agents.

PRM-006 / SHD-004: This module now includes JSON repair, field consistency
checks, and echo detection so that LLM outputs which parse as valid JSON but
contain contradictory fields or merely mirror the input are treated as
fallbacks rather than successes.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any


AGENT_NAME = "EditorialJudgmentAgent"
SCHEMA_VERSION = "editorial_judgment_v0"

GAME_RELEVANCE_VALUES = {
    "core_game_news",
    "platform_or_pc_game_adjacent",
    "community_game_meme",
    "off_topic",
    "unknown",
}
PUBLISHABILITY_VALUES = {"publishable", "needs_human_review", "reject"}
HEAT_VALIDITY_VALUES = {"game_discussion", "general_social_heat", "unclear"}

AMBIGUOUS_CANDIDATE_TYPES = {
    "manual_review",
    "supplemental_context",
    "pc_hardware_or_event",
    "general_tech",
    "off_topic_entertainment",
    "meme_gallery",
    "discussion_search_lead",
}
HIGH_RISK_FALSE_POSITIVE_PATTERN = re.compile(
    r"比尔盖茨|爱泼斯坦|黄仁勋|梅西|滨崎步|易梦玲|鹅腿阿姨|胖东来|于东来|"
    r"\bbill gates\b|\bepstein\b|\bnvidia ceo\b",
    flags=re.IGNORECASE,
)


def _text(item: dict[str, Any]) -> str:
    parts = [
        item.get("title", ""),
        item.get("snippet", ""),
        item.get("summary", ""),
        " ".join(str(tag) for tag in item.get("tags", [])),
    ]
    return " ".join(str(part) for part in parts if part)


def _candidate_url(item: dict[str, Any]) -> str:
    if item.get("url"):
        return str(item["url"])
    urls = item.get("source_urls")
    if isinstance(urls, list) and urls:
        return str(urls[0])
    return ""


def _candidate_type(item: dict[str, Any]) -> str:
    value = item.get("candidate_type")
    if value:
        return str(value)
    claims = item.get("claims")
    if isinstance(claims, list):
        for claim in claims:
            if not isinstance(claim, dict):
                continue
            metadata = claim.get("metadata", {})
            if isinstance(metadata, dict) and metadata.get("candidate_type"):
                return str(metadata["candidate_type"])
            if claim.get("claim_type"):
                return str(claim["claim_type"])
    return ""


def _source_id(item: dict[str, Any]) -> str:
    value = item.get("source_id")
    if value:
        return str(value)
    claims = item.get("claims")
    if isinstance(claims, list):
        for claim in claims:
            if not isinstance(claim, dict):
                continue
            metadata = claim.get("metadata", {})
            if isinstance(metadata, dict) and metadata.get("source_id"):
                return str(metadata["source_id"])
    return ""


def _score(item: dict[str, Any], *keys: str) -> float:
    for key in keys:
        value = item.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return 0.0


def _judgment_reasons(item: dict[str, Any], *, force_all: bool) -> list[str]:
    reasons: list[str] = []
    candidate_type = _candidate_type(item)
    if force_all:
        reasons.append("forced_review")
    if candidate_type in AMBIGUOUS_CANDIDATE_TYPES:
        reasons.append(f"ambiguous_candidate_type:{candidate_type}")
    if HIGH_RISK_FALSE_POSITIVE_PATTERN.search(_text(item)):
        reasons.append("off_topic_risk")
    if str(item.get("candidate_lane", "")) == "supplemental":
        reasons.append("supplemental_lane")
    if _score(item, "discussion_score") >= 25 and candidate_type not in {
        "news",
        "rumor",
        "platform_price",
        "hardware_platform",
        "review_score",
    }:
        reasons.append("social_heat_needs_game_relevance_check")
    return reasons


def _request_id(item: dict[str, Any], index: int) -> str:
    raw = f"{_candidate_url(item)}|{item.get('title', '')}|{index}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]
    return f"editorial_judgment_{digest}"


def _trim(value: Any, limit: int = 600) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."


def _public_candidate_view(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": _trim(item.get("title", "")),
        "url": _candidate_url(item),
        "source_id": _source_id(item),
        "candidate_type": _candidate_type(item),
        "candidate_lane": item.get("candidate_lane", ""),
        "theme_section": item.get("theme_section", ""),
        "snippet": _trim(item.get("snippet") or item.get("summary") or ""),
        "score": _score(item, "score", "story_score"),
        "heat_score": _score(item, "heat_score"),
        "discussion_score": _score(item, "discussion_score"),
        "discussion_level": item.get("discussion_level", ""),
        "discussion_profile": item.get("discussion_profile", {}),
        "tags": item.get("tags", []),
    }


def build_editorial_judgment_requests(
    candidates: list[dict[str, Any]],
    *,
    limit: int = 20,
    force_all: bool = False,
) -> list[dict[str, Any]]:
    """Build JSON requests for an LLM/human editorial relevance judgment step.

    The request is deliberately advisory: the future agent may judge game
    relevance and publishability, but it must not add facts or verify claims.
    """

    requests: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(candidates):
        if not isinstance(item, dict):
            continue
        reasons = _judgment_reasons(item, force_all=force_all)
        if not reasons:
            continue
        key = _candidate_url(item) or str(item.get("title", ""))
        if key in seen:
            continue
        seen.add(key)
        requests.append(
            {
                "request_id": _request_id(item, index),
                "schema_version": SCHEMA_VERSION,
                "agent_name": AGENT_NAME,
                "produces_facts": False,
                "task": "judge_editorial_relevance_and_publishability",
                "candidate": _public_candidate_view(item),
                "judgment_reasons": reasons,
                "constraints": [
                    "do_not_add_facts",
                    "do_not_verify_claim_truth",
                    "do_not_invent_sources",
                    "judge_only_from_provided_candidate_fields",
                ],
                "output_schema": {
                    "game_relevance": sorted(GAME_RELEVANCE_VALUES),
                    "publishability": sorted(PUBLISHABILITY_VALUES),
                    "heat_validity": sorted(HEAT_VALIDITY_VALUES),
                    "confidence": "number 0..1",
                    "reason": "short explanation",
                    "risk_flags": "list of short strings",
                },
            }
        )
        if len(requests) >= limit:
            break
    return requests


def _safe_choice(value: Any, allowed: set[str], fallback: str) -> str:
    text = str(value or "").strip()
    return text if text in allowed else fallback


def _safe_confidence(value: Any) -> float:
    if not isinstance(value, (int, float)):
        return 0.0
    return round(max(0.0, min(1.0, float(value))), 3)


# ---------------------------------------------------------------------------
# PRM-006 / SHD-004: JSON repair helpers
# ---------------------------------------------------------------------------

# Common LLM JSON mistakes that can be fixed with regex before parsing.
_JSON_REPAIR_PATTERNS: list[tuple[str, str, str]] = [
    # (name, pattern, replacement)
    ("trailing_comma_before_close", r",(\s*[}\]])", r"\1"),
    ("single_quoted_keys", r"'([^']+)'(\s*):", r'"\1"\2:'),
    ("single_quoted_values", r":\s*'([^']*)'", r': "\1"'),
    ("unquoted_keys", r"(?<!\\)\b([a-zA-Z_][a-zA-Z0-9_]*)(\s*):", r'"\1"\2:'),
    ("line_comment", r"//[^\n]*", ""),
    ("trailing_comma_in_array", r",(\s*])", r"\1"),
]


def _try_repair_json(raw: str) -> str | None:
    """Attempt lightweight JSON repair for common LLM output mistakes.

    Returns the repaired string if any repairs were applied, or ``None`` if
    no known pattern matched (caller should fall back to the original).
    """
    repaired = raw.strip()
    changed = False

    # Strip markdown code fences if present
    fence_match = re.match(r"```(?:json)?\s*(.*?)\s*```", repaired, re.DOTALL)
    if fence_match:
        repaired = fence_match.group(1).strip()
        changed = True

    # Try to extract the first JSON object/array
    obj_start = repaired.find("{")
    arr_start = repaired.find("[")
    if obj_start >= 0 or arr_start >= 0:
        start = obj_start if (obj_start >= 0 and (arr_start < 0 or obj_start < arr_start)) else arr_start
        if start > 0:
            repaired = repaired[start:]
            changed = True

    # Apply repair patterns
    for _name, pattern, replacement in _JSON_REPAIR_PATTERNS:
        prev = repaired
        repaired = re.sub(pattern, replacement, repaired, flags=re.MULTILINE)
        if repaired != prev:
            changed = True

    # Try to balance braces
    open_braces = repaired.count("{") - repaired.count("}")
    open_brackets = repaired.count("[") - repaired.count("]")
    if open_braces > 0 and open_braces <= 3:
        repaired = repaired.rstrip() + "}" * open_braces
        changed = True
    if open_brackets > 0 and open_brackets <= 3:
        repaired = repaired.rstrip() + "]" * open_brackets
        changed = True

    return repaired if changed else None


# ---------------------------------------------------------------------------
# PRM-006 / SHD-004: Field consistency and echo detection
# ---------------------------------------------------------------------------


def _check_editorial_consistency(payload: dict[str, Any]) -> list[str]:
    """Return a list of inconsistency flags for editorial judgment fields.

    An empty list means the output passed consistency checks.
    """
    flags: list[str] = []
    game_relevance = str(payload.get("game_relevance", "")).strip()
    publishability = str(payload.get("publishability", "")).strip()
    heat_validity = str(payload.get("heat_validity", "")).strip()
    confidence = payload.get("confidence")
    reason = str(payload.get("reason", "")).strip()
    risk_flags = payload.get("risk_flags", [])

    # Required fields present
    if not game_relevance:
        flags.append("missing_game_relevance")
    if not publishability:
        flags.append("missing_publishability")
    if not heat_validity:
        flags.append("missing_heat_validity")

    # Confidence must be a number 0-1
    if not isinstance(confidence, (int, float)):
        flags.append("confidence_not_numeric")
    elif confidence < 0 or confidence > 1:
        flags.append("confidence_out_of_range")

    # Reason must be non-empty and substantive
    if len(reason) < 8:
        flags.append("reason_too_short_or_missing")

    # risk_flags must be a list
    if not isinstance(risk_flags, list):
        flags.append("risk_flags_not_list")

    # Cross-field consistency checks
    if game_relevance == "off_topic" and publishability == "publishable":
        flags.append("inconsistent:off_topic_but_publishable")
    if game_relevance == "core_game_news" and publishability == "reject":
        flags.append("inconsistent:core_game_news_but_rejected")
    if heat_validity == "game_discussion" and game_relevance == "off_topic":
        flags.append("inconsistent:game_discussion_but_off_topic")
    if publishability == "publishable" and confidence is not None and isinstance(confidence, (int, float)) and confidence < 0.3:
        flags.append("inconsistent:publishable_with_low_confidence")

    return flags


def _detect_echo(payload: dict[str, Any], candidate: dict[str, Any]) -> bool:
    """Return True if the LLM output appears to mainly echo input fields.

    Checks if the ``reason`` field is essentially a copy of the candidate
    title/snippet without any editorial assessment.  Uses fuzzy prefix
    matching rather than exact string comparison to handle punctuation and
    whitespace differences.
    """
    reason = str(payload.get("reason", "")).strip()
    if len(reason) < 15:
        return False  # too short to judge — caught by consistency check

    title = str(candidate.get("title", "")).strip()
    snippet = str(candidate.get("snippet", "")).strip()

    def _normalize_for_echo(text: str) -> str:
        """Strip punctuation and collapse whitespace for comparison."""
        import re as _re
        cleaned = _re.sub(r"[，。！？、；：""''（）《》【】.,!?;:\"'()\\[\\]<>]", " ", text)
        return " ".join(cleaned.split()).lower()

    norm_reason = _normalize_for_echo(reason)
    norm_title = _normalize_for_echo(title)
    norm_snippet = _normalize_for_echo(snippet)
    norm_combined = f"{norm_title} {norm_snippet}".strip()

    # If reason contains the full title verbatim and adds nothing, it's an echo
    if norm_title and len(norm_title) > 12 and norm_title in norm_reason:
        ratio = len(norm_title) / max(len(norm_reason), 1)
        if ratio > 0.6:
            return True

    # If reason is just title + snippet concatenated with no new words
    if norm_snippet and len(norm_snippet) > 15:
        if len(norm_combined) > 20:
            # Check if reason starts with the combined title+snippet (fuzzy)
            prefix_len = min(len(norm_combined), len(norm_reason))
            overlap = sum(1 for i in range(min(prefix_len, 60)) if i < len(norm_combined) and i < len(norm_reason) and norm_combined[i] == norm_reason[i])
            prefix_chars = min(prefix_len, 60)
            if prefix_chars > 0 and overlap / prefix_chars > 0.85:
                return True

    return False


def _normalize_search_relevance_fields(payload: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Fix inconsistent search_relevance shadow fields.

    The v020_fix_verify run showed cases where ``relevance=same_game`` but
    ``same_game=false``.  This function normalises such contradictions and
    returns the corrected payload along with any fixes applied.
    """
    fixes: list[str] = []
    normalized = dict(payload)

    relevance = str(normalized.get("relevance", "")).strip()
    same_game = normalized.get("same_game")
    same_event = normalized.get("same_event")
    is_current = normalized.get("is_current_window")
    confidence = normalized.get("confidence")

    # Fix: relevance says "same_game" but same_game is False/0/null
    if relevance == "same_game" and same_game in (False, 0, None, "false", "no"):
        normalized["same_game"] = True
        fixes.append("normalized:same_game_true_to_match_relevance")

    # Fix: relevance says "same_event" but same_event is False
    if relevance == "same_event" and same_event in (False, 0, None, "false", "no"):
        normalized["same_event"] = True
        fixes.append("normalized:same_event_true_to_match_relevance")

    # Fix: relevance is a specific game/platform but same_game=False
    if relevance not in ("same_game", "same_event", "unrelated", "general_discussion", "old_news", ""):
        if same_game in (False, 0, "false", "no") and same_event in (False, 0, "false", "no"):
            normalized["same_game"] = True
            fixes.append("normalized:same_game_true_for_specific_relevance")

    # Fix: is_current_window but confidence is 0
    if is_current in (True, 1, "true", "yes") and isinstance(confidence, (int, float)) and confidence == 0:
        normalized["confidence"] = 0.5
        fixes.append("normalized:confidence_0_5_for_current_window")

    return normalized, fixes


def parse_editorial_judgment_result(
    request_id: str,
    raw_response: str,
    *,
    candidate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Parse an LLM editorial judgment response with safe fallback semantics.

    PRM-006 / SHD-004: Before treating the response as a hard failure this
    function attempts lightweight JSON repair (trailing commas, missing
    braces, unquoted keys, markdown fences).  After parsing it runs field
    consistency checks and echo detection.  Responses that parse as valid
    JSON but fail consistency or are pure echoes are downgraded to fallback.
    """

    # ---- Phase 1: parse JSON (with repair attempt) ----
    payload: dict[str, Any] | None = None
    parse_status = "invalid_json"

    # Try direct parse first
    try:
        payload = json.loads(raw_response)
        parse_status = "ok"
    except json.JSONDecodeError:
        # Attempt repair
        repaired = _try_repair_json(raw_response)
        if repaired is not None:
            try:
                payload = json.loads(repaired)
                parse_status = "ok_repaired"
            except json.JSONDecodeError:
                payload = None

    if payload is None or not isinstance(payload, dict):
        return {
            "request_id": request_id,
            "schema_version": SCHEMA_VERSION,
            "parse_status": "invalid_json",
            "game_relevance": "unknown",
            "publishability": "needs_human_review",
            "heat_validity": "unclear",
            "confidence": 0.0,
            "reason": "LLM response was not valid JSON.",
            "risk_flags": ["invalid_json"],
            "_consistency_checks": [],
            "_echo_detected": False,
        }

    # ---- Phase 2: field consistency (PRM-006) ----
    consistency_flags = _check_editorial_consistency(payload)

    # ---- Phase 3: echo detection (SHD-004) ----
    echo_detected = False
    if candidate is not None:
        echo_detected = _detect_echo(payload, candidate)

    # ---- Phase 4: extract fields with safe fallbacks ----
    risk_flags = payload.get("risk_flags", [])
    if not isinstance(risk_flags, list):
        risk_flags = ["invalid_risk_flags"]
    risk_flags = [str(flag) for flag in risk_flags[:10]]

    # Fold consistency flags into risk_flags for auditability
    if consistency_flags:
        risk_flags = consistency_flags + risk_flags
    if echo_detected:
        risk_flags = ["echo_detected"] + risk_flags

    # Determine effective parse_status
    effective_status = parse_status
    has_blocking_consistency_issue = any(
        flag.startswith("missing_") or flag.startswith("inconsistent:")
        for flag in consistency_flags
    )
    if echo_detected or has_blocking_consistency_issue:
        effective_status = "fallback_inconsistent"

    result = {
        "request_id": request_id,
        "schema_version": SCHEMA_VERSION,
        "parse_status": effective_status,
        "game_relevance": _safe_choice(
            payload.get("game_relevance"),
            GAME_RELEVANCE_VALUES,
            "unknown",
        ),
        "publishability": _safe_choice(
            payload.get("publishability"),
            PUBLISHABILITY_VALUES,
            "needs_human_review",
        ),
        "heat_validity": _safe_choice(
            payload.get("heat_validity"),
            HEAT_VALIDITY_VALUES,
            "unclear",
        ),
        "confidence": _safe_confidence(payload.get("confidence")),
        "reason": _trim(payload.get("reason", ""), 500),
        "risk_flags": risk_flags,
        "_consistency_checks": consistency_flags,
        "_echo_detected": echo_detected,
    }

    # If the LLM output is inconsistent or pure echo, force fallback semantics
    # regardless of what the model claimed (SHD-004)
    if has_blocking_consistency_issue or echo_detected:
        if result["publishability"] == "publishable":
            result["publishability"] = "needs_human_review"
        result["game_relevance"] = "unknown"
        result["heat_validity"] = "unclear"

    return result
