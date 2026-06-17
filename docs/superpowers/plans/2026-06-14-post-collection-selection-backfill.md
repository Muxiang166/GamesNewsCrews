# Post-Collection Selection Backfill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make post-collection selection auditable and allow theme-specific document-fetch backfill when a section has enough candidates but too few story candidates.

**Architecture:** Keep LangGraph as the workflow. Add a lightweight diagnostic module that compares stage artifacts by theme, then add a controlled backfill node that fetches more documents from underfilled theme pools. Long-lookback runs remain offline evaluation harnesses, not daily briefing inputs.

**Tech Stack:** Python `unittest`, existing LangGraph nodes, JSON artifacts, current `HttpFetcher`, current candidate/theme/story modules.

---

## File Structure

- Create `LangGraph/src/games_news_agent/selection_diagnostics.py`
  - Builds `selection_stage_diagnostics.json` from candidates, theme pool, context packs, claims, story candidates and theme sections.
- Create `LangGraph/tests/test_selection_diagnostics.py`
  - Unit tests for per-theme stage counts and bottleneck labels.
- Modify `LangGraph/src/games_news_agent/nodes.py`
  - Write `selection_stage_diagnostics.json` after `score_heat`.
  - Later add optional `backfill_documents_for_underfilled_sections` node.
- Modify `LangGraph/src/games_news_agent/schemas.py`
  - Add paths and state keys for selection diagnostics and backfill results.
- Modify `LangGraph/src/games_news_agent/run.py`
  - Add CLI flags for backfill and long-lookback eval controls.
- Create `LangGraph/tests/test_selection_backfill.py`
  - Unit tests for section backfill candidate selection.
- Create `docs/long_lookback_eval.md`
  - Operating guide for 30-day and 60-day evaluation runs.

---

### Task 1: Selection Stage Diagnostics

**Files:**
- Create: `LangGraph/src/games_news_agent/selection_diagnostics.py`
- Create: `LangGraph/tests/test_selection_diagnostics.py`
- Modify: `LangGraph/src/games_news_agent/nodes.py`
- Modify: `LangGraph/src/games_news_agent/schemas.py`

- [x] **Step 1: Write failing tests for section stage counts**

Add this test to `LangGraph/tests/test_selection_diagnostics.py`:

```python
from __future__ import annotations

import unittest

from games_news_agent.selection_diagnostics import build_selection_stage_diagnostics


class SelectionDiagnosticsTest(unittest.TestCase):
    def test_reports_theme_drop_between_pool_and_story_candidates(self) -> None:
        theme_candidate_pool = {
            "sections": [
                {
                    "id": "nintendo",
                    "candidate_count": 34,
                    "pool_count": 20,
                    "fetch_selected_count": 4,
                    "candidates": [
                        {"url": f"https://example.invalid/switch-{index}", "theme_section": "nintendo"}
                        for index in range(20)
                    ],
                }
            ]
        }
        context_packs = [
            {"candidate": {"url": f"https://example.invalid/switch-{index}", "theme_section": "nintendo"}}
            for index in range(4)
        ]
        claim_verifications = [
            {"metadata": {"candidate_url": f"https://example.invalid/switch-{index}", "theme_section": "nintendo"}}
            for index in range(4)
        ]
        story_candidates = [
            {"id": f"story_{index}", "url": f"https://example.invalid/switch-{index}", "theme_section": "nintendo"}
            for index in range(3)
        ]
        theme_sections = {
            "sections": [
                {"id": "nintendo", "candidate_count": 3, "pool_count": 3, "selected_count": 3}
            ]
        }

        report = build_selection_stage_diagnostics(
            theme_candidate_pool=theme_candidate_pool,
            context_packs=context_packs,
            claim_verifications=claim_verifications,
            story_candidates=story_candidates,
            theme_sections=theme_sections,
        )

        nintendo = report["sections"]["nintendo"]
        self.assertEqual(nintendo["candidate_count"], 34)
        self.assertEqual(nintendo["pool_count"], 20)
        self.assertEqual(nintendo["fetch_selected_count"], 4)
        self.assertEqual(nintendo["context_pack_count"], 4)
        self.assertEqual(nintendo["claim_verification_count"], 4)
        self.assertEqual(nintendo["story_candidate_count"], 3)
        self.assertEqual(nintendo["final_selected_count"], 3)
        self.assertEqual(nintendo["primary_bottleneck"], "document_fetch_budget")
```

