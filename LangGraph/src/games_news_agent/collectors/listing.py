"""Generic listing-page collector for media index pages."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from html import unescape
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin

from ..schemas import SearchCandidate


CHINA_TZ = timezone(timedelta(hours=8))


class _ListingHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.items: list[dict[str, Any]] = []
        self._section_nodeid_stack: list[str] = []
        self._li_depth = 0
        self._current_item: dict[str, Any] | None = None
        self._current_link: dict[str, Any] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = {key.lower(): value or "" for key, value in attrs}
        tag_name = tag.lower()

        if tag_name == "ul":
            self._section_nodeid_stack.append(attrs_map.get("data-nodeid", "").strip())

        if tag_name == "li":
            if self._li_depth == 0:
                self._current_item = {
                    "links": [],
                    "text_parts": [],
                    "section_nodeid": self._current_section_nodeid(),
                }
            self._li_depth += 1

        if tag_name == "a" and self._current_item is not None:
            href = attrs_map.get("href", "").strip()
            if href:
                self._current_link = {
                    "href": href,
                    "title": attrs_map.get("title", "").strip(),
                    "text_parts": [],
                }
                self._current_item["links"].append(self._current_link)

    def handle_endtag(self, tag: str) -> None:
        tag_name = tag.lower()
        if tag_name == "a":
            self._current_link = None
        if tag_name == "li" and self._li_depth:
            self._li_depth -= 1
            if self._li_depth == 0 and self._current_item is not None:
                self.items.append(self._current_item)
                self._current_item = None
                self._current_link = None
        if tag_name == "ul" and self._section_nodeid_stack:
            self._section_nodeid_stack.pop()

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if not text or self._current_item is None:
            return
        self._current_item["text_parts"].append(text)
        if self._current_link is not None:
            self._current_link["text_parts"].append(text)

    def _current_section_nodeid(self) -> str:
        for nodeid in reversed(self._section_nodeid_stack):
            if nodeid:
                return nodeid
        return ""


class _ArticleLinkHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[dict[str, str]] = []
        self._link_stack: list[dict[str, Any]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_name = tag.lower()
        if tag_name == "img" and self._link_stack:
            attrs_map = {key.lower(): value or "" for key, value in attrs}
            alt = " ".join(attrs_map.get("alt", "").split()).strip()
            if alt:
                self._link_stack[-1]["text_parts"].append(alt)
            return

        if tag_name != "a":
            return
        attrs_map = {key.lower(): value or "" for key, value in attrs}
        href = attrs_map.get("href", "").strip()
        if not href:
            return
        self._link_stack.append(
            {
                "href": href,
                "title": attrs_map.get("title", "").strip(),
                "aria_label": attrs_map.get("aria-label", "").strip(),
                "text_parts": [],
            }
        )

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._link_stack:
            current_link = self._link_stack.pop()
            label = (
                current_link.get("title")
                or current_link.get("aria_label")
                or " ".join(current_link.get("text_parts", []))
            )
            self.links.append(
                {
                    "href": str(current_link.get("href") or ""),
                    "label": str(label).strip(),
                }
            )

    def handle_data(self, data: str) -> None:
        if not self._link_stack:
            return
        text = " ".join(data.split())
        if text:
            self._link_stack[-1]["text_parts"].append(text)


def _relative_delta(value: int, unit: str) -> timedelta:
    normalized = unit.lower().strip()
    if normalized in {"m", "min", "mins", "minute", "minutes"}:
        return timedelta(minutes=value)
    if normalized in {"h", "hr", "hrs", "hour", "hours"}:
        return timedelta(hours=value)
    if normalized in {"d", "day", "days"}:
        return timedelta(days=value)
    return timedelta(weeks=value)


def _parse_relative_datetime(raw_text: str, *, discovered_at: datetime) -> datetime | None:
    if discovered_at.tzinfo is None:
        discovered_at = discovered_at.replace(tzinfo=timezone.utc)
    else:
        discovered_at = discovered_at.astimezone(timezone.utc)

    match = re.match(r"\s*(\d{1,3})\s*(m|h|d|w)\b", raw_text, flags=re.IGNORECASE)
    if not match:
        match = re.search(
            r"\b(\d{1,3})\s*(m|h|d|w|mins?|minutes?|hrs?|hours?|days?|weeks?)\s*ago\b",
            raw_text,
            flags=re.IGNORECASE,
        )
    if not match:
        return None
    value = int(match.group(1))
    unit = match.group(2).lower()
    return discovered_at - _relative_delta(value, unit)


def _clean_article_link_title(raw_text: str) -> str:
    title = " ".join(raw_text.split()).strip()
    if not title:
        return ""
    had_relative_prefix = re.match(r"\d{1,3}\s*(?:m|h|d|w)\b", title, flags=re.IGNORECASE) is not None
    title = re.sub(r"^\d{1,3}\s*(?:m|h|d|w)\b\s*", "", title, flags=re.IGNORECASE).strip()
    if had_relative_prefix:
        title = re.sub(r"\s+\d{1,5}$", "", title).strip()
    return title


def _is_weak_listing_title(title: str) -> bool:
    compact = re.sub(r"\s+", "", str(title or ""))
    if not compact:
        return True
    if len(compact) < 8:
        return True
    return bool(re.fullmatch(r"[A-Za-z0-9]+", compact) and len(compact) < 12)


def _best_listing_title(attribute_title: str, link_text: str) -> tuple[str, bool]:
    title = " ".join(str(attribute_title or "").split()).strip()
    visible = " ".join(str(link_text or "").split()).strip()
    if not title:
        return visible, False
    if (
        visible
        and _is_weak_listing_title(title)
        and len(visible) >= len(title) + 4
        and visible.lower().startswith(title.lower())
    ):
        return visible, True
    return title, False


def _parse_listing_datetime(raw_text: str, *, discovered_at: datetime) -> datetime | None:
    if discovered_at.tzinfo is None:
        discovered_at = discovered_at.replace(tzinfo=timezone.utc)
    local_now = discovered_at.astimezone(CHINA_TZ)

    relative = _parse_relative_datetime(raw_text, discovered_at=discovered_at)
    if relative is not None:
        return relative

    absolute_match = re.search(
        r"(20\d{2})[-/年.](\d{1,2})[-/月.](\d{1,2})\s*(?:日)?\s+(\d{1,2}):(\d{2})",
        raw_text,
    )
    if absolute_match:
        year, month, day, hour, minute = [int(part) for part in absolute_match.groups()]
        return datetime(year, month, day, hour, minute, tzinfo=CHINA_TZ)

    month_day_match = re.search(r"(?<!\d)(\d{1,2})[-/](\d{1,2})\s+(\d{1,2}):(\d{2})", raw_text)
    if month_day_match:
        month, day, hour, minute = [int(part) for part in month_day_match.groups()]
        return datetime(local_now.year, month, day, hour, minute, tzinfo=CHINA_TZ)

    today_match = re.search(r"(今天|今日)\s*(\d{1,2}):(\d{2})", raw_text)
    if today_match:
        _, hour, minute = today_match.groups()
        return datetime(
            local_now.year,
            local_now.month,
            local_now.day,
            int(hour),
            int(minute),
            tzinfo=CHINA_TZ,
        )

    yesterday_match = re.search(r"昨天\s*(\d{1,2}):(\d{2})", raw_text)
    if yesterday_match:
        hour, minute = yesterday_match.groups()
        day = local_now - timedelta(days=1)
        return datetime(day.year, day.month, day.day, int(hour), int(minute), tzinfo=CHINA_TZ)

    return None


def _html_fragment_text(fragment: str) -> str:
    fragment = re.sub(r"<script\b[^>]*>.*?</script>", " ", fragment, flags=re.IGNORECASE | re.DOTALL)
    fragment = re.sub(r"<style\b[^>]*>.*?</style>", " ", fragment, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", fragment)
    return " ".join(unescape(text).split())


def _parse_nearby_article_link_datetime(
    html: str,
    href: str,
    *,
    discovered_at: datetime,
    window_chars: int = 1200,
) -> datetime | None:
    raw_href = str(href or "").strip()
    if not raw_href:
        return None
    index = html.find(raw_href)
    if index < 0:
        return None

    after = html[index : min(len(html), index + len(raw_href) + window_chars)]
    after_time = _parse_listing_datetime(_html_fragment_text(after), discovered_at=discovered_at)
    if after_time is not None:
        return after_time

    before = html[max(0, index - window_chars) : index]
    return _parse_listing_datetime(_html_fragment_text(before), discovered_at=discovered_at)


def _dump_candidate(candidate: SearchCandidate) -> dict[str, Any]:
    data = candidate.model_dump()
    for key in ("discovered_at", "published_at", "observed_at"):
        value = data.get(key)
        if isinstance(value, datetime):
            data[key] = value.isoformat()
    return data


@dataclass(frozen=True)
class ListingCollection:
    candidates: list[dict[str, Any]]
    diagnostics: dict[str, Any]


@dataclass(frozen=True)
class ListingCollector:
    source_id: str
    query: str = ""
    default_tags: list[str] = field(default_factory=list)
    section_node_theme_map: dict[str, str] = field(default_factory=dict)
    article_url_patterns: list[str] = field(default_factory=lambda: [r"/articles/"])

    def collect_from_html(
        self,
        html: str,
        *,
        base_url: str,
        discovered_at: datetime,
    ) -> list[dict[str, Any]]:
        return self.collect_with_diagnostics(
            html,
            base_url=base_url,
            discovered_at=discovered_at,
        ).candidates

    def collect_with_diagnostics(
        self,
        html: str,
        *,
        base_url: str,
        discovered_at: datetime,
    ) -> ListingCollection:
        parser = _ListingHtmlParser()
        parser.feed(html)

        candidates: list[dict[str, Any]] = []
        seen_urls: set[str] = set()
        link_count = 0
        duplicate_url_count = 0
        for item in parser.items:
            item_text = " ".join(item.get("text_parts", []))
            published_at = _parse_listing_datetime(item_text, discovered_at=discovered_at)
            section_nodeid = str(item.get("section_nodeid") or "").strip()
            section_theme = self.section_node_theme_map.get(section_nodeid, "")
            for link in item.get("links", []):
                link_count += 1
                link_text = " ".join(link.get("text_parts", [])).strip()
                title, title_repaired = _best_listing_title(str(link.get("title") or ""), link_text)
                url = urljoin(base_url, str(link.get("href", "")))
                if url in seen_urls:
                    duplicate_url_count += 1
                    continue
                if not title or not url:
                    continue
                seen_urls.add(url)
                candidate = SearchCandidate(
                    title=title,
                    url=url,
                    source_id=self.source_id,
                    snippet=item_text,
                    query=self.query,
                    discovered_at=discovered_at,
                    published_at=published_at,
                    observed_at=published_at,
                    tags=list(self.default_tags),
                )
                dumped = _dump_candidate(candidate)
                if section_nodeid:
                    dumped["source_section_nodeid"] = section_nodeid
                if section_theme:
                    dumped["source_section_theme"] = section_theme
                    dumped["theme_section"] = section_theme
                if title_repaired:
                    dumped["title_repair_source"] = "link_text"
                candidates.append(dumped)

        article_link_count = 0
        article_link_candidate_count = 0
        article_link_context_time_count = 0
        if not candidates:
            (
                article_link_count,
                article_link_candidate_count,
                article_link_context_time_count,
            ) = self._collect_article_link_candidates(
                html,
                base_url=base_url,
                discovered_at=discovered_at,
                candidates=candidates,
                seen_urls=seen_urls,
            )

        missing_time_count = sum(
            1
            for candidate in candidates
            if not candidate.get("published_at") and not candidate.get("observed_at")
        )
        diagnostics = {
            "source_id": self.source_id,
            "entry_url": base_url,
            "collector": "media_listing",
            "raw_html_bytes": len(html.encode("utf-8")),
            "link_count": link_count,
            "candidate_count": len(candidates),
            "missing_time_count": missing_time_count,
            "duplicate_url_count": duplicate_url_count,
            "title_repair_count": sum(1 for candidate in candidates if candidate.get("title_repair_source")),
            "detail_time_backfill_count": 0,
            "parse_warning_count": 0 if parser.items or candidates else 1,
            "section_node_counts": self._section_node_counts(candidates),
            "article_link_count": article_link_count,
            "article_link_candidate_count": article_link_candidate_count,
            "article_link_context_time_count": article_link_context_time_count,
            "listing_strategy": "article_link_fallback" if article_link_candidate_count else "li_listing",
        }
        return ListingCollection(candidates=candidates, diagnostics=diagnostics)

    def _collect_article_link_candidates(
        self,
        html: str,
        *,
        base_url: str,
        discovered_at: datetime,
        candidates: list[dict[str, Any]],
        seen_urls: set[str],
    ) -> tuple[int, int, int]:
        parser = _ArticleLinkHtmlParser()
        parser.feed(html)
        link_count = 0
        candidate_count = 0
        context_time_count = 0
        for link in parser.links:
            label = str(link.get("label") or "").strip()
            href = str(link.get("href") or "").strip()
            url = urljoin(base_url, href)
            if not label or not url:
                continue
            if not self._article_url_allowed(url):
                continue
            link_count += 1
            if url in seen_urls:
                continue
            title = _clean_article_link_title(label)
            if not title:
                continue
            seen_urls.add(url)
            published_at = _parse_listing_datetime(label, discovered_at=discovered_at)
            listing_time_source = "link_label" if published_at is not None else ""
            if published_at is None:
                published_at = _parse_nearby_article_link_datetime(
                    html,
                    href,
                    discovered_at=discovered_at,
                )
                if published_at is not None:
                    listing_time_source = "nearby_article_context"
                    context_time_count += 1
            candidate = SearchCandidate(
                title=title,
                url=url,
                source_id=self.source_id,
                snippet=label,
                query=self.query,
                discovered_at=discovered_at,
                published_at=published_at,
                observed_at=published_at,
                tags=list(self.default_tags),
            )
            dumped = _dump_candidate(candidate)
            dumped["listing_strategy"] = "article_link_fallback"
            if listing_time_source:
                dumped["listing_time_source"] = listing_time_source
            candidates.append(dumped)
            candidate_count += 1
        return link_count, candidate_count, context_time_count

    def _article_url_allowed(self, url: str) -> bool:
        if not self.article_url_patterns:
            return "/articles/" in url
        for pattern in self.article_url_patterns:
            try:
                if re.search(pattern, url, flags=re.IGNORECASE):
                    return True
            except re.error:
                if pattern.lower() in url.lower():
                    return True
        return False

    def _section_node_counts(self, candidates: list[dict[str, Any]]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for candidate in candidates:
            nodeid = str(candidate.get("source_section_nodeid") or "").strip()
            if not nodeid:
                continue
            counts[nodeid] = counts.get(nodeid, 0) + 1
        return counts
