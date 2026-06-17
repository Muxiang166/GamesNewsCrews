"""Event timeline construction (CLU-003) and historical duplicate check (CLU-004).

CLU-003  Event Timeline:
  - ``build_event_timeline``  group story clusters by event, order
    chronologically, label each entry (initial_report / new_detail /
    official_confirmation / reaction / correction).
  - ``detect_continuous_event``  identify 发布会/直播/游戏节 burst patterns
    by detecting concentration of same-game stories within a short timeframe.

CLU-004  Historical Duplicate Check:
  - ``check_historical_duplicate``  classify a single candidate against
    candidate memory as new_story / late_repost / follow_up_update.
  - ``batch_historical_duplicate_check``  run the check across a batch.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlsplit, urlunsplit


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _isoformat(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _parse_datetime(value: Any) -> datetime | None:
    """Safely parse a datetime from a string or datetime object."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None
    else:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalized_title(raw_title: str, *, min_compact_len: int = 10) -> str:
    """Normalize a title string for comparison: NFKC, lower, tokens.

    Returns empty string when the compact (no-space) result is shorter than
    *min_compact_len* — this prevents false matches on very short fragments.
    """
    title = unicodedata.normalize("NFKC", str(raw_title or ""))
    tokens = re.findall(r"[a-z0-9]+|[一-鿿]+", title.lower())
    normalized = " ".join(tokens).strip()
    compact = normalized.replace(" ", "")
    if len(compact) < min_compact_len:
        return ""
    return normalized


def _normalized_entity(raw_name: str) -> str:
    """Normalize a game entity name — lenient threshold for short names."""
    return _normalized_title(raw_name, min_compact_len=2)


def _canonical_url(raw_url: str) -> str:
    """Reduce a URL to scheme + netloc + normalised path (no qs / fragment)."""
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


def _game_entities_from_text(text: str) -> list[str]:
    """Extract game name entities from a text blob.

    Looks for 《...》 and double-quoted names, then normalises.
    """
    entities: list[str] = []
    for value in re.findall(r"《([^》]{2,80})》", text):
        entities.append(value)
    for value in re.findall(r"[\"']([^\"']{3,80})[\"']", text):
        entities.append(value)
    result: list[str] = []
    for entity in entities:
        norm = _normalized_entity(entity)
        if norm and norm not in result:
            result.append(norm)
    return result


def _text_search_pool(candidate: dict[str, Any]) -> str:
    return " ".join(
        str(candidate.get(key, "") or "")
        for key in ("title", "snippet", "game_title", "canonical_title", "candidate_type")
    )


# ---------------------------------------------------------------------------
# Event-type classification
# ---------------------------------------------------------------------------

_EVENT_TYPE_RULES: list[tuple[str, str]] = [
    ("confirmed_report", r"已上线|正式上线|推送上线|公布|发布|发售|定档|确认|宣布|官方宣布|公开|"
     r"正式公开|\b(confirmed|revealed|announced)\b"),
    ("community_reaction", r"热议|争议|走红|疯传|转发|玩家反应|客服|补偿|梗|整活|离谱|"
     r"投票|评论区|火了|刷屏"),
    ("review_or_score", r"评分|评测|评分解禁|m站|metacritic|opencritic|review score|媒体评分|"
     r"斩获.*分|获得.*分|高分|低分"),
    ("price_or_market", r"售价|涨价|降价|价格|销量|首周|定价|股价|暴涨|暴跌|"
     r"\b(price|pricing|sale figure|revenue)\b"),
    ("leak_or_rumor", r"爆料|泄露|传闻|据称|有望|曝光|\b(leak|rumor)\b"),
    ("patch_or_update", r"更新|补丁|新版本|赛季更新|\b(patch|update|hotfix)\b|上线更新|新增内容"),
    ("release_or_launch", r"发售|解锁|预载|上线|推出|登陆|launch|已登陆|即将登陆"),
    ("development", r"开发|制作人|主创|工作室|团队|开发进展|\b(developer|studio update)\b"),
]


