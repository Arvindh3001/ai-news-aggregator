"""
Pipeline — master orchestrator for the daily AI news digest.

Execution order:
  1. Scrape metadata   (all sources, fast)
  2. Enrichment        (transcripts + markdown, slow — failures are logged, not fatal)
  3. Digest generation (DigestAgent per article — failures are per-item, not fatal)
  4. Curation          (CuratorAgent scores all unsent digests)
  5. Email composition (EmailAgent generates subject + greeting)
  6. Send              (Gmail SMTP)
  7. Mark sent         (writes sent_at on every delivered digest — CRITICAL)

Failure strategy:
  - Steps 1-4 are wrapped individually.  A complete failure of scraping still
    allows leftover digests from previous runs to be curated and sent.
  - Steps 5-7 are treated as a unit: if the email fails to send, sent_at is
    NOT written so those digests will be retried tomorrow.
  - The session is closed in a `finally` block regardless of outcome.
"""
import logging

from app.agents.curator_agent import CuratedItem, load_user_profile
from app.agents.email_agent import EmailAgent
from app.database.connection import get_db_session
from app.database.repository import Repository
from app.services.digests import DigestService
from app.services.email import EmailArticle, EmailService
from app.services.scrapers import DEFAULT_YOUTUBE_CHANNELS, ScraperService

logger = logging.getLogger(__name__)

# How many top-scored articles to include in the email
_TOP_N = 10


def run_pipeline() -> None:
    """
    Execute the full daily pipeline.  Designed to be called from main.py / cron.
    Raises nothing — all errors are logged and the pipeline exits gracefully.
    """
    logger.info("=" * 60)
    logger.info("Pipeline started")
    logger.info("=" * 60)

    session = get_db_session()
    repo = Repository(session)

    try:
        # ------------------------------------------------------------------
        # Step 1 — Scrape metadata
        # ------------------------------------------------------------------
        try:
            scraper_service = ScraperService(repo, youtube_channels=DEFAULT_YOUTUBE_CHANNELS)
            meta_summary = scraper_service.run_metadata()
            logger.info("Metadata — %s", meta_summary)
        except Exception as exc:
            logger.error("Metadata scraping failed: %s", exc)

        # ------------------------------------------------------------------
        # Step 2 — Enrichment (transcripts + markdown)
        # ------------------------------------------------------------------
        try:
            enrich_summary = scraper_service.run_enrichment()
            logger.info("Enrichment — %s", enrich_summary)
        except Exception as exc:
            logger.error("Enrichment failed: %s", exc)

        # ------------------------------------------------------------------
        # Step 3 — Digest generation
        # ------------------------------------------------------------------
        try:
            digest_service = DigestService(repo)
            gen_summary = digest_service.run_generation()
            logger.info("Generation — %s", gen_summary)
        except Exception as exc:
            logger.error("Digest generation failed: %s", exc)

        # ------------------------------------------------------------------
        # Step 4 — Curation
        # ------------------------------------------------------------------
        profile = load_user_profile("profiles/user_profile.json")
        try:
            ranked: list[CuratedItem] = digest_service.run_curation(profile)
        except Exception as exc:
            logger.error("Curation failed: %s", exc)
            ranked = []

        if not ranked:
            logger.warning("No curated digests available — skipping email for today.")
            return

        # ------------------------------------------------------------------
        # Step 5 — Build email article list (top-N)
        # ------------------------------------------------------------------
        top_curated = ranked[:_TOP_N]
        top_digest_ids = [item.digest_id for item in top_curated]

        # Fetch full Digest rows so we have title/summary/category
        digests_by_id = {d.id: d for d in repo.get_digests_by_ids(top_digest_ids)}

        # Build the reasoning lookup from curation
        reasoning_by_id = {item.digest_id: item.reasoning for item in top_curated}

        # Assemble EmailArticle objects in ranked order
        email_articles: list[EmailArticle] = []
        for item in top_curated:
            digest = digests_by_id.get(item.digest_id)
            if not digest:
                logger.warning("Digest id=%d not found — skipping from email", item.digest_id)
                continue
            source_url = repo.get_source_url(digest.article_id, digest.article_type)
            email_articles.append(
                EmailArticle(
                    title=digest.digest_title,
                    summary=digest.digest_summary,
                    category=digest.category,
                    source_url=source_url,
                    score=item.score,
                    article_type=digest.article_type,
                )
            )

        if not email_articles:
            logger.warning("Email article list is empty after assembly — aborting.")
            return

        # ------------------------------------------------------------------
        # Step 6 — Generate email prose (subject, greeting, sign-off)
        # ------------------------------------------------------------------
        email_agent = EmailAgent()
        try:
            email_content = email_agent.generate(
                reader_name=profile.name,
                reader_background=profile.background,
                top_articles=[
                    {
                        "title": a.title,
                        "category": a.category,
                        "summary": a.summary,
                    }
                    for a in email_articles
                ],
            )
        except Exception as exc:
            logger.error("EmailAgent failed: %s", exc)
            return

        # ------------------------------------------------------------------
        # Step 7 — Send email
        # ------------------------------------------------------------------
        email_service = EmailService()
        try:
            email_service.send_digest(email_content, email_articles, profile.name)
        except Exception as exc:
            logger.error("Email send failed: %s — sent_at will NOT be written", exc)
            return

        # ------------------------------------------------------------------
        # Step 8 — Mark digests as sent (only reached if send succeeded)
        # ------------------------------------------------------------------
        sent_ids = [a_id for a_id in top_digest_ids if a_id in digests_by_id]
        repo.mark_digests_sent(sent_ids)
        repo.commit()
        logger.info("Marked %d digest(s) as sent.", len(sent_ids))

        logger.info("=" * 60)
        logger.info("Pipeline completed successfully.")
        logger.info("=" * 60)

    except Exception as exc:
        logger.exception("Unhandled pipeline error: %s", exc)
        repo.rollback()

    finally:
        session.close()
        logger.info("DB session closed.")
