"""
DigestService — two-phase AI processing pipeline.

Phase 1  run_generation():
  Query all enriched articles that have no digest yet, call DigestAgent for each,
  and persist the result.  Each item is committed individually so a single API
  error does not roll back the whole batch.

  Sources processed (in order):
    1. YouTube videos with transcript_status = 'done'
    2. OpenAI articles  (uses description field as content)
    3. Anthropic articles with markdown_content populated

Phase 2  run_curation(profile):
  Load today's unsent digests, call CuratorAgent to score them against the user
  profile, write the scores back to the DB, and return the ranked list ready
  for the EmailAgent.

Usage from pipeline.py:
    from app.services.digests import DigestService
    from app.agents.curator_agent import load_user_profile

    profile = load_user_profile("profiles/user_profile.json")
    service = DigestService(repo)
    service.run_generation()
    ranked = service.run_curation(profile)
"""
import logging

from app.agents.curator_agent import CandidateDigest, CuratorAgent, CuratedItem, UserProfile
from app.agents.digest_agent import DigestAgent
from app.database.models import AnthropicArticle, OpenAIArticle, YouTubeVideo
from app.database.repository import Repository

logger = logging.getLogger(__name__)

# Minimum content length to bother calling the DigestAgent.
# Avoids wasting API calls on empty descriptions.
_MIN_CONTENT_CHARS = 50


class DigestService:
    """
    Orchestrates digest generation and curation.

    Args:
        repo: Injected Repository (session lifecycle managed by caller / pipeline).
    """

    def __init__(self, repo: Repository) -> None:
        self._repo = repo
        self._digest_agent = DigestAgent()
        self._curator_agent = CuratorAgent()

    # ------------------------------------------------------------------
    # Phase 1 — Generation
    # ------------------------------------------------------------------

    def run_generation(self) -> dict[str, int]:
        """
        Generate digests for all enriched articles that don't have one yet.

        Returns:
            {"youtube": N, "openai": N, "anthropic": N, "failed": N}
        """
        summary = {"youtube": 0, "openai": 0, "anthropic": 0, "failed": 0}

        # --- YouTube ---
        videos: list[YouTubeVideo] = self._repo.get_videos_without_digests()
        logger.info("DigestService: %d YouTube video(s) need digests", len(videos))
        for video in videos:
            if not video.transcript or len(video.transcript) < _MIN_CONTENT_CHARS:
                logger.warning("Skipping video %s — transcript too short or missing", video.video_id)
                continue
            if self._generate_and_save(
                article_id=video.id,
                article_type="youtube",
                article_title=video.title,
                content=video.transcript,
                source_type="youtube",
            ):
                summary["youtube"] += 1
            else:
                summary["failed"] += 1

        # --- OpenAI ---
        openai_articles: list[OpenAIArticle] = self._repo.get_openai_articles_without_digests()
        logger.info("DigestService: %d OpenAI article(s) need digests", len(openai_articles))
        for article in openai_articles:
            content = article.description or ""
            if len(content) < _MIN_CONTENT_CHARS:
                logger.warning("Skipping OpenAI article '%s' — description too short", article.title)
                continue
            if self._generate_and_save(
                article_id=article.id,
                article_type="openai",
                article_title=article.title,
                content=content,
                source_type="openai",
            ):
                summary["openai"] += 1
            else:
                summary["failed"] += 1

        # --- Anthropic ---
        anthropic_articles: list[AnthropicArticle] = (
            self._repo.get_anthropic_articles_without_digests()
        )
        logger.info(
            "DigestService: %d Anthropic article(s) need digests", len(anthropic_articles)
        )
        for article in anthropic_articles:
            content = article.markdown_content or ""
            if len(content) < _MIN_CONTENT_CHARS:
                logger.warning(
                    "Skipping Anthropic article '%s' — markdown missing or too short", article.title
                )
                continue
            if self._generate_and_save(
                article_id=article.id,
                article_type="anthropic",
                article_title=article.title,
                content=content,
                source_type="anthropic",
            ):
                summary["anthropic"] += 1
            else:
                summary["failed"] += 1

        logger.info(
            "Generation complete — YouTube=%d  OpenAI=%d  Anthropic=%d  Failed=%d",
            summary["youtube"],
            summary["openai"],
            summary["anthropic"],
            summary["failed"],
        )
        return summary

    def _generate_and_save(
        self,
        article_id: int,
        article_type: str,
        article_title: str,
        content: str,
        source_type: str,
    ) -> bool:
        """
        Call DigestAgent and persist the result.  Commits individually.

        Returns True on success, False on any error.
        """
        try:
            item = self._digest_agent.generate(
                article_title=article_title,
                content=content,
                source_type=source_type,
            )
            self._repo.add_digest(
                {
                    "article_id": article_id,
                    "article_type": article_type,
                    "digest_title": item.title,
                    "digest_summary": item.summary,
                    "category": item.category,
                    "score": 0.0,  # placeholder; overwritten by run_curation()
                }
            )
            self._repo.commit()
            logger.info("Digest created for %s article_id=%d: '%s'", article_type, article_id, item.title)
            return True

        except Exception as exc:
            self._repo.rollback()
            logger.error(
                "Failed to generate digest for %s article_id=%d ('%s'): %s",
                article_type,
                article_id,
                article_title,
                exc,
            )
            return False

    # ------------------------------------------------------------------
    # Phase 2 — Curation
    # ------------------------------------------------------------------

    def run_curation(
        self,
        profile: UserProfile,
        hours: int = 24,
        limit: int = 20,
    ) -> list[CuratedItem]:
        """
        Score unsent digests from the last `hours` hours against the user profile,
        write scores to the DB, and return the ranked list.

        Args:
            profile: The reader's interest profile.
            hours:   Look-back window for unsent digests (default 24h).
            limit:   Max candidates to pass to the CuratorAgent (default 20).

        Returns:
            CuratedItems sorted by score descending (same list the EmailAgent uses).
        """
        digests = self._repo.get_unsent_digests(hours=hours, limit=limit)
        if not digests:
            logger.info("Curation: no unsent digests found in the last %dh", hours)
            return []

        logger.info("Curation: scoring %d digest(s) for %s", len(digests), profile.name)

        candidates = [
            CandidateDigest(
                digest_id=d.id,
                title=d.digest_title,
                summary=d.digest_summary,
                category=d.category,
            )
            for d in digests
        ]

        try:
            ranked = self._curator_agent.curate(candidates, profile)
        except Exception as exc:
            logger.error("CuratorAgent failed: %s — returning digests unranked", exc)
            return []

        # Write scores back to DB
        score_map = {item.digest_id: item.score for item in ranked}
        for digest in digests:
            new_score = score_map.get(digest.id)
            if new_score is not None:
                digest.score = new_score

        try:
            self._repo.commit()
        except Exception as exc:
            self._repo.rollback()
            logger.error("Failed to persist curation scores: %s", exc)

        logger.info(
            "Curation complete — top item: '%s' (score=%.2f)",
            ranked[0].digest_id if ranked else "n/a",
            ranked[0].score if ranked else 0.0,
        )
        return ranked
