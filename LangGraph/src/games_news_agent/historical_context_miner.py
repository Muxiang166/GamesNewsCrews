"""MEM-004: Mine historical context for stories from event and evidence stores.

v0 uses SQL query rules — no LLM calls. The module answers:
  - Has this game/studio/event-type been in the news before?
  - Are there "first since YEAR" patterns?
  - Can we generate a short historical-context sentence with citations?
"""

from __future__ import annotations

import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

ContextClass = Literal["confirmed_record", "record_candidate", "analogy"]


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------

def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def _extract_domain(url: str) -> str:
    m = re.search(r"://(?:www\.)?([^/]+)", (url or ""))
    return m.group(1).lower() if m else ""


def _extract_year(iso_string: str) -> int | None:
    """Extract a four-digit year from an ISO-8601 string."""
    m = re.match(r"(\d{4})", (iso_string or "").strip())
    return int(m.group(1)) if m else None


# ---------------------------------------------------------------------------
# Entity extraction (v0: keyword / game-name heuristics)
# ---------------------------------------------------------------------------

# A small curated list of game/studio/event-type keywords for v0 matching.
# In production this could come from a config file or a game DB.
_GAME_KEYWORDS: dict[str, list[str]] = {
    "nintendo": ["nintendo", "switch", "mario", "zelda", "pokémon", "splatoon", "animal crossing"],
    "playstation": ["playstation", "ps5", "ps4", "sony", "naughty dog", "insomniac", "santa monica"],
    "xbox": ["xbox", "microsoft", "bethesda", "halo", "forza", "starfield"],
    "pc": ["steam", "epic games", "gog", "valve", "pc gaming"],
    "mobile": ["ios", "android", "mobile game", "gacha", "honkai", "genshin"],
    "esports": ["esports", "league of legends", "lol esports", "dota 2", "valorant champions", "cs:go"],
}


def _guess_game_entities(text: str) -> list[str]:
    """Return a list of known game entity tags found in text."""
    text_lower = _clean_text(text)
    matched: list[str] = []
    for category, keywords in _GAME_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                matched.append(kw)
    return list(dict.fromkeys(matched))  # deduplicate preserving order


def _event_type_keywords() -> dict[str, list[str]]:
    return {
        "launch": ["launch", "release date", "released", "now available", "out now"],
        "update": ["update", "patch", "hotfix", "season", "dlc", "expansion"],
        "delay": ["delay", "delayed", "postponed", "pushed back"],
        "shutdown": ["shutdown", "sunset", "end of service", "closing", "discontinued"],
        "acquisition": ["acquisition", "acquired", "merged", "bought"],
        "controversy": ["controversy", "backlash", "outrage", "criticism", "boycott"],
        "award": ["award", "game of the year", "goty", "nomination", "won"],
        "record": ["record", "milestone", "broke", "fastest", "highest", "best-selling"],
    }


def _classify_event_type(text: str) -> list[str]:
    """Return the likely event type(s) matching keywords in text."""
    text_lower = _clean_text(text)
    matched: list[str] = []
    for etype, keywords in _event_type_keywords().items():
        if any(kw in text_lower for kw in keywords):
            matched.append(etype)
    return matched if matched else ["general"]


# ---------------------------------------------------------------------------
# MEM-004: mine_historical_context
# ---------------------------------------------------------------------------

def mine_historical_context(
    story: dict[str, Any],
    event_store_db: str | Path,
    evidence_store_db: str | Path | None = None,
    *,
    lookback_years: int = 5,
    max_context_items: int = 8,
) -> dict[str, Any]:
    """Search related historical events for a story.

    Strategy (v0 SQL rules):
      1. Extract game entities from story title/summary.
      2. Classify the event type (launch, update, delay, etc.).
      3. Query the event store for prior candidates/stories matching the same
         game entities OR the same event type, within *lookback_years*.
      4. Detect "first since YEAR" gaps.
      5. Generate short context sentences with source citations (URL or event_id).

    Args:
        story: Dict with at least ``title``, optionally ``summary``, ``url``, ``source_id``.
        event_store_db: Path to the SQLite mirror DB.
        evidence_store_db: Optional path to evidence chunks DB (unused in v0 but
            kept for future integration).
        lookback_years: How far back to search for related events.
        max_context_items: Max number of context items to return.

    Returns:
        Dict with keys: ``story_title``, ``entities``, ``event_types``,
        ``related_events`` (list), ``first_since_patterns`` (list),
        ``context_sentences`` (list of {sentence, citation_url, citation_event_id}).
    """
    story_title = str(story.get("title", ""))
    story_summary = str(story.get("summary", ""))
    story_url = str(story.get("url", ""))
    combined_text = f"{story_title} {story_summary}"

    entities = _guess_game_entities(combined_text)
    event_types = _classify_event_type(combined_text)

    # Fallback: if no entities detected, use words from the title as search terms
    if not entities:
        title_words = [w for w in _clean_text(story_title).split() if len(w) > 3]
        entities = title_words[:5]

    # Determine the cutoff year
    current_year = datetime.now(timezone.utc).year
    min_year = current_year - lookback_years

    conn = sqlite3.connect(str(event_store_db))
    try:
        related_events = _query_related_events(
            conn, entities, event_types, min_year, max_items=max_context_items * 2
        )
    except sqlite3.OperationalError:
        related_events = []
    finally:
        conn.close()

    # Detect "first since YEAR" patterns
    first_since = _detect_first_since_patterns(
        story_title, related_events, current_year
    )

    # Generate context sentences
    context_sentences = _generate_context_sentences(
        story_title,
        story_url,
        entities,
        event_types,
        related_events,
        first_since,
    )

    # Limit context items
    if len(context_sentences) > max_context_items:
        context_sentences = context_sentences[:max_context_items]

    return {
        "story_title": story_title,
        "entities": entities,
        "event_types": event_types,
        "related_events": related_events[:max_context_items],
        "first_since_patterns": first_since,
        "context_sentences": context_sentences,
    }


