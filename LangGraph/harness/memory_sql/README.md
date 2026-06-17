# Memory SQL Harness

This harness area covers `MEM-*` issues from `docs/issues.md`.

Current MVP cases are implemented as unit tests in `LangGraph/tests/test_sqlite_mirror.py`
and `LangGraph/tests/test_agent_db_query.py`:

- `H-MEM-001`: ingest a small output directory and verify row counts match core artifacts.
- `H-MEM-003`: query the SQLite mirror through `agent_query.py` read-only whitelist commands.
- Idempotency: ingesting the same `run_id` twice replaces the snapshot instead of duplicating rows.
- Publish lifecycle seed: final stories default to `publish_status=unpublished`; platform posts default to `publish_status=draft`.

Add JSON fixtures here when cross-run historical import, event-store clustering, or RAG retrieval needs replayable sample data.
