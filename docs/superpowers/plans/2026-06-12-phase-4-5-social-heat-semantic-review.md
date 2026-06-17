# Phase 4.5 Social Heat And Semantic Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add auditable social heat evidence, source dominance diagnostics, semantic review inputs, and theme-aware reranking before Phase 5 layout work.

**Architecture:** Keep LangGraph workflow as the primary orchestration layer. Add deterministic modules that produce JSON artifacts first; use bounded ReAct only for local tool routing and access diagnosis; use reflection only for reviewing completed run artifacts and recommending next-run changes.

**Tech Stack:** Python standard library, existing LangGraph package, unittest, JSON artifacts, existing OpenAI-compatible `llm_provider.py` when optional LLM execution is introduced.

---

## Agent Pattern Decision

This plan uses a mixed mature-agent architecture:

- `Workflow` is the default for collection and evaluation. Every stage must have stable inputs, outputs, artifacts, tests, and progress reporting.
- `Bounded ReAct` is allowed only inside tool-routing steps. It can choose among known providers such as `public_search`, `browser_sidecar`, `manual_import`, `api_or_search_service`, existing collectors, and existing parsers. It cannot invent sources, browse arbitrary URLs, bypass login, or change fact status.
- `Reflection` is allowed only after a run has produced artifacts. It reviews `social_heat_observations.json`, `source_dominance_audit.json`, `content_quality_report.json`, `editorial_judgment_requests.json`, and human review labels to recommend next-run changes.

The project should not become a free-form ReAct crawler. The goal is an auditable multi-agent workflow where agents diagnose, route, review, and explain deterministic tool outputs.

## Build-vs-Buy Gate

Every new feature in this phase must pass a short toolchain decision before implementation:

- Use deterministic project code first when the feature defines game-news-specific policy, fact boundaries, heat evidence, source dominance, or publication safety.
- Use an existing library behind an adapter when the feature is generic infrastructure: browser automation, structured LLM calls, tracing/evals, vector search, HTML cleanup, or crawler scheduling.
- Keep the LangGraph workflow as the orchestration backbone. External libraries must return existing JSON artifacts instead of owning the pipeline state.
- Keep new dependencies optional until a live run proves they improve recall, precision, cost, or observability.

Initial decisions:

- `SocialHeatProvider`: custom contract first; provider adapters later.
- `Bilibili/Steam public search`: stdlib HTTP first; Playwright only if ordinary HTTP is blocked or JS-empty.
- `Weibo/Tieba/Reddit/X/YouTube`: defer automatic HTTP as default; evaluate browser sidecar, API, or search-service adapters.
- `Xiaoheihe`: manual import first; login/app automation requires explicit human approval.
- `RelevanceClassifierAgent`: deterministic relevance check first; RAG/LLM classifier later consumes only filtered observations.
- `RAG`: SQLite/metadata/BM25 first; LlamaIndex/vector store only after story/evidence IDs and human review labels are stable.

## File Structure

- Create `LangGraph/src/games_news_agent/agent_patterns.py`: constants and helpers for allowed agent modes, access modes, action types, and approval requirements.
- Create `LangGraph/tests/test_agent_patterns.py`: unit tests that prevent unsafe agent decisions such as arbitrary browsing, login bypass, or direct fact mutation.
- Create `LangGraph/src/games_news_agent/social_heat.py`: platform-agnostic observation schema helpers, provider request builder, observation merger.
- Create `LangGraph/tests/test_social_heat.py`: unit tests for observation schema, platform access modes, and heat validity hints.
- Modify `LangGraph/src/games_news_agent/discussion_probe_provider.py`: map current provider output into the social heat observation shape without changing network behavior.
- Modify `LangGraph/src/games_news_agent/nodes.py`: write `social_heat_observations.json` and pass observations into discussion reports.
- Modify `LangGraph/src/games_news_agent/schemas.py`: add state paths for social heat observations.
- Create `LangGraph/src/games_news_agent/source_dominance.py`: explain source dominance as volume/fetch/language/real engagement/false heat/noise.
- Create `LangGraph/tests/test_source_dominance.py`: lock source dominance audit behavior.
- Modify `LangGraph/src/games_news_agent/content_review.py`: include source dominance and social heat summaries in the human review pack.
- Create `LangGraph/src/games_news_agent/social_heat_relevance.py`: deterministic relevance checks for social search results before any LLM/RAG semantic judgment.
- Create `LangGraph/tests/test_social_heat_relevance.py`: tests for same-game, same-platform-only, off-topic, unknown-time, and self-reference removal.
- Create `LangGraph/src/games_news_agent/semantic_review.py`: parse and normalize human semantic review labels.
- Create `LangGraph/tests/test_semantic_review.py`: validate review label schema and safe fallback behavior.
- Modify `LangGraph/src/games_news_agent/editorial_judgment.py`: add optional result application helpers that produce suggestions only.
- Modify `LangGraph/src/games_news_agent/story_sections.py`: add source caps, theme balance guards, and off-topic risk demotion.
- Modify `docs/roadmap.md` and `docs/retrieval_strategy.md`: keep implementation notes current after each task.

