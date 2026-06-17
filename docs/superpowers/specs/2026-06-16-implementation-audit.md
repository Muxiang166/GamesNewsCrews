# Implementation Audit Report — 2026-06-16

Synthesized from four phases of analysis: hardcoded values, roadmap alignment, interface gaps, and integration consistency.

---

## 1. CRITICAL ISSUES (must fix)

### CRIT-1: Dead conditional branch in `should_continue_after_quality_gate` renders `--run-story-cluster-review-agent` inert

**Location:** `LangGraph/src/games_news_agent/graph.py`, lines 35-48 and 146-154

**Problem:** The routing function `should_continue_after_quality_gate()` returns only `"continue"` or `"end_early"`. The graph's `add_conditional_edges` call maps three keys: `"continue"`, `"skip_review"`, and `"end_early"`. The `"skip_review"` branch targets `write_material_bundle` and is intended to allow bypassing the content review pack, but it is **unreachable** — nothing ever returns `"skip_review"`.

The CLI flag `--run-story-cluster-review-agent` is parsed, placed into `PipelineState`, but **never read by any conditional edge or node**. Its help text claims "Write content review pack after quality gate (RUN-004)" but the content review pack is always written when the quality gate passes.

**Fix:** Either (a) add the flag check inside `should_continue_after_quality_gate` to return `"skip_review"` when the flag is false, or (b) remove the `"skip_review"` branch and the inert `--run-story-cluster-review-agent` flag.

### CRIT-2: `--run-llm-source-navigator` and `--run-llm-search-expansion` use real LLM calls without per-node LLM feature gating available at the CLI level

**Location:** `LangGraph/src/games_news_agent/nodes.py` lines 398-401, 685-689, 730-749

**Problem:** When `--run-llm-source-navigator` is set, the `run_source_navigation_requests()` function makes real LLM calls via `llm_provider.py`. When `--run-llm-search-expansion` is set, the system makes real LLM calls via `run_llm_json_requests()`. However, **no warning or confirmation is printed** in dry-run mode. A user running `--dry-run` with these flags enabled may accidentally consume tokens.

**Fix:** Add a user confirmation prompt or at minimum a loud warning when LLM flags are enabled in dry-run mode.

### CRIT-3: `user_agent` defaults to `example.invalid` — real HTTP requests carry an invalid domain in the User-Agent header

**Location:** `LangGraph/src/games_news_agent/fetching.py`, line 115

**Problem:** `HttpFetcher.__init__` default `user_agent` is `"GamesNewsAgent/0.1 (+https://example.invalid)"`. This is sent on every live HTTP request. Some servers may reject or rate-limit requests with invalid User-Agent strings.

**Fix:** Change to `"GamesNewsAgent/0.1"` or make it configurable via an environment variable (`GAMES_NEWS_USER_AGENT`).

---

## 2. HARDCODED VALUES (should be configurable)

### 2.1 Heat scoring weights — `ranking.py`

| Value | Location | Severity | Reason |
|---|---|---|---|
| `recency_score` multiplier: `15.0` | `ranking.py:123` | HIGH | Changes recency/age tradeoff — must be tuned per lookback window |
| `priority * 0.12` | `ranking.py:128` | HIGH | Source priority weight in scoring formula |
| `community` source bonus: `8.0` | `ranking.py:133` | MEDIUM | Biases community over official sources |
| `official` source bonus: `4.0` | `ranking.py:136` | MEDIUM | |
| `media` source bonus: `2.0` | `ranking.py:138` | MEDIUM | |
| `meme/player_story` bonus: `14.0` | `ranking.py:144` | HIGH | Largest single bonus — can dominate all other signals |
| `hot_discussion` bonus: `6.0` | `ranking.py:147` | MEDIUM | |
| `controversy-or-market-risk` bonus: `7.0` | `ranking.py:150` | MEDIUM | |
| `discussion_score * 0.45` | `ranking.py:159` | HIGH | Discussion signal scaling |

**Recommended fix:** Extract all weights and multipliers to a dedicated `config/heat_weights.yaml` or a `HeatConfig` dataclass seeded from environment variables.

