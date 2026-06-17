"""Lightweight evidence chunk storage primitives."""

from __future__ import annotations

import re
from typing import Any


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _chunk_text(text: str, *, max_chars: int, overlap: int) -> list[str]:
    cleaned = _clean_text(text)
    if not cleaned:
        return []
    if max_chars <= 0:
        return [cleaned]

    chunks: list[str] = []
    start = 0
    safe_overlap = max(0, min(overlap, max_chars - 1))
    while start < len(cleaned):
        end = min(start + max_chars, len(cleaned))
        chunks.append(cleaned[start:end].strip())
        if end == len(cleaned):
            break
        start = end - safe_overlap
    return [chunk for chunk in chunks if chunk]


def build_evidence_chunks(
    documents: list[dict[str, Any]],
    *,
    max_chars: int = 700,
    overlap: int = 120,
) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for document_index, document in enumerate(documents):
        url = str(document.get("candidate_url", ""))
        source_id = str(document.get("source_id", ""))
        title = str(document.get("title", ""))
        content_chunks = _chunk_text(
            str(document.get("content", "")),
            max_chars=max_chars,
            overlap=overlap,
        )
        for chunk_index, quote in enumerate(content_chunks):
            chunks.append(
                {
                    "chunk_id": f"{source_id}-{document_index}-{chunk_index}",
                    "url": url,
                    "source_id": source_id,
                    "source_kind": document.get("metadata", {}).get("source_kind", ""),
                    "title": title,
                    "published_at": document.get("published_at"),
                    "observed_at": document.get("metadata", {}).get("observed_at"),
                    "quote": quote,
                    "credibility_hint": document.get("metadata", {}).get("candidate_type", ""),
                    "document_index": document_index,
                    "chunk_index": chunk_index,
                    "metadata": document.get("metadata", {}),
                }
            )
    return chunks
