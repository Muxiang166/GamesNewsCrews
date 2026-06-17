"""Deterministic search intelligence for social-platform querying.

This module provides three core capabilities without LLM calls:

- SRC-001 Query Compression: extract key entities from candidate titles/snippets
  and compress them into short social-platform search queries.
- SRC-002 Result Relevance Classification: classify a search result against its
  originating candidate to decide whether it is same-event, same-game, noise, etc.
- SRC-004 Fallback Search: build a safe fallback query from the raw candidate
  title and known entities when advanced query methods fail or produce nothing.

All functions are deterministic and auditable. No LLM is ever invoked.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Shared entity detection helpers
# ---------------------------------------------------------------------------

# Game names in Chinese angle brackets: 《塞尔达传说》
_GAME_BOOKMARK_RE = re.compile(r"《([^》]+)》")

# Known platform keywords (lowercase for matching).
_PLATFORM_KEYWORDS: tuple[str, ...] = (
    "ps5",
    "ps6",
    "playstation",
    "xbox series x",
    "xbox series s",
    "xbox one",
    "xbox",
    "nintendo switch 2",
    "nintendo switch",
    "switch 2",
    "switch",
    "steam deck",
    "steam",
    "pc",
    "mobile",
    "ios",
    "android",
    "epic games store",
    "epic",
    "gog",
)

# Known event / showcase keywords (lowercase).
_EVENT_KEYWORDS: tuple[str, ...] = (
    "summer game fest",
    "xbox games showcase",
    "state of play",
    "nintendo direct",
    "gamescom",
    "tokyo game show",
    "the game awards",
    "showcase",
    "direct",
    "fest",
    "游戏节",
    "游戏展",
    "发布会",
    "直面会",
    "展示会",
)

# Capitalisation map: lowercase key -> preferred display form.
_PLATFORM_DISPLAY: dict[str, str] = {
    "ps5": "PS5",
    "ps6": "PS6",
    "playstation": "PlayStation",
    "xbox series x": "Xbox Series X",
    "xbox series s": "Xbox Series S",
    "xbox one": "Xbox One",
    "xbox": "Xbox",
    "nintendo switch 2": "Nintendo Switch 2",
    "nintendo switch": "Nintendo Switch",
    "switch 2": "Switch 2",
    "switch": "Switch",
    "steam deck": "Steam Deck",
    "steam": "Steam",
    "pc": "PC",
    "mobile": "Mobile",
    "ios": "iOS",
    "android": "Android",
    "epic games store": "Epic Games Store",
    "epic": "Epic",
    "gog": "GOG",
}

_EVENT_DISPLAY: dict[str, str] = {
    "summer game fest": "Summer Game Fest",
    "xbox games showcase": "Xbox Games Showcase",
    "state of play": "State of Play",
    "nintendo direct": "Nintendo Direct",
    "gamescom": "gamescom",
    "tokyo game show": "Tokyo Game Show",
    "the game awards": "The Game Awards",
}

# Clickbait indicator patterns.
_CLICKBAIT_PATTERNS: tuple[str, ...] = (
    r"你不会相信",
    r"震惊",
    r"惊人",
    r"独家",
    r"不看后悔",
    r"居然",
    r"网传",
    r"曝光.*黑幕",
    r"you won'?t believe",
    r"shocking",
    r"insane",
    r"mind.?blowing",
    r"jaw.?dropping",
    r"gone wrong",
    r"exposed",
)

_MIN_QUERY_LENGTH = 4  # characters – below this we fall back to raw title.

# ---------------------------------------------------------------------------
# Entity extraction
# ---------------------------------------------------------------------------

def _extract_game_names(text: str) -> list[str]:
    """Return game names found inside 《...》 bookmarks, deduplicated in order."""
    seen: set[str] = set()
    result: list[str] = []
    for match in _GAME_BOOKMARK_RE.finditer(text):
        name = match.group(1).strip()
        if name and name not in seen:
            seen.add(name)
            result.append(name)
    return result


def _extract_platforms(text: str) -> list[str]:
    """Return platform display names mentioned in *text*, longest-match first."""
    lowered = text.lower()
    found: list[tuple[int, str]] = []
    for key in sorted(_PLATFORM_KEYWORDS, key=len, reverse=True):
        pos = lowered.find(key)
        if pos >= 0:
            found.append((pos, _PLATFORM_DISPLAY.get(key, key)))
    found.sort(key=lambda pair: pair[0])
    seen: set[str] = set()
    result: list[str] = []
    for _pos, display in found:
        if display.lower() not in seen:
            seen.add(display.lower())
            result.append(display)
    return result


def _extract_events(text: str) -> list[str]:
    """Return event display names mentioned in *text*, longest-match first."""
    lowered = text.lower()
    found: list[tuple[int, str]] = []
    for key in sorted(_EVENT_KEYWORDS, key=len, reverse=True):
        pos = lowered.find(key)
        if pos >= 0:
            display = _EVENT_DISPLAY.get(key, key.title())
            found.append((pos, display))
    found.sort(key=lambda pair: pair[0])
    seen: set[str] = set()
    result: list[str] = []
    for _pos, display in found:
        if display.lower() not in seen:
            seen.add(display.lower())
            result.append(display)
    return result


def _extract_entities(text: str) -> dict[str, list[str]]:
    """Return {games, platforms, events} extracted from *text*."""
    return {
        "games": _extract_game_names(text),
        "platforms": _extract_platforms(text),
        "events": _extract_events(text),
    }


def _tokenize(text: str) -> set[str]:
    """Return a set of meaningful lowercase tokens from *text*."""
    # Remove URLs, then split on non-alphanumeric / non-CJK boundaries.
    cleaned = re.sub(r"https?://\S+", " ", text)
    tokens: set[str] = set()
    # Keep CJK characters as single-character tokens and alphanumeric runs.
    for token in re.findall(r"[\w一-鿿]+", cleaned, flags=re.UNICODE):
        lower = token.lower().strip()
        if len(lower) >= 2 or (len(lower) == 1 and "一" <= lower <= "鿿"):
            tokens.add(lower)
    return tokens


def _token_overlap_ratio(set_a: set[str], set_b: set[str]) -> float:
    """Jaccard-like overlap of two token sets."""
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


# ---------------------------------------------------------------------------
# SRC-001: Query Compression
# ---------------------------------------------------------------------------

def compress_to_social_queries(
    title: str,
    snippet: str = "",
    *,
    max_queries: int = 3,
) -> list[str]:
    """Compress a candidate title+snippet into short social-platform search queries.

    Rules (deterministic, no LLM):
    1. Extract game names in 《》, platforms, and event names from the combined text.
    2. Build queries from the most specific entity combinations:
       - game + event  (if both present)
       - game + platform
       - game alone
       - platform + event
       - event alone
    3. Never invent entities not present in the source text.
    4. Fall back to the original title (trimmed) if the text is too short or
       no entities are found.

    Returns up to *max_queries* distinct queries, each 96 chars or shorter.
    """
    combined = f"{title} {snippet}".strip()
    if len(combined) < _MIN_QUERY_LENGTH:
        return [_truncate_query(title.strip())]

    entities = _extract_entities(combined)
    games = entities["games"]
    platforms = entities["platforms"]
    events = entities["events"]

    queries: list[str] = []

    # Priority 1: game + event
    if games and events:
        for game in games:
            for event in events:
                candidate = f"《{game}》 {event}"
                if candidate not in queries:
                    queries.append(candidate)

    # Priority 2: game + platform
    if games and platforms:
        for game in games:
            for platform in platforms:
                candidate = f"《{game}》 {platform}"
                if candidate not in queries:
                    queries.append(candidate)

    # Priority 3: game alone
    if games:
        for game in games:
            candidate = f"《{game}》"
            if candidate not in queries:
                queries.append(candidate)

    # Priority 4: platform + event
    if platforms and events:
        for platform in platforms:
            for event in events:
                candidate = f"{platform} {event}"
                if candidate not in queries:
                    queries.append(candidate)

    # Priority 5: event alone
    if events:
        for event in events:
            if event not in queries:
                queries.append(event)

    # Priority 6: platform alone
    if platforms:
        for platform in platforms:
            if platform not in queries:
                queries.append(platform)

    # Truncate and deduplicate.
    final: list[str] = []
    for q in queries:
        short = _truncate_query(q)
        if short and short not in final:
            final.append(short)

    if not final:
        # Fallback: return the original title as the only query.
        fallback = _truncate_query(title.strip())
        return [fallback] if fallback else [title.strip()[:96]]

    return final[: max(max_queries, 1)]


def _truncate_query(text: str, *, max_length: int = 96) -> str:
    """Trim text to *max_length* chars, keeping whole words where possible."""
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= max_length:
        return compact
    truncated = compact[:max_length].rsplit(" ", 1)[0].strip()
    return truncated or compact[:max_length].strip()


# ---------------------------------------------------------------------------
# SRC-002: Result Relevance Classification
# ---------------------------------------------------------------------------

_RelevanceLabel = str  # one of the six labels below

RELEVANCE_SAME_EVENT_SAME_GAME: _RelevanceLabel = "same_event_same_game"
RELEVANCE_SAME_GAME_DIFFERENT_EVENT: _RelevanceLabel = "same_game_different_event"
RELEVANCE_OLD_NEWS: _RelevanceLabel = "old_news"
RELEVANCE_CLICKBAIT_TITLE: _RelevanceLabel = "clickbait_title"
RELEVANCE_REPOST: _RelevanceLabel = "repost"
RELEVANCE_UNRELATED: _RelevanceLabel = "unrelated"

# Token overlap thresholds (empirically chosen).
_SAME_GAME_OVERLAP = 0.22
_REPOST_OVERLAP = 0.55


@dataclass(frozen=True)
class SearchRelevancePolicy:
    """Tunable thresholds for deterministic search-result relevance checks."""

    same_game_overlap: float = _SAME_GAME_OVERLAP
    repost_overlap: float = _REPOST_OVERLAP
    lookback_hours: float = 48


def _event_overlap(
    candidate_events: list[str],
    result_events: list[str],
) -> bool:
    """True when any candidate event appears in result events (case-insensitive)."""
    if not candidate_events or not result_events:
        return False
    cand_set = {e.lower() for e in candidate_events}
    result_set = {e.lower() for e in result_events}
    return bool(cand_set & result_set)


def _game_overlap(
    candidate_games: list[str],
    result_games: list[str],
) -> bool:
    """True when any candidate game name appears in result game names."""
    if not candidate_games or not result_games:
        return False
    cand_set = {g.lower() for g in candidate_games}
    result_set = {g.lower() for g in result_games}
    return bool(cand_set & result_set)


def _is_clickbait(text: str) -> bool:
    """True if *text* matches known clickbait indicator patterns."""
    for pattern in _CLICKBAIT_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return True
    return False


def _hours_ago(reference_dt: datetime | None, lookback_hours: float) -> bool:
    """True when *reference_dt* is older than *lookback_hours* from now."""
    if reference_dt is None:
        return False
    now = datetime.now(timezone.utc)
    if reference_dt.tzinfo is None:
        reference_dt = reference_dt.replace(tzinfo=timezone.utc)
    delta = now - reference_dt
    return delta.total_seconds() > lookback_hours * 3600


def classify_search_result(
    result_title: str,
    result_snippet: str,
    original_candidate: dict[str, Any],
    *,
    lookback_hours: float | None = None,
    result_published_at: object | None = None,
    result_metadata: dict[str, Any] | None = None,
    policy: SearchRelevancePolicy | None = None,
) -> dict[str, Any]:
    """Classify a search result against its originating candidate.

    Categories (in priority order, highest-first):
    - **same_event_same_game**: result references the same game AND the same event.
    - **old_news**: result published_at is older than *lookback_hours*.
    - **repost**: very high token overlap with the candidate title+snippet.
    - **same_game_different_event**: same game but a different (or no) event.
    - **clickbait_title**: result title matches clickbait indicator patterns.
    - **unrelated**: fails all of the above.

    Returns a dict with:
        label: one of the six relevance label strings
        reasons: list of human-readable reasons for the classification
        token_overlap: float 0.0-1.0
        candidate_entities: {games, platforms, events}
        result_entities: {games, platforms, events}
    """
    relevance_policy = policy or SearchRelevancePolicy()
    resolved_lookback_hours = (
        relevance_policy.lookback_hours if lookback_hours is None else lookback_hours
    )
    candidate_title = str(original_candidate.get("title") or "")
    candidate_snippet = str(original_candidate.get("snippet") or "")
    candidate_text = f"{candidate_title} {candidate_snippet}"

    result_text = f"{result_title} {result_snippet}"

    # Extract entities.
    cand_entities = _extract_entities(candidate_text)
    res_entities = _extract_entities(result_text)

    # Token overlap.
    cand_tokens = _tokenize(candidate_text)
    res_tokens = _tokenize(result_text)
    overlap = _token_overlap_ratio(cand_tokens, res_tokens)

    # --- gather signals ---
    # Time check.
    published_at = original_candidate.get("published_at")
    if isinstance(published_at, str):
        try:
            published_at = datetime.fromisoformat(published_at)
        except (ValueError, TypeError):
            published_at = None
    metadata = result_metadata if isinstance(result_metadata, dict) else {}
    result_published = (
        result_published_at
        or metadata.get("result_published_at")
        or metadata.get("published_at")
        or metadata.get("observed_at")
        or original_candidate.get("result_published_at")
    )
    if isinstance(result_published, str):
        try:
            result_published = datetime.fromisoformat(result_published)
        except (ValueError, TypeError):
            result_published = None
    effective_time = result_published or published_at
    is_old = _hours_ago(effective_time, resolved_lookback_hours)

    # Entity overlap signals.
    same_game = _game_overlap(cand_entities["games"], res_entities["games"])
    same_event = _event_overlap(cand_entities["events"], res_entities["events"])
    is_repost = overlap >= relevance_policy.repost_overlap
    is_clickbait = _is_clickbait(result_title)
    token_suggests_same_game = bool(
        not same_game
        and overlap >= relevance_policy.same_game_overlap
        and overlap < relevance_policy.repost_overlap
    )

    # --- classify in strict priority order (highest-first) ---
    # Priority order:
    #   1. same_event_same_game (game + event entity match)
    #   2. old_news            (temporal: too stale to be useful)
    #   3. repost              (near-identical text)
    #   4. same_game_different_event (same game, different context)
    #   5. clickbait_title
    #   6. unrelated
    reasons: list[str] = []
    label: _RelevanceLabel

    if same_game and same_event:
        label = RELEVANCE_SAME_EVENT_SAME_GAME
        reasons.append("same game and same event referenced")
    elif is_old:
        label = RELEVANCE_OLD_NEWS
        reasons.append(f"published more than {resolved_lookback_hours:.0f}h ago")
    elif is_repost:
        label = RELEVANCE_REPOST
        reasons.append(
            f"token overlap {overlap:.2f} >= {relevance_policy.repost_overlap} indicates repost"
        )
    elif same_game or token_suggests_same_game:
        # Token-based detection only fires when overlap is in the
        # [SAME_GAME_OVERLAP, REPOST_OVERLAP) range, i.e. below repost
        # threshold.  Above that, repost already captured it.
        label = RELEVANCE_SAME_GAME_DIFFERENT_EVENT
        if same_game:
            reasons.append("same game, different event")
        else:
            reasons.append(
                f"token overlap {overlap:.2f} >= {relevance_policy.same_game_overlap} suggests same game"
            )
    elif is_clickbait:
        label = RELEVANCE_CLICKBAIT_TITLE
        reasons.append("clickbait title pattern detected")
    else:
        label = RELEVANCE_UNRELATED
        reasons.append("no relevance signal detected")

    return {
        "label": label,
        "reasons": reasons,
        "token_overlap": round(overlap, 4),
        "candidate_entities": cand_entities,
        "result_entities": res_entities,
    }


# ---------------------------------------------------------------------------
# SRC-004: Fallback Search
# ---------------------------------------------------------------------------

def build_fallback_query(
    candidate_title: str,
    candidate_entities: dict[str, list[str]] | None = None,
) -> str:
    """Build a safe fallback query preserving original keywords.

    When advanced query methods (entity compression, LLM rewriting, etc.) fail or
    produce unusable output, this function constructs a deterministic fallback:

    1. If *candidate_entities* provides game names, use the first game name
       wrapped in 《》 followed by the first platform or event.
    2. Otherwise, sanitise the raw *candidate_title*: strip URLs, brackets,
       and excessive whitespace, then truncate to 96 characters.

    The result is always non-empty and safe for direct use as a search query.
    """
    entities = candidate_entities or {}
    games: list[str] = list(entities.get("games") or [])
    platforms: list[str] = list(entities.get("platforms") or [])
    events: list[str] = list(entities.get("events") or [])

    if games:
        parts: list[str] = [f"《{games[0]}》"]
        if platforms:
            parts.append(platforms[0])
        elif events:
            parts.append(events[0])
        return " ".join(parts).strip()

    # No entities available – sanitise the raw title.
    return _truncate_query(candidate_title) or candidate_title.strip()[:96]
