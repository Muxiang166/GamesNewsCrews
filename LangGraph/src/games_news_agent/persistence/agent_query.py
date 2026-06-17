"""Read-only SQLite query helpers for agents and review tools.

The SQLite mirror remains an index of run artifacts. This module exposes a
small whitelist of stable queries so an agent can inspect runs without scanning
output folders or generating ad-hoc SQL.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any, Sequence


SCHEMA_VERSION = "agent_db_query_v0"

RUN_TABLES = (
    "artifacts",
    "raw_sources",
    "candidates",
    "documents",
    "evidence_chunks",
    "claims",
    "claim_verifications",
    "story_candidates",
    "stories",
    "platform_posts",
    "user_notifications",
)


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def _connect_readonly(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"SQLite database does not exist: {path}")
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _parse_raw_json(value: Any) -> Any:
    if not isinstance(value, str) or not value:
        return {}
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return {}


def _row_to_dict(row: sqlite3.Row, *, include_raw: bool = False) -> dict[str, Any]:
    data = {key: row[key] for key in row.keys() if key != "raw_json"}
    if include_raw and "raw_json" in row.keys():
        data["raw_json"] = _parse_raw_json(row["raw_json"])
    return data


def _limit(value: int | str | None) -> int:
    try:
        parsed = int(value or 20)
    except (TypeError, ValueError):
        parsed = 20
    return max(1, min(parsed, 500))


def _latest_run_id(conn: sqlite3.Connection) -> str:
    row = conn.execute(
        """
        select run_id
        from runs
        order by
            coalesce(nullif(ended_at, ''), nullif(started_at, ''), run_id) desc,
            rowid desc
        limit 1
        """
    ).fetchone()
    return str(row["run_id"]) if row else ""


def _resolve_run_id(conn: sqlite3.Connection, run_id: str | None) -> str:
    resolved = str(run_id or "").strip() or _latest_run_id(conn)
    if not resolved:
        raise ValueError("No run_id was provided and the database has no runs.")
    return resolved


def _base_result(
    *,
    query_type: str,
    db_path: str | Path,
    run_id: str = "",
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "query_type": query_type,
        "db_path": str(db_path),
        "run_id": run_id,
        "filters": filters or {},
        "rows": [],
        "summary": {},
    }


def list_runs(conn: sqlite3.Connection, *, limit: int = 20) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        select run_id, output_dir, status, started_at, ended_at, schema_version
        from runs
        order by
            coalesce(nullif(ended_at, ''), nullif(started_at, ''), run_id) desc,
            rowid desc
        limit ?
        """,
        (_limit(limit),),
    ).fetchall()
    return [_row_to_dict(row) for row in rows]


def get_run_summary(conn: sqlite3.Connection, *, run_id: str | None = None) -> dict[str, Any]:
    resolved = _resolve_run_id(conn, run_id)
    run = conn.execute(
        "select run_id, output_dir, status, started_at, ended_at, schema_version from runs where run_id = ?",
        (resolved,),
    ).fetchone()
    if run is None:
        raise ValueError(f"Run not found: {resolved}")
    counts: dict[str, int] = {}
    for table in RUN_TABLES:
        counts[table] = int(
            conn.execute(f"select count(*) from {table} where run_id = ?", (resolved,)).fetchone()[0]
        )
    open_notifications = int(
        conn.execute(
            "select count(*) from user_notifications where run_id = ? and status != 'closed'",
            (resolved,),
        ).fetchone()[0]
    )
    return {
        "run": _row_to_dict(run),
        "table_counts": counts,
        "open_notifications": open_notifications,
    }


def list_stories(
    conn: sqlite3.Connection,
    *,
    run_id: str | None = None,
    theme_section: str = "",
    limit: int = 20,
    include_raw: bool = False,
) -> list[dict[str, Any]]:
    resolved = _resolve_run_id(conn, run_id)
    where = ["run_id = ?"]
    params: list[Any] = [resolved]
    if theme_section:
        where.append("theme_section = ?")
        params.append(theme_section)
    params.append(_limit(limit))
    rows = conn.execute(
        f"""
        select run_id, story_id, title, theme_section, status, selection_status,
               story_score, publish_status, published_at, platform_publish_id, raw_json
        from stories
        where {' and '.join(where)}
        order by story_score desc, story_id asc
        limit ?
        """,
        params,
    ).fetchall()
    return [_row_to_dict(row, include_raw=include_raw) for row in rows]


