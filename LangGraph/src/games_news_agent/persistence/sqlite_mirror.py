"""SQLite mirror for replayable LangGraph run artifacts.

JSON artifacts remain the source of truth for the current workflow. This module
builds a query-friendly mirror so later deduplication, RAG, review, and
publication state can work across runs.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Sequence

from ..io import read_json, read_jsonl


SCHEMA_VERSION = "0.1.0"


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


def _optional_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return read_json(path)
    except (OSError, json.JSONDecodeError):
        return default


def _optional_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        return read_jsonl(path)
    except (OSError, json.JSONDecodeError):
        return []


def _rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _run_id(output_dir: Path, manifest: dict[str, Any]) -> str:
    explicit = _text(manifest.get("run_id"))
    if explicit:
        return explicit
    return f"run_{output_dir.name}"


def _create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        create table if not exists runs (
            run_id text primary key,
            output_dir text not null,
            status text not null default '',
            started_at text not null default '',
            ended_at text not null default '',
            schema_version text not null,
            manifest_json text not null
        );

        create table if not exists artifacts (
            run_id text not null,
            artifact_key text not null,
            path text not null,
            stage text not null default '',
            exists_flag integer not null default 0,
            size_bytes integer not null default 0,
            sha256 text not null default '',
            raw_json text not null,
            primary key (run_id, artifact_key, path)
        );

        create table if not exists raw_sources (
            run_id text not null,
            source_id text not null default '',
            url text not null default '',
            collector text not null default '',
            ok integer not null default 0,
            status_code integer,
            fetched_at text not null default '',
            raw_json text not null
        );

        create table if not exists candidates (
            run_id text not null,
            lane text not null,
            candidate_id text not null,
            title text not null default '',
            url text not null default '',
            source_id text not null default '',
            published_at text not null default '',
            observed_at text not null default '',
            theme_section text not null default '',
            heat_score real not null default 0,
            memory_status text not null default '',
            reject_reason text not null default '',
            raw_json text not null,
            primary key (run_id, lane, candidate_id)
        );

        create table if not exists documents (
            run_id text not null,
            document_id text not null,
            candidate_url text not null default '',
            title text not null default '',
            source_id text not null default '',
            published_at text not null default '',
            fetched_at text not null default '',
            raw_json text not null,
            primary key (run_id, document_id)
        );

        create table if not exists evidence_chunks (
            run_id text not null,
            chunk_id text not null,
            url text not null default '',
            source_id text not null default '',
            title text not null default '',
            published_at text not null default '',
            quote text not null default '',
            raw_json text not null,
            primary key (run_id, chunk_id)
        );

        create table if not exists claims (
            run_id text not null,
            claim_id text not null,
            story_id text not null default '',
            text text not null default '',
            check_status text not null default '',
            confidence real not null default 0,
            raw_json text not null,
            primary key (run_id, claim_id)
        );

        create table if not exists claim_verifications (
            run_id text not null,
            verification_id text not null,
            claim_id text not null default '',
            story_id text not null default '',
            status text not null default '',
            confidence real not null default 0,
            raw_json text not null,
            primary key (run_id, verification_id)
        );

        create table if not exists story_candidates (
            run_id text not null,
            story_id text not null,
            title text not null default '',
            theme_section text not null default '',
            status text not null default '',
            story_score real not null default 0,
            raw_json text not null,
            primary key (run_id, story_id)
        );

        create table if not exists stories (
            run_id text not null,
            story_id text not null,
            title text not null default '',
            theme_section text not null default '',
            status text not null default '',
            selection_status text not null default 'final',
            story_score real not null default 0,
            publish_status text not null default 'unpublished',
            published_at text not null default '',
            platform_publish_id text not null default '',
            raw_json text not null,
            primary key (run_id, story_id)
        );

        create table if not exists platform_posts (
            run_id text not null,
            post_id text not null,
            story_id text not null default '',
            platform text not null default '',
            publish_status text not null default 'draft',
            published_at text not null default '',
            platform_publish_id text not null default '',
            raw_json text not null,
            primary key (run_id, post_id)
        );

        create table if not exists user_notifications (
            run_id text not null,
            notification_id text not null,
            severity text not null default '',
            stage text not null default '',
            issue_id text not null default '',
            title text not null default '',
            message text not null default '',
            status text not null default 'open',
            raw_json text not null,
            primary key (run_id, notification_id)
        );
        """
    )


def _delete_run(conn: sqlite3.Connection, run_id: str) -> None:
    tables = [
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
        "runs",
    ]
    for table in tables:
        conn.execute(f"delete from {table} where run_id = ?", (run_id,))


def _candidate_id(item: dict[str, Any], index: int) -> str:
    for key in ("candidate_id", "id", "url", "title"):
        value = _text(item.get(key))
        if value:
            return value
    return f"candidate_{index}"


def _story_id(item: dict[str, Any], index: int) -> str:
    for key in ("id", "story_id", "title"):
        value = _text(item.get(key))
        if value:
            return value
    return f"story_{index}"