### 2.2 Story editorial bonuses — `story_sections.py`

| Value | Location | Severity | Reason |
|---|---|---|---|
| `core_game_update`: `12.0` | `story_sections.py:25` | HIGH | Primary editorial control — should be configurable |
| `core_game_report`: `8.0` | `story_sections.py:26` | MEDIUM | |
| `platform_business`: `3.0` | `story_sections.py:27` | LOW | |
| `personal_or_sentiment`: `-10.0` | `story_sections.py:30` | HIGH | Negative bonus magnitude matters for ranking |
| `per_section_limit=20` | Nodes call site only; hardcoded in `nodes.py:468,1134` | HIGH | Caps thematic pool; affects final story selection |
| `final_per_section_limit=10` | `nodes.py:1135` | HIGH | Caps final stories per section |

**Recommended fix:** Add `--theme-pool-per-section-limit` and `--final-stories-per-section-limit` CLI flags (or config entries). Move editorial bonuses to a `config/story_editorial.yaml`.

### 2.3 Engagement signal weights — `trend_signals.py`

| Value | Location | Severity | Reason |
|---|---|---|---|
| `likes`: `0.004` | `trend_signals.py:25` | MEDIUM | Signature weights in the discussion scoring model |
| `comments`: `0.075` | `trend_signals.py:26` | MEDIUM | |
| `shares`: `0.11` | `trend_signals.py:27` | MEDIUM | |
| `reposts`: `0.11` | `trend_signals.py:28` | MEDIUM | |
| `danmaku`: `0.055` | `trend_signals.py:32` | MEDIUM | |

**Recommended fix:** Move to `config/engagement_weights.yaml` or a `TrendConfig` dataclass.

### 2.4 Status bonuses — `story_ranking.py`

| Value | Location | Severity | Reason |
|---|---|---|---|
| `verified`: `20.0` | `story_ranking.py:14` | HIGH | Determines which stories make final cut |
| `likely`: `12.0` | `story_ranking.py:15` | HIGH | |
| `credible_rumor`: `7.0` | `story_ranking.py:16` | MEDIUM | |
| `weak_rumor`: `1.0` | `story_ranking.py:17` | LOW | |
| `rumor`: `2.0` | `story_ranking.py:18` | LOW | |

**Recommended fix:** Add `config/verification_weights.yaml`. Allow tuning during Phase 4.5 calibration.

### 2.5 Content quality gate thresholds — `content_quality.py`

| Value | Location | Severity | Reason |
|---|---|---|---|
| `pass` threshold: `>= 85` | `content_quality.py:18` | HIGH | Controls whether pipeline enters Phase 5 |
| `needs_review` threshold: `>= 60` | `content_quality.py:20` | HIGH | Controls whether content gets manual review or is blocked |
| `blocked` threshold: `< 60` | `content_quality.py:22` | HIGH | |

**Recommended fix:** Add `--content-quality-pass-threshold` and `--content-quality-review-threshold` CLI flags.

### 2.6 Network and timeout values

| Value | Location | Severity | Reason |
|---|---|---|---|
| Fetcher timeout: `8.0` seconds | `nodes.py:726,901,904` | MEDIUM | Hardcoded at call sites instead of using a config value |
| Fetcher default timeout: `12.0` seconds | `fetching.py:114` | LOW | Already configurable via constructor |
| LLM timeout: `45.0` seconds | `llm_provider.py:23` | LOW | Configurable via `LLM_TIMEOUT` env var |
| LLM temperature: `0.1` | `llm_provider.py:24` | LOW | Configurable via `LLM_TEMPERATURE` env var |
| LLM max_tokens: `700` | `llm_provider.py:25` | LOW | Configurable via `LLM_MAX_TOKENS` env var |

### 2.7 Historical context mining parameters

| Value | Location | Severity | Reason |
|---|---|---|---|
| `lookback_years=5` | `nodes.py:1535` | MEDIUM | Hardcoded at call site |
| `max_context_items=5` | `nodes.py:1536` | MEDIUM | Hardcoded at call site |
| Default `max_context_items=8` | `historical_context_miner.py:100` | LOW | Function default only |

