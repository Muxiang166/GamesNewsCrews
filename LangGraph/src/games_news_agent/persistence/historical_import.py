"""MEM-003: Ingest historical runs, detect duplicates, and build eval sets.

Uses the SQLite mirror (sqlite_mirror.py) as the event store. All v0 logic is
SQL-query-based — no LLM needed.
"""

from __future__ import annotations

import sqlite3
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

from .sqlite_mirror import ingest_run


# ---------------------------------------------------------------------------
# MEM-003: import_from_output_dirs
# ---------------------------------------------------------------------------

def import_from_output_dirs(
    output_dirs: Iterable[str | Path],
    db_path: str | Path,
) -> dict[str, Any]:
    """Ingest multiple output_dir runs into the shared event store.

    Each run is imported idempotently via ``ingest_run``. The returned summary
    includes per-run counts and grand totals.
    """
    database = Path(db_path)
    database.parent.mkdir(parents=True, exist_ok=True)

    per_run: list[dict[str, Any]] = []
    run_ids: set[str] = set()
    total_rows: dict[str, int] = defaultdict(int)

    for output_dir in output_dirs:
        summary = ingest_run(output_dir=output_dir, db_path=database)
        per_run.append(summary)
        run_ids.add(summary["run_id"])
        for table, count in summary.get("tables", {}).items():
            total_rows[table] += count

    return {
        "db_path": str(database),
        "runs_imported": len(run_ids),
        "run_ids": sorted(run_ids),
        "per_run": per_run,
        "totals": dict(total_rows),
    }


# ---------------------------------------------------------------------------
# MEM-003: detect_duplicates_across_runs
# ---------------------------------------------------------------------------

def _normalize_title(title: str) -> str:
    """Normalize a title for fuzzy matching: lowercase, collapse whitespace,
    strip common noise words at the edges."""
    t = re.sub(r"\s+", " ", (title or "").strip().lower())
    # Strip common noise prefixes/suffixes
    t = re.sub(r"^(breaking|update|exclusive|just in|report)\s*:\s*", "", t)
    return t.strip()