def _claim_id(item: dict[str, Any], index: int) -> str:
    for key in ("claim_id", "id", "text"):
        value = _text(item.get(key))
        if value:
            return value
    return f"claim_{index}"


def _document_id(item: dict[str, Any], index: int) -> str:
    for key in ("document_id", "id", "candidate_url", "url", "title"):
        value = _text(item.get(key))
        if value:
            return value
    return f"document_{index}"


def _insert_candidates(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    lane: str,
    items: Iterable[dict[str, Any]],
) -> int:
    count = 0
    for index, item in enumerate(items, start=1):
        conn.execute(
            """
            insert or replace into candidates (
                run_id, lane, candidate_id, title, url, source_id,
                published_at, observed_at, theme_section, heat_score,
                memory_status, reject_reason, raw_json
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                lane,
                _candidate_id(item, index),
                _text(item.get("title")),
                _text(item.get("url")),
                _text(item.get("source_id")),
                _text(item.get("published_at")),
                _text(item.get("observed_at")),
                _text(item.get("theme_section")),
                _number(item.get("heat_score")),
                _text(item.get("memory_status")),
                _text(item.get("reject_reason")),
                _json_text(item),
            ),
        )
        count += 1
    return count


def _insert_list_artifacts(conn: sqlite3.Connection, *, run_id: str, output_dir: Path) -> dict[str, int]:
    counts: dict[str, int] = {}

    raw_sources = _optional_jsonl(output_dir / "raw_sources.jsonl")
    for item in raw_sources:
        conn.execute(
            """
            insert into raw_sources (
                run_id, source_id, url, collector, ok, status_code, fetched_at, raw_json
            ) values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                _text(item.get("source_id")),
                _text(item.get("url")),
                _text(item.get("collector")),
                1 if bool(item.get("ok")) else 0,
                item.get("status_code") if item.get("status_code") != "" else None,
                _text(item.get("fetched_at")),
                _json_text(item),
            ),
        )
    counts["raw_sources"] = len(raw_sources)

    counts["candidates"] = 0
    counts["candidates"] += _insert_candidates(
        conn,
        run_id=run_id,
        lane="main",
        items=_rows(_optional_json(output_dir / "candidates.json", [])),
    )
    counts["candidates"] += _insert_candidates(
        conn,
        run_id=run_id,
        lane="supplemental",
        items=_rows(_optional_json(output_dir / "supplemental_candidates.json", [])),
    )
    counts["candidates"] += _insert_candidates(
        conn,
        run_id=run_id,
        lane="rejected",
        items=_rows(_optional_json(output_dir / "rejected_candidates.json", [])),
    )

    documents = _rows(_optional_json(output_dir / "documents.json", []))
    for index, item in enumerate(documents, start=1):
        conn.execute(
            """
            insert or replace into documents (
                run_id, document_id, candidate_url, title, source_id,
                published_at, fetched_at, raw_json
            ) values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                _document_id(item, index),
                _text(item.get("candidate_url") or item.get("url")),
                _text(item.get("title")),
                _text(item.get("source_id")),
                _text(item.get("published_at")),
                _text(item.get("fetched_at")),
                _json_text(item),
            ),
        )
    counts["documents"] = len(documents)

    chunks = _rows(_optional_json(output_dir / "evidence_chunks.json", []))
    for index, item in enumerate(chunks, start=1):
        chunk_id = _text(item.get("chunk_id") or item.get("id")) or f"chunk_{index}"
        conn.execute(
            """
            insert or replace into evidence_chunks (
                run_id, chunk_id, url, source_id, title, published_at, quote, raw_json
            ) values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                chunk_id,
                _text(item.get("url") or item.get("source_url")),
                _text(item.get("source_id")),
                _text(item.get("title")),
                _text(item.get("published_at")),
                _text(item.get("quote") or item.get("snippet")),
                _json_text(item),
            ),
        )
    counts["evidence_chunks"] = len(chunks)

    claims = _rows(_optional_json(output_dir / "claims.json", []))
    for index, item in enumerate(claims, start=1):
        conn.execute(
            """
            insert or replace into claims (
                run_id, claim_id, story_id, text, check_status, confidence, raw_json
            ) values (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                _claim_id(item, index),
                _text(item.get("story_id")),
                _text(item.get("text")),
                _text(item.get("check_status") or item.get("status")),
                _number(item.get("confidence")),
                _json_text(item),
            ),
        )
    counts["claims"] = len(claims)

    verifications = _rows(_optional_json(output_dir / "claim_verifications.json", []))
    for index, item in enumerate(verifications, start=1):
        verification_id = _text(item.get("verification_id") or item.get("id")) or f"verification_{index}"
        conn.execute(
            """
            insert or replace into claim_verifications (
                run_id, verification_id, claim_id, story_id, status, confidence, raw_json
            ) values (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                verification_id,
                _text(item.get("claim_id")),
                _text(item.get("story_id")),
                _text(item.get("status") or item.get("verification_status")),
                _number(item.get("confidence")),
                _json_text(item),
            ),
        )
    counts["claim_verifications"] = len(verifications)

    story_candidates = _rows(_optional_json(output_dir / "story_candidates.json", []))
    for index, item in enumerate(story_candidates, start=1):
        conn.execute(
            """
            insert or replace into story_candidates (
                run_id, story_id, title, theme_section, status, story_score, raw_json
            ) values (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                _story_id(item, index),
                _text(item.get("title")),
                _text(item.get("theme_section")),
                _text(item.get("status")),
                _number(item.get("story_score") or item.get("score")),
                _json_text(item),
            ),
        )
    counts["story_candidates"] = len(story_candidates)

    stories = _rows(_optional_json(output_dir / "stories.json", []))
    for index, item in enumerate(stories, start=1):
        conn.execute(
            """
            insert or replace into stories (
                run_id, story_id, title, theme_section, status, selection_status,
                story_score, publish_status, published_at, platform_publish_id, raw_json
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                _story_id(item, index),
                _text(item.get("title")),
                _text(item.get("theme_section")),
                _text(item.get("status")),
                _text(item.get("selection_status")) or "final",
                _number(item.get("story_score") or item.get("score")),
                _text(item.get("publish_status")) or "unpublished",
                _text(item.get("published_at")),
                _text(item.get("platform_publish_id")),
                _json_text(item),
            ),
        )
    counts["stories"] = len(stories)

    posts = _rows(_optional_json(output_dir / "platform_posts.json", []))
    for index, item in enumerate(posts, start=1):
        post_id = _text(item.get("post_id") or item.get("id")) or f"post_{index}"
        conn.execute(
            """
            insert or replace into platform_posts (
                run_id, post_id, story_id, platform, publish_status, published_at,
                platform_publish_id, raw_json
            ) values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                post_id,
                _text(item.get("story_id")),
                _text(item.get("platform")),
                _text(item.get("publish_status")) or "draft",
                _text(item.get("published_at")),
                _text(item.get("platform_publish_id")),
                _json_text(item),
            ),
        )
    counts["platform_posts"] = len(posts)

    notifications = _rows(_optional_json(output_dir / "user_notifications.json", []))
    for index, item in enumerate(notifications, start=1):
        notification_id = _text(item.get("notification_id")) or f"notification_{index}"
        conn.execute(
            """
            insert or replace into user_notifications (
                run_id, notification_id, severity, stage, issue_id, title, message, status, raw_json
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                notification_id,
                _text(item.get("severity")),
                _text(item.get("stage")),
                _text(item.get("issue_id")),
                _text(item.get("title")),
                _text(item.get("message")),
                _text(item.get("status")) or "open",
                _json_text(item),
            ),
        )
    counts["user_notifications"] = len(notifications)
    return counts


