"""SVC-001: Run/Artifact read-only API router.

Endpoints:
    GET /api/v1/health
    GET /api/v1/runs
    GET /api/v1/runs/{run_id}
    GET /api/v1/runs/{run_id}/stories
    GET /api/v1/runs/{run_id}/candidates
    GET /api/v1/runs/{run_id}/notifications
    GET /api/v1/runs/{run_id}/artifacts
    GET /api/v1/runs/{run_id}/quality-flags

All queries go through persistence/agent_query.py whitelist.
Reference harness: LangGraph/harness/service_workbench/H-SVC-001-run-list-api.json
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query

_SERVICE_DIR = Path(__file__).resolve().parent.parent
_SRC_DIR = _SERVICE_DIR.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from games_news_agent.persistence.agent_query import (  # noqa: E402
    _connect_readonly,
    _latest_run_id,
    _limit,
    get_run_summary,
    list_runs,
    list_stories,
    list_candidates,
    list_notifications,
    list_artifacts,
    list_quality_flags,
)

router = APIRouter(prefix="/api/v1", tags=["runs"])


def _get_db_path() -> str:
    """Resolve the SQLite mirror database path.

    Checks environment variable GAMES_NEWS_DB_PATH first, then falls back
    to the default location relative to the LangGraph directory.
    """
    import os

    env_path = os.environ.get("GAMES_NEWS_DB_PATH", "")
    if env_path:
        return env_path

    default = _SERVICE_DIR.parent / "outputs" / "langgraph" / "mirror" / "games_news.db"
    return str(default)


@router.get("/health")
async def health() -> dict[str, Any]:
    """Health check endpoint."""
    return {"status": "ok", "version": "0.1.0"}


@router.get("/runs")
async def get_runs(
    limit: int = Query(default=20, ge=1, le=500, description="Max runs to return"),
) -> dict[str, Any]:
    """List recent runs with open notification counts.

    Returns:
        200: Run list with open_notification_count per run.
    """
    db_path = _get_db_path()
    try:
        conn = _connect_readonly(db_path)
    except FileNotFoundError:
        return {
            "schema_version": "agent_db_query_v0",
            "query_type": "runs",
            "db_path": db_path,
            "rows": [],
            "summary": {"row_count": 0, "note": "No database found at the configured path."},
        }
    try:
        runs = list_runs(conn, limit=limit)
        # Enrich each run with open notification count
        for run in runs:
            run_id = run.get("run_id", "")
            if run_id:
                open_count = conn.execute(
                    "select count(*) from user_notifications where run_id = ? and status != 'closed'",
                    (run_id,),
                ).fetchone()
                run["open_notification_count"] = int(open_count[0]) if open_count else 0
            else:
                run["open_notification_count"] = 0
        return {
            "schema_version": "agent_db_query_v0",
            "query_type": "runs",
            "db_path": db_path,
            "rows": runs,
            "summary": {"row_count": len(runs)},
        }
    finally:
        conn.close()


@router.get("/runs/{run_id}")
async def get_run(
    run_id: str,
) -> dict[str, Any]:
    """Get run summary including table counts and open notifications.

    Use 'latest' as run_id to get the most recent run.
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

        summary = get_run_summary(conn, run_id=resolved)
        return {
            "schema_version": "agent_db_query_v0",
            "query_type": "summary",
            "run_id": resolved,
            "db_path": db_path,
            "rows": [summary["run"]],
            "summary": {
                "run": summary["run"],
                "table_counts": summary.get("table_counts", {}),
                "open_notifications": summary.get("open_notifications", 0),
            },
        }
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    finally:
        conn.close()