def _classify_event_type(source: dict[str, Any]) -> str:
    """Return the most specific event type for a cluster or candidate."""
    text = _text_search_pool(source).lower()
    for event_type, pattern in _EVENT_TYPE_RULES:
        if re.search(pattern, text, re.IGNORECASE):
            return event_type
    candidate_type = str(source.get("candidate_type", "news"))
    if candidate_type == "rumor":
        return "leak_or_rumor"
    if candidate_type == "review_score":
        return "review_or_score"
    if candidate_type == "platform_price":
        return "price_or_market"
    return "general_news"


# ---------------------------------------------------------------------------
# Entry label derivation
# ---------------------------------------------------------------------------

_CORRECTION_KEYWORDS = {"更正", "纠正", "修正", "澄清", "辟谣", "correction", "correct", "clarify"}


def _derive_entry_label(
    cluster: dict[str, Any],
    *,
    is_first: bool,
    event_has_official: bool,
    idx: int,
    total: int,
) -> str:
    """Derive a human-readable timeline entry label."""
    title_lower = str(cluster.get("canonical_title", "")).lower()
    tags = {str(t).lower() for t in cluster.get("tags", [])}

    # Correction check
    if any(kw in title_lower for kw in _CORRECTION_KEYWORDS) or (
        tags & _CORRECTION_KEYWORDS
    ):
        return "correction"

    event_type = _classify_event_type(cluster)

    # First entry
    if is_first and idx == 0:
        event_type_str = str(cluster.get("candidate_type", "news"))
        if event_type_str == "rumor":
            return "initial_report"
        return "initial_report"

    # Official confirmation
    if event_type == "confirmed_report" and str(cluster.get("candidate_type", "")) == "news":
        return "official_confirmation"

    # Reaction
    if event_type == "community_reaction":
        return "reaction"

    # Subsequent detail
    if total > 1 and idx > 0:
        return "new_detail"

    return "new_detail"


# ---------------------------------------------------------------------------
# CLU-003  build_event_timeline
# ---------------------------------------------------------------------------

def _cluster_event_key(cluster: dict[str, Any]) -> str:
    """Create a stable grouping key: same game entity + same event type."""
    sigs = sorted(set(
        str(e).strip().lower()
        for e in cluster.get("entity_signatures", [])
        if str(e).strip()
    ))
    event_type = _classify_event_type(cluster)
    entities_hash = (
        hashlib.sha1("|".join(sigs).encode("utf-8")).hexdigest()[:16]
        if sigs
        else "no_entity"
    )
    return f"ev:{entities_hash}:{event_type}"


def _cluster_best_time(cluster: dict[str, Any]) -> datetime | None:
    for key in ("observed_at", "published_at", "discovered_at", "first_seen_at"):
        parsed = _parse_datetime(cluster.get(key))
        if parsed:
            return parsed
    return None