def ingest_run(*, output_dir: str | Path, db_path: str | Path) -> dict[str, Any]:
    """Mirror one LangGraph output directory into SQLite.

    The operation is idempotent for a run_id: existing rows for that run are
    replaced before the latest artifact snapshot is inserted.
    """

    run_dir = Path(output_dir)
    database = Path(db_path)
    database.parent.mkdir(parents=True, exist_ok=True)
    manifest = _optional_json(run_dir / "run_manifest.json", {})
    if not isinstance(manifest, dict):
        manifest = {}
    run_id = _run_id(run_dir, manifest)

    conn = sqlite3.connect(database)
    try:
        _create_schema(conn)
        _delete_run(conn, run_id)
        conn.execute(
            """
            insert into runs (
                run_id, output_dir, status, started_at, ended_at, schema_version, manifest_json
            ) values (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                str(run_dir),
                _text(manifest.get("status")),
                _text(manifest.get("started_at")),
                _text(manifest.get("ended_at")),
                SCHEMA_VERSION,
                _json_text(manifest),
            ),
        )
        for item in _rows(manifest.get("artifact_index")):
            conn.execute(
                """
                insert or replace into artifacts (
                    run_id, artifact_key, path, stage, exists_flag, size_bytes, sha256, raw_json
                ) values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    _text(item.get("artifact_key")),
                    _text(item.get("path")),
                    _text(item.get("stage")),
                    1 if bool(item.get("exists")) else 0,
                    int(_number(item.get("size_bytes"))),
                    _text(item.get("sha256")),
                    _json_text(item),
                ),
        )
        counts = _insert_list_artifacts(conn, run_id=run_id, output_dir=run_dir)
        counts["artifacts"] = len(_rows(manifest.get("artifact_index")))
        counts["runs"] = 1
        conn.commit()
    finally:
        conn.close()

    return {
        "db_path": str(database),
        "output_dir": str(run_dir),
        "run_id": run_id,
        "schema_version": SCHEMA_VERSION,
        "tables": counts,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="sqlite-mirror",
        description="Ingest a LangGraph output directory into a local SQLite mirror.",
    )
    parser.add_argument("--output-dir", required=True, help="LangGraph output directory to ingest.")
    parser.add_argument("--db-path", required=True, help="SQLite database path to create or update.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    summary = ingest_run(output_dir=args.output_dir, db_path=args.db_path)
    print(_json_text(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
