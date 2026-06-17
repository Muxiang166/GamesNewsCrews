"""Deterministic claim extraction scaffold.

This module intentionally avoids LLM calls for now. It creates one candidate-level
claim per context pack so downstream verifier prompts have a stable artifact to
consume before we replace this with an LLM claim splitter.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any


THEME_CARRYOVER_FIELDS = (
    "theme_section_candidates",
    "source_entry_theme",
    "source_entry_themes",
    "source_section_theme",
    "editorial_intent",
    "editorial_priority",
)


def _stable_story_id(candidate: dict[str, Any]) -> str:
    cluster_id = str(candidate.get("story_cluster_id") or "").strip()
    if cluster_id:
        return cluster_id
    raw = str(candidate.get("url") or candidate.get("title") or candidate.get("source_id") or "")
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return f"story_{digest}"


def _source_urls(
    candidate: dict[str, Any],
    evidence: list[dict[str, Any]],
    *,
    evidence_scope: str,
) -> list[str]:
    urls: list[str] = []
    evidence_urls = [item.get("url") for item in evidence] if evidence_scope == "candidate_url" else []
    for value in [candidate.get("url"), *evidence_urls]:
        url = str(value or "").strip()
        if url and url not in urls:
            urls.append(url)
    return urls


def _claim_type(candidate_type: str) -> str:
    if candidate_type == "discussion_search_lead":
        return "search_lead"
    if candidate_type in {
        "deal",
        "general_tech",
        "guide",
        "manual_review",
        "meme_gallery",
        "off_topic_entertainment",
        "pc_hardware_or_event",
    }:
        return "supplemental_context"
    if candidate_type in {"rumor", "platform_price", "hardware_platform", "review_score", "news"}:
        return candidate_type
    return "fact_candidate"


def _clean_evidence_title(raw_title: Any) -> str:
    title = " ".join(str(raw_title or "").split()).strip()
    for separator in (" _ ", " | "):
        if separator in title:
            title = title.split(separator, 1)[0].strip()
    return title


def _is_weak_title(title: str) -> bool:
    compact = re.sub(r"\s+", "", str(title or ""))
    if not compact:
        return True
    if len(compact) < 8:
        return True
    return bool(re.fullmatch(r"[A-Za-z0-9]+", compact) and len(compact) < 12)


def _evidence_title_for_weak_candidate(
    candidate_title: str,
    evidence: list[dict[str, Any]],
) -> str:
    candidate_text = candidate_title.strip().lower()
    for item in evidence:
        if not isinstance(item, dict):
            continue
        title = _clean_evidence_title(item.get("title"))
        if not title or len(title) <= len(candidate_title):
            continue
        if candidate_text and candidate_text not in title.lower():
            continue
        return title
    return ""


def _fallback_text(candidate: dict[str, Any], evidence: list[dict[str, Any]]) -> str:
    title = str(candidate.get("title", "")).strip()
    if title:
        if _is_weak_title(title):
            evidence_title = _evidence_title_for_weak_candidate(title, evidence)
            if evidence_title:
                return evidence_title
        return title
    for item in evidence:
        evidence_title = _clean_evidence_title(item.get("title") if isinstance(item, dict) else "")
        if evidence_title:
            return evidence_title
        quote = str(item.get("quote", "")).strip()
        if quote:
            return quote[:180]
    return "Untitled claim"


def _candidate_metadata(candidate: dict[str, Any], candidate_type: str, evidence_scope: str) -> dict[str, Any]:
    metadata = {
        "source_id": candidate.get("source_id", ""),
        "candidate_url": candidate.get("url", ""),
        "candidate_type": candidate_type,
        "candidate_lane": candidate.get("candidate_lane", ""),
        "theme_section": candidate.get("theme_section", ""),
        "heat_score": candidate.get("heat_score", 0),
        "discussion_score": candidate.get("discussion_score", 0),
        "discussion_level": candidate.get("discussion_level", "none"),
        "discussion_profile": candidate.get("discussion_profile", {}),
        "evidence_scope": evidence_scope,
        "extractor": "deterministic_candidate_claim_v0",
    }
    for field in THEME_CARRYOVER_FIELDS:
        if field in candidate:
            metadata[field] = candidate.get(field)
    return metadata


def build_claims_from_context_packs(
    context_packs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    for pack in context_packs:
        candidate = pack.get("candidate", {})
        if not isinstance(candidate, dict):
            candidate = {}
        evidence = pack.get("evidence", [])
        if not isinstance(evidence, list):
            evidence = []
        missing_fields = [
            str(item)
            for item in pack.get("missing_fields", [])
            if str(item).strip()
        ]
        candidate_type = str(candidate.get("candidate_type", ""))
        story_id = _stable_story_id(candidate)
        evidence_scope = str(pack.get("evidence_scope") or "candidate_url")
        source_urls = _source_urls(candidate, evidence, evidence_scope=evidence_scope)
        evidence_chunk_ids = [
            str(item.get("chunk_id"))
            for item in evidence
            if evidence_scope == "candidate_url" and isinstance(item, dict) and item.get("chunk_id")
        ]
        extraction_status = "needs_evidence" if "evidence" in missing_fields else "candidate_claim"

        claims.append(
            {
                "text": _fallback_text(candidate, evidence),
                "story_id": story_id,
                "source_urls": source_urls,
                "check_status": "unchecked",
                "confidence": 0.0,
                "claim_type": _claim_type(candidate_type),
                "extraction_status": extraction_status,
                "evidence_chunk_ids": evidence_chunk_ids,
                "missing_fields": missing_fields,
                "metadata": _candidate_metadata(candidate, candidate_type, evidence_scope),
            }
        )
    return claims
