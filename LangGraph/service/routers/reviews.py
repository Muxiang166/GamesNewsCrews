"""SVC-003: Human review capture router.

Writes review records to human_reviews.json (source of truth) and
SQLite human_reviews table (query index). Never modifies facts, rankings,
claims, or platform drafts.

Endpoints:
    POST /api/v1/runs/{run_id}/human-reviews
    GET  /api/v1/runs/{run_id}/human-reviews

Reference harness: LangGraph/harness/service_workbench/H-SVC-003-human-review-save.json
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

_SERVICE_DIR = Path(__file__).resolve().parent.parent
_SRC_DIR = _SERVICE_DIR.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from games_news_agent.persistence.agent_query import (  # noqa: E402
    _connect_readonly,
    _latest_run_id,
)
from games_news_agent.io import read_json, write_json  # noqa: E402

router = APIRouter(prefix="/api/v1", tags=["reviews"])


# --- Pydantic models ---

_VALID_STYLE_DIRECTIONS = frozenset({
    "more_game_content_first",
    "more_community_discussion",
    "balanced",
    "breaking_news_priority",
    "in_depth_analysis",
    "quick_roundup",
})


class HumanReviewRequest(BaseModel):
    """Schema for submitting a human review."""

    story_id: str = Field(..., min_length=1, max_length=256, description="Story identifier")
    score: int = Field(..., ge=1, le=5, description="Human score (1-5)")
    style_direction: str = Field(
        default="balanced",
        min_length=1,
        max_length=64,
        description="Editorial style direction",
    )
    notes: str = Field(default="", max_length=4096, description="Review notes")

    @field_validator("style_direction")
    @classmethod
    def validate_style_direction(cls, v: str) -> str:
        if v not in _VALID_STYLE_DIRECTIONS:
            raise ValueError(
                f"style_direction must be one of: {', '.join(sorted(_VALID_STYLE_DIRECTIONS))}"
            )
        return v

    @field_validator("story_id")
    @classmethod
    def validate_story_id(cls, v: str) -> str:
        if ".." in v or "/" in v or "\\" in v:
            raise ValueError("story_id must not contain path separators")
        return v


class HumanReviewResponse(BaseModel):
    """Schema for a stored human review record."""

    review_id: str
    run_id: str
    story_id: str
    score: int
    style_direction: str
    notes: str
    created_at: str


# --- Helpers ---

def _get_db_path() -> str:
    env_path = os.environ.get("GAMES_NEWS_DB_PATH", "")
    if env_path:
        return env_path
    default = _SERVICE_DIR.parent / "outputs" / "langgraph" / "mirror" / "games_news.db"
    return str(default)


def _get_reviews_file(run_output_dir: str) -> Path:
    """Resolve the human_reviews.json path for a given output directory."""
    langgraph_dir = _SERVICE_DIR.parent
    reviews_path = langgraph_dir / run_output_dir / "human_reviews.json"
    return reviews_path


def _generate_review_id(run_id: str, story_id: str) -> str:
    timestamp = datetime.now(tz=timezone(timedelta(hours=8))).strftime("%Y%m%d%H%M%S")
    raw = f"{run_id}:{story_id}:{timestamp}"
    short_hash = hashlib.sha256(raw.encode()).hexdigest()[:12]
    return f"rev_{short_hash}"


def _now_iso() -> str:
    return datetime.now(tz=timezone(timedelta(hours=8))).isoformat()


# --- Routes ---

@router.post(
    "/runs/{run_id}/human-reviews",
    response_model=HumanReviewResponse,
    status_code=201,
)
async def submit_review(
    run_id: str,
    body: HumanReviewRequest,
) -> dict[str, Any]:
    """Submit a human review for a story.

    Writes to human_reviews.json (source of truth) and the SQLite
    human_reviews table (query index). Never modifies facts, rankings,
    claims, or platform drafts.

    Returns:
        201: Created review record.
        404: Run not found.
        422: Invalid request body.
    """
    db_path = _get_db_path()
    try:
        conn = _connect_readonly(db_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Database not found: {db_path}")

    try:
        resolved = run_id if run_id and run_id != "latest" else _latest_run_id(conn)
        if not resolved:
            raise HTTPException(status_code=404, detail="No runs found in database.")

        # Get run output_dir
        run_row = conn.execute(
            "select output_dir from runs where run_id = ?",
            (resolved,),
        ).fetchone()
        if run_row is None:
            raise HTTPException(status_code=404, detail=f"Run not found: {resolved}")

        output_dir = str(run_row["output_dir"] or "")

        review_id = _generate_review_id(resolved, body.story_id)
        created_at = _now_iso()

        review_record: dict[str, Any] = {
            "review_id": review_id,
            "run_id": resolved,
            "story_id": body.story_id,
            "score": body.score,
            "style_direction": body.style_direction,
            "notes": body.notes,
            "created_at": created_at,
        }

        # 1) Write to human_reviews.json (source of truth - append)
        if output_dir:
            reviews_file = _get_reviews_file(output_dir)
            reviews_file.parent.mkdir(parents=True, exist_ok=True)
            if reviews_file.exists():
                try:
                    existing = read_json(reviews_file)
                    if isinstance(existing, list):
                        existing.append(review_record)
                    else:
                        existing = [review_record]
                    write_json(reviews_file, existing)
                except (OSError, json.JSONDecodeError):
                    write_json(reviews_file, [review_record])
            else:
                write_json(reviews_file, [review_record])

        # 2) Write to SQLite human_reviews table (query index)
        _ensure_reviews_table(db_path)
        _insert_review_record(db_path, review_record)

        return review_record
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        conn.close()


@router.get("/runs/{run_id}/human-reviews")
async def list_reviews(
    run_id: str,
) -> dict[str, Any]:
    """List human reviews for a run.

    Returns:
        200: List of review records.
    """
    db_path = _get_db_path()
    try:
        conn = _connect_readonly(db_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Database not found: {db_path}")

    try:
        resolved = run_id if run_id and run_id != "latest" else _latest_run_id(conn)
        if not resolved:
            return {
                "run_id": resolved,
                "rows": [],
                "summary": {"row_count": 0},
            }

        rows = _read_reviews_from_json(resolved)
        return {
            "run_id": resolved,
            "rows": rows,
            "summary": {"row_count": len(rows)},
        }
    finally:
        conn.close()


# --- SQLite helpers ---

def _ensure_reviews_table(db_path: str) -> None:
    """Create the human_reviews table in the SQLite mirror if it does not exist."""
    import sqlite3

    write_conn = sqlite3.connect(db_path)
    try:
        write_conn.execute("""
            create table if not exists human_reviews (
                review_id text primary key,
                run_id text not null,
                story_id text not null,
                score integer not null,
                style_direction text not null default '',
                notes text not null default '',
                created_at text not null
            )
        """)
        write_conn.commit()
    finally:
        write_conn.close()


def _insert_review_record(db_path: str, record: dict[str, Any]) -> None:
    """Insert a single review record into the SQLite human_reviews table."""
    import sqlite3

    write_conn = sqlite3.connect(db_path)
    try:
        write_conn.execute(
            """
            insert or replace into human_reviews
                (review_id, run_id, story_id, score, style_direction, notes, created_at)
            values (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["review_id"],
                record["run_id"],
                record["story_id"],
                int(record["score"]),
                str(record.get("style_direction", "")),
                str(record.get("notes", "")),
                str(record.get("created_at", "")),
            ),
        )
        write_conn.commit()
    finally:
        write_conn.close()


