"""Evidence retrieval with SQLite FTS5, BM25, and keyword fallback.

Pipeline:
  SQLiteEvidenceRetriever (FTS5, requires db_path)
  -> BM25EvidenceRetriever (in-memory BM25 scoring)
  -> keyword (token-overlap fallback)

Unified entry point::
    retrieve_evidence(claim_or_story, db_path=None, *, max_results=5, **filters)

Output schema: retrieved_evidence_packs.json (see :func:`retrieve_evidence`).
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "for",
    "from",
    "in",
    "is",
    "of",
    "on",
    "the",
    "to",
    "with",
}


def _tokens(text: str) -> set[str]:
    raw_tokens = re.findall(r"[a-z0-9]+|[一-鿿]{2,}", text.lower())
    return {token for token in raw_tokens if token not in STOPWORDS and len(token) > 1}


def _score_chunk(chunk: dict[str, Any], query_tokens: set[str]) -> int:
    haystack = " ".join(
        [
            str(chunk.get("title", "")),
            str(chunk.get("quote", "")),
            str(chunk.get("url", "")),
        ]
    ).lower()
    return sum(1 for token in query_tokens if token in haystack)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _extract_query_text(claim_or_story: dict[str, Any] | str) -> str:
    """Derive a searchable query from a claim dict, story dict, or raw string."""
    if isinstance(claim_or_story, str):
        return claim_or_story.strip()
    for key in ("text", "title", "summary"):
        value = claim_or_story.get(key, "")
        if value:
            return str(value).strip()
    return ""


def _passes_filters(
    chunk: dict[str, Any],
    *,
    source_ids: set[str] | None = None,
    theme_section: str | set[str] | None = None,
    time_window: tuple[str | datetime, str | datetime] | None = None,
    **_rest: Any,
) -> bool:
    if source_ids:
        chunk_src = str(chunk.get("source_id", ""))
        if chunk_src not in source_ids:
            return False
    if theme_section is not None:
        if isinstance(theme_section, str):
            wanted = {theme_section}
        else:
            wanted = set(theme_section)
        chunk_theme = str(chunk.get("theme_section", "") or "")
        if not chunk_theme or chunk_theme not in wanted:
            return False
    if time_window is not None:
        published = chunk.get("published_at")
        if published:
            try:
                # Handle both ISO string and datetime
                if isinstance(published, datetime):
                    ts = published
                elif isinstance(published, str):
                    ts = datetime.fromisoformat(published.replace("Z", "+00:00"))
                else:
                    ts = None
            except (ValueError, TypeError):
                ts = None
            if ts is not None:
                start_raw, end_raw = time_window
                start = _coerce_dt(start_raw)
                end = _coerce_dt(end_raw)
                if start is not None and ts < start:
                    return False
                if end is not None and ts > end:
                    return False
    return True


def _coerce_dt(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None
    return None


def _to_evidence_pack(chunk: dict[str, Any], relevance_score: float = 0.0) -> dict[str, Any]:
    """Normalise a chunk row / chunk dict into a standard evidence pack."""
    return {
        "chunk_id": str(chunk.get("chunk_id", "")),
        "url": str(chunk.get("url", "")),
        "source_id": str(chunk.get("source_id", "")),
        "title": str(chunk.get("title", "")),
        "published_at": chunk.get("published_at"),
        "quote": str(chunk.get("quote", "")),
        "credibility_hint": str(chunk.get("credibility_hint", "")),
        "relevance_score": round(float(relevance_score), 4),
    }


def _credibility_hint_from_json(raw_json: str | None) -> str:
    """Extract credibility_hint from a raw_json column value."""
    if not raw_json:
        return ""
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError:
        return ""
    if isinstance(data, dict):
        hint = data.get("credibility_hint", "")
        if hint:
            return str(hint)
        metadata = data.get("metadata")
        if isinstance(metadata, dict):
            candidate_type = metadata.get("candidate_type", "")
            if candidate_type:
                return str(candidate_type)
    return ""


# ---------------------------------------------------------------------------
# Keyword fallback (kept for backward-compat and final fallback)
# ---------------------------------------------------------------------------


def _retrieve_evidence_keyword(
    chunks: list[dict[str, Any]],
    query: str,
    *,
    top_k: int = 5,
    source_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Original keyword retrieval — kept as internal fallback."""
    query_tokens = _tokens(query)
    scored: list[dict[str, Any]] = []
    for chunk in chunks:
        if source_ids and str(chunk.get("source_id")) not in source_ids:
            continue
        score = _score_chunk(chunk, query_tokens)
        if score <= 0:
            continue
        enriched = dict(chunk)
        enriched["score"] = score
        scored.append(enriched)

    scored.sort(
        key=lambda item: (
            item.get("score", 0),
            item.get("published_at") or "",
        ),
        reverse=True,
    )
    return scored[: max(top_k, 0)]


