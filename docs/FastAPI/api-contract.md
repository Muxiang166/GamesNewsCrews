# FastAPI Workbench API Contract

**Version**: 0.1.0
**Base URL**: `http://localhost:8000/api/v1`

## Overview

The FastAPI service provides a read-only query surface over the Games News SQLite mirror. All data access goes through the whitelist query API (`persistence/agent_query.py`). Write operations are limited to human review records only.

## Security

- All endpoints are read-only except `POST /runs/{run_id}/human-reviews`
- Path traversal, arbitrary SQL, and publish actions are blocked by SVC-004 middleware
- Artifact content serving validates keys against `artifact_manifest.json`

## Endpoints

### Health

```
GET /api/v1/health
```

**Response** `200`:
```json
{
  "status": "ok",
  "version": "0.1.0"
}
```

---

### List Runs

```
GET /api/v1/runs?limit=20
```

**Response** `200`:
```json
{
  "schema_version": "agent_db_query_v0",
  "query_type": "runs",
  "rows": [
    {
      "run_id": "run_20260617_001",
      "output_dir": "outputs/langgraph/v020_review",
      "status": "completed",
      "started_at": "2026-06-17T10:00:00+08:00",
      "ended_at": "2026-06-17T10:08:00+08:00",
      "open_notification_count": 1
    }
  ],
  "summary": { "row_count": 1 }
}
```

---

### Get Run Summary

```
GET /api/v1/runs/{run_id}
```

Use `latest` as run_id to get the most recent run.

**Response** `200`:
```json
{
  "schema_version": "agent_db_query_v0",
  "query_type": "summary",
  "run_id": "run_20260617_001",
  "rows": [{ "run_id": "...", "output_dir": "...", "status": "completed", ... }],
  "summary": {
    "run": { ... },
    "table_counts": { "candidates": 45, "stories": 12, ... },
    "open_notifications": 2
  }
}
```

---

### List Stories

```
GET /api/v1/runs/{run_id}/stories?theme_section=sony&limit=20
```

**Response** `200`:
```json
{
  "schema_version": "agent_db_query_v0",
  "query_type": "stories",
  "run_id": "run_20260617_001",
  "rows": [
    {
      "story_id": "story_001",
      "title": "...",
      "theme_section": "sony",
      "status": "published",
      "selection_status": "selected",
      "story_score": 0.85
    }
  ],
  "summary": { "row_count": 1 }
}
```

---

### List Candidates

```
GET /api/v1/runs/{run_id}/candidates?lane=main&theme_section=sony&source_id=psblog&limit=20
```

**Response** `200`:
```json
{
  "schema_version": "agent_db_query_v0",
  "query_type": "candidates",
  "run_id": "run_20260617_001",
  "rows": [
    {
      "candidate_id": "cand_001",
      "title": "...",
      "url": "https://...",
      "source_id": "psblog",
      "lane": "main",
      "theme_section": "sony",
      "heat_score": 0.72,
      "memory_status": "new"
    }
  ],
  "summary": { "row_count": 1 }
}
```

---

### List Notifications

```
GET /api/v1/runs/{run_id}/notifications?severity=warning&status=open&limit=50
```

**Response** `200`:
```json
{
  "schema_version": "agent_db_query_v0",
  "query_type": "notifications",
  "run_id": "run_20260617_001",
  "rows": [
    {
      "notification_id": "notif_abc",
      "severity": "warning",
      "stage": "source_collection",
      "issue_id": "SRC-001",
      "title": "Source health degraded",
      "message": "...",
      "status": "open"
    }
  ],
  "summary": { "row_count": 1 }
}
```

---

### List Artifacts

```
GET /api/v1/runs/{run_id}/artifacts?stage=platform_content&limit=100
```

**Response** `200`:
```json
{
  "schema_version": "agent_db_query_v0",
  "query_type": "artifacts",
  "run_id": "run_20260617_001",
  "rows": [
    {
      "artifact_key": "content_review_path",
      "path": "outputs/langgraph/v020_review/artifacts_by_stage/platform_content/content_review.md",
      "stage": "platform_content",
      "exists_flag": 1,
      "size_bytes": 4096,
      "sha256": "abc123..."
    }
  ],
  "summary": { "row_count": 1 }
}
```

---

### Get Artifact Content

```
GET /api/v1/runs/{run_id}/artifacts/{artifact_key}
```

Returns the raw file content with appropriate Content-Type header.

**Response** `200`: file content (text/markdown, application/json, etc.)

**Response** `403`: artifact key not in manifest
**Response** `404`: file not found on disk

---

### Quality Flags

```
GET /api/v1/runs/{run_id}/quality-flags?min_title_chars=8&limit=50
```

**Response** `200`:
```json
{
  "schema_version": "agent_db_query_v0",
  "query_type": "quality-flags",
  "run_id": "run_20260617_001",
  "rows": [
    {
      "flag_type": "short_title",
      "table": "stories",
      "object_id": "story_005",
      "title": "DLC"
    }
  ],
  "summary": { "row_count": 1 }
}
```

---

### Submit Human Review

```
POST /api/v1/runs/{run_id}/human-reviews
Content-Type: application/json

{
  "story_id": "story_001",
  "score": 4,
  "style_direction": "more_game_content_first",
  "notes": "保留游戏本体更新，下沉泛讨论。"
}
```

**Response** `201`:
```json
{
  "review_id": "rev_20260617_001",
  "run_id": "run_20260617_001",
  "story_id": "story_001",
  "score": 4,
  "style_direction": "more_game_content_first",
  "notes": "保留游戏本体更新，下沉泛讨论。",
  "created_at": "2026-06-17T15:30:00+08:00"
}
```

---

### List Human Reviews

```
GET /api/v1/runs/{run_id}/human-reviews
```

**Response** `200`:
```json
{
  "run_id": "run_20260617_001",
  "rows": [
    {
      "review_id": "rev_20260617_001",
      "story_id": "story_001",
      "score": 4,
      "style_direction": "more_game_content_first",
      "notes": "保留游戏本体更新，下沉泛讨论。",
      "created_at": "2026-06-17T15:30:00+08:00"
    }
  ],
  "summary": { "row_count": 1 }
}
```

---

## Error Responses

All errors follow this format:

```json
{
  "detail": "Human-readable error description",
  "issue_id": "SVC-004",
  "stage": "service_workbench"
}
```

HTTP status codes used:
- `200` — success
- `201` — review created
- `400` — invalid request body
- `403` — blocked by security guard
- `404` — run/artifact not found
- `422` — validation error
- `500` — internal server error
