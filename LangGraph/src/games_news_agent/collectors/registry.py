"""Collector registry for configured live sources."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from time import perf_counter
from typing import Any, Callable
from urllib.parse import urlencode, urljoin

from ..fetching import FetchResult, HttpFetcher
from ..site_parser_contract import (
    SiteParserContract,
    parser_contract_from_source_config,
    validate_parser_contract,
)
from .listing import ListingCollector
from .rss import RssCollector
from .web import WebPageCollector


SUPPORTED_RSS_COLLECTORS = {"rss", "media_rss"}
SUPPORTED_LISTING_COLLECTORS = {"listing_page", "media_listing", "web_listing"}
SUPPORTED_INCREMENTAL_LISTING_COLLECTORS = {
    "incremental_listing",
    "media_incremental_listing",
}
SUPPORTED_JSONP_PAGED_LISTING_COLLECTORS = {
    "jsonp_paged_listing",
    "media_jsonp_paged_listing",
}
SUPPORTED_LIVE_COLLECTORS = (
    SUPPORTED_RSS_COLLECTORS
    | SUPPORTED_LISTING_COLLECTORS
    | SUPPORTED_INCREMENTAL_LISTING_COLLECTORS
    | SUPPORTED_JSONP_PAGED_LISTING_COLLECTORS
)
ProgressCallback = Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class CollectionResult:
    candidates: list[dict[str, Any]] = field(default_factory=list)
    raw_sources: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    diagnostics: list[dict[str, Any]] = field(default_factory=list)


def _source_url(source: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = source.get(key)
        if value:
            return str(value)
    return str(source.get("url", ""))


def _source_urls(
    source: dict[str, Any],
    *,
    list_key: str,
    scalar_key: str,
    fallback_key: str = "url",
) -> list[str]:
    urls: list[str] = []
    values = source.get(list_key, [])
    if isinstance(values, list):
        for value in values:
            url = str(value).strip()
            if url and url not in urls:
                urls.append(url)
    url = str(source.get(scalar_key, "")).strip()
    if url and url not in urls:
        urls.append(url)
    if not urls:
        url = str(source.get(fallback_key, "")).strip()
        if url and url not in urls:
            urls.append(url)
    return urls


def _source_entries(
    source: dict[str, Any],
    *,
    entries_key: str,
    list_key: str,
    scalar_key: str,
    fallback_key: str = "url",
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add_entry(value: Any) -> None:
        if value is None:
            return
        if isinstance(value, dict):
            url = str(value.get("url") or value.get("href") or "").strip()
            if not url or url in seen:
                return
            entry = dict(value)
            entry["url"] = url
        else:
            url = str(value).strip()
            if not url or url.lower() == "none" or url in seen:
                return
            entry = {"url": url}
        seen.add(url)
        entries.append(entry)

    configured_entries = source.get(entries_key, [])
    if isinstance(configured_entries, list):
        for value in configured_entries:
            add_entry(value)

    values = source.get(list_key, [])
    if isinstance(values, list):
        for value in values:
            add_entry(value)

    add_entry(source.get(scalar_key, ""))
    if not entries:
        add_entry(source.get(fallback_key, ""))
    return entries


def _entry_url(entry: dict[str, Any]) -> str:
    return str(entry.get("url") or "").strip()


def _pagination_entries(source: dict[str, Any]) -> list[dict[str, Any]]:
    config = source.get("collector_config", {})
    if not isinstance(config, dict):
        return []
    entries = config.get("pagination_entries", [])
    if not isinstance(entries, list):
        return []

    normalized: list[dict[str, Any]] = []
    for value in entries:
        if not isinstance(value, dict):
            continue
        node_id = str(value.get("node_id") or value.get("nodeId") or "").strip()
        if not node_id:
            continue
        entry = dict(value)
        entry["node_id"] = node_id
        entry.setdefault("is_node_id", "true")
        entry.setdefault("label", node_id)
        normalized.append(entry)
    return normalized


def _entry_tags(default_tags: list[str], entry: dict[str, Any]) -> list[str]:
    tags = list(default_tags)
    entry_tags = entry.get("tags", [])
    if isinstance(entry_tags, str):
        entry_tags = [entry_tags]
    if isinstance(entry_tags, list):
        for tag in entry_tags:
            text = str(tag).strip()
            if text and text not in tags:
                tags.append(text)
    theme = str(entry.get("theme_section") or "").strip()
    if theme and theme not in tags:
        tags.append(theme)
    return tags


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return []


def _int_config(config: dict[str, Any], key: str, default: int) -> int:
    value = config.get(key, default)
    if isinstance(value, int):
        return max(value, 0)
    try:
        return max(int(str(value)), 0)
    except (TypeError, ValueError):
        return max(default, 0)


def _render_payload_value(value: Any, *, entry: dict[str, Any], page: int) -> Any:
    placeholders = {
        "page": page,
        "node_id": str(entry.get("node_id") or ""),
        "nodeId": str(entry.get("node_id") or ""),
        "is_node_id": str(entry.get("is_node_id") or "true"),
        "isNodeId": str(entry.get("is_node_id") or "true"),
        "label": str(entry.get("label") or ""),
    }
    if isinstance(value, dict):
        return {
            str(key): _render_payload_value(item, entry=entry, page=page)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_render_payload_value(item, entry=entry, page=page) for item in value]
    if isinstance(value, str):
        if value == "{page}":
            return page
        return value.format(**placeholders)
    return value


def _build_jsonp_listing_url(
    config: dict[str, Any],
    *,
    entry: dict[str, Any],
    page: int,
) -> str:
    endpoint = str(config.get("pagination_url") or "").strip()
    if not endpoint:
        return ""
    param_name = str(config.get("pagination_param") or "jsondata").strip() or "jsondata"
    template = config.get("request_payload_template")
    if not isinstance(template, dict):
        template = {
            "type": "updatenodelabel",
            "isCache": True,
            "cacheTime": 60,
            "nodeId": "{node_id}",
            "isNodeId": "{is_node_id}",
            "page": "{page}",
        }
    payload = _render_payload_value(template, entry=entry, page=page)
    query = urlencode(
        {
            param_name: json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
            )
        }
    )
    separator = "&" if "?" in endpoint else "?"
    return f"{endpoint}{separator}{query}"


def _extract_json_response(text: str) -> dict[str, Any]:
    raw = text.strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        pass

    match = re.search(r"^\s*[\w.$]+\((\{.*\})\)\s*;?\s*$", raw, flags=re.DOTALL)
    if not match:
        match = re.search(r"^\s*\((\{.*\})\)\s*;?\s*$", raw, flags=re.DOTALL)
    if not match:
        return {}
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _extract_next_listing_url(
    html: str,
    *,
    current_url: str,
    config: dict[str, Any],
) -> str:
    patterns = _string_list(config.get("next_url_patterns"))
    if not patterns:
        patterns = [
            r'href=["\'](?P<url>[^"\']*?endIndex=\d+[^"\']*)["\'][^>]*>\s*Load More\s*</a>',
        ]
    for pattern in patterns:
        try:
            match = re.search(pattern, html, flags=re.IGNORECASE | re.DOTALL)
        except re.error:
            continue
        if not match:
            continue
        if "url" in match.groupdict():
            value = match.group("url")
        else:
            value = match.group(1)
        next_url = urljoin(current_url, str(value).strip())
        if next_url and next_url != current_url:
            return next_url
    return ""


def _parse_candidate_datetime(value: Any) -> datetime | None:
    if not value:
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


def _candidate_event_time(candidate: dict[str, Any]) -> datetime | None:
    return _parse_candidate_datetime(candidate.get("published_at")) or _parse_candidate_datetime(
        candidate.get("observed_at")
    )


def _page_is_older_than_lookback(
    candidates: list[dict[str, Any]],
    *,
    discovered_at: datetime,
    lookback_hours: int | None,
) -> bool:
    if not lookback_hours or lookback_hours <= 0:
        return False
    if discovered_at.tzinfo is None:
        discovered_at = discovered_at.replace(tzinfo=timezone.utc)
    else:
        discovered_at = discovered_at.astimezone(timezone.utc)
    cutoff = discovered_at - timedelta(hours=lookback_hours)
    event_times = [
        event_time
        for candidate in candidates
        if isinstance(candidate, dict)
        for event_time in [_candidate_event_time(candidate)]
        if event_time is not None
    ]
    return bool(event_times) and all(event_time < cutoff for event_time in event_times)


def _entry_display_fields(entry: dict[str, Any]) -> dict[str, str]:
    fields: dict[str, str] = {}
    for key, output_key in (
        ("url", "source_entry_url"),
        ("label", "source_entry_label"),
        ("name", "source_entry_label"),
        ("theme_section", "source_entry_theme"),
        ("kind", "source_entry_kind"),
    ):
        value = str(entry.get(key) or "").strip()
        if value and output_key not in fields:
            fields[output_key] = value
    return fields


def _apply_entry_metadata(
    candidates: list[dict[str, Any]],
    *,
    entry: dict[str, Any],
    default_tags: list[str],
) -> list[dict[str, Any]]:
    fields = _entry_display_fields(entry)
    tags = _entry_tags(default_tags, entry)
    theme = str(entry.get("theme_section") or "").strip()

    enriched: list[dict[str, Any]] = []
    for candidate in candidates:
        item = dict(candidate)
        for key, value in fields.items():
            item[key] = value
        if theme and not item.get("theme_section"):
            item["theme_section"] = theme
        existing_tags = [str(tag) for tag in item.get("tags", []) if str(tag).strip()]
        merged_tags = list(existing_tags)
        for tag in tags:
            if tag not in merged_tags:
                merged_tags.append(tag)
        item["tags"] = merged_tags
        enriched.append(item)
    return enriched


def _unique_strings(values: list[Any]) -> list[str]:
    unique: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in unique:
            unique.append(text)
    return unique


def _merge_duplicate_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    by_key: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        key = str(candidate.get("url") or candidate.get("title") or "").strip()
        if not key:
            merged.append(dict(candidate))
            continue
        existing = by_key.get(key)
        if existing is None:
            item = dict(candidate)
            entry_theme = str(item.get("source_entry_theme") or "").strip()
            entry_label = str(item.get("source_entry_label") or "").strip()
            entry_url = str(item.get("source_entry_url") or "").strip()
            if entry_theme:
                item["source_entry_themes"] = [entry_theme]
            if entry_label:
                item["source_entry_labels"] = [entry_label]
            if entry_url:
                item["source_entry_urls"] = [entry_url]
            by_key[key] = item
            merged.append(item)
            continue

        existing["tags"] = _unique_strings([*existing.get("tags", []), *candidate.get("tags", [])])
        themes = _unique_strings(
            [
                *existing.get("source_entry_themes", []),
                existing.get("source_entry_theme", ""),
                candidate.get("source_entry_theme", ""),
            ]
        )
        labels = _unique_strings(
            [
                *existing.get("source_entry_labels", []),
                existing.get("source_entry_label", ""),
                candidate.get("source_entry_label", ""),
            ]
        )
        urls = _unique_strings(
            [
                *existing.get("source_entry_urls", []),
                existing.get("source_entry_url", ""),
                candidate.get("source_entry_url", ""),
            ]
        )
        if themes:
            existing["source_entry_themes"] = themes
            existing["source_entry_theme"] = themes[0] if len(themes) == 1 else "multiple"
            if len(themes) == 1:
                existing["theme_section"] = themes[0]
            else:
                existing.pop("theme_section", None)
        if labels:
            existing["source_entry_labels"] = labels
            existing["source_entry_label"] = labels[0] if len(labels) == 1 else "multiple"
        if urls:
            existing["source_entry_urls"] = urls
            existing["source_entry_url"] = urls[0] if len(urls) == 1 else "multiple"
    return merged


def _raw_source_record(
    source: dict[str, Any],
    *,
    url: str,
    collector: str,
    result: FetchResult,
    fetched_at: datetime,
    entry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record = {
        "source_id": source.get("id"),
        "url": url,
        "collector": collector,
        "ok": result.ok,
        "status_code": result.status_code,
        "content_type": result.content_type,
        "error": result.error,
        "error_type": result.error_type,
        "retryable": result.retryable,
        "attempts": result.attempts,
        "fetched_at": fetched_at.isoformat(),
    }
    if entry:
        record.update(_entry_display_fields(entry))
    return record


def _fetch_error_record(
    source_id: str,
    url: str,
    result: FetchResult,
    *,
    stage: str = "",
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "source_id": source_id,
        "url": url,
        "error": result.error,
        "error_type": result.error_type,
        "retryable": result.retryable,
        "attempts": result.attempts,
    }
    if stage:
        record["stage"] = stage
    return record


def _emit_progress(progress_callback: ProgressCallback | None, event: dict[str, Any]) -> None:
    if progress_callback is not None:
        progress_callback(event)


def _elapsed_seconds(started_at: float) -> float:
    return round(max(perf_counter() - started_at, 0.0), 2)


def _detail_time_backfill_limit(source: dict[str, Any]) -> int:
    config = source.get("collector_config", {})
    if not isinstance(config, dict):
        return 0
    value = config.get("detail_time_backfill_limit", 0)
    if isinstance(value, int):
        return max(value, 0)
    try:
        return max(int(str(value)), 0)
    except ValueError:
        return 0


def _needs_time_backfill(candidate: dict[str, Any]) -> bool:
    return not candidate.get("published_at") and not candidate.get("observed_at")


def _backfill_listing_candidate_times(
    source: dict[str, Any],
    *,
    candidates: list[dict[str, Any]],
    fetcher: HttpFetcher,
    fetched_at: datetime,
    limit: int,
) -> tuple[int, list[dict[str, Any]], list[dict[str, Any]]]:
    if limit <= 0:
        return 0, [], []

    source_id = str(source.get("id", ""))
    raw_sources: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    backfilled = 0
    attempted = 0
    for candidate in candidates:
        if attempted >= limit:
            break
        if not _needs_time_backfill(candidate):
            continue
        url = str(candidate.get("url", "")).strip()
        if not url:
            continue
        attempted += 1
        fetch_result = fetcher.fetch_text(url)
        raw_sources.append(
            _raw_source_record(
                source,
                url=url,
                collector="detail_time_backfill",
                result=fetch_result,
                fetched_at=fetched_at,
            )
        )
        if not fetch_result.ok:
            errors.append(
                _fetch_error_record(
                    source_id,
                    url,
                    fetch_result,
                    stage="detail_time_backfill",
                )
            )
            continue
        document = WebPageCollector(source_id=source_id).parse_html(
            url=url,
            html=fetch_result.text,
            fetched_at=fetched_at,
        )
        published_at = document.get("published_at")
        if not published_at:
            continue
        candidate["published_at"] = published_at
        candidate["observed_at"] = published_at
        backfilled += 1
    return backfilled, raw_sources, errors


def collect_from_source(
    source: dict[str, Any],
    *,
    fetcher: HttpFetcher,
    discovered_at: datetime,
    query: str,
    lookback_hours: int | None = None,
    progress_callback: ProgressCallback | None = None,
) -> CollectionResult:
    collector_name = str(source.get("collector", "")).strip()
    source_id = str(source.get("id", "")).strip()
    default_tags = [str(tag) for tag in source.get("tags", [])]
    started_at = perf_counter()

    # ---- parser contract validation (advisory) ----
    contract_errors: list[str] = []
    if collector_name in SUPPORTED_LIVE_COLLECTORS:
        _contract, contract_errors = validate_source_contract(source)

    if collector_name in SUPPORTED_RSS_COLLECTORS:
        entries = _source_entries(
            source,
            entries_key="feed_entries",
            list_key="feed_urls",
            scalar_key="feed_url",
        )
    elif collector_name in SUPPORTED_LISTING_COLLECTORS or collector_name in SUPPORTED_INCREMENTAL_LISTING_COLLECTORS:
        entries = _source_entries(
            source,
            entries_key="page_entries",
            list_key="page_urls",
            scalar_key="page_url",
        )
    elif collector_name in SUPPORTED_JSONP_PAGED_LISTING_COLLECTORS:
        entries = _pagination_entries(source)
    else:
        entries = []

    _emit_progress(
        progress_callback,
        {
            "event": "source_start",
            "source_id": source_id,
            "source_name": source.get("name") or source_id,
            "collector": collector_name,
            "entry_url_count": len(entries),
        },
    )

    def finish(result: CollectionResult) -> CollectionResult:
        if result.candidates:
            result = CollectionResult(
                candidates=_merge_duplicate_candidates(result.candidates),
                raw_sources=result.raw_sources,
                errors=result.errors,
                diagnostics=result.diagnostics,
            )
        if contract_errors:
            result.diagnostics.append(
                {
                    "source_id": source_id,
                    "collector": collector_name,
                    "contract_valid": False,
                    "contract_errors": contract_errors,
                }
            )
        _emit_progress(
            progress_callback,
            {
                "event": "source_done",
                "source_id": source_id,
                "source_name": source.get("name") or source_id,
                "collector": collector_name,
                "entry_url_count": len(entries),
                "raw_fetch_count": len(result.raw_sources),
                "candidate_count": len(result.candidates),
                "error_count": len(result.errors),
                "elapsed_seconds": _elapsed_seconds(started_at),
            },
        )
        return result

    if collector_name in SUPPORTED_RSS_COLLECTORS:
        combined = CollectionResult()
        for entry in entries:
            url = _entry_url(entry)
            fetch_result = fetcher.fetch_text(url)
            combined.raw_sources.append(
                _raw_source_record(
                    source,
                    url=url,
                    collector=collector_name,
                    result=fetch_result,
                    fetched_at=discovered_at,
                    entry=entry,
                )
            )
            if not fetch_result.ok:
                combined.errors.append(_fetch_error_record(source_id, url, fetch_result))
                continue
            try:
                candidates = RssCollector(
                    source_id=source_id,
                    query=query,
                    default_tags=_entry_tags(default_tags, entry),
                ).collect_from_text(fetch_result.text, discovered_at=discovered_at)
            except Exception as exc:  # XML parsers surface multiple narrow exceptions.
                combined.errors.append({"source_id": source_id, "url": url, "error": str(exc)})
                continue
            combined.candidates.extend(
                _apply_entry_metadata(candidates, entry=entry, default_tags=default_tags)
            )
        return finish(combined)

    if collector_name in SUPPORTED_INCREMENTAL_LISTING_COLLECTORS:
        combined = CollectionResult()
        config = source.get("collector_config", {})
        if not isinstance(config, dict):
            config = {}
        raw_section_map = config.get("section_node_theme_map") or {}
        if not isinstance(raw_section_map, dict):
            raw_section_map = {}
        section_node_theme_map = {
            str(nodeid): str(theme)
            for nodeid, theme in raw_section_map.items()
            if str(nodeid).strip() and str(theme).strip()
        }
        max_pages = _int_config(config, "max_pages_per_entry", 3)
        stale_page_stop_count = _int_config(config, "stale_page_stop_count", 1)
        for entry in entries:
            next_url = _entry_url(entry)
            seen_page_urls: set[str] = set()
            seen_candidate_urls: set[str] = set()
            stale_pages = 0
            for page in range(1, max_pages + 1):
                if not next_url or next_url in seen_page_urls:
                    break
                url = next_url
                seen_page_urls.add(url)
                fetch_result = fetcher.fetch_text(url)
                combined.raw_sources.append(
                    _raw_source_record(
                        source,
                        url=url,
                        collector=collector_name,
                        result=fetch_result,
                        fetched_at=discovered_at,
                        entry=entry,
                    )
                )
                if not fetch_result.ok:
                    combined.errors.append(_fetch_error_record(source_id, url, fetch_result))
                    break

                listing_result = ListingCollector(
                    source_id=source_id,
                    query=query,
                    default_tags=_entry_tags(default_tags, entry),
                    section_node_theme_map=section_node_theme_map,
                    article_url_patterns=_string_list(config.get("article_url_patterns")),
                ).collect_with_diagnostics(
                    fetch_result.text,
                    base_url=url,
                    discovered_at=discovered_at,
                )
                candidates = _apply_entry_metadata(
                    listing_result.candidates,
                    entry=entry,
                    default_tags=default_tags,
                )
                unique_page_candidates: list[dict[str, Any]] = []
                for candidate in candidates:
                    candidate_url = str(candidate.get("url") or "").strip()
                    if candidate_url and candidate_url in seen_candidate_urls:
                        continue
                    if candidate_url:
                        seen_candidate_urls.add(candidate_url)
                    candidate["source_pagination_page"] = page
                    candidate["source_pagination_url"] = url
                    unique_page_candidates.append(candidate)

                next_url = _extract_next_listing_url(
                    fetch_result.text,
                    current_url=url,
                    config=config,
                )
                diagnostics = dict(listing_result.diagnostics)
                diagnostics.update(_entry_display_fields(entry))
                diagnostics["entry_url"] = url
                diagnostics["status_code"] = fetch_result.status_code
                diagnostics["content_type"] = fetch_result.content_type
                diagnostics["pagination_page"] = page
                diagnostics["next_page_url"] = next_url
                diagnostics["new_candidate_count"] = len(unique_page_candidates)
                diagnostics["pagination_stale_page"] = _page_is_older_than_lookback(
                    unique_page_candidates,
                    discovered_at=discovered_at,
                    lookback_hours=lookback_hours,
                )
                stop_reason = ""
                if not unique_page_candidates:
                    stop_reason = "no_new_candidates"
                elif diagnostics["pagination_stale_page"] and stale_page_stop_count and stale_pages + 1 >= stale_page_stop_count:
                    stop_reason = "stale_page_limit"
                elif not next_url:
                    stop_reason = "no_next_page"
                elif next_url in seen_page_urls:
                    stop_reason = "next_page_already_seen"
                elif page >= max_pages:
                    stop_reason = "max_pages_reached"
                diagnostics["pagination_stop_reason"] = stop_reason
                combined.diagnostics.append(diagnostics)
                combined.candidates.extend(unique_page_candidates)

                if not unique_page_candidates:
                    break
                if diagnostics["pagination_stale_page"]:
                    stale_pages += 1
                else:
                    stale_pages = 0
                if stale_page_stop_count and stale_pages >= stale_page_stop_count:
                    break

        backfill_limit = _detail_time_backfill_limit(source)
        backfill_needed = sum(1 for candidate in combined.candidates if _needs_time_backfill(candidate))
        if backfill_limit > 0 and backfill_needed:
            _emit_progress(
                progress_callback,
                {
                    "event": "detail_time_backfill_start",
                    "source_id": source_id,
                    "source_name": source.get("name") or source_id,
                    "needed": backfill_needed,
                    "limit": min(backfill_limit, backfill_needed),
                },
            )
            backfill_started_at = perf_counter()
            backfilled, detail_raw, detail_errors = _backfill_listing_candidate_times(
                source,
                candidates=combined.candidates,
                fetcher=fetcher,
                fetched_at=discovered_at,
                limit=backfill_limit,
            )
            _emit_progress(
                progress_callback,
                {
                    "event": "detail_time_backfill_done",
                    "source_id": source_id,
                    "source_name": source.get("name") or source_id,
                    "attempted": len(detail_raw),
                    "backfilled": backfilled,
                    "error_count": len(detail_errors),
                    "elapsed_seconds": _elapsed_seconds(backfill_started_at),
                },
            )
            combined.raw_sources.extend(detail_raw)
            combined.errors.extend(detail_errors)
            if combined.diagnostics:
                combined.diagnostics[0]["detail_time_backfill_count"] = backfilled

        return finish(combined)

    if collector_name in SUPPORTED_JSONP_PAGED_LISTING_COLLECTORS:
        combined = CollectionResult()
        config = source.get("collector_config", {})
        if not isinstance(config, dict):
            config = {}
        base_url = _source_url(source, "page_url", "url")
        max_pages = _int_config(config, "max_pages_per_entry", 3)
        stale_page_stop_count = _int_config(config, "stale_page_stop_count", 1)
        body_field = str(config.get("response_body_field") or "body").strip() or "body"
        total_pages_field = str(config.get("response_total_pages_field") or "totalPages").strip()
        raw_section_map = config.get("section_node_theme_map") or {}
        if not isinstance(raw_section_map, dict):
            raw_section_map = {}
        section_node_theme_map = {
            str(nodeid): str(theme)
            for nodeid, theme in raw_section_map.items()
            if str(nodeid).strip() and str(theme).strip()
        }

        for entry in entries:
            stale_pages = 0
            for page in range(1, max_pages + 1):
                url = _build_jsonp_listing_url(config, entry=entry, page=page)
                if not url:
                    combined.errors.append(
                        {
                            "source_id": source_id,
                            "collector": collector_name,
                            "error": "missing_pagination_url",
                        }
                    )
                    break

                fetch_result = fetcher.fetch_text(url)
                combined.raw_sources.append(
                    _raw_source_record(
                        source,
                        url=url,
                        collector=collector_name,
                        result=fetch_result,
                        fetched_at=discovered_at,
                        entry=entry,
                    )
                )
                if not fetch_result.ok:
                    combined.errors.append(_fetch_error_record(source_id, url, fetch_result))
                    break

                payload = _extract_json_response(fetch_result.text)
                body = str(payload.get(body_field) or "")
                total_pages = payload.get(total_pages_field) if total_pages_field else None
                if not body:
                    combined.diagnostics.append(
                        {
                            "source_id": source_id,
                            "entry_url": url,
                            "collector": collector_name,
                            "pagination_page": page,
                            "pagination_node_id": entry.get("node_id"),
                            "pagination_label": entry.get("label"),
                            "candidate_count": 0,
                            "parse_warning_count": 1,
                            "pagination_total_pages": total_pages,
                            "status_code": fetch_result.status_code,
                            "content_type": fetch_result.content_type,
                        }
                    )
                    break

                listing_result = ListingCollector(
                    source_id=source_id,
                    query=query,
                    default_tags=_entry_tags(default_tags, entry),
                    section_node_theme_map=section_node_theme_map,
                    article_url_patterns=_string_list(config.get("article_url_patterns")),
                ).collect_with_diagnostics(
                    body,
                    base_url=base_url,
                    discovered_at=discovered_at,
                )
                candidates = _apply_entry_metadata(
                    listing_result.candidates,
                    entry=entry,
                    default_tags=default_tags,
                )
                for candidate in candidates:
                    candidate["source_pagination_page"] = page
                    candidate["source_pagination_node_id"] = str(entry.get("node_id") or "")
                    candidate["source_pagination_label"] = str(entry.get("label") or "")

                diagnostics = dict(listing_result.diagnostics)
                diagnostics["entry_url"] = url
                diagnostics["status_code"] = fetch_result.status_code
                diagnostics["content_type"] = fetch_result.content_type
                diagnostics["pagination_page"] = page
                diagnostics["pagination_node_id"] = entry.get("node_id")
                diagnostics["pagination_label"] = entry.get("label")
                diagnostics["pagination_total_pages"] = total_pages
                diagnostics["pagination_stale_page"] = _page_is_older_than_lookback(
                    candidates,
                    discovered_at=discovered_at,
                    lookback_hours=lookback_hours,
                )
                combined.diagnostics.append(diagnostics)
                combined.candidates.extend(candidates)

                if not candidates:
                    break
                if diagnostics["pagination_stale_page"]:
                    stale_pages += 1
                else:
                    stale_pages = 0
                if stale_page_stop_count and stale_pages >= stale_page_stop_count:
                    break

        return finish(combined)

    if collector_name in SUPPORTED_LISTING_COLLECTORS:
        combined = CollectionResult()
        config = source.get("collector_config", {})
        if not isinstance(config, dict):
            config = {}
        raw_section_map = config.get("section_node_theme_map") or {}
        if not isinstance(raw_section_map, dict):
            raw_section_map = {}
        section_node_theme_map = {
            str(nodeid): str(theme)
            for nodeid, theme in raw_section_map.items()
            if str(nodeid).strip() and str(theme).strip()
        }
        for entry in entries:
            url = _entry_url(entry)
            fetch_result = fetcher.fetch_text(url)
            combined.raw_sources.append(
                _raw_source_record(
                    source,
                    url=url,
                    collector=collector_name,
                    result=fetch_result,
                    fetched_at=discovered_at,
                    entry=entry,
                )
            )
            if not fetch_result.ok:
                combined.errors.append(_fetch_error_record(source_id, url, fetch_result))
                continue
            listing_result = ListingCollector(
                source_id=source_id,
                query=query,
                default_tags=_entry_tags(default_tags, entry),
                section_node_theme_map=section_node_theme_map,
                article_url_patterns=_string_list(config.get("article_url_patterns")),
            ).collect_with_diagnostics(
                fetch_result.text,
                base_url=url,
                discovered_at=discovered_at,
            )
            candidates = _apply_entry_metadata(
                listing_result.candidates,
                entry=entry,
                default_tags=default_tags,
            )
            backfill_limit = _detail_time_backfill_limit(source)
            backfill_needed = sum(1 for candidate in candidates if _needs_time_backfill(candidate))
            if backfill_limit > 0 and backfill_needed:
                _emit_progress(
                    progress_callback,
                    {
                        "event": "detail_time_backfill_start",
                        "source_id": source_id,
                        "source_name": source.get("name") or source_id,
                        "entry_url": url,
                        "needed": backfill_needed,
                        "limit": min(backfill_limit, backfill_needed),
                    },
                )
                backfill_started_at = perf_counter()
            else:
                backfill_started_at = perf_counter()
            backfilled, detail_raw, detail_errors = _backfill_listing_candidate_times(
                source,
                candidates=candidates,
                fetcher=fetcher,
                fetched_at=discovered_at,
                limit=backfill_limit,
            )
            if backfill_limit > 0 and backfill_needed:
                _emit_progress(
                    progress_callback,
                    {
                        "event": "detail_time_backfill_done",
                        "source_id": source_id,
                        "source_name": source.get("name") or source_id,
                        "entry_url": url,
                        "attempted": len(detail_raw),
                        "backfilled": backfilled,
                        "error_count": len(detail_errors),
                        "elapsed_seconds": _elapsed_seconds(backfill_started_at),
                    },
                )
            diagnostics = dict(listing_result.diagnostics)
            diagnostics["status_code"] = fetch_result.status_code
            diagnostics["content_type"] = fetch_result.content_type
            diagnostics["detail_time_backfill_count"] = backfilled
            combined.diagnostics.append(diagnostics)
            combined.raw_sources.extend(detail_raw)
            combined.errors.extend(detail_errors)
            combined.candidates.extend(candidates)
        return finish(combined)

    return finish(
        CollectionResult(
            errors=[
                {
                    "source_id": source_id,
                    "collector": collector_name,
                    "error": "unsupported_collector",
                }
            ]
        )
    )


def collect_from_sources(
    sources: list[dict[str, Any]],
    *,
    fetcher: HttpFetcher,
    discovered_at: datetime,
    query: str,
    lookback_hours: int | None = None,
    progress_callback: ProgressCallback | None = None,
) -> CollectionResult:
    combined = CollectionResult()
    contract_errors_map = validate_sources_contracts(sources)
    if contract_errors_map:
        for source_id, errors in contract_errors_map.items():
            combined.diagnostics.append(
                {
                    "source_id": source_id,
                    "contract_valid": False,
                    "contract_errors": errors,
                }
            )
    for source in live_collectible_sources(sources):
        result = collect_from_source(
            source,
            fetcher=fetcher,
            discovered_at=discovered_at,
            query=query,
            lookback_hours=lookback_hours,
            progress_callback=progress_callback,
        )
        combined.candidates.extend(result.candidates)
        combined.raw_sources.extend(result.raw_sources)
        combined.errors.extend(result.errors)
        combined.diagnostics.extend(result.diagnostics)
    return combined


def live_collectible_sources(
    sources: list[dict[str, Any]],
    *,
    validate_contracts: bool = False,
) -> list[dict[str, Any]]:
    """Return the subset of sources that are supported for live collection.

    When *validate_contracts* is True, sources whose parser contract fails
    validation are excluded and their validation errors are logged to
    ``diagnostics`` on the returned item (keyed as ``_contract_errors``).
    """
    filtered: list[dict[str, Any]] = []
    for source in sources:
        collector = str(source.get("collector", "")).strip()
        if collector not in SUPPORTED_LIVE_COLLECTORS:
            continue
        if validate_contracts:
            source_id = str(source.get("id", "")).strip()
            try:
                contract = parser_contract_from_source_config(source)
            except Exception as exc:
                source["_contract_errors"] = [f"contract_factory_error: {exc}"]
                filtered.append(source)
                continue
            errors = validate_parser_contract(source_id, contract)
            if errors:
                source["_contract_errors"] = list(errors)
            else:
                source["_contract"] = contract
            filtered.append(source)
        else:
            filtered.append(source)
    return filtered


def validate_source_contract(source: dict[str, Any]) -> tuple[SiteParserContract | None, list[str]]:
    """Build and validate a parser contract for one source config entry.

    Returns ``(contract, errors)``.  *contract* is None when the factory
    itself raises; *errors* is the result of
    :func:`validate_parser_contract`.
    """
    source_id = str(source.get("id", "")).strip()
    contract: SiteParserContract | None = None
    try:
        contract = parser_contract_from_source_config(source)
    except Exception as exc:
        return None, [f"contract_factory_error: {exc}"]

    errors = validate_parser_contract(source_id, contract)
    return contract, errors


def validate_sources_contracts(
    sources: list[dict[str, Any]],
) -> dict[str, list[str]]:
    """Validate contracts for every source.  Returns ``{source_id: errors}``.

    Sources with no errors are omitted from the result.  Sources whose
    contract factory raises have an error entry starting with
    ``contract_factory_error:``.
    """
    result: dict[str, list[str]] = {}
    for source in sources:
        source_id = str(source.get("id", "")).strip()
        _contract, errors = validate_source_contract(source)
        if errors:
            result[source_id] = errors
    return result