**Recommended fix:** Add `--historical-context-lookback-years` and `--historical-context-max-items` CLI flags (both already have `--run-historical-context` gate).

### 2.8 Other magic numbers/strings

| Value | Location | Severity | Reason |
|---|---|---|---|
| `MAX_ATTEMPTS=3` for fetcher retry | `fetching.py:118` | LOW | Already configurable via constructor; reasonable default |
| `backoff_base_seconds=0.5` | `fetching.py:119` | LOW | |
| `backoff_max_seconds=8.0` | `fetching.py:120` | LOW | |
| `SourceConfig.priority` default `50` | `schemas.py:31` | LOW | Sensible default |
| `editorial_judgment limit=20` | `nodes.py:1153` | MEDIUM | Hardcoded at call site; editorial judgment request limit |
| `per_observation_limit=1` for search expansion | `nodes.py:757` | LOW | |

---

## 3. SPEC DEVIATIONS (does not match roadmap/issues.md)

### 3.1 Missing prompt files

**Spec says** (roadmap line 456-458): Prompts for `claim_extractor.md`, `evidence_verifier.md`, `markdown_editor.md`, `platform_writer.md`, `layout_designer.md`, `historical_context_miner.md`.

**Actual:** Only 3 prompt files exist: `evidence_verifier.md`, `search_query_compressor.md`, `search_result_relevance.md`.

Missing: `claim_extractor.md`, `markdown_editor.md`, `platform_writer.md`, `layout_designer.md`, `historical_context_miner.md`.

### 3.2 ClaimExtractor is rule-based only — spec says LLM should be the primary engine

**Spec says** (roadmap line 147-153): "将资讯拆成可验证声明... 每个故事拆成 1-5 个 claim." Later lines 155-160 state current state produces 1 unchecked claim per context_pack, with LLM planned for next phase.

**Actual:** `claim_extraction.py` produces exactly 1 claim per context pack with `unchecked` status. No LLM path exists. This matches the "最小实现状态" entry, so it is a **known staged deviation**, not a gap. The spec for full LLM-based claim extraction (1-5 claims per story) is not yet implemented.

### 3.3 EvidenceVerifier rule-based v0 cannot output `verified` or `conflict` statuses

**Spec says** (roadmap lines 205-206): "当前版本不会输出 `verified` 或 `conflict`，这两个状态留给后续 LLM verifier 基于完整 context pack 判断。"

**Actual:** This is correct for the current phase. However, **`verified` is defined as a `PUBLISHABLE_STATUSES` member** in `story_ranking.py` (line 11), meaning if an LLM verifier produces `verified`, it will be treated as publishable. This is expected but worth noting: the rule-based verifier can never reach `verified`, creating a quality gap in non-LLM runs.

### 3.4 No `OpsReviewer` or `Publisher` nodes

**Spec says** (roadmap lines 372-383): OpsReviewer and Publisher are planned for future phases.

**Actual:** These are correctly not implemented. The `design_layout`, `render_assets`, and `organize_artifacts` nodes serve as skeleton placeholders. This is a **known staged gap**, not a bug.

### 3.5 `run_story_cluster_review_agent` CLI flag has wrong semantics

**CLI says** (run.py line 147): `"--run-story-cluster-review-agent"` with help text "Write content review pack after quality gate (RUN-004)."

**Spec says** (issues.md line 313-315): "AG-004 StoryClusterReviewAgent: 处理 dedup_semantic_review_requests.json 和 RAG evidence pack."

**Actual:** The flag writes the content review pack (which is `GEN-004` territory, not `AG-004`). The `story_cluster_review_agent.py` module exists but is **never invoked by any node**, and the flag name does not match its behavior. The actual `--run-story-cluster-review-agent` flag has zero effect on behavior (see CRIT-1).

### 3.6 No `EditorialJudgmentAgent` execution path

**Spec says** (roadmap lines 866-871): "将 EditorialJudgmentAgent 先用于人工/LLM 对照评估." And claudeCheck (line 921-924): "设计保留，暂缓执行."

