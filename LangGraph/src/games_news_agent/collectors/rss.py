"""RSS collector skeleton.

This parser intentionally works on provided XML text first. Live HTTP fetching
can be added later without changing the normalized SearchCandidate output.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from xml.etree import ElementTree

from ..schemas import SearchCandidate


def _node_text(parent: ElementTree.Element, name: str) -> str:
    node = parent.find(name)
    if node is None or node.text is None:
        return ""
    return node.text.strip()


def _parse_rss_datetime(raw: str) -> datetime | None:
    if not raw:
        return None
    try:
        parsed = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _dump_candidate(candidate: SearchCandidate) -> dict[str, Any]:
    data = candidate.model_dump()
    for key in ("discovered_at", "published_at", "observed_at"):
        value = data.get(key)
        if isinstance(value, datetime):
            data[key] = value.isoformat()
    return data


@dataclass(frozen=True)
class RssCollector:
    source_id: str
    query: str = ""
    default_tags: list[str] = field(default_factory=list)

    def collect_from_text(
        self,
        xml_text: str,
        *,
        discovered_at: datetime,
    ) -> list[dict[str, Any]]:
        root = ElementTree.fromstring(xml_text)
        items = root.findall(".//item")
        candidates: list[dict[str, Any]] = []

        for item in items:
            title = _node_text(item, "title")
            link = _node_text(item, "link")
            if not title or not link:
                continue

            published_at = _parse_rss_datetime(
                _node_text(item, "pubDate") or _node_text(item, "published")
            )
            tags = list(self.default_tags)
            for category in item.findall("category"):
                if category.text and category.text.strip():
                    tags.append(category.text.strip())

            candidate = SearchCandidate(
                title=title,
                url=link,
                source_id=self.source_id,
                snippet=_node_text(item, "description"),
                query=self.query,
                discovered_at=discovered_at,
                published_at=published_at,
                observed_at=published_at,
                tags=tags,
            )
            candidates.append(_dump_candidate(candidate))

        return candidates
