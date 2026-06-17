"""Static web page collector skeleton for HTML already fetched elsewhere."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any

from ..schemas import SourceDocument


class _MetadataHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title_parts: list[str] = []
        self.body_parts: list[str] = []
        self.meta: dict[str, str] = {}
        self.in_title = False
        self.capture_body = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = {key.lower(): value or "" for key, value in attrs}
        if tag.lower() == "title":
            self.in_title = True
        if tag.lower() in {"article", "main", "p"}:
            self.capture_body = True
        if tag.lower() == "meta":
            key = attrs_map.get("property") or attrs_map.get("name")
            content = attrs_map.get("content", "")
            if key and content:
                self.meta[key.lower()] = content.strip()

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self.in_title = False
        if tag.lower() in {"article", "main", "p"}:
            self.capture_body = False

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if not text:
            return
        if self.in_title:
            self.title_parts.append(text)
        if self.capture_body:
            self.body_parts.append(text)


def _parse_iso_datetime(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _dump_document(document: SourceDocument) -> dict[str, Any]:
    data = document.model_dump()
    for key in ("published_at", "fetched_at"):
        value = data.get(key)
        if isinstance(value, datetime):
            data[key] = value.isoformat()
    return data


@dataclass(frozen=True)
class WebPageCollector:
    source_id: str

    def parse_html(
        self,
        *,
        url: str,
        html: str,
        fetched_at: datetime,
    ) -> dict[str, Any]:
        parser = _MetadataHtmlParser()
        parser.feed(html)

        title = (
            parser.meta.get("og:title")
            or " ".join(parser.title_parts).strip()
            or url
        )
        published_at = _parse_iso_datetime(
            parser.meta.get("article:published_time")
            or parser.meta.get("date")
            or parser.meta.get("pubdate")
        )
        image_urls = [
            value
            for key, value in parser.meta.items()
            if key in {"og:image", "twitter:image"} and value
        ]
        description = parser.meta.get("description", "")
        content = " ".join(parser.body_parts).strip() or description

        document = SourceDocument(
            candidate_url=url,
            title=title,
            source_id=self.source_id,
            content=content,
            published_at=published_at,
            fetched_at=fetched_at,
            image_urls=image_urls,
            metadata={"description": description},
        )
        return _dump_document(document)