**Actual:** The request builder exists in `editorial_judgment.py` and `score_heat` writes `editorial_judgment_requests.json`. However, there is **no CLI flag** (`--run-editorial-judgment-agent` does not exist), **no LLM execution path**, and **no result parser** wired back into the ranking. The editorial judgment requests are generated but never consumed by an LLM.

### 3.7 `CandidateDedup v1` and `StoryClusterer v1` not yet implemented

**Spec says** (issues.md lines 193-204): `CLU-001 CandidateDedup v1` and `CLU-002 Semantic Review Requests`.

**Actual:** The `deduplication.py` module exists with rule-based clustering via `annotate_story_clusters`. Full URL normalization, token/Jaccard similarity, and entity overlap clustering are not implemented. This is a **known staged gap** (roadmap lines 900-902).

### 3.8 Section keyword lists are hardcoded and cannot be extended without code changes

**Spec says** (roadmap lines 779-784): Five fixed theme sections with editorial weighting.

**Actual:** The `SECTION_KEYWORDS` dict in `story_sections.py` (lines 33-89) hardcodes game/platform names (e.g., `"marvel wolverine"`, `"insomniac"`, `"naughty dog"`). New games require code changes. This should be configurable via `config/theme_sections.yaml`.

---

## 4. MISSING EXTENSIBILITY HOOKS

### 4.1 No provider interface for swapping v0 rule logic with LLM

The spec outlines a clear "确定性 first, LLM later" pattern (roadmap lines 462-467). The following modules have rule-based v0 implementations but lack an abstract provider interface that would allow swapping for an LLM:

| Module | v0 Implementation | LLM Swap Target | Missing Hook |
|---|---|---|---|
| `claim_extraction.py` | 1 claim per context pack, rule-based | LLM claim decomposition (1-5 claims/story) | `ClaimExtractor` protocol/ABC with `extract_claims(context_packs) -> list[Claim]` |
| `evidence_verification.py` | Keyword overlap scoring | LLM evidence assessment | `EvidenceVerifier` protocol/ABC with `verify(claim, evidence) -> VerificationResult` |
| `deduplication.py` | Rule-based title/URL clustering | LLM semantic dedup review | `DedupClassifier` protocol/ABC |
| `editorial_judgment.py` | Request builder only, no executor | LLM editorial judgment | `EditorialJudgmentExecutor` protocol/ABC (requests are built, but no execution path) |
| `story_ranking.py` | Weighted sum formula | LLM reranker | `StoryReranker` protocol/ABC |

### 4.2 `fetch_documents` node bundles ContextPackBuilder — no separate hook

**Spec says** (roadmap lines 222-231): ContextPackBuilder should be a separate concern that structures evidence packs for LLM consumption.

**Actual:** `fetch_documents` (nodes.py:458-540) builds theme_candidate_pool, fetches documents, builds evidence chunks, and builds context packs all in one node. There is no `ContextPackBuilder` node or provider interface. The `build_context_packs()` function is called directly. A `ContextPackProvider` interface that takes `(candidates, evidence_chunks)` and returns context packs would allow future pluggable pack construction strategies (different pack shapes for different LLM nodes).

### 4.3 No callback/observer hook for node lifecycle events

The `RunTraceRecorder` captures node finished events, but nodes have no pre-execution or post-execution hook. An `Observer` protocol would allow:
- Cost tracking per node
- Token counting at LLM call sites
- Custom logging/metrics
- Feature-flag gating per node without modifying graph.py

### 4.4 `llm_provider.py` is hardwired to OpenAI-compatible chat completions

**Location:** `LangGraph/src/games_news_agent/llm_provider.py`

**Problem:** The `OpenAICompatibleVerifierClient` hardcodes `/chat/completions` endpoint construction (line 63). The `LlmConfig` dataclass exposes `temperature` and `max_tokens` but not `top_p`, `stop`, `presence_penalty`, or `frequency_penalty`. The `response_format: {"type": "json_object"}` is hardcoded.