---

### Task 0: Agent Pattern Guardrails

**Files:**
- Create: `LangGraph/src/games_news_agent/agent_patterns.py`
- Test: `LangGraph/tests/test_agent_patterns.py`

- [ ] **Step 1: Write failing tests for allowed modes and unsafe actions**

Create tests that assert:

```python
def test_agent_decision_rejects_arbitrary_browse_and_login_bypass():
    decision = validate_agent_decision({
        "agent_mode": "react",
        "action_type": "tool_call_request",
        "target_tool": "arbitrary_browser",
        "params": {"url": "https://unknown.example"},
        "requires_human_approval": False,
    })
    assert decision["status"] == "rejected"
    assert "tool_not_whitelisted" in decision["risk_flags"]

def test_agent_decision_requires_approval_for_login_or_fact_mutation():
    decision = validate_agent_decision({
        "agent_mode": "react",
        "action_type": "tool_call_request",
        "target_tool": "browser_sidecar",
        "params": {"access_mode": "login_required"},
        "requires_human_approval": False,
    })
    assert decision["status"] == "needs_human_approval"
    assert "login_required" in decision["risk_flags"]
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```powershell
$env:PYTHONPATH='LangGraph/src'; D:\Anaconda\envs\gamesnewscrew\python.exe -m unittest LangGraph.tests.test_agent_patterns
```

Expected: import failure for `games_news_agent.agent_patterns`.

- [ ] **Step 3: Implement minimal guardrail helpers**

Implement:

```python
def validate_agent_decision(decision: dict[str, Any]) -> dict[str, Any]:
    """Return normalized allow/reject/needs_human_approval decision for an agent action."""

def allowed_agent_modes() -> list[str]:
    """Return workflow, react, and reflection."""

def whitelisted_agent_tools() -> list[str]:
    """Return deterministic provider, parser, retrieval, review, and sidecar tool names."""