def _query_related_events(
    conn: sqlite3.Connection,
    entities: list[str],
    event_types: list[str],
    min_year: int,
    max_items: int,
) -> list[dict[str, Any]]:
    """Query the event store for candidates matching game entities or event types.

    Uses ``published_at`` for year filtering and ``title`` for keyword matching.
    """
    if not entities and not event_types:
        return []

    # Build LIKE clauses
    entity_clauses: list[str] = []
    entity_params: list[str] = []
    for e in entities:
        entity_clauses.append("lower(title) like ?")
        entity_params.append(f"%{e.lower()}%")

    event_clauses: list[str] = []
    event_params: list[str] = []
    for et in event_types:
        keywords = _event_type_keywords().get(et, [et])
        for kw in keywords:
            event_clauses.append("lower(title) like ?")
            event_params.append(f"%{kw.lower()}%")

    where_clauses: list[str] = []
    params: list[Any] = []

    if entity_clauses:
        where_clauses.append(f"({' or '.join(entity_clauses)})")
        params.extend(entity_params)
    if event_clauses:
        where_clauses.append(f"({' or '.join(event_clauses)})")
        params.extend(event_params)

    if not where_clauses:
        return []

    where_sql = " or ".join(f"({c})" for c in where_clauses)
    sql = f"""
        select run_id, candidate_id, title, url, published_at, theme_section, raw_json
        from candidates
        where ({where_sql})
          and cast(substr(coalesce(published_at, ''), 1, 4) as integer) >= ?
        order by published_at desc
        limit ?
    """
    params.append(min_year)
    params.append(max_items)

    rows = conn.execute(sql, params).fetchall()
    return [
        {
            "run_id": row[0],
            "candidate_id": row[1],
            "title": row[2],
            "url": row[3],
            "published_at": row[4],
            "theme_section": row[5],
            "raw_json": row[6],
        }
        for row in rows
    ]


def _detect_first_since_patterns(
    story_title: str,
    related_events: list[dict[str, Any]],
    current_year: int,
) -> list[dict[str, Any]]:
    """Find "first since YEAR" patterns in related events.

    Detects gaps: if the most recent related event is from year X and
    X < current_year - 1, it is a "first since X" candidate.
    Also detects multi-year gaps in the event timeline.
    """
    patterns: list[dict[str, Any]] = []
    if not related_events:
        return patterns

    # Group events by year
    years: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for ev in related_events:
        year = _extract_year(ev.get("published_at", ""))
        if year:
            years[year].append(ev)

    if not years:
        return patterns

    sorted_years = sorted(years.keys(), reverse=True)
    most_recent_year = sorted_years[0]
    gap = current_year - most_recent_year

    if gap >= 2:
        patterns.append(
            {
                "pattern": "first_since_year",
                "year": most_recent_year,
                "gap_years": gap,
                "latest_event": years[most_recent_year][0],
                "sentence": f"This is the first such event since {most_recent_year} "
                f"({gap} years ago).",
            }
        )

    # Also detect internal gaps of 2+ years
    for i in range(len(sorted_years) - 1):
        year_a = sorted_years[i]
        year_b = sorted_years[i + 1]
        gap_between = year_a - year_b
        if gap_between >= 2:
            patterns.append(
                {
                    "pattern": "resumed_after_gap",
                    "year_before_gap": year_a,
                    "year_after_gap": year_b,
                    "gap_years": gap_between,
                    "sentence": f"After a {gap_between}-year gap since {year_a}, "
                    f"activity resumed in {year_b}.",
                }
            )

    return patterns


