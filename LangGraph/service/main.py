"""FastAPI application factory for the Games News internal workbench.

Serves:
    SVC-001: Run/Artifact read-only API  (routers/runs.py)
    SVC-002: Artifact content serving     (routers/artifacts.py)
    SVC-003: Human review capture         (routers/reviews.py)
    SVC-004: Read-only safety guard       (guards/readonly.py)

Usage:
    python -m service.main
    uvicorn service.main:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the service and src directories are on sys.path
_SERVICE_DIR = Path(__file__).resolve().parent
_LANGGRAPH_DIR = _SERVICE_DIR.parent
_SRC_DIR = _LANGGRAPH_DIR / "src"
for p in (_SERVICE_DIR, _LANGGRAPH_DIR, _SRC_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .guards.readonly import ReadonlyGuardMiddleware
from .routers import runs as runs_router
from .routers import artifacts as artifacts_router
from .routers import reviews as reviews_router


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""

    app = FastAPI(
        title="Games News Workbench API",
        description="Internal read-only workbench API for the Games News Crew pipeline.",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS: allow Nuxt3 dev server
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    # SVC-004: Read-only safety guard (must be added before routes)
    app.add_middleware(ReadonlyGuardMiddleware)

    # Register routers
    app.include_router(runs_router.router)
    app.include_router(artifacts_router.router)
    app.include_router(reviews_router.router)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "service.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
