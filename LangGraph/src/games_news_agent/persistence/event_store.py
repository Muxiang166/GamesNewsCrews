"""SQL event store for cross-run game-news entities (MEM-002).

This module persists game entities, news items, events, and their
relationships across LangGraph runs so that later stages — deduplication,
RAG, timeline queries, and editorial review — can query historical data.

Tables
------
- news_items        : canonical news articles with dedup fields.
- games             : canonical game entities with alias/plat info.
- news_game_links   : many-to-many between news_items and games.
- events            : game events (announcement, release, controversy, …).
- event_news_links  : many-to-many between events and news_items.
- decision_traces   : audit log of model decisions per run/stage.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Sequence
from urllib.parse import urlsplit, urlunsplit


SCHEMA_VERSION = "0.1.0"


# ---------------------------------------------------------------------------
# Row-level helpers (mirror pattern from sqlite_mirror.py)
# ---------------------------------------------------------------------------

def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _number(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return 0.0


def _int_or_none(value: Any) -> int | None:
    """Return an integer or None (for nullable integer columns)."""
    raw = str(value or "").strip()
    if raw == "" or raw == "None":
        return None
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return None


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _normalized_title(raw_title: str, *, min_compact_len: int = 4) -> str:
    """Normalize a title for comparison: NFKC, lower, tokens."""
    title = unicodedata.normalize("NFKC", str(raw_title or ""))
    tokens = re.findall(r"[a-z0-9]+|[一-鿿]+", title.lower())
    normalized = " ".join(tokens).strip()
    compact = normalized.replace(" ", "")
    if len(compact) < min_compact_len:
        return ""
    return normalized


def _hash_id(prefix: str, *parts: str) -> str:
    """Deterministic short id: ``prefix_<sha1[:12]>``."""
    digest = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def create_event_store_schema(conn: sqlite3.Connection) -> None:
    """Create (if not exists) all MEM-002 tables and indexes."""
    conn.executescript(
        """
        create table if not exists news_items (
            id text primary key,
            canonical_url text not null,
            title text not null default '',
            title_norm text not null default '',
            source_id text not null default '',
            published_at text not null default '',
            crawled_at text not null default '',
            first_seen_at text not null default '',
            last_seen_at text not null default '',
            content_hash text not null default '',
            simhash text not null default '',
            raw_json text not null
        );

        create unique index if not exists idx_news_items_canonical_url
            on news_items (canonical_url);

        create index if not exists idx_news_items_title_norm
            on news_items (title_norm);

        create index if not exists idx_news_items_source_id
            on news_items (source_id);

        create index if not exists idx_news_items_published_at
            on news_items (published_at);

        create table if not exists games (
            id text primary key,
            canonical_title text not null,
            aliases text not null default '[]',
            platforms text not null default '[]',
            steam_app_id text,
            igdb_id text
        );

        create unique index if not exists idx_games_canonical_title
            on games (canonical_title);

        create table if not exists news_game_links (
            news_item_id text not null,
            game_id text not null,
            match_method text not null default 'keyword_match',
            confidence real not null default 0.0,
            primary key (news_item_id, game_id),
            foreign key (news_item_id) references news_items (id),
            foreign key (game_id) references games (id)
        );

        create index if not exists idx_news_game_links_game_id
            on news_game_links (game_id);

        create table if not exists events (
            id text primary key,
            event_title text not null default '',
            event_type text not null default 'other',
            game_id text not null default '',
            started_at text not null default '',
            ended_at text not null default '',
            parent_event_id text,
            foreign key (game_id) references games (id)
        );

        create index if not exists idx_events_game_id
            on events (game_id);

        create index if not exists idx_events_event_type
            on events (event_type);

        create index if not exists idx_events_started_at
            on events (started_at);

        create table if not exists event_news_links (
            event_id text not null,
            news_item_id text not null,
            role text not null default 'duplicate_report',
            confidence real not null default 0.0,
            primary key (event_id, news_item_id),
            foreign key (event_id) references events (id),
            foreign key (news_item_id) references news_items (id)
        );

        create index if not exists idx_event_news_links_news_item_id
            on event_news_links (news_item_id);

        create table if not exists decision_traces (
            id text primary key,
            run_id text not null,
            stage text not null default '',
            decision_type text not null default '',
            input_artifact_refs text not null default '[]',
            output_decision text not null default '{}',
            model_used text not null default '',
            prompt_version text not null default '',
            created_at text not null default ''
        );

        create index if not exists idx_decision_traces_run_id
            on decision_traces (run_id);

        create index if not exists idx_decision_traces_stage
            on decision_traces (stage);

        create index if not exists idx_decision_traces_created_at
            on decision_traces (created_at);
        """
    )


# ---------------------------------------------------------------------------
# ingest_candidates_to_news_items
# ---------------------------------------------------------------------------

def _extract_candidate_hash(candidate: dict[str, Any]) -> str:
    """Compute a content hash for a candidate dict."""
    if candidate.get("content_hash"):
        return str(candidate["content_hash"])
    payload = _json_text({
        "title": _text(candidate.get("title")),
        "url": _canonical_url(str(candidate.get("url", ""))),
        "source_id": _text(candidate.get("source_id")),
    })
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _extract_simhash(candidate: dict[str, Any]) -> str:
    """Return an existing simhash or empty string."""
    return _text(candidate.get("simhash") or candidate.get("sim_hash"))


def _best_timestamp(candidate: dict[str, Any], *keys: str) -> str:
    """Return the first non-empty timestamp from *keys* or ''."""
    for key in keys:
        val = _text(candidate.get(key))
        if val:
            return val
    return ""


def ingest_candidates_to_news_items(
    conn: sqlite3.Connection,
    candidates: Iterable[dict[str, Any]],
    run_id: str,
) -> int:
    """Upsert candidates into ``news_items``.

    Each candidate is keyed by its ``canonical_url``.  When the URL is new a
    row is inserted with ``first_seen_at`` set to the candidate timestamp
    (falling back to now).  On conflict the existing rowʼs ``first_seen_at``
    is preserved and ``last_seen_at`` is bumped.

    Returns the number of rows inserted or updated.
    """
    create_event_store_schema(conn)
    count = 0
    now_iso = _iso_now()

    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue

        canon_url = _canonical_url(str(candidate.get("url", "")))
        if not canon_url:
            continue

        title = _text(candidate.get("title"))
        title_norm = _normalized_title(title)
        source_id = _text(candidate.get("source_id"))
        published_at = _best_timestamp(candidate, "published_at", "observed_at")
        crawled_at = _best_timestamp(
            candidate, "crawled_at", "observed_at", "discovered_at", "fetched_at"
        ) or now_iso
        content_hash = _extract_candidate_hash(candidate)
        simhash = _extract_simhash(candidate)

        news_id = _hash_id("ni", canon_url)

        # Check for existing row to preserve first_seen_at.
        existing = conn.execute(
            "select first_seen_at from news_items where id = ?", (news_id,)
        ).fetchone()

        if existing and existing[0]:
            first_seen_at = existing[0]
            last_seen_at = now_iso
        else:
            first_seen_at = published_at or crawled_at or now_iso
            last_seen_at = now_iso

        conn.execute(
            """
            insert or replace into news_items (
                id, canonical_url, title, title_norm, source_id,
                published_at, crawled_at, first_seen_at, last_seen_at,
                content_hash, simhash, raw_json
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                news_id,
                canon_url,
                title,
                title_norm,
                source_id,
                published_at,
                crawled_at,
                first_seen_at,
                last_seen_at,
                content_hash,
                simhash,
                _json_text(candidate),
            ),
        )
        count += 1

    return count