**Recommended fix:** Add a `LlmProvider` ABC with `chat(request: LlmRequest) -> LlmResponse` and allow provider selection via config (OpenAI, Anthropic, local Ollama, etc.).

### 4.5 No provider interface for discussion/heat data

The `discussion_probe_provider.py` uses hardcoded platform-specific HTTP fetching. The `social_heat.py` module defines a contract but no abstract provider interface. A `SocialHeatProvider` ABC would allow:
- `BilibiliProvider`, `WeiboProvider`, `RedditProvider`, etc.
- Future API-based providers (e.g., SocialData APIs)
- Manual import provider for air-gapped environments

### 4.6 Missing `EventBurstDetector` as a pluggable component

The `search_expansion.py` module includes `event_burst` logic but the event detection (Showcase, Direct, Game Fest, 发布会, 游戏展) is hardcoded in regex patterns. An `EventBurstDetector` protocol would allow:
- Calendar-based burst detection (known event dates)
- LLM-based burst detection from news velocity
- Per-region event detection (TGS, ChinaJoy, Gamescom, etc.)

---

## 5. INTEGRATION GAPS

### 5.1 Graph nodes without corresponding test files

These graph nodes lack dedicated unit tests for their specific behavior:

| Graph Node | Test File | Gap |
|---|---|---|
| `expand_search_candidates` | `test_search_expansion.py` exists | Partial — tests the module but not the node's state-update logic |
| `probe_discussions` | `test_discussion_probe.py` exists | Same — tests the module, not node integration |
| `extract_assets` | No dedicated test | Only `test_materials.py` tests `build_assets_from_documents` |
| `deduplicate_stories` | `test_story_deduplication.py` exists | OK |
| `plan_selection_backfill` | `test_selection_backfill.py` exists | OK |
| `write_material_bundle` | No dedicated test | Only `test_materials.py` covers `build_material_bundle` |
| `organize_artifacts` | `test_artifact_manifest.py` exists | OK |
| `check_source_health` | `test_source_recovery_agent.py` exists | OK |
| `retrieve_evidence` (node) | `test_evidence_retrieval.py` exists | Tests the function but not the node's full state write path |
| `build_event_timeline` | `test_event_timeline.py` exists | OK |
| `mine_historical_context` | `test_historical_context_miner.py` exists | OK |

### 5.2 State fields in `PipelineState` without CLI flags

The following state fields are declared in `PipelineState` (schemas.py) but have **no corresponding CLI flag** in `run.py`:

| State Field | Purpose |
|---|---|
| `underfilled_section_diagnostics` / `_path` | FIL-004 output |
| `agent_contracts_path` | AG-001 output |
| `source_recovery_decisions` / `_path` | AG-003 output |
| `source_recovery_suggestions_path` | COL-004 output |
| `site_parser_contracts` / `_path` | COL-003 output |
| `story_cluster_review_decisions` / `_path` | AG-004 output |
| `historical_duplicate_checks` / `_path` | CLU-004 output |
| `search_intelligence_path` | SRC-001/SRC-002 output |
| `user_notification_contract_path` | RUN-003 output |
| `source_recovery_decisions_path` | AG-003 output |

These fields are populated by nodes but never seeded by CLI, which is acceptable for artifact paths. However, `underfilled_section_diagnostics` has no feature flag to enable/disable underfilled section fill logic.

### 5.3 CLI flags without effect in graph

| CLI Flag | Effect |
|---|---|
| `--run-story-cluster-review-agent` | Parsed, placed into state, **never read by any conditional edge or node** (see CRIT-1) |

### 5.4 Harness fixtures without corresponding tests

All 29 harness fixtures exist (issues.md lines 39-68), but not all have automated tests that load and assert against them:

