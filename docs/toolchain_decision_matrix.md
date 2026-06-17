# Toolchain Decision Matrix

This document records build-vs-buy decisions for the games news agent. The rule is simple: keep project-specific news policy in auditable code and artifacts; use mature libraries for generic infrastructure when they reduce risk.

## Decision Template

Each new feature should answer:

- `function_area`: collection, social heat, relevance, verification, RAG, memory, ranking, layout, publishing, evaluation.
- `current_problem`: the concrete failure observed in live or dry-run artifacts.
- `candidate_tools`: existing frameworks, libraries, APIs, or project modules considered.
- `decision`: `custom_first`, `adapter_to_existing_library`, `defer`, or `reject_for_now`.
- `reason`: why this choice fits the current phase.
- `integration_boundary`: input artifact, output artifact, optional flags, approval gates.
- `promotion_criteria`: what evidence allows this adapter to become default.

## Current Decisions

| Function area | Current decision | Candidate tools | Reason | Integration boundary |
| --- | --- | --- | --- | --- |
| Main orchestration | `custom_first` with LangGraph backbone | LangGraph, CrewAI | The pipeline needs stable nodes, replayable artifacts, and deterministic gates. CrewAI remains a creative sidecar later. | LangGraph state + JSON artifacts |
| Prompt management | `custom_first` registry now, LangChain templates later | `prompt_registry.json`, LangChain PromptTemplate/structured output | Prompt ownership, fallback, harness mapping, and fact-safety rules are project-specific. LangChain can later execute registered prompts, but should not become the source of truth. | `LangGraph/prompts/prompt_registry.json` -> `*_requests/results/failures.json` |
| LLM calls | `adapter_to_existing_library` later | Existing `llm_provider.py`, LangChain structured output | Keep the current OpenAI-compatible provider now; evaluate LangChain when multiple structured agents need shared retries, tracing, or tool calling. | `*_requests.json` -> `*_results.json` |
| Public social search | `custom_first` | stdlib HTTP, Playwright later | Bilibili and Steam can be probed with ordinary HTTP first. Playwright only when JS shell or browser-only evidence blocks progress. | `social_heat_observations.json` |
| Login/app social platforms | `defer` | manual import, Playwright sidecar, platform/search APIs | Xiaoheihe and similar sources should not be automated until manual samples prove value and user approves login/state handling. | `manual_import` observations |
| Social result relevance | `custom_first` then RAG/LLM | deterministic classifier, RAG-backed classifier, LangChain structured output | Same-event and same-game judgment must first remove self-reference and obvious off-topic results before spending tokens. | `social_heat_relevance_checks.json` -> `semantic_relevance_results.json` |
| Evidence retrieval | `custom_first` now, vector/RAG libraries later | SQLite FTS/BM25, LlamaIndex, Chroma, FAISS, Qdrant | Metadata and source/time boundaries are not stable enough for full vector QA yet. | `evidence_chunks.json`, `context_packs.json` |
| Persistent memory | `custom_first` now | SQLite, sqlite-vec later | Story lifecycle, first_seen, last_seen, and human labels are project-specific; vector similarity can be added after stable schema. | `StoryMemoryStore` |
| Browser sidecar | `adapter_to_existing_library` when needed | Playwright | Browser automation is generic infrastructure and should not be hand-rolled. Use only with rate limits and approval gates. | `browser_sidecar` observations/screenshots |
| Crawling/extraction | `defer` for big crawler frameworks | Scrapy, Crawl4AI, Firecrawl | Current sources need site-specific parsers and diagnostics more than a broad crawler. Evaluate these when parser maintenance becomes the bottleneck. | collector adapters -> candidates/documents |
| Evaluation/tracing | `defer` until LLM affects ranking | LangSmith, custom harness | Existing unittest + artifact review is enough while LLM only writes optional suggestions. Add tracing when LLM decisions start influencing ranking. | run artifacts + eval cases |

## Agent Toolchain Direction After v020_fix_verify

The `outputs/langgraph/v020_fix_verify` run showed that deterministic collection, SQLite mirror, schema validation, and small LLM shadow tasks can coexist. It also showed why the next toolchain step should be stricter contracts, not more autonomy.