def _generate_context_sentences(
    story_title: str,
    story_url: str,
    entities: list[str],
    event_types: list[str],
    related_events: list[dict[str, Any]],
    first_since_patterns: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Generate context sentences with source citations."""
    sentences: list[dict[str, Any]] = []

    # Sentences from related events
    for ev in related_events[:5]:
        ev_title = ev.get("title", "")
        ev_url = ev.get("url", "")
        ev_date = ev.get("published_at", "")
        ev_year = _extract_year(ev_date)
        year_suffix = f" ({ev_year})" if ev_year else ""
        sentences.append(
            {
                "sentence": f"Related: {ev_title}{year_suffix}.",
                "citation_url": ev_url,
                "citation_event_id": ev.get("candidate_id", ""),
                "source": "event_store",
            }
        )

    # Sentences from "first since" patterns
    for pattern in first_since_patterns:
        citation = ""
        citation_event_id = ""
        if "latest_event" in pattern:
            citation = pattern["latest_event"].get("url", "")
            citation_event_id = pattern["latest_event"].get("candidate_id", "")
        sentences.append(
            {
                "sentence": pattern["sentence"],
                "citation_url": citation,
                "citation_event_id": citation_event_id,
                "source": "first_since_analysis",
            }
        )

    # Summary sentence about what we found
    entity_str = ", ".join(entities) if entities else "unknown entities"
    etype_str = ", ".join(event_types) if event_types else "general news"
    sentences.insert(
        0,
        {
            "sentence": f"Historical analysis for story about {entity_str} "
            f"(event type: {etype_str}). Found {len(related_events)} related "
            f"events, {len(first_since_patterns)} timeline patterns.",
            "citation_url": "",
            "citation_event_id": "",
            "source": "summary",
        },
    )

    return sentences


# ---------------------------------------------------------------------------
# MEM-004: classify_context
# ---------------------------------------------------------------------------

def classify_context(
    context: dict[str, Any],
) -> ContextClass:
    """Classify the reliability of historical context.

    Classification rules (v0):
      - ``confirmed_record``: >= 3 related events with URLs AND at least one
        first_since pattern with a citation.
      - ``record_candidate``: >= 1 related event with a URL but evidence is thin
        (fewer than 3 related events, or no first_since pattern).
      - ``analogy``: No related events with URLs — only narrative/pattern-based
        context that should be treated as an aid, not a fact.

    Args:
        context: The dict returned by ``mine_historical_context``.

    Returns:
        One of ``"confirmed_record"``, ``"record_candidate"``, ``"analogy"``.
    """
    related = context.get("related_events", [])
    first_since = context.get("first_since_patterns", [])
    sentences = context.get("context_sentences", [])

    # Count events with actual URLs
    events_with_url = sum(1 for ev in related if ev.get("url"))
    patterns_with_citation = sum(
        1 for p in first_since if p.get("latest_event", {}).get("url")
    )

    if events_with_url >= 3 and patterns_with_citation >= 1:
        return "confirmed_record"

    if events_with_url >= 1:
        return "record_candidate"

    # No events with URLs — only narrative/analogy
    return "analogy"


# ---------------------------------------------------------------------------
# MEM-004: validate_historical_context
# ---------------------------------------------------------------------------

def validate_historical_context(
    context: dict[str, Any],
) -> dict[str, Any]:
    """Validate that every context sentence has a source reference.

    Each sentence must have either a ``citation_url`` or a ``citation_event_id``
    (or both). Sentences without any citation are flagged.

    Returns:
        Dict with ``valid`` (bool), ``total_sentences``, ``valid_sentences``,
        ``invalid_sentences`` (list of sentences missing citations), and
        ``issues`` (list of human-readable issue descriptions).
    """
    sentences = context.get("context_sentences", [])
    total = len(sentences)
    valid_count = 0
    invalid_list: list[dict[str, Any]] = []
    issues: list[str] = []

    for i, sent in enumerate(sentences):
        has_url = bool((sent.get("citation_url") or "").strip())
        has_event_id = bool((sent.get("citation_event_id") or "").strip())
        has_citation = has_url or has_event_id

        if has_citation:
            valid_count += 1
        else:
            invalid_list.append(sent)
            issues.append(
                f"Sentence {i} missing citation: \"{sent.get('sentence', '')[:80]}...\""
            )

    # Also check: related_events should have URLs
    for i, ev in enumerate(context.get("related_events", [])):
        if not (ev.get("url") or "").strip():
            issues.append(
                f"Related event {i} \"{ev.get('title', '')[:60]}\" missing URL."
            )

    # Check: first_since patterns should reference a real event
    for i, pat in enumerate(context.get("first_since_patterns", [])):
        latest = pat.get("latest_event")
        if latest and not (latest.get("url") or latest.get("candidate_id")):
            issues.append(
                f"First-since pattern {i} references an event without URL or ID."
            )

    return {
        "valid": len(invalid_list) == 0,
        "total_sentences": total,
        "valid_sentences": valid_count,
        "invalid_sentences": invalid_list,
        "issues": issues,
    }
