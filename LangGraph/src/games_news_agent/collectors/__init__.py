"""Collector interfaces and skeleton implementations."""

from .rss import RssCollector
from .web import WebPageCollector

__all__ = ["RssCollector", "WebPageCollector"]