# ---------------------------------------------------------------------------
# SQLiteEvidenceRetriever  (FTS5)
# ---------------------------------------------------------------------------


class SQLiteEvidenceRetriever:
    """Retrieve evidence chunks from a SQLite mirror DB using FTS5 full-text search.

    The mirror DB is expected to have an ``evidence_chunks`` table (created by
    :mod:`games_news_agent.persistence.sqlite_mirror`).  On first use the
    retriever builds an FTS5 virtual table ``evidence_chunks_fts`` that indexes
    the ``title`` and ``quote`` columns.

    Metadata filters (``source_ids``, ``theme_section``, ``time_window``) are
    applied after the FTS5 search by joining against ``candidates`` when needed.
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            self._ensure_fts()
        return self._conn

    # ------------------------------------------------------------------
    # FTS5 lifecycle
    # ------------------------------------------------------------------

    @staticmethod
    def _tokenize_for_fts(text: str) -> str:
        """Insert spaces around CJK characters so the unicode61 tokenizer
        treats each as a standalone token.

        Without this, FTS5 merges ``原神`` into a single token that can
        never match a single-character query.
        """
        result: list[str] = []
        for ch in text:
            if "一" <= ch <= "鿿" or "㐀" <= ch <= "䶿":
                result.append(" ")
                result.append(ch)
                result.append(" ")
            else:
                result.append(ch)
        return "".join(result)

    def _ensure_fts(self) -> None:
        conn = self._conn
        if conn is None:
            return
        exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='evidence_chunks_fts'"
        ).fetchone()
        if not exists:
            self._rebuild_fts()
        else:
            row_count = conn.execute(
                "SELECT count(*) FROM evidence_chunks_fts"
            ).fetchone()[0]
            base_count = conn.execute(
                "SELECT count(*) FROM evidence_chunks"
            ).fetchone()[0]
            if row_count == 0 and base_count > 0:
                self._rebuild_fts()

    def _rebuild_fts(self) -> None:
        conn = self._conn
        if conn is None:
            return
        conn.execute("DROP TABLE IF EXISTS evidence_chunks_fts")
        # Standalone FTS table (no content=) so we control tokenisation.
        conn.execute(
            """
            CREATE VIRTUAL TABLE evidence_chunks_fts USING fts5(
                title, quote
            )
            """
        )
        rows = conn.execute(
            "SELECT rowid, title, quote FROM evidence_chunks"
        ).fetchall()
        for row in rows:
            conn.execute(
                "INSERT INTO evidence_chunks_fts(rowid, title, quote) "
                "VALUES (?, ?, ?)",
                (
                    row["rowid"],
                    self._tokenize_for_fts(row["title"]),
                    self._tokenize_for_fts(row["quote"]),
                ),
            )
        conn.commit()

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def _fts_query(self, text: str) -> str | None:
        """Build a safe FTS5 MATCH expression from raw text.

        CJK characters are tokenised individually for compat with the
        default unicode61 tokenizer, which splits each CJK codepoint
        into a separate FTS token.
        """
        terms = _tokens(text)
        if not terms:
            return None
        escaped: list[str] = []
        for term in terms:
            # CJK-only term -> split per codepoint
            if re.fullmatch(r"[一-鿿㐀-䶿豈-﫿]+", term):
                for ch in term:
                    escaped.append(ch)
            else:
                escaped.append(term.replace('"', '""'))
        if not escaped:
            return None
        quoted = [f'"{e}"' for e in escaped]
        return " OR ".join(quoted)

    def _build_where_clauses(
        self,
        source_ids: set[str] | None = None,
        theme_section: str | set[str] | None = None,
        time_window: tuple[str | datetime, str | datetime] | None = None,
    ) -> tuple[str, list[Any]]:
        clauses: list[str] = []
        params: list[Any] = []

        if source_ids:
            placeholders = ", ".join("?" for _ in source_ids)
            clauses.append(f"e.source_id IN ({placeholders})")
            params.extend(source_ids)

        if theme_section is not None:
            if isinstance(theme_section, str):
                wanted = {theme_section}
            else:
                wanted = set(theme_section)
            placeholders = ", ".join("?" for _ in wanted)
            clauses.append(f"c.theme_section IN ({placeholders})")
            params.extend(wanted)

        if time_window is not None:
            start_raw, end_raw = time_window
            start = _coerce_dt(start_raw)
            end = _coerce_dt(end_raw)
            if start is not None:
                clauses.append("e.published_at >= ?")
                params.append(start.isoformat())
            if end is not None:
                clauses.append("e.published_at <= ?")
                params.append(end.isoformat())

        if clauses:
            return " AND " + " AND ".join(clauses), params
        return "", params

    def search(
        self,
        query: str,
        max_results: int = 5,
        **filters: Any,
    ) -> list[dict[str, Any]]:
        """Run an FTS5 full-text search with optional metadata filters.

        Parameters
        ----------
        query:
            Natural-language query text.
        max_results:
            Maximum number of evidence packs to return.
        **filters:
            ``source_ids``, ``theme_section``, ``time_window`` (see
            :func:`_passes_filters`).

        Returns
        -------
        list[dict]
            Evidence packs with keys ``chunk_id``, ``url``, ``source_id``,
            ``title``, ``published_at``, ``quote``, ``credibility_hint``,
            ``relevance_score``.
        """
        fts_expr = self._fts_query(query)
        if not fts_expr:
            return []

        source_ids = filters.pop("source_ids", None)
        if isinstance(source_ids, (list, tuple)):
            source_ids = set(source_ids)
        theme_section = filters.pop("theme_section", None)
        time_window = filters.pop("time_window", None)

        where_sql, where_params = self._build_where_clauses(
            source_ids=source_ids,
            theme_section=theme_section,
            time_window=time_window,
        )

        # Need LEFT JOIN with candidates for theme_section filter
        need_candidates_join = theme_section is not None

        if need_candidates_join:
            sql = f"""
                SELECT
                    e.chunk_id, e.url, e.source_id, e.title,
                    e.published_at, e.quote, e.raw_json,
                    c.theme_section,
                    fts.rank AS relevance_score
                FROM evidence_chunks_fts fts
                JOIN evidence_chunks e ON e.rowid = fts.rowid
                LEFT JOIN candidates c ON c.url = e.url AND c.run_id = e.run_id
                WHERE evidence_chunks_fts MATCH ?
                {where_sql}
                ORDER BY fts.rank
                LIMIT ?
            """
        else:
            sql = f"""
                SELECT
                    e.chunk_id, e.url, e.source_id, e.title,
                    e.published_at, e.quote, e.raw_json,
                    fts.rank AS relevance_score
                FROM evidence_chunks_fts fts
                JOIN evidence_chunks e ON e.rowid = fts.rowid
                WHERE evidence_chunks_fts MATCH ?
                {where_sql}
                ORDER BY fts.rank
                LIMIT ?
            """

        params = [fts_expr] + where_params + [max_results]
        rows = self.conn.execute(sql, params).fetchall()

        packs: list[dict[str, Any]] = []
        for row in rows:
            row_dict = dict(row)
            credibility = _credibility_hint_from_json(row_dict.get("raw_json", ""))
            pack = _to_evidence_pack(
                {
                    "chunk_id": row_dict.get("chunk_id"),
                    "url": row_dict.get("url"),
                    "source_id": row_dict.get("source_id"),
                    "title": row_dict.get("title"),
                    "published_at": row_dict.get("published_at"),
                    "quote": row_dict.get("quote"),
                    "credibility_hint": credibility,
                },
                relevance_score=row_dict.get("relevance_score", 0.0),
            )
            packs.append(pack)
        return packs

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "SQLiteEvidenceRetriever":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


# ---------------------------------------------------------------------------
# BM25EvidenceRetriever
# ---------------------------------------------------------------------------


class BM25EvidenceRetriever:
    """In-memory BM25 scorer over evidence chunks.

    Parameters
    ----------
    chunks:
        Evidence chunk dicts (as built by
        :func:`games_news_agent.evidence_store.build_evidence_chunks`).
    k1:
        Term-frequency saturation parameter.  Default 1.2.
    b:
        Length-normalisation parameter.  Default 0.75.
    """

    def __init__(
        self,
        chunks: list[dict[str, Any]],
        k1: float = 1.2,
        b: float = 0.75,
    ) -> None:
        self.chunks = chunks
        self.k1 = k1
        self.b = b
        self._doc_tokens: list[dict[str, int]] = []
        self._doc_lens: list[int] = []
        self._avg_doc_len: float = 0.0
        self._idf: dict[str, float] = {}
        self._N: int = 0
        if chunks:
            self._index()

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    def _tokenize(self, text: str) -> list[str]:
        """Tokenize using the same stopword-aware tokeniser."""
        raw_tokens = re.findall(r"[a-z0-9]+|[一-鿿]{2,}", text.lower())
        return [t for t in raw_tokens if t not in STOPWORDS and len(t) > 1]

    def _index(self) -> None:
        all_tokens: list[list[str]] = []
        for chunk in self.chunks:
            text = f"{chunk.get('title', '')} {chunk.get('quote', '')}"
            tokens = self._tokenize(text)
            all_tokens.append(tokens)

        self._N = len(self.chunks)
        self._doc_lens = [len(tokens) for tokens in all_tokens]
        self._avg_doc_len = (
            sum(self._doc_lens) / max(self._N, 1) if self._N > 0 else 0.0
        )

        # TF counts per document
        self._doc_tokens = []
        for tokens in all_tokens:
            tf: dict[str, int] = {}
            for token in tokens:
                tf[token] = tf.get(token, 0) + 1
            self._doc_tokens.append(tf)

        # Document frequencies
        df: dict[str, int] = {}
        for tf_map in self._doc_tokens:
            for token in tf_map:
                df[token] = df.get(token, 0) + 1

        # IDF
        for token, count in df.items():
            self._idf[token] = math.log(
                (self._N - count + 0.5) / (count + 0.5) + 1.0
            )

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def _bm25_score(self, query_tokens: set[str], doc_idx: int) -> float:
        if doc_idx < 0 or doc_idx >= self._N:
            return 0.0
        doc_tf = self._doc_tokens[doc_idx]
        doc_len = self._doc_lens[doc_idx]
        score = 0.0
        for token in query_tokens:
            if token not in self._idf:
                continue
            tf = doc_tf.get(token, 0)
            if tf == 0:
                continue
            idf = self._idf[token]
            numerator = tf * (self.k1 + 1)
            denominator = tf + self.k1 * (
                1.0 - self.b + self.b * doc_len / max(self._avg_doc_len, 1.0)
            )
            score += idf * numerator / denominator
        return score

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        max_results: int = 5,
        **filters: Any,
    ) -> list[dict[str, Any]]:
        """BM25-ranked search over in-memory chunks with metadata filters.

        Parameters
        ----------
        query:
            Natural-language query text.
        max_results:
            Maximum number of evidence packs to return.
        **filters:
            ``source_ids``, ``theme_section``, ``time_window`` (see
            :func:`_passes_filters`).

        Returns
        -------
        list[dict]
            Evidence packs (same schema as :meth:`SQLiteEvidenceRetriever.search`).
        """
        query_tokens = self._tokenize(query)
        query_tokens_set = set(query_tokens)
        if not query_tokens_set or self._N == 0:
            return []

        scored: list[tuple[float, dict[str, Any]]] = []
        for idx, chunk in enumerate(self.chunks):
            if not _passes_filters(chunk, **filters):
                continue
            score = self._bm25_score(query_tokens_set, idx)
            if score > 0:
                scored.append((score, chunk))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            _to_evidence_pack(chunk, relevance_score=score)
            for score, chunk in scored[:max_results]
        ]


# ---------------------------------------------------------------------------
# Unified entry point
# ---------------------------------------------------------------------------


def retrieve_evidence(
    claim_or_story: dict[str, Any] | str,
    db_path: str | Path | None = None,
    *,
    max_results: int = 5,
    **filters: Any,
) -> dict[str, Any]:
    """Retrieve evidence packs using the best available method.

    Strategy (in priority order):
    1. **FTS5** — when ``db_path`` points to a valid SQLite mirror.
    2. **BM25** — when ``chunks`` kwarg is passed.
    3. **Keyword** — deterministic fallback using token overlap.

    The result matches the ``retrieved_evidence_packs.json`` schema::

        {
          "query": "<derived query text>",
          "timestamp": "2026-06-16T...",
          "retriever": "fts5 | bm25 | keyword",
          "packs": [
            {
              "chunk_id": "...",
              "url": "...",
              "source_id": "...",
              "title": "...",
              "published_at": "...",
              "quote": "...",
              "credibility_hint": "...",
              "relevance_score": 0.0
            }
          ]
        }

    Parameters
    ----------
    claim_or_story:
        A claim dict, story dict, or raw query string.  The function
        extracts ``text`` / ``title`` / ``summary`` for search.
    db_path:
        Path to a SQLite mirror database.  When provided, FTS5 is used.
    max_results:
        How many evidence packs to return (default 5).
    **filters:
        ``source_ids``, ``theme_section``, ``time_window``, and also
        ``chunks`` (a ``list[dict]``) for BM25/keyword fallback.

    Returns
    -------
    dict
        Retrieval result with ``query``, ``timestamp``, ``retriever``, and
        ``packs``.
    """
    query_text = _extract_query_text(claim_or_story)
    timestamp = datetime.now(timezone.utc).isoformat()

    # Extract chunks from filters if present
    chunks: list[dict[str, Any]] | None = filters.pop("chunks", None)

    # Move source_ids to filter-compatible form
    source_ids_raw = filters.pop("source_ids", None)
    if isinstance(source_ids_raw, (list, tuple)):
        source_ids_raw = set(source_ids_raw)

    # --- Try FTS5 ---
    if db_path is not None:
        try:
            with SQLiteEvidenceRetriever(db_path) as retriever:
                packs = retriever.search(
                    query_text,
                    max_results=max_results,
                    source_ids=source_ids_raw,
                    **filters,
                )
            return {
                "query": query_text,
                "timestamp": timestamp,
                "retriever": "fts5",
                "packs": packs,
            }
        except Exception:
            # FTS5 failed — fall through
            pass

    # --- Try BM25 ---
    if chunks:
        bm25 = BM25EvidenceRetriever(chunks)
        packs = bm25.search(
            query_text,
            max_results=max_results,
            source_ids=source_ids_raw,
            **filters,
        )
        if packs:
            return {
                "query": query_text,
                "timestamp": timestamp,
                "retriever": "bm25",
                "packs": packs,
            }

    # --- Fallback: keyword ---
    if chunks:
        keyword_packs = _retrieve_evidence_keyword(
            chunks,
            query_text,
            top_k=max_results,
            source_ids=source_ids_raw,
        )
        return {
            "query": query_text,
            "timestamp": timestamp,
            "retriever": "keyword",
            "packs": [
                _to_evidence_pack(chunk, relevance_score=float(chunk.get("score", 0)))
                for chunk in keyword_packs
            ],
        }

    # No chunks, no db — return empty
    return {
        "query": query_text,
        "timestamp": timestamp,
        "retriever": "none",
        "packs": [],
    }


def retrieve_evidence_packs_to_json(
    claim_or_story: dict[str, Any] | str,
    db_path: str | Path | None = None,
    *,
    max_results: int = 5,
    **filters: Any,
) -> str:
    """Convenience: call ``retrieve_evidence`` and return a JSON string."""
    result = retrieve_evidence(
        claim_or_story,
        db_path=db_path,
        max_results=max_results,
        **filters,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Backward-compatible shim for context_packs.py
# ---------------------------------------------------------------------------


def retrieve_evidence_from_chunks(
    chunks: list[dict[str, Any]],
    query: str,
    *,
    top_k: int = 5,
    source_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Legacy compat wrapper — delegates to keyword retriever.

    Prefer :func:`retrieve_evidence` for new code.  This function is kept
    for existing callers (e.g. :mod:`games_news_agent.context_packs`).
    """
    return _retrieve_evidence_keyword(
        chunks, query, top_k=top_k, source_ids=source_ids
    )
