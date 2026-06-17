"""Freshness checks that compare candidates with known story memory."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _isoformat(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _normalized_title(title: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]+", title.lower()))


def _generated_candidate_memory_key(candidate: dict[str, Any]) -> str:
    url = str(candidate.get("url") or "").strip().lower().rstrip("/")
    if url:
        return f"url:{url}"
    title = _normalized_title(str(candidate.get("title") or ""))
    if title:
        digest = hashlib.sha1(title.encode("utf-8")).hexdigest()[:16]
        return f"title:{digest}"
    return ""


def _memory_lookup(memory_records: Any) -> dict[str, dict[str, Any]]:
    if isinstance(memory_records, dict):
        return {str(key): dict(value) for key, value in memory_records.items() if isinstance(value, dict)}
    if isinstance(memory_records, list):
        records: dict[str, dict[str, Any]] = {}
        for record in memory_records:
            if not isinstance(record, dict):
                continue
            key = record.get("memory_key") or record.get("story_id") or record.get("id")
            if key:
                records[str(key)] = dict(record)
        return records
    return {}


def _parse_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _candidate_memory_key(candidate: dict[str, Any]) -> str:
    explicit = str(
        candidate.get("memory_key")
        or candidate.get("related_story_id")
        or candidate.get("story_id")
        or ""
    ).strip()
    if explicit:
        return explicit
    return _generated_candidate_memory_key(candidate)


def load_candidate_memory(path: str | Path | None) -> dict[str, dict[str, Any]]:
    if not path:
        return {}
    memory_path = Path(path)
    if not memory_path.exists():
        return {}
    try:
        raw = json.loads(memory_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    records = raw.get("records", raw)
    if not isinstance(records, dict):
        return {}
    return {
        str(key): dict(value)
        for key, value in records.items()
        if isinstance(value, dict)
    }


def _append_unique(values: list[Any], value: Any) -> list[Any]:
    text = str(value or "").strip()
    if not text:
        return values
    if text not in values:
        values.append(text)
    return values


def update_candidate_memory_store(
    path: str | Path,
    candidates: list[dict[str, Any]],
    *,
    seen_at: datetime,
) -> dict[str, Any]:
    records = load_candidate_memory(path)
    new_records = 0
    updated_records = 0
    skipped_records = 0
    seen_at_text = _isoformat(seen_at)

    for candidate in candidates:
        if not isinstance(candidate, dict):
            skipped_records += 1
            continue
        key = _candidate_memory_key(candidate)
        if not key:
            skipped_records += 1
            continue

        record = records.get(key)
        if record is None:
            record = {
                "memory_key": key,
                "first_seen_at": seen_at_text,
                "last_seen_at": seen_at_text,
                "seen_count": 0,
                "titles": [],
                "urls": [],
                "source_ids": [],
                "published_at_values": [],
            }
            records[key] = record
            new_records += 1
        else:
            updated_records += 1

        record["last_seen_at"] = seen_at_text
        record["seen_count"] = int(record.get("seen_count", 0)) + 1
        _append_unique(record.setdefault("titles", []), candidate.get("title"))
        _append_unique(record.setdefault("urls", []), candidate.get("url"))
        _append_unique(record.setdefault("source_ids", []), candidate.get("source_id"))
        _append_unique(
            record.setdefault("published_at_values", []),
            candidate.get("published_at") or candidate.get("observed_at"),
        )
        record["title"] = str(candidate.get("title") or record.get("title") or "")
        record["url"] = str(candidate.get("url") or record.get("url") or "")
        record["source_id"] = str(candidate.get("source_id") or record.get("source_id") or "")

    memory_path = Path(path)
    memory_path.parent.mkdir(parents=True, exist_ok=True)
    memory_path.write_text(
        json.dumps(
            {
                "version": "0.1.0",
                "updated_at": seen_at_text,
                "records": records,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return {
        "memory_path": str(memory_path),
        "total_records": len(records),
        "new_records": new_records,
        "updated_records": updated_records,
        "skipped_records": skipped_records,
    }


def _is_current_update(candidate: dict[str, Any]) -> bool:
    if bool(candidate.get("is_current_update")):
        return True
    tags = {str(tag).lower() for tag in candidate.get("tags", [])}
    if tags & {"current_update", "follow_up_update", "new_detail"}:
        return True
    signals = candidate.get("heat_signals", {})
    return isinstance(signals, dict) and bool(signals.get("current_update"))


def apply_memory_freshness(
    candidate: dict[str, Any],
    *,
    memory_records: Any,
    now: datetime,
    lookback_hours: int,
) -> dict[str, Any]:
    enriched = dict(candidate)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)

    key = _candidate_memory_key(candidate)
    lookup = _memory_lookup(memory_records)
    record = lookup.get(key) if key else None

    if record is None:
        enriched["memory_status"] = "new_story"
        enriched["memory_reasons"] = ["no-related-memory-record"]
        return enriched

    first_seen_at = _parse_datetime(record.get("first_seen_at"))
    if first_seen_at is None:
        enriched["memory_status"] = "known_story_unknown_first_seen"
        enriched["memory_reasons"] = ["related-memory-record-without-first-seen-time"]
        return enriched

    age_hours = (now - first_seen_at).total_seconds() / 3600
    if age_hours <= lookback_hours:
        enriched["memory_status"] = "known_recent_story"
        enriched["memory_reasons"] = ["related-story-first-seen-inside-lookback"]
        return enriched

    if _is_current_update(candidate):
        enriched["memory_status"] = "follow_up_update"
        enriched["memory_reasons"] = [
            "related-story-first-seen-outside-lookback",
            "candidate-has-current-update-signal",
        ]
        return enriched

    enriched["memory_status"] = "late_repost"
    enriched["memory_reasons"] = [
        "related-story-first-seen-outside-lookback",
        "candidate-lacks-current-update-signal",
    ]
    return enriched
