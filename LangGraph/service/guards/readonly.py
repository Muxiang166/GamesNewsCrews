"""SVC-004: Read-only safety guard middleware.

Blocks:
- Path traversal in artifact keys and URL parameters
- Arbitrary SQL execution
- Publish actions
- File reads outside artifact manifest boundaries
- HTTP methods beyond GET + POST (human-reviews only)

Reference harness: LangGraph/harness/service_workbench/H-SVC-004-readonly-guard.json
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


_PATH_TRAVERSAL_PATTERN = re.compile(
    r"(?:\.\.[/\\])|(?:%2[eE]{2})|(?:%2[fF])|(?:%5[cC])",
)

_FORBIDDEN_PATHS = re.compile(
    r"^/(?:sql|publish|admin|config|env)",
)

_BLOCKED_RESPONSE: dict[str, Any] = {
    "detail": "This endpoint is blocked by the read-only safety guard.",
    "issue_id": "SVC-004",
    "stage": "service_workbench",
}

_PUBLISH_PATTERN = re.compile(r"/runs/[^/]+/publish")


def _has_path_traversal(value: str) -> bool:
    """Check if a string contains path traversal patterns."""
    decoded = unquote(str(value))
    if _PATH_TRAVERSAL_PATTERN.search(decoded):
        return True
    if ".." in decoded:
        return True
    return False


def _is_forbidden_path(path: str) -> bool:
    """Check if the request path targets a forbidden endpoint."""
    if _FORBIDDEN_PATHS.match(path):
        return True
    if _PUBLISH_PATTERN.search(path):
        return True
    return False


def validate_artifact_key(artifact_key: str) -> tuple[bool, str]:
    """Validate an artifact key for safety.

    Returns (is_safe, reason).
    """
    if not artifact_key or not artifact_key.strip():
        return False, "Empty artifact key"

    if _has_path_traversal(artifact_key):
        return False, f"Path traversal detected in artifact key: {artifact_key}"

    if "/" in artifact_key or "\\" in artifact_key:
        return False, f"Artifact key must not contain path separators: {artifact_key}"

    return True, ""


def validate_run_id(run_id: str) -> tuple[bool, str]:
    """Validate a run_id parameter for safety.

    Returns (is_safe, reason).
    """
    if not run_id or not run_id.strip():
        return False, "Empty run_id"

    if _has_path_traversal(run_id):
        return False, f"Path traversal detected in run_id: {run_id}"

    if "/" in run_id or "\\" in run_id:
        return False, f"run_id must not contain path separators: {run_id}"

    return True, ""


class ReadonlyGuardMiddleware(BaseHTTPMiddleware):
    """SVC-004 middleware that enforces read-only safety boundaries.

    Rejects:
    - Forbidden paths: /sql, /publish, /admin, /config, /env
    - Path traversal in URL parameters
    - Non-GET/POST methods
    - POST on anything except /runs/{run_id}/human-reviews
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Allow OPTIONS (CORS preflight) and HEAD (health checks) through
        if request.method in ("OPTIONS", "HEAD"):
            return await call_next(request)

        # Block forbidden paths
        if _is_forbidden_path(path):
            return JSONResponse(
                status_code=403,
                content=_BLOCKED_RESPONSE,
            )

        # Block unsupported HTTP methods
        if request.method not in ("GET", "POST", "OPTIONS", "HEAD"):
            return JSONResponse(
                status_code=403,
                content={
                    **_BLOCKED_RESPONSE,
                    "detail": f"HTTP method '{request.method}' is not allowed. Only GET and POST are permitted.",
                },
            )

        # Block POST on anything except human-reviews
        if request.method == "POST" and "/human-reviews" not in path:
            return JSONResponse(
                status_code=403,
                content={
                    **_BLOCKED_RESPONSE,
                    "detail": "POST is only allowed for /runs/{run_id}/human-reviews.",
                },
            )

        # Check path parameters for traversal
        for param_name, param_value in request.path_params.items():
            if isinstance(param_value, str) and _has_path_traversal(param_value):
                return JSONResponse(
                    status_code=403,
                    content={
                        **_BLOCKED_RESPONSE,
                        "detail": f"Path traversal detected in parameter '{param_name}'.",
                    },
                )

        # Check query parameters for traversal
        for param_name, param_value in request.query_params.items():
            if _has_path_traversal(param_value):
                return JSONResponse(
                    status_code=403,
                    content={
                        **_BLOCKED_RESPONSE,
                        "detail": f"Path traversal detected in query parameter '{param_name}'.",
                    },
                )

        return await call_next(request)