def _title_similarity(a: str, b: str) -> float:
    """Simple word-overlap Jaccard-like similarity for duplicate detection."""
    na = _normalize_title(a)
    nb = _normalize_title(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    words_a = set(na.split())
    words_b = set(nb.split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


def _extract_domain(url: str) -> str:
    """Extract a simplified domain from a URL for matching."""
    m = re.search(r"://(?:www\.)?([^/]+)", (url or ""))
    return m.group(1).lower() if m else ""


def detect_duplicates_across_runs(
    db_path: str | Path,
    *,
    title_similarity_threshold: float = 0.65,
) -> list[dict[str, Any]]:
    """Scan the event store for same stories appearing across different runs.

    Detection strategy (v0):
      1. Group candidates and stories by normalized URL domain + title overlap.
      2. For each group, compute the Jaccard similarity of normalized titles.
      3. Pairs above *title_similarity_threshold* are treated as duplicates.

    Returns a list of duplicate groups, each containing the matched entries
    from different runs with their similarity scores.
    """
    conn = sqlite3.connect(str(db_path))
    try:
        # Collect all candidates across runs
        rows = list(
            conn.execute(
                """
                select run_id, lane, candidate_id, title, url, theme_section,
                       published_at, observed_at
                from candidates
                order by run_id, lane, candidate_id
                """
            )
        )
    except sqlite3.OperationalError:
        # Table does not exist (empty/uninitialized DB)
        return []
    finally:
        conn.close()

    if not rows:
        return []

    # Index by domain for efficient grouping
    domain_index: dict[str, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    entries: list[dict[str, Any]] = []
    for idx, row in enumerate(rows):
        entry = {
            "run_id": row[0],
            "lane": row[1],
            "candidate_id": row[2],
            "title": row[3],
            "url": row[4],
            "theme_section": row[5],
            "published_at": row[6],
            "observed_at": row[7],
        }
        entries.append(entry)
        domain = _extract_domain(entry["url"])
        domain_index[domain].append((idx, entry))

    duplicate_groups: list[dict[str, Any]] = []
    seen_pairs: set[tuple[int, int]] = set()

    for domain, domain_entries in domain_index.items():
        if len(domain_entries) < 2:
            continue
        for i in range(len(domain_entries)):
            for j in range(i + 1, len(domain_entries)):
                idx_a, entry_a = domain_entries[i]
                idx_b, entry_b = domain_entries[j]
                if entry_a["run_id"] == entry_b["run_id"]:
                    continue  # same run is not a cross-run duplicate
                pair_key = (min(idx_a, idx_b), max(idx_a, idx_b))
                if pair_key in seen_pairs:
                    continue
                sim = _title_similarity(entry_a["title"], entry_b["title"])
                if sim >= title_similarity_threshold:
                    seen_pairs.add(pair_key)
                    duplicate_groups.append(
                        {
                            "entry_a": entry_a,
                            "entry_b": entry_b,
                            "title_similarity": round(sim, 4),
                            "domain": domain,
                        }
                    )

    # Sort by similarity descending
    duplicate_groups.sort(key=lambda g: g["title_similarity"], reverse=True)
    return duplicate_groups


# ---------------------------------------------------------------------------
# MEM-003: build_evaluation_set
# ---------------------------------------------------------------------------

def build_evaluation_set(
    db_path: str | Path,
    min_date: str,
    max_date: str,
    max_items: int = 2000,
    *,
    seed: int = 42,
) -> list[dict[str, Any]]:
    """Export a balanced evaluation set from the event store.

    Balances across theme_section and lane, capped at *max_items*.
    Date filtering is applied on ``published_at`` (ISO-8601 text comparison).

    Returns a list of eval items with title, url, theme_section, lane,
    run_id, published_at, and raw_json.
    """
    conn = sqlite3.connect(str(db_path))
    try:
        # Count per theme_section within the date range
        theme_counts = dict(
            conn.execute(
                """
                select theme_section, count(*) as cnt
                from candidates
                where published_at >= ? and published_at <= ?
                  and coalesce(theme_section, '') != ''
                group by theme_section
                order by cnt desc
                """,
                (min_date, max_date),
            )
        )
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()

    if not theme_counts:
        return []

    total_eligible = sum(theme_counts.values())
    if total_eligible == 0:
        return []

    # Allocate per-theme quota proportionally, with a minimum floor of 1
    per_theme_quota: dict[str, int] = {}
    remaining = max_items
    for theme, cnt in sorted(theme_counts.items(), key=lambda x: -x[1]):
        if remaining <= 0:
            break
        quota = max(1, int(max_items * cnt / total_eligible))
        quota = min(quota, cnt, remaining)
        per_theme_quota[theme] = quota
        remaining -= quota

    eval_items: list[dict[str, Any]] = []
    rng_state = seed

    conn = sqlite3.connect(str(db_path))
    try:
        for theme, quota in per_theme_quota.items():
            rows = list(
                conn.execute(
                    """
                    select run_id, lane, candidate_id, title, url, theme_section,
                           published_at, raw_json
                    from candidates
                    where published_at >= ? and published_at <= ?
                      and theme_section = ?
                    order by published_at desc
                    """,
                    (min_date, max_date, theme),
                )
            )
            # Deterministic sampling: spread picks across the result set
            if len(rows) <= quota:
                pick_indices = list(range(len(rows)))
            else:
                step = len(rows) / quota
                pick_indices = sorted({int(i * step) for i in range(quota)} | {0, len(rows) - 1})
                pick_indices = pick_indices[:quota]

            for idx in pick_indices:
                if idx >= len(rows):
                    continue
                row = rows[idx]
                eval_items.append(
                    {
                        "run_id": row[0],
                        "lane": row[1],
                        "candidate_id": row[2],
                        "title": row[3],
                        "url": row[4],
                        "theme_section": row[5],
                        "published_at": row[6],
                        "raw_json": row[7],
                    }
                )
    finally:
        conn.close()

    # Ensure we don't exceed max_items
    if len(eval_items) > max_items:
        eval_items = eval_items[:max_items]

    return eval_items
