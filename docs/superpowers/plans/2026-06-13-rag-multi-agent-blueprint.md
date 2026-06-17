# RAG Multi-Agent Blueprint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Evolve the games news pipeline from a content-validation workflow into a complete multi-agent news intelligence system with evidence RAG, memory, historical context, and citation-backed QA.

**Architecture:** Keep LangGraph workflow as the backbone. Add RAG in stages: evidence scaffold first, claim-level retrieval second, persistent memory third, and QA agent last. Bounded ReAct may route retrieval tools, while reflection reviews run artifacts and recommends next-run changes.

**Tech Stack:** Python, LangGraph workflow, existing JSON artifacts, SQLite + FTS/BM25 as the first persistent store, optional SQLite-vec/FAISS/Qdrant/Chroma later, OpenAI-compatible LLM provider for structured JSON decisions.

---

## RAG Entry Decision

RAG should be added when the pipeline has stable material to retrieve from. It should not be used to compensate for missing collectors, missing timestamps, weak social heat access, or unclear candidate boundaries.

Use this staged policy:

- `RAG-0 Evidence Scaffold`: already present. Keep strengthening `documents.json`, `evidence_chunks.json`, `context_packs.json`, and metadata filters.
- `RAG-1 Claim-Level Retrieval`: start after SocialHeatProvider and SourceDominanceAudit make it clear that remaining failures are evidence/verification failures, not candidate discovery failures.
- `RAG-1.5 Semantic Relevance Gate`: start after deterministic social heat relevance checks exist. RAG retrieves candidate evidence, social observations, and story memory so an LLM classifier can judge same-event, same-game, within-window, old-news, or clickbait status with citations.
- `RAG-2 Persistent Memory Retrieval`: start after several live runs produce stable story ids, claim ids, evidence ids, and human review labels.
- `RAG-3 NewsQAAgent`: start after the persistent stores can answer retrieval questions with citations and after hallucination guard tests exist.

---

## Target Multi-Agent System

### Workflow Backbone

```text
Trigger
 -> SourcePlanner
 -> CollectorRouterAgent
 -> SearchCollector / SocialCollector
 -> CandidateNormalizer
 -> CandidateTypeGate
 -> SocialHeatProvider
 -> DedupClusterer
 -> ClaimExtractor
 -> EvidenceGatheringAgent
 -> VerificationAgent
 -> MemoryFreshnessAgent
 -> HistoricalContextAgent
 -> RerankAgent
 -> EditorialJudgmentAgent
 -> MarkdownEditorAgent
 -> PlatformWriterAgent
 -> ContentQualityAgent
 -> NewsQAAgent
 -> LayoutPlanningAgent
 -> OpsReviewAgent
```

### Stores

- `RunArtifactStore`: every run's JSON/Markdown artifacts for replay and audit.
- `CandidateStore`: normalized candidates with time, source, theme, source entry, and memory keys.
- `EvidenceStore`: article chunks and evidence metadata, initially SQLite + FTS/BM25.
- `SocialHeatStore`: platform observations, access mode, engagement signals, and heat validity hints.
- `StoryMemoryStore`: story lifecycle, first_seen, last_seen, follow-up links, final status.
- `HumanReviewStore`: semantic review labels and style feedback.
- `VectorIndex`: optional semantic index after metadata retrieval is stable.

### Agent Roles

- `CollectorRouterAgent`: chooses whitelisted collector/parser/provider based on diagnostics.
- `EvidenceGatheringAgent`: retrieves claim evidence with metadata filters and compact context packs.
- `SemanticRelevanceAgent`: consumes deterministic relevance checks plus retrieved evidence; it decides whether a social/search result is the same event, same game, current within the run window, old news, or clickbait. It cannot add URLs, facts, or social results.
- `VerificationAgent`: labels claims as verified, likely, rumor, conflict, reject, or manual review.
- `MemoryFreshnessAgent`: detects old reposts and current follow-up updates.
- `HistoricalContextAgent`: finds historical records and "first since year" style context.
- `RumorProfileAgent`: tracks source credibility and rumor lifecycle.
- `RerankAgent`: explains theme-level ranking and final Top 10 selection.
- `EditorialJudgmentAgent`: identifies non-game, weak-game, or high-risk content.
- `NewsQAAgent`: answers user questions over stored evidence with citations.
- `ContentQualityAgent`: reflects on run artifacts and recommends next-run changes.

---

## Task 1: RAG Store Contracts

**Files:**
- Create: `LangGraph/src/games_news_agent/rag_contracts.py`
- Test: `LangGraph/tests/test_rag_contracts.py`
- Docs: `docs/roadmap.md`

- [ ] **Step 1: Write tests for stable ids and metadata**

Tests should assert that evidence records require:

```python
{
    "evidence_id": "evidence_001",
    "story_id": "story_switch_price",
    "claim_id": "claim_001",
    "source_url": "https://example.invalid/story",
    "source_id": "ign",
    "published_at": "2026-06-13T08:00:00+00:00",
    "observed_at": "2026-06-13T08:30:00+00:00",
    "theme_section": "nintendo",
    "chunk_text": "Nintendo Switch 2 price discussion...",
    "evidence_scope": "candidate_url"
}
```

