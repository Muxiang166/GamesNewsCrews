"""SVC-002: Artifact content serving router.

Serves artifact content through the artifact_manifest whitelist.
Blocks path traversal and reads outside manifest boundaries.

Endpoints:
    GET /api/v1/runs/{run_id}/artifacts/{artifact_key}

Reference harness: LangGraph/harness/service_workbench/H-SVC-002-artifact-stage-browser.json
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

_SERVICE_DIR = Path(__file__).resolve().parent.parent
_SRC_DIR = _SERVICE_DIR.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from games_news_agent.persistence.agent_query import (  # noqa: E402
    _connect_readonly,
    _latest_run_id,
    list_artifacts,
)
from ..guards.readonly import validate_artifact_key  # noqa: E402

_BLOCKED_RESPONSE = {
    "detail": "Access blocked by read-only safety guard.",
    "issue_id": "SVC-004",
    "stage": "service_workbench",
}

router = APIRouter(prefix="/api/v1", tags=["artifacts"])


def _get_db_path() -> str:
    import os

    env_path = os.environ.get("GAMES_NEWS_DB_PATH", "")
    if env_path:
        return env_path

    default = _SERVICE_DIR.parent / "outputs" / "langgraph" / "mirror" / "games_news.db"
    return str(default)


_CONTENT_TYPES: dict[str, str] = {
    ".md": "text/markdown; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".jsonl": "application/x-ndjson; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".yaml": "text/yaml; charset=utf-8",
    ".yml": "text/yaml; charset=utf-8",
    ".csv": "text/csv; charset=utf-8",
}


def _get_content_type(file_path: str) -> str:
    suffix = Path(file_path).suffix.lower()
    return _CONTENT_TYPES.get(suffix, "application/octet-stream")


@router.get("/runs/{run_id}/artifacts/{artifact_key}")
async def get_artifact_content(
    run_id: str,
    artifact_key: str,
) -> Any:
    """Serve a single artifact's content.

    The artifact_key must be registered in the artifact index (SQLite artifacts table).
    Path traversal is blocked by the SVC-004 middleware and validated here as defense-in-depth.

    Returns:
        200: Raw artifact content with appropriate Content-Type.
        403: Artifact key not found in manifest or blocked by safety check.
        404: Artifact file not found on disk.
    """
    # Defense-in-depth: validate artifact_key
    is_safe, reason = validate_artifact_key(artifact_key)
    if not is_safe:
        return JSONResponse(
            status_code=403,
            content={
                "detail": reason,
                "issue_id": "SVC-004",
                "stage": "service_workbench",
            },
        )

    db_path = _get_db_path()
    try:
        conn = _connect_readonly(db_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Database not found: {db_path}")

    try:
        resolved = run_id if run_id and run_id != "latest" else _latest_run_id(conn)
        if not resolved:
            raise HTTPException(status_code=404, detail="No runs found in database.")

        # Look up the artifact key in the artifact index
        artifacts = list_artifacts(conn, run_id=resolved)
        matched = [
            a for a in artifacts if a.get("artifact_key") == artifact_key
        ]

        if not matched:
            return JSONResponse(
                status_code=403,
                content={
                    "detail": f"Artifact key '{artifact_key}' is not registered in the artifact manifest for run {resolved}.",
                    "issue_id": "SVC-004",
                    "stage": "service_workbench",
                },
            )

        artifact = matched[0]
        file_path = artifact.get("path", "")
        if not file_path:
            raise HTTPException(
                status_code=404,
                detail=f"Artifact '{artifact_key}' has no file path in manifest.",
            )

        # Resolve path relative to the LangGraph directory
        langgraph_dir = _SERVICE_DIR.parent
        artifact_path = langgraph_dir / file_path

        # Defense-in-depth: verify resolved path stays within LangGraph directory
        try:
            artifact_path = artifact_path.resolve()
            langgraph_dir.resolve()
            artifact_path.relative_to(langgraph_dir.resolve())
        except ValueError:
            return JSONResponse(
                status_code=403,
                content={
                    "detail": f"Artifact path '{file_path}' resolves outside the project directory.",
                    "issue_id": "SVC-004",
                    "stage": "service_workbench",
                },
            )

        if not artifact_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Artifact file not found: {file_path}",
            )

        # Read and return content
        from fastapi.responses import PlainTextResponse

        content = artifact_path.read_text(encoding="utf-8")
        content_type = _get_content_type(file_path)

        return PlainTextResponse(
            content=content,
            media_type=content_type,
            headers={
                "X-Artifact-Key": artifact_key,
                "X-Artifact-Stage": artifact.get("stage", ""),
            },
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        conn.close()
