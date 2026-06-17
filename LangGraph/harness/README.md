# LangGraph Harness

This directory stores replayable fixtures for graph nodes, deterministic tools, and later agent/LLM shadow-mode checks.

Issue mapping lives in `docs/issues.md`. Harness cases should use IDs from that document, for example:

- `H-RUN-001` for run trace and notification artifacts.
- `H-COL-001` for source collection retry behavior.
- `H-MEM-001` for SQLite ingest parity.
- `H-EVI-001` for evidence retrieval.
- `H-SRC-001` for LLM query compression shadow mode.
- `H-PRM-001` for prompt registry validity.
- `H-AG-001` for bounded agent decisions.
- `H-SVC-001` for FastAPI/Nuxt3 internal workbench run listing.

Directory convention:

```text
LangGraph/harness/
  run_trace/
  source_collection/
  search_expansion/
  candidate_filtering/
  evidence_retrieval/
  discussion_heat/
  story_clustering/
  claim_verification/
  story_selection/
  content_quality/
  layout_render/
  operations/
  service_workbench/
  memory_sql/
  prompt_management/
  agent_contracts/
  langchain_adapter/
  shadow_tasks/
```

Unit tests in `LangGraph/tests/` are also harnesses when they pin a design contract. JSON fixtures should be added here when a case needs cross-node replay or human review.

A harness fixture proves a contract or replay case; it does not by itself mean the feature is enabled in the default LangGraph flow. Track default-flow, flagged-node, shadow-mode, offline-tool, and harness-only status in `docs/issues.md`.

When adding a new harness case, first map it to the relevant layer goal in `docs/issues.md#层级目标与验收标准`. The case should prove an acceptance criterion or boundary condition, not only that a command completes successfully.
