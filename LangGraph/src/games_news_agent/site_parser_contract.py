"""Site parser contract: formalise parsing expectations per source.

Every live source declares a parser contract so downstream tooling can
verify configuration, surface mismatches, and auto-tune collector settings.

A contract is a TypedDict-shaped dataclass that describes:

* which entry points the collector must hit (URL, HTTP method, priority)
* how pagination works (style, param name, max pages)
* where the source timestamps live and how to fall back
* what stop conditions cause the collector to stop paginating
* what failure types the collector should anticipate

Contracts are validated before a source runs. The module also includes a
factory that generates a sensible default contract from a sources.yaml
config entry so existing sources work without manual contract authoring.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

COLLECTOR_PAGINATION_STYLES = frozenset({
    "none",            # no pagination (single-page fetch)
    "rss",             # feed content arrives in one response
    "incremental",     # Load More links, next_url_patterns
    "paged",           # page=N query param
    "jsonp_paged",     # JSONP endpoint with page in payload
    "cursor",          # opaque cursor-based pagination
    "scroll",          # infinite scroll via API
})
"""Recognised pagination styles."""

COLLECTOR_ENTRY_METHODS = frozenset({"GET", "POST", "JSONP_POST"})
"""HTTP methods accepted in entry-point records."""

CONDITION_NAMES = frozenset({
    "max_pages_reached",
    "no_next_page",
    "no_new_candidates",
    "stale_page_limit",
    "next_page_already_seen",
    "empty_response_body",
    "total_pages_exceeded",
    "lookback_exceeded",
    "error_threshold",
})
"""Well-known stop-condition names.  New conditions must be added here to
pass validation."""


@dataclass(frozen=True)
class FailureTypeSpec:
    """Description of a failure the collector should anticipate."""

    error_type: str
    """Canonical error-type string, e.g. ``http_404``, ``url_error``."""

    retryable: bool
    """Whether the collector is allowed to retry this failure."""

    suggested_action: str
    """Human-readable suggestion, e.g. ``verify_feed_url``."""


@dataclass(frozen=True)
class EntryPointSpec:
    """A single URL the collector fetches, with method and priority."""

    url: str
    """Target URL (may include ``{page}`` or ``{node_id}`` placeholders)."""

    method: str = "GET"
    """HTTP method: ``GET``, ``POST``, or ``JSONP_POST``."""

    priority: int = 100
    """Relative priority within the source (higher = fetch first)."""


@dataclass(frozen=True)
class PaginationSpec:
    """How the collector walks multiple pages."""

    style: str = "none"
    """One of the :data:`COLLECTOR_PAGINATION_STYLES` values."""

    param_name: str = ""
    """Query / payload parameter name that carries the page cursor."""

    max_pages: int = 1
    """Hard upper bound on pages fetched per entry."""


@dataclass(frozen=True)
class TimestampSourceSpec:
    """Where a candidate's ``published_at`` timestamp can be found."""

    field: str = ""
    """The HTML / RSS / JSON field that carries the timestamp, e.g.
    ``pubDate``, ``meta[article:published_time]``, ``.time``."""

    format: str = ""
    """Expected datetime format hint, e.g. ``RFC_2822``, ``ISO_8601``,
    ``CN_DATETIME`` (``YYYY-MM-DD HH:MM`` in Asia/Shanghai)."""

    fallback_strategy: str = ""
    """Strategy when the primary field is missing, e.g.
    ``detail_page_backfill``, ``relative_time_infer``,
    ``observed_at_only``, ``none``."""


@dataclass(frozen=True)
class StopConditionSpec:
    """A threshold that causes the collector to stop pagination."""

    condition: str
    """One of the :data:`CONDITION_NAMES` values."""

    threshold: int = 1
    """How many consecutive pages / occurrences trigger the stop.

    For absolute limits like ``max_pages_reached`` this is the cap
    itself.  For incremental signals like ``stale_page_limit`` it is the
    number of consecutive stale pages."""


