"""LLM verifier request/response harness.

This module does not call a model. It prepares compact verification requests
and validates/merges schema-shaped LLM responses when a provider is wired in.
"""

from __future__ import annotations

import json
from typing import Any


ALLOWED_STATUSES = [
    "verified",
    "likely",
    "credible_rumor",
    "weak_rumor",
    "unverified_rumor",
    "rumor",
    "conflict",
    "reject",
    "manual_review_required",
]

JSON_SCHEMA = {
    "type": "object",
    "required": [
        "check_status",
        "confidence",
        "rationale",
        "used_evidence_chunk_ids",
        "risk_flags",
    ],
    "properties": {
        "check_status": {"type": "string", "enum": ALLOWED_STATUSES},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "rationale": {"type": "string"},
        "used_evidence_chunk_ids": {
            "type": "array",
            "items": {"type": "string"},
        },
        "risk_flags": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
}

INSTRUCTIONS = (
    "You are a cautious games news fact verifier. Use only the provided evidence. "
    "Keep rumors labeled as rumors unless the evidence explicitly confirms them. "
    "Return JSON matching the schema exactly."
)


def _claim_url(claim: dict[str, Any]) -> str:
    metadata = claim.get("metadata", {})
    if isinstance(metadata, dict) and metadata.get("candidate_url"):
        return str(metadata["candidate_url"])
    urls = claim.get("source_urls", [])
    if isinstance(urls, list) and urls:
        return str(urls[0])
    return ""


def _context_evidence_for_claim(
    claim: dict[str, Any],
    context_packs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    claim_url = _claim_url(claim)
    if not claim_url:
        return []
    for pack in context_packs:
        candidate = pack.get("candidate", {})
        if isinstance(candidate, dict) and str(candidate.get("url", "")) == claim_url:
            evidence = pack.get("evidence", [])
            if isinstance(evidence, list):
                return [dict(item) for item in evidence if isinstance(item, dict)]
    return []


def _request_id(claim: dict[str, Any]) -> str:
    return str(claim.get("story_id") or claim.get("id") or _claim_url(claim) or claim.get("text", ""))


def build_llm_verification_requests(
    rule_verifications: list[dict[str, Any]],
    context_packs: list[dict[str, Any]],
    *,
    max_evidence: int = 5,
) -> list[dict[str, Any]]:
    requests: list[dict[str, Any]] = []
    for claim in rule_verifications:
        evidence = _context_evidence_for_claim(claim, context_packs)
        if not evidence:
            evidence = [
                dict(item)
                for item in claim.get("evidence", [])
                if isinstance(item, dict)
            ]
        requests.append(
            {
                "request_id": _request_id(claim),
                "schema_version": "llm_verifier_request_v0",
                "prompt_name": "evidence_verifier.md",
                "instructions": INSTRUCTIONS,
                "claim": {
                    "text": claim.get("text", ""),
                    "claim_type": claim.get("claim_type", ""),
                    "rule_check_status": claim.get("check_status", ""),
                    "rule_confidence": claim.get("confidence", 0),
                    "source_urls": claim.get("source_urls", []),
                    "risk_context": claim.get("verification_reasons", []),
                },
                "evidence": evidence[: max(max_evidence, 0)],
                "allowed_statuses": list(ALLOWED_STATUSES),
                "json_schema": JSON_SCHEMA,
            }
        )
    return requests


def _load_response(raw_response: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw_response, dict):
        return dict(raw_response)
    return json.loads(raw_response)


def parse_llm_verification_response(
    request_id: str,
    raw_response: str | dict[str, Any],
) -> dict[str, Any]:
    try:
        parsed = _load_response(raw_response)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        return {
            "request_id": request_id,
            "parse_status": "invalid_json",
            "check_status": "manual_review_required",
            "confidence": 0.0,
            "rationale": str(exc),
            "used_evidence_chunk_ids": [],
            "risk_flags": ["invalid_llm_json"],
        }

    status = str(parsed.get("check_status", "manual_review_required"))
    if status not in ALLOWED_STATUSES:
        return {
            "request_id": request_id,
            "parse_status": "invalid_status",
            "check_status": "manual_review_required",
            "confidence": 0.0,
            "rationale": f"Unsupported status: {status}",
            "used_evidence_chunk_ids": [],
            "risk_flags": ["invalid_llm_status"],
        }

    confidence = parsed.get("confidence", 0.0)
    if not isinstance(confidence, (int, float)):
        confidence = 0.0

    return {
        "request_id": request_id,
        "parse_status": "parsed",
        "check_status": status,
        "confidence": max(0.0, min(float(confidence), 1.0)),
        "rationale": str(parsed.get("rationale", "")),
        "used_evidence_chunk_ids": [
            str(item)
            for item in parsed.get("used_evidence_chunk_ids", [])
            if str(item).strip()
        ],
        "risk_flags": [
            str(item)
            for item in parsed.get("risk_flags", [])
            if str(item).strip()
        ],
    }


def apply_llm_verification_results(
    rule_verifications: list[dict[str, Any]],
    llm_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_request_id = {str(item.get("request_id", "")): item for item in llm_results}
    merged: list[dict[str, Any]] = []
    for claim in rule_verifications:
        request_id = _request_id(claim)
        result = by_request_id.get(request_id)
        if not result or result.get("parse_status") != "parsed":
            merged.append(dict(claim))
            continue

        enriched = dict(claim)
        enriched["rule_check_status"] = claim.get("check_status", "")
        enriched["rule_confidence"] = claim.get("confidence", 0)
        enriched["check_status"] = result["check_status"]
        enriched["confidence"] = result["confidence"]
        enriched["verification_method"] = "llm_schema_v0"
        enriched["llm_verification"] = {
            "rationale": result.get("rationale", ""),
            "used_evidence_chunk_ids": result.get("used_evidence_chunk_ids", []),
            "risk_flags": result.get("risk_flags", []),
        }
        merged.append(enriched)
    return merged
