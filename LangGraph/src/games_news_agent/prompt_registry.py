"""Prompt registry — load, validate, and manage failure contracts for LLM prompt tasks.

PRM-001: Every prompt used by an LLM or agent shadow task must be declared in
prompt_registry.json with a stable prompt_id, input artifacts, output schema,
fallback behavior, and harness cases.

PRM-002: When a prompt fails (file missing, parse error, schema mismatch,
timeout, refusal), write a structured failure record and use the registered
deterministic fallback instead.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def load_prompt_registry(registry_path: str | Path) -> dict[str, Any]:
    """Load and return the prompt registry from a JSON file.

    Args:
        registry_path: Absolute or relative path to prompt_registry.json.

    Returns:
        The parsed registry dict with top-level ``schema_version`` and
        ``prompts`` keys.

    Raises:
        FileNotFoundError: If the registry file does not exist.
        json.JSONDecodeError: If the file contains invalid JSON.
    """
    file_path = Path(registry_path)
    if not file_path.exists():
        raise FileNotFoundError(f"Prompt registry not found: {file_path}")
    with file_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


# ---------------------------------------------------------------------------
# Lookup
# ---------------------------------------------------------------------------


def get_prompt_config(prompt_id: str, registry: dict[str, Any]) -> dict[str, Any]:
    """Return the config entry for *prompt_id*.

    Args:
        prompt_id: The key in ``registry["prompts"]`` (e.g. ``"claim_verification"``).
        registry: A registry dict previously loaded via :func:`load_prompt_registry`.

    Returns:
        The prompt config dict.

    Raises:
        KeyError: If *prompt_id* is not found in the registry.
    """
    prompts = registry.get("prompts", {})
    if prompt_id in prompts:
        return prompts[prompt_id]
    for config in prompts.values():
        if isinstance(config, dict) and config.get("prompt_id") == prompt_id:
            return config
    raise KeyError(f"Prompt id '{prompt_id}' not found in registry")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_prompt_file_exists(
    prompt_config: dict[str, Any],
    prompts_dir: str | Path,
) -> bool:
    """Return True if the prompt file referenced by *prompt_config* exists.

    A ``null`` or missing ``prompt_file`` is treated as a deliberate
    no-file entry (e.g. a purely deterministic node) and returns True.
    """
    prompt_file = prompt_config.get("prompt_file")
    if prompt_file is None:
        return True
    file_path = Path(prompts_dir) / prompt_file
    return file_path.exists()


def validate_all_prompts(
    registry: dict[str, Any],
    prompts_dir: str | Path,
) -> list[dict[str, Any]]:
    """Validate every prompt entry in *registry* and return a list of errors.

    Each error dict has keys: ``prompt_id``, ``error_type``, ``message``.

    Checks performed:
        - ``prompt_file`` exists on disk (unless null).
        - ``input_artifacts`` is a non-empty list.
        - ``output_schema`` is a non-empty string.
        - ``fallback`` is a non-empty string.
    """
    errors: list[dict[str, Any]] = []
    prompts = registry.get("prompts", {})
    prompts_dir_path = Path(prompts_dir)

    for prompt_id, config in prompts.items():
        # prompt_file existence
        if not validate_prompt_file_exists(config, prompts_dir_path):
            errors.append(
                {
                    "prompt_id": prompt_id,
                    "error_type": "missing_prompt_file",
                    "message": (
                        f"Prompt file '{config.get('prompt_file')}' not found "
                        f"in {prompts_dir_path}"
                    ),
                }
            )

        # input_artifacts must be a non-empty list
        input_artifacts = config.get("input_artifacts", [])
        if not isinstance(input_artifacts, list) or len(input_artifacts) == 0:
            errors.append(
                {
                    "prompt_id": prompt_id,
                    "error_type": "missing_input_artifacts",
                    "message": "input_artifacts must be a non-empty list",
                }
            )

        # output_schema must be a non-empty string
        output_schema = config.get("output_schema", "")
        if not isinstance(output_schema, str) or not output_schema.strip():
            errors.append(
                {
                    "prompt_id": prompt_id,
                    "error_type": "missing_output_schema",
                    "message": "output_schema must be a non-empty string",
                }
            )

        # fallback must be a non-empty string
        fallback = config.get("fallback", "")
        if not isinstance(fallback, str) or not fallback.strip():
            errors.append(
                {
                    "prompt_id": prompt_id,
                    "error_type": "missing_fallback",
                    "message": "fallback must be a non-empty string",
                }
            )

        # New registry contract fields are optional for small unit-test
        # registries, but validated when present.
        status = config.get("status")
        if status is not None and status not in {"active", "shadow", "deferred"}:
            errors.append(
                {
                    "prompt_id": prompt_id,
                    "error_type": "invalid_status",
                    "message": "status must be active, shadow, or deferred",
                }
            )
        default_enabled = config.get("default_enabled")
        if default_enabled is not None and not isinstance(default_enabled, bool):
            errors.append(
                {
                    "prompt_id": prompt_id,
                    "error_type": "invalid_default_enabled",
                    "message": "default_enabled must be a boolean when present",
                }
            )

    return errors


# ---------------------------------------------------------------------------
# Failure contract (PRM-002)
# ---------------------------------------------------------------------------


def build_prompt_failure(
    prompt_id: str,
    error_type: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a structured failure record matching the PRM-002 contract.

    Args:
        prompt_id: The prompt key that failed (e.g. ``"claim_verification"``).
        error_type: One of ``"missing_prompt_file"``, ``"parse_error"``,
            ``"schema_mismatch"``, ``"timeout"``, ``"refusal"``,
            ``"provider_error"``.
        details: Optional dict with extra context such as ``"task_type"``,
            ``"input_artifact_refs"``, ``"raw_output_prefix"``,
            ``"exception_message"``.

    Returns:
        A failure dict with keys ``prompt_id``, ``error_type``,
        ``timestamp``, ``details``, ``fallback_used``.
    """
    record: dict[str, Any] = {
        "prompt_id": prompt_id,
        "error_type": error_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "details": details or {},
        "fallback_used": None,
    }
    return record


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------