@dataclass(frozen=True)
class SiteParserContract:
    """Full contract describing how a collector should parse a site.

    .. code-block:: python

        contract = SiteParserContract(
            source_id="ign",
            entry_points=[
                EntryPointSpec(
                    url="https://www.ign.com/news/playstation",
                    method="GET",
                    priority=90,
                ),
            ],
            pagination=PaginationSpec(
                style="incremental",
                param_name="endIndex",
                max_pages=5,
            ),
            timestamp_source=TimestampSourceSpec(
                field="meta[article:published_time]",
                format="ISO_8601",
                fallback_strategy="detail_page_backfill",
            ),
            stop_conditions=[
                StopConditionSpec(condition="max_pages_reached", threshold=5),
                StopConditionSpec(condition="stale_page_limit", threshold=1),
                StopConditionSpec(condition="no_new_candidates", threshold=1),
            ],
            failure_types=[
                FailureTypeSpec(
                    error_type="http_404",
                    retryable=False,
                    suggested_action="verify_page_url",
                ),
            ],
        )
    """

    source_id: str
    """Matches the ``id`` field in sources.yaml."""

    entry_points: list[EntryPointSpec] = field(default_factory=list)
    """At least one entry-point URL must be present."""

    pagination: PaginationSpec = field(default_factory=PaginationSpec)
    """Defaults to ``style=none, max_pages=1``."""

    timestamp_source: TimestampSourceSpec = field(default_factory=TimestampSourceSpec)
    """Defaults to empty fields (no timestamp extraction)."""

    stop_conditions: list[StopConditionSpec] = field(default_factory=list)
    """Ordered list.  The first condition whose threshold is met stops
    pagination."""

    failure_types: list[FailureTypeSpec] = field(default_factory=list)
    """Anticipated failure types.  Used by diagnostics to surface
    actionable errors."""


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_parser_contract(
    source_id: str,
    contract: SiteParserContract,
) -> list[str]:
    """Return a list of human-readable validation errors (empty = valid).

    Checks that:

    * ``source_id`` matches the contract id
    * there is at least one entry point
    * every entry point has a non-empty URL and recognised method
    * pagination style is recognised
    * every stop-condition name is recognised
    * every failure-type has a non-empty ``error_type``
    """
    errors: list[str] = []

    # --- identity ---
    if contract.source_id != source_id:
        errors.append(
            f"source_id mismatch: expected '{source_id}', "
            f"got '{contract.source_id}'"
        )

    # --- entry points ---
    if not contract.entry_points:
        errors.append("entry_points must contain at least one entry")
    for idx, ep in enumerate(contract.entry_points):
        prefix = f"entry_points[{idx}]"
        if not ep.url.strip():
            errors.append(f"{prefix}.url must be non-empty")
        if ep.method.upper() not in COLLECTOR_ENTRY_METHODS:
            errors.append(
                f"{prefix}.method '{ep.method}' is not recognised; "
                f"use one of {sorted(COLLECTOR_ENTRY_METHODS)}"
            )

    # --- pagination ---
    if contract.pagination.style not in COLLECTOR_PAGINATION_STYLES:
        errors.append(
            f"pagination.style '{contract.pagination.style}' is not "
            f"recognised; use one of {sorted(COLLECTOR_PAGINATION_STYLES)}"
        )
    if contract.pagination.max_pages < 1:
        errors.append(
            f"pagination.max_pages must be >= 1, got "
            f"{contract.pagination.max_pages}"
        )

    # --- stop conditions ---
    for idx, sc in enumerate(contract.stop_conditions):
        prefix = f"stop_conditions[{idx}]"
        if sc.condition not in CONDITION_NAMES:
            errors.append(
                f"{prefix}.condition '{sc.condition}' is not recognised; "
                f"use one of {sorted(CONDITION_NAMES)}"
            )

    # --- failure types ---
    for idx, ft in enumerate(contract.failure_types):
        prefix = f"failure_types[{idx}]"
        if not ft.error_type.strip():
            errors.append(f"{prefix}.error_type must be non-empty")

    return errors


