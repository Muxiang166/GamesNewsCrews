"""Shared state and data models for the games news pipeline."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional, TypedDict

from pydantic import BaseModel, Field, HttpUrl


class SourceKind(str, Enum):
    OFFICIAL = "official"
    MEDIA = "media"
    COMMUNITY = "community"
    SEARCH = "search"


class SourceConfig(BaseModel):
    id: str
    name: str
    kind: SourceKind
    url: HttpUrl
    region: str = "global"
    priority: int = Field(default=50, ge=0, le=100)
    collector: str
    tags: list[str] = Field(default_factory=list)


class SearchCandidate(BaseModel):
    title: str
    url: str
    source_id: str
    snippet: str = ""
    query: str = ""
    discovered_at: datetime
    published_at: Optional[datetime] = None
    observed_at: Optional[datetime] = None
    heat_signals: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    heat_score: float = Field(default=0.0, ge=0.0, le=100.0)
    heat_reasons: list[str] = Field(default_factory=list)


class SourceDocument(BaseModel):
    candidate_url: str
    title: str
    source_id: str
    content: str = ""
    author: Optional[str] = None
    published_at: Optional[datetime] = None
    fetched_at: datetime
    image_urls: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Asset(BaseModel):
    url: Optional[str] = None
    kind: Literal["article_image", "video_cover", "screenshot", "meme", "placeholder"]
    source_url: str
    status: Literal["available", "missing", "manual_fill_required"] = "available"
    note: str = ""


class Claim(BaseModel):
    text: str
    story_id: str
    source_urls: list[str] = Field(default_factory=list)
    check_status: Literal["unchecked", "verified", "likely", "rumor", "conflict", "reject"] = "unchecked"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class Story(BaseModel):
    id: str
    title: str
    summary: str = ""
    category: Literal["official", "hot_discussion", "player_meme", "controversy", "market"] = "official"
    source_urls: list[str] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    assets: list[Asset] = Field(default_factory=list)
    heat_score: float = Field(default=0.0, ge=0.0, le=100.0)
    credibility_score: float = Field(default=0.0, ge=0.0, le=100.0)
    status: Literal["draft", "ready", "needs_review", "rejected"] = "draft"


class PipelineState(TypedDict, total=False):
    topic: str
    dry_run: bool
    lookback_hours: int
    started_at: str
    output_dir: str
    sources: list[dict[str, Any]]
    candidates: list[dict[str, Any]]
    rejected_candidates: list[dict[str, Any]]
    documents: list[dict[str, Any]]
    assets: list[dict[str, Any]]
    stories: list[dict[str, Any]]
    briefing_path: str
    layout_manifest_path: str
    render_queue_path: str
    notes: list[str]
