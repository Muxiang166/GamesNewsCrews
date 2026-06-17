"""Shared test fixtures for the service test suite.

Creates a temporary SQLite mirror database with enough schema and data
to exercise all four SVC harness contracts.
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient


# ── Test data (mirrors harness/service_workbench/ fixtures) ──

SAMPLE_RUN_ID = "run_20260617_001"
SAMPLE_OUTPUT_DIR = "outputs/langgraph/v020_review"

SAMPLE_RUNS: list[dict[str, Any]] = [
    {
        "run_id": SAMPLE_RUN_ID,
        "output_dir": SAMPLE_OUTPUT_DIR,
        "status": "completed",
        "started_at": "2026-06-17T10:00:00+08:00",
        "ended_at": "2026-06-17T10:08:00+08:00",
        "schema_version": "0.1.0",
        "manifest_json": "{}",
    },
]

SAMPLE_NOTIFICATIONS: list[dict[str, Any]] = [
    {
        "run_id": SAMPLE_RUN_ID,
        "notification_id": "notif_abc",
        "severity": "warning",
        "stage": "source_collection",
        "issue_id": "SRC-001",
        "title": "Source health degraded",
        "message": "2 sources had HTTP errors.",
        "status": "open",
        "raw_json": "{}",
    },
]

SAMPLE_ARTIFACTS: list[dict[str, Any]] = [
    {
        "run_id": SAMPLE_RUN_ID,
        "artifact_key": "content_review_path",
        "path": f"{SAMPLE_OUTPUT_DIR}/artifacts_by_stage/platform_content/content_review.md",
        "stage": "platform_content",
        "exists_flag": 1,
        "size_bytes": 4096,
        "sha256": "abc123def456",
        "raw_json": "{}",
    },
]

SAMPLE_STORIES: list[dict[str, Any]] = [
    {
        "run_id": SAMPLE_RUN_ID,
        "story_id": "story_001",
        "title": "Test Story: Major Game Update",
        "theme_section": "sony",
        "status": "published",
        "selection_status": "selected",
        "story_score": 0.85,
        "publish_status": "",
        "published_at": "",
        "platform_publish_id": "",
        "raw_json": "{}",
    },
]

SAMPLE_CANDIDATES: list[dict[str, Any]] = [
    {
        "run_id": SAMPLE_RUN_ID,
        "candidate_id": "cand_001",
        "lane": "main",
        "title": "Test Candidate",
        "url": "https://example.com/news/1",
        "source_id": "psblog",
        "published_at": "2026-06-17T08:00:00+08:00",
        "observed_at": "2026-06-17T10:00:00+08:00",
        "theme_section": "sony",
        "heat_score": 0.72,
        "memory_status": "new",
        "reject_reason": "",
        "raw_json": "{}",
    },
]


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
        create table if not exists user_notifications (
            run_id text not null,
            notification_id text not null,
            severity text not null default '',
            stage text not null default '',
            issue_id text not null default '',
            title text not null default '',
            message text not null default '',
            status text not null default 'open',
            raw_json text not null default '{}',
            primary key (run_id, notification_id)
        );
        create table if not exists artifacts (
            run_id text not null,
            artifact_key text not null,
            path text not null default '',
            stage text not null default '',
            exists_flag integer not null default 0,
            size_bytes integer not null default 0,
            sha256 text not null default '',
            raw_json text not null default '{}',
            primary key (run_id, artifact_key)
        );
        create table if not exists stories (
            run_id text not null,
            story_id text not null,
            title text not null default '',
            theme_section text not null default '',
            status text not null default '',
            selection_status text not null default '',
            story_score real not null default 0.0,
            publish_status text not null default '',
            published_at text not null default '',
            platform_publish_id text not null default '',
            raw_json text not null default '{}',
            primary key (run_id, story_id)
        );
        create table if not exists candidates (
            run_id text not null,
            candidate_id text not null,
            lane text not null default '',
            title text not null default '',
            url text not null default '',
            source_id text not null default '',
            published_at text not null default '',
            observed_at text not null default '',
            theme_section text not null default '',
            heat_score real not null default 0.0,
            memory_status text not null default '',
            reject_reason text not null default '',
            raw_json text not null default '{}',
            primary key (run_id, candidate_id)
        );
        create table if not exists raw_sources (run_id text, source_id text, raw_json text, primary key (run_id, source_id));
        create table if not exists documents (run_id text, document_id text, title text, candidate_url text, raw_json text, primary key (run_id, document_id));
        create table if not exists evidence_chunks (run_id text, chunk_id text, raw_json text, primary key (run_id, chunk_id));
        create table if not exists claims (run_id text, claim_id text, raw_json text, primary key (run_id, claim_id));
        create table if not exists claim_verifications (run_id text, claim_id text, raw_json text, primary key (run_id, claim_id));
        create table if not exists story_candidates (run_id text, story_id text, title text, theme_section text, raw_json text, primary key (run_id, story_id));
        create table if not exists platform_posts (run_id text, post_id text, raw_json text, primary key (run_id, post_id));
    """
    )


