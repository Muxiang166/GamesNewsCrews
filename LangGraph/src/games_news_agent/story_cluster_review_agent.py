"""Story cluster semantic review agent — deterministic comparison of ambiguous
same-entity clusters that the lightweight dedup pass could not resolve."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Any
from urllib.parse import urlsplit, urlunsplit

AGENT_NAME = "StoryClusterReviewAgent"
SCHEMA_VERSION = "story_cluster_review_v0"

CLUSTER_ROLE_VALUES: set[str] = {
    "duplicate_report",
    "new_detail_after_announcement",
    "official_confirmation",
    "reaction_or_commentary",
    "unrelated",
}

# ---------------------------------------------------------------------------
# Detail / commentary keywords for deterministic classification
# ---------------------------------------------------------------------------

DETAIL_KEYWORDS: list[str] = [
    "新角色",
    "新预告",
    "发售日",
    "发售日期",
    "定档",
    "售价",
    "价格",
    "预购",
    "预载",
    "试玩",
    "demo",
    "dlc",
    "更新",
    "patch",
    "补丁",
    "系统要求",
    "配置",
    "画面对比",
    "实机演示",
    "gameplay",
    "trailer",
    "release date",
    "price",
    "preorder",
    "preload",
    "system requirements",
    "new character",
    "new trailer",
    "update",
]

COMMENTARY_KEYWORDS: list[str] = [
    "评论",
    "热议",
    "玩家反应",
    "吐槽",
    "整活",
    "梗",
    "恶搞",
    "二创",
    "网友",
    "社区",
    "分析",
    "评测",
    "测评",
    "观点",
    "看法",
    "为什么",
    "reaction",
    "commentary",
    "opinion",
    "editorial",
    "analysis",
    "review",
    "impressions",
    "hands-on",
    "take",
    "hot take",
]

OFFICIAL_SOURCE_PATTERNS: list[str] = [
    r"\bnintendo\b",
    r"\bplaystation\b",
    r"\bxbox\b",
    r"\bsteampowered\b",
    r"\bepicgames\b",
    r"\bsquare-enix\b",
    r"\bubisoft\b",
    r"\bea\.com\b",
    r"\bbethesda\b",
    r"\bcapcom\b",
    r"\bsega\b",
    r"\bbandainamco\b",
    r"\bactivision\b",
    r"\bblizzard\b",
    r"\briotgames\b",
    r"\brockstargames\b",
    r"\bfromsoftware\b",
    r"任天堂",
    r"索尼",
    r"微软",
]

SUGGESTED_ACTIONS: dict[str, str] = {
    "duplicate_report": "merge_clusters",
    "new_detail_after_announcement": "keep_separate_link_as_follow_up",
    "official_confirmation": "keep_separate_note_confirmation_source",
    "reaction_or_commentary": "keep_separate_link_as_reaction",
    "unrelated": "keep_separate",
}

# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------


def _canonical_url(raw_url: str) -> str:
    """Strip query string and fragment, lowercase scheme and host."""
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
    """NFKC-normalize, lowercase, keep alphanumeric and CJK tokens."""
    title = unicodedata.normalize("NFKC", str(raw_title or "")).lower()
    tokens = re.findall(r"[a-z0-9]+|[一-鿿]+", title)
    normalized = " ".join(tokens).strip()
    return normalized


def _title_token_set(title: str) -> set[str]:
    """Extract meaningful tokens from a title for Jaccard comparison.

    CJK sequences are further split into overlapping bigrams so that
    partial textual overlap (e.g. shared game-name characters) is
    captured even when the surrounding detail words differ.
    """
    normalized = _normalized_title(title)
    tokens: list[str] = []
    for token in normalized.split():
        if re.fullmatch(r"[一-鿿]{2,}", token):
            # CJK-run: emit character bigrams
            for i in range(len(token) - 1):
                tokens.append(token[i : i + 2])
        elif len(token) >= 2:
            tokens.append(token)
        elif re.fullmatch(r"[一-鿿]", token):
            # single isolated CJK char
            tokens.append(token)
        # skip single latin letters / digits
    return set(tokens)


def _jaccard(set_a: set[str], set_b: set[str]) -> float:
    """Jaccard similarity coefficient."""
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union)


def _extract_generic_entities(text: str) -> set[str]:
    """Pull named entities from 《...》 and double-quoted spans."""
    entities: set[str] = set()
    for value in re.findall(r"《([^》]{2,80})》", text):
        normalized = _normalized_title(value)
        if normalized:
            entities.add(normalized)
    for value in re.findall(r"[\"']([^\"']{3,80})[\"']", text):
        normalized = _normalized_title(value)
        if normalized:
            entities.add(normalized)
    return entities


def _extract_entities_from_cluster(
    cluster: dict[str, Any],
    request_entity: str,
) -> set[str]:
    """Extract game entities from a cluster using multiple signals.

    Combines 《...》/quoted-entity extraction, explicit game_title fields
    from context-pack candidates, and (when verified against the title)
    the dedup request entity.
    """
    entities: set[str] = set()
    title = str(cluster.get("canonical_title", ""))
    urls = [str(u) for u in cluster.get("source_urls", [])]
    combined = f"{title} {' '.join(urls)}"

    # Markup markers
    entities |= _extract_generic_entities(combined)

    # Explicit game_title from context-pack candidates
    for cand in cluster.get("_candidates", []):
        if not isinstance(cand, dict):
            continue
        game_title = str(cand.get("game_title", ""))
        if game_title:
            normalized = _normalized_title(game_title)
            if normalized:
                entities.add(normalized)

    # Request entity (the entity that caused dedup to group these clusters).
    # Only accepted if it appears as a substring in the cluster title/urls
    # — this prevents spurious matches from overly generic entity keys.
    req_entity = _normalized_title(request_entity)
    if req_entity and len(req_entity) >= 2:
        norm_title = _normalized_title(title)
        haystack = f"{norm_title} {combined}"
        if req_entity in haystack:
            entities.add(req_entity)

    return entities


def _has_any_keyword(text: str, keywords: list[str]) -> bool:
    text_lower = text.lower()
    for kw in keywords:
        if kw in text_lower:
            return True
    return False


def _is_official_source(source_urls: list[str]) -> bool:
    for url in source_urls:
        for pattern in OFFICIAL_SOURCE_PATTERNS:
            if re.search(pattern, str(url), flags=re.IGNORECASE):
                return True
    return False


# ---------------------------------------------------------------------------
# Cluster comparison
# ---------------------------------------------------------------------------


def _time_proximity_hours(
    cluster_a: dict[str, Any],
    cluster_b: dict[str, Any],
) -> float | None:
    """Return approximate time separation in hours, or None if no timestamps."""
    candidates_a = cluster_a.get("_candidates", [])
    candidates_b = cluster_b.get("_candidates", [])
    if not candidates_a or not candidates_b:
        return None
    from datetime import datetime, timezone

    def _best_time(cands: list[dict[str, Any]]) -> datetime | None:
        best: datetime | None = None
        for c in cands:
            for key in ("published_at", "observed_at", "discovered_at"):
                raw = c.get(key)
                if raw is None or raw == "":
                    continue
                try:
                    if isinstance(raw, datetime):
                        dt = raw
                    else:
                        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    continue
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if best is None or dt < best:
                    best = dt
                break
        return best

    ta = _best_time(candidates_a)
    tb = _best_time(candidates_b)
    if ta is None or tb is None:
        return None
    return abs((ta - tb).total_seconds()) / 3600.0


def _source_diversity_score(
    cluster_a: dict[str, Any],
    cluster_b: dict[str, Any],
) -> float:
    """Measure how distinct the source domains are between clusters.
    Returns 0 (all same) to 1 (completely distinct sources).
    """
    urls_a = [str(u) for u in cluster_a.get("source_urls", [])]
    urls_b = [str(u) for u in cluster_b.get("source_urls", [])]
    domains_a: set[str] = set()
    domains_b: set[str] = set()
    for u in urls_a:
        try:
            domains_a.add(urlsplit(u).netloc.lower())
        except ValueError:
            pass
    for u in urls_b:
        try:
            domains_b.add(urlsplit(u).netloc.lower())
        except ValueError:
            pass
    if not domains_a or not domains_b:
        return 0.5  # cannot determine
    shared = domains_a & domains_b
    all_domains = domains_a | domains_b
    if not all_domains:
        return 0.5
    return 1.0 - len(shared) / len(all_domains)


def _request_id(request: dict[str, Any]) -> str:
    return str(request.get("request_id", ""))


def _compare_clusters(
    cluster_a: dict[str, Any],
    cluster_b: dict[str, Any],
) -> dict[str, Any]:
    """Compare two story clusters and classify their relationship.

    Returns a per-pair decision dict with cluster_role, confidence,
    and evidence_summary.
    """
    title_a = str(cluster_a.get("canonical_title", ""))
    title_b = str(cluster_b.get("canonical_title", ""))
    id_a = str(cluster_a.get("story_cluster_id", ""))
    id_b = str(cluster_b.get("story_cluster_id", ""))
    urls_a = [str(u) for u in cluster_a.get("source_urls", [])]
    urls_b = [str(u) for u in cluster_b.get("source_urls", [])]

    # --- 1. URL canonical exact match ----------------------------------
    canonical_a = {_canonical_url(u) for u in urls_a} - {""}
    canonical_b = {_canonical_url(u) for u in urls_b} - {""}
    if canonical_a & canonical_b:
        return {
            "cluster_a_id": id_a,
            "cluster_b_id": id_b,
            "cluster_role": "duplicate_report",
            "confidence": 0.95,
            "evidence_summary": (
                "Canonical URLs (scheme+host+path, without query/fragment) "
                "are identical — same underlying article."
            ),
            "suggested_action": SUGGESTED_ACTIONS["duplicate_report"],
        }

    # --- Tokenization --------------------------------------------------
    tokens_a = _title_token_set(title_a)
    tokens_b = _title_token_set(title_b)
    title_jaccard = _jaccard(tokens_a, tokens_b)

    # Extract game-name entities (uses verified request entity, game_title
    # field, markup markers, etc.)
    req_entity = str(cluster_a.get("_request_entity", ""))
    entities_a = _extract_entities_from_cluster(cluster_a, req_entity)
    entities_b = _extract_entities_from_cluster(cluster_b, req_entity)

    entity_overlap = bool(entities_a & entities_b)
    all_entities = entities_a | entities_b

    # Detail / commentary keyword checks
    detail_a = _has_any_keyword(title_a, DETAIL_KEYWORDS)
    detail_b = _has_any_keyword(title_b, DETAIL_KEYWORDS)
    commentary_a = _has_any_keyword(title_a, COMMENTARY_KEYWORDS)
    commentary_b = _has_any_keyword(title_b, COMMENTARY_KEYWORDS)

    # Official source check
    official_a = _is_official_source(urls_a)
    official_b = _is_official_source(urls_b)

    # Time proximity
    time_hours = _time_proximity_hours(cluster_a, cluster_b)

    # Source diversity
    source_div = _source_diversity_score(cluster_a, cluster_b)

    # --- 2. Very high Jaccard → duplicate (even without entity markers)
    if title_jaccard > 0.8:
        conf = round(max(0.82, min(0.95, title_jaccard)), 2)
        evidence = (
            f"Title Jaccard={title_jaccard:.2f} (>0.8)"
        )
        if entity_overlap:
            conf = min(conf + 0.03, 0.97)
            evidence += (
                f" with overlapping game entities {sorted(all_entities)[:5]}"
            )
        evidence += ". Titles are paraphrases of the same report."
        return {
            "cluster_a_id": id_a,
            "cluster_b_id": id_b,
            "cluster_role": "duplicate_report",
            "confidence": conf,
            "evidence_summary": evidence,
            "suggested_action": SUGGESTED_ACTIONS["duplicate_report"],
        }

    # --- 3. Official source + same event → official confirmation ------
    if (official_a or official_b) and entity_overlap:
        conf = 0.82
        if official_a and official_b:
            conf = 0.88
        return {
            "cluster_a_id": id_a,
            "cluster_b_id": id_b,
            "cluster_role": "official_confirmation",
            "confidence": round(conf, 2),
            "evidence_summary": (
                f"At least one cluster originates from an official source "
                f"(official_a={official_a}, official_b={official_b}) and "
                f"both share game entities {sorted(all_entities)[:5]}. "
                f"One is likely the official announcement; the other is "
                f"media coverage."
            ),
            "suggested_action": SUGGESTED_ACTIONS["official_confirmation"],
        }

    # --- 4. Low overlap + same game + commentary → reaction -----------
    # Checked BEFORE new-detail so that titles with clear commentary
    # signals are classified as reactions even when one side also
    # carries detail keywords.
    if title_jaccard < 0.4 and entity_overlap and (commentary_a or commentary_b):
        return {
            "cluster_a_id": id_a,
            "cluster_b_id": id_b,
            "cluster_role": "reaction_or_commentary",
            "confidence": 0.68,
            "evidence_summary": (
                f"Title Jaccard={title_jaccard:.2f} (<0.4) with shared "
                f"entities {sorted(all_entities)[:5]} and "
                f"commentary/reaction tone. Likely a reaction piece or "
                f"community discussion, not a separate news event."
            ),
            "suggested_action": SUGGESTED_ACTIONS["reaction_or_commentary"],
        }

    # --- 5. Medium Jaccard + same game + detail keywords → follow-up --
    detail_jaccard_range = 0.15 <= title_jaccard <= 0.8
    if detail_jaccard_range and entity_overlap and (detail_a or detail_b):
        conf = 0.70
        if time_hours is not None and time_hours < 72:
            conf = 0.76
        if source_div > 0.5:
            conf = min(conf + 0.05, 0.90)
        return {
            "cluster_a_id": id_a,
            "cluster_b_id": id_b,
            "cluster_role": "new_detail_after_announcement",
            "confidence": round(conf, 2),
            "evidence_summary": (
                f"Title Jaccard={title_jaccard:.2f} with shared "
                f"game entities {sorted(all_entities)[:5]} and distinct detail "
                f"keywords (detail_a={detail_a}, detail_b={detail_b}). "
                f"Likely a follow-up announcement or new detail."
            ),
            "suggested_action": SUGGESTED_ACTIONS["new_detail_after_announcement"],
        }

    # --- 6. Default: unrelated ----------------------------------------
    conf = 0.55 if entity_overlap else 0.82
    return {
        "cluster_a_id": id_a,
        "cluster_b_id": id_b,
        "cluster_role": "unrelated",
        "confidence": round(conf, 2),
        "evidence_summary": (
            f"Title Jaccard={title_jaccard:.2f}, "
            f"entity_overlap={entity_overlap}, "
            f"shared entities={sorted(all_entities)[:5] if all_entities else 'none'}. "
            f"{'Shared entities but insufficient textual similarity.' if entity_overlap else 'Different events — no entity or title overlap.'}"
        ),
        "suggested_action": SUGGESTED_ACTIONS["unrelated"],
    }


# ---------------------------------------------------------------------------
# Agent class
# ---------------------------------------------------------------------------


class StoryClusterReviewAgent:
    """Deterministic agent that reviews ambiguous story-cluster relationships.

    When the lightweight dedup pass (URL canonicalization, title normalisation)
    cannot decide whether two clusters refer to the same story, this agent
    applies evidence-based heuristics (title Jaccard, entity overlap, time
    proximity, source diversity, keyword detection) to classify the
    relationship.

    It does **not** use an LLM and does **not** invent new facts — every
    decision is backed by concrete evidence signals recorded in the output.
    """

    def __init__(
        self,
        dedup_semantic_review_requests: list[dict[str, Any]],
        context_packs: list[dict[str, Any]] | None = None,
        evidence_chunks: list[dict[str, Any]] | None = None,
        candidate_memory: dict[str, Any] | None = None,
    ):
        self.review_requests = dedup_semantic_review_requests
        self.context_packs = context_packs or []
        self.evidence_chunks = evidence_chunks or []
        self.candidate_memory = candidate_memory or {}

        # Build lookup: story_cluster_id → enriched cluster info
        self._cluster_lookup: dict[str, dict[str, Any]] = {}
        self._build_cluster_lookup()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_cluster_lookup(self) -> None:
        """Index context_packs by story_cluster_id to enrich cluster info."""
        # First pass: gather candidates per story_cluster_id
        cluster_candidates: dict[str, list[dict[str, Any]]] = {}
        for pack in self.context_packs:
            if not isinstance(pack, dict):
                continue
            candidate = pack.get("candidate", {})
            if not isinstance(candidate, dict):
                continue
            cluster_id = str(candidate.get("story_cluster_id", ""))
            if not cluster_id:
                continue
            cluster_candidates.setdefault(cluster_id, []).append(candidate)

        # Second pass: build enriched cluster entries from review requests
        for request in self.review_requests:
            if not isinstance(request, dict):
                continue
            entity = str(request.get("entity", ""))
            for cand in request.get("candidates", []):
                if not isinstance(cand, dict):
                    continue
                cluster_id = str(cand.get("story_cluster_id", ""))
                if not cluster_id:
                    continue
                entry = dict(cand)
                entry["_request_entity"] = entity
                entry["_request_id"] = str(request.get("request_id", ""))
                entry["_candidates"] = cluster_candidates.get(cluster_id, [])
                self._cluster_lookup[cluster_id] = entry

    def _request_for_clusters(
        self, cluster_ids: list[str]
    ) -> dict[str, Any] | None:
        for request in self.review_requests:
            if not isinstance(request, dict):
                continue
            req_ids = [
                str(c.get("story_cluster_id", ""))
                for c in request.get("candidates", [])
                if isinstance(c, dict)
            ]
            if set(cluster_ids).issubset(set(req_ids)):
                return request
        return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def review_cluster(self, request: dict[str, Any]) -> dict[str, Any]:
        """Review a single dedup review request containing multiple clusters.

        Compares every pair of clusters in the request and classifies
        their relationship using deterministic signals.
        """
        request_id = str(request.get("request_id", ""))
        entity = str(request.get("entity", ""))
        candidates = request.get("candidates", [])
        if not isinstance(candidates, list) or len(candidates) < 2:
            return {
                "request_id": request_id,
                "agent_name": AGENT_NAME,
                "schema_version": SCHEMA_VERSION,
                "entity": entity,
                "total_clusters": len(candidates) if isinstance(candidates, list) else 0,
                "total_comparisons": 0,
                "decisions": [],
                "dominant_role": "unrelated",
                "overall_confidence": 0.0,
                "aggregate_summary": "Insufficient clusters for comparison.",
            }

        # Enrich clusters from our lookup
        enriched: list[dict[str, Any]] = []
        for cand in candidates:
            if not isinstance(cand, dict):
                continue
            cluster_id = str(cand.get("story_cluster_id", ""))
            lookup_entry = self._cluster_lookup.get(cluster_id, {})
            enriched_entry = dict(cand)
            enriched_entry["_request_entity"] = entity
            enriched_entry["_request_id"] = request_id
            enriched_entry["_candidates"] = lookup_entry.get("_candidates", [])
            enriched.append(enriched_entry)

        # Compare every pair
        pair_decisions: list[dict[str, Any]] = []
        for i in range(len(enriched)):
            for j in range(i + 1, len(enriched)):
                decision = _compare_clusters(enriched[i], enriched[j])
                pair_decisions.append(decision)

        # Determine dominant classification
        role_votes: dict[str, int] = {}
        role_confidences: dict[str, list[float]] = {}
        for d in pair_decisions:
            role = d.get("cluster_role", "unrelated")
            role_votes[role] = role_votes.get(role, 0) + 1
            role_confidences.setdefault(role, []).append(d.get("confidence", 0.0))

        dominant_role = max(role_votes, key=lambda k: (role_votes[k], sum(role_confidences.get(k, [0])) / max(len(role_confidences.get(k, [1])), 1)))
        overall_conf = round(
            sum(role_confidences.get(dominant_role, [0.0]))
            / max(len(role_confidences.get(dominant_role, [1])), 1),
            2,
        )

        return {
            "request_id": request_id,
            "agent_name": AGENT_NAME,
            "schema_version": SCHEMA_VERSION,
            "entity": entity,
            "total_clusters": len(enriched),
            "total_comparisons": len(pair_decisions),
            "decisions": pair_decisions,
            "dominant_role": dominant_role,
            "overall_confidence": overall_conf,
            "aggregate_summary": (
                f"Compared {len(pair_decisions)} cluster pair(s) for entity "
                f"'{entity}'. Dominant classification: {dominant_role} "
                f"(confidence={overall_conf}). "
                f"Vote breakdown: {role_votes}."
            ),
        }

    def review_all(self) -> list[dict[str, Any]]:
        """Run review for every pending request."""
        results: list[dict[str, Any]] = []
        for request in self.review_requests:
            if not isinstance(request, dict):
                continue
            result = self.review_cluster(request)
            results.append(result)
        return results


# ---------------------------------------------------------------------------
# Convenience entry point
# ---------------------------------------------------------------------------


def run_story_cluster_review(
    dedup_requests: list[dict[str, Any]],
    context_packs: list[dict[str, Any]] | None = None,
    evidence_chunks: list[dict[str, Any]] | None = None,
    candidate_memory: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Main entry point for the StoryClusterReviewAgent.

    Args:
        dedup_requests: Review requests from deduplication.annotate_story_clusters.
        context_packs: Context packs with candidate details per cluster.
        evidence_chunks: Optional fetched-document evidence chunks.
        candidate_memory: Optional candidate memory records.

    Returns:
        A list of review result dicts — one per request.  Suitable for
        serializing as ``story_cluster_review_decisions.json``.
    """
    agent = StoryClusterReviewAgent(
        dedup_semantic_review_requests=dedup_requests,
        context_packs=context_packs or [],
        evidence_chunks=evidence_chunks or [],
        candidate_memory=candidate_memory or {},
    )
    return agent.review_all()