| Need | Decision | Candidate tools | Why now | Promotion criteria |
| --- | --- | --- | --- | --- |
| Workflow state, recovery, human gates | Keep LangGraph as default | LangGraph checkpointers, persistence, interrupts, human-in-the-loop | The project needs a replayable graph with stage artifacts and review gates. | Add only after current JSON/SQLite run trace can be loaded by the service UI. |
| Tool calling and structured LLM calls | Wrap through project contracts first, LangChain adapter second | LangChain tools, Runnable, structured output, retry | LangChain is useful once outputs already have schemas; project-specific fact boundaries remain in artifacts. | A shadow task has stable JSON success rate, fallback behavior, and unit/offline fixtures. |
| Prompt and output quality | Strengthen local registry before LangSmith | `prompt_registry.json`, local schema gate, later LangSmith datasets/evals | `editorial_judgment` still fails JSON 4/5; fix structure locally before external tracing. | Positive/failure/boundary fixtures exist; failures become actionable review items. |
| Agent diagnosis | Bounded review/diagnosis agents only | SourceRecoveryAgent, ContentQualityAgent, SemanticRelevanceAgent | Agents should read artifacts and choose whitelisted tools, not invent facts or sources. | `AgentDecision` includes input refs, chosen tool, fallback, and `needs_user_action` path. |
| Database access for agents/UI | Whitelist query API | `persistence/agent_query.py`, SQLite mirror | Future runs may not emit every JSON by default. Agents and UI need a safe query surface. | Add new query types before exposing raw SQL; every query has tests and limits. |
| Internal workbench | `adapter_to_existing_library` with strict read-only core | FastAPI, Nuxt3/Vue3, Tailwind, ECharts | The next bottleneck is review and comparison, not more autonomous agents. A workbench lets the user score real runs, inspect warnings, compare deterministic vs LLM shadow, and generate labels for later RAG/Agent evaluation. | First release exposes run/artifact/notification/quality/shadow APIs and human review capture; no platform login, no auto publish, no arbitrary SQL. |
| Evaluation | Local harness first, LangSmith later | unittest, harness JSON, human review pack, LangSmith evals | LLM output is still shadow-only. Local fixtures are enough until LLM affects ranking. | When LLM suggestions influence rank/review decisions, add trace/eval comparison. |

## Agent Toolchain Direction After v020_ultracode_verify (PRM-006/SHD-004/GEN-005/RUN-006)

The `v020_ultracode_verify` round implemented the four structural gates identified in the previous round.  Key toolchain decisions that emerged:

| Need | Decision | Candidate tools | Why now | Promotion criteria |
| --- | --- | --- | --- | --- |
| JSON repair for LLM outputs | Custom lightweight repair (regex-based, no external parser) | `json.loads` + regex patterns, `json_repair` library (deferred) | 4/5 editorial_judgment failures were invalid JSON; regex repair covers trailing commas, unquoted keys, markdown fences, unbalanced braces — enough for current shadow volume. | If repair rate stays below 50% or error patterns diversify beyond regex, evaluate `json_repair` library. |
| Structured output validation gate | Three-layer local gate: required fields → cross-field consistency → echo detection | `_validate_shadow_output` in `llm_shadow.py`, per-task-type field contracts | Even valid JSON can have contradictory fields (relevance=same_game + same_game=false) or echo input verbatim. Gate catches these before they're counted as success. | When gate catches >10% of parsed-OK outputs, the prompt needs revision; track rate in shadow_run_report. |
| Human review pack stability | Always-on node (not gated by feature flag) | `content_review.py` write in `write_content_review_pack` node | The review pack is Phase 4.5's primary deliverable. Feature flags should gate agent behavior, not artifact generation. | When content_review.md is missing from any run with stories, trigger RUN-006 warning notification. |
| Non-blocking warning visibility | Warning notification pipeline (source health → shadow fallback → missing artifacts) | `run_notifications.py`, `user_notifications.json` | Source failures and high fallback rates were invisible to users/agents. Warnings aggregate cross-run patterns. | When an agent/workbench reads `user_notifications.json` and auto-surfaces repeated warnings, promote to agent-query view. |

## Service-First Workbench Decision

After the `v020_ultracode_verify` review, the recommended next layer is an internal FastAPI/Nuxt3 workbench before deeper autonomous Agent/RAG behavior.

Why this is reasonable:

- The deterministic pipeline already emits enough artifacts to review, but human review is still too file-system heavy.
- LLM shadow is useful only if the user can compare it against deterministic results and score the difference.
- SQL/RAG/Agent work needs labels and failure examples; the workbench is the fastest way to collect them from real runs.
- Service APIs create stable boundaries for future Agents: they call whitelisted query/review endpoints instead of reading arbitrary files or writing arbitrary SQL.

Boundaries:

- FastAPI reads through `persistence/agent_query.py` and `artifact_manifest.json`; raw SQL and arbitrary path reads stay forbidden.
- Nuxt3 displays run state, artifacts, notifications, source health, content review, quality flags, and shadow comparison.
- Write paths are limited to human review records and notification acknowledgement/resolution.
- Publication, platform login, browser sidecars, and LLM fact mutation remain deferred.

Reference baseline:

- [LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview)：orchestration runtime for durable execution, persistence, human-in-the-loop, and stateful agents.
- [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)：human-in-the-loop interruption and resume model for review gates.
- [LangChain structured output](https://docs.langchain.com/oss/python/langchain/structured-output)：schema-based structured responses for agents and LLM calls.
- [LangSmith evaluation](https://docs.langchain.com/langsmith/evaluation)：curated datasets, offline/online evaluations, and experiment comparison after LLM behavior needs regression testing.

## Non-Negotiable Boundaries

- External tools never bypass the project artifacts.
- Search pages and comments are heat/context evidence, not fact verification.
- RAG/LLM classifiers can judge observed material, but cannot create facts, URLs, or source claims.
- Login-required access, publication, and fact-state mutation require human approval.
- A dependency becomes default only after tests and at least one live run show better precision, recall, cost, or observability.