# ---------------------------------------------------------------------------
# ingest_stories_to_events
# ---------------------------------------------------------------------------

_EVENT_TYPE_MAP: dict[str, str] = {
    "confirmed_report": "announcement",
    "release_or_launch": "release",
    "patch_or_update": "update",
    "community_reaction": "controversy",
    "leak_or_rumor": "rumor",
    "price_or_market": "other",
    "review_or_score": "other",
    "development": "update",
    "general_news": "other",
}

_ROLE_MAP: dict[str, str] = {
    "initial_report": "primary_event",
    "new_detail": "new_detail",
    "official_confirmation": "official_confirmation",
    "reaction": "reaction",
    "correction": "new_detail",
    "late_repost": "late_repost",
    "duplicate_report": "duplicate_report",
}


def _classify_event_type_from_story(story: dict[str, Any]) -> str:
    """Map a story/candidate event_type string to the canonical enum."""
    raw = _text(story.get("event_type") or story.get("candidate_type"))
    return _EVENT_TYPE_MAP.get(raw, "other")


def _classify_role(story: dict[str, Any]) -> str:
    """Derive the event-news link role from a story."""
    raw = _text(story.get("event_label") or story.get("memory_status"))
    return _ROLE_MAP.get(raw, "duplicate_report")


def ingest_stories_to_events(
    conn: sqlite3.Connection,
    stories: Iterable[dict[str, Any]],
    run_id: str,
) -> dict[str, int]:
    """Upsert stories as events and link their backing news items.

    Each story becomes an ``events`` row.  If the story carries
    ``source_urls``, matching ``news_items`` are linked via
    ``event_news_links``.  If ``game_title`` / ``entity_signatures`` is
    present, the event is linked to a game row (created on demand).

    Returns counts keyed by ``events``, ``event_news_links``,
    ``games_created``, ``news_game_links``.
    """
    create_event_store_schema(conn)
    counts: dict[str, int] = {
        "events": 0,
        "event_news_links": 0,
        "games_created": 0,
        "news_game_links": 0,
    }

    for story in stories:
        if not isinstance(story, dict):
            continue

        story_id = _text(story.get("id") or story.get("story_id"))
        event_title = _text(story.get("title") or story.get("canonical_title"))
        if not event_title:
            continue

        event_type = _classify_event_type_from_story(story)

        # Resolve / create game row.
        game_id = ""
        game_title = _text(
            story.get("game_title")
            or story.get("canonical_title")
        )
        entity_sigs = story.get("entity_signatures", [])
        if isinstance(entity_sigs, list) and entity_sigs:
            game_title = game_title or _text(entity_sigs[0])
        if game_title:
            game_id = _ensure_game(conn, game_title)
            if game_id:
                counts["games_created"] += 1

        # Determine time range.
        started_at = _best_timestamp(story, "started_at", "observed_at", "published_at")
        ended_at = _best_timestamp(story, "ended_at", "last_updated_at", "observed_at")

        parent_event_id = _text(story.get("parent_event_id")) or None

        event_id = _hash_id("ev", event_title, event_type, game_id)

        conn.execute(
            """
            insert or replace into events (
                id, event_title, event_type, game_id,
                started_at, ended_at, parent_event_id
            ) values (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                event_title,
                event_type,
                game_id,
                started_at,
                ended_at,
                parent_event_id,
            ),
        )
        counts["events"] += 1

        # Link source URLs to news_items.
        source_urls: list[str] = []
        raw_urls = story.get("source_urls", [])
        if isinstance(raw_urls, list):
            source_urls = [str(u) for u in raw_urls if u]
        # Also check candidate-level URLs.
        candidate_url = str(story.get("url") or story.get("candidate_url") or "")
        if candidate_url and candidate_url not in source_urls:
            source_urls.append(candidate_url)

        role = _classify_role(story)
        confidence = _number(story.get("confidence") or story.get("story_score")) / 100.0

        for url in source_urls:
            canon = _canonical_url(url)
            if not canon:
                continue
            ni_id = _hash_id("ni", canon)
            # Only link if the news_item exists.
            exists = conn.execute(
                "select 1 from news_items where id = ?", (ni_id,)
            ).fetchone()
            if exists:
                conn.execute(
                    """
                    insert or replace into event_news_links (
                        event_id, news_item_id, role, confidence
                    ) values (?, ?, ?, ?)
                    """,
                    (event_id, ni_id, role, confidence),
                )
                counts["event_news_links"] += 1

            # Also link news_item to game.
            if game_id and exists:
                conn.execute(
                    """
                    insert or replace into news_game_links (
                        news_item_id, game_id, match_method, confidence
                    ) values (?, ?, ?, ?)
                    """,
                    (ni_id, game_id, "keyword_match", confidence),
                )
                counts["news_game_links"] += 1

    return counts


# ---------------------------------------------------------------------------
# Game entity helpers
# ---------------------------------------------------------------------------

def _ensure_game(
    conn: sqlite3.Connection,
    game_title: str,
    *,
    aliases: list[str] | None = None,
    platforms: list[str] | None = None,
    steam_app_id: str | None = None,
    igdb_id: str | None = None,
) -> str:
    """Find or create a game row; return its ``id``."""
    canonical_title = _text(game_title).strip().lower()
    if not canonical_title:
        return ""

    game_id = _hash_id("g", canonical_title)
    existing = conn.execute(
        "select id from games where id = ?", (game_id,)
    ).fetchone()
    if existing:
        return game_id

    conn.execute(
        """
        insert or replace into games (
            id, canonical_title, aliases, platforms, steam_app_id, igdb_id
        ) values (?, ?, ?, ?, ?, ?)
        """,
        (
            game_id,
            canonical_title,
            _json_text(aliases or []),
            _json_text(platforms or []),
            steam_app_id or None,
            igdb_id or None,
        ),
    )
    return game_id


# ---------------------------------------------------------------------------
# link_news_to_game
# ---------------------------------------------------------------------------

def link_news_to_game(
    conn: sqlite3.Connection,
    news_item_id: str,
    game_title: str,
    match_method: str,
    *,
    confidence: float = 1.0,
) -> dict[str, Any]:
    """Link a single news item to a game entity.

    Creates the game row on demand via ``_ensure_game``, then inserts (or
    replaces) the ``news_game_links`` row.

    Returns a summary dict with the ids and match info.
    """
    create_event_store_schema(conn)

    game_id = _ensure_game(conn, game_title)
    if not game_id:
        return {
            "news_item_id": news_item_id,
            "game_id": "",
            "match_method": match_method,
            "confidence": confidence,
            "error": "empty_game_title",
        }

    conn.execute(
        """
        insert or replace into news_game_links (
            news_item_id, game_id, match_method, confidence
        ) values (?, ?, ?, ?)
        """,
        (news_item_id, game_id, match_method, confidence),
    )
    return {
        "news_item_id": news_item_id,
        "game_id": game_id,
        "match_method": match_method,
        "confidence": confidence,
    }


# ---------------------------------------------------------------------------
# query_event_timeline
# ---------------------------------------------------------------------------

def query_event_timeline(
    conn: sqlite3.Connection,
    game_id: str,
    time_window_days: int = 90,
) -> list[dict[str, Any]]:
    """Return events for *game_id* within *time_window_days* with linked news.

    Each returned dict represents one event and includes:
    - Event metadata (id, title, type, timestamps)
    - Nested ``news_items`` list with title, url, source_id, published_at
    """
    create_event_store_schema(conn)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=time_window_days)).isoformat()

    events_rows = conn.execute(
        """
        select id, event_title, event_type, game_id, started_at, ended_at, parent_event_id
        from events
        where game_id = ? and (started_at >= ? or started_at = '')
        order by started_at desc
        """,
        (game_id, cutoff),
    ).fetchall()

    result: list[dict[str, Any]] = []
    for row in events_rows:
        event_id, event_title, event_type, _gid, started_at, ended_at, parent_event_id = row

        # Fetch linked news items.
        news_rows = conn.execute(
            """
            select ni.id, ni.canonical_url, ni.title, ni.source_id, ni.published_at,
                   enl.role, enl.confidence
            from event_news_links enl
            join news_items ni on ni.id = enl.news_item_id
            where enl.event_id = ?
            order by ni.published_at asc
            """,
            (event_id,),
        ).fetchall()

        news_items: list[dict[str, Any]] = []
        for nr in news_rows:
            news_items.append({
                "news_item_id": nr[0],
                "canonical_url": nr[1],
                "title": nr[2],
                "source_id": nr[3],
                "published_at": nr[4],
                "role": nr[5],
                "confidence": nr[6],
            })

        result.append({
            "event_id": event_id,
            "event_title": event_title,
            "event_type": event_type,
            "game_id": _gid,
            "started_at": started_at,
            "ended_at": ended_at,
            "parent_event_id": parent_event_id,
            "news_items": news_items,
        })

    return result


# ---------------------------------------------------------------------------
# Decision trace recording
# ---------------------------------------------------------------------------

def record_decision_trace(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    stage: str,
    decision_type: str,
    input_artifact_refs: Sequence[str] = (),
    output_decision: dict[str, Any] | None = None,
    model_used: str = "",
    prompt_version: str = "",
) -> str:
    """Record a model decision trace for audit/debug.

    Returns the generated trace id.
    """
    create_event_store_schema(conn)
    now = _iso_now()
    trace_id = _hash_id("dt", run_id, stage, decision_type, now)
    conn.execute(
        """
        insert or replace into decision_traces (
            id, run_id, stage, decision_type, input_artifact_refs,
            output_decision, model_used, prompt_version, created_at
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            trace_id,
            run_id,
            stage,
            decision_type,
            _json_text(list(input_artifact_refs)),
            _json_text(output_decision or {}),
            _text(model_used),
            _text(prompt_version),
            now,
        ),
    )
    return trace_id


# ---------------------------------------------------------------------------
# Convenience: open + schema + close
# ---------------------------------------------------------------------------

def open_event_store(db_path: str | bytes) -> sqlite3.Connection:
    """Open (or create) an event-store database and ensure the schema exists."""
    conn = sqlite3.connect(str(db_path))
    create_event_store_schema(conn)
    return conn
