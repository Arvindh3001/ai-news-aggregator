"""
ScraperService — two-stage scraping orchestrator.

Stage A (run_metadata):
  - Iterates all registered scrapers.
  - Saves new video/article rows to the DB via Repository.
  - Already-seen items are silently skipped (deduplication in Repository).

Stage B (run_enrichment):
  - Fetches transcripts for YouTube videos still in status='pending'.
  - Fetches + converts HTML → Markdown for Anthropic articles with no markdown_content yet.
  - Every item is committed individually so a single failure does not lose the whole batch.

Usage (from pipeline.py):
    from app.services.scrapers import ScraperService, DEFAULT_YOUTUBE_CHANNELS
    service = ScraperService(repo, youtube_channels=DEFAULT_YOUTUBE_CHANNELS)
    service.run_metadata()
    service.run_enrichment()
"""
import logging

from app.database.repository import Repository
from app.scrapers.ai_news import AnthropicScraper, OpenAIScraper, fetch_article_markdown
from app.scrapers.base import ArticleItem, VideoItem
from app.scrapers.youtube import YouTubeScraper

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Default YouTube channels to monitor
# Update channel IDs here to add/remove sources.
# Find a channel's ID from its "About" page or via yt-dlp.
# ------------------------------------------------------------------

DEFAULT_YOUTUBE_CHANNELS: list[tuple[str, str]] = [
    # (channel_id, display_name)
    ("UCXZCJLdBC09xxGZ6gcdrc6A", "OpenAI"),
    ("UCwLpdrzHC7CnpvRJJ3w8FqA", "Anthropic"),
    ("UCP7jMXSY2xbc3KCAE0MHQ-A", "Google DeepMind"),
]


class ScraperService:
    """
    Orchestrates metadata collection and content enrichment across all sources.

    Args:
        repo:             Injected Repository instance (session managed by caller).
        youtube_channels: List of (channel_id, name) tuples. Defaults to
                          DEFAULT_YOUTUBE_CHANNELS.
    """

    def __init__(
        self,
        repo: Repository,
        youtube_channels: list[tuple[str, str]] | None = None,
    ) -> None:
        self._repo = repo

        channels = youtube_channels or DEFAULT_YOUTUBE_CHANNELS
        self._yt_scrapers: list[YouTubeScraper] = [
            YouTubeScraper(channel_id=cid, channel_name=name) for cid, name in channels
        ]
        self._openai_scraper = OpenAIScraper()
        self._anthropic_scraper = AnthropicScraper()

    # ------------------------------------------------------------------
    # Stage A — Metadata
    # ------------------------------------------------------------------

    def run_metadata(self) -> dict[str, int]:
        """
        Fetch latest metadata from all sources and persist new rows.

        Returns a summary dict: {"youtube": N, "openai": N, "anthropic": N}
        where N is the number of *newly created* rows (existing rows are skipped).
        """
        summary = {"youtube": 0, "openai": 0, "anthropic": 0}

        # --- YouTube ---
        for scraper in self._yt_scrapers:
            items: list[VideoItem] = scraper.scrape_metadata()
            for item in items:
                _, created = self._repo.add_youtube_video(
                    {
                        "video_id": item.video_id,
                        "title": item.title,
                        "url": item.url,
                        "published_at": item.published_at,
                        "transcript_status": "pending",
                    }
                )
                if created:
                    summary["youtube"] += 1

        # --- OpenAI ---
        for item in self._openai_scraper.scrape_metadata():
            item: ArticleItem
            _, created = self._repo.add_openai_article(
                {
                    "guid": item.guid,
                    "title": item.title,
                    "url": item.url,
                    "description": item.description,
                    "published_at": item.published_at,
                }
            )
            if created:
                summary["openai"] += 1

        # --- Anthropic ---
        for item in self._anthropic_scraper.scrape_metadata():
            item: ArticleItem
            _, created = self._repo.add_anthropic_article(
                {
                    "guid": item.guid,
                    "title": item.title,
                    "url": item.url,
                    "markdown_content": None,
                    "published_at": item.published_at,
                }
            )
            if created:
                summary["anthropic"] += 1

        self._repo.commit()
        logger.info(
            "Metadata complete — new rows: YouTube=%d  OpenAI=%d  Anthropic=%d",
            summary["youtube"],
            summary["openai"],
            summary["anthropic"],
        )
        return summary

    # ------------------------------------------------------------------
    # Stage B — Enrichment
    # ------------------------------------------------------------------

    def run_enrichment(self) -> dict[str, int]:
        """
        Enrich previously saved rows that are still missing content:
          - YouTube videos with transcript_status='pending'
          - Anthropic articles with markdown_content=None

        Each item is committed individually.  A failed item is rolled back and
        logged, but processing continues for the remaining items.

        Returns a summary dict: {"transcripts_done": N, "transcripts_unavailable": N,
                                  "markdown_done": N, "markdown_failed": N}
        """
        summary = {
            "transcripts_done": 0,
            "transcripts_unavailable": 0,
            "markdown_done": 0,
            "markdown_failed": 0,
        }

        # --- YouTube transcripts ---
        pending_videos = self._repo.get_pending_transcripts()
        logger.info("Enrichment: %d video(s) need transcripts", len(pending_videos))

        # Build a map from channel_id → scraper so we reuse the same API instance
        # (and therefore the same proxy session) across all videos for that channel.
        # For videos whose channel we don't recognise, fall back to the first scraper.
        scraper_by_channel: dict[str, YouTubeScraper] = {
            s.channel_id: s for s in self._yt_scrapers
        }
        fallback_scraper = self._yt_scrapers[0] if self._yt_scrapers else YouTubeScraper("_")

        for video in pending_videos:
            # Determine which scraper handles this channel.
            # We can infer channel_id from the video URL: ?v=VIDEO_ID doesn't tell us the
            # channel, so we just use the fallback (proxy settings are the same for all).
            scraper = fallback_scraper

            try:
                text, status = scraper.fetch_transcript(video.video_id)
                self._repo.update_transcript(video.video_id, text, status)
                self._repo.commit()

                if status == "done":
                    summary["transcripts_done"] += 1
                    logger.info("Transcript saved for video %s", video.video_id)
                else:
                    summary["transcripts_unavailable"] += 1

            except Exception as exc:
                self._repo.rollback()
                logger.error(
                    "Unexpected error during transcript enrichment for %s: %s",
                    video.video_id,
                    exc,
                )
                summary["transcripts_unavailable"] += 1

        # --- Anthropic markdown ---
        pending_articles = self._repo.get_anthropic_articles_pending_markdown()
        logger.info("Enrichment: %d Anthropic article(s) need markdown", len(pending_articles))

        for article in pending_articles:
            try:
                md = fetch_article_markdown(article.url)
                if md:
                    self._repo.update_anthropic_markdown(article.id, md)
                    self._repo.commit()
                    summary["markdown_done"] += 1
                    logger.info("Markdown saved for article '%s'", article.title)
                else:
                    # fetch_article_markdown already logged the reason
                    summary["markdown_failed"] += 1

            except Exception as exc:
                self._repo.rollback()
                logger.error(
                    "Unexpected error during markdown enrichment for '%s': %s",
                    article.title,
                    exc,
                )
                summary["markdown_failed"] += 1

        logger.info(
            "Enrichment complete — transcripts: done=%d unavailable=%d | "
            "markdown: done=%d failed=%d",
            summary["transcripts_done"],
            summary["transcripts_unavailable"],
            summary["markdown_done"],
            summary["markdown_failed"],
        )
        return summary