```

Rules:

- `workflow` may run deterministic nodes.
- `react` may only choose whitelisted tools.
- `reflection` may only create review recommendations.
- `login_required`, publication, source expansion, and fact-state mutation require human approval.
- Unknown tools, arbitrary browsing, and direct fact mutation are rejected.

- [ ] **Step 4: Verify guardrail tests pass**

Run:

```powershell
$env:PYTHONPATH='LangGraph/src'; D:\Anaconda\envs\gamesnewscrew\python.exe -m unittest LangGraph.tests.test_agent_patterns
```

Expected: all tests pass.

### Task 1: SocialHeatProvider Artifact Contract

2026-06-13 update:

The first provider contract must include platform access profiles before adding more crawling code. Low-frequency public probes showed:

- `bilibili` and `steam_discussions` are the first automatic `public_search` targets.
- `youtube` and `x` should start as `browser_sidecar` or `api_or_search_service` candidates because ordinary HTTP may only return JS shells.
- `weibo`, `tieba`, and `reddit` should not be treated as stable public HTTP providers yet because they return visitor/blocked responses in basic probes.
- `xiaoheihe` should start as `manual_import`; later browser/app-assisted collection needs explicit human approval.

This task therefore builds both the normalized observation schema and a static platform access profile. Provider implementations must write status instead of hiding failures.

Implementation status:

- `social_heat.py` now normalizes observations, builds summaries, exposes no-login-first platform profiles, and converts existing `DiscussionProbeProvider` reports.
- `probe_discussions` writes `social_heat_observations.json` with summary, platform profiles, first-batch public search platforms, and observations.
- `score_heat` writes `source_dominance_audit.json` without changing ranking.
- `content_review.md` now shows social heat observation summary and source dominance diagnostics for human review.
- `heat_validity_hint=game_discussion` means "game-context discussion signal", not "same event verified". Bilibili public search can return game-related but unrelated results, so the next implementation step must add relevance classification or human `same_event` labels before boosting ranking.

**Files:**
- Create: `LangGraph/src/games_news_agent/social_heat.py`
- Test: `LangGraph/tests/test_social_heat.py`

- [ ] **Step 1: Write the failing schema tests**

Create tests that assert a Bilibili public search observation and a Xiaoheihe manual observation normalize to the same keys:

```python
def test_normalize_social_heat_observation_keeps_access_mode_and_engagement():
    observation = normalize_social_heat_observation({
        "candidate_url": "https://example.invalid/story",
        "candidate_title": "Switch 2 price debate",
        "platform": "bilibili",
        "access_mode": "public_search",
        "query": "Switch 2 涨价",
        "status": "ok",
        "result_count": 8,
        "engagement_signals": {"comments": 120, "danmaku": 60},
        "top_results": [{"title": "Switch 2 涨价讨论", "url": "https://bilibili.com/video/BV1"}],
    })
    assert observation["heat_validity_hint"] == "game_discussion"
    assert observation["engagement_signals"]["comments"] == 120
```

- [ ] **Step 2: Run the new tests and confirm failure**

Run:

```powershell
$env:PYTHONPATH='LangGraph/src'; D:\Anaconda\envs\gamesnewscrew\python.exe -m unittest LangGraph.tests.test_social_heat
```

Expected: import failure for `games_news_agent.social_heat`.

- [ ] **Step 3: Implement the minimal social heat helpers**

Implement:

```python
def normalize_social_heat_observation(raw: dict[str, Any]) -> dict[str, Any]:
    """Return a complete normalized observation with allowed enum values."""

def build_social_heat_summary(observations: list[dict[str, Any]]) -> dict[str, Any]:
    """Return counts by platform, access mode, status, and heat validity hint."""

def infer_heat_validity_hint(observation: dict[str, Any]) -> str:
    """Return game_discussion, general_social_heat, or unclear from evidence text and engagement fields."""

def default_social_platform_profiles() -> list[dict[str, Any]]:
    """Return the no-login-first access profile for social heat providers."""