- [ ] **Step 2: Implement normalizers**

Required functions:

```python
def normalize_evidence_record(raw: dict[str, Any]) -> dict[str, Any]:
    """Return a complete evidence record or mark missing required fields."""

def normalize_story_memory_record(raw: dict[str, Any]) -> dict[str, Any]:
    """Return story lifecycle fields with safe defaults."""
```

- [ ] **Step 3: Verify with unittest**

Run:

```powershell
$env:PYTHONPATH='LangGraph/src'; D:\Anaconda\envs\gamesnewscrew\python.exe -m unittest LangGraph.tests.test_rag_contracts
```

---

## Task 2: Claim-Level Retrieval Plan

**Files:**
- Modify: `LangGraph/src/games_news_agent/retrieval.py`
- Modify: `LangGraph/src/games_news_agent/context_packs.py`
- Test: `LangGraph/tests/test_evidence_pipeline.py`

- [ ] **Step 1: Add tests for metadata-first retrieval**

Test that a claim about Nintendo only retrieves chunks matching:

- same `story_id` or close cluster
- same `theme_section`
- inside lookback window or historical query mode
- `evidence_scope=candidate_url` before `retrieved_context`

- [ ] **Step 2: Implement retrieval ranking**

Scoring order:

1. exact candidate URL / story cluster
2. same source or official source
3. same time window
4. entity overlap
5. keyword/BM25 score

- [ ] **Step 3: Keep evidence pack small**

Each claim gets at most 5 evidence chunks, with explicit `missing_fields` when insufficient.

---

## Task 3: Persistent Memory Store

**Files:**
- Create: `LangGraph/src/games_news_agent/persistent_memory.py`
- Test: `LangGraph/tests/test_persistent_memory.py`

- [ ] **Step 1: Define SQLite schema**

Tables:

- `stories`
- `claims`
- `evidence_chunks`
- `social_heat_observations`
- `human_reviews`
- `run_artifacts`

- [ ] **Step 2: Add import from JSON artifacts**

Function:

```python
def import_run_artifacts(output_dir: str, sqlite_path: str) -> dict[str, Any]:
    """Import one LangGraph run into persistent memory and return row counts."""
```

- [ ] **Step 3: Add first query helpers**

Functions:

```python
def find_similar_story_titles(sqlite_path: str, title: str, limit: int = 10) -> list[dict[str, Any]]:
    """Return similar story records using FTS/BM25."""

def find_story_evidence(sqlite_path: str, story_id: str, limit: int = 5) -> list[dict[str, Any]]:
    """Return evidence records for one story."""
```

---

## Task 4: Historical Context Retrieval

**Files:**
- Create: `LangGraph/src/games_news_agent/historical_context.py`
- Test: `LangGraph/tests/test_historical_context.py`

- [ ] **Step 1: Add tests for record candidates**

Examples:

- "first PC release from this studio"
- "first price rise since 2024"
- "first trailer after two years"

- [ ] **Step 2: Implement candidate generation**

Output statuses:

- `confirmed_record`
- `record_candidate`
- `analogy`
- `manual_review_required`

Every output must cite evidence ids or mark missing evidence.

---

## Task 5: NewsQAAgent MVP

**Files:**
- Create: `LangGraph/src/games_news_agent/news_qa.py`
- Test: `LangGraph/tests/test_news_qa.py`
- Prompt: `LangGraph/prompts/news_qa.md`

- [ ] **Step 1: Define supported questions**

MVP supports:

- evidence chain questions
- why selected / why not selected
- rumor credibility questions
- follow-up vs old repost questions
- historical context questions

- [ ] **Step 2: Add answer schema**

Answer JSON:

```json
{
  "answer": "string",
  "confidence": 0.0,
  "citations": [
    {
      "source_url": "https://example.invalid/story",
      "evidence_id": "evidence_001",
      "quote": "short excerpt"
    }
  ],
  "missing_evidence": [],
  "unsupported_claims": []
}
```

- [ ] **Step 3: Guard unsupported answers**

If no citations are available, return:

```json
{
  "answer": "证据不足，无法回答。",
  "confidence": 0.0,
  "citations": [],
  "missing_evidence": ["no_matching_evidence"],
  "unsupported_claims": []
}
```

---

## Task 6: Evaluation Harness

**Files:**
- Create: `LangGraph/tests/test_news_qa_eval.py`
- Create: `LangGraph/harness/qa_examples.json`

- [ ] **Step 1: Add gold QA examples**

At least 10 examples:

- 3 evidence-chain questions
- 2 rumor questions
- 2 historical context questions
- 2 why-selected questions
- 1 insufficient-evidence question

- [ ] **Step 2: Evaluate answer quality**

Metrics:

- citation coverage
- unsupported claim count
- recency correctness
- source attribution correctness
- insufficient-evidence correctness

---

## Implementation Order

1. Finish Phase 4.5 social heat and semantic review first.
2. Implement RAG store contracts.
3. Upgrade claim-level retrieval.
4. Add persistent memory store.
5. Add historical context retrieval.
6. Add NewsQAAgent MVP.
7. Add evaluation harness before presenting QA as a finished capability.