| Harness Fixture | Automated Test Coverage |
|---|---|
| `H-AG-001-bounded-decision.json` | `test_agent_contracts.py` |
| `H-AG-002-no-suitable-tool.json` | `test_agent_contracts.py` |
| `H-FIL-001-theme-split.json` | `test_story_sections.py` (partial) |
| `H-FIL-002-non-game-filter.json` | `test_candidate_type_gate.py` |
| `H-VER-001-fact-vs-rumor.json` | `test_evidence_verification.py` (partial) |
| `H-EVI-001-evidence-chunks.json` | No dedicated fixture-loading test |
| `H-EVI-002-evidence-pack.json` | No dedicated fixture-loading test |
| `H-RANK-001-per-section-selection.json` | `test_story_ranking.py` (partial) |
| `H-RANK-002-core-game-priority.json` | No dedicated fixture-loading test |
| `H-CLU-001-dedup-merge.json` | `test_story_deduplication.py` (partial) |
| `H-LAY-001-missing-image.json` | No test (layout is skeleton) |
| `H-MEM-001-ingest-parity.json` | `test_sqlite_mirror.py` |
| `H-MEM-002-query-differentiate.json` | `test_event_store.py` (partial) |
| `H-OPS-001-blocking-stops-publish.json` | `test_content_quality.py` (partial) |
| `H-RUN-001-dry-run-manifest.json` | `test_run_trace.py` |
| `H-RUN-002-node-exception.json` | `test_run_trace.py` |
| `H-RUN-003-artifact-index.json` | `test_run_trace.py` |
| `H-COL-001..004` | `test_live_collection_building_blocks.py` |

### 5.5 `organize_artifacts` node runs unconditionally at end of graph

The `organize_artifacts` node runs after `render_assets` with no conditional check. If earlier nodes fail and the graph short-circuits via `END` (e.g., `should_continue_after_quality_gate` returns `"end_early"`), artifacts are still organized by the `RunTraceRecorder` in `run.py` lines 257-264, but the graph node `organize_artifacts` is skipped. This is handled correctly at the run.py level but the dual artifact organization paths (graph node + run.py finally block) create complexity.

---

## 6. RECOMMENDED FIXES (prioritized)

### Quick Fixes (under 5 minutes each)

1. **Fix CRIT-1 — Dead conditional branch.** In `graph.py`, add the `run_story_cluster_review_agent` flag check in `should_continue_after_quality_gate`:
   ```python
   if not state.get("run_story_cluster_review_agent", True):
       return "skip_review"
   ```
   Or remove the `"skip_review"` branch and the flag entirely.

2. **Fix CRIT-3 — User-Agent.** Change `fetching.py:115` default from `"GamesNewsAgent/0.1 (+https://example.invalid)"` to `"GamesNewsAgent/0.1"` and add `GAMES_NEWS_USER_AGENT` env-var override.

3. **Fix flag help text.** Change `--run-story-cluster-review-agent` help text in `run.py:147-148` to match actual behavior (or remove the flag).

4. **Add missing `--run-editorial-judgment-agent` flag.** In `run.py`, add:
   ```python
   parser.add_argument("--run-editorial-judgment-agent", action="store_true",
                       help="Call LLM for editorial judgment on story candidates.")
   ```
   And wire it into `score_heat` in `nodes.py` (the request builder already exists at line 1151).

5. **Fix search expansion fetcher timeout.** The calls at `nodes.py:726` and `nodes.py:901` pass `HttpFetcher(timeout=8.0)`. These should use a shared constant or config value instead of duplicating the magic number.

6. **Remove `example.invalid` URLs from dry-run candidates.** The 5 dry-run example candidates in `nodes.py:155-205` all use `https://example.invalid/...` URLs. While intentionally invalid for dry-run, they risk leaking into artifacts during testing/debugging. Consider using a `dry-run://` scheme or `data:text/` URI that cannot be confused with real URLs.

### Medium Fixes (require refactoring one module)

7. **Extract heat scoring weights to config.** Create `LangGraph/config/heat_weights.yaml`:
   ```yaml
   scoring:
     recency_multiplier: 15.0
     source_priority_weight: 0.12
     community_bonus: 8.0
     official_bonus: 4.0
     media_bonus: 2.0
     meme_player_story_bonus: 14.0
     hot_discussion_bonus: 6.0
     controversy_bonus: 7.0
     discussion_score_weight: 0.45
   ```
   Load in `ranking.py` and pass via constructor or module-level config.

