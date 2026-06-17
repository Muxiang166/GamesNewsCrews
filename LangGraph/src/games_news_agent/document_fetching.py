"""Fetch and normalize article documents for selected candidates."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from .collectors.web import WebPageCollector
from .fetching import FetchResult


class TextFetcher(Protocol):
    def fetch_text(self, url: str) -> FetchResult:
        ...


@dataclass(frozen=True)
class DocumentFetchResult:
    documents: list[dict[str, Any]] = field(default_factory=list)
    raw_fetches: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)


def _candidate_metadata(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_title": candidate.get("title", ""),
        "candidate_type": candidate.get("candidate_type", ""),
        "candidate_lane": candidate.get("candidate_lane", ""),
        "theme_section": candidate.get("theme_section", ""),
        "heat_score": candidate.get("heat_score", 0),
        "heat_reasons": candidate.get("heat_reasons", []),
    }


def _with_candidate_metadata(
    document: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    enriched = dict(document)
    metadata = dict(enriched.get("metadata", {}))
    metadata.update(_candidate_metadata(candidate))
    enriched["metadata"] = metadata
    return enriched


def _candidate_fallback_content(candidate: dict[str, Any]) -> str:
    parts = [
        str(candidate.get("title") or "").strip(),
        str(candidate.get("snippet") or "").strip(),
    ]
    return "\n".join(part for part in parts if part).strip()


def synthetic_documents_from_candidates(
    candidates: list[dict[str, Any]],
    *,
    fetched_at: datetime,
    limit: int,
) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    for candidate in candidates[: max(limit, 0)]:
        title = str(candidate.get("title", ""))
        snippet = str(candidate.get("snippet", ""))
        content = "\n".join(part for part in [title, snippet] if part).strip()
        document = {
            "candidate_url": str(candidate.get("url", "")),
            "title": title or str(candidate.get("url", "")),
            "source_id": str(candidate.get("source_id", "")),
            "content": content,
            "author": None,
            "published_at": candidate.get("published_at") or candidate.get("observed_at"),
            "fetched_at": fetched_at.isoformat(),
            "image_urls": [],
            "metadata": {
                **_candidate_metadata(candidate),
                "dry_run_synthetic": True,
            },
        }
        documents.append(document)
    return documents


def fetch_candidate_documents(
    candidates: list[dict[str, Any]],
    *,
    fetcher: TextFetcher,
    fetched_at: datetime,
    limit: int,
) -> DocumentFetchResult:
    result = DocumentFetchResult()
    for candidate in candidates[: max(limit, 0)]:
        url = str(candidate.get("url", ""))
        source_id = str(candidate.get("source_id", ""))
        if not url:
            result.errors.append(
                {
                    "candidate_url": "",
                    "source_id": source_id,
                    "title": candidate.get("title", ""),
                    "error": "missing_url",
                }
            )
            continue

        fetch_result = fetcher.fetch_text(url)
        result.raw_fetches.append(
            {
                "url": url,
                "source_id": source_id,
                "ok": fetch_result.ok,
                "status_code": fetch_result.status_code,
                "content_type": fetch_result.content_type,
                "error": fetch_result.error,
                "fetched_at": fetched_at.isoformat(),
            }
        )
        if not fetch_result.ok:
            result.errors.append(
                {
                    "candidate_url": url,
                    "source_id": source_id,
                    "title": candidate.get("title", ""),
                    "status_code": fetch_result.status_code,
                    "error": fetch_result.error,
                }
            )
            continue

        document = WebPageCollector(source_id=source_id).parse_html(
            url=url,
            html=fetch_result.text,
            fetched_at=fetched_at,
        )
        document = _with_candidate_metadata(document, candidate)
        if not str(document.get("content") or "").strip():
            fallback_content = _candidate_fallback_content(candidate)
            if not fallback_content:
                result.errors.append(
                    {
                        "candidate_url": url,
                        "source_id": source_id,
                        "title": candidate.get("title", ""),
                        "status_code": fetch_result.status_code,
                        "error": "empty_document_content",
                    }
                )
                continue
            document["content"] = fallback_content
            metadata = dict(document.get("metadata", {}))
            metadata["content_fallback"] = "candidate_text"
            document["metadata"] = metadata
        result.documents.append(document)

    return result