- [x] **Step 2: Run test to verify it fails**

Run:

```powershell
$env:PYTHONPATH='LangGraph/src'
D:\Anaconda\envs\gamesnewscrew\python.exe -m unittest LangGraph.tests.test_selection_diagnostics
```

Expected: fail with `ModuleNotFoundError` or missing `build_selection_stage_diagnostics`.

- [x] **Step 3: Implement `selection_diagnostics.py`**

Create `LangGraph/src/games_news_agent/selection_diagnostics.py`:

```python
from __future__ import annotations

from typing import Any


SECTION_IDS = ("sony", "nintendo", "microsoft", "pc", "supplemental")


def _candidate_url(value: dict[str, Any]) -> str:
    return str(value.get("url") or value.get("candidate_url") or "").strip()


def _candidate_theme(value: dict[str, Any]) -> str:
    return str(value.get("theme_section") or value.get("metadata", {}).get("theme_section") or "supplemental")


def _context_pack_counts(context_packs: list[dict[str, Any]]) -> dict[str, int]:
    counts = {section_id: 0 for section_id in SECTION_IDS}
    for pack in context_packs:
        candidate = pack.get("candidate", {}) if isinstance(pack, dict) else {}
        if isinstance(candidate, dict):
            section = _candidate_theme(candidate)
            counts[section if section in counts else "supplemental"] += 1
    return counts


def _claim_counts(claim_verifications: list[dict[str, Any]]) -> dict[str, int]:
    counts = {section_id: 0 for section_id in SECTION_IDS}
    for claim in claim_verifications:
        metadata = claim.get("metadata", {}) if isinstance(claim, dict) else {}
        if isinstance(metadata, dict):
            section = _candidate_theme({"metadata": metadata})
            counts[section if section in counts else "supplemental"] += 1
    return counts


def _story_counts(story_candidates: list[dict[str, Any]]) -> dict[str, int]:
    counts = {section_id: 0 for section_id in SECTION_IDS}
    for story in story_candidates:
        if not isinstance(story, dict):
            continue
        section = _candidate_theme(story)
        counts[section if section in counts else "supplemental"] += 1
    return counts


def _final_counts(theme_sections: dict[str, Any]) -> dict[str, int]:
    counts = {section_id: 0 for section_id in SECTION_IDS}
    sections = theme_sections.get("sections", []) if isinstance(theme_sections, dict) else []
    for section in sections:
        if not isinstance(section, dict):
            continue
        section_id = str(section.get("id") or "supplemental")
        counts[section_id if section_id in counts else "supplemental"] = int(section.get("selected_count") or 0)
    return counts


def _bottleneck(item: dict[str, int]) -> str:
    if item["pool_count"] > item["fetch_selected_count"]:
        return "document_fetch_budget"
    if item["fetch_selected_count"] > item["context_pack_count"]:
        return "document_fetch_failure"
    if item["context_pack_count"] > item["claim_verification_count"]:
        return "claim_extraction_or_verification"
    if item["claim_verification_count"] > item["story_candidate_count"]:
        return "story_publishability_filter"
    if item["story_candidate_count"] > item["final_selected_count"]:
        return "final_ranking_limit"
    return "no_drop_detected"


def build_selection_stage_diagnostics(
    *,
    theme_candidate_pool: dict[str, Any],
    context_packs: list[dict[str, Any]],
    claim_verifications: list[dict[str, Any]],
    story_candidates: list[dict[str, Any]],
    theme_sections: dict[str, Any],
) -> dict[str, Any]:
    context_counts = _context_pack_counts(context_packs)
    claim_counts = _claim_counts(claim_verifications)
    story_counts = _story_counts(story_candidates)
    final_counts = _final_counts(theme_sections)

    sections: dict[str, dict[str, int | str]] = {}
    for section in theme_candidate_pool.get("sections", []):
        if not isinstance(section, dict):
            continue
        section_id = str(section.get("id") or "supplemental")
        if section_id not in SECTION_IDS:
            section_id = "supplemental"
        item = {
            "candidate_count": int(section.get("candidate_count") or 0),
            "pool_count": int(section.get("pool_count") or 0),
            "fetch_selected_count": int(section.get("fetch_selected_count") or 0),
            "context_pack_count": context_counts.get(section_id, 0),
            "claim_verification_count": claim_counts.get(section_id, 0),
            "story_candidate_count": story_counts.get(section_id, 0),
            "final_selected_count": final_counts.get(section_id, 0),
        }
        sections[section_id] = {**item, "primary_bottleneck": _bottleneck(item)}

    return {"version": "0.1.0", "sections": sections}
```

