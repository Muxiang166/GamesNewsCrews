# Nuxt3 Internal Workbench Guide

**Version**: 0.1.0
**Purpose**: Internal review workbench for the Games News Crew pipeline.

## Architecture

The Nuxt3 SPA is a pure frontend that communicates exclusively through the FastAPI REST API (`http://localhost:8000/api/v1`). It holds no business logic and performs no filesystem access.

## Setup

```bash
cd LangGraph/workbench
npm install
npm run dev        # http://localhost:5173
```

## Configuration

All configurable parameters are in `ParamSettings.vue` and default to the project-standard values:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `api_base_url` | `http://localhost:8000` | FastAPI service address |
| `db_path` | `outputs/langgraph/mirror/games_news.db` | SQLite mirror path (for direct CLI use) |
| `theme_section` | (empty = all) | Filter by game platform section |
| `limit` | 20 | Results per page |

Parameters are NOT hardcoded — they read from the settings panel and can be changed at any time.

## Pages

### `/` — Run List

Displays all historical runs in a table:
- Run ID, status (completed/running/failed), start/end time
- Open notification count (clickable, jumps to notifications view)
- Click a row to navigate to run detail

### `/runs/[id]` — Run Detail

Shows run summary with:
- Run metadata (output_dir, status, schema_version)
- Table counts: candidates, documents, claims, stories, platform_posts, etc.
- Open notifications with severity badges
- Quality flags (short titles, empty documents, open notifications)
- Navigation tabs: Stories | Candidates | Artifacts | Notifications

### `/runs/[id]/stories` — Story Browser

Story cards display:
- Title, score, theme_section, selection_status
- Filter bar: theme_section dropdown
- Each card links to artifact content

### `/runs/[id]/artifacts` — Artifact Stage Browser

- Left panel: 10 artifact stages as a tree
- Click a stage to expand and show artifact files
- Click a file to preview content in the right panel
- Content types supported: text/markdown, application/json (syntax-highlighted)

## Components

### ParamSettings.vue

Settings panel (collapsible sidebar or modal):
- Text inputs with labels and current values
- "Apply" button to update, "Reset" button to restore defaults
- Values persist in localStorage

### ActionButtons.vue

Action bar at top of run list:
- "Refresh" — reloads run list from API
- "New Run" — reserved (triggers pipeline run via API when implemented)
- "Export Reviews" — downloads human review data as JSON

## Future
- Vector DB integration for preference learning
- Shadow vs deterministic comparison view
- Source health trend charts