def _insert_test_data(conn: sqlite3.Connection) -> None:
    for run in SAMPLE_RUNS:
        conn.execute(
            "insert or replace into runs values (?, ?, ?, ?, ?, ?, ?)",
            (run["run_id"], run["output_dir"], run["status"],
             run["started_at"], run["ended_at"], run["schema_version"], run["manifest_json"]),
        )
    for n in SAMPLE_NOTIFICATIONS:
        conn.execute(
            "insert or replace into user_notifications values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (n["run_id"], n["notification_id"], n["severity"], n["stage"],
             n["issue_id"], n["title"], n["message"], n["status"], n["raw_json"]),
        )
    for a in SAMPLE_ARTIFACTS:
        conn.execute(
            "insert or replace into artifacts values (?, ?, ?, ?, ?, ?, ?, ?)",
            (a["run_id"], a["artifact_key"], a["path"], a["stage"],
             a["exists_flag"], a["size_bytes"], a["sha256"], a["raw_json"]),
        )
    for s in SAMPLE_STORIES:
        conn.execute(
            "insert or replace into stories values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (s["run_id"], s["story_id"], s["title"], s["theme_section"],
             s["status"], s["selection_status"], s["story_score"],
             s["publish_status"], s["published_at"], s["platform_publish_id"], s["raw_json"]),
        )
    for c in SAMPLE_CANDIDATES:
        conn.execute(
            "insert or replace into candidates values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (c["run_id"], c["candidate_id"], c["lane"], c["title"], c["url"],
             c["source_id"], c["published_at"], c["observed_at"],
             c["theme_section"], c["heat_score"], c["memory_status"],
             c["reject_reason"], c["raw_json"]),
        )
    conn.commit()


@pytest.fixture
def temp_db_path(tmp_path: Path) -> str:
    """Create a temporary SQLite mirror database with test schema and data."""
    db_path = str(tmp_path / "games_news.db")
    conn = sqlite3.connect(db_path)
    _create_schema(conn)
    _insert_test_data(conn)
    conn.close()
    return db_path


@pytest.fixture
def temp_output_dir(tmp_path: Path) -> str:
    """Create a temporary output directory mimicking a real run."""
    output_dir = tmp_path / "outputs" / "langgraph" / "v020_review"
    artifacts_dir = output_dir / "artifacts_by_stage" / "platform_content"
    artifacts_dir.mkdir(parents=True)

    # Write a sample artifact file
    content_review = artifacts_dir / "content_review.md"
    content_review.write_text("# Content Review\n\nThis is a test review.", encoding="utf-8")

    return str(output_dir)


@pytest.fixture
def client(temp_db_path: str, temp_output_dir: str, monkeypatch) -> TestClient:
    """Create a FastAPI TestClient wired to the temporary database."""
    monkeypatch.setenv("GAMES_NEWS_DB_PATH", temp_db_path)

    from service.main import app
    return TestClient(app)


@pytest.fixture
def client_no_db(monkeypatch) -> TestClient:
    """Create a TestClient pointing to a non-existent database."""
    monkeypatch.setenv("GAMES_NEWS_DB_PATH", "/nonexistent/path/games_news.db")
    from service.main import app
    return TestClient(app)