def _timeline_snapshot(
    cluster: dict[str, Any],
    claims_by_story: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    cluster_id = str(cluster.get("id", ""))
    related = claims_by_story.get(cluster_id, [])
    metadata: dict[str, Any] = {}
    if related and isinstance(related[0].get("metadata"), dict):
        metadata = related[0]["metadata"]

    observed_at = metadata.get("observed_at") or cluster.get("observed_at")
    published_at = metadata.get("published_at") or cluster.get("published_at")

    return {
        "story_cluster_id": cluster_id,
        "canonical_title": cluster.get("canonical_title", ""),
        "entity_signatures": cluster.get("entity_signatures", []),
        "source_urls": cluster.get("source_urls", []),
        "candidate_count": cluster.get("candidate_count", 0),
        "candidate_type": cluster.get("candidate_type",
                                      str(metadata.get("candidate_type", "news"))),
        "event_type": _classify_event_type(cluster),
        "observed_at": _isoformat(_parse_datetime(observed_at)) if observed_at else None,
        "published_at": _isoformat(_parse_datetime(published_at)) if published_at else None,
        "heat_score": metadata.get("heat_score") or cluster.get("heat_score", 0),
        "discussion_score": metadata.get("discussion_score") or cluster.get("discussion_score", 0),
        "claim_count": len(related),
    }


def _timeline_label(entities: list[str], event_has_official: bool) -> str:
    label_entity = " / ".join(entities[:2]) if entities else "未识别游戏"
    if event_has_official:
        return f"{label_entity} — 官方动态时间线"
    return f"{label_entity} — 事件时间线"


def build_event_timeline(
    story_clusters: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    context_packs: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build event timelines from story clusters and claims (CLU-003).

    Parameters
    ----------
    story_clusters : list[dict]
        Output of ``annotate_story_clusters``. Each cluster has an ``id``,
        ``entity_signatures``, ``canonical_title``, ``source_urls``, etc.
    claims : list[dict]
        Output of ``build_claims_from_context_packs``. Each claim has a
        ``story_id`` that matches a cluster id.
    context_packs : list[dict]
        Original context packs (used as a fallback for extra metadata).

    Returns
    -------
    dict
        A dictionary suitable for serialization as **event_timelines.json**::

            {
                "version": "0.1.0",
                "generated_at": "<iso>",
                "total_timelines": N,
                "total_entries": M,
                "timelines": [
                    {
                        "event_id": "...",
                        "timeline_label": "...",
                        "entity_signatures": [...],
                        "started_at": "<iso>",
                        "last_updated_at": "<iso>",
                        "entry_count": N,
                        "has_official_confirmation": bool,
                        "has_community_reaction": bool,
                        "has_correction": bool,
                        "entries": [
                            {
                                "story_cluster_id": "...",
                                "chronological_index": 0,
                                "event_label": "initial_report" | ...,
                                ...
                            }
                        ]
                    }
                ]
            }
    """
    # Index claims by story_id
    claims_by_story: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        sid = str(claim.get("story_id", ""))
        if sid:
            claims_by_story[sid].append(claim)

    # Enrich clusters with extra fields from claims metadata
    enriched: list[dict[str, Any]] = []
    for cluster in story_clusters:
        if not isinstance(cluster, dict):
            continue
        c = dict(cluster)
        cid = str(cluster.get("id", ""))
        related = claims_by_story.get(cid, [])
        if related and isinstance(related[0].get("metadata"), dict):
            meta = related[0]["metadata"]
            for k in ("candidate_type", "observed_at", "published_at",
                       "heat_score", "discussion_score", "tags"):
                if meta.get(k) and not c.get(k):
                    c[k] = meta[k]
        enriched.append(c)

    # Group into events
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for cluster in enriched:
        groups[_cluster_event_key(cluster)].append(cluster)

    # Build timelines
    timelines: list[dict[str, Any]] = []
    for event_key, e_clusters in sorted(groups.items()):
        e_clusters.sort(
            key=lambda cl: _cluster_best_time(cl) or datetime(2000, 1, 1, tzinfo=timezone.utc)
        )

        all_types = [_classify_event_type(cl) for cl in e_clusters]
        has_official = "confirmed_report" in all_types
        has_reaction = "community_reaction" in all_types
        has_correction = any(
            any(kw in str(cl.get("canonical_title", "")).lower()
                for kw in _CORRECTION_KEYWORDS)
            or (set(str(t).lower() for t in cl.get("tags", [])) & _CORRECTION_KEYWORDS)
            for cl in e_clusters
        )

        all_entities: list[str] = []
        for cl in e_clusters:
            for e in cl.get("entity_signatures", []):
                if str(e) not in all_entities:
                    all_entities.append(str(e))

        total = len(e_clusters)
        entries: list[dict[str, Any]] = []
        for i, cl in enumerate(e_clusters):
            snap = _timeline_snapshot(cl, claims_by_story)
            snap["event_label"] = _derive_entry_label(
                cl,
                is_first=(i == 0),
                event_has_official=has_official,
                idx=i,
                total=total,
            )
            snap["chronological_index"] = i
            entries.append(snap)

        first_t = _cluster_best_time(e_clusters[0]) if e_clusters else None
        last_t = _cluster_best_time(e_clusters[-1]) if e_clusters else None

        timelines.append({
            "event_id": hashlib.sha1(event_key.encode("utf-8")).hexdigest()[:12],
            "event_key": event_key,
            "timeline_label": _timeline_label(all_entities, has_official),
            "entity_signatures": all_entities,
            "started_at": _isoformat(first_t) if first_t else None,
            "last_updated_at": _isoformat(last_t) if last_t else None,
            "entry_count": total,
            "has_official_confirmation": has_official,
            "has_community_reaction": has_reaction,
            "has_correction": has_correction,
            "event_types_present": list(dict.fromkeys(all_types)),
            "entries": entries,
        })

    timelines.sort(key=lambda t: t.get("started_at") or "2000-01-01", reverse=True)

    return {
        "version": "0.1.0",
        "generated_at": _isoformat(datetime.now(timezone.utc)),
        "total_timelines": len(timelines),
        "total_entries": sum(t["entry_count"] for t in timelines),
        "timelines": timelines,
    }


# ---------------------------------------------------------------------------
# CLU-003  detect_continuous_event
# ---------------------------------------------------------------------------

_LIVE_EVENT_PATTERNS: list[tuple[str, str]] = [
    ("livestream", r"直播|live broadcast|livestream|实况|试玩直播|前瞻直播|"
     r"特别节目|special program|全程直播"),
    ("press_conference", r"发布会|直面会|direct|showcase|state of play|"
     r"gamescom|tgs|东京电玩展|e3|"
     r"tga|the game awards|科隆|chinajoy|cj展|games award"),
    ("game_festival", r"游戏节|游戏展|嘉年华|festival|fest|游戏展会|试玩活动|"
     r"play day|preview event|开放日|summer game fest|"
     r"夏日游戏节"),
    ("beta_or_demo", r"试玩|demo|beta|公测|内测|体验版|测试.*上线|playtest|"
     r"early access.*上|抢先体验"),
    ("patch_day", r"赛季|更新.*上线|新版本|大型更新|资料片|expansion|dlc.*上线"
     r"|第.*季|season"),
]


def _detect_live_event_type(text: str) -> str:
    text_lower = text.lower()
    for etype, pattern in _LIVE_EVENT_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return etype
    return "story_burst"


def detect_continuous_event(
    candidates: list[dict[str, Any]],
    time_window_hours: int = 72,
) -> dict[str, Any]:
    """Detect live/continuous event burst patterns (CLU-003).

    Searches for concentration of same-game stories within a short
    timeframe — a signal of an ongoing 发布会 (press conference),
    直播 (livestream), or 游戏节 (game festival).

    Parameters
    ----------
    candidates : list[dict]
        Candidates with at minimum ``title``, and optionally
        ``observed_at`` / ``published_at`` / ``discovered_at``,
        ``story_cluster_id``, ``source_id``, ``url``, ``snippet``,
        ``game_title``, ``entity_signatures``.
    time_window_hours : int
        Sliding window width in hours (default 72 = 3 days).

    Returns
    -------
    dict
        Report suitable for **continuous_events.json**::

            {
                "version": "0.1.0",
                "generated_at": "<iso>",
                "time_window_hours": 72,
                "continuous_events": [
                    {
                        "continuous_event_id": "...",
                        "entity": "游戏名",
                        "event_type": "press_conference" | "livestream" | ...,
                        "story_count": N,
                        "started_at": "<iso>",
                        "ended_at": "<iso>",
                        "duration_hours": 2.5,
                        "source_ids": [...],
                        "urls": [...],
                        "candidate_story_cluster_ids": [...]
                    }
                ],
                "summary": {
                    "total_detected": N,
                    "by_type": {...}
                }
            }
    """
    if not candidates:
        return {
            "version": "0.1.0",
            "generated_at": _isoformat(datetime.now(timezone.utc)),
            "time_window_hours": time_window_hours,
            "continuous_events": [],
            "summary": {"total_detected": 0, "by_type": {}},
        }

    # Attach timestamps
    timed: list[tuple[datetime, dict[str, Any]]] = []
    for c in candidates:
        if not isinstance(c, dict):
            continue
        ts = _parse_datetime(
            c.get("observed_at") or c.get("published_at") or c.get("discovered_at")
        )
        if ts:
            timed.append((ts, c))
    timed.sort(key=lambda x: x[0])

    # Build per-entity timelines
    entity_buckets: dict[str, list[tuple[datetime, dict[str, Any]]]] = defaultdict(list)
    for ts, c in timed:
        text = " ".join(str(c.get(k, "") or "") for k in ("title", "snippet", "game_title"))
        entities = _game_entities_from_text(text)
        if not entities:
            entities = [str(e).strip() for e in c.get("entity_signatures", []) if str(e).strip()]
        if not entities:
            entities = ["_unidentified"]
        for ent in entities:
            norm = _normalized_entity(ent)
            if norm:
                entity_buckets[norm].append((ts, c))

    window = timedelta(hours=time_window_hours)
    continuous_events: list[dict[str, Any]] = []

    for entity, items in sorted(entity_buckets.items()):
        if entity == "_unidentified":
            continue
        if len(items) < 3:
            continue

        items.sort(key=lambda x: x[0])

        # Sliding-window burst detection
        burst_ranges: list[tuple[int, int]] = []  # [start, end)
        i = 0
        while i < len(items):
            j = i + 1
            while j < len(items) and (items[j][0] - items[i][0]) <= window:
                j += 1
            count = j - i
            if count >= 3:
                burst_ranges.append((i, j))
            i += 1

        # Merge overlapping ranges
        if not burst_ranges:
            continue
        merged: list[tuple[int, int]] = []
        for s, e in burst_ranges:
            if merged and s < merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], e))
            else:
                merged.append((s, e))

        for s, e in merged:
            w_items = items[s:e]
            w_cands = [c for _, c in w_items]
            w_times = [t for t, _ in w_items]

            combined_text = " ".join(
                str(c.get("title", "")) + " " + str(c.get("snippet", ""))
                for c in w_cands
            )
            live_type = _detect_live_event_type(combined_text)

            source_ids = list(dict.fromkeys(
                str(c.get("source_id", ""))
                for c in w_cands if c.get("source_id")
            ))
            urls = list(dict.fromkeys(
                str(c.get("url", ""))
                for c in w_cands if c.get("url")
            ))
            story_ids = list(dict.fromkeys(
                str(c.get("story_cluster_id", ""))
                for c in w_cands if c.get("story_cluster_id")
            ))

            continuous_events.append({
                "continuous_event_id": hashlib.sha1(
                    f"{entity}:{w_times[0].isoformat()}:{len(w_items)}".encode("utf-8")
                ).hexdigest()[:12],
                "entity": entity,
                "event_type": live_type,
                "story_count": len(w_items),
                "started_at": _isoformat(w_times[0]),
                "ended_at": _isoformat(w_times[-1]),
                "duration_hours": round(
                    (w_times[-1] - w_times[0]).total_seconds() / 3600, 1
                ),
                "source_ids": source_ids,
                "urls": urls,
                "candidate_story_cluster_ids": story_ids,
            })

    continuous_events.sort(key=lambda e: e["story_count"], reverse=True)

    by_type: dict[str, int] = {}
    for e in continuous_events:
        et = e["event_type"]
        by_type[et] = by_type.get(et, 0) + 1

    return {
        "version": "0.1.0",
        "generated_at": _isoformat(datetime.now(timezone.utc)),
        "time_window_hours": time_window_hours,
        "continuous_events": continuous_events,
        "summary": {
            "total_detected": len(continuous_events),
            "by_type": dict(sorted(by_type.items())),
        },
    }


# ---------------------------------------------------------------------------
# CLU-004  Historical Duplicate Check
# ---------------------------------------------------------------------------

def _url_similarity(url_a: str, url_b: str) -> float:
    """Compute URL similarity score (0.0 to 1.0).

    Exact canonical match = 1.0.  Same domain + partial path overlap is
    scored via Jaccard similarity of path tokens.
    """
    ca = _canonical_url(url_a)
    cb = _canonical_url(url_b)
    if not ca or not cb:
        return 0.0
    if ca == cb:
        return 1.0
    try:
        pa, pb = urlsplit(ca), urlsplit(cb)
    except ValueError:
        return 0.0
    if pa.netloc != pb.netloc:
        return 0.0
    tok_a = set(re.findall(r"[a-z0-9]+|[一-鿿]+", pa.path.lower()))
    tok_b = set(re.findall(r"[a-z0-9]+|[一-鿿]+", pb.path.lower()))
    if not tok_a or not tok_b:
        return 0.3
    inter = tok_a & tok_b
    union = tok_a | tok_b
    return len(inter) / len(union) if union else 0.3


def _title_token_overlap(title_a: str, title_b: str) -> float:
    """Jaccard similarity of normalised title tokens."""
    na = set(_normalized_title(title_a).split())
    nb = set(_normalized_title(title_b).split())
    if not na or not nb:
        return 0.0
    inter = na & nb
    union = na | nb
    return len(inter) / len(union) if union else 0.0


def _entity_match_score(entities_a: list[str], entities_b: list[str]) -> float:
    """Entity overlap score (intersection / min(|A|, |B|))."""
    na = {_normalized_entity(e) for e in entities_a}
    nb = {_normalized_entity(e) for e in entities_b}
    na.discard("")
    nb.discard("")
    if not na or not nb:
        return 0.0
    inter = na & nb
    if not inter:
        return 0.0
    return len(inter) / min(len(na), len(nb))


def check_historical_duplicate(
    candidate: dict[str, Any],
    candidate_memory: dict[str, dict[str, Any]],
    *,
    title_overlap_threshold: float = 0.6,
    entity_match_threshold: float = 0.5,
) -> dict[str, Any]:
    """Classify a candidate against persisted candidate memory (CLU-004).

    Uses three orthogonal signals:
    1. **URL normalisation** — exact canonical URL match is definitive.
    2. **Title token overlap** — high Jaccard similarity suggests same story.
    3. **Entity matching** — same game entity names reinforce the match.

    Parameters
    ----------
    candidate : dict
        A single candidate dict (must have ``url`` and ``title`` at minimum;
        ``snippet``, ``game_title``, and ``entity_signatures`` improve
        accuracy).
    candidate_memory : dict[str, dict]
        Records loaded by ``load_candidate_memory`` (keyed by memory_key).
    title_overlap_threshold : float
        Threshold above which titles are considered a strong match.
    entity_match_threshold : float
        Threshold above which entity overlap is considered significant.

    Returns
    -------
    dict
        Classification result::

            {
                "candidate_url": "...",
                "candidate_title": "...",
                "candidate_entities": [...],
                "classification": "new_story" | "late_repost" | "follow_up_update",
                "reasons": [...],
                "requires_review": bool,
                "best_match_score": 0.85,
                "best_match": {...},
                "all_matches_count": N,
                "all_matches": [...]
            }
    """
    candidate_url = str(candidate.get("url", ""))
    candidate_title = str(candidate.get("title", ""))
    candidate_text = _text_search_pool(candidate)
    candidate_entities = _game_entities_from_text(candidate_text)
    for e in candidate.get("entity_signatures", []):
        norm = _normalized_entity(str(e))
        if norm and norm not in candidate_entities:
            candidate_entities.append(norm)

    matches: list[dict[str, Any]] = []
    best_match: dict[str, Any] | None = None
    best_score = 0.0

    for memory_key, record in candidate_memory.items():
        if not isinstance(record, dict):
            continue

        record_urls: list[str] = record.get("urls", [])
        if not isinstance(record_urls, list):
            u = record.get("url")
            record_urls = [str(u)] if u else []

        record_titles: list[str] = record.get("titles", [])
        if not isinstance(record_titles, list):
            t = record.get("title")
            record_titles = [str(t)] if t else []

        # 1. URL
        url_scores = [_url_similarity(candidate_url, str(ru)) for ru in record_urls]
        max_url = max(url_scores) if url_scores else 0.0

        # 2. Title overlap
        title_scores = [
            _title_token_overlap(candidate_title, str(rt))
            for rt in record_titles
        ]
        max_title = max(title_scores) if title_scores else 0.0

        # 3. Entities
        rec_text_parts: list[str] = [str(record.get("title", "")), " ".join(record_titles)]
        rec_text = " ".join(part for part in rec_text_parts if part.strip())
        rec_entities = _game_entities_from_text(rec_text)
        entity_score = _entity_match_score(candidate_entities, rec_entities)

        combined = 0.5 * max_url + 0.35 * max_title + 0.15 * entity_score
        if max_url >= 0.99:
            combined = max(combined, 0.95)

        info = {
            "memory_key": memory_key,
            "url_similarity": round(max_url, 4),
            "title_overlap": round(max_title, 4),
            "entity_match": round(entity_score, 4),
            "combined_score": round(combined, 4),
            "first_seen_at": record.get("first_seen_at"),
            "seen_count": record.get("seen_count", 0),
            "matching_urls": [
                ru for ru in record_urls
                if _url_similarity(candidate_url, str(ru)) >= 0.8
            ],
            "matching_titles": [
                rt for rt in record_titles
                if _title_token_overlap(candidate_title, str(rt)) >= title_overlap_threshold
            ],
        }
        matches.append(info)

        if combined > best_score:
            best_score = combined
            best_match = info

    # --- classification ---
    if best_match is None or best_score < 0.3:
        classification = "new_story"
        reasons = ["no_historical_match_above_threshold"]
        requires_review = False
    elif best_score >= 0.9:
        classification = "late_repost"
        reasons = ["canonical_url_exact_match"
                   if (best_match.get("url_similarity", 0) >= 0.99)
                   else "high_title_overlap_and_entity_match",
                   "high_combined_score"]
        requires_review = False
    elif best_score >= 0.55:
        classification = "follow_up_update"
        reasons = ["moderate_similarity_suggests_follow_up",
                   "same_entity_different_details"]
        requires_review = True
    elif best_score >= 0.3:
        classification = "new_story"
        reasons = ["low_similarity_likely_different_event",
                   "minor_entity_overlap"]
        requires_review = False
    else:
        classification = "new_story"
        reasons = ["no_meaningful_match"]
        requires_review = False

    return {
        "candidate_url": candidate_url,
        "candidate_title": candidate_title,
        "candidate_entities": candidate_entities,
        "classification": classification,
        "reasons": reasons,
        "requires_review": requires_review,
        "best_match_score": round(best_score, 4),
        "best_match": best_match,
        "all_matches_count": len(matches),
        "all_matches": sorted(matches, key=lambda m: m["combined_score"], reverse=True)[:10],
    }


def batch_historical_duplicate_check(
    candidates: list[dict[str, Any]],
    candidate_memory: dict[str, dict[str, Any]],
    *,
    title_overlap_threshold: float = 0.6,
    entity_match_threshold: float = 0.5,
) -> dict[str, Any]:
    """Run ``check_historical_duplicate`` across a batch of candidates.

    Returns a report suitable for serialization as
    **historical_duplicate_check.json**.
    """
    results: list[dict[str, Any]] = []
    stats: dict[str, int] = {
        "new_story": 0,
        "late_repost": 0,
        "follow_up_update": 0,
        "requires_review": 0,
    }

    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        r = check_historical_duplicate(
            candidate,
            candidate_memory,
            title_overlap_threshold=title_overlap_threshold,
            entity_match_threshold=entity_match_threshold,
        )
        results.append(r)
        stats[r["classification"]] = stats.get(r["classification"], 0) + 1
        if r["requires_review"]:
            stats["requires_review"] += 1

    return {
        "version": "0.1.0",
        "generated_at": _isoformat(datetime.now(timezone.utc)),
        "total_checked": len(results),
        "summary": stats,
        "results": results,
    }