- [x] **Step 4: Run test to verify it passes**

Run:

```powershell
$env:PYTHONPATH='LangGraph/src'
D:\Anaconda\envs\gamesnewscrew\python.exe -m unittest LangGraph.tests.test_selection_diagnostics
```

Expected: pass.

- [x] **Step 5: Wire diagnostics into `score_heat`**

In `LangGraph/src/games_news_agent/nodes.py`, import:

```python
from .selection_diagnostics import build_selection_stage_diagnostics
```

Inside `score_heat`, after `theme_sections` is built and before returning:

```python
selection_stage_diagnostics = build_selection_stage_diagnostics(
    theme_candidate_pool=state.get("theme_candidate_pool", {}),
    context_packs=state.get("context_packs", []),
    claim_verifications=state.get("claim_verifications", []),
    story_candidates=story_candidates,
    theme_sections=theme_sections,
)
selection_stage_diagnostics_path = output_dir / "selection_stage_diagnostics.json"
write_json(selection_stage_diagnostics_path, selection_stage_diagnostics)
```

Add to return:

```python
"selection_stage_diagnostics": selection_stage_diagnostics,
"selection_stage_diagnostics_path": str(selection_stage_diagnostics_path),
```

- [x] **Step 6: Add schema keys**

In `LangGraph/src/games_news_agent/schemas.py`, add:

```python
selection_stage_diagnostics: dict[str, Any]
selection_stage_diagnostics_path: str
```

- [x] **Step 7: Run focused tests**

Run:

```powershell
$env:PYTHONPATH='LangGraph/src'
D:\Anaconda\envs\gamesnewscrew\python.exe -m unittest LangGraph.tests.test_selection_diagnostics LangGraph.tests.test_evidence_pipeline
```

Expected: all tests pass.

---

### Task 2: Theme Fetch Backfill Planner

**Files:**
- Create: `LangGraph/src/games_news_agent/selection_backfill.py`
- Create: `LangGraph/tests/test_selection_backfill.py`

- [x] **Step 1: Write failing tests**

Create `LangGraph/tests/test_selection_backfill.py`:

```python
from __future__ import annotations

import unittest

from games_news_agent.selection_backfill import select_backfill_candidates


class SelectionBackfillTest(unittest.TestCase):
    def test_selects_unfetched_main_candidates_from_underfilled_section(self) -> None:
        theme_candidate_pool = {
            "sections": [
                {
                    "id": "nintendo",
                    "candidates": [
                        {
                            "title": f"Switch 2 story {index}",
                            "url": f"https://example.invalid/switch-{index}",
                            "candidate_lane": "main",
                            "candidate_type": "news",
                            "heat_score": 100 - index,
                            "document_fetch_selected": index < 4,
                        }
                        for index in range(10)
                    ],
                }
            ]
        }
        diagnostics = {
            "sections": {
                "nintendo": {
                    "story_candidate_count": 3,
                    "primary_bottleneck": "document_fetch_budget",
                }
            }
        }

        selected = select_backfill_candidates(
            theme_candidate_pool=theme_candidate_pool,
            selection_stage_diagnostics=diagnostics,
            min_story_candidates_per_section=5,
            max_backfill_fetch_per_section=3,
            max_total_backfill_fetch=10,
        )

        self.assertEqual([item["url"] for item in selected], [
            "https://example.invalid/switch-4",
            "https://example.invalid/switch-5",
            "https://example.invalid/switch-6",
        ])
```

- [x] **Step 2: Run test to verify it fails**

Run:

```powershell
$env:PYTHONPATH='LangGraph/src'
D:\Anaconda\envs\gamesnewscrew\python.exe -m unittest LangGraph.tests.test_selection_backfill
```

Expected: fail with missing module/function.

- [x] **Step 3: Implement planner**

Create `LangGraph/src/games_news_agent/selection_backfill.py`:

