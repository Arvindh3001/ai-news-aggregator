"""
AI blog scrapers: OpenAI and Anthropic.

OpenAIScraper   — reads the official OpenAI news RSS feed.
AnthropicScraper — aggregates three Anthropic feeds (news, engineering, research)
                   and deduplicates by GUID.

fetch_article_markdown() — standalone utility: fetches a URL, strips chrome
                            (nav/header/footer/scripts), and converts the article
                            body to Markdown via html2text.  Used during enrichment
                            to populate AnthropicArticle.markdown_content.
"""
import logging
from typing import Optional

import html2text
import requests
from bs4 import BeautifulSoup

from .base import HEADERS, ArticleItem, BaseScraper, fetch_feed, parse_date

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# HTML → Markdown utility
# ------------------------------------------------------------------

_TAGS_TO_STRIP = ["script", "style", "nav", "footer", "header", "aside", "noscript"]


def _build_converter() -> html2text.HTML2Text:
    h = html2text.HTML2Text()
    h.ignore_links = False
    h.ignore_images = True
    h.ignore_emphasis = False
    h.body_width = 0  # no hard line-wrapping
    h.unicode_snob = True
    return h


_converter = _build_converter()


def fetch_article_markdown(url: str, timeout: int = 20) -> Optional[str]:
    """
    Fetch a URL, extract the main article body, and return Markdown.

    Extraction priority: <article> → <main> → element with "content" in class → <body>.
    Returns None if the request fails or Cloudflare blocks it (non-2xx after redirect).
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
    except requests.HTTPError as exc:
        logger.warning("HTTP error fetching %s: %s", url, exc)
        return None
    except requests.RequestException as exc:
        logger.warning("Network error fetching %s: %s", url, exc)
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    # Remove chrome elements that pollute the markdown output
    for tag in soup(_TAGS_TO_STRIP):
        tag.decompose()

    # Find the most specific container for article body
    main = (
        soup.find("article")
        or soup.find("main")
        or soup.find(attrs={"class": lambda c: c and "content" in " ".join(c).lower()})
        or soup.body
    )

    if main is None:
        logger.warning("Could not find article body at %s", url)
        return None

    md = _converter.handle(str(main)).strip()
    if not md:
        logger.warning("html2text produced empty output for %s", url)
        return None

    return md


# ------------------------------------------------------------------
# OpenAI scraper
# ------------------------------------------------------------------

_OPENAI_RSS = "https://openai.com/news/rss.xml"


class OpenAIScraper(BaseScraper):
    """Scrapes the official OpenAI news RSS feed (RSS 2.0)."""

    def scrape_metadata(self) -> list[ArticleItem]:
        try:
            root = fetch_feed(_OPENAI_RSS)
        except Exception as exc:
            logger.error("Failed to fetch OpenAI RSS: %s", exc)
            return []

        channel = root.find("channel")
        if channel is None:
            logger.warning("OpenAI RSS: no <channel> element found")
            return []

        items: list[ArticleItem] = []

        for elem in channel.findall("item"):
            title_el = elem.find("title")
            link_el = elem.find("link")
            guid_el = elem.find("guid")
            desc_el = elem.find("description")
            pub_el = elem.find("pubDate")

            # link and title are the bare minimum
            if title_el is None or link_el is None or pub_el is None:
                continue

            url = (link_el.text or "").strip()
            guid = (guid_el.text or "").strip() if guid_el is not None else url
            if not guid:
                guid = url

            items.append(
                ArticleItem(
                    guid=guid,
                    title=(title_el.text or "").strip(),
                    url=url,
                    description=(desc_el.text or "").strip() if desc_el is not None else None,
                    published_at=parse_date(pub_el.text or ""),
                )
            )

        logger.info("OpenAI: scraped %d articles", len(items))
        return items


# ------------------------------------------------------------------
# Anthropic scraper
# ------------------------------------------------------------------

# Anthropic does NOT publish official RSS feeds.
# We use RSS.app-generated feeds that mirror the public Anthropic blog pages.
# If these break, generate new ones at https://rss.app for:
#   https://www.anthropic.com/news
#   https://www.anthropic.com/research
_ANTHROPIC_FEEDS: dict[str, str] = {
    "news":     "https://rss.app/feeds/tvqbLl0ILhGGkHoO.xml",
    "research": "https://rss.app/feeds/WfZp0mLRvWvLgRXj.xml",
}


class AnthropicScraper(BaseScraper):
    """
    Aggregates three Anthropic RSS feeds.
    Deduplicates by GUID so a post that appears in multiple feeds is only returned once.
    """

    def scrape_metadata(self) -> list[ArticleItem]:
        all_items: list[ArticleItem] = []
        seen_guids: set[str] = set()

        for feed_name, feed_url in _ANTHROPIC_FEEDS.items():
            try:
                batch = self._parse_feed(feed_url, feed_name)
            except Exception as exc:
                # One feed failing should not stop the others
                logger.warning("Anthropic '%s' feed error: %s", feed_name, exc)
                continue

            for item in batch:
                if item.guid not in seen_guids:
                    seen_guids.add(item.guid)
                    all_items.append(item)

        logger.info("Anthropic: scraped %d articles across all feeds", len(all_items))
        return all_items

    # ------------------------------------------------------------------

    def _parse_feed(self, url: str, feed_name: str) -> list[ArticleItem]:
        root = fetch_feed(url)

        channel = root.find("channel")
        if channel is None:
            logger.warning("Anthropic '%s': no <channel> element", feed_name)
            return []

        items: list[ArticleItem] = []

        for elem in channel.findall("item"):
            title_el = elem.find("title")
            link_el = elem.find("link")
            guid_el = elem.find("guid")
            desc_el = elem.find("description")
            pub_el = elem.find("pubDate")

            if title_el is None or link_el is None or pub_el is None:
                continue

            url_str = (link_el.text or "").strip()
            guid = (guid_el.text or "").strip() if guid_el is not None else url_str
            if not guid:
                guid = url_str

            items.append(
                ArticleItem(
                    guid=guid,
                    title=(title_el.text or "").strip(),
                    url=url_str,
                    description=(desc_el.text or "").strip() if desc_el is not None else None,
                    published_at=parse_date(pub_el.text or ""),
                )
            )

        return items