def _read_reviews_from_json(run_id: str) -> list[dict[str, Any]]:
    """Read human reviews from the JSON source of truth for a given run.

    Falls back to SQLite if JSON is unavailable.
    """
    db_path = _get_db_path()
    conn = _connect_readonly(db_path)
    try:
        run_row = conn.execute(
            "select output_dir from runs where run_id = ?",
            (run_id,),
        ).fetchone()
    finally:
        conn.close()

    if run_row:
        output_dir = str(run_row["output_dir"] or "")
        if output_dir:
            reviews_file = _get_reviews_file(output_dir)
            if reviews_file.exists():
                try:
                    data = read_json(reviews_file)
                    if isinstance(data, list):
                        return [r for r in data if r.get("run_id") == run_id]
                except (OSError, json.JSONDecodeError):
                    pass

    # Fallback: read from SQLite
    return _read_reviews_from_sqlite(run_id)


def _read_reviews_from_sqlite(run_id: str) -> list[dict[str, Any]]:
    """Read reviews from SQLite table as fallback."""
    db_path = _get_db_path()
    conn = _connect_readonly(db_path)
    try:
        rows = conn.execute(
            """
            select review_id, run_id, story_id, score, style_direction, notes, created_at
            from human_reviews
            where run_id = ?
            order by created_at desc
            """,
            (run_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    except Exception:
        return []
    finally:
        conn.close()
