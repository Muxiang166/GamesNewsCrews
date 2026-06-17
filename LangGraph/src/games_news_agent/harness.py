"""Harness fixtures for repeatable offline pipeline runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .io import read_json


DEFAULT_HARNESS_DIR = Path(__file__).resolve().parents[2] / "harness"


def load_harness_candidates(harness_dir: str | Path | None = None) -> list[dict[str, Any]]:
    root = Path(harness_dir) if harness_dir else DEFAULT_HARNESS_DIR
    path = root / "sample_candidates.json"
    if not path.exists():
        return []
    data = read_json(path)
    if not isinstance(data, list):
        raise ValueError(f"Harness candidates must be a list: {path}")
    return [dict(item) for item in data]