8. **Extract editorial bonuses to config.** Create `LangGraph/config/story_editorial.yaml` with editorial bonus values from `story_sections.py` and `story_ranking.py`.

9. **Add `ContentQualityConfig` and corresponding CLI flags.** Add `--content-quality-pass-threshold` (default 85) and `--content-quality-review-threshold` (default 60) to `run.py`, wire into `content_quality.py`.

10. **Create missing prompt stub files.** Create `LangGraph/prompts/claim_extractor.md`, `markdown_editor.md`, `platform_writer.md`, `layout_designer.md`, `historical_context_miner.md` with placeholder content pointing to the roadmap sections.

11. **Make fetcher timeout configurable per call site.** Add `search_expansion_timeout` and `discussion_probe_timeout` fields to state/CLI, with defaults of 8.0 seconds, rather than hardcoding at call sites.

12. **Fix `should_continue_after_quality_gate` to check for `gate_status == "needs_review"` returning `skip_review` when flag is off.** Currently `needs_review` routes to `continue`, meaning content review pack is always generated even for low-quality content. The flag should control whether `needs_review` goes to review pack or material bundle.

### Long-Term Improvements (architectural changes)

13. **Define provider abstractions for all v0→LLM transition points.** Create ABCs/protocols for:
    - `ClaimExtractor` (swapping rule-based 1-claim for LLM-based 1-5 claims)
    - `EvidenceVerifier` (swapping keyword overlap for LLM evidence assessment)
    - `DedupClassifier` (swapping title/URL rules for LLM semantic dedup)
    - `StoryReranker` (swapping weighted formula for LLM reranker with rationale)
    - `SocialHeatProvider` (unifying Bilibili/Weibo/Reddit/etc. into a common interface)
    - `EventBurstDetector` (swapping regex for calendar/velocity-based detection)

14. **Split `fetch_documents` node into `select_theme_candidates` and `build_context_packs`.** The current monolithic node makes it impossible to swap out context pack construction strategy. A separate `ContextPackBuilder` node would align with the roadmap spec (roadmap lines 222-231).

15. **Implement `EditorialJudgmentAgent` execution path.** The request builder already exists. Add:
    - CLI flag `--run-editorial-judgment-agent`
    - LLM execution via `run_llm_json_requests()`
    - Result parser in `editorial_judgment.py`
    - Story-level annotation of `editorial_judgment_result` in `score_heat`
    - Integration with `theme_story_ranking_diagnostics.json`

16. **Add `LlmRouter` task-type routing.** Per roadmap line 908: "让 editorial judgment、semantic relevance、claim verification、story clustering 使用不同模型/温度/token 上限." Add `task_type` parameter to `LlmConfig` and allow per-task-type overrides in environment variables (e.g., `LLM_EDITORIAL_MODEL`, `LLM_EDITORIAL_TEMPERATURE`).

17. **Migrate keyword/section lists to config files.** Move `SECTION_KEYWORDS` from `story_sections.py` and `GAME_SIGNAL_PATTERN` from `candidate_types.py` to `config/theme_sections.yaml` and `config/game_signals.yaml` respectively.

18. **Add per-node token tracking.** Integrate with the `RunTraceRecorder` to estimate and log token consumption per LLM call, enabling cost analysis and budget enforcement.

---

## Summary Counts

| Category | Count |
|---|---|
| CRITICAL issues | 3 |
| Hardcoded values (unique items) | 24 |
| Spec deviations | 8 |
| Missing extensibility hooks | 6 |
| Integration gaps | 12 |
| Quick fixes | 6 |
| Medium fixes | 6 |
| Long-term improvements | 6 |

**Overall assessment:** The codebase has strong foundational architecture with LangGraph workflow, rich artifact production, comprehensive harness fixtures, and 55 test files. The three critical issues are all quick-fix scope (dead conditional branch, bad User-Agent, missing LLM safety warning). The most impactful medium-term work is extracting configurable weights (heat scoring, editorial bonuses, quality thresholds) and adding the missing EditorialJudgmentAgent execution path. The code is well-structured for the "Phase 4.5 — Content Quality Validation" stage it aims for.
