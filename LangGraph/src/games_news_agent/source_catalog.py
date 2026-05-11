"""Source catalog loading."""

from __future__ import annotations

from pathlib import Path

import yaml

from .schemas import SourceConfig


DEFAULT_SOURCE_PATH = Path(__file__).resolve().parents[2] / "config" / "sources.yaml"


def load_sources(path: Path | None = None) -> list[SourceConfig]:
    source_path = path or DEFAULT_SOURCE_PATH
    with source_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    sources = raw.get("sources", [])
    if not isinstance(sources, list):
        raise ValueError(f"`sources` must be a list in {source_path}")

    return [SourceConfig.model_validate(item) for item in sources]
