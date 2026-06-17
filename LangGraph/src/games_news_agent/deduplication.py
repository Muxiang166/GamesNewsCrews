"""Lightweight story clustering before claim extraction."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Any
from urllib.parse import urlsplit, urlunsplit


def _text(candidate: dict[str, Any]) -> str:
    return " ".join(
        str(candidate.get(key, "") or "")
        for key in ("title", "snippet", "url", "game_title")
    ).lower()


def _canonical_url(raw_url: str) -> str:
    url = str(raw_url or "").strip()
    if not url:
        return ""
    try:
        parsed = urlsplit(url)
    except ValueError:
        return ""
    if not parsed.scheme or not parsed.netloc:
        return ""
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, "", ""))


def _normalized_title(raw_title: str) -> str:
    title = unicodedata.normalize("NFKC", str(raw_title or "")).lower()
    tokens = re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]+", title)
    normalized = " ".join(tokens).strip()
    compact = normalized.replace(" ", "")
    if len(compact) < 10:
        return ""
    return normalized


def _game_entities(candidate: dict[str, Any]) -> list[str]:
    entities: list[str] = []
    explicit = str(candidate.get("game_title") or "").strip()
    if explicit:
        entities.append(explicit)

    text = " ".join(str(candidate.get(key, "") or "") for key in ("title", "snippet"))
    for value in re.findall(r"《([^》]{2,80})》", text):
        entities.append(value)
    for value in re.findall(r"[\"']([^\"']{3,80})[\"']", text):
        entities.append(value)

    normalized_entities: list[str] = []
    for entity in entities:
        normalized = _normalized_title(entity)
        if normalized and normalized not in normalized_entities:
            normalized_entities.append(normalized)
    return normalized_entities


def _known_cluster_key(candidate: dict[str, Any]) -> tuple[str, str, str] | None:
    text = _text(candidate)
    if re.search(r"最终幻想\s*6|final fantasy\s*6|ff6", text, flags=re.IGNORECASE) and re.search(
        r"ai|重制|remake", text, flags=re.IGNORECASE
    ):
        return ("known:final_fantasy_6_ai_remake", "最终幻想6 AI重制版走红", "curated_rule")
    return None


def _cluster_key(candidate: dict[str, Any], duplicate_urls: set[str] | None = None) -> tuple[str, str, str]:
    known = _known_cluster_key(candidate)
    if known:
        return known

    title = str(candidate.get("title") or "").strip()
    canonical_url = _canonical_url(str(candidate.get("url") or ""))
    if canonical_url and duplicate_urls and canonical_url in duplicate_urls:
        return (f"url:{canonical_url}", title or canonical_url, "canonical_url")

    normalized_title = _normalized_title(title)
    candidate_type = str(candidate.get("candidate_type") or "news")
    if normalized_title:
        return (f"title:{candidate_type}:{normalized_title}", title or normalized_title, "normalized_title")

    if canonical_url:
        return (f"url:{canonical_url}", title or canonical_url, "canonical_url")

    digest_source = " ".join(title.lower().split()) or str(candidate.get("source_id") or "")
    digest = hashlib.sha1(digest_source.encode("utf-8")).hexdigest()[:12]
    return (f"fallback:{candidate_type}:{digest}", title or "Untitled story", "fallback_hash")


def _story_cluster_id(key: str) -> str:
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
    return f"story_{digest}"


def _dedup_review_requests(clusters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    clusters_by_entity: dict[str, list[dict[str, Any]]] = {}
    for cluster in clusters:
        for entity in cluster.get("entity_signatures", []):
            clusters_by_entity.setdefault(str(entity), []).append(cluster)

    requests: list[dict[str, Any]] = []
    for entity, entity_clusters in sorted(clusters_by_entity.items()):
        unique_clusters = {str(cluster["id"]): cluster for cluster in entity_clusters}
        if len(unique_clusters) < 2:
            continue
        cluster_list = list(unique_clusters.values())
        requests.append(
            {
                "request_id": f"dedup_semantic_{hashlib.sha1(entity.encode('utf-8')).hexdigest()[:12]}",
                "task_type": "story_cluster_semantic_review",
                "entity": entity,
                "reason": "same_entity_distinct_titles",
                "instruction": (
                    "Decide whether these clusters are duplicate reports, follow-up details, "
                    "official confirmations, reactions, or unrelated similar events. Do not add facts."
                ),
                "candidate_story_cluster_ids": [str(cluster["id"]) for cluster in cluster_list],
                "candidates": [
                    {
                        "story_cluster_id": str(cluster["id"]),
                        "canonical_title": str(cluster.get("canonical_title", "")),
                        "source_urls": list(cluster.get("source_urls", [])),
                    }
                    for cluster in cluster_list
                ],
            }
        )
    return requests


def annotate_story_clusters(context_packs: list[dict[str, Any]]) -> dict[str, Any]:
    """Annotate context-pack candidates with stable story cluster ids.

    This first pass intentionally merges only obvious duplicates. More ambiguous
    same-game relationships are emitted as review requests for a future
    RAG/LLM-backed story clustering agent.
    """

    clusters_by_key: dict[str, dict[str, Any]] = {}
    annotated_packs: list[dict[str, Any]] = []
    url_counts: dict[str, int] = {}

    for pack in context_packs:
        candidate = pack.get("candidate", {}) if isinstance(pack, dict) else {}
        if not isinstance(candidate, dict):
            continue
        canonical_url = _canonical_url(str(candidate.get("url") or ""))
        if canonical_url:
            url_counts[canonical_url] = url_counts.get(canonical_url, 0) + 1
    duplicate_urls = {url for url, count in url_counts.items() if count > 1}

    for pack in context_packs:
        if not isinstance(pack, dict):
            continue
        candidate = pack.get("candidate", {})
        if not isinstance(candidate, dict):
            candidate = {}
        key, canonical_title, merge_reason = _cluster_key(candidate, duplicate_urls)
        cluster_id = _story_cluster_id(key)

        cluster = clusters_by_key.setdefault(
            key,
            {
                "id": cluster_id,
                "key": key,
                "canonical_title": canonical_title,
                "candidate_count": 0,
                "source_urls": [],
                "merge_reason": merge_reason,
                "cluster_role": "primary_event",
                "entity_signatures": [],
            },
        )
        cluster["candidate_count"] += 1
        url = str(candidate.get("url") or "").strip()
        if url and url not in cluster["source_urls"]:
            cluster["source_urls"].append(url)
        for entity in _game_entities(candidate):
            if entity not in cluster["entity_signatures"]:
                cluster["entity_signatures"].append(entity)

        annotated_candidate = dict(candidate)
        annotated_candidate["story_cluster_id"] = cluster_id
        annotated_candidate["story_cluster_key"] = key
        annotated_candidate["canonical_story_title"] = canonical_title
        annotated_candidate["story_cluster_merge_reason"] = merge_reason

        annotated_pack = dict(pack)
        annotated_pack["candidate"] = annotated_candidate
        annotated_packs.append(annotated_pack)

    story_clusters = list(clusters_by_key.values())
    return {
        "context_packs": annotated_packs,
        "story_clusters": story_clusters,
        "dedup_semantic_review_requests": _dedup_review_requests(story_clusters),
    }