```

Allowed values:

- `access_mode`: `public_search`, `browser_sidecar`, `manual_import`, `api_or_search_service`
- `status`: `ok`, `blocked`, `login_required`, `manual_required`, `error`
- `heat_validity_hint`: `game_discussion`, `general_social_heat`, `unclear`

Initial platform defaults:

- `bilibili`: `public_search`, `zh_cn`, automatic first batch.
- `steam_discussions`: `public_search`, `global`, automatic first batch.
- `youtube`: `browser_sidecar`, `global`, later.
- `x`: `browser_sidecar`, `global`, later.
- `weibo`: `browser_sidecar`, `zh_cn`, later.
- `tieba`: `browser_sidecar`, `zh_cn`, later.
- `reddit`: `api_or_search_service`, `en_global`, later.
- `xiaoheihe`: `manual_import`, `zh_cn`, later.

- [ ] **Step 4: Verify the tests pass**

Run:

```powershell
$env:PYTHONPATH='LangGraph/src'; D:\Anaconda\envs\gamesnewscrew\python.exe -m unittest LangGraph.tests.test_social_heat
```

Expected: all tests pass.

---

### Task 2: Persist Social Heat Observations

**Files:**
- Modify: `LangGraph/src/games_news_agent/discussion_probe_provider.py`
- Modify: `LangGraph/src/games_news_agent/nodes.py`
- Modify: `LangGraph/src/games_news_agent/schemas.py`
- Test: `LangGraph/tests/test_discussion_probe_provider.py`

- [ ] **Step 1: Add failing test for artifact conversion**

Assert current provider observations can be converted into `social_heat_observations.json` with `platform`, `access_mode`, `status`, `result_count`, and `heat_validity_hint`.

- [ ] **Step 2: Add node output fields**

Add state keys:

```python
social_heat_observations: list[dict[str, Any]]
social_heat_observations_path: str
social_heat_summary: dict[str, Any]
```

- [ ] **Step 3: Write the artifact in `probe_discussions`**

After provider observations are built, normalize them and write:

```text
outputs/langgraph/<run>/social_heat_observations.json
```

- [ ] **Step 4: Verify targeted and full tests**

Run:

```powershell
$env:PYTHONPATH='LangGraph/src'; D:\Anaconda\envs\gamesnewscrew\python.exe -m unittest LangGraph.tests.test_discussion_probe_provider LangGraph.tests.test_social_heat
$env:PYTHONPATH='LangGraph/src'; D:\Anaconda\envs\gamesnewscrew\python.exe -m unittest discover -s LangGraph\tests
```

Expected: all tests pass.

---

### Task 3: SourceDominanceAudit

**Files:**
- Create: `LangGraph/src/games_news_agent/source_dominance.py`
- Create: `LangGraph/tests/test_source_dominance.py`
- Modify: `LangGraph/src/games_news_agent/nodes.py`
- Modify: `LangGraph/src/games_news_agent/content_quality.py`
- Modify: `LangGraph/src/games_news_agent/content_review.py`

- [ ] **Step 1: Write failing audit tests**

Create samples where `gamergen` dominates due to volume only, and where it dominates with real engagement. Expected audit reasons:

```python
["volume_advantage", "language_advantage", "false_heat_advantage"]
["volume_advantage", "real_engagement_advantage"]
```

- [ ] **Step 2: Implement `build_source_dominance_audit`**

Function signature:

```python
def build_source_dominance_audit(state: dict[str, Any]) -> dict[str, Any]:
    """Explain source dominance from existing pipeline artifacts without changing ranking."""
```

Output keys:

- `summary`
- `sources`
- `dominant_source_id`
- `dominant_source_share`
- `risk_flags`
- `recommended_actions`

- [ ] **Step 3: Persist `source_dominance_audit.json`**

Write it after `score_heat` or inside `validate_content_quality`, then link it from `briefing.md` and `content_review.md`.

- [ ] **Step 4: Verify dominance is explanatory, not punitive**

The audit should not directly alter story ranking in this task. It only explains why source dominance happened.

---

### Task 3.5: Deterministic Social Heat Relevance Gate

**Files:**
- Create: `LangGraph/src/games_news_agent/social_heat_relevance.py`
- Create: `LangGraph/tests/test_social_heat_relevance.py`
- Modify: `LangGraph/src/games_news_agent/nodes.py`
- Modify: `LangGraph/src/games_news_agent/schemas.py`

- [x] **Step 1: Write failing tests for same-event guardrails**

Create tests where:

```python
def test_self_reference_does_not_create_same_event_match():
    result = classify_social_heat_result(
        candidate={
            "title": "示例线索：玩家游戏梗图刷屏",
            "url": "https://example.invalid/story",
            "theme_section": "microsoft",
        },
        observation={
            "platform": "bilibili",
            "query": "示例线索：玩家游戏梗图刷屏",
            "top_results": [
                {"title": "生活搞笑聊天截图", "url": "https://www.bilibili.com/video/BV1"}
            ],
            "evidence_texts": ["示例线索：玩家游戏梗图刷屏 生活搞笑聊天截图 评论"],
        },
    )
    assert result["deterministic_status"] == "off_topic"
    assert "self_reference_removed" in result["reasons"]
