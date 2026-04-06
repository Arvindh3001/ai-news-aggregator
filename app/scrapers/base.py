"""
Shared primitives for all scrapers:
- Pydantic transfer models (VideoItem, ArticleItem)
- fetch_feed(): fetch and parse an RSS/Atom URL into an ElementTree root
- parse_date(): normalize any date string to a UTC-aware datetime
- HEADERS: browser-like User-Agent used by all HTTP requests
"""
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional

import requests
from pydantic import BaseModel

# ------------------------------------------------------------------
# Transfer models
# ------------------------------------------------------------------


class VideoItem(BaseModel):
    """Represents a single YouTube video scraped from the RSS feed."""

    video_id: str
    title: str
    url: str
    published_at: datetime


class ArticleItem(BaseModel):
    """Represents a single blog article scraped from an RSS feed."""

    guid: str
    title: str
    url: str
    description: Optional[str] = None
    published_at: datetime


# ------------------------------------------------------------------
# HTTP helpers
# ------------------------------------------------------------------

HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}


def fetch_feed(url: str, timeout: int = 15) -> ET.Element:
    """
    Fetch an RSS/Atom feed URL and return the parsed XML root element.
    Raises requests.HTTPError on non-2xx status.
    """
    resp = requests.get(url, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    return ET.fromstring(resp.content)


# ------------------------------------------------------------------
# Date normalization
# ------------------------------------------------------------------


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_date(raw: str) -> datetime:
    """
    Parse a date string to a timezone-aware UTC datetime.
    Handles both RFC 2822 (RSS 2.0) and ISO 8601 (Atom) formats.
    Falls back to now(UTC) if both parsers fail.
    """
    raw = raw.strip()

    # RFC 2822 — e.g. "Mon, 06 Apr 2026 10:00:00 +0000"
    try:
        return _to_utc(parsedate_to_datetime(raw))
    except Exception:
        pass

    # ISO 8601 — e.g. "2026-04-06T10:00:00+00:00"
    try:
        return _to_utc(datetime.fromisoformat(raw))
    except Exception:
        pass

    return datetime.now(timezone.utc)


# ------------------------------------------------------------------
# Abstract base
# ------------------------------------------------------------------


class BaseScraper(ABC):
    @abstractmethod
    def scrape_metadata(self) -> list[VideoItem] | list[ArticleItem]:
        """
        Fetch the feed and return a list of transfer model objects.
        Does NOT write to the database — that is done by ScraperService.
        """
        ...
