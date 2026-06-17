# Prompt Management

This directory stores human-readable prompt templates for optional LLM and agent shadow tasks.

The source of truth is `prompt_registry.json`. Code should resolve prompts through the registry rather than hard-coding filenames. The registry makes prompt use auditable, testable, and safe to disable.

## Rules

- Every prompt must have a stable `prompt_id` in the form `<domain>.<task>.vN`.
- Every prompt must declare `task_type`, `issue_ids`, `input_artifacts`, `output_artifact`, `output_schema`, `fallback`, and `harness_cases`.
- Prompt output must be structured JSON. Markdown, explanations, or partial natural-language output must be treated as parse failure unless the registry explicitly says otherwise.
- LLM output can write only `*_results.json`, `*_failures.json`, review packs, or suggestions. It must not directly mutate facts, claim verification state, ranking, source URLs, or publish status.
- Prompt files may include human-facing instructions, but artifact contracts live in the registry.
- Deferred prompts can stay in this directory, but their registry status must be `deferred` and `default_enabled` must be `false`.

## Status Values

- `active`: callable behind an explicit CLI flag or node option.
- `shadow`: request/result artifact exists, but output does not affect final facts or ranking by default.
- `deferred`: planned prompt kept for design continuity; not callable in the current flow.

## Failure Handling

For every LLM task:

1. Build a `*_requests.json` record with `prompt_id`, `prompt_version`, `input_artifact_refs`, and `output_schema`.
2. Parse model output as JSON.
3. Validate required fields from `output_schema`.
4. If parsing or validation fails, write `*_failures.json`, emit a warning notification, and use the deterministic fallback.
5. Apply results only in the narrow stage declared by the registry.

Harness cases live in `LangGraph/harness/prompt_management/`.