def record_prompt_failure(
    failure: dict[str, Any],
    failures_path: str | Path,
) -> None:
    """Append a failure record to a JSON-array failures file.

    Creates the file (and parent directories) if they do not exist.

    Args:
        failure: A failure dict from :func:`build_prompt_failure`.
        failures_path: Path to the JSON failures file (e.g.
            ``"outputs/prompt_failures.json"``).
    """
    file_path = Path(failures_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    existing: list[dict[str, Any]] = []
    if file_path.exists():
        try:
            with file_path.open("r", encoding="utf-8") as handle:
                existing = json.load(handle)
        except (json.JSONDecodeError, FileNotFoundError):
            existing = []

    if not isinstance(existing, list):
        existing = []

    existing.append(failure)

    with file_path.open("w", encoding="utf-8") as handle:
        json.dump(existing, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


# ---------------------------------------------------------------------------
# Convenience: resolve fallback for a prompt
# ---------------------------------------------------------------------------


def resolve_fallback(
    prompt_id: str,
    registry: dict[str, Any],
) -> str | None:
    """Return the registered fallback strategy for *prompt_id*.

    Returns None if the prompt_id or its fallback is missing.
    """
    try:
        config = get_prompt_config(prompt_id, registry)
    except KeyError:
        return None
    fallback = config.get("fallback")
    if isinstance(fallback, str) and fallback.strip():
        return fallback
    return None


# ---------------------------------------------------------------------------
# Convenience: look up all prompts whose prompt_file exists
# ---------------------------------------------------------------------------


def list_available_prompts(
    registry: dict[str, Any],
    prompts_dir: str | Path,
) -> list[str]:
    """Return prompt_ids whose ``prompt_file`` exists on disk."""
    available: list[str] = []
    for prompt_id, config in registry.get("prompts", {}).items():
        if validate_prompt_file_exists(config, prompts_dir):
            available.append(prompt_id)
    return available
