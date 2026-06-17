"""Build compact context packs for later LLM verifier/editor nodes."""

from __future__ import annotations

from typing import Any

from .retrieval import retrieve_evidence_from_chunks


THEME_CARRYOVER_FIELDS = (
    "theme_section_candidates",
    "source_entry_theme",
    "source_entry_themes",
    "source_section_theme",
    "editorial_intent",
    "editorial_priority",
)


def _candidate_query(candidate: dict[str, Any]) -> str:
    return " ".join(
        str(candidate.get(key, ""))
        for key in ("title", "snippet", "query")
        if candidate.get(key)
    )


def _candidate_snapshot(candidate: dict[str, Any], candidate_url: str) -> dict[str, Any]:
    snapshot = {
        "title": candidate.get("title", ""),
        "url": candidate_url,
        "source_id": candidate.get("source_id", ""),
        "candidate_type": candidate.get("candidate_type", ""),
        "candidate_lane": candidate.get("candidate_lane", ""),
        "theme_section": candidate.get("theme_section", ""),
        "heat_score": candidate.get("heat_score", 0),
        "discussion_score": candidate.get("discussion_score", 0),
        "discussion_level": candidate.get("discussion_level", "none"),
        "discussion_profile": candidate.get("discussion_profile", {}),
        "published_at": candidate.get("published_at"),
        "observed_at": candidate.get("observed_at"),
    }
    for field in THEME_CARRYOVER_FIELDS:
        if field in candidate:
            snapshot[field] = candidate.get(field)
    return snapshot


def build_context_packs(
    candidates: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    *,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    packs: list[dict[str, Any]] = []
    for candidate in candidates:
        candidate_url = str(candidate.get("url", ""))
        same_url_chunks = [chunk for chunk in chunks if str(chunk.get("url")) == candidate_url]
        evidence = same_url_chunks[:top_k]
        evidence_scope = "candidate_url"
        if not evidence:
            evidence = retrieve_evidence_from_chunks(chunks, _candidate_query(candidate), top_k=top_k)
            evidence_scope = "retrieved_context" if evidence else "none"

        missing_fields: list[str] = []
        if not evidence:
            missing_fields.append("evidence")
        elif evidence_scope != "candidate_url":
            missing_fields.append("source_document")
        if not candidate.get("published_at") and not candidate.get("observed_at"):
            missing_fields.append("time")

        packs.append(
            {
                "candidate": _candidate_snapshot(candidate, candidate_url),
                "evidence": evidence,
                "evidence_scope": evidence_scope,
                "missing_fields": missing_fields,
            }
        )
    return packs