def list_candidates(
    conn: sqlite3.Connection,
    *,
    run_id: str | None = None,
    lane: str = "",
    theme_section: str = "",
    source_id: str = "",
    limit: int = 20,
    include_raw: bool = False,
) -> list[dict[str, Any]]:
    resolved = _resolve_run_id(conn, run_id)
    where = ["run_id = ?"]
    params: list[Any] = [resolved]
    if lane:
        where.append("lane = ?")
        params.append(lane)
    if theme_section:
        where.append("theme_section = ?")
        params.append(theme_section)
    if source_id:
        where.append("source_id = ?")
        params.append(source_id)
    params.append(_limit(limit))
    rows = conn.execute(
        f"""
        select run_id, lane, candidate_id, title, url, source_id, published_at,
               observed_at, theme_section, heat_score, memory_status,
               reject_reason, raw_json
        from candidates
        where {' and '.join(where)}
        order by heat_score desc, published_at desc, observed_at desc, candidate_id asc
        limit ?
        """,
        params,
    ).fetchall()
    return [_row_to_dict(row, include_raw=include_raw) for row in rows]


def list_notifications(
    conn: sqlite3.Connection,
    *,
    run_id: str | None = None,
    severity: str = "",
    status: str = "",
    limit: int = 50,
    include_raw: bool = False,
) -> list[dict[str, Any]]:
    resolved = _resolve_run_id(conn, run_id)
    where = ["run_id = ?"]
    params: list[Any] = [resolved]
    if severity:
        where.append("severity = ?")
        params.append(severity)
    if status:
        where.append("status = ?")
        params.append(status)
    params.append(_limit(limit))
    rows = conn.execute(
        f"""
        select run_id, notification_id, severity, stage, issue_id, title,
               message, status, raw_json
        from user_notifications
        where {' and '.join(where)}
        order by severity desc, notification_id asc
        limit ?
        """,
        params,
    ).fetchall()
    return [_row_to_dict(row, include_raw=include_raw) for row in rows]


def list_artifacts(
    conn: sqlite3.Connection,
    *,
    run_id: str | None = None,
    stage: str = "",
    limit: int = 100,
    include_raw: bool = False,
) -> list[dict[str, Any]]:
    resolved = _resolve_run_id(conn, run_id)
    where = ["run_id = ?"]
    params: list[Any] = [resolved]
    if stage:
        where.append("stage = ?")
        params.append(stage)
    params.append(_limit(limit))
    rows = conn.execute(
        f"""
        select run_id, artifact_key, path, stage, exists_flag, size_bytes,
               sha256, raw_json
        from artifacts
        where {' and '.join(where)}
        order by stage asc, artifact_key asc, path asc
        limit ?
        """,
        params,
    ).fetchall()
    return [_row_to_dict(row, include_raw=include_raw) for row in rows]


def list_quality_flags(
    conn: sqlite3.Connection,
    *,
    run_id: str | None = None,
    min_title_chars: int = 8,
    limit: int = 50,
) -> list[dict[str, Any]]:
    resolved = _resolve_run_id(conn, run_id)
    flags: list[dict[str, Any]] = []

    for table, id_column in (("stories", "story_id"), ("story_candidates", "story_id")):
        rows = conn.execute(
            f"""
            select {id_column} as object_id, title, theme_section, raw_json
            from {table}
            where run_id = ? and length(trim(title)) < ?
            order by length(trim(title)) asc, title asc
            limit ?
            """,
            (resolved, max(1, min_title_chars), _limit(limit)),
        ).fetchall()
        for row in rows:
            flags.append(
                {
                    "flag_type": "short_title",
                    "table": table,
                    "object_id": row["object_id"],
                    "title": row["title"],
                    "theme_section": row["theme_section"],
                }
            )

    document_rows = conn.execute(
        "select document_id, candidate_url, title, raw_json from documents where run_id = ?",
        (resolved,),
    ).fetchall()
    for row in document_rows:
        raw = _parse_raw_json(row["raw_json"])
        if not str(raw.get("content") or "").strip():
            flags.append(
                {
                    "flag_type": "empty_document_content",
                    "table": "documents",
                    "object_id": row["document_id"],
                    "title": row["title"],
                    "url": row["candidate_url"],
                }
            )

    notifications = list_notifications(conn, run_id=resolved, status="open", limit=limit)
    for row in notifications:
        flags.append(
            {
                "flag_type": "open_notification",
                "table": "user_notifications",
                "object_id": row["notification_id"],
                "title": row["title"],
                "stage": row["stage"],
                "severity": row["severity"],
            }
        )

    return flags[: _limit(limit)]


