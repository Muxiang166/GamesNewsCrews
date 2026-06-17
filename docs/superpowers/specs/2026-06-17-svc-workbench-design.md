# SVC Workbench Design Spec

**Date**: 2026-06-17
**Status**: approved → implementing
**Scope**: SVC-001 FastAPI Run/Artifact API, SVC-002 Nuxt3 Internal Workbench, SVC-003 Human Review Capture, SVC-004 Read-only Safety Guard

## 1. Architecture

```
LangGraph/workbench/   (Nuxt3 SPA :5173)
  │ fetch(/api/v1/...)
  ▼
LangGraph/service/     (FastAPI :8000)
  │ import
  ▼
persistence/agent_query.py   (只读白名单查询)
persistence/sqlite_mirror.py (SQLite 镜像)
io.py                        (JSON 读写)
```

FastAPI and Nuxt3 are independently deployable. FastAPI imports the existing `agent_query` module directly; Nuxt3 is a pure presentation layer that calls the FastAPI REST API.

## 2. SVC-001 FastAPI Run/Artifact API

### Endpoints

| Method | Path | Description | Backing |
|--------|------|-------------|---------|
| GET | `/api/v1/health` | Health check | — |
| GET | `/api/v1/runs` | Run list with open_notification_count | `agent_query.list_runs()` |
| GET | `/api/v1/runs/{run_id}` | Run summary (table_counts, notifications) | `agent_query.get_run_summary()` |
| GET | `/api/v1/runs/{run_id}/stories` | Stories list (?theme_section=) | `agent_query.list_stories()` |
| GET | `/api/v1/runs/{run_id}/candidates` | Candidates list (?lane=&source_id=) | `agent_query.list_candidates()` |
| GET | `/api/v1/runs/{run_id}/notifications` | Notifications (?severity=&status=) | `agent_query.list_notifications()` |
| GET | `/api/v1/runs/{run_id}/artifacts` | Artifact index (?stage=) | `agent_query.list_artifacts()` |
| GET | `/api/v1/runs/{run_id}/quality-flags` | Quality flags | `agent_query.list_quality_flags()` |
| GET | `/api/v1/runs/{run_id}/artifacts/{key}` | Single artifact content | artifact_manifest → filesystem read |

### Key Behaviors
- Empty `run_id` auto-resolves to latest run
- `limit` default 20, max 500
- Response format: `{ schema_version, query_type, rows, summary }`
- Error format: `{ detail: string, issue_id?: string }`

## 3. SVC-004 Read-only Safety Guard

FastAPI middleware executing before all routes:

- **Path traversal**: Reject `../`, `%2e%2e`, absolute paths in artifact keys
- **SQL injection**: Reject `POST /sql` and any body containing raw SQL
- **Publish block**: Reject `POST /runs/{id}/publish`
- **Artifact whitelist**: Artifact key must exist in `artifact_manifest.json`
- **HTTP method restrict**: Allow only GET + POST (human-reviews only)

Rejection response: `403 {"detail": "...", "issue_id": "SVC-004", "stage": "service_workbench"}`

## 4. SVC-002 Nuxt3 Internal Workbench

### Routes

| Route | Component | Content |
|-------|-----------|---------|
| `/` | RunList.vue | Run list table: run_id, status, time, notification count |
| `/runs/[id]` | RunDetail.vue | Run summary: table_counts, notifications, quality-flags |
| `/runs/[id]/stories` | StoryBrowser.vue | Story cards, filterable by theme_section |
| `/runs/[id]/artifacts` | ArtifactStageBrowser.vue | Artifact tree by stage + content preview |

### Components
- **ParamSettings.vue**: db_path, api_base_url, theme_section, limit (configurable with defaults)
- **ActionButtons.vue**: Refresh, trigger new run (reserved), export review data

### Tech
- Nuxt3 + Vue3 + Tailwind CSS
- Dev server for local use; static generate for deployment

## 5. SVC-003 Human Review Capture

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/runs/{run_id}/human-reviews` | Submit review |
| GET | `/api/v1/runs/{run_id}/human-reviews` | List reviews |

### POST Body

```json
{
  "story_id": "story_001",
  "score": 4,
  "style_direction": "more_game_content_first",
  "notes": "保留游戏本体更新，下沉泛讨论。"
}
```

### Storage
1. `human_reviews.json` — source of truth (append-only, with `created_at` timestamps)
2. SQLite `human_reviews` table — query index (extending `sqlite_mirror.py`)

### Non-mutation Guarantee
Review writes never modify `stories.json`, `claims.json`, `platform_posts.json`, or `publish_status`.

## 6. Testing Strategy

| Harness | Test File | Key Assertions |
|---------|-----------|----------------|
| H-SVC-001 | `test_runs_api.py` | Run list with open_notification_count, no raw SQL |
| H-SVC-002 | `test_artifacts_api.py` | Only manifest-registered artifacts, reject path traversal |
| H-SVC-003 | `test_reviews_api.py` | POST writes review record, does not mutate fact artifacts |
| H-SVC-004 | `test_readonly_guard.py` | Reject `../`, `/sql`, `/publish` → 403/404 |

Test data reuses `harness/service_workbench/` JSON fixtures.

## 7. File Structure

```
LangGraph/service/                # FastAPI deployable
  __init__.py
  main.py                         # app factory + uvicorn entry
  routers/
    __init__.py
    runs.py                       # SVC-001
    artifacts.py                  # SVC-002
    reviews.py                    # SVC-003
  guards/
    __init__.py
    readonly.py                   # SVC-004 middleware
  tests/
    conftest.py                   # TestClient + temp SQLite fixtures
    test_runs_api.py
    test_artifacts_api.py
    test_reviews_api.py
    test_readonly_guard.py
  requirements.txt

LangGraph/workbench/              # Nuxt3 SPA
  nuxt.config.ts
  package.json
  app.vue
  pages/
    index.vue
    runs/[id].vue
    runs/[id]/stories.vue
    runs/[id]/artifacts.vue
  components/
    ParamSettings.vue
    ActionButtons.vue

docs/FastAPI/                     # API documentation
  api-contract.md
docs/Vue/                         # Frontend documentation
  workbench-guide.md
```

## 8. Spec Self-Review

- **Placeholders**: None. All endpoints, storage formats, and test assertions are explicit.
- **Consistency**: Architecture matches feature descriptions. SVC-004 middleware sits before all routes.
- **Scope**: Four SVC features are independently testable and deployable as a single service.
- **Ambiguity**: Resolved. Artifact content serving uses artifact_manifest as whitelist; human reviews use dual JSON+SQLite storage.