@router.get("/runs/{run_id}/stories")
async def get_stories(
    run_id: str,
    theme_section: str = Query(default="", description="Filter by theme section"),
    limit: int = Query(default=20, ge=1, le=500),
) -> dict[str, Any]:
    """List stories for a run, optionally filtered by theme_section."""
    db_path = _get_db_path()
    try:
        conn = _connect_readonly(db_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Database not found: {db_path}")

    try:
        resolved = run_id if run_id and run_id != "latest" else _latest_run_id(conn)
        rows = list_stories(
            conn, run_id=resolved, theme_section=theme_section, limit=limit
        )
        return {
            "schema_version": "agent_db_query_v0",
            "query_type": "stories",
            "run_id": resolved,
            "db_path": db_path,
            "rows": rows,
            "summary": {"row_count": len(rows)},
        }
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    finally:
        conn.close()


@router.get("/runs/{run_id}/candidates")
async def get_candidates(
    run_id: str,
    lane: str = Query(default="", description="Filter by lane (main/supplemental)"),
    theme_section: str = Query(default="", description="Filter by theme section"),
    source_id: str = Query(default="", description="Filter by source ID"),
    limit: int = Query(default=20, ge=1, le=500),
) -> dict[str, Any]:
    """List candidates for a run with optional filters."""
    db_path = _get_db_path()
    try:
        conn = _connect_readonly(db_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Database not found: {db_path}")

    try:
        resolved = run_id if run_id and run_id != "latest" else _latest_run_id(conn)
        rows = list_candidates(
            conn,
            run_id=resolved,
            lane=lane,
            theme_section=theme_section,
            source_id=source_id,
            limit=limit,
        )
        return {
            "schema_version": "agent_db_query_v0",
            "query_type": "candidates",
            "run_id": resolved,
            "db_path": db_path,
            "rows": rows,
            "summary": {"row_count": len(rows)},
        }
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    finally:
        conn.close()


@router.get("/runs/{run_id}/notifications")
async def get_notifications(
    run_id: str,
    severity: str = Query(default="", description="Filter by severity (warning/error/info)"),
    status: str = Query(default="", description="Filter by status (open/closed)"),
    limit: int = Query(default=50, ge=1, le=500),
) -> dict[str, Any]:
    """List user notifications for a run."""
    db_path = _get_db_path()
    try:
        conn = _connect_readonly(db_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Database not found: {db_path}")

    try:
        resolved = run_id if run_id and run_id != "latest" else _latest_run_id(conn)
        rows = list_notifications(
            conn,
            run_id=resolved,
            severity=severity,
            status=status,
            limit=limit,
        )
        return {
            "schema_version": "agent_db_query_v0",
            "query_type": "notifications",
            "run_id": resolved,
            "db_path": db_path,
            "rows": rows,
            "summary": {"row_count": len(rows)},
        }
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    finally:
        conn.close()


@router.get("/runs/{run_id}/artifacts")
async def get_artifacts(
    run_id: str,
    stage: str = Query(default="", description="Filter by artifact stage"),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    """List artifact index records for a run."""
    db_path = _get_db_path()
    try:
        conn = _connect_readonly(db_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Database not found: {db_path}")

    try:
        resolved = run_id if run_id and run_id != "latest" else _latest_run_id(conn)
        rows = list_artifacts(conn, run_id=resolved, stage=stage, limit=limit)
        return {
            "schema_version": "agent_db_query_v0",
            "query_type": "artifacts",
            "run_id": resolved,
            "db_path": db_path,
            "rows": rows,
            "summary": {"row_count": len(rows)},
        }
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    finally:
        conn.close()


@router.get("/runs/{run_id}/quality-flags")
async def get_quality_flags(
    run_id: str,
    min_title_chars: int = Query(default=8, ge=1, le=100, description="Minimum title length to flag"),
    limit: int = Query(default=50, ge=1, le=500),
) -> dict[str, Any]:
    """List quality flags for a run (short titles, empty documents, open notifications)."""
    db_path = _get_db_path()
    try:
        conn = _connect_readonly(db_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Database not found: {db_path}")

    try:
        resolved = run_id if run_id and run_id != "latest" else _latest_run_id(conn)
        rows = list_quality_flags(
            conn, run_id=resolved, min_title_chars=min_title_chars, limit=limit
        )
        return {
            "schema_version": "agent_db_query_v0",
            "query_type": "quality-flags",
            "run_id": resolved,
            "db_path": db_path,
            "rows": rows,
            "summary": {"row_count": len(rows)},
        }
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    finally:
        conn.close()
