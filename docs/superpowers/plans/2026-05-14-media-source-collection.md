# Media Source Collection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first live collection path for four authoritative games media sources: IGN, PC Gamer, GameSpot, and Gamersky.

**Architecture:** Keep `SearchCollector` deterministic and source-first. Use a stdlib HTTP fetcher, a collector registry that routes RSS and listing pages to normalized `SearchCandidate` records, then apply hard 48-hour filtering plus a memory freshness gate before any LLM/RAG work.

**Tech Stack:** Python stdlib `urllib`, `html.parser`, existing Pydantic schemas, `unittest`, LangGraph node state.

---

### Task 1: HTTP Fetcher

**Files:**
- Create: `LangGraph/src/games_news_agent/fetching.py`
- Test: `LangGraph/tests/test_live_collection_building_blocks.py`

- [x] **Step 1: Write the failing test**

```python
result = HttpFetcher(open_url=fake_open, timeout=4.0).fetch_text("https://example.invalid/feed.xml")
self.assertTrue(result.ok)
self.assertEqual(result.status_code, 200)
self.assertEqual(result.text, "<rss>ok</rss>")
```

- [x] **Step 2: Run test to verify it fails**

Run: `D:\Anaconda\envs\gamesnewscrew\python.exe -m unittest LangGraph.tests.test_live_collection_building_blocks -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'games_news_agent.collectors.registry'`.

- [x] **Step 3: Write minimal implementation**

Create `FetchResult` and `HttpFetcher.fetch_text()` with injected `open_url`, user-agent, status, content-type, text decoding, and recoverable error return.

- [x] **Step 4: Run test to verify it passes**

Run: `D:\Anaconda\envs\gamesnewscrew\python.exe -m unittest LangGraph.tests.test_live_collection_building_blocks -v`

Expected: 4 tests pass.

### Task 2: Collector Registry

**Files:**
- Create: `LangGraph/src/games_news_agent/collectors/registry.py`
- Create: `LangGraph/src/games_news_agent/collectors/listing.py`
- Modify: `LangGraph/config/sources.yaml`
- Test: `LangGraph/tests/test_live_collection_building_blocks.py`

- [x] **Step 1: Write failing tests for RSS and listing collection**

```python
result = collect_from_source(source, fetcher=_StaticFetcher(rss), discovered_at=now, query="games")
self.assertEqual(result.candidates[0]["source_id"], "ign")

result = collect_from_source(source, fetcher=_StaticFetcher(html, "text/html"), discovered_at=now, query="games")
self.assertEqual(result.candidates[0]["published_at"], "2026-05-14T20:13:00+08:00")
```

- [x] **Step 2: Implement registry routing**

Route `media_rss` to `RssCollector` and `media_listing` to `ListingCollector`; skip unsupported planned collectors during bulk live collection.

- [x] **Step 3: Wire four source entries**

Set:
- `ign`: `media_rss`, `http://feeds.ign.com/ign/all`
- `gamespot`: `media_rss`, `https://www.gamespot.com/feeds/news/`
- `pc_gamer`: `media_rss`, `https://www.pcgamer.com/rss/`
- `gamergen`: `media_listing`, `https://www.gamersky.com/news/`

### Task 3: Memory Freshness Gate

**Files:**
- Create: `LangGraph/src/games_news_agent/memory.py`
- Modify: `LangGraph/src/games_news_agent/ranking.py`
- Modify: `LangGraph/src/games_news_agent/schemas.py`
- Test: `LangGraph/tests/test_live_collection_building_blocks.py`

- [x] **Step 1: Write failing memory behavior test**

```python
accepted, rejected = filter_and_rank_candidates(
    [late_repost, current_update],
    sources,
    now=now,
    lookback_hours=48,
    memory_records=memory_records,
)
self.assertEqual(rejected[0]["reject_reason"], "late_repost_without_current_update")
self.assertEqual(accepted[0]["memory_status"], "follow_up_update")
```

- [x] **Step 2: Implement minimal memory classification**

Classify candidates as `new_story`, `known_recent_story`, `follow_up_update`, or `late_repost` using `memory_key`, `first_seen_at`, and `is_current_update`/tags.

- [x] **Step 3: Integrate with ranking**

Reject `late_repost` before scoring; keep `follow_up_update` and add `memory-follow-up-update` to heat reasons.

### Task 4: LangGraph Live Search Branch

**Files:**
- Modify: `LangGraph/src/games_news_agent/nodes.py`
- Test: full unittest suite, compileall, dry-run, and a live run attempt.

- [x] **Step 1: Replace live `NotImplementedError`**

Call `collect_from_sources()`, write `raw_sources.jsonl`, `candidates.json`, `rejected_candidates.json`, and `collector_errors.json`.

- [ ] **Step 2: Run full verification**

Run:
`D:\Anaconda\envs\gamesnewscrew\python.exe -m unittest discover -s LangGraph\tests -v`

Run:
`D:\Anaconda\envs\gamesnewscrew\python.exe -m compileall -q LangGraph\src`

Run dry-run and live-run attempts with `PYTHONPATH=D:\PythonProjects\Games_News_Crew\LangGraph\src`.