```

```python
def test_same_game_unclear_event_requires_time_hint_before_boost():
    result = classify_social_heat_result(
        candidate={
            "title": "Switch 2 price debate",
            "url": "https://example.invalid/story",
            "theme_section": "nintendo",
        },
        observation={
            "platform": "bilibili",
            "top_results": [
                {"title": "Switch 2 价格讨论 最近一天", "url": "https://www.bilibili.com/video/BV2"}
            ],
            "evidence_texts": ["Switch 2 价格讨论 最近一天 评论 弹幕"],
        },
    )
    assert result["deterministic_status"] in {"likely_same_event", "same_game_unclear_event"}
    assert result["time_hint_status"] == "within_window"
```

- [x] **Step 2: Implement deterministic classifier**

Function signatures:

```python
def classify_social_heat_result(candidate: dict[str, Any], observation: dict[str, Any]) -> dict[str, Any]:
    """Classify one social heat observation without LLM or RAG."""

def build_social_heat_relevance_checks(
    candidates: list[dict[str, Any]],
    observations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return deterministic relevance checks for social heat observations."""
```

Allowed statuses:

- `likely_same_event`
- `same_game_unclear_event`
- `same_platform_only`
- `off_topic`
- `unknown`

The classifier must remove candidate title and query text before matching. It must not use `heat_validity_hint=game_discussion` as a same-event proof.

- [x] **Step 3: Persist relevance checks**

Write:

```text
outputs/langgraph/<run>/social_heat_relevance_checks.json
```

Include summary counts by deterministic status and time hint status.

- [x] **Step 4: Leave RAG/LLM semantic interface**

Create request shape but do not execute LLM by default:

```json
{
  "request_id": "semantic_relevance_1",
  "candidate_url": "https://example.invalid/switch-2-price",
  "observation_id": "social_heat_1",
  "deterministic_status": "same_game_unclear_event",
  "candidate": {},
  "observation": {},
  "evidence_context_ids": [],
  "questions": ["same_event", "same_game", "within_48h", "old_news", "marketing_or_clickbait"]
}
```

Future RAG-backed classifier writes `semantic_relevance_results.json` with `same_event`, `same_game`, `within_48h`, `confidence`, `evidence_ids`, and `missing_evidence`. It cannot add URLs or fact claims.

2026-06-13 implementation note:

- Added `LangGraph/src/games_news_agent/social_heat_relevance.py` and `LangGraph/tests/test_social_heat_relevance.py`.
- `probe_discussions` now writes `social_heat_relevance_checks.json`, `semantic_relevance_requests.json`, and `semantic_relevance_results.json`.
- `content_review.md` now summarizes deterministic social relevance checks.
- Ranking remains unchanged until live-run calibration confirms the relevance gate is useful.

---

### Task 4: Human Semantic Review Labels

**Files:**
- Create: `LangGraph/src/games_news_agent/semantic_review.py`
- Create: `LangGraph/tests/test_semantic_review.py`
- Modify: `LangGraph/src/games_news_agent/content_review.py`

- [ ] **Step 1: Write failing parser tests**

The parser should accept:

```json
{
  "story_id": "story_1",
  "game_relevance": "core_game_news",
  "same_event": "yes",
  "heat_validity": "game_discussion",
  "publishability": "publishable",
  "style_fit": 4,
  "review_notes": "Good player-discussion story."
}
```

Invalid or missing values should normalize to `needs_human_review`.

- [ ] **Step 2: Implement semantic review normalizer**

Function signature:

```python
def normalize_human_semantic_review(raw: dict[str, Any]) -> dict[str, Any]:
    """Return a complete human semantic review record with safe fallback labels."""
```

- [ ] **Step 3: Extend `human_review_template.json`**

Add fields:

- `game_relevance`
- `same_event`
- `heat_validity`
- `publishability`
- `style_fit`
- `review_notes`

- [ ] **Step 4: Verify content review output**

Run a dry-run and confirm `content_review.md` describes how to score semantic quality.

---

### Task 5: Optional EditorialJudgmentAgent Result Application

**Files:**
- Modify: `LangGraph/src/games_news_agent/editorial_judgment.py`
- Modify: `LangGraph/src/games_news_agent/nodes.py`
- Modify: `LangGraph/src/games_news_agent/run.py`
- Test: `LangGraph/tests/test_editorial_judgment.py`

- [ ] **Step 1: Add failing tests for non-mutating suggestions**

Given one LLM result:

```json
{
  "request_id": "editorial_judgment_1",
  "game_relevance": "off_topic",
  "publishability": "reject",
  "heat_validity": "general_social_heat",
  "confidence": 0.9,
  "reason": "Company founder social controversy, not game news.",
  "risk_flags": ["company_name_false_positive"]
}
```

Expected output is an `editorial_judgment_suggestions.json` item with `suggested_action=reject_or_demote`, but original stories remain unchanged.

- [ ] **Step 2: Add CLI flags**

Add:

```text
--run-editorial-judgment-agent
--editorial-judgment-limit
```

Default: disabled.

- [ ] **Step 3: Run optional LLM only when enabled**

Use existing `run_llm_json_requests` with the request schema. If LLM fails, write empty results and keep deterministic pipeline unchanged.

- [ ] **Step 4: Verify no fact mutation**

Tests must assert LLM output cannot add `source_urls`, cannot change `claim_verifications`, and cannot mark a rejected fact as verified.

---

### Task 6: Theme-Aware Reranking Guards

**Files:**
- Modify: `LangGraph/src/games_news_agent/story_sections.py`
- Modify: `LangGraph/src/games_news_agent/story_ranking.py`
- Test: `LangGraph/tests/test_story_sections.py`
- Test: `LangGraph/tests/test_story_ranking.py`

- [ ] **Step 1: Add tests for non-game demotion and source caps**

Create stories where one source owns 8 of 10 top scores and one story has `off_topic_risk`. Expected:

- off-topic risk story is not selected unless forced manual review.
- final Top 10 does not exceed configured soft source cap unless there are not enough alternatives.

- [ ] **Step 2: Add scoring inputs**

Use existing fields:

- `discussion_score`
- `discussion_level`
- `source_id`
- `candidate_type`
- `editorial_judgment_suggestion`
- `source_language`

- [ ] **Step 3: Implement soft caps**

Use soft caps instead of hard rejection:

- First pass: select best story per theme while respecting source diversity.
- Second pass: fill remaining slots by score.
- If alternatives are unavailable, allow cap overflow and record `cap_overflow_reason`.

- [ ] **Step 4: Verify live reviewability**

Ensure `theme_sections.json` records why a story was selected or skipped.

---

### Task 7: Live Validation Run

**Files:**
- Read: `outputs/langgraph/<run>/content_quality_report.json`
- Read: `outputs/langgraph/<run>/source_dominance_audit.json`
- Read: `outputs/langgraph/<run>/social_heat_observations.json`
- Read: `outputs/langgraph/<run>/editorial_judgment_requests.json`
- Read: `outputs/langgraph/<run>/content_review.md`

- [ ] **Step 1: Run small live validation**

Run:

```powershell
D:\Anaconda\envs\gamesnewscrew\python.exe LangGraph\main.py --lookback-hours 48 --topic games --document-fetch-limit 20 --output-dir outputs\langgraph\phase_4_5_social_heat_live --memory-path outputs\langgraph\memory\candidate_memory.json --run-discussion-probe-provider --discussion-probe-provider-platform-limit 2
```

- [ ] **Step 2: Check success criteria**

Pass conditions:

- `social_heat_observations.json` exists and has platform/access mode/status counts.
- `source_dominance_audit.json` explains whether dominance is volume, real engagement, false heat, or noise.
- `editorial_judgment_requests.json` includes high-risk ambiguous candidates.
- `content_review.md` shows human semantic review fields.
- `content_quality_report.json` no longer hides heat weakness under generic story score.

- [ ] **Step 3: Decide next branch**

If social heat observations are mostly blocked or login-required, prioritize manual/browser sidecar.  
If observations are valid but ranking remains poor, prioritize Task 6 reranking.  
If non-game content still enters final stories, prioritize Task 5 editorial judgment application and stronger candidate gate tests.