```python
from __future__ import annotations

from typing import Any


PUBLISHABLE_CANDIDATE_TYPES = {"news", "rumor", "platform_price", "hardware_platform", "review_score"}


def _score(candidate: dict[str, Any]) -> float:
    value = candidate.get("heat_score", 0)
    return float(value) if isinstance(value, (int, float)) else 0.0


def select_backfill_candidates(
    *,
    theme_candidate_pool: dict[str, Any],
    selection_stage_diagnostics: dict[str, Any],
    min_story_candidates_per_section: int = 5,
    max_backfill_fetch_per_section: int = 8,
    max_total_backfill_fetch: int = 20,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    diagnostics = selection_stage_diagnostics.get("sections", {})
    for section in theme_candidate_pool.get("sections", []):
        if not isinstance(section, dict):
            continue
        section_id = str(section.get("id") or "")
        section_diag = diagnostics.get(section_id, {})
        if int(section_diag.get("story_candidate_count") or 0) >= min_story_candidates_per_section:
            continue
        if section_diag.get("primary_bottleneck") != "document_fetch_budget":
            continue

        candidates = [
            dict(candidate)
            for candidate in section.get("candidates", [])
            if isinstance(candidate, dict)
            and not candidate.get("document_fetch_selected")
            and str(candidate.get("candidate_lane") or "main") == "main"
            and str(candidate.get("candidate_type") or "news") in PUBLISHABLE_CANDIDATE_TYPES
        ]
        candidates.sort(key=_score, reverse=True)
        for candidate in candidates[: max_backfill_fetch_per_section]:
            selected.append(candidate)
            if len(selected) >= max_total_backfill_fetch:
                return selected
    return selected
```

- [x] **Step 4: Run test to verify it passes**

Run:

```powershell
$env:PYTHONPATH='LangGraph/src'
D:\Anaconda\envs\gamesnewscrew\python.exe -m unittest LangGraph.tests.test_selection_backfill
```

Expected: pass.

---

### Task 3: Optional Backfill Node

**Files:**
- Modify: `LangGraph/src/games_news_agent/nodes.py`
- Modify: `LangGraph/src/games_news_agent/graph.py`
- Modify: `LangGraph/src/games_news_agent/run.py`
- Modify: `LangGraph/src/games_news_agent/schemas.py`
- Test: `LangGraph/tests/test_evidence_pipeline.py`

- [x] **Step 1: Add CLI flags**

In `LangGraph/src/games_news_agent/run.py`, add parser arguments:

```python
parser.add_argument("--run-selection-backfill", action="store_true")
parser.add_argument("--selection-backfill-min-stories", type=int, default=5)
parser.add_argument("--selection-backfill-limit", type=int, default=20)
```

Add these keys to the initial state:

```python
"run_selection_backfill": args.run_selection_backfill,
"selection_backfill_min_stories": args.selection_backfill_min_stories,
"selection_backfill_limit": args.selection_backfill_limit,
```

- [x] **Step 2: Add state keys**

In `LangGraph/src/games_news_agent/schemas.py`, add:

```python
run_selection_backfill: bool
selection_backfill_min_stories: int
selection_backfill_limit: int
selection_backfill_candidates: list[dict[str, Any]]
selection_backfill_candidates_path: str
```

- [x] **Step 3: Add a backfill node skeleton**

In `LangGraph/src/games_news_agent/nodes.py`, create:

```python
def plan_selection_backfill(state: PipelineState) -> dict[str, Any]:
    output_dir = _output_dir(state)
    if not state.get("run_selection_backfill"):
        candidates: list[dict[str, Any]] = []
    else:
        candidates = select_backfill_candidates(
            theme_candidate_pool=state.get("theme_candidate_pool", {}),
            selection_stage_diagnostics=state.get("selection_stage_diagnostics", {}),
            min_story_candidates_per_section=int(state.get("selection_backfill_min_stories", 5)),
            max_total_backfill_fetch=int(state.get("selection_backfill_limit", 20)),
        )
    path = output_dir / "selection_backfill_candidates.json"
    write_json(path, candidates)
    return {
        "selection_backfill_candidates": candidates,
        "selection_backfill_candidates_path": str(path),
        "notes": _append_note(state, f"Planned {len(candidates)} selection backfill candidates."),
    }
```

This first node only plans backfill candidates. The second phase can fetch and rerun claim/story generation after the diagnostic is stable.

- [x] **Step 4: Wire node after first `score_heat`**

In `LangGraph/src/games_news_agent/graph.py`, place `plan_selection_backfill` after `score_heat` and before review-writing nodes. Do not rerun story selection yet.

- [x] **Step 5: Add node test**

Add to `LangGraph/tests/test_evidence_pipeline.py`:

```python
def test_plan_selection_backfill_writes_candidates_for_underfilled_section(self) -> None:
    with TemporaryDirectory() as tmp:
        state = {
            "output_dir": tmp,
            "run_selection_backfill": True,
            "selection_backfill_min_stories": 5,
            "selection_backfill_limit": 3,
            "theme_candidate_pool": {
                "sections": [
                    {
                        "id": "nintendo",
                        "candidates": [
                            {
                                "title": f"Switch 2 story {index}",
                                "url": f"https://example.invalid/switch-{index}",
                                "candidate_lane": "main",
                                "candidate_type": "news",
                                "heat_score": 100 - index,
                                "document_fetch_selected": index < 4,
                            }
                            for index in range(10)
                        ],
                    }
                ]
            },
            "selection_stage_diagnostics": {
                "sections": {
                    "nintendo": {
                        "story_candidate_count": 3,
                        "primary_bottleneck": "document_fetch_budget",
                    }
                }
            },
            "notes": [],
        }

        update = plan_selection_backfill(state)

        self.assertEqual(len(update["selection_backfill_candidates"]), 3)
        self.assertTrue(Path(update["selection_backfill_candidates_path"]).exists())
```

- [x] **Step 6: Run focused tests**

Run:

```powershell
$env:PYTHONPATH='LangGraph/src'
D:\Anaconda\envs\gamesnewscrew\python.exe -m unittest LangGraph.tests.test_selection_backfill LangGraph.tests.test_evidence_pipeline
```

Expected: pass.

---

### Task 4: Long-Lookback Evaluation Guide

**Files:**
- Create: `docs/long_lookback_eval.md`

- [x] **Step 1: Create evaluation guide**

Create `docs/long_lookback_eval.md`:

```markdown
# Long-Lookback Evaluation Guide

Use 30-day and 60-day runs to evaluate post-collection ranking, backfill and event-burst behavior. Do not use these runs as daily briefing output.

## 30-Day Collection

```powershell
D:\Anaconda\envs\gamesnewscrew\python.exe LangGraph\main.py --lookback-hours 720 --topic games --document-fetch-limit 20 --theme-candidate-pool-limit 300 --output-dir outputs\langgraph\eval_30d_collection --memory-path outputs\langgraph\memory\eval_30d_candidate_memory.json
```

## 60-Day Collection

```powershell
D:\Anaconda\envs\gamesnewscrew\python.exe LangGraph\main.py --lookback-hours 1440 --topic games --document-fetch-limit 30 --theme-candidate-pool-limit 500 --output-dir outputs\langgraph\eval_60d_collection --memory-path outputs\langgraph\memory\eval_60d_candidate_memory.json
```

## Review Checklist

- Compare `source_theme_counts.json` with `theme_candidate_pool.json`.
- Compare `theme_candidate_pool.sections[].fetch_selected_count` with `story_candidates.json`.
- Check `selection_stage_diagnostics.json` once implemented.
- Check if event-burst days produce enough Nintendo/Sony/Microsoft/PC story candidates.
- Check if old news and late reposts are separated from current updates.
```

- [x] **Step 2: Run markdown presence check**

Run:

```powershell
rg "30-Day Collection|selection_stage_diagnostics|lookback-hours 720" docs/long_lookback_eval.md
```

Expected: all terms appear.

---

### Task 5: Full Verification

**Files:**
- No new files.

- [x] **Step 1: Run full test suite**

Run:

```powershell
$env:PYTHONPATH='LangGraph/src'
D:\Anaconda\envs\gamesnewscrew\python.exe -m unittest discover -s LangGraph\tests
```

Expected: all tests pass.

- [x] **Step 2: Run dry-run with diagnostics**

Run:

```powershell
D:\Anaconda\envs\gamesnewscrew\python.exe LangGraph\main.py --dry-run --lookback-hours 48 --topic games --document-fetch-limit 20 --output-dir outputs\langgraph\selection_diagnostics_dry_run --memory-path outputs\langgraph\selection_diagnostics_dry_run\candidate_memory.json
```

Expected files:

- `outputs\langgraph\selection_diagnostics_dry_run\selection_stage_diagnostics.json`
- `outputs\langgraph\selection_diagnostics_dry_run\theme_candidate_pool.json`
- `outputs\langgraph\selection_diagnostics_dry_run\story_candidates.json`

- [ ] **Step 3: Run long-lookback collection only after user approval**

Use the commands in `docs/long_lookback_eval.md`. These runs may collect a lot of data and should not be started automatically during normal coding turns.