def query_agent_database(
    *,
    db_path: str | Path,
    query_type: str,
    run_id: str | None = None,
    limit: int = 20,
    include_raw: bool = False,
    theme_section: str = "",
    lane: str = "",
    source_id: str = "",
    severity: str = "",
    status: str = "",
    stage: str = "",
    min_title_chars: int = 8,
) -> dict[str, Any]:
    """Run a whitelisted read-only database query for agents."""

    filters = {
        "limit": _limit(limit),
        "include_raw": include_raw,
        "theme_section": theme_section,
        "lane": lane,
        "source_id": source_id,
        "severity": severity,
        "status": status,
        "stage": stage,
        "min_title_chars": min_title_chars,
    }
    result = _base_result(
        query_type=query_type,
        db_path=db_path,
        run_id=str(run_id or ""),
        filters={key: value for key, value in filters.items() if value not in ("", False, None)},
    )
    conn = _connect_readonly(db_path)
    try:
        if query_type == "runs":
            rows = list_runs(conn, limit=limit)
            result["rows"] = rows
            result["summary"] = {"row_count": len(rows)}
            return result

        resolved = _resolve_run_id(conn, run_id)
        result["run_id"] = resolved
        if query_type == "summary":
            summary = get_run_summary(conn, run_id=resolved)
            result["summary"] = summary
            result["rows"] = [summary["run"]]
        elif query_type == "stories":
            rows = list_stories(
                conn,
                run_id=resolved,
                theme_section=theme_section,
                limit=limit,
                include_raw=include_raw,
            )
            result["rows"] = rows
            result["summary"] = {"row_count": len(rows)}
        elif query_type == "candidates":
            rows = list_candidates(
                conn,
                run_id=resolved,
                lane=lane,
                theme_section=theme_section,
                source_id=source_id,
                limit=limit,
                include_raw=include_raw,
            )
            result["rows"] = rows
            result["summary"] = {"row_count": len(rows)}
        elif query_type == "notifications":
            rows = list_notifications(
                conn,
                run_id=resolved,
                severity=severity,
                status=status,
                limit=limit,
                include_raw=include_raw,
            )
            result["rows"] = rows
            result["summary"] = {"row_count": len(rows)}
        elif query_type == "artifacts":
            rows = list_artifacts(
                conn,
                run_id=resolved,
                stage=stage,
                limit=limit,
                include_raw=include_raw,
            )
            result["rows"] = rows
            result["summary"] = {"row_count": len(rows)}
        elif query_type == "quality-flags":
            rows = list_quality_flags(
                conn,
                run_id=resolved,
                min_title_chars=min_title_chars,
                limit=limit,
            )
            result["rows"] = rows
            result["summary"] = {"row_count": len(rows)}
        else:
            raise ValueError(f"Unknown query_type: {query_type}")
    finally:
        conn.close()
    return result


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="agent-db-query",
        description="Run read-only whitelisted queries against a Games News SQLite mirror.",
    )
    parser.add_argument("--db-path", required=True, help="SQLite mirror path.")

    subcommands = parser.add_subparsers(dest="query_type", required=True)
    runs = subcommands.add_parser("runs", help="List recent runs.")
    runs.add_argument("--limit", type=int, default=20)

    summary = subcommands.add_parser("summary", help="Show one run summary.")
    summary.add_argument("--run-id", default="")

    stories = subcommands.add_parser("stories", help="List final stories.")
    stories.add_argument("--run-id", default="")
    stories.add_argument("--theme", dest="theme_section", default="")
    stories.add_argument("--limit", type=int, default=20)
    stories.add_argument("--include-raw", action="store_true")

    candidates = subcommands.add_parser("candidates", help="List collected candidates.")
    candidates.add_argument("--run-id", default="")
    candidates.add_argument("--lane", default="")
    candidates.add_argument("--theme", dest="theme_section", default="")
    candidates.add_argument("--source", dest="source_id", default="")
    candidates.add_argument("--limit", type=int, default=20)
    candidates.add_argument("--include-raw", action="store_true")

    notifications = subcommands.add_parser("notifications", help="List user notifications.")
    notifications.add_argument("--run-id", default="")
    notifications.add_argument("--severity", default="")
    notifications.add_argument("--status", default="")
    notifications.add_argument("--limit", type=int, default=50)
    notifications.add_argument("--include-raw", action="store_true")

    artifacts = subcommands.add_parser("artifacts", help="List artifact index records.")
    artifacts.add_argument("--run-id", default="")
    artifacts.add_argument("--stage", default="")
    artifacts.add_argument("--limit", type=int, default=100)
    artifacts.add_argument("--include-raw", action="store_true")

    quality = subcommands.add_parser("quality-flags", help="List obvious review flags.")
    quality.add_argument("--run-id", default="")
    quality.add_argument("--min-title-chars", type=int, default=8)
    quality.add_argument("--limit", type=int, default=50)

    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = query_agent_database(
        db_path=args.db_path,
        query_type=args.query_type,
        run_id=getattr(args, "run_id", ""),
        limit=getattr(args, "limit", 20),
        include_raw=getattr(args, "include_raw", False),
        theme_section=getattr(args, "theme_section", ""),
        lane=getattr(args, "lane", ""),
        source_id=getattr(args, "source_id", ""),
        severity=getattr(args, "severity", ""),
        status=getattr(args, "status", ""),
        stage=getattr(args, "stage", ""),
        min_title_chars=getattr(args, "min_title_chars", 8),
    )
    print(_json_text(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
