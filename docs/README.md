# Documentation Map

This directory separates current project direction from historical planning notes.

## Canonical Docs

- `roadmap.md`: current product and engineering roadmap. Keep only decisions that affect future direction.
- `issues.md`: global issue, layer goal, acceptance, and harness index by functional layer. Use this when adding work, tests, or user-facing capability descriptions.
- `experience.md`: dated run reviews, tuning lessons, and implementation audit notes. Link from roadmap instead of copying long retrospectives there.
- `toolchain_decision_matrix.md`: build-vs-buy decisions for libraries, frameworks, APIs, LangChain/LangGraph, crawler tools, RAG, tracing, and evaluation.
- `retrieval_strategy.md`: detailed retrieval/source/social heat strategy notes.
- `post_collection_selection_strategy.md`: post-collection filtering, selection, dedup, and backfill strategy.
- `release_date_strategy.md`: release-date calendar and game-date memory design.
- `long_lookback_eval.md`: long-window evaluation commands and expected diagnostics.
- `../智览AI项目组成参考.md`: extracted reference notes from the attached PDF. Use it only as architecture/toolchain inspiration for FastAPI, Nuxt 3, Vue, Redis, RAG, and dashboard planning; it does not override this project's roadmap.

## Historical Plans

Files under `docs/superpowers/plans/` and `docs/superpowers/specs/` are historical design and execution notes. They are kept for traceability, but they should not override the canonical docs above.

## Prompt Docs

Prompt templates live under `LangGraph/prompts/`. Their registry is `LangGraph/prompts/prompt_registry.json`; do not treat a prompt file as callable unless it appears in that registry.

## Stale Doc Rule

When a document conflicts with the current implementation:

1. Update the canonical doc first.
2. Move detailed observations to `experience.md` if they are still useful.
3. Mark old planning docs as historical through this map rather than deleting them, unless they are duplicated generated output with no unique decision value.
