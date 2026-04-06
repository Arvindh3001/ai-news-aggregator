"""
YouTube scraper.

Responsibilities:
  1. scrape_metadata() — parse the channel's Atom RSS feed, return VideoItem list
  2. fetch_transcript()  — fetch transcript text via youtube-transcript-api 1.x

Transcript errors are all normalised to status='unavailable' so the pipeline
never retries an unworkable video.  A proxy is used when WEBSHARE_USERNAME /
WEBSHARE_PASSWORD are present in settings.
"""
import logging
from typing import Optional

from youtube_transcript_api import (
    CouldNotRetrieveTranscript,
    IpBlocked,
    NoTranscriptFound,
    RequestBlocked,
    TranscriptsDisabled,
    YouTubeTranscriptApi,
)
from youtube_transcript_api.proxies import WebshareProxyConfig

from app.database.connection import settings

from .base import BaseScraper, VideoItem, fetch_feed, parse_date

logger = logging.getLogger(__name__)

# YouTube Atom feed for a channel
_FEED_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

# XML namespaces present in YouTube's Atom feed
_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
}


class YouTubeScraper(BaseScraper):
    """
    Scraper for a single YouTube channel.

    Args:
        channel_id:   The 24-character YouTube channel ID (UCxxxxxxxxxxxxxxxxxxxxxxxx).
        channel_name: Human-readable label used in log messages.
    """

    def __init__(self, channel_id: str, channel_name: str = "") -> None:
        self.channel_id = channel_id
        self.channel_name = channel_name or channel_id
        self._api: Optional[YouTubeTranscriptApi] = None

    # ------------------------------------------------------------------
    # Lazy API initialisation (proxy set up once, reused across calls)
    # ------------------------------------------------------------------

    def _get_api(self) -> YouTubeTranscriptApi:
        if self._api is not None:
            return self._api

        if settings.WEBSHARE_USERNAME and settings.WEBSHARE_PASSWORD:
            proxy_config = WebshareProxyConfig(
                proxy_username=settings.WEBSHARE_USERNAME,
                proxy_password=settings.WEBSHARE_PASSWORD,
            )
            self._api = YouTubeTranscriptApi(proxy_config=proxy_config)
            logger.info(
                "[%s] Transcript API initialised with Webshare proxy", self.channel_name
            )
        else:
            self._api = YouTubeTranscriptApi()

        return self._api

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def scrape_metadata(self) -> list[VideoItem]:
        """Fetch the channel RSS feed and return non-Shorts VideoItems."""
        url = _FEED_URL.format(channel_id=self.channel_id)
        try:
            root = fetch_feed(url)
        except Exception as exc:
            logger.error("[%s] Failed to fetch RSS feed: %s", self.channel_name, exc)
            return []

        items: list[VideoItem] = []

        for entry in root.findall("atom:entry", _NS):
            video_id_el = entry.find("yt:videoId", _NS)
            link_el = entry.find("atom:link[@rel='alternate']", _NS)
            title_el = entry.find("atom:title", _NS)
            published_el = entry.find("atom:published", _NS)

            if any(el is None for el in (video_id_el, link_el, title_el, published_el)):
                continue

            video_url = (link_el.get("href") or "").strip()  # type: ignore[union-attr]

            # Skip YouTube Shorts — they have no meaningful transcript
            if "/shorts/" in video_url:
                logger.debug("[%s] Skipping Short: %s", self.channel_name, video_url)
                continue

            items.append(
                VideoItem(
                    video_id=video_id_el.text.strip(),  # type: ignore[union-attr]
                    title=title_el.text.strip(),  # type: ignore[union-attr]
                    url=video_url,
                    published_at=parse_date(published_el.text or ""),  # type: ignore[union-attr]
                )
            )

        logger.info("[%s] Scraped %d videos from RSS", self.channel_name, len(items))
        return items

    # ------------------------------------------------------------------
    # Transcript enrichment
    # ------------------------------------------------------------------

    def fetch_transcript(self, video_id: str) -> tuple[Optional[str], str]:
        """
        Fetch the English transcript for a video.

        Returns:
            (text, "done")        — transcript successfully retrieved
            (None, "unavailable") — transcript does not exist or cannot be fetched
        """
        try:
            api = self._get_api()
            fetched = api.fetch(video_id, languages=["en", "en-US", "en-GB"])
            text = " ".join(snippet.text for snippet in fetched).strip()
            if not text:
                logger.warning("[%s] Empty transcript for %s", self.channel_name, video_id)
                return None, "unavailable"
            logger.debug(
                "[%s] Transcript fetched for %s (%d chars)",
                self.channel_name,
                video_id,
                len(text),
            )
            return text, "done"

        except (NoTranscriptFound, TranscriptsDisabled):
            logger.warning(
                "[%s] No transcript available for %s", self.channel_name, video_id
            )

        except (IpBlocked, RequestBlocked) as exc:
            logger.error(
                "[%s] Blocked fetching transcript for %s: %s",
                self.channel_name,
                video_id,
                exc,
            )

        except CouldNotRetrieveTranscript as exc:
            logger.error(
                "[%s] Could not retrieve transcript for %s: %s",
                self.channel_name,
                video_id,
                exc,
            )

        except Exception as exc:
            logger.error(
                "[%s] Unexpected error fetching transcript for %s: %s",
                self.channel_name,
                video_id,
                exc,
            )

        return None, "unavailable"