# ---------------------------------------------------------------------------
# Auto-generation from sources.yaml
# ---------------------------------------------------------------------------

def parser_contract_from_source_config(
    source_config: dict[str, Any],
) -> SiteParserContract:
    """Build a default :class:`SiteParserContract` from a sources.yaml entry.

    The factory inspects ``collector``, ``collector_config``, feed/page URL
    fields and produces a best-effort contract.  Users may override the
    result before registration.

    Mapping logic:

    * **entry_points**: built from ``feed_url`` / ``feed_urls`` /
      ``feed_entries`` (RSS collectors) or ``page_url`` / ``page_urls`` /
      ``page_entries`` / ``pagination_entries`` (listing / JSONP
      collectors).
    * **pagination**: derived from ``collector_config.max_pages_per_entry``,
      ``pagination_param``, and collector type.
    * **timestamp_source**: guessed from collector type (RSS →
      ``pubDate`` / RFC_2822; listing → ``.time`` / CN_DATETIME with
      detail-page backfill when ``detail_time_backfill_limit`` is set).
    * **stop_conditions**: populated from ``max_pages_per_entry`` and
      ``stale_page_stop_count``.
    * **failure_types**: a standard set based on fetch-layer error types.
    """
    collector = str(source_config.get("collector", "")).strip()
    collector_config = source_config.get("collector_config", {})
    if not isinstance(collector_config, dict):
        collector_config = {}
    source_id = str(source_config.get("id", "")).strip()
    priority = _int_from_config(source_config, "priority", 100)

    # ---- entry points ----
    entry_points = _build_entry_points(source_config, collector, priority)

    # ---- pagination ----
    pagination = _build_pagination_spec(collector, collector_config)

    # ---- timestamp source ----
    timestamp_source = _build_timestamp_spec(collector, collector_config)

    # ---- stop conditions ----
    stop_conditions = _build_stop_conditions(collector, collector_config)

    # ---- failure types ----
    failure_types = _build_failure_types(collector)

    return SiteParserContract(
        source_id=source_id,
        entry_points=entry_points,
        pagination=pagination,
        timestamp_source=timestamp_source,
        stop_conditions=stop_conditions,
        failure_types=failure_types,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_RSS_COLLECTORS = frozenset({"rss", "media_rss"})
_LISTING_COLLECTORS = frozenset({"listing_page", "media_listing", "web_listing"})
_INCREMENTAL_COLLECTORS = frozenset({
    "incremental_listing",
    "media_incremental_listing",
})
_JSONP_PAGED_COLLECTORS = frozenset({
    "jsonp_paged_listing",
    "media_jsonp_paged_listing",
})
_ALL_LISTING_COLLECTORS = (
    _LISTING_COLLECTORS | _INCREMENTAL_COLLECTORS | _JSONP_PAGED_COLLECTORS
)

_STANDARD_FAILURE_TYPES: list[FailureTypeSpec] = [
    FailureTypeSpec(
        error_type="http_404",
        retryable=False,
        suggested_action="verify_feed_url or page_url",
    ),
    FailureTypeSpec(
        error_type="http_500",
        retryable=True,
        suggested_action="retry with backoff; alert if persistent",
    ),
    FailureTypeSpec(
        error_type="http_429",
        retryable=True,
        suggested_action="respect Retry-After header; reduce frequency",
    ),
    FailureTypeSpec(
        error_type="url_error",
        retryable=True,
        suggested_action="check network connectivity and DNS",
    ),
    FailureTypeSpec(
        error_type="os_error",
        retryable=True,
        suggested_action="check socket / proxy configuration",
    ),
    FailureTypeSpec(
        error_type="parse_error",
        retryable=False,
        suggested_action="review parser for site markup changes",
    ),
    FailureTypeSpec(
        error_type="fetch_attempts_exhausted",
        retryable=True,
        suggested_action="increase max_attempts or investigate upstream issues",
    ),
    FailureTypeSpec(
        error_type="encoding_error",
        retryable=False,
        suggested_action="check charset fallback chain (utf-8, gb18030)",
    ),
]


def _int_from_config(config: dict[str, Any], key: str, default: int) -> int:
    value = config.get(key, default)
    if isinstance(value, int):
        return max(value, 0)
    try:
        return max(int(str(value)), 0)
    except (TypeError, ValueError):
        return max(default, 0)


def _url_from_entry(entry: object) -> str:
    if isinstance(entry, dict):
        return str(entry.get("url") or entry.get("href") or "").strip()
    return str(entry).strip()


def _build_entry_points(
    source_config: dict[str, Any],
    collector: str,
    default_priority: int,
) -> list[EntryPointSpec]:
    entries: list[EntryPointSpec] = []

    if collector in _RSS_COLLECTORS:
        # feed_entries > feed_urls > feed_url
        feed_entries = source_config.get("feed_entries")
        if isinstance(feed_entries, list):
            for entry in feed_entries:
                url = _url_from_entry(entry)
                if url:
                    entries.append(EntryPointSpec(url=url, method="GET", priority=default_priority))
        else:
            feed_urls = source_config.get("feed_urls")
            if isinstance(feed_urls, list):
                for url in feed_urls:
                    url_str = str(url).strip()
                    if url_str:
                        entries.append(EntryPointSpec(url=url_str, method="GET", priority=default_priority))
            else:
                feed_url = str(source_config.get("feed_url", "")).strip()
                if feed_url:
                    entries.append(EntryPointSpec(url=feed_url, method="GET", priority=default_priority))

    elif collector in _ALL_LISTING_COLLECTORS:
        if collector in _JSONP_PAGED_COLLECTORS:
            pagination_entries = source_config.get("collector_config", {}).get("pagination_entries")
            if isinstance(pagination_entries, list):
                base_url = str(
                    source_config.get("page_url")
                    or source_config.get("url")
                    or ""
                ).strip()
                for entry in pagination_entries:
                    if isinstance(entry, dict):
                        node_id = str(
                            entry.get("node_id") or entry.get("nodeId") or ""
                        ).strip()
                        if node_id:
                            entries.append(
                                EntryPointSpec(
                                    url=f"{base_url}?node_id={node_id}" if base_url else f"node_id={node_id}",
                                    method="JSONP_POST",
                                    priority=default_priority,
                                )
                            )
            if not entries:
                page_url = str(
                    source_config.get("page_url")
                    or source_config.get("url")
                    or ""
                ).strip()
                if page_url:
                    entries.append(EntryPointSpec(url=page_url, method="GET", priority=default_priority))
        else:
            # listing / incremental: page_entries > page_urls > page_url
            page_entries = source_config.get("page_entries")
            if isinstance(page_entries, list):
                for entry in page_entries:
                    url = _url_from_entry(entry)
                    if url:
                        entries.append(EntryPointSpec(url=url, method="GET", priority=default_priority))
            else:
                page_urls = source_config.get("page_urls")
                if isinstance(page_urls, list):
                    for url in page_urls:
                        url_str = str(url).strip()
                        if url_str:
                            entries.append(EntryPointSpec(url=url_str, method="GET", priority=default_priority))
                else:
                    page_url = str(
                        source_config.get("page_url")
                        or source_config.get("url")
                        or ""
                    ).strip()
                    if page_url:
                        entries.append(EntryPointSpec(url=page_url, method="GET", priority=default_priority))

    # Fallback: use url field
    if not entries:
        url = str(source_config.get("url", "")).strip()
        if url:
            entries.append(EntryPointSpec(url=url, method="GET", priority=default_priority))

    return entries


def _build_pagination_spec(
    collector: str,
    collector_config: dict[str, Any],
) -> PaginationSpec:
    max_pages = _int_from_config(collector_config, "max_pages_per_entry", 3)

    if collector in _RSS_COLLECTORS:
        return PaginationSpec(style="rss", param_name="", max_pages=1)
    if collector in _JSONP_PAGED_COLLECTORS:
        param_name = str(collector_config.get("pagination_param", "jsondata")).strip()
        return PaginationSpec(style="jsonp_paged", param_name=param_name, max_pages=max_pages)
    if collector in _INCREMENTAL_COLLECTORS:
        return PaginationSpec(style="incremental", param_name="endIndex", max_pages=max_pages)
    if collector in _LISTING_COLLECTORS:
        return PaginationSpec(style="none", param_name="", max_pages=1)

    # stub / unknown
    return PaginationSpec(style="none", param_name="", max_pages=1)


def _build_timestamp_spec(
    collector: str,
    collector_config: dict[str, Any],
) -> TimestampSourceSpec:
    detail_backfill = _int_from_config(collector_config, "detail_time_backfill_limit", 0)

    if collector in _RSS_COLLECTORS:
        return TimestampSourceSpec(
            field="pubDate",
            format="RFC_2822",
            fallback_strategy="observed_at_only",
        )
    if collector in _ALL_LISTING_COLLECTORS:
        fallback = "detail_page_backfill" if detail_backfill > 0 else "observed_at_only"
        return TimestampSourceSpec(
            field="meta[article:published_time], .time",
            format="ISO_8601",
            fallback_strategy=fallback,
        )
    return TimestampSourceSpec(
        field="",
        format="",
        fallback_strategy="observed_at_only",
    )


def _build_stop_conditions(
    collector: str,
    collector_config: dict[str, Any],
) -> list[StopConditionSpec]:
    conditions: list[StopConditionSpec] = []
    max_pages = _int_from_config(collector_config, "max_pages_per_entry", 3)
    stale_stop = _int_from_config(collector_config, "stale_page_stop_count", 1)

    if collector in _RSS_COLLECTORS or collector in _LISTING_COLLECTORS:
        return conditions  # single-page collectors: no stop conditions

    # Paginating collectors share these base conditions
    conditions.append(StopConditionSpec(condition="max_pages_reached", threshold=max_pages))
    conditions.append(StopConditionSpec(condition="no_new_candidates", threshold=1))
    if stale_stop > 0:
        conditions.append(StopConditionSpec(condition="stale_page_limit", threshold=stale_stop))

    if collector in _INCREMENTAL_COLLECTORS or collector in _JSONP_PAGED_COLLECTORS:
        conditions.append(StopConditionSpec(condition="no_next_page", threshold=1))
        conditions.append(StopConditionSpec(condition="next_page_already_seen", threshold=1))

    if collector in _JSONP_PAGED_COLLECTORS:
        conditions.append(StopConditionSpec(condition="empty_response_body", threshold=1))

    return conditions


def _build_failure_types(collector: str) -> list[FailureTypeSpec]:
    """Return the standard failure-type palette for a collector.

    Listing collectors add a ``parse_error`` entry to highlight that markup
    changes can silently break extraction.  Stub collectors get a minimal
    set because they do not fetch at all.
    """
    base = list(_STANDARD_FAILURE_TYPES)
    if collector in _LISTING_COLLECTORS or collector in _INCREMENTAL_COLLECTORS:
        # Ensure parse_error is present (already in _STANDARD_FAILURE_TYPES)
        pass
    if collector.endswith("_stub") or collector in (
        "browser_stub",
        "app_or_browser_stub",
    ):
        return [
            FailureTypeSpec(
                error_type="stub_collector",
                retryable=False,
                suggested_action="implement collector before running live",
            ),
        ]
    return base
