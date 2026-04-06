from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AnthropicArticle, Digest, OpenAIArticle, YouTubeVideo


class Repository:
    def __init__(self, session: Session) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # YouTube
    # ------------------------------------------------------------------

    def add_youtube_video(self, video_data: dict) -> tuple[YouTubeVideo, bool]:
        """Insert a video row. Returns (video, created) — created=False if it already existed."""
        stmt = select(YouTubeVideo).where(YouTubeVideo.video_id == video_data["video_id"])
        existing = self.session.execute(stmt).scalar_one_or_none()
        if existing:
            return existing, False

        video = YouTubeVideo(**video_data)
        self.session.add(video)
        self.session.flush()  # populate video.id without committing
        return video, True

    def get_pending_transcripts(self) -> list[YouTubeVideo]:
        """Videos that have been saved but whose transcripts have not yet been fetched."""
        stmt = select(YouTubeVideo).where(YouTubeVideo.transcript_status == "pending")
        return list(self.session.execute(stmt).scalars())

    def update_transcript(
        self, video_id: str, transcript: Optional[str], status: str
    ) -> None:
        """Set transcript text and status (done | unavailable) for a given video_id."""
        stmt = select(YouTubeVideo).where(YouTubeVideo.video_id == video_id)
        video = self.session.execute(stmt).scalar_one_or_none()
        if video:
            video.transcript = transcript
            video.transcript_status = status
            self.session.flush()

    def get_videos_without_digests(self) -> list[YouTubeVideo]:
        """Done-transcript videos that do not yet have a digest row."""
        stmt = (
            select(YouTubeVideo)
            .where(YouTubeVideo.transcript_status == "done")
            .where(
                ~select(Digest)
                .where(
                    Digest.article_id == YouTubeVideo.id,
                    Digest.article_type == "youtube",
                )
                .correlate(YouTubeVideo)
                .exists()
            )
        )
        return list(self.session.execute(stmt).scalars())

    # ------------------------------------------------------------------
    # OpenAI articles
    # ------------------------------------------------------------------

    def add_openai_article(self, article_data: dict) -> tuple[OpenAIArticle, bool]:
        stmt = select(OpenAIArticle).where(OpenAIArticle.guid == article_data["guid"])
        existing = self.session.execute(stmt).scalar_one_or_none()
        if existing:
            return existing, False

        article = OpenAIArticle(**article_data)
        self.session.add(article)
        self.session.flush()
        return article, True

    def get_openai_articles_without_digests(self) -> list[OpenAIArticle]:
        stmt = (
            select(OpenAIArticle)
            .where(
                ~select(Digest)
                .where(
                    Digest.article_id == OpenAIArticle.id,
                    Digest.article_type == "openai",
                )
                .correlate(OpenAIArticle)
                .exists()
            )
        )
        return list(self.session.execute(stmt).scalars())

    # ------------------------------------------------------------------
    # Anthropic articles
    # ------------------------------------------------------------------

    def add_anthropic_article(self, article_data: dict) -> tuple[AnthropicArticle, bool]:
        stmt = select(AnthropicArticle).where(AnthropicArticle.guid == article_data["guid"])
        existing = self.session.execute(stmt).scalar_one_or_none()
        if existing:
            return existing, False

        article = AnthropicArticle(**article_data)
        self.session.add(article)
        self.session.flush()
        return article, True

    def update_anthropic_markdown(self, article_id: int, markdown_content: str) -> None:
        stmt = select(AnthropicArticle).where(AnthropicArticle.id == article_id)
        article = self.session.execute(stmt).scalar_one_or_none()
        if article:
            article.markdown_content = markdown_content
            self.session.flush()

    def get_anthropic_articles_pending_markdown(self) -> list[AnthropicArticle]:
        """Articles whose HTML has not yet been converted to Markdown."""
        stmt = select(AnthropicArticle).where(AnthropicArticle.markdown_content.is_(None))
        return list(self.session.execute(stmt).scalars())

    def get_anthropic_articles_without_digests(self) -> list[AnthropicArticle]:
        stmt = (
            select(AnthropicArticle)
            .where(
                ~select(Digest)
                .where(
                    Digest.article_id == AnthropicArticle.id,
                    Digest.article_type == "anthropic",
                )
                .correlate(AnthropicArticle)
                .exists()
            )
        )
        return list(self.session.execute(stmt).scalars())

    # ------------------------------------------------------------------
    # Digests
    # ------------------------------------------------------------------

    def add_digest(self, digest_data: dict) -> Digest:
        digest = Digest(**digest_data)
        self.session.add(digest)
        self.session.flush()
        return digest

    def get_unsent_digests(self, hours: int = 24, limit: int = 10) -> list[Digest]:
        """Unsent digests created within the last `hours` hours, ranked by score."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        stmt = (
            select(Digest)
            .where(Digest.sent_at.is_(None))
            .where(Digest.created_at >= cutoff)
            .order_by(Digest.score.desc())
            .limit(limit)
        )
        return list(self.session.execute(stmt).scalars())

    def mark_digests_sent(self, digest_ids: list[int]) -> None:
        """Bulk-mark a list of digest IDs as sent."""
        now = datetime.now(timezone.utc)
        stmt = select(Digest).where(Digest.id.in_(digest_ids))
        digests = self.session.execute(stmt).scalars().all()
        for digest in digests:
            digest.sent_at = now
        self.session.flush()

    # ------------------------------------------------------------------
    # Session control (caller decides when to commit / rollback)
    # ------------------------------------------------------------------

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()
